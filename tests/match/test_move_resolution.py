"""Property proof: the show-dont-tell consequence preview can never diverge
from the live match resolver (2026-07-24 spatial representation arms R1/R2).

``resolve_move_destination`` (``match.move_resolution``) was extracted from
``MatchRunner._resolve_move`` specifically so a prompt-facing consequence
preview and the live resolver call the SAME function. These tests drive both
paths -- the real ``MatchRunner._resolve_move`` (via a real injected-arena
match) and the standalone pure function -- from the identical pre-move state
and assert they agree, including the obstacle-blocked / greedy-sidestep case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.move_resolution import resolve_move_destination
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPosition,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.reducers.movement import effective_speed
from tests.runtime import match_runner

pytestmark = pytest.mark.unit

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_PRODUCER_NODE = "test.node.move_resolution_proof"


class _RemainPilot:
    """Always REMAIN -- holds both mechs at spawn for a known pre-move state."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        del observation
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0),),
        )


def _wall_arena() -> ModelSOArenaSpec:
    """Same shape as ``test_arena_terrain.py``'s wall, isolated to this module."""

    return ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="test_wall_move_resolution",
        display_name="Test wall (move resolution proof)",
        size=12,
        spawn_a=ModelSOPosition(x=1, y=5),
        spawn_b=ModelSOPosition(x=10, y=5),
        obstacles=(ModelSOPosition(x=5, y=5),),
        rects=(),
    )


def _open_arena() -> ModelSOArenaSpec:
    return ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="test_open_move_resolution",
        display_name="Test open field (move resolution proof)",
        size=20,
        spawn_a=ModelSOPosition(x=2, y=10),
        spawn_b=ModelSOPosition(x=17, y=10),
        obstacles=(),
        rects=(),
    )


@pytest.mark.parametrize(
    ("arena_factory", "direction"),
    [
        (_open_arena, "toward_enemy"),
        (_open_arena, "defensive"),
        (_open_arena, "flank_left"),
        (_open_arena, "flank_right"),
        # Directly at the obstacle's Chebyshev-adjacent approach: exercises
        # the walk-stops-at-terrain AND greedy-sidestep fallback branches, the
        # exact code path a naive re-implementation would be most likely to
        # get wrong.
        (_wall_arena, "toward_enemy"),
    ],
)
def test_preview_matches_live_resolution(
    arena_factory: object,
    direction: str,
) -> None:
    """``resolve_move_destination`` must equal what ``MatchRunner._resolve_move``
    actually publishes, driven from the identical pre-move state."""

    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    arena = arena_factory()  # type: ignore[operator]
    loadout = load_loadout(_LOADOUT)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.test.move-resolution-proof",
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=1,
        arena_override=arena,
        pilots_override={"mech.a.01": _RemainPilot(), "mech.b.01": _RemainPilot()},
    )
    # One REMAIN-only tick establishes a known, unmoved pre-move state (both
    # mechs still at their spawn cells) before this test drives its own
    # scripted MOVE_INTENT below.
    runner.run()
    events.clear()

    state = runner.fold.state
    mech = state.mech_states["mech.a.01"]
    enemy = state.mech_states["mech.b.01"]
    pre_move_position = mech.position
    assert pre_move_position == arena.spawn_a
    assert enemy.position == arena.spawn_b

    intent = runner._events.make(
        match_id=runner._match_id,
        tick=state.tick,
        sequence_in_tick=0,
        event_type=SOEventType.MOVE_INTENT,
        producer_node=_PRODUCER_NODE,
        subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
        payload={"direction": direction},
        correlation_id=runner._correlation_id,
    )
    runner._resolve_move(intent, state, mech)

    resolved = [event for event in events if event.event_type is SOEventType.MOVEMENT_RESOLVED]
    assert len(resolved) <= 1

    budget = min(effective_speed(mech), mech.boiler.pressure_current)
    preview = resolve_move_destination(
        from_pos=pre_move_position,
        direction=direction,  # type: ignore[arg-type]
        budget=budget,
        enemy_pos=enemy.position,
        obstacles=arena.obstacle_cells,
        arena_size=arena.size,
    )

    if resolved:
        payload = resolved[0].payload
        actual = ModelSOPosition(x=payload["to"]["x"], y=payload["to"]["y"])
        assert preview == actual
        assert preview != pre_move_position
    else:
        # The runner treated this as a pinned/no-op move (no MOVEMENT_RESOLVED
        # published); the preview must agree that nothing moved.
        assert preview == pre_move_position
