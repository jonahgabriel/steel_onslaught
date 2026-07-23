"""Storage-neutral ledger conformance suite.

Future adapters join ``_ADAPTERS`` and must pass these unchanged; they do not
receive a backend-specific event model or codec.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.codec import dump_persisted_event
from steel_onslaught.ledger.protocol import EventLedger
from tests.fixtures.event_samples import build_sample_envelopes
from tests.sqlite_ledger import open_sqlite_ledger

LedgerFactory = Callable[[Path], EventLedger]
_ADAPTERS: tuple[object, ...] = (pytest.param(open_sqlite_ledger, id="sqlite"),)


def _events() -> list[ModelSOEventEnvelope]:
    samples = build_sample_envelopes()
    selected = [
        samples[SOEventType.MATCH_STARTED],
        samples[SOEventType.MATCH_TICK],
        samples[SOEventType.PILOT_DECISION_MADE],
    ]
    return [
        event.model_copy(update={"tick": tick, "sequence_in_tick": sequence})
        for event, tick, sequence in (
            (selected[2], 2, 0),
            (selected[0], 0, 0),
            (selected[1], 1, 0),
        )
    ]


@pytest.mark.unit
@pytest.mark.parametrize("ledger_factory", _ADAPTERS)
def test_adapter_round_trips_canonical_events(
    ledger_factory: LedgerFactory, tmp_path: Path
) -> None:
    ledger = ledger_factory(tmp_path / "events.sqlite")
    events = _events()
    for event in events:
        ledger.append(event)

    persisted = list(ledger.read_all(events[0].match_id))
    expected = sorted(
        events, key=lambda event: (event.tick, event.sequence_in_tick, event.event_id)
    )
    assert persisted == expected
    assert [dump_persisted_event(event) for event in persisted] == [
        dump_persisted_event(event) for event in expected
    ]


@pytest.mark.unit
@pytest.mark.parametrize("ledger_factory", _ADAPTERS)
def test_adapter_read_after_uses_canonical_tick_order(
    ledger_factory: LedgerFactory, tmp_path: Path
) -> None:
    ledger = ledger_factory(tmp_path / "events.sqlite")
    events = _events()
    for event in events:
        ledger.append(event)

    assert [event.tick for event in ledger.read_after(events[0].match_id, 0)] == [1, 2]


@pytest.mark.unit
def test_ledger_contract_subscribes_to_all_37_canonical_event_topics() -> None:
    contract = (
        Path(__file__).resolve().parents[2] / "src/steel_onslaught/ledger/contract.yaml"
    ).read_text(encoding="utf-8")
    topics = {
        line.strip().removeprefix("- ")
        for line in contract.splitlines()
        if line.strip().startswith("- onex.evt.steel-onslaught.")
    }
    expected = {
        f"onex.evt.steel-onslaught.{event_type.value.replace('_', '-')}.v1"
        for event_type in SOEventType
    }

    assert len(SOEventType) == 37
    assert topics == expected
