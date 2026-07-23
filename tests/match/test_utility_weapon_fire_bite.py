"""Phase 2 U-GATE bite proof: chaff and flares degrade REAL weapon fire.

The scaffold proved chaff/flares only at the pure-function level (and with a
manually-set ``lock_confidence=0``).  These regressions instead drive the actual
``MatchRunner._resolve_weapon_fire`` seam end to end: a weapon is fired at a
target while a runner-folded chaff aura / flare is ACTIVE on that target, and the
emitted ``WEAPON_FIRED.hit_probability`` is asserted to actually drop.

Every effect here is real — deployed through the runner's own ``_resolve_utility``
emit seam and folded by the runner's ``MatchStateFold`` — not a hand-built
effect tuple.  No balance knob is touched: the weapon's damage/range/accuracy
curve are unchanged; only the counterplay consult moves the number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.geometry import line_of_sight_clear
from steel_onslaught.match.runner import MatchRunner
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchStatus,
)
from steel_onslaught.match.utility_effects import (
    ModelSOUtilityEffect,
    chaff_targeting_debuff,
    flare_lock_broken,
)
from steel_onslaught.pilots.schemas import ModelSOPosition

# Aliased so pytest does not try to collect the ``Test``-prefixed fixture class.
from tests.runtime import TestRuntime as RuntimeFixture
from tests.runtime import match_runner

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_WEAPON_ID = "weapon.light.machine_gun"
_MATCH_ID = "match.test.utility-bite"


def _open_arena() -> ModelSOArenaSpec:
    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_utility_bite",
            "display_name": "Utility bite arena",
            "size": 40,
            "spawn_a": {"x": 5, "y": 5},
            "spawn_b": {"x": 5, "y": 9},
            "obstacles": [],
            "rects": [],
            "sudden_death_start_tick": 100,
            "sudden_death_damage_base": 8,
        }
    )


def _mechs(
    runner: MatchRunner, loadout: ModelSOLoadout
) -> tuple[ModelSOMechRuntimeState, ModelSOMechRuntimeState]:
    red = runner._build_mech(
        loadout,
        mech_id="mech.a.01",
        player_id="player.a",
        side="red",
        position=ModelSOPosition(x=5, y=5),
        facing=45,
    )
    blue = runner._build_mech(
        loadout,
        mech_id="mech.b.01",
        player_id="player.b",
        side="blue",
        position=ModelSOPosition(x=5, y=9),
        facing=225,
    )
    return red, blue


def _seed_lock(runner: MatchRunner, runtime: RuntimeFixture, tick: int) -> None:
    """Put a real sensor lock (RED observing BLUE) into the runner's buffer.

    Because ``resolve_hit_probability`` multiplies by ``lock_confidence``, a
    baseline shot needs a lock to be non-zero; the flare test then proves the
    flare removes exactly that lock.
    """

    observation = runtime.event_factory.make(
        match_id=_MATCH_ID,
        correlation_id=runner.identity.correlation_id,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.SENSOR_OBSERVATION,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        payload={
            "enemy_mech_id": "mech.b.01",
            "distance_estimate": 4.0,
            "confidence": 0.9,
        },
    )
    runner._sensor_buffer.append(observation)


def _deploy_by_blue(
    runner: MatchRunner,
    runtime: RuntimeFixture,
    *,
    utility_kind: str,
    radius: int,
    duration_ticks: int,
    tick: int,
    blue: ModelSOMechRuntimeState,
) -> tuple[ModelSOUtilityEffect, ...]:
    """Deploy a utility card BY BLUE through the real runner emit seam.

    Returns the runner-folded active effects so the caller can consult the same
    tuple the weapon-fire resolver reads.
    """

    deploy_state = ModelSOMatchState(
        match_id=_MATCH_ID,
        seed=7,
        tick=tick,
        status=SOMatchStatus.RUNNING,
        mech_states={blue.mech_id: blue},
    )
    intent = runtime.event_factory.make(
        match_id=_MATCH_ID,
        correlation_id=runner.identity.correlation_id,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.UTILITY_DEPLOY_INTENT,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.b.01", player_id="player.b"),
        payload={
            "card_id": f"card.utility.{utility_kind}",
            "utility_kind": utility_kind,
            "radius": radius,
            "duration_ticks": duration_ticks,
        },
    )
    runner._resolve_utility(intent, deploy_state, blue)
    effects = runner.fold.state.active_utility_effects
    assert effects, "the runner must have folded the deployed effect"
    return effects


def _fire_hit_probability(
    runner: MatchRunner,
    runtime: RuntimeFixture,
    *,
    red: ModelSOMechRuntimeState,
    blue: ModelSOMechRuntimeState,
    effects: tuple[ModelSOUtilityEffect, ...],
    tick: int,
) -> float:
    """Fire RED's weapon at BLUE through the real resolver; return hit_probability."""

    captured: list[ModelSOEventEnvelope] = []
    runner._bus.subscribe(captured.append)
    state = ModelSOMatchState(
        match_id=_MATCH_ID,
        seed=7,
        tick=tick,
        status=SOMatchStatus.RUNNING,
        mech_states={red.mech_id: red, blue.mech_id: blue},
        active_utility_effects=effects,
    )
    intent = runtime.event_factory.make(
        match_id=_MATCH_ID,
        correlation_id=runner.identity.correlation_id,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.WEAPON_FIRE_INTENT,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        payload={"weapon_id": _WEAPON_ID, "target_mech_id": "mech.b.01"},
    )
    runner._resolve_weapon_fire(intent, state, red)
    fired = [e for e in captured if e.event_type is SOEventType.WEAPON_FIRED]
    assert len(fired) == 1, "exactly one WEAPON_FIRED must be emitted"
    return float(fired[0].payload["hit_probability"])


@pytest.mark.integration
def test_chaff_aura_reduces_hit_probability_through_runner() -> None:
    bus = InProcessEventBus()
    from steel_onslaught.match.composition import load_loadout

    loadout = load_loadout(_LOADOUT)
    runner, runtime = match_runner(
        bus=bus,
        match_id=_MATCH_ID,
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=None,
        arena_override=_open_arena(),
    )
    red, blue = _mechs(runner, loadout)
    assert line_of_sight_clear(red.position, blue.position, runner._obstacles) is True
    _seed_lock(runner, runtime, tick=2)

    # Baseline: locked shot, no chaff active.
    baseline = _fire_hit_probability(runner, runtime, red=red, blue=blue, effects=(), tick=2)
    assert baseline > 0.0, "a locked, LOS-clear shot must have positive hit probability"

    # Deploy chaff BY BLUE (aura on the target), then fire the same shot.
    effects = _deploy_by_blue(
        runner, runtime, utility_kind="chaff", radius=2, duration_ticks=3, tick=2, blue=blue
    )
    # The consult the resolver uses reports a real, positive debuff on the target.
    assert chaff_targeting_debuff(effects, "mech.b.01", 2) > 0.0
    red2, blue2 = _mechs(runner, loadout)  # fresh mechs => no cooldown/pressure carryover
    with_chaff = _fire_hit_probability(
        runner, runtime, red=red2, blue=blue2, effects=effects, tick=2
    )

    assert with_chaff < baseline, (
        f"chaff must lower hit probability through the real resolver "
        f"(baseline={baseline}, with_chaff={with_chaff})"
    )


@pytest.mark.integration
def test_flare_breaks_lock_and_zeros_hit_probability_through_runner() -> None:
    bus = InProcessEventBus()
    from steel_onslaught.match.composition import load_loadout

    loadout = load_loadout(_LOADOUT)
    runner, runtime = match_runner(
        bus=bus,
        match_id=_MATCH_ID,
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=None,
        arena_override=_open_arena(),
    )
    red, blue = _mechs(runner, loadout)
    assert line_of_sight_clear(red.position, blue.position, runner._obstacles) is True
    _seed_lock(runner, runtime, tick=2)

    # Baseline: the lock (confidence 0.9) drives a positive aimed-shot probability.
    locked = _fire_hit_probability(runner, runtime, red=red, blue=blue, effects=(), tick=2)
    assert locked > 0.0, "a locked shot must have positive hit probability"

    # Deploy flares BY BLUE — the decoy spoils the lock on the target.
    effects = _deploy_by_blue(
        runner, runtime, utility_kind="flares", radius=1, duration_ticks=3, tick=2, blue=blue
    )
    assert flare_lock_broken(effects, "mech.b.01", 2) is True
    red2, blue2 = _mechs(runner, loadout)
    with_flare = _fire_hit_probability(
        runner, runtime, red=red2, blue=blue2, effects=effects, tick=2
    )

    # The flare zeros lock_confidence => the aimed shot collapses to a miss.
    assert with_flare < locked, (
        f"flare must break the lock and lower hit probability "
        f"(locked={locked}, with_flare={with_flare})"
    )
    assert with_flare == 0.0, "a fully broken lock zeros the aimed hit probability"
