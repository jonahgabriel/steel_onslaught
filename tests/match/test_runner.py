"""Tests for the minimal synchronous match runner — Task 28."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from tests.runtime import match_runner
from tests.sqlite_ledger import open_sqlite_ledger

LOADOUT_A = Path("contracts_data/loadouts/example_aggressive_light.yaml")
LOADOUT_B = Path("contracts_data/loadouts/example_predictive_heavy.yaml")

MATCH_ID = "match.2026-04-30.runner-test"


def _run_match(
    *,
    seed: int = 12345,
    max_ticks: int = 8,
    ledger: SQLiteLedger | None = None,
) -> tuple[Any, list[ModelSOEventEnvelope]]:
    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    if ledger is not None:
        bus.subscribe(ledger.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=seed,
        loadout_a=load_loadout(LOADOUT_A),
        loadout_b=load_loadout(LOADOUT_B),
        max_ticks=max_ticks,
    )
    final = runner.run()
    return final, collected


@pytest.mark.integration
def test_run_terminates_at_bound_with_draw() -> None:
    final, _events = _run_match(max_ticks=8)
    assert final.status is SOMatchStatus.ENDED
    assert final.tick == 8
    # Both mechs survive the minimal stack (no damage path wired) -> draw.
    assert final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert final.winner_id is None


@pytest.mark.integration
def test_first_event_is_match_started_recording_seed() -> None:
    _, events = _run_match(seed=777, max_ticks=3)
    first = events[0]
    assert first.event_type is SOEventType.MATCH_STARTED
    assert first.tick == 0
    assert first.payload["seed"] == 777
    assert first.payload["max_ticks"] == 3
    assert len(first.payload["mechs"]) == 2


@pytest.mark.integration
def test_match_tick_emitted_for_every_tick() -> None:
    _, events = _run_match(max_ticks=5)
    ticks = [e.tick for e in events if e.event_type is SOEventType.MATCH_TICK]
    assert ticks == [1, 2, 3, 4, 5]


@pytest.mark.integration
def test_same_seed_produces_identical_event_stream() -> None:
    _, events_one = _run_match(seed=12345, max_ticks=8)
    _, events_two = _run_match(seed=12345, max_ticks=8)

    def fingerprint(
        events: list[ModelSOEventEnvelope],
    ) -> list[tuple[int, int, SOEventType, dict[str, Any]]]:
        return [(e.tick, e.sequence_in_tick, e.event_type, e.payload) for e in events]

    assert fingerprint(events_one) == fingerprint(events_two)


@pytest.mark.integration
def test_pilot_decisions_emitted_per_living_mech_per_tick() -> None:
    _, events = _run_match(max_ticks=4)
    decisions = [e for e in events if e.event_type is SOEventType.PILOT_DECISION_MADE]
    # 2 living mechs x 4 ticks; the terminal tick (4) ends the match before
    # pilots are invoked, so 2 mechs x 3 ticks = 6 decisions.
    assert len(decisions) == 6
    assert {e.subject.mech_id for e in decisions} == {"mech.a.01", "mech.b.01"}


@pytest.mark.integration
def test_run_with_ledger_persists_all_events_in_canonical_order(tmp_path: Path) -> None:
    ledger = open_sqlite_ledger(tmp_path / "ledger.sqlite")
    _, collected = _run_match(max_ticks=5, ledger=ledger)

    persisted = list(ledger.read_all(MATCH_ID))
    assert len(persisted) == len(collected)
    assert [(e.tick, e.sequence_in_tick) for e in persisted] == [
        (e.tick, e.sequence_in_tick) for e in collected
    ]


@pytest.mark.unit
def test_unknown_pilot_archetype_fails_fast() -> None:
    loadout = load_loadout(LOADOUT_A)
    bad = loadout.model_copy(update={"pilot_id": "pilot.example.unknown_v1"})
    bus = InProcessEventBus()
    with pytest.raises(ValueError, match="unknown exact pilot_id"):
        match_runner(
            bus=bus,
            match_id=MATCH_ID,
            seed=1,
            loadout_a=bad,
            loadout_b=load_loadout(LOADOUT_B),
            max_ticks=3,
        )[0].run()
