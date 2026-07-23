"""Phase 2 cross-boundary regression — the REAL runner emits UTILITY_DEPLOYED.

Drives the actual runner seam, not a surrogate: a resolved utility deploy
intent flows through ``MatchRunner._resolve_utility`` (Stage B), which selects
the allowlisted resolution handler, stamps the deploying mech's live cell as the
origin, and publishes a payload-valid, causation-chained UTILITY_DEPLOYED on the
real bus.  The runner's real ``MatchStateFold`` folds it, and the runner's own
LOS-obstacle union (the smoke consult) blocks a previously-clear line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.events.payloads import ModelSOUtilityDeployedPayload
from steel_onslaught.match.geometry import line_of_sight_clear
from steel_onslaught.match.state import ModelSOMatchState, SOMatchStatus
from steel_onslaught.match.utility_effects import smoke_obstacle_cells
from steel_onslaught.pilots.schemas import ModelSOPosition
from tests.runtime import match_runner

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")


def _open_arena(spawn_a: tuple[int, int], spawn_b: tuple[int, int]) -> ModelSOArenaSpec:
    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_utility_e2e",
            "display_name": "Utility e2e arena",
            "size": 40,
            "spawn_a": {"x": spawn_a[0], "y": spawn_a[1]},
            "spawn_b": {"x": spawn_b[0], "y": spawn_b[1]},
            "obstacles": [],
            "rects": [],
            "sudden_death_start_tick": 100,
            "sudden_death_damage_base": 8,
        }
    )


@pytest.mark.integration
def test_runner_resolve_utility_emits_and_smoke_blocks_a_clear_line() -> None:
    from steel_onslaught.match.composition import load_loadout

    match_id = "match.test.utility-e2e"
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)

    loadout = load_loadout(_LOADOUT)
    runner, runtime = match_runner(
        bus=bus,
        match_id=match_id,
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=None,
        arena_override=_open_arena((5, 5), (5, 9)),
    )
    # The runner's real fold subscribes to the bus; drive it to spawn the roster.
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
    state = ModelSOMatchState(
        match_id=match_id,
        seed=7,
        tick=2,
        status=SOMatchStatus.RUNNING,
        mech_states={red.mech_id: red, blue.mech_id: blue},
    )

    # BEFORE: the line red -> blue is clear (no smoke, real runner obstacle set).
    a, b = red.position, blue.position
    obstacles = runner._obstacles
    assert line_of_sight_clear(a, b, obstacles) is True

    # A resolved utility card => a typed deploy intent for RED.
    intent = runtime.event_factory.make(
        match_id=match_id,
        correlation_id=runner.identity.correlation_id,
        tick=2,
        sequence_in_tick=0,
        event_type=SOEventType.UTILITY_DEPLOY_INTENT,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        payload={
            "card_id": "card.utility.smoke",
            "utility_kind": "smoke",
            "radius": 2,
            "duration_ticks": 3,
        },
    )

    # Drive the REAL runner emit seam (Stage B).
    runner._resolve_utility(intent, state, red)

    deployed_events = [e for e in captured if e.event_type is SOEventType.UTILITY_DEPLOYED]
    assert len(deployed_events) == 1
    deployed = deployed_events[0]
    payload = ModelSOUtilityDeployedPayload.model_validate(deployed.payload)
    # Origin is the deploying mech's live cell; the runner stamped it.
    assert payload.origin == ModelSOPosition(x=5, y=5)
    assert payload.utility_kind == "smoke"
    assert payload.radius == 2
    assert payload.card_id == "card.utility.smoke"
    # Causation chains UTILITY_DEPLOYED back to the deploy intent.
    assert deployed.causation_id == intent.envelope.message_id
    assert deployed.subject.mech_id == "mech.a.01"

    # The runner's fold folded the emitted event; the runner's LOS-obstacle
    # union (the smoke consult) now blocks the previously-clear line.
    effects = runner.fold.state.active_utility_effects
    assert len(effects) == 1
    los_obstacles = obstacles | smoke_obstacle_cells(effects, state.tick)
    assert line_of_sight_clear(a, b, los_obstacles) is False
