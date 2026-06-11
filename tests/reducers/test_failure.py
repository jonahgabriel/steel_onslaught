"""Tests for the failure cascade reducer — Task 26.

Cascade ladder (deterministic order):
1. Heat >= redline_threshold -> HEAT_REDLINE_ENTERED (owned by the boiler
   reducer, Task 22 — NOT re-emitted here; this reducer only counts ticks).
2. Sustained redline (3+ consecutive ticks) -> BOILER_OVERLOADED.
   Effects: -20% accuracy on next firing, mode switch disabled for 3 ticks.
3. Heat >= rupture_threshold OR sustained overload (5+ overloaded ticks)
   -> BOILER_RUPTURED. Effects: target hp -= 30, area damage within 3 cells.
4. On rupture: pilot survival roll, p = 0.5 + 0.2 per emergency safety gizmo,
   via MatchRng.for_event(tick, mech_id, "rupture_survival"). Fail -> PILOT_KILLED.
5. MECH_DESTROYED (from rupture or cumulative damage): mech leaves active state.
6. Exactly one player with surviving mechs -> VICTORY_DECLARED(last_mech_standing).

Invariants covered:
- Cascade ordering is deterministic: redline before overload before rupture
  before death.
- Two replays produce identical rupture/survival outcomes (deterministic RNG).
- A mech that ruptures in tick N has VICTORY_DECLARED in tick N if no other
  mechs remain.
"""

from __future__ import annotations

from typing import Any

import pytest

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.failure import (
    OVERLOAD_ACCURACY_PENALTY,
    OVERLOAD_MODE_SWITCH_DISABLED_TICKS,
    OVERLOAD_REDLINE_TICKS,
    RUPTURE_AREA_DAMAGE,
    RUPTURE_AREA_RADIUS_CELLS,
    RUPTURE_DIRECT_DAMAGE,
    RUPTURE_OVERLOAD_TICKS,
    RUPTURE_SURVIVAL_BASE,
    RUPTURE_SURVIVAL_PER_SAFETY_GIZMO,
    ReducerFailureCascade,
    SODestructionCause,
    SORuptureCause,
)

_MATCH_ID = "match.001"
_SAFETY_GIZMO = "gizmo.cooling.emergency_condenser"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_boiler(
    mech_id: str,
    *,
    heat_current: int = 0,
    heat_redline_threshold: int = 70,
    heat_rupture_threshold: int = 100,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=_MATCH_ID,
        mech_id=mech_id,
        tick=0,
        pressure_current=40,
        pressure_maximum=80,
        regeneration_per_tick=4,
        heat_current=heat_current,
        heat_redline_threshold=heat_redline_threshold,
        heat_rupture_threshold=heat_rupture_threshold,
        heat_vent_rate=0,
        status_redline=heat_current >= heat_redline_threshold,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _make_mech(
    mech_id: str,
    player_id: str,
    *,
    heat_current: int = 0,
    hp: int = 100,
    position: ModelSOPosition | None = None,
    gizmo_ids: tuple[str, ...] = (),
    alive: bool = True,
    pilot_alive: bool = True,
    redline_consecutive_ticks: int = 0,
    overloaded: bool = False,
    overloaded_consecutive_ticks: int = 0,
) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=player_id,
        loadout_id="loadout.a",
        pilot_id="pilot.aggressive",
        chassis_id="chassis.medium.hunter_mk1",
        chassis_class="medium",
        gizmo_ids=gizmo_ids,
        base_speed=3,
        position=position or ModelSOPosition(x=0, y=0),
        facing=0,
        speed=3,
        hp=hp,
        hp_max=100,
        armor_value=10,
        alive=alive,
        pilot_alive=pilot_alive,
        current_mode="recon",
        boiler=_make_boiler(mech_id, heat_current=heat_current),
        redline_consecutive_ticks=redline_consecutive_ticks,
        overloaded=overloaded,
        overloaded_consecutive_ticks=overloaded_consecutive_ticks,
    )


def _make_match(
    *mechs: ModelSOMechRuntimeState,
    seed: int = 42,
    status: SOMatchStatus = SOMatchStatus.RUNNING,
    end_reason: SOMatchEndReason | None = None,
) -> ModelSOMatchState:
    return ModelSOMatchState(
        match_id=_MATCH_ID,
        tick=0,
        status=status,
        seed=seed,
        max_ticks=200,
        mech_states={mech.mech_id: mech for mech in mechs},
        end_reason=end_reason,
    )


_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")


def _env(
    event_type: SOEventType,
    *,
    tick: int,
    subject: ModelSOEventSubject = _MATCH_SUBJECT,
    payload: dict[str, Any] | None = None,
    match_id: str = _MATCH_ID,
    seq: int = 0,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=f"01JTESTTESTTESTTESTTEST{seq:03d}",
        match_id=match_id,
        tick=tick,
        sequence_in_tick=seq,
        event_type=event_type,
        producer_node="node.test",
        subject=subject,
        payload=payload or {},
        emitted_at="2026-04-30T16:00:00Z",
    )


def _tick(tick: int) -> ModelSOEventEnvelope:
    return _env(SOEventType.MATCH_TICK, tick=tick, seq=tick)


def _run_ticks(
    reducer: ReducerFailureCascade,
    state: ModelSOMatchState,
    ticks: range,
) -> ModelSOMatchState:
    for t in ticks:
        state = reducer.apply(_tick(t), state)
    return state


def _types(emitted: list[ModelSOEventEnvelope]) -> list[SOEventType]:
    return [e.event_type for e in emitted]


# ---------------------------------------------------------------------------
# Redline counting + overload
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_redline_no_emissions() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=10)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = _run_ticks(reducer, state, range(1, 4))

    assert emitted == []
    assert new_state.mech_states["mech.red.01"].redline_consecutive_ticks == 0
    assert new_state.mech_states["mech.red.01"].overloaded is False


@pytest.mark.unit
def test_redline_tick_increments_counter_without_overload() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=75)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert emitted == []
    assert new_state.mech_states["mech.red.01"].redline_consecutive_ticks == 1
    assert new_state.mech_states["mech.red.01"].overloaded is False


@pytest.mark.unit
def test_overload_after_three_consecutive_redline_ticks() -> None:
    """3+ consecutive redline ticks -> BOILER_OVERLOADED with overload effects."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=75)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = _run_ticks(reducer, state, range(1, OVERLOAD_REDLINE_TICKS + 1))

    assert _types(emitted) == [SOEventType.BOILER_OVERLOADED]
    overload = emitted[0]
    assert overload.tick == OVERLOAD_REDLINE_TICKS
    assert overload.subject.mech_id == "mech.red.01"

    updated = new_state.mech_states["mech.red.01"]
    assert updated.overloaded is True
    assert updated.overloaded_consecutive_ticks == 1
    assert updated.accuracy_penalty_next_fire == OVERLOAD_ACCURACY_PENALTY
    assert (
        updated.mode_switch_disabled_until
        == OVERLOAD_REDLINE_TICKS + OVERLOAD_MODE_SWITCH_DISABLED_TICKS
    )


@pytest.mark.unit
def test_overload_not_re_emitted_while_overloaded() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=75)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = _run_ticks(reducer, state, range(1, OVERLOAD_REDLINE_TICKS + 2))

    assert _types(emitted).count(SOEventType.BOILER_OVERLOADED) == 1
    assert new_state.mech_states["mech.red.01"].overloaded_consecutive_ticks == 2


@pytest.mark.unit
def test_redline_exit_resets_counters_and_clears_overload() -> None:
    """Dropping below redline resets the ladder: counters zeroed, overload off."""
    mech = _make_mech(
        "mech.red.01",
        "player.a",
        heat_current=10,
        redline_consecutive_ticks=4,
        overloaded=True,
        overloaded_consecutive_ticks=2,
    )
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert emitted == []
    updated = new_state.mech_states["mech.red.01"]
    assert updated.redline_consecutive_ticks == 0
    assert updated.overloaded is False
    assert updated.overloaded_consecutive_ticks == 0


@pytest.mark.unit
def test_two_redline_ticks_then_exit_never_overloads() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=75)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    state = _run_ticks(reducer, state, range(1, 3))  # two redline ticks

    # Simulate venting below redline (the boiler reducer owns heat itself).
    cooled = state.mech_states["mech.red.01"].model_copy(
        update={"boiler": _make_boiler("mech.red.01", heat_current=10)}
    )
    state = state.model_copy(update={"mech_states": {**state.mech_states, "mech.red.01": cooled}})
    state = reducer.apply(_tick(3), state)

    # Back to redline for two more ticks — still under the 3-tick ladder.
    reheated = state.mech_states["mech.red.01"].model_copy(
        update={"boiler": _make_boiler("mech.red.01", heat_current=75)}
    )
    state = state.model_copy(update={"mech_states": {**state.mech_states, "mech.red.01": reheated}})
    state = _run_ticks(reducer, state, range(4, 6))

    assert SOEventType.BOILER_OVERLOADED not in _types(emitted)
    assert state.mech_states["mech.red.01"].redline_consecutive_ticks == 2


# ---------------------------------------------------------------------------
# Rupture triggers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rupture_on_heat_at_rupture_threshold() -> None:
    """Heat >= rupture_threshold ruptures immediately, without sustained overload."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    reducer.apply(_tick(1), state)

    ruptures = [e for e in emitted if e.event_type == SOEventType.BOILER_RUPTURED]
    assert len(ruptures) == 1
    assert ruptures[0].payload["cause"] == SORuptureCause.HEAT_THRESHOLD.value
    assert ruptures[0].subject.mech_id == "mech.red.01"


@pytest.mark.unit
def test_rupture_after_five_sustained_overload_ticks() -> None:
    """Overload at tick 3; 5 overloaded ticks (3..7) -> rupture at tick 7."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=75)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    rupture_tick = OVERLOAD_REDLINE_TICKS + RUPTURE_OVERLOAD_TICKS - 1  # 7
    state = _run_ticks(reducer, state, range(1, rupture_tick))
    assert SOEventType.BOILER_RUPTURED not in _types(emitted)

    state = reducer.apply(_tick(rupture_tick), state)

    ruptures = [e for e in emitted if e.event_type == SOEventType.BOILER_RUPTURED]
    assert len(ruptures) == 1
    assert ruptures[0].tick == rupture_tick
    assert ruptures[0].payload["cause"] == SORuptureCause.SUSTAINED_OVERLOAD.value


@pytest.mark.unit
def test_rupture_applies_direct_damage_and_destroys_mech() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=100, hp=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    updated = new_state.mech_states["mech.red.01"]
    assert updated.hp == 100 - RUPTURE_DIRECT_DAMAGE
    assert updated.alive is False  # rupture is terminal regardless of remaining hp
    assert updated.boiler.status_ruptured is True
    assert updated.boiler.status_disabled is True

    destroyed = [
        e
        for e in emitted
        if e.event_type == SOEventType.MECH_DESTROYED and e.subject.mech_id == "mech.red.01"
    ]
    assert len(destroyed) == 1
    assert destroyed[0].payload["cause"] == SODestructionCause.BOILER_RUPTURE.value


@pytest.mark.unit
def test_cascade_order_overload_before_rupture_before_destruction() -> None:
    """Invariant: cascade ordering is deterministic — overload < rupture < death."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=75)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    _run_ticks(reducer, state, range(1, 8))

    types = _types(emitted)
    overload_idx = types.index(SOEventType.BOILER_OVERLOADED)
    rupture_idx = types.index(SOEventType.BOILER_RUPTURED)
    destroyed_idx = types.index(SOEventType.MECH_DESTROYED)
    assert overload_idx < rupture_idx < destroyed_idx


@pytest.mark.unit
def test_dead_mech_skipped_by_cascade() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=100, alive=False)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert emitted == []
    assert new_state == state


# ---------------------------------------------------------------------------
# Pilot rupture-survival roll
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pilot_killed_on_failed_survival_roll() -> None:
    """Seed 0 / tick 1 / mech.red.01 rolls ~0.6267 >= 0.5 -> pilot killed."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=0)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    killed = [e for e in emitted if e.event_type == SOEventType.PILOT_KILLED]
    assert len(killed) == 1
    assert killed[0].subject.mech_id == "mech.red.01"
    assert killed[0].payload["survival_probability"] == RUPTURE_SURVIVAL_BASE
    assert new_state.mech_states["mech.red.01"].pilot_alive is False

    types = _types(emitted)
    assert types.index(SOEventType.BOILER_RUPTURED) < types.index(SOEventType.PILOT_KILLED)
    assert types.index(SOEventType.PILOT_KILLED) < types.index(SOEventType.MECH_DESTROYED)


@pytest.mark.unit
def test_pilot_survives_on_successful_roll() -> None:
    """Seed 1 / tick 1 / mech.red.01 rolls ~0.1335 < 0.5 -> pilot survives."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert SOEventType.PILOT_KILLED not in _types(emitted)
    updated = new_state.mech_states["mech.red.01"]
    assert updated.pilot_alive is True
    assert updated.alive is False  # mech still destroyed by the rupture


@pytest.mark.unit
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5])
def test_survival_roll_matches_match_rng_contract(seed: int) -> None:
    """Killed iff MatchRng.for_event(tick, mech_id, 'rupture_survival') >= p."""
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=seed)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    reducer.apply(_tick(1), state)

    roll = MatchRng(match_seed=seed).for_event(1, "mech.red.01", "rupture_survival").random()
    expected_killed = roll >= RUPTURE_SURVIVAL_BASE
    assert (SOEventType.PILOT_KILLED in _types(emitted)) == expected_killed


@pytest.mark.unit
def test_safety_gizmo_raises_survival_probability() -> None:
    """Seed 0 rolls ~0.6267: killed at p=0.5, survives at p=0.7 with one gizmo."""
    mech = _make_mech(
        "mech.red.01",
        "player.a",
        heat_current=100,
        gizmo_ids=(_SAFETY_GIZMO, "gizmo.amplifier.burst_amplifier"),
    )
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=0)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(
        _MATCH_ID,
        emit=emitted.append,
        safety_gizmo_ids=frozenset({_SAFETY_GIZMO}),
    )

    new_state = reducer.apply(_tick(1), state)

    assert SOEventType.PILOT_KILLED not in _types(emitted)
    assert new_state.mech_states["mech.red.01"].pilot_alive is True


@pytest.mark.unit
@pytest.mark.parametrize("seed", [0, 2, 8, 9, 14])
def test_three_safety_gizmos_clamp_probability_to_one(seed: int) -> None:
    """p = 0.5 + 3*0.2 = 1.1 clamps to 1.0 -> pilot always survives."""
    gizmos = tuple(f"gizmo.safety.unit_{i}" for i in range(3))
    assert RUPTURE_SURVIVAL_BASE + 3 * RUPTURE_SURVIVAL_PER_SAFETY_GIZMO > 1.0
    mech = _make_mech("mech.red.01", "player.a", heat_current=100, gizmo_ids=gizmos)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"), seed=seed)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(
        _MATCH_ID,
        emit=emitted.append,
        safety_gizmo_ids=frozenset(gizmos),
    )

    reducer.apply(_tick(1), state)

    assert SOEventType.PILOT_KILLED not in _types(emitted)


# ---------------------------------------------------------------------------
# Area damage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_area_damage_within_three_cells_only() -> None:
    """Chebyshev distance 3 takes area damage; distance 4 takes none."""
    exploder = _make_mech("mech.red.01", "player.a", heat_current=100)
    near = _make_mech("mech.red.02", "player.a", position=ModelSOPosition(x=3, y=3))
    far = _make_mech("mech.blue.01", "player.b", position=ModelSOPosition(x=4, y=0))
    state = _make_match(exploder, near, far, seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert new_state.mech_states["mech.red.02"].hp == 100 - RUPTURE_AREA_DAMAGE
    assert new_state.mech_states["mech.blue.01"].hp == 100

    area_hits = [
        e
        for e in emitted
        if e.event_type == SOEventType.DAMAGE_APPLIED
        and e.payload["cause"] == SODestructionCause.RUPTURE_AREA_DAMAGE.value
    ]
    assert [e.subject.mech_id for e in area_hits] == ["mech.red.02"]
    assert area_hits[0].payload["damage"] == RUPTURE_AREA_DAMAGE
    assert area_hits[0].payload["radius_cells"] == RUPTURE_AREA_RADIUS_CELLS


@pytest.mark.unit
def test_area_damage_destroys_low_hp_neighbor() -> None:
    exploder = _make_mech("mech.red.01", "player.a", heat_current=100)
    weak = _make_mech("mech.red.02", "player.a", hp=10, position=ModelSOPosition(x=1, y=1))
    bystander = _make_mech("mech.blue.01", "player.b", position=ModelSOPosition(x=9, y=9))
    state = _make_match(exploder, weak, bystander, seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    updated = new_state.mech_states["mech.red.02"]
    assert updated.hp == 0
    assert updated.alive is False

    destroyed = [
        e
        for e in emitted
        if e.event_type == SOEventType.MECH_DESTROYED and e.subject.mech_id == "mech.red.02"
    ]
    assert len(destroyed) == 1
    assert destroyed[0].payload["cause"] == SODestructionCause.RUPTURE_AREA_DAMAGE.value


# ---------------------------------------------------------------------------
# Victory declaration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rupture_declares_victory_in_same_tick() -> None:
    """Invariant: a rupture at tick N emits VICTORY_DECLARED at tick N when only
    one player has surviving mechs afterwards."""
    doomed = _make_mech("mech.red.01", "player.a", heat_current=100)
    survivor = _make_mech("mech.blue.01", "player.b", position=ModelSOPosition(x=9, y=9))
    state = _make_match(doomed, survivor, seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    tick_n = 5
    reducer.apply(_tick(tick_n), state)

    victories = [e for e in emitted if e.event_type == SOEventType.VICTORY_DECLARED]
    assert len(victories) == 1
    assert victories[0].tick == tick_n
    assert victories[0].payload["winner_player_id"] == "player.b"
    assert victories[0].payload["reason"] == SOMatchEndReason.LAST_MECH_STANDING.value
    # Victory is the final event of the cascade for the tick.
    assert emitted[-1].event_type == SOEventType.VICTORY_DECLARED


@pytest.mark.unit
def test_no_victory_when_no_survivors() -> None:
    """Mutual destruction leaves zero surviving players -> no VICTORY_DECLARED
    (the lifecycle reducer's max_ticks draw is the terminal backstop)."""
    red = _make_mech("mech.red.01", "player.a", heat_current=100)
    blue = _make_mech(
        "mech.blue.01", "player.b", heat_current=100, position=ModelSOPosition(x=9, y=9)
    )
    state = _make_match(red, blue, seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert SOEventType.VICTORY_DECLARED not in _types(emitted)
    assert new_state.surviving_player_ids() == frozenset()


@pytest.mark.unit
def test_no_victory_when_multiple_players_survive() -> None:
    doomed = _make_mech("mech.red.01", "player.a", heat_current=100)
    ally = _make_mech("mech.red.02", "player.a", position=ModelSOPosition(x=9, y=9))
    enemy = _make_mech("mech.blue.01", "player.b", position=ModelSOPosition(x=0, y=9))
    state = _make_match(doomed, ally, enemy, seed=1)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    reducer.apply(_tick(1), state)

    assert SOEventType.VICTORY_DECLARED not in _types(emitted)


# ---------------------------------------------------------------------------
# Folding externally produced death events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_external_mech_destroyed_folds_and_declares_victory() -> None:
    red = _make_mech("mech.red.01", "player.a")
    blue = _make_mech("mech.blue.01", "player.b")
    state = _make_match(red, blue)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    destroyed_env = _env(
        SOEventType.MECH_DESTROYED,
        tick=4,
        subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.a"),
        payload={"cause": "cumulative_damage"},
    )
    new_state = reducer.apply(destroyed_env, state)

    assert new_state.mech_states["mech.red.01"].alive is False
    victories = [e for e in emitted if e.event_type == SOEventType.VICTORY_DECLARED]
    assert len(victories) == 1
    assert victories[0].payload["winner_player_id"] == "player.b"

    # Idempotent re-fold: no state change, no duplicate VICTORY_DECLARED.
    refolded = reducer.apply(destroyed_env, new_state)
    assert refolded == new_state
    assert _types(emitted).count(SOEventType.VICTORY_DECLARED) == 1


@pytest.mark.unit
def test_external_pilot_killed_folds_and_declares_victory() -> None:
    red = _make_mech("mech.red.01", "player.a")
    blue = _make_mech("mech.blue.01", "player.b")
    state = _make_match(red, blue)
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    killed_env = _env(
        SOEventType.PILOT_KILLED,
        tick=4,
        subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.a"),
        payload={},
    )
    new_state = reducer.apply(killed_env, state)

    assert new_state.mech_states["mech.red.01"].pilot_alive is False
    victories = [e for e in emitted if e.event_type == SOEventType.VICTORY_DECLARED]
    assert len(victories) == 1
    assert victories[0].payload["winner_player_id"] == "player.b"

    refolded = reducer.apply(killed_env, new_state)
    assert refolded == new_state
    assert _types(emitted).count(SOEventType.VICTORY_DECLARED) == 1


# ---------------------------------------------------------------------------
# Replay determinism
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replay_produces_identical_outcomes() -> None:
    """Invariant: two replays of the same event sequence produce identical
    rupture/survival outcomes and identical final state."""

    def run() -> tuple[ModelSOMatchState, list[tuple[SOEventType, dict[str, Any]]]]:
        red = _make_mech("mech.red.01", "player.a", heat_current=75)
        near = _make_mech("mech.red.02", "player.a", hp=10, position=ModelSOPosition(x=2, y=2))
        blue = _make_mech("mech.blue.01", "player.b", position=ModelSOPosition(x=9, y=9))
        state = _make_match(red, near, blue, seed=0)
        emitted: list[ModelSOEventEnvelope] = []
        reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)
        state = _run_ticks(reducer, state, range(1, 8))
        return state, [(e.event_type, e.payload) for e in emitted]

    state_a, events_a = run()
    state_b, events_b = run()

    assert state_a == state_b
    assert events_a == events_b
    assert SOEventType.BOILER_RUPTURED in [t for t, _ in events_a]


# ---------------------------------------------------------------------------
# Scope guards
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ignores_events_for_other_matches() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_env(SOEventType.MATCH_TICK, tick=1, match_id="match.other"), state)

    assert new_state == state
    assert emitted == []


@pytest.mark.unit
def test_tick_on_non_running_match_is_ignored() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(
        mech,
        _make_mech("mech.blue.01", "player.b"),
        status=SOMatchStatus.ENDED,
        end_reason=SOMatchEndReason.ABORTED,
    )
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(_tick(1), state)

    assert new_state == state
    assert emitted == []


@pytest.mark.unit
def test_unrelated_events_are_ignored() -> None:
    mech = _make_mech("mech.red.01", "player.a", heat_current=100)
    state = _make_match(mech, _make_mech("mech.blue.01", "player.b"))
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerFailureCascade(_MATCH_ID, emit=emitted.append)

    new_state = reducer.apply(
        _env(
            SOEventType.SENSOR_OBSERVATION,
            tick=1,
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.a"),
            payload={"distance_estimate": 4.0},
        ),
        state,
    )

    assert new_state == state
    assert emitted == []
