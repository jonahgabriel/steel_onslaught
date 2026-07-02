"""Tests for the mode transition reducer — Task 23.

Invariants covered
------------------
1. MODE_TRANSITION_STARTED is emitted only by the mode reducer (static check via
   source-file inspection).
2. A MODE_SWITCH_INTENT with heat == cannot_switch_if_heat_above is rejected
   (no MODE_TRANSITION_STARTED emitted, boiler unchanged).
3. A rejected intent leaves the boiler unchanged (no pressure/heat consumed).
4. During transition_ticks, mech has evasion_penalty_during_transition applied.
5. MODE_TRANSITION_COMPLETED follows MODE_TRANSITION_STARTED for every accepted
   transition (no orphan completions, no stuck transitions).
6. A valid MODE_SWITCH_INTENT produces MODE_TRANSITION_STARTED and sets
   transition fields; after enough ticks, MODE_TRANSITION_COMPLETED fires.
7. Intent rejected when mode_lock not expired.
8. Intent rejected when boiler is disabled.
9. Intent rejected when pressure is insufficient.
10. Intent rejected when from_mode != mech.current_mode.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import (
    ModelSOModeTransition,
    ModelSOModeTransitionCosts,
    ModelSOModeTransitionRestrictions,
    ModelSOModeTransitionVulnerability,
)
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState, SOMatchStatus
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.mode import ReducerModeTransition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MATCH_ID = "match.test.001"
_MECH_ID = "mech.red.01"
_PLAYER_ID = "player.red"


def _boiler_state(
    pressure: int = 50,
    heat: int = 20,
    *,
    disabled: bool = False,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=_MATCH_ID,
        mech_id=_MECH_ID,
        tick=0,
        pressure_current=pressure,
        pressure_maximum=80,
        regeneration_per_tick=3,
        heat_current=heat,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=4,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=disabled,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _mech(
    *,
    current_mode: str = "recon",
    mode_lock_until: int = 0,
    transition_ticks_remaining: int = 0,
    transition_to_mode: str | None = None,
    sensor_dropout_ticks_remaining: int = 0,
    boiler: ModelSOBoilerState | None = None,
    alive: bool = True,
    evasion: float = 0.0,
) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id=_MECH_ID,
        player_id=_PLAYER_ID,
        loadout_id="loadout.test.001",
        pilot_id="pilot.aggressive",
        chassis_id="chassis.heavy.ironclad_mk1",
        chassis_class="heavy",
        base_speed=2,
        position=ModelSOPosition(x=0, y=0),
        facing=0,
        speed=2,
        hp=100,
        hp_max=100,
        armor_value=10,
        armor_max=10,
        alive=alive,
        pilot_alive=True,
        current_mode=current_mode,
        mode_lock_until=mode_lock_until,
        transition_ticks_remaining=transition_ticks_remaining,
        transition_to_mode=transition_to_mode,
        sensor_dropout_ticks_remaining=sensor_dropout_ticks_remaining,
        evasion=evasion,
        boiler=boiler or _boiler_state(),
    )


def _match(tick: int = 5, mech: ModelSOMechRuntimeState | None = None) -> ModelSOMatchState:
    m = mech or _mech()
    return ModelSOMatchState(
        match_id=_MATCH_ID,
        tick=tick,
        status=SOMatchStatus.RUNNING,
        seed=1,
        max_ticks=200,
        mech_states={_MECH_ID: m},
    )


def _transition(
    *,
    from_mode: str = "recon",
    to_mode: str = "assault",
    pressure_cost: int = 10,
    heat_cost: int = 5,
    transition_ticks: int = 2,
    min_lock_ticks: int = 3,
    cannot_switch_if_heat_above: int | None = None,
    cannot_switch_if_boiler_disabled: bool = False,
    evasion_penalty: float = 0.1,
    sensor_dropout_ticks: int = 1,
) -> ModelSOModeTransition:
    return ModelSOModeTransition(
        schema_version="0.1.0",
        kind="steel_onslaught.mode_transition",
        from_mode=from_mode,
        to_mode=to_mode,
        costs=ModelSOModeTransitionCosts(
            pressure=pressure_cost,
            heat=heat_cost,
            transition_ticks=transition_ticks,
        ),
        restrictions=ModelSOModeTransitionRestrictions(
            minimum_lock_ticks_after_switch=min_lock_ticks,
            cannot_switch_if_heat_above=cannot_switch_if_heat_above,
            cannot_switch_if_boiler_disabled=cannot_switch_if_boiler_disabled,
        ),
        vulnerability=ModelSOModeTransitionVulnerability(
            evasion_penalty_during_transition=evasion_penalty,
            sensor_dropout_ticks=sensor_dropout_ticks,
        ),
    )


def _intent_env(
    from_mode: str = "recon",
    to_mode: str = "assault",
    *,
    tick: int = 5,
    mech_id: str = _MECH_ID,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEF10",
        match_id=_MATCH_ID,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.MODE_SWITCH_INTENT,
        producer_node="node.pilot.red.01",
        subject=ModelSOEventSubject(mech_id=mech_id, player_id=_PLAYER_ID),
        payload={"from_mode": from_mode, "to_mode": to_mode},
        emitted_at="2026-04-30T16:00:00Z",
    )


def _tick_env(tick: int) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=f"01JABCDE012345678ABCD{tick:05d}",
        match_id=_MATCH_ID,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="node.reducer.lifecycle",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        payload={"tick": tick},
        emitted_at="2026-04-30T16:00:00Z",
    )


# ---------------------------------------------------------------------------
# Static invariant: MODE_TRANSITION_STARTED only emitted by the mode reducer
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mode_transition_started_emitted_only_by_mode_reducer() -> None:
    """Scan every source file (except mode.py itself) for direct *emission* of
    MODE_TRANSITION_STARTED and assert none exist.

    "Emission" means passing the event type as the ``event_type`` argument to an
    envelope constructor or publish call.  Mere references in comments, docstrings,
    enum definitions, or ``case SOEventType.MODE_TRANSITION_STARTED:`` match arms
    (which are *subscriptions*, not emissions) are allowed.

    The pattern ``event_type=SOEventType.MODE_TRANSITION_STARTED`` uniquely
    identifies an emission site.  All other references are legitimate.

    This guards the intent/event separation invariant at the code level.
    """
    src_root = Path(__file__).parents[2] / "src"
    mode_reducer = src_root / "steel_onslaught" / "reducers" / "mode.py"
    # Match only the assignment form that appears in publish / ModelSOEventEnvelope calls.
    emission_pattern = re.compile(r"event_type\s*=\s*SOEventType\.MODE_TRANSITION_STARTED")

    offenders: list[str] = []
    for py_file in src_root.rglob("*.py"):
        if py_file.resolve() == mode_reducer.resolve():
            continue  # mode.py IS allowed to emit it
        text = py_file.read_text()
        if emission_pattern.search(text):
            offenders.append(str(py_file.relative_to(src_root)))

    assert offenders == [], f"MODE_TRANSITION_STARTED emitted outside mode reducer in: {offenders}"


# ---------------------------------------------------------------------------
# Rejection invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_intent_rejected_heat_at_limit() -> None:
    """Intent with heat == cannot_switch_if_heat_above is rejected (no started event)."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition(cannot_switch_if_heat_above=75)
    }
    match_state = _match(tick=5, mech=_mech(boiler=_boiler_state(pressure=50, heat=75)))
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(
        match_id=_MATCH_ID,
        transitions=transitions,
        bus=bus,
    )
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted
    # Boiler must be unchanged (no pressure/heat consumed on rejection)
    updated_mech = reducer.get_mech_state(_MECH_ID)
    assert updated_mech.boiler.pressure_current == 50
    assert updated_mech.boiler.heat_current == 75


@pytest.mark.unit
def test_intent_rejected_leaves_boiler_unchanged() -> None:
    """A rejected intent (mode lock not expired) leaves pressure/heat unchanged."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition()
    }
    # mode_lock_until=10 > current tick=5 → locked
    match_state = _match(
        tick=5, mech=_mech(mode_lock_until=10, boiler=_boiler_state(pressure=50, heat=20))
    )
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted
    updated_mech = reducer.get_mech_state(_MECH_ID)
    assert updated_mech.boiler.pressure_current == 50
    assert updated_mech.boiler.heat_current == 20


@pytest.mark.unit
def test_intent_rejected_mode_lock_not_expired() -> None:
    """MODE_SWITCH_INTENT is silently dropped when mode_lock_until > current_tick."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition()
    }
    match_state = _match(tick=5, mech=_mech(mode_lock_until=6))
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted


@pytest.mark.unit
def test_intent_rejected_boiler_disabled() -> None:
    """Intent rejected when boiler is disabled and restriction is set."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition(cannot_switch_if_boiler_disabled=True)
    }
    match_state = _match(tick=5, mech=_mech(boiler=_boiler_state(disabled=True)))
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted


@pytest.mark.unit
def test_intent_rejected_insufficient_pressure() -> None:
    """Intent rejected when current pressure < cost."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition(pressure_cost=60)
    }
    match_state = _match(tick=5, mech=_mech(boiler=_boiler_state(pressure=50)))
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted


@pytest.mark.unit
def test_intent_rejected_wrong_from_mode() -> None:
    """Intent rejected when from_mode doesn't match mech's current_mode."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition()
    }
    # Mech is in assault mode, intent claims from_mode=recon
    match_state = _match(tick=5, mech=_mech(current_mode="assault"))
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted


# ---------------------------------------------------------------------------
# Acceptance invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_intent_starts_transition() -> None:
    """A valid MODE_SWITCH_INTENT produces MODE_TRANSITION_STARTED and sets
    transition fields on the mech state."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition(pressure_cost=10, heat_cost=5, transition_ticks=2)
    }
    match_state = _match(
        tick=5,
        mech=_mech(boiler=_boiler_state(pressure=50, heat=20)),
    )
    emitted: list[ModelSOEventEnvelope] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    started_events = [e for e in emitted if e.event_type == SOEventType.MODE_TRANSITION_STARTED]
    assert len(started_events) == 1

    mech = reducer.get_mech_state(_MECH_ID)
    # Transition fields set
    assert mech.transition_ticks_remaining == 2
    assert mech.transition_to_mode == "assault"
    # Pressure and heat consumed
    assert mech.boiler.pressure_current == 40  # 50 - 10
    assert mech.boiler.heat_current == 25  # 20 + 5


@pytest.mark.unit
def test_evasion_penalty_applied_during_transition() -> None:
    """While transition_ticks_remaining > 0 the mech has the evasion penalty."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition(evasion_penalty=0.2, transition_ticks=2)
    }
    match_state = _match(
        tick=5,
        mech=_mech(boiler=_boiler_state()),
    )
    bus = InProcessEventBus()
    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    mech = reducer.get_mech_state(_MECH_ID)
    # The evasion field on the mech should reflect the transition penalty
    assert mech.transition_ticks_remaining > 0
    assert mech.evasion == pytest.approx(0.2)


@pytest.mark.unit
def test_transition_completed_after_ticks() -> None:
    """MODE_TRANSITION_COMPLETED fires after transition_ticks elapses.

    Sequence:
      tick 5 → intent accepted → STARTED (ticks_remaining=2)
      tick 6 → MATCH_TICK → ticks_remaining=1
      tick 7 → MATCH_TICK → ticks_remaining=0 → COMPLETED
    """
    transition = _transition(transition_ticks=2, min_lock_ticks=3, evasion_penalty=0.1)
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {("recon", "assault"): transition}
    match_state = _match(
        tick=5,
        mech=_mech(boiler=_boiler_state()),
    )
    emitted: list[ModelSOEventEnvelope] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    # No COMPLETED yet
    completed_events = [e for e in emitted if e.event_type == SOEventType.MODE_TRANSITION_COMPLETED]
    assert len(completed_events) == 0

    # Tick 6
    tick6_state = match_state.model_copy(update={"tick": 6})
    reducer.update_state(tick6_state)
    reducer.apply(_tick_env(tick=6))

    completed_events = [e for e in emitted if e.event_type == SOEventType.MODE_TRANSITION_COMPLETED]
    assert len(completed_events) == 0

    # Tick 7 → COMPLETED
    tick7_state = match_state.model_copy(update={"tick": 7})
    reducer.update_state(tick7_state)
    reducer.apply(_tick_env(tick=7))

    completed_events = [e for e in emitted if e.event_type == SOEventType.MODE_TRANSITION_COMPLETED]
    assert len(completed_events) == 1

    mech = reducer.get_mech_state(_MECH_ID)
    assert mech.current_mode == "assault"
    assert mech.transition_ticks_remaining == 0
    assert mech.transition_to_mode is None
    # mode_lock_until = 7 + 3 = 10
    assert mech.mode_lock_until == 10
    # Evasion penalty removed after completion
    assert mech.evasion == 0.0


@pytest.mark.unit
def test_no_orphan_completions() -> None:
    """Every STARTED event is followed by exactly one COMPLETED event (no orphans)."""
    transition = _transition(transition_ticks=1, min_lock_ticks=2)
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {("recon", "assault"): transition}
    match_state = _match(tick=5, mech=_mech(boiler=_boiler_state()))
    emitted: list[ModelSOEventEnvelope] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    tick6_state = match_state.model_copy(update={"tick": 6})
    reducer.update_state(tick6_state)
    reducer.apply(_tick_env(tick=6))

    started = [e for e in emitted if e.event_type == SOEventType.MODE_TRANSITION_STARTED]
    completed = [e for e in emitted if e.event_type == SOEventType.MODE_TRANSITION_COMPLETED]
    assert len(started) == 1
    assert len(completed) == 1


@pytest.mark.unit
def test_no_stuck_transition_after_completion() -> None:
    """After COMPLETED, transition_ticks_remaining == 0 and transition_to_mode is None."""
    transition = _transition(transition_ticks=1)
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {("recon", "assault"): transition}
    match_state = _match(tick=5, mech=_mech(boiler=_boiler_state()))
    bus = InProcessEventBus()
    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    tick6_state = match_state.model_copy(update={"tick": 6})
    reducer.update_state(tick6_state)
    reducer.apply(_tick_env(tick=6))

    mech = reducer.get_mech_state(_MECH_ID)
    assert mech.transition_ticks_remaining == 0
    assert mech.transition_to_mode is None


@pytest.mark.unit
def test_sensor_dropout_ticks_set_on_transition_start() -> None:
    """sensor_dropout_ticks_remaining is set on the mech when the transition starts."""
    transition = _transition(sensor_dropout_ticks=2, transition_ticks=3)
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {("recon", "assault"): transition}
    match_state = _match(tick=5, mech=_mech(boiler=_boiler_state()))
    bus = InProcessEventBus()
    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    mech = reducer.get_mech_state(_MECH_ID)
    assert mech.sensor_dropout_ticks_remaining == 2


@pytest.mark.unit
def test_no_transition_for_dead_mech() -> None:
    """A dead mech's intent is silently dropped."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {
        ("recon", "assault"): _transition()
    }
    match_state = _match(tick=5, mech=_mech(alive=False))
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted


@pytest.mark.unit
def test_unknown_transition_rejected() -> None:
    """If the transition pair is not in the transitions map, intent is dropped."""
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {}
    match_state = _match(tick=5, mech=_mech())
    emitted: list[SOEventType] = []
    bus = InProcessEventBus()
    bus.subscribe(lambda e: emitted.append(e.event_type))

    reducer = ReducerModeTransition(match_id=_MATCH_ID, transitions=transitions, bus=bus)
    reducer.update_state(match_state)
    reducer.apply(_intent_env("recon", "assault", tick=5))

    assert SOEventType.MODE_TRANSITION_STARTED not in emitted
