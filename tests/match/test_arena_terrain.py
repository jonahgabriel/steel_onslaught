"""Injected arena runtime, movement, LOS, and strict replay-truth proof."""

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPosition,
    SOPilotAction,
    SOPilotReasonCode,
)
from tests.runtime import match_runner

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")


class _FirePilot:
    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        del observation
        return ModelSOPilotDecision(
            action=SOPilotAction.FIRE_WEAPON,
            action_params={"weapon_id": "weapon.light.machine_gun"},
            reason_code=SOPilotReasonCode.TARGET_IN_RANGE,
            confidence=1.0,
            considered_actions=(
                ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=1.0),
            ),
        )


def _wall_arena() -> ModelSOArenaSpec:
    return ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="test_wall",
        display_name="Test wall",
        size=12,
        spawn_a=ModelSOPosition(x=1, y=5),
        spawn_b=ModelSOPosition(x=10, y=5),
        obstacles=(ModelSOPosition(x=5, y=5),),
        rects=(),
    )


@pytest.mark.integration
def test_injected_arena_snapshot_blocks_weapon_line_of_sight() -> None:
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    arena = _wall_arena()
    loadout = load_loadout(_LOADOUT)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.test.terrain-los",
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=2,
        arena_override=arena,
        pilots_override={"mech.a.01": _FirePilot(), "mech.b.01": _FirePilot()},
    )

    runner.run()

    started = next(event for event in events if event.event_type is SOEventType.MATCH_STARTED)
    assert started.model_dump(mode="json")["payload"]["arena"] == (
        arena.to_snapshot().model_dump(mode="json")
    )
    fired = [event for event in events if event.event_type is SOEventType.WEAPON_FIRED]
    assert fired
    assert all(event.payload["hit_probability"] == 0.0 for event in fired)
    assert not any(event.event_type is SOEventType.HIT_RESOLVED for event in events)


@pytest.mark.unit
def test_runner_walk_stops_before_injected_obstacle() -> None:
    bus = InProcessEventBus()
    arena = _wall_arena()
    loadout = load_loadout(_LOADOUT)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.test.terrain-movement",
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=2,
        arena_override=arena,
    )

    reached = runner._walk_to(
        ModelSOPosition(x=1, y=5),
        ModelSOPosition(x=10, y=5),
    )

    assert reached == ModelSOPosition(x=4, y=5)
    assert (reached.x, reached.y) not in arena.obstacle_cells
