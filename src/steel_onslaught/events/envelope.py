from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from omnibase_core.models.common.model_envelope import ModelEnvelope
from pydantic import BaseModel, ConfigDict, Field, model_validator

from steel_onslaught.immutable import FrozenJSONMapping


class SOEventType(StrEnum):
    # Lifecycle
    MATCH_STARTED = "match_started"
    RUNTIME_STATUS_CHANGED = "runtime_status_changed"
    MATCH_TICK = "match_tick"
    MECH_SPAWNED = "mech_spawned"
    # Observation
    SENSOR_OBSERVATION = "sensor_observation"
    # Pilot decision (informational, emitted before intents)
    PILOT_DECISION_MADE = "pilot_decision_made"
    # LLM effect evidence (informational; fold ignores all three)
    LLM_COMPLETION_REQUESTED = "llm_completion_requested"
    LLM_COMPLETION_RESOLVED = "llm_completion_resolved"
    LLM_COMPLETION_FAILED = "llm_completion_failed"
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
    WEAPON_FIRE_REJECTED = "weapon_fire_rejected"
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
    # Card lifecycle (typed telemetry; activation remains out of scope for this
    # slice and the canonical fold treats these as no-op observations). These
    # members append to the existing protocol vocabulary to preserve ordering.
    HAND_DEALT = "hand_dealt"
    PLAN_COMMITTED = "plan_committed"
    REGISTER_RESOLVED = "register_resolved"
    CARDS_DISCARDED = "cards_discarded"
    # Live-learning promotion (append-only, same protocol-ordering discipline
    # as the card members above).  Appended to the PROMOTING match's stream
    # after MATCH_SCORED; a no-op for the canonical match fold — cross-match
    # policy state folds from it via learning.promotion_fold instead.
    POLICY_PROMOTED = "policy_promoted"
    # Objective control scoring (Phase 4, append-only).  Emitted by the
    # canonical fold once per objective per controlled round; VP state itself
    # folds from MATCH_TICK (the same derivation live and on replay), so this
    # member is telemetry for projections/frontends and a fold no-op when it
    # arrives back from the ledger — the BOILER_UPDATED discipline.
    OBJECTIVE_SCORED = "objective_scored"


class ModelSOEventSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "0.1.0"
    event_id: str = Field(min_length=26, max_length=26)  # ULID; uniqueness only
    match_id: str
    tick: int = Field(ge=0)  # primary ordering authority
    sequence_in_tick: int = Field(ge=0)  # secondary ordering authority
    producer_node: str
    subject: ModelSOEventSubject
    event_type: SOEventType
    payload: FrozenJSONMapping
    # The ONEX canonical envelope: tracing identity + causation chain.
    # entity_id is the match_id (partition key); message_id is a fresh UUID
    # per event (distinct from the application-level ULID event_id).
    envelope: ModelEnvelope

    @model_validator(mode="after")
    def _envelope_entity_matches_match_id(self) -> ModelSOEventEnvelope:
        """The envelope's entity_id (partition key) must equal the match_id."""
        if self.envelope.entity_id != self.match_id:
            raise ValueError(
                f"envelope.entity_id ({self.envelope.entity_id!r}) must equal "
                f"match_id ({self.match_id!r})"
            )
        return self

    # Read-only conveniences over the canonical composed envelope. They do not
    # define or accept a second, flat input protocol.

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
    payload: Mapping[str, Any],
    correlation_id: UUID,
    causation_id: UUID | None = None,
    event_id: str,
    message_id: UUID,
    emitted_at: datetime,
) -> ModelSOEventEnvelope:
    """Build an event with a composed ONEX envelope (the canonical factory).

    Args:
        match_id:       Match identity; becomes the envelope entity_id (partition key).
        correlation_id: The match/workflow correlation id (shared across all events
                        of one match). Generate once per match; reuse for all events.
        causation_id:   The message_id of the event that caused this one (None for
                        root events like MATCH_STARTED).
        event_id:       Injected ULID string (uniqueness).
        message_id:     Injected ONEX message UUID.
        emitted_at:     Injected tz-aware UTC datetime.
    """
    return ModelSOEventEnvelope(
        event_id=event_id,
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
            message_id=message_id,
            emitted_at=emitted_at,
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
    payload: Mapping[str, Any],
    event_id: str,
    message_id: UUID,
    emitted_at: datetime,
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
