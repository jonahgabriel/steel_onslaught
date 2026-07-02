"""Tests for the match lifecycle reducer — Task 18 invariants."""

from __future__ import annotations

from typing import Any

import pytest
import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.state import (
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle

MATCH_ID = "match.2026-04-30.test"

_LIFECYCLE_TYPES = [
    SOEventType.MATCH_STARTED,
    SOEventType.MATCH_TICK,
    SOEventType.VICTORY_DECLARED,
    SOEventType.MATCH_ENDED,
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _boiler(mech_id: str) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=MATCH_ID,
        mech_id=mech_id,
        tick=0,
        pressure_current=60,
        pressure_maximum=90,
        regeneration_per_tick=3,
        heat_current=0,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=4,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _mech(mech_id: str, player_id: str, *, alive: bool = True) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=player_id,
        loadout_id="loadout.example.aggressive_light",
        pilot_id="pilot.aggressive.01",
        chassis_id="chassis.light.scout_mk1",
        chassis_class="light",
        base_speed=4,
        position=ModelSOPosition(x=0, y=0),
        facing=0,
        speed=4,
        hp=100,
        hp_max=100,
        armor_value=10,
        armor_max=10,
        alive=alive,
        current_mode="recon",
        weapon_cooldowns={"weapon.machine_gun": 0},
        boiler=_boiler(mech_id),
    )


def _envelope(
    event_type: SOEventType,
    payload: dict[str, Any],
    tick: int = 0,
    match_id: str = MATCH_ID,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=match_id,
        tick=tick,
        sequence_in_tick=0,
        event_type=event_type,
        producer_node="node.test.driver",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        payload=payload,
        emitted_at="2026-04-30T16:00:00Z",
    )


def _started(
    mechs: list[ModelSOMechRuntimeState] | None = None,
    seed: int = 42,
    max_ticks: int | None = None,
) -> ModelSOEventEnvelope:
    if mechs is None:
        mechs = [_mech("mech.red.01", "player.red"), _mech("mech.blue.01", "player.blue")]
    payload: dict[str, Any] = {
        "seed": seed,
        "mechs": [m.model_dump(mode="json") for m in mechs],
    }
    if max_ticks is not None:
        payload["max_ticks"] = max_ticks
    return _envelope(SOEventType.MATCH_STARTED, payload)


def _tick(tick: int) -> ModelSOEventEnvelope:
    return _envelope(SOEventType.MATCH_TICK, {}, tick=tick)


def _victory(
    winner_player_id: str = "player.red",
    reason: str = "last_mech_standing",
) -> ModelSOEventEnvelope:
    return _envelope(
        SOEventType.VICTORY_DECLARED,
        {"winner_player_id": winner_player_id, "reason": reason},
    )


# ---------------------------------------------------------------------------
# MATCH_STARTED
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_started_initializes_state() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    state = reducer.apply(_started(seed=1234, max_ticks=50))
    assert state.status is SOMatchStatus.RUNNING
    assert state.seed == 1234
    assert state.max_ticks == 50
    assert state.tick == 0
    assert set(state.mech_states) == {"mech.red.01", "mech.blue.01"}
    assert state.mech_states["mech.red.01"].player_id == "player.red"


@pytest.mark.unit
def test_match_started_default_max_ticks_is_200() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    state = reducer.apply(_started())
    assert state.max_ticks == 200


@pytest.mark.unit
def test_duplicate_match_started_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    with pytest.raises(ReducerError, match="match_already_started"):
        reducer.apply(_started())


@pytest.mark.unit
def test_match_id_mismatch_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    with pytest.raises(ReducerError, match="match_id_mismatch"):
        reducer.apply(_envelope(SOEventType.MATCH_STARTED, {"seed": 1}, match_id="match.other"))


# ---------------------------------------------------------------------------
# MATCH_TICK
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_tick_on_pending_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    with pytest.raises(ReducerError, match="match_not_running"):
        reducer.apply(_tick(1))


@pytest.mark.unit
def test_match_tick_on_ended_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    reducer.apply(_victory())
    with pytest.raises(ReducerError, match="match_not_running"):
        reducer.apply(_tick(1))


@pytest.mark.unit
def test_tick_increments_exactly_plus_one() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    for t in (1, 2, 3):
        state = reducer.apply(_tick(t))
        assert state.tick == t
    assert reducer.state.status is SOMatchStatus.RUNNING


@pytest.mark.unit
def test_tick_skip_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    reducer.apply(_tick(1))
    with pytest.raises(ReducerError, match="tick_skip"):
        reducer.apply(_tick(3))


@pytest.mark.unit
def test_match_tick_past_max_ticks_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started(max_ticks=2))
    reducer.apply(_tick(1))
    reducer.apply(_tick(2))  # terminates the match at the bound
    assert reducer.state.status is SOMatchStatus.ENDED
    with pytest.raises(ReducerError, match="match_not_running"):
        reducer.apply(_tick(3))


# ---------------------------------------------------------------------------
# max_ticks bound: draw + single-survivor victory
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_max_ticks_draw_ends_match_and_emits_scored() -> None:
    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    reducer = ReducerMatchLifecycle(MATCH_ID, bus=bus)
    bus.subscribe(reducer.handle, event_types=_LIFECYCLE_TYPES)

    bus.publish(_started(max_ticks=3))
    for t in (1, 2, 3):
        bus.publish(_tick(t))

    state = reducer.state
    assert state.status is SOMatchStatus.ENDED
    assert state.tick == 3
    assert state.winner_id is None
    assert state.end_reason is SOMatchEndReason.DRAW_MAX_TICKS

    types = [e.event_type for e in collected]
    ended_idx = types.index(SOEventType.MATCH_ENDED)
    scored_idx = types.index(SOEventType.MATCH_SCORED)
    assert ended_idx < scored_idx, "MATCH_ENDED must precede MATCH_SCORED"

    ended = collected[ended_idx]
    assert ended.tick == 3
    assert ended.payload["reason"] == "draw_max_ticks"
    assert ended.payload["winner_id"] is None

    scored = collected[scored_idx]
    assert scored.payload["scores"] == {
        "player.red": {"victory": 0},
        "player.blue": {"victory": 0},
    }


@pytest.mark.unit
def test_max_ticks_single_survivor_declares_victory() -> None:
    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    reducer = ReducerMatchLifecycle(MATCH_ID, bus=bus)
    bus.subscribe(reducer.handle, event_types=_LIFECYCLE_TYPES)

    mechs = [
        _mech("mech.red.01", "player.red"),
        _mech("mech.blue.01", "player.blue", alive=False),
    ]
    bus.publish(_started(mechs=mechs, max_ticks=2))
    bus.publish(_tick(1))
    bus.publish(_tick(2))

    state = reducer.state
    assert state.status is SOMatchStatus.ENDED
    assert state.winner_id == "player.red"
    assert state.end_reason is SOMatchEndReason.LAST_MECH_STANDING

    types = [e.event_type for e in collected]
    assert SOEventType.VICTORY_DECLARED in types
    assert SOEventType.MATCH_ENDED not in types
    victory = collected[types.index(SOEventType.VICTORY_DECLARED)]
    assert victory.payload["winner_player_id"] == "player.red"
    assert victory.payload["reason"] == "last_mech_standing"


@pytest.mark.unit
def test_max_ticks_draw_without_bus_still_ends_match() -> None:
    """Replay path: bus=None means no emission, but state must still terminate."""
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started(max_ticks=1))
    state = reducer.apply(_tick(1))
    assert state.status is SOMatchStatus.ENDED
    assert state.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert state.winner_id is None


# ---------------------------------------------------------------------------
# VICTORY_DECLARED
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_victory_declared_ends_match_with_winner() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    reducer.apply(_tick(1))
    state = reducer.apply(_victory("player.blue", "last_mech_standing"))
    assert state.status is SOMatchStatus.ENDED
    assert state.winner_id == "player.blue"
    assert state.end_reason is SOMatchEndReason.LAST_MECH_STANDING
    assert state.tick == 1


@pytest.mark.unit
def test_victory_declared_on_pending_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    with pytest.raises(ReducerError, match="match_not_started"):
        reducer.apply(_victory())


@pytest.mark.unit
def test_victory_declared_idempotent_restatement() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    first = reducer.apply(_victory("player.red", "pilot_killed"))
    second = reducer.apply(_victory("player.red", "pilot_killed"))
    assert first == second


@pytest.mark.unit
def test_conflicting_victory_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    reducer.apply(_victory("player.red"))
    with pytest.raises(ReducerError, match="conflicting_terminal_state"):
        reducer.apply(_victory("player.blue"))


# ---------------------------------------------------------------------------
# MATCH_ENDED
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_ended_on_running_records_draw() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    state = reducer.apply(
        _envelope(SOEventType.MATCH_ENDED, {"reason": "aborted", "winner_id": None})
    )
    assert state.status is SOMatchStatus.ENDED
    assert state.end_reason is SOMatchEndReason.ABORTED
    assert state.winner_id is None


@pytest.mark.unit
def test_match_ended_idempotent_restatement() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started(max_ticks=1))
    first = reducer.apply(_tick(1))  # draw at the bound
    second = reducer.apply(
        _envelope(SOEventType.MATCH_ENDED, {"reason": "draw_max_ticks", "winner_id": None})
    )
    assert first == second


@pytest.mark.unit
def test_match_ended_conflicting_restatement_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started(max_ticks=1))
    reducer.apply(_tick(1))  # draw at the bound
    with pytest.raises(ReducerError, match="conflicting_terminal_state"):
        reducer.apply(
            _envelope(SOEventType.MATCH_ENDED, {"reason": "aborted", "winner_id": "player.red"})
        )


@pytest.mark.unit
def test_match_ended_on_pending_rejected() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    with pytest.raises(ReducerError, match="match_not_started"):
        reducer.apply(_envelope(SOEventType.MATCH_ENDED, {"reason": "aborted"}))


# ---------------------------------------------------------------------------
# Replay determinism + non-lifecycle events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replaying_same_events_twice_produces_identical_state() -> None:
    events = [_started(max_ticks=3), _tick(1), _tick(2), _tick(3)]

    def run() -> object:
        reducer = ReducerMatchLifecycle(MATCH_ID)
        for event in events:
            reducer.apply(event)
        return reducer.state

    first = run()
    second = run()
    assert first == second


@pytest.mark.unit
def test_non_lifecycle_events_are_ignored() -> None:
    reducer = ReducerMatchLifecycle(MATCH_ID)
    reducer.apply(_started())
    before = reducer.state
    after = reducer.apply(_envelope(SOEventType.WEAPON_FIRED, {"weapon_id": "weapon.machine_gun"}))
    assert after == before
