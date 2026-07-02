from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SOEventType(StrEnum):
    # Lifecycle
    MATCH_STARTED = "match_started"
    MATCH_TICK = "match_tick"
    MECH_SPAWNED = "mech_spawned"
    # Observation
    SENSOR_OBSERVATION = "sensor_observation"
    # Pilot decision (informational, emitted before intents)
    PILOT_DECISION_MADE = "pilot_decision_made"
    # Intents — produced by the pilot tick reducer; consumed by downstream
    #           reducers which validate and either accept or reject.
    MOVE_INTENT = "move_intent"
    WEAPON_FIRE_INTENT = "weapon_fire_intent"
    MODE_SWITCH_INTENT = "mode_switch_intent"
    VENT_INTENT = "vent_intent"
    # Resolved state changes (canonical truth)
    MOVEMENT_RESOLVED = "movement_resolved"
    BOILER_UPDATED = "boiler_updated"
    HEAT_REDLINE_ENTERED = "heat_redline_entered"
    HEAT_REDLINE_EXITED = "heat_redline_exited"
    BOILER_OVERLOADED = "boiler_overloaded"
    BOILER_RUPTURED = "boiler_ruptured"
    MODE_TRANSITION_STARTED = "mode_transition_started"
    MODE_TRANSITION_COMPLETED = "mode_transition_completed"
    WEAPON_FIRED = "weapon_fired"
    HIT_RESOLVED = "hit_resolved"
    ARMOR_ABSORBED = "armor_absorbed"
    DAMAGE_APPLIED = "damage_applied"
    PILOT_INJURED = "pilot_injured"
    PILOT_KILLED = "pilot_killed"
    MECH_DESTROYED = "mech_destroyed"
    # Termination
    VICTORY_DECLARED = "victory_declared"
    MATCH_ENDED = "match_ended"
    MATCH_SCORED = "match_scored"


class ModelSOEventSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mech_id: str
    player_id: str


class ModelSOEventEnvelope(BaseModel):
    """A Steel Onslaught game event, ONEX-envelope-composed.

    Composes the OmniNode canonical ``ModelEnvelope`` (message_id /
    correlation_id / causation_id / emitted_at / entity_id) for distributed
    tracing and causation-chain replay semantics, alongside the game-specific
    ordering + payload fields the deterministic fold and frontend depend on.

    Ordering authority is ``(tick, sequence_in_tick)`` — the bus re-stamps
    these. ``emitted_at`` (on the composed envelope) is wall-clock metadata,
    excluded from ordering and from replay-validity (which compares
    ``ModelSOMatchState``, not raw envelopes). See
    docs/plans/2026-07-02-determinism-boundaries.md.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: str = "0.1.0"
    event_id: str = Field(min_length=26, max_length=26)  # ULID; uniqueness only
    match_id: str
    tick: int = Field(ge=0)  # primary ordering authority
    sequence_in_tick: int = Field(ge=0)  # secondary ordering authority
    producer_node: str
    subject: ModelSOEventSubject
    event_type: SOEventType
    payload: dict[str, Any]
    # The ONEX canonical envelope: tracing identity + causation chain.
    # entity_id is the match_id (partition key); message_id is a fresh UUID
    # per event (distinct from the ULID event_id, which is retained for
    # backward compatibility with existing ledger rows).
    envelope: ModelEnvelope

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_flat_fields(cls, data: Any) -> Any:
        """Backward-compatible construction from the pre-ONEX flat envelope shape.

        Existing callers/tests construct with the legacy fields
        ``correlation_id``/``causation_id``/``emitted_at`` (strings/scalars)
        rather than the composed ``envelope`` dict. This translates the flat
        shape into the composed ONEX envelope so those constructions keep
        working during the migration. New code should use ``make_event()``.
        """
        if not isinstance(data, dict):
            return data
        if "envelope" in data:
            return data  # already the composed shape
        legacy_corr = data.get("correlation_id")
        legacy_caus = data.get("causation_id")
        legacy_emitted = data.get("emitted_at")
        match_id = data.get("match_id")
        if match_id is None:
            return data  # let required-field validation surface the real error
        emitted_dt: datetime
        if isinstance(legacy_emitted, datetime):
            emitted_dt = legacy_emitted
        else:
            # Tolerate ISO strings and fall back to now for legacy rows.
            try:
                emitted_dt = (
                    datetime.fromisoformat(str(legacy_emitted))
                    if legacy_emitted
                    else datetime.now(UTC)
                )
            except ValueError:
                emitted_dt = datetime.now(UTC)
            if emitted_dt.tzinfo is None:
                emitted_dt = emitted_dt.replace(tzinfo=UTC)
        envelope_dict: dict[str, Any] = {
            "entity_id": str(match_id),
            "emitted_at": emitted_dt.isoformat(),
        }
        # message_id: legacy event_id is a ULID string (not a UUID); derive a
        # stable UUID from it so the ONEX message_id is deterministic per event.
        mid = data.get("event_id")
        if isinstance(mid, str) and len(mid) >= 26:
            envelope_dict["message_id"] = str(UUID(int=int.from_bytes(mid[:16].encode())))
        else:
            envelope_dict["message_id"] = str(uuid4())

        # correlation_id / causation_id: coerce legacy string UUIDs to UUID form.
        def _coerce_uuid(v: object) -> UUID | None:
            if v is None:
                return None
            if isinstance(v, UUID):
                return v
            try:
                return UUID(str(v))
            except (ValueError, AttributeError):
                # Not a UUID string (e.g. a match id) — derive a stable UUID.
                return UUID(int=hash(str(v)) & ((1 << 128) - 1))

        envelope_dict["correlation_id"] = str(
            _coerce_uuid(legacy_corr if legacy_corr is not None else match_id)
        )
        caus = _coerce_uuid(legacy_caus)
        if caus is not None:
            envelope_dict["causation_id"] = str(caus)
        data = {
            k: v
            for k, v in data.items()
            if k not in {"correlation_id", "causation_id", "emitted_at"}
        }
        data["envelope"] = envelope_dict
        return data

    @model_validator(mode="after")
    def _envelope_entity_matches_match_id(self) -> ModelSOEventEnvelope:
        """The envelope's entity_id (partition key) must equal the match_id."""
        if self.envelope.entity_id != self.match_id:
            raise ValueError(
                f"envelope.entity_id ({self.envelope.entity_id!r}) must equal "
                f"match_id ({self.match_id!r})"
            )
        return self

    # -- Backward-compatible accessors delegating to the composed envelope --
    # These keep the 165 existing field reads working during the ONEX migration;
    # the legacy string-typed correlation_id/causation_id/emitted_at are derived
    # from the canonical UUID/datetime values on the envelope.

    @property
    def correlation_id(self) -> UUID:
        """Workflow correlation id (delegates to the ONEX envelope)."""
        return self.envelope.correlation_id

    @property
    def causation_id(self) -> UUID | None:
        """Parent message id that caused this one (delegates to ONEX envelope)."""
        return self.envelope.causation_id

    @property
    def emitted_at(self) -> str:
        """Wall-clock metadata ISO string (delegates to ONEX envelope)."""
        return self.envelope.emitted_at.isoformat()


# ---------------------------------------------------------------------------
# Construction factories (ONEX-envelope-aware)
# ---------------------------------------------------------------------------
#
# Centralized so every event carries a correctly-linked ONEX ModelEnvelope
# (correlation_id shared across a match; causation_id linking causes). The
# non-deterministic inputs (event_id ULID, message UUID, emitted_at) are
# generated here — the single effect-boundary site — so the pure fold and
# reducers stay free of clock/UUID reads (the ONEX purity discipline).
#
# For replay determinism, the ledger persists the full envelope and reloads it
# verbatim; same-seed replayability is asserted at the state level
# (verify_replay_validity), not at the envelope level (see
# docs/plans/2026-07-02-determinism-boundaries.md).


def make_event(
    *,
    match_id: str,
    tick: int,
    sequence_in_tick: int,
    event_type: SOEventType,
    producer_node: str,
    subject: ModelSOEventSubject,
    payload: dict[str, Any],
    correlation_id: UUID,
    causation_id: UUID | None = None,
    event_id: str | None = None,
    message_id: UUID | None = None,
    emitted_at: datetime | None = None,
) -> ModelSOEventEnvelope:
    """Build an event with a composed ONEX envelope (the canonical factory).

    Args:
        match_id:       Match identity; becomes the envelope entity_id (partition key).
        correlation_id: The match/workflow correlation id (shared across all events
                        of one match). Generate once per match; reuse for all events.
        causation_id:   The message_id of the event that caused this one (None for
                        root events like MATCH_STARTED).
        event_id:       ULID string (uniqueness). Generated if omitted.
        message_id:     ONEX message UUID. Generated if omitted.
        emitted_at:     tz-aware UTC datetime. Generated if omitted.
    """
    _now = emitted_at if emitted_at is not None else datetime.now(UTC)
    _msg = message_id if message_id is not None else uuid4()
    return ModelSOEventEnvelope(
        event_id=event_id if event_id is not None else ulid.new().str,
        match_id=match_id,
        tick=tick,
        sequence_in_tick=sequence_in_tick,
        producer_node=producer_node,
        subject=subject,
        event_type=event_type,
        payload=payload,
        envelope=ModelEnvelope(
            correlation_id=correlation_id,
            causation_id=causation_id,
            entity_id=match_id,
            message_id=_msg,
            emitted_at=_now,
        ),
    )


def caused_by(
    parent: ModelSOEventEnvelope,
    *,
    match_id: str,
    tick: int,
    sequence_in_tick: int,
    event_type: SOEventType,
    producer_node: str,
    subject: ModelSOEventSubject,
    payload: dict[str, Any],
    event_id: str | None = None,
    message_id: UUID | None = None,
    emitted_at: datetime | None = None,
) -> ModelSOEventEnvelope:
    """Build an event caused by *parent* — inherits correlation_id, links causation.

    Use this when one event directly causes another (e.g. WEAPON_FIRED is caused
    by the WEAPON_FIRE_INTENT that triggered it). The child shares the parent's
    correlation_id (same match workflow) and sets causation_id to the parent's
    message_id.
    """
    return make_event(
        match_id=match_id,
        tick=tick,
        sequence_in_tick=sequence_in_tick,
        event_type=event_type,
        producer_node=producer_node,
        subject=subject,
        payload=payload,
        correlation_id=parent.envelope.correlation_id,
        causation_id=parent.envelope.message_id,
        event_id=event_id,
        message_id=message_id,
        emitted_at=emitted_at,
    )
