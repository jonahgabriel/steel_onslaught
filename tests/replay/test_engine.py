"""Tests for the ReplayEngine — Task 27 invariants.

Critical invariants:
- reconstruct_at_tick(final_tick) == live_final_state (round-trip determinism)
- reconstruct_at_tick(N).tick == N for all N <= final_tick
- step_forward() then step_backward() yields the same state as reconstructing at N
- all_ticks() returns sorted list of distinct tick numbers present in the ledger
- events_at_tick(tick) returns all events with that tick, in canonical order
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.runner import MatchRunner, load_loadout
from steel_onslaught.match.state import ModelSOMatchState, SOMatchStatus
from steel_onslaught.replay.engine import ReplayEngine

LOADOUT_A = Path("contracts_data/loadouts/example_aggressive_light.yaml")
LOADOUT_B = Path("contracts_data/loadouts/example_predictive_heavy.yaml")

MATCH_ID = "match.2026-04-30.replay-test"
SEED = 12345
MAX_TICKS = 5  # short so tests run fast


def _run_and_record(
    tmp_path: Path,
    *,
    match_id: str = MATCH_ID,
    seed: int = SEED,
    max_ticks: int = MAX_TICKS,
) -> tuple[ModelSOMatchState, SQLiteLedger]:
    """Run a match and record all events to a SQLite ledger.

    Returns the live final state and an open ledger (same file) for replay.
    """
    ledger_path = tmp_path / f"{match_id}.sqlite"
    ledger = SQLiteLedger(ledger_path)
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)

    runner = MatchRunner(
        match_id=match_id,
        seed=seed,
        loadout_a=load_loadout(LOADOUT_A),
        loadout_b=load_loadout(LOADOUT_B),
        bus=bus,
        max_ticks=max_ticks,
    )
    live_state = runner.run()
    return live_state, ledger


# ---------------------------------------------------------------------------
# Round-trip determinism (the critical invariant from the plan)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_replay_reproduces_live_state(tmp_path: Path) -> None:
    """reconstruct_at_tick(final_tick) must equal the live final state exactly."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state


# ---------------------------------------------------------------------------
# reconstruct_at_tick(N).tick == N for N <= final_tick
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reconstruct_at_tick_has_correct_tick(tmp_path: Path) -> None:
    """Reconstructed state at tick N records tick == N."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)
    # Check a few intermediate ticks (match runs MAX_TICKS ticks, 0-indexed start)
    for t in range(1, live_state.tick + 1):
        state = replay.reconstruct_at_tick(t)
        assert state.tick == t, f"at tick {t}: state.tick={state.tick}"


# ---------------------------------------------------------------------------
# step_forward / step_backward round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_step_forward_then_backward_round_trips(tmp_path: Path) -> None:
    """step_forward() then step_backward() must yield the same state as
    reconstruct_at_tick(original_tick)."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)

    final_tick = live_state.tick
    # Start in the middle so both directions have room.
    mid_tick = max(1, final_tick // 2)
    state_at_mid = replay.reconstruct_at_tick(mid_tick)

    # Step stepper to mid_tick first.
    replay.reconstruct_at_tick(mid_tick)  # positions cursor at mid_tick

    # Forward then backward must return to mid_tick state.
    replay.step_forward()
    state_back = replay.step_backward()
    assert state_back.tick == mid_tick
    assert state_back == state_at_mid, (
        "step_forward+step_backward must yield the same state as reconstruct_at_tick"
    )


# ---------------------------------------------------------------------------
# all_ticks()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_all_ticks_returns_sorted_unique_list(tmp_path: Path) -> None:
    """all_ticks() returns a sorted list with no duplicates."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)
    ticks = replay.all_ticks()

    assert isinstance(ticks, list)
    assert ticks == sorted(set(ticks)), "all_ticks() must be sorted and deduplicated"
    assert ticks[0] == 0, "tick 0 (MATCH_STARTED) must be present"
    assert ticks[-1] == live_state.tick


# ---------------------------------------------------------------------------
# events_at_tick()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_events_at_tick_returns_events_in_canonical_order(tmp_path: Path) -> None:
    """events_at_tick(N) must return only events with tick==N, sorted by
    (sequence_in_tick ASC, event_id ASC)."""
    _live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)

    for tick in replay.all_ticks():
        events = replay.events_at_tick(tick)
        assert all(e.tick == tick for e in events), (
            f"events_at_tick({tick}) returned events with wrong tick numbers"
        )
        # Verify canonical ordering within the tick.
        seqs = [(e.sequence_in_tick, e.event_id) for e in events]
        assert seqs == sorted(seqs), (
            f"events_at_tick({tick}) not in canonical (sequence_in_tick, event_id) order"
        )


@pytest.mark.integration
def test_events_at_tick_returns_empty_for_nonexistent_tick(tmp_path: Path) -> None:
    """events_at_tick() for a tick not in the ledger returns an empty list."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)
    result = replay.events_at_tick(live_state.tick + 9999)
    assert result == []


# ---------------------------------------------------------------------------
# step_forward / step_backward boundary conditions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_step_forward_at_final_tick_returns_same_state(tmp_path: Path) -> None:
    """step_forward() at the last tick must return the same (final) state."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)
    replay.reconstruct_at_tick(live_state.tick)  # position at end
    at_end = replay.step_forward()
    assert at_end.status is SOMatchStatus.ENDED
    assert at_end.tick == live_state.tick  # cannot advance past end


@pytest.mark.integration
def test_step_backward_at_tick_zero_returns_same_state(tmp_path: Path) -> None:
    """step_backward() at tick 0 must not go below 0."""
    _live_state, ledger = _run_and_record(tmp_path)
    replay = ReplayEngine(ledger, match_id=MATCH_ID)
    replay.reconstruct_at_tick(0)  # position at start
    at_start = replay.step_backward()
    assert at_start.tick == 0  # cannot go below 0
