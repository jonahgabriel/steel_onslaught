"""Tests for the match lifecycle reducer — Task 18 invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.state import (
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle

MATCH_ID = "match.2026-04-30.test"
_TEST_CORRELATION_ID = UUID(int=1)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC)


class _FixedIdentities:
    def new_match_id(self) -> str:
        return "match.test.fixed"

    def new_correlation_id(self) -> UUID:
        return _TEST_CORRELATION_ID

    def new_event_id(self) -> str:
        return "01JABCDE0123456789ABCDEFGX"

    def new_message_id(self) -> UUID:
        return UUID(int=2)


_EVENT_FACTORY = EventFactory(clock=_FixedClock(), identities=_FixedIdentities())


def _lifecycle(bus: InProcessEventBus | None = None) -> ReducerMatchLifecycle:
    return ReducerMatchLifecycle(
        MATCH_ID,
        _TEST_CORRELATION_ID,
        event_factory=_EVENT_FACTORY,
        bus=bus,
    )


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
        current_mode=ModeId.RECON,
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
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id=match_id,
            emitted_at=datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
        ),
    )


def _started(
    mechs: list[ModelSOMechRuntimeState] | None = None,
    seed: int = 42,
    max_ticks: int = 200,
) -> ModelSOEventEnvelope:
    if mechs is None:
        mechs = [_mech("mech.red.01", "player.red"), _mech("mech.blue.01", "player.blue")]
    payload: dict[str, Any] = {
        "seed": seed,
        "max_ticks": max_ticks,
        "mechs": [m.model_dump(mode="json") for m in mechs],
    }
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
    reducer = _lifecycle()
    state = reducer.apply(_started(seed=1234, max_ticks=50))
    assert state.status is SOMatchStatus.RUNNING
    assert state.seed == 1234
    assert state.max_ticks == 50
    assert state.tick == 0
    assert set(state.mech_states) == {"mech.red.01", "mech.blue.01"}
    assert state.mech_states["mech.red.01"].player_id == "player.red"


@pytest.mark.unit
def test_match_started_records_explicit_max_ticks_200() -> None:
    reducer = _lifecycle()
    state = reducer.apply(_started())
    assert state.max_ticks == 200


@pytest.mark.unit
def test_duplicate_match_started_rejected() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    with pytest.raises(ReducerError, match="match_already_started"):
        reducer.apply(_started())


@pytest.mark.unit
def test_match_id_mismatch_rejected() -> None:
    reducer = _lifecycle()
    with pytest.raises(ReducerError, match="match_id_mismatch"):
        reducer.apply(_envelope(SOEventType.MATCH_STARTED, {"seed": 1}, match_id="match.other"))


# ---------------------------------------------------------------------------
# MATCH_TICK
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_tick_on_pending_rejected() -> None:
    reducer = _lifecycle()
    with pytest.raises(ReducerError, match="match_not_running"):
        reducer.apply(_tick(1))


@pytest.mark.unit
def test_match_tick_on_ended_rejected() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    reducer.apply(_victory())
    with pytest.raises(ReducerError, match="match_not_running"):
        reducer.apply(_tick(1))


@pytest.mark.unit
def test_tick_increments_exactly_plus_one() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    for t in (1, 2, 3):
        state = reducer.apply(_tick(t))
        assert state.tick == t
    assert reducer.state.status is SOMatchStatus.RUNNING


@pytest.mark.unit
def test_tick_skip_rejected() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    reducer.apply(_tick(1))
    with pytest.raises(ReducerError, match="tick_skip"):
        reducer.apply(_tick(3))


@pytest.mark.unit
def test_match_tick_past_max_ticks_rejected() -> None:
    reducer = _lifecycle()
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
    reducer = _lifecycle(bus)
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
    reducer = _lifecycle(bus)
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
    reducer = _lifecycle()
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
    reducer = _lifecycle()
    reducer.apply(_started())
    reducer.apply(_tick(1))
    state = reducer.apply(_victory("player.blue", "last_mech_standing"))
    assert state.status is SOMatchStatus.ENDED
    assert state.winner_id == "player.blue"
    assert state.end_reason is SOMatchEndReason.LAST_MECH_STANDING
    assert state.tick == 1


@pytest.mark.unit
def test_victory_declared_on_pending_rejected() -> None:
    reducer = _lifecycle()
    with pytest.raises(ReducerError, match="match_not_started"):
        reducer.apply(_victory())


@pytest.mark.unit
def test_victory_declared_idempotent_restatement() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    first = reducer.apply(_victory("player.red", "pilot_killed"))
    second = reducer.apply(_victory("player.red", "pilot_killed"))
    assert first == second


@pytest.mark.unit
def test_conflicting_victory_rejected() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    reducer.apply(_victory("player.red"))
    with pytest.raises(ReducerError, match="conflicting_terminal_state"):
        reducer.apply(_victory("player.blue"))


# ---------------------------------------------------------------------------
# MATCH_ENDED
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_ended_on_running_records_draw() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    state = reducer.apply(
        _envelope(SOEventType.MATCH_ENDED, {"reason": "aborted", "winner_id": None})
    )
    assert state.status is SOMatchStatus.ENDED
    assert state.end_reason is SOMatchEndReason.ABORTED
    assert state.winner_id is None


@pytest.mark.unit
def test_match_ended_idempotent_restatement() -> None:
    reducer = _lifecycle()
    reducer.apply(_started(max_ticks=1))
    first = reducer.apply(_tick(1))  # draw at the bound
    second = reducer.apply(
        _envelope(SOEventType.MATCH_ENDED, {"reason": "draw_max_ticks", "winner_id": None})
    )
    assert first == second


@pytest.mark.unit
def test_match_ended_conflicting_restatement_rejected() -> None:
    reducer = _lifecycle()
    reducer.apply(_started(max_ticks=1))
    reducer.apply(_tick(1))  # draw at the bound
    with pytest.raises(ReducerError, match="conflicting_terminal_state"):
        reducer.apply(
            _envelope(SOEventType.MATCH_ENDED, {"reason": "aborted", "winner_id": "player.red"})
        )


@pytest.mark.unit
def test_match_ended_on_pending_rejected() -> None:
    reducer = _lifecycle()
    with pytest.raises(ReducerError, match="match_not_started"):
        reducer.apply(_envelope(SOEventType.MATCH_ENDED, {"reason": "aborted"}))


# ---------------------------------------------------------------------------
# Replay determinism + non-lifecycle events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replaying_same_events_twice_produces_identical_state() -> None:
    events = [_started(max_ticks=3), _tick(1), _tick(2), _tick(3)]

    def run() -> object:
        reducer = _lifecycle()
        for event in events:
            reducer.apply(event)
        return reducer.state

    first = run()
    second = run()
    assert first == second


@pytest.mark.unit
def test_non_lifecycle_events_are_ignored() -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    before = reducer.state
    after = reducer.apply(_envelope(SOEventType.WEAPON_FIRED, {"weapon_id": "weapon.machine_gun"}))
    assert after == before


@pytest.mark.unit
def test_match_started_missing_max_ticks_fails_closed() -> None:
    reducer = _lifecycle()
    event = _started()
    payload = dict(event.payload)
    del payload["max_ticks"]

    with pytest.raises(ValueError, match="max_ticks"):
        reducer.apply(event.model_copy(update={"payload": payload}))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (
            SOEventType.VICTORY_DECLARED,
            {
                "winner_player_id": "player.red",
                "reason": "last_mech_standing",
                "unexpected": True,
            },
        ),
        (
            SOEventType.MATCH_ENDED,
            {"reason": "aborted", "winner_id": None, "unexpected": True},
        ),
    ],
)
def test_terminal_payload_unknown_fields_fail_closed(
    event_type: SOEventType,
    payload: dict[str, object],
) -> None:
    reducer = _lifecycle()
    reducer.apply(_started())
    with pytest.raises(ValueError, match="unexpected"):
        reducer.apply(_envelope(event_type, payload))
