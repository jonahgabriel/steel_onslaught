from __future__ import annotations

import json

import pytest

from steel_onslaught.ledger.codec import (
    PersistedEventFormatError,
    dump_persisted_event,
    load_persisted_event,
)
from tests.fixtures.event_samples import build_sample_envelopes


@pytest.mark.unit
def test_canonical_codec_round_trips_exact_json() -> None:
    event = next(iter(build_sample_envelopes().values()))
    blob = dump_persisted_event(event)

    assert blob == event.model_dump_json()
    assert load_persisted_event(blob) == event
    assert dump_persisted_event(load_persisted_event(blob)) == blob


@pytest.mark.unit
@pytest.mark.parametrize(
    "required_field",
    ["message_id", "correlation_id", "causation_id", "emitted_at", "entity_id"],
)
def test_codec_rejects_missing_nested_envelope_field(required_field: str) -> None:
    event = next(iter(build_sample_envelopes().values()))
    raw = json.loads(dump_persisted_event(event))
    del raw["envelope"][required_field]

    with pytest.raises(PersistedEventFormatError, match=required_field):
        load_persisted_event(json.dumps(raw))


@pytest.mark.unit
def test_codec_rejects_outer_and_nested_extras() -> None:
    event = next(iter(build_sample_envelopes().values()))
    raw = json.loads(dump_persisted_event(event))
    raw["unknown_outer"] = True
    with pytest.raises(ValueError, match="extra_forbidden"):
        load_persisted_event(json.dumps(raw))

    del raw["unknown_outer"]
    raw["envelope"]["unknown_nested"] = True
    with pytest.raises(ValueError, match="extra_forbidden"):
        load_persisted_event(json.dumps(raw))
