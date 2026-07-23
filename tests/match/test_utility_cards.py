"""Phase 2 — utility-card battlefield effects, folded and consulted.

Covers the design's Phase 2 seam table (2026-07-22 unified depth+learning,
§3.2 / §6) at the fold + consult boundary, driving the ACTUAL functions the
weapon-fire resolver calls (``smoke_obstacle_cells`` /
``chaff_targeting_debuff`` / ``flare_lock_broken`` / ``resolve_hit_probability``
/ ``line_of_sight_clear``) over the real ``MatchStateFold``:

  - a smoke cell blocks a previously-clear LOS for its duration;
  - the effect expires exactly on schedule (LOS clear again);
  - chaff strictly lowers the attacker's hit probability against the aura mech;
  - a flare zeros the sensor lock (drives an aimed shot toward a miss);
  - a bus-less refold of the SAME canonical stream reproduces the effects
    (replay identity for the new active-utility-effects fold);
  - the allowlisted resolution registry fails closed on an unselected id/kind.

The real-runner emit path (``MatchRunner._resolve_utility`` publishing
UTILITY_DEPLOYED, then the runner's smoke consult) lives in
``tests/match/test_utility_match_e2e.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cards.utility_handlers import (
    UtilityHandlerSelectionError,
    default_utility_registry,
)
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.fold import MatchStateFold
from steel_onslaught.match.geometry import line_of_sight_clear
from steel_onslaught.match.state import SOMatchStatus
from steel_onslaught.match.utility_effects import (
    chaff_targeting_debuff,
    flare_lock_broken,
    smoke_obstacle_cells,
)
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.weapons import resolve_hit_probability
from tests.runtime import TestRuntime as _TestRuntime
from tests.runtime import runtime_dependencies

_MATCH_ID = "match.test.utility-cards"
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")
_RED = ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red")
_BLUE = ModelSOEventSubject(mech_id="mech.blue.01", player_id="player.blue")


def _open_arena(*, spawn_a: tuple[int, int], spawn_b: tuple[int, int]) -> ModelSOArenaSpec:
    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_utility",
            "display_name": "Utility test arena",
            "size": 40,
            "spawn_a": {"x": spawn_a[0], "y": spawn_a[1]},
            "spawn_b": {"x": spawn_b[0], "y": spawn_b[1]},
            "obstacles": [],
            "rects": [],
        }
    )


def _runtime_with(arena: ModelSOArenaSpec) -> _TestRuntime:
    from steel_onslaught.match.fold import MatchContractCatalog

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
    mech_id: str, player_id: str, *, position: tuple[int, int], side: str
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


def _start(
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


def _deploy(
    bus: InProcessEventBus,
    *,
    tick: int,
    subject: ModelSOEventSubject,
    utility_kind: str,
    origin: tuple[int, int],
    radius: int,
    duration_ticks: int,
) -> None:
    bus.publish(
        _env(
            SOEventType.UTILITY_DEPLOYED,
            tick=tick,
            subject=subject,
            payload={
                "kind": "steel_onslaught.utility_deployed",
                "card_id": f"card.utility.{utility_kind}",
                "utility_kind": utility_kind,
                "origin": {"x": origin[0], "y": origin[1]},
                "radius": radius,
                "duration_ticks": duration_ticks,
            },
        )
    )


# ---------------------------------------------------------------------------
# Smoke — LOS block on a previously-clear line + expiry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_smoke_blocks_a_previously_clear_line_of_sight_then_expires() -> None:
    spawn_a, spawn_b = (5, 5), (5, 9)
    runtime = _runtime_with(_open_arena(spawn_a=spawn_a, spawn_b=spawn_b))
    bus = InProcessEventBus()
    fold, _ = _start(bus, runtime, spawn_a=spawn_a, spawn_b=spawn_b)

    a = ModelSOPosition(x=5, y=5)
    b = ModelSOPosition(x=5, y=9)
    obstacles = runtime.arena.obstacle_cells

    # BEFORE: no smoke, the line is clear (the exact runner expression).
    state = fold.state
    before = obstacles | smoke_obstacle_cells(state.active_utility_effects, state.tick)
    assert before == obstacles
    assert line_of_sight_clear(a, b, before) is True

    # Deploy smoke on an interior cell of that exact line.  The bus re-stamps
    # the event tick to the current match tick (0 here, before the first
    # MATCH_TICK), so duration 3 keeps the cloud active through ticks 0..2 and
    # expires it at tick 3 (expiry_tick = deploy_tick + duration_ticks).
    _deploy(
        bus,
        tick=0,
        subject=_RED,
        utility_kind="smoke",
        origin=(5, 7),
        radius=0,
        duration_ticks=3,
    )

    # AFTER: the same geometry is now blocked (identical expression).
    state = fold.state
    assert len(state.active_utility_effects) == 1
    blocked = obstacles | smoke_obstacle_cells(state.active_utility_effects, state.tick)
    assert (5, 7) in blocked
    assert line_of_sight_clear(a, b, blocked) is False

    # Still active across intermediate ticks, then expires exactly on schedule.
    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))
    assert len(fold.state.active_utility_effects) == 1
    bus.publish(_env(SOEventType.MATCH_TICK, tick=2))
    assert len(fold.state.active_utility_effects) == 1  # still active at tick 2
    bus.publish(_env(SOEventType.MATCH_TICK, tick=3))
    state = fold.state
    assert state.active_utility_effects == ()  # expiry_tick 3 reached
    cleared = obstacles | smoke_obstacle_cells(state.active_utility_effects, state.tick)
    assert line_of_sight_clear(a, b, cleared) is True


@pytest.mark.unit
def test_smoke_radius_covers_an_area() -> None:
    spawn_a, spawn_b = (5, 5), (5, 9)
    runtime = _runtime_with(_open_arena(spawn_a=spawn_a, spawn_b=spawn_b))
    bus = InProcessEventBus()
    fold, _ = _start(bus, runtime, spawn_a=spawn_a, spawn_b=spawn_b)
    _deploy(
        bus,
        tick=1,
        subject=_RED,
        utility_kind="smoke",
        origin=(5, 7),
        radius=1,
        duration_ticks=2,
    )
    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))
    cells = smoke_obstacle_cells(fold.state.active_utility_effects, 1)
    # A radius-1 cloud covers the 3x3 Chebyshev ring around the origin.
    assert (5, 7) in cells and (6, 8) in cells and (4, 6) in cells
    assert len(cells) == 9


# ---------------------------------------------------------------------------
# Chaff — targeting debuff on the aura mech (drives resolve_hit_probability)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chaff_strictly_lowers_hit_probability_against_the_aura_mech() -> None:
    spawn_a, spawn_b = (5, 5), (5, 9)
    runtime = _runtime_with(_open_arena(spawn_a=spawn_a, spawn_b=spawn_b))
    bus = InProcessEventBus()
    fold, _ = _start(bus, runtime, spawn_a=spawn_a, spawn_b=spawn_b)

    _deploy(
        bus,
        tick=1,
        subject=_BLUE,  # blue deploys chaff on itself
        utility_kind="chaff",
        origin=(5, 9),
        radius=0,
        duration_ticks=3,
    )
    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))

    state = fold.state
    debuff = chaff_targeting_debuff(state.active_utility_effects, "mech.blue.01", state.tick)
    assert debuff > 0.0
    # No debuff against the OTHER mech (aura is mech-scoped).
    assert chaff_targeting_debuff(state.active_utility_effects, "mech.red.01", state.tick) == 0.0

    base_accuracy, lock, evasion, penalty = 0.8, 1.0, 0.1, 0.0
    without = resolve_hit_probability(base_accuracy, lock, evasion, penalty, 0.0)
    with_chaff = resolve_hit_probability(base_accuracy, lock, evasion, penalty, debuff)
    assert with_chaff < without


# ---------------------------------------------------------------------------
# Flares — spoil a sensor lock (drives lock_confidence -> 0)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_flares_break_a_lock_driving_the_aimed_shot_to_a_miss() -> None:
    spawn_a, spawn_b = (5, 5), (5, 9)
    runtime = _runtime_with(_open_arena(spawn_a=spawn_a, spawn_b=spawn_b))
    bus = InProcessEventBus()
    fold, _ = _start(bus, runtime, spawn_a=spawn_a, spawn_b=spawn_b)

    _deploy(
        bus,
        tick=1,
        subject=_BLUE,
        utility_kind="flares",
        origin=(5, 9),
        radius=0,
        duration_ticks=2,
    )
    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))

    state = fold.state
    assert flare_lock_broken(state.active_utility_effects, "mech.blue.01", state.tick) is True
    assert flare_lock_broken(state.active_utility_effects, "mech.red.01", state.tick) is False

    # A high sensor lock produces a real hit chance; the flare zeros the lock
    # (the runner's consult) which multiplicatively drives the aimed shot to 0.
    base_accuracy, evasion, penalty = 0.9, 0.0, 0.0
    locked = resolve_hit_probability(base_accuracy, 0.9, evasion, penalty)
    assert locked > 0.0
    lock_confidence = 0.0  # what the runner sets when flare_lock_broken is True
    spoiled = resolve_hit_probability(base_accuracy, lock_confidence, evasion, penalty)
    assert spoiled == 0.0


# ---------------------------------------------------------------------------
# Replay identity — bus-less refold reproduces the effect state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_utility_effect_fold_is_replay_identical_from_the_canonical_stream() -> None:
    spawn_a, spawn_b = (5, 5), (5, 9)
    runtime = _runtime_with(_open_arena(spawn_a=spawn_a, spawn_b=spawn_b))
    bus = InProcessEventBus()
    fold, captured = _start(bus, runtime, spawn_a=spawn_a, spawn_b=spawn_b)

    _deploy(
        bus,
        tick=1,
        subject=_RED,
        utility_kind="smoke",
        origin=(5, 7),
        radius=1,
        duration_ticks=5,
    )
    for tick in range(1, 4):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))

    assert len(fold.state.active_utility_effects) == 1

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
    assert replay_fold.state.active_utility_effects == fold.state.active_utility_effects


@pytest.mark.unit
def test_effects_with_no_deployment_leave_state_byte_identical() -> None:
    """Empty active-effects => every consult is identity (no number moves)."""

    spawn_a, spawn_b = (5, 5), (5, 9)
    runtime = _runtime_with(_open_arena(spawn_a=spawn_a, spawn_b=spawn_b))
    bus = InProcessEventBus()
    fold, _ = _start(bus, runtime, spawn_a=spawn_a, spawn_b=spawn_b)
    for tick in range(1, 5):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))

    state = fold.state
    assert state.active_utility_effects == ()
    assert smoke_obstacle_cells(state.active_utility_effects, state.tick) == frozenset()
    assert chaff_targeting_debuff(state.active_utility_effects, "mech.blue.01", state.tick) == 0.0
    assert flare_lock_broken(state.active_utility_effects, "mech.blue.01", state.tick) is False


# ---------------------------------------------------------------------------
# Allowlisted resolution registry — fail-closed selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_utility_registry_selects_by_kind_and_fails_closed() -> None:
    registry = default_utility_registry()
    # All three kinds resolve to a handler.
    for kind in ("smoke", "chaff", "flares"):
        handler = registry.for_kind(kind)
        assert handler.descriptor.utility_kind == kind
        assert len(handler.descriptor.implementation_sha256) == 64

    # A sub-selection that omits a kind fails closed on that kind.
    smoke_only = registry.select(["utility.smoke.v1"])
    assert smoke_only.for_kind("smoke").descriptor.handler_id == "utility.smoke.v1"
    with pytest.raises(UtilityHandlerSelectionError):
        smoke_only.for_kind("chaff")

    # Unknown / empty / duplicate selections all fail closed.
    with pytest.raises(UtilityHandlerSelectionError):
        registry.select(["utility.nope.v1"])
    with pytest.raises(UtilityHandlerSelectionError):
        registry.select([])
    with pytest.raises(UtilityHandlerSelectionError):
        registry.select(["utility.smoke.v1", "utility.smoke.v1"])
