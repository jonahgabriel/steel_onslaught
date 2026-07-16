from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope
from pydantic import ValidationError

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)

_CORR = uuid4()
_CAUS = uuid4()


def _coerce_uuid(v: object) -> UUID:
    """Coerce a str/UUID override into a real UUID (matches ONEX coercion)."""
    if isinstance(v, UUID):
        return v
    return UUID(str(v))


def _envelope(
    match_id: str = "match.2026-04-30.001",
    emitted_at: datetime = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
) -> ModelEnvelope:
    """Composed ONEX ModelEnvelope (message_id/correlation_id/causation_id/entity_id/emitted_at)."""
    return ModelEnvelope(
        message_id=uuid4(),
        correlation_id=_CORR,
        causation_id=_CAUS,
        entity_id=match_id,
        emitted_at=emitted_at,
    )


def _base_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return a valid set of kwargs for ModelSOEventEnvelope with optional overrides.

    Legacy ``correlation_id``/``causation_id``/``emitted_at`` overrides are routed
    into the composed ``envelope`` ModelEnvelope (matching the ONEX migration).
    """
    # ULID is 26 chars (10-char timestamp + 16-char random, Crockford base32)
    match_id = overrides.get("match_id", "match.2026-04-30.001")
    correlation_id = _CORR
    causation_id: UUID | None = _CAUS
    emitted_at = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC)
    if "correlation_id" in overrides:
        correlation_id = _coerce_uuid(overrides.pop("correlation_id"))
    if "causation_id" in overrides:
        caus = overrides.pop("causation_id")
        causation_id = None if caus is None else _coerce_uuid(caus)
    if "emitted_at" in overrides:
        emitted_at = datetime.fromisoformat(str(overrides.pop("emitted_at")))
    envelope = ModelEnvelope(
        message_id=uuid4(),
        correlation_id=correlation_id,
        causation_id=causation_id,
        entity_id=match_id,
        emitted_at=emitted_at,
    )
    base: dict[str, Any] = {
        "event_id": "01JABCDE0123456789ABCDEFGX",  # 26 chars
        "match_id": match_id,
        "tick": 42,
        "sequence_in_tick": 0,
        "event_type": SOEventType.PILOT_DECISION_MADE,
        "producer_node": "node.pilot.red.01",
        "subject": {"mech_id": "mech.red.01", "player_id": "player.17"},
        "payload": {"action": "vent"},
        "envelope": envelope,
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_envelope_round_trip() -> None:
    env = ModelSOEventEnvelope(**_base_kwargs())
    blob = env.model_dump_json()
    parsed = ModelSOEventEnvelope.model_validate_json(blob)
    assert parsed == env


@pytest.mark.unit
def test_envelope_rejects_unknown_field() -> None:
    """Canonical event contracts fail closed on undeclared top-level fields."""
    with pytest.raises(ValidationError) as exc_info:
        ModelSOEventEnvelope(**_base_kwargs(unexpected_contract_field=True))

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


@pytest.mark.unit
@pytest.mark.parametrize("flat_field", ["correlation_id", "causation_id", "emitted_at"])
def test_envelope_rejects_legacy_flat_fields(flat_field: str) -> None:
    raw = _base_kwargs()
    raw[flat_field] = "legacy-flat-value"
    with pytest.raises(ValidationError) as exc_info:
        ModelSOEventEnvelope.model_validate(raw)

    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == (flat_field,)
        for error in exc_info.value.errors()
    )


@pytest.mark.unit
def test_nested_envelope_rejects_unknown_field() -> None:
    raw = _base_kwargs()
    raw["envelope"] = raw["envelope"].model_dump(mode="json")
    raw["envelope"]["unexpected_nested_field"] = True
    with pytest.raises(ValidationError) as exc_info:
        ModelSOEventEnvelope.model_validate(raw)

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


@pytest.mark.unit
def test_envelope_rejects_negative_tick() -> None:
    with pytest.raises((ValueError, ValidationError)):
        ModelSOEventEnvelope(
            event_id="01JABCDE0123456789ABCDEFGX",
            match_id="m",
            tick=-1,
            sequence_in_tick=0,
            event_type=SOEventType.MATCH_STARTED,
            producer_node="p",
            subject=ModelSOEventSubject(mech_id="m", player_id="p"),
            payload={},
            envelope=_envelope(match_id="m"),
        )


@pytest.mark.unit
def test_event_id_must_be_26_chars() -> None:
    # Too short
    with pytest.raises((ValueError, ValidationError)):
        ModelSOEventEnvelope(**_base_kwargs(event_id="TOOSHORT"))
    # Too long
    with pytest.raises((ValueError, ValidationError)):
        ModelSOEventEnvelope(**_base_kwargs(event_id="01JABCDE0123456789ABCDEFGH_TOO_LONG"))


@pytest.mark.unit
def test_event_id_exactly_26_chars_accepted() -> None:
    env = ModelSOEventEnvelope(**_base_kwargs(event_id="01JABCDE0123456789ABCDEFGX"))
    assert len(env.event_id) == 26


@pytest.mark.unit
def test_sequence_in_tick_non_negative() -> None:
    # Zero is valid
    env = ModelSOEventEnvelope(**_base_kwargs(sequence_in_tick=0))
    assert env.sequence_in_tick == 0
    # Positive is valid
    env2 = ModelSOEventEnvelope(**_base_kwargs(sequence_in_tick=5))
    assert env2.sequence_in_tick == 5
    # Negative is rejected
    with pytest.raises((ValueError, ValidationError)):
        ModelSOEventEnvelope(**_base_kwargs(sequence_in_tick=-1))


@pytest.mark.unit
def test_subject_validates_mech_and_player_id() -> None:
    subj = ModelSOEventSubject(mech_id="mech.red.01", player_id="player.17")
    env = ModelSOEventEnvelope(**_base_kwargs(subject=subj))
    assert env.subject.mech_id == "mech.red.01"
    assert env.subject.player_id == "player.17"


@pytest.mark.unit
def test_subject_as_dict_coerced() -> None:
    env = ModelSOEventEnvelope(**_base_kwargs(subject={"mech_id": "m1", "player_id": "p1"}))
    assert isinstance(env.subject, ModelSOEventSubject)
    assert env.subject.mech_id == "m1"


@pytest.mark.unit
def test_event_type_known_enum_values() -> None:
    # MODE_SWITCH_INTENT and WEAPON_FIRE_INTENT are required by the plan
    env1 = ModelSOEventEnvelope(**_base_kwargs(event_type=SOEventType.MODE_SWITCH_INTENT))
    assert env1.event_type == SOEventType.MODE_SWITCH_INTENT

    env2 = ModelSOEventEnvelope(**_base_kwargs(event_type=SOEventType.WEAPON_FIRE_INTENT))
    assert env2.event_type == SOEventType.WEAPON_FIRE_INTENT


@pytest.mark.unit
def test_event_type_unknown_rejected() -> None:
    with pytest.raises((ValueError, ValidationError)):
        ModelSOEventEnvelope(**_base_kwargs(event_type="not_a_real_event_type"))


@pytest.mark.unit
def test_schema_version_defaults_to_010() -> None:
    env = ModelSOEventEnvelope(**_base_kwargs())
    assert env.schema_version == "0.1.0"


@pytest.mark.unit
def test_causation_id_round_trips() -> None:
    """causation_id is now a UUID on the composed ONEX envelope; round-trips via JSON."""
    from uuid import uuid4

    cause = uuid4()
    env = ModelSOEventEnvelope(**_base_kwargs(causation_id=str(cause)))
    blob = env.model_dump_json()
    parsed = ModelSOEventEnvelope.model_validate_json(blob)
    assert parsed.causation_id == cause
    assert parsed == env


@pytest.mark.unit
def test_optional_ids_can_be_none() -> None:
    """correlation_id is always present (UUID); causation_id is None for root events."""
    env = ModelSOEventEnvelope(**_base_kwargs(causation_id=None))
    assert env.correlation_id is not None  # always a UUID now
    assert env.causation_id is None  # root event: no parent
    blob = env.model_dump_json()
    parsed = ModelSOEventEnvelope.model_validate_json(blob)
    assert parsed == env


@pytest.mark.unit
def test_two_envelopes_same_tick_seq_different_event_id_both_accepted() -> None:
    """Uniqueness is enforced at the ledger layer, not the model layer."""
    env1 = ModelSOEventEnvelope(**_base_kwargs(event_id="01JABCDE0123456789ABCDEF1X"))
    env2 = ModelSOEventEnvelope(**_base_kwargs(event_id="01JABCDE0123456789ABCDEF2X"))
    # Both have tick=42, sequence_in_tick=0 — Pydantic accepts both
    assert env1.tick == env2.tick
    assert env1.sequence_in_tick == env2.sequence_in_tick
    assert env1.event_id != env2.event_id


@pytest.mark.unit
def test_envelope_is_frozen() -> None:
    env = ModelSOEventEnvelope(**_base_kwargs())
    with pytest.raises((TypeError, ValidationError)):
        env.tick = 99


@pytest.mark.unit
def test_all_soeventtype_variants_are_str_enum() -> None:
    """Ensure StrEnum: every variant value is a plain str."""
    for member in SOEventType:
        assert isinstance(member.value, str)
        assert member == member.value  # StrEnum equality with str
