"""Phase 4 — objective control, VP fold, and the vp_threshold victory.

Covers the design's Phase 4 seam table (2026-07-22 unified depth+learning,
§6) at the fold boundary:

  - mutual contest scores for NOBODY (the control rule, not arrival order);
  - a sole controller accrues VP per round with a durable OBJECTIVE_SCORED
    record per award;
  - reaching ``vp_threshold`` exactly declares VICTORY_DECLARED with
    ``reason=vp_threshold`` + ``victory_kind=vp_threshold``;
  - the explicit tick-cap bound is classified ``tick_cap_failsafe``;
  - a bus-less refold of the SAME canonical stream reproduces the state
    (replay identity for the new VP fold).

The full-runner cross-boundary test (real match on ``foundry_60_asym_v1`` to
a vp_threshold terminal, replay validity, evidence projection) lives in
``tests/match/test_objective_match_e2e.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.payloads import (
    ModelSOObjectiveScoredPayload,
    ModelSOVictoryDeclaredPayload,
)
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.objectives import (
    OBJECTIVE_CONTROL_RADIUS,
    classify_control,
    objective_controller,
)
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.schemas import ModelSOPosition
from tests.runtime import TestRuntime as _TestRuntime
from tests.runtime import runtime_dependencies

_MATCH_ID = "match.test.objective-scoring"
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")


def _objective_arena(
    *,
    spawn_a: tuple[int, int],
    spawn_b: tuple[int, int],
    objectives: tuple[tuple[str, int, int, int], ...],
    vp_threshold: int,
) -> ModelSOArenaSpec:
    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_objectives",
            "display_name": "Objective test arena",
            "size": 40,
            "spawn_a": {"x": spawn_a[0], "y": spawn_a[1]},
            "spawn_b": {"x": spawn_b[0], "y": spawn_b[1]},
            "obstacles": [],
            "rects": [],
            "objectives": [
                {
                    "objective_id": objective_id,
                    "cell": {"x": x, "y": y},
                    "vp_per_round": vp,
                }
                for objective_id, x, y, vp in objectives
            ],
            "vp_threshold": vp_threshold,
        }
    )


def _runtime_with(arena: ModelSOArenaSpec) -> _TestRuntime:
    runtime = runtime_dependencies()
    return _TestRuntime(
        event_factory=runtime.event_factory,
        catalog=MatchContractCatalog(
            arenas={**runtime.catalog.arenas, arena.arena_id: arena},
            chassis=runtime.catalog.chassis,
            boilers=runtime.catalog.boilers,
            sensors=runtime.catalog.sensors,
            weapons=runtime.catalog.weapons,
            gizmos=runtime.catalog.gizmos,
            transitions=runtime.catalog.transitions,
        ),
        arena=arena,
    )


def _env(
    event_type: SOEventType,
    *,
    tick: int,
    subject: ModelSOEventSubject = _MATCH_SUBJECT,
    payload: dict[str, Any] | None = None,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=_MATCH_ID,
        tick=tick,
        sequence_in_tick=0,
        event_type=event_type,
        producer_node="node.test",
        subject=subject,
        payload=payload or {},
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id=_MATCH_ID,
            emitted_at=datetime.now(UTC),
        ),
    )


def _mech_dict(
    mech_id: str,
    player_id: str,
    *,
    position: tuple[int, int],
    side: str,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.mech_runtime_state",
        "mech_id": mech_id,
        "player_id": player_id,
        "side": side,
        "loadout_id": "loadout.a",
        "pilot_id": "pilot.aggressive",
        "chassis_id": "chassis.medium.hunter_mk1",
        "chassis_class": "medium",
        "sensor_ids": [],
        "gizmo_ids": [],
        "base_speed": 4,
        "position": {"x": position[0], "y": position[1]},
        "facing": 45,
        "speed": 4,
        "hp": 100,
        "hp_max": 100,
        "armor_value": 10,
        "armor_max": 10,
        "alive": True,
        "pilot_alive": True,
        "current_mode": "recon",
        "mode_lock_until": 0,
        "transition_ticks_remaining": 0,
        "transition_to_mode": None,
        "sensor_dropout_ticks_remaining": 0,
        "mode_switch_disabled_until": 0,
        "weapon_cooldowns": {},
        "evasion": 0.0,
        "accuracy_penalty_next_fire": 0.0,
        "jamming_intensity": 0.0,
        "under_sensor_lock": False,
        "boiler": {
            "match_id": _MATCH_ID,
            "mech_id": mech_id,
            "tick": 0,
            "pressure_current": 30,
            "pressure_maximum": 60,
            "regeneration_per_tick": 5,
            "heat_current": 0,
            "heat_redline_threshold": 80,
            "heat_rupture_threshold": 100,
            "heat_vent_rate": 5,
            "status_redline": False,
            "status_rupture_warning": False,
            "status_disabled": False,
            "status_ruptured": False,
            "modifier_heat_weapon_pressure": 1.0,
            "modifier_venting_penalty": 0.0,
            "modifier_mode_switch_heat_delta": 0,
        },
        "redline_consecutive_ticks": 0,
        "overloaded": False,
        "overloaded_consecutive_ticks": 0,
    }


def _start_match(
    bus: InProcessEventBus,
    runtime: _TestRuntime,
    *,
    spawn_a: tuple[int, int],
    spawn_b: tuple[int, int],
) -> tuple[MatchStateFold, list[ModelSOEventEnvelope]]:
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold = MatchStateFold(
        _MATCH_ID,
        UUID("11111111-1111-1111-1111-111111111111"),
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )
    bus.subscribe(fold.handle)
    bus.publish(
        _env(
            SOEventType.MATCH_STARTED,
            tick=0,
            payload={
                "seed": 1,
                "max_ticks": 200,
                "mechs": [
                    _mech_dict("mech.red.01", "player.red", position=spawn_a, side="red"),
                    _mech_dict("mech.blue.01", "player.blue", position=spawn_b, side="blue"),
                ],
                "arena": runtime.arena.to_snapshot().model_dump(mode="json"),
            },
        )
    )
    assert fold.state.status is SOMatchStatus.RUNNING
    return fold, captured


# ---------------------------------------------------------------------------
# Control rule (pure helpers)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_control_radius_is_the_king_move_ring() -> None:
    """Exactly-on-cell control would make mutual contest impossible."""

    assert OBJECTIVE_CONTROL_RADIUS == 1


@pytest.mark.unit
def test_mutual_contest_controls_for_nobody() -> None:
    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(6, 6),
        objectives=(("objective.contested", 5, 6, 1),),
        vp_threshold=3,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(6, 6))

    for tick in range(1, 4):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))

    assert fold.state.status is SOMatchStatus.RUNNING
    assert fold.state.vp_totals == {"player.blue": 0, "player.red": 0}
    assert not [e for e in captured if e.event_type is SOEventType.OBJECTIVE_SCORED]
    cell = ModelSOPosition(x=5, y=6)
    assert objective_controller(cell, fold.state) is None
    assert classify_control(cell, fold.state, viewer_player_id="player.red") == "contested"


@pytest.mark.unit
def test_unclaimed_objective_scores_for_nobody() -> None:
    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(35, 35),
        objectives=(("objective.far", 20, 20, 1),),
        vp_threshold=3,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(35, 35))

    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))

    assert fold.state.vp_totals == {"player.blue": 0, "player.red": 0}
    assert not [e for e in captured if e.event_type is SOEventType.OBJECTIVE_SCORED]
    cell = ModelSOPosition(x=20, y=20)
    assert classify_control(cell, fold.state, viewer_player_id="player.red") == "unclaimed"


# ---------------------------------------------------------------------------
# Threshold-exact victory + replay identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_threshold_exact_control_declares_vp_victory() -> None:
    """Red holds the objective alone; VP hits the threshold EXACTLY."""

    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(35, 35),
        objectives=(("objective.red_yard", 5, 6, 1),),
        vp_threshold=3,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(35, 35))

    for tick in range(1, 4):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))

    # Terminal: ENDED on the exact threshold round, reason vp_threshold.
    assert fold.state.status is SOMatchStatus.ENDED
    assert fold.state.winner_id == "player.red"
    assert fold.state.end_reason is SOMatchEndReason.VP_THRESHOLD
    assert fold.state.vp_totals == {"player.blue": 0, "player.red": 3}
    assert fold.state.tick == 3

    # One durable OBJECTIVE_SCORED per controlled round, cumulative and exact.
    scored = [e for e in captured if e.event_type is SOEventType.OBJECTIVE_SCORED]
    assert len(scored) == 3
    payloads = [ModelSOObjectiveScoredPayload.model_validate(e.payload) for e in scored]
    assert [p.cumulative_vp["player.red"] for p in payloads] == [1, 2, 3]
    assert all(p.objective_id == "objective.red_yard" for p in payloads)
    assert all(p.controlling_player_id == "player.red" for p in payloads)
    assert [p.round_index for p in payloads] == [1, 2, 3]
    assert scored[0].subject.mech_id == "mech.red.01"

    # The victory names both the reason and the kind.
    victories = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victories) == 1
    victory = ModelSOVictoryDeclaredPayload.model_validate(victories[0].payload)
    assert victory.winner_player_id == "player.red"
    assert victory.reason is SOMatchEndReason.VP_THRESHOLD
    assert victory.victory_kind == "vp_threshold"

    # No further scoring after the terminal.
    assert max(e.tick for e in scored) == 3


@pytest.mark.unit
def test_vp_fold_is_replay_identical_from_the_canonical_stream() -> None:
    """A bus-less refold of the recorded stream reproduces the VP state."""

    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(35, 35),
        objectives=(("objective.red_yard", 5, 6, 1),),
        vp_threshold=3,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(35, 35))
    for tick in range(1, 4):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))
    assert fold.state.status is SOMatchStatus.ENDED

    replay_fold = MatchStateFold(
        _MATCH_ID,
        UUID("11111111-1111-1111-1111-111111111111"),
        bus=None,  # replay path: emissions discarded, ledger events re-fold
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )
    for event in captured:
        replay_fold.apply(event)

    assert replay_fold.state == fold.state
    assert replay_fold.state.vp_totals == {"player.blue": 0, "player.red": 3}


@pytest.mark.unit
def test_threshold_tie_declares_nothing_until_totals_diverge() -> None:
    """Both sides at the line with equal totals: play on, no invented winner."""

    # Two symmetric objectives, one per side, threshold reached the same round.
    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(35, 35),
        objectives=(
            ("objective.red_side", 5, 6, 1),
            ("objective.blue_side", 35, 36, 1),
        ),
        vp_threshold=2,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(35, 35))

    for tick in range(1, 4):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))

    assert fold.state.status is SOMatchStatus.RUNNING
    assert fold.state.vp_totals == {"player.blue": 3, "player.red": 3}
    assert not [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]


# ---------------------------------------------------------------------------
# Elimination + failsafe classification
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_elimination_victory_carries_victory_kind() -> None:
    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(35, 35),
        objectives=(("objective.far", 20, 20, 1),),
        vp_threshold=50,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(35, 35))

    bus.publish(
        _env(
            SOEventType.MECH_DESTROYED,
            tick=1,
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
            payload={"cause": "weapon_damage", "source_mech_id": "mech.blue.01"},
        )
    )

    assert fold.state.status is SOMatchStatus.ENDED
    victories = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victories) == 1
    victory = ModelSOVictoryDeclaredPayload.model_validate(victories[0].payload)
    assert victory.reason is SOMatchEndReason.LAST_MECH_STANDING
    assert victory.victory_kind == "elimination"


@pytest.mark.unit
def test_tick_cap_bound_is_classified_tick_cap_failsafe() -> None:
    """A clock ending is an anomaly: same reason, distinct victory_kind."""

    arena = _objective_arena(
        spawn_a=(5, 5),
        spawn_b=(35, 35),
        objectives=(("objective.far", 20, 20, 1),),
        vp_threshold=50,
    )
    runtime = _runtime_with(arena)
    bus = InProcessEventBus()
    fold, captured = _start_match(bus, runtime, spawn_a=(5, 5), spawn_b=(35, 35))

    # Kill blue at tick 1... no: a death declares elimination immediately.
    # Instead drive a max_ticks=3 lifecycle: re-start with explicit small cap.
    del fold, captured
    bus2 = InProcessEventBus()
    captured2: list[ModelSOEventEnvelope] = []
    bus2.subscribe(captured2.append)
    fold2 = MatchStateFold(
        _MATCH_ID,
        UUID("11111111-1111-1111-1111-111111111111"),
        bus=bus2,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )
    bus2.subscribe(fold2.handle)
    dead_red = _mech_dict("mech.red.01", "player.red", position=(5, 5), side="red")
    dead_red["alive"] = False  # lone survivor exists from the start
    bus2.publish(
        _env(
            SOEventType.MATCH_STARTED,
            tick=0,
            payload={
                "seed": 1,
                "max_ticks": 2,
                "mechs": [
                    dead_red,
                    _mech_dict("mech.blue.01", "player.blue", position=(35, 35), side="blue"),
                ],
                "arena": runtime.arena.to_snapshot().model_dump(mode="json"),
            },
        )
    )
    bus2.publish(_env(SOEventType.MATCH_TICK, tick=1))
    bus2.publish(_env(SOEventType.MATCH_TICK, tick=2))

    assert fold2.state.status is SOMatchStatus.ENDED
    victories = [e for e in captured2 if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victories) == 1
    victory = ModelSOVictoryDeclaredPayload.model_validate(victories[0].payload)
    assert victory.winner_player_id == "player.blue"
    assert victory.reason is SOMatchEndReason.LAST_MECH_STANDING
    assert victory.victory_kind == "tick_cap_failsafe"
