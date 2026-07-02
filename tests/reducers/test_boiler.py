"""Tests for the boiler/heat/pressure reducer — Task 22.

Invariants verified:
- Pressure never goes negative or above max.
- Heat never goes below 0.
- Two consecutive ticks with no actions: pressure regen x2, heat vent x2.
- WEAPON_FIRED reduces pressure and adds heat.
- MODE_TRANSITION_STARTED reduces pressure and adds heat.
- BOILER_UPDATED is emitted on every pressure/heat change.
- HEAT_REDLINE_ENTERED emitted when heat crosses redline_threshold upward.
- HEAT_REDLINE_EXITED emitted when heat crosses redline_threshold downward.
- ReducerError("insufficient_pressure") NOT raised by the boiler reducer
  (pressure validation belongs to weapon validation upstream, Task 24).
"""

from __future__ import annotations

import pytest

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState, SOMatchStatus
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.boiler import ReducerBoiler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_boiler(
    *,
    pressure_current: int = 40,
    pressure_maximum: int = 80,
    regen_per_tick: int = 4,
    heat_current: int = 0,
    heat_redline_threshold: int = 70,
    heat_rupture_threshold: int = 100,
    heat_vent_rate: int = 3,
    status_redline: bool = False,
    status_rupture_warning: bool = False,
    status_disabled: bool = False,
    status_ruptured: bool = False,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id="match.001",
        mech_id="mech.red.01",
        tick=0,
        pressure_current=pressure_current,
        pressure_maximum=pressure_maximum,
        regeneration_per_tick=regen_per_tick,
        heat_current=heat_current,
        heat_redline_threshold=heat_redline_threshold,
        heat_rupture_threshold=heat_rupture_threshold,
        heat_vent_rate=heat_vent_rate,
        status_redline=status_redline,
        status_rupture_warning=status_rupture_warning,
        status_disabled=status_disabled,
        status_ruptured=status_ruptured,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _make_mech(boiler: ModelSOBoilerState) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id="mech.red.01",
        player_id="player.01",
        loadout_id="loadout.a",
        pilot_id="pilot.aggressive",
        chassis_id="chassis.medium.hunter_mk1",
        chassis_class="medium",
        base_speed=3,
        position=ModelSOPosition(x=0, y=0),
        facing=0,
        speed=3,
        hp=100,
        hp_max=100,
        armor_value=10,
        armor_max=10,
        current_mode="recon",
        boiler=boiler,
    )


def _make_match(mech: ModelSOMechRuntimeState) -> ModelSOMatchState:
    return ModelSOMatchState(
        match_id="match.001",
        tick=1,
        status=SOMatchStatus.RUNNING,
        seed=42,
        max_ticks=200,
        mech_states={"mech.red.01": mech},
    )


_SUBJECT = ModelSOEventSubject(mech_id="mech.red.01", player_id="player.01")


def _env(
    event_type: SOEventType,
    payload: dict,  # type: ignore[type-arg]
    eid: str = "01JABCDE0123456789ABCDEFG1",
    tick: int = 1,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=eid,
        match_id="match.001",
        tick=tick,
        sequence_in_tick=0,
        event_type=event_type,
        producer_node="node.test",
        subject=_SUBJECT,
        payload=payload,
        emitted_at="2026-04-30T16:00:00Z",
    )


# ---------------------------------------------------------------------------
# Tick regen/vent
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tick_regen_adds_pressure() -> None:
    """MATCH_TICK: pressure increases by regen_per_tick, capped at maximum."""
    boiler = _make_boiler(pressure_current=40, pressure_maximum=80, regen_per_tick=4)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    tick_evt = _env(SOEventType.MATCH_TICK, {})
    new_state = reducer.apply(tick_evt, state)

    updated_boiler = new_state.mech_states["mech.red.01"].boiler
    assert updated_boiler.pressure_current == 44
    # BOILER_UPDATED should have been emitted
    types = [e.event_type for e in emitted]
    assert SOEventType.BOILER_UPDATED in types


@pytest.mark.unit
def test_tick_vent_reduces_heat() -> None:
    """MATCH_TICK: heat decreases by vent_rate, floored at 0."""
    boiler = _make_boiler(heat_current=10, heat_vent_rate=3)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    tick_evt = _env(SOEventType.MATCH_TICK, {})
    new_state = reducer.apply(tick_evt, state)

    updated_boiler = new_state.mech_states["mech.red.01"].boiler
    assert updated_boiler.heat_current == 7


@pytest.mark.unit
def test_tick_heat_floored_at_zero() -> None:
    """MATCH_TICK: heat never goes below 0."""
    boiler = _make_boiler(heat_current=2, heat_vent_rate=5)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    tick_evt = _env(SOEventType.MATCH_TICK, {})
    new_state = reducer.apply(tick_evt, state)

    updated_boiler = new_state.mech_states["mech.red.01"].boiler
    assert updated_boiler.heat_current == 0


@pytest.mark.unit
def test_tick_pressure_capped_at_maximum() -> None:
    """MATCH_TICK: pressure never exceeds maximum."""
    boiler = _make_boiler(pressure_current=78, pressure_maximum=80, regen_per_tick=5)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    tick_evt = _env(SOEventType.MATCH_TICK, {})
    new_state = reducer.apply(tick_evt, state)

    updated_boiler = new_state.mech_states["mech.red.01"].boiler
    assert updated_boiler.pressure_current == 80


@pytest.mark.unit
def test_two_consecutive_ticks_no_actions() -> None:
    """Two consecutive ticks with no other events: regen x2 and vent x2."""
    boiler = _make_boiler(
        pressure_current=30,
        pressure_maximum=80,
        regen_per_tick=4,
        heat_current=20,
        heat_vent_rate=3,
    )
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    emit = lambda e: emitted.append(e)  # noqa: E731
    reducer = ReducerBoiler("mech.red.01", state, emit)

    tick1 = _env(SOEventType.MATCH_TICK, {}, eid="01JABCDE0123456789ABCDEFG1", tick=1)
    state = reducer.apply(tick1, state)

    tick2 = ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEFG2",
        match_id="match.001",
        tick=2,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="node.test",
        subject=_SUBJECT,
        payload={},
        emitted_at="2026-04-30T16:00:02Z",
    )
    state = reducer.apply(tick2, state)

    updated_boiler = state.mech_states["mech.red.01"].boiler
    assert updated_boiler.pressure_current == 38  # 30 + 4 + 4
    assert updated_boiler.heat_current == 14  # 20 - 3 - 3


# ---------------------------------------------------------------------------
# WEAPON_FIRED
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_weapon_fired_reduces_pressure_and_adds_heat() -> None:
    """WEAPON_FIRED: pressure -= cost, heat += weapon heat_generated."""
    boiler = _make_boiler(pressure_current=60, heat_current=10)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    fire_evt = _env(
        SOEventType.WEAPON_FIRED,
        {"weapon_id": "weapon.machine_gun", "pressure_cost": 8, "heat_generated": 12},
        eid="01JABCDE0123456789ABCDEFG2",
    )
    new_state = reducer.apply(fire_evt, state)

    updated_boiler = new_state.mech_states["mech.red.01"].boiler
    assert updated_boiler.pressure_current == 52  # 60 - 8
    assert updated_boiler.heat_current == 22  # 10 + 12

    types = [e.event_type for e in emitted]
    assert SOEventType.BOILER_UPDATED in types


@pytest.mark.unit
def test_weapon_fired_pressure_never_negative() -> None:
    """WEAPON_FIRED: pressure floored at 0 (validation is upstream, not here)."""
    boiler = _make_boiler(pressure_current=5)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    # Large cost but no ReducerError from boiler reducer — that's Task 24's job
    fire_evt = _env(
        SOEventType.WEAPON_FIRED,
        {"weapon_id": "weapon.steam_cannon", "pressure_cost": 20, "heat_generated": 5},
        eid="01JABCDE0123456789ABCDEFG3",
    )
    new_state = reducer.apply(fire_evt, state)
    # Pressure floored at 0 by boiler reducer
    assert new_state.mech_states["mech.red.01"].boiler.pressure_current == 0


# ---------------------------------------------------------------------------
# MODE_TRANSITION_STARTED
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mode_transition_started_costs_applied() -> None:
    """MODE_TRANSITION_STARTED: pressure -= costs.pressure, heat += costs.heat."""
    boiler = _make_boiler(pressure_current=50, heat_current=5)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    mode_evt = _env(
        SOEventType.MODE_TRANSITION_STARTED,
        {
            "from_mode": "recon",
            "to_mode": "assault",
            "costs": {"pressure": 10, "heat": 8, "transition_ticks": 2},
            "transition_ticks": 2,
        },
        eid="01JABCDE0123456789ABCDEFG4",
    )
    new_state = reducer.apply(mode_evt, state)

    updated_boiler = new_state.mech_states["mech.red.01"].boiler
    assert updated_boiler.pressure_current == 40  # 50 - 10
    assert updated_boiler.heat_current == 13  # 5 + 8

    types = [e.event_type for e in emitted]
    assert SOEventType.BOILER_UPDATED in types


# ---------------------------------------------------------------------------
# Redline transitions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_heat_redline_entered_emitted_when_crossing_upward() -> None:
    """HEAT_REDLINE_ENTERED emitted when heat crosses redline_threshold upward."""
    # heat_current=65, threshold=70: not yet redline
    boiler = _make_boiler(heat_current=65, heat_redline_threshold=70, heat_rupture_threshold=100)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    # Weapon fire generates 10 heat -> 65 + 10 = 75 (crosses redline at 70)
    fire_evt = _env(
        SOEventType.WEAPON_FIRED,
        {"weapon_id": "weapon.heat_lance", "pressure_cost": 5, "heat_generated": 10},
        eid="01JABCDE0123456789ABCDEFG5",
    )
    new_state = reducer.apply(fire_evt, state)

    assert new_state.mech_states["mech.red.01"].boiler.heat_current == 75
    types = [e.event_type for e in emitted]
    assert SOEventType.HEAT_REDLINE_ENTERED in types


@pytest.mark.unit
def test_heat_redline_exited_emitted_when_crossing_downward() -> None:
    """HEAT_REDLINE_EXITED emitted when heat crosses redline_threshold downward."""
    # Start at redline (heat 75 >= threshold 70), status_redline=True
    boiler = _make_boiler(
        heat_current=75,
        heat_redline_threshold=70,
        heat_rupture_threshold=100,
        heat_vent_rate=10,
        status_redline=True,
    )
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    # One tick with vent_rate=10: 75 - 10 = 65, crosses downward past threshold 70
    tick_evt = _env(SOEventType.MATCH_TICK, {})
    new_state = reducer.apply(tick_evt, state)

    assert new_state.mech_states["mech.red.01"].boiler.heat_current == 65
    types = [e.event_type for e in emitted]
    assert SOEventType.HEAT_REDLINE_EXITED in types
    assert SOEventType.HEAT_REDLINE_ENTERED not in types


@pytest.mark.unit
def test_heat_redline_not_emitted_when_already_at_redline() -> None:
    """HEAT_REDLINE_ENTERED is NOT re-emitted if already in redline."""
    # Already in redline; another weapon fire keeps heat above threshold
    boiler = _make_boiler(
        heat_current=80,
        heat_redline_threshold=70,
        heat_rupture_threshold=100,
        status_redline=True,
    )
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    fire_evt = _env(
        SOEventType.WEAPON_FIRED,
        {"weapon_id": "weapon.machine_gun", "pressure_cost": 3, "heat_generated": 5},
        eid="01JABCDE0123456789ABCDEFG6",
    )
    new_state = reducer.apply(fire_evt, state)

    # Heat went from 80 to 85, still above redline — no new HEAT_REDLINE_ENTERED
    assert new_state.mech_states["mech.red.01"].boiler.heat_current == 85
    types = [e.event_type for e in emitted]
    assert SOEventType.HEAT_REDLINE_ENTERED not in types


@pytest.mark.unit
def test_heat_redline_exited_not_emitted_when_not_in_redline() -> None:
    """HEAT_REDLINE_EXITED is NOT emitted if the mech was not in redline."""
    # heat=50, below redline at 70; vent reduces to 40
    boiler = _make_boiler(
        heat_current=50,
        heat_redline_threshold=70,
        heat_rupture_threshold=100,
        heat_vent_rate=10,
        status_redline=False,
    )
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    tick_evt = _env(SOEventType.MATCH_TICK, {})
    new_state = reducer.apply(tick_evt, state)

    types = [e.event_type for e in emitted]
    assert SOEventType.HEAT_REDLINE_EXITED not in types
    # heat=50-10=40, still below redline — no crossing
    assert new_state.mech_states["mech.red.01"].boiler.heat_current == 40


# ---------------------------------------------------------------------------
# BOILER_UPDATED emitted on change
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_boiler_updated_emitted_on_weapon_fire() -> None:
    """BOILER_UPDATED is emitted after WEAPON_FIRED changes pressure or heat."""
    boiler = _make_boiler()
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    fire_evt = _env(
        SOEventType.WEAPON_FIRED,
        {"weapon_id": "weapon.machine_gun", "pressure_cost": 5, "heat_generated": 3},
        eid="01JABCDE0123456789ABCDEFG7",
    )
    reducer.apply(fire_evt, state)

    assert any(e.event_type == SOEventType.BOILER_UPDATED for e in emitted)


@pytest.mark.unit
def test_boiler_updated_emitted_on_tick_regen() -> None:
    """BOILER_UPDATED is emitted after MATCH_TICK changes pressure or heat."""
    boiler = _make_boiler(pressure_current=40, heat_current=10)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    tick_evt = _env(SOEventType.MATCH_TICK, {})
    reducer.apply(tick_evt, state)

    assert any(e.event_type == SOEventType.BOILER_UPDATED for e in emitted)


# ---------------------------------------------------------------------------
# Irrelevant events are ignored
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unrelated_event_ignored() -> None:
    """Events not relevant to the boiler reducer are silently ignored."""
    boiler = _make_boiler(pressure_current=40, heat_current=10)
    mech = _make_mech(boiler)
    state = _make_match(mech)

    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerBoiler("mech.red.01", state, lambda e: emitted.append(e))

    unrelated = _env(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 1, "y": 1},
            "ticks_consumed": 1,
            "pressure_consumed": 1,
        },
        eid="01JABCDE0123456789ABCDEFG8",
    )
    new_state = reducer.apply(unrelated, state)

    # State unchanged for this mech's boiler
    assert new_state.mech_states["mech.red.01"].boiler.pressure_current == 40
    assert new_state.mech_states["mech.red.01"].boiler.heat_current == 10
    # No events emitted
    assert emitted == []
