"""Tests for the spawn + position + movement reducer — Task 19.

Invariants checked:
- MECH_SPAWNED sets position and facing on the mech runtime state.
- MOVEMENT_RESOLVED with 4 cells, base_speed 2, 2 ticks succeeds.
- MOVEMENT_RESOLVED with 5 cells (Chebyshev), base_speed 2, 2 ticks
  raises ReducerError("speed_exceeded").
- Movement consumes pressure (1 per cell of Chebyshev distance per move).
- Evasion mode adds +1; recon and assault preserve chassis base speed.
- Moving with pressure below the move cost raises ReducerError("insufficient_pressure").
- The reducer ignores events for a different match_id (raises match_id_mismatch).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.contracts.arena import ModelSOCurrentLiveArenaSnapshot
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.movement import ReducerMovement, chebyshev, mode_effective_speed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MATCH_ID = "match.test.001"
MECH_ID = "mech.red.01"
PLAYER_ID = "player.1"


def _arena(
    *obstacles: ModelSOPosition,
) -> ModelSOCurrentLiveArenaSnapshot:
    return ModelSOCurrentLiveArenaSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.arena_snapshot",
        arena_id="movement_test",
        size=40,
        spawn_a=ModelSOPosition(x=0, y=0),
        spawn_b=ModelSOPosition(x=39, y=39),
        obstacles=obstacles,
        sudden_death_start_tick=None,
        sudden_death_damage_base=8,
    )


def _boiler(
    pressure: int = 60, match_id: str = MATCH_ID, mech_id: str = MECH_ID
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=match_id,
        mech_id=mech_id,
        tick=0,
        pressure_current=pressure,
        pressure_maximum=100,
        regeneration_per_tick=4,
        heat_current=0,
        heat_redline_threshold=80,
        heat_rupture_threshold=95,
        heat_vent_rate=2,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _mech(
    mech_id: str = MECH_ID,
    position: ModelSOPosition | None = None,
    base_speed: int = 2,
    pressure: int = 60,
    current_mode: ModeId = ModeId.RECON,
) -> ModelSOMechRuntimeState:
    pos = position or ModelSOPosition(x=0, y=0)
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=PLAYER_ID,
        loadout_id="loadout.test.01",
        pilot_id="pilot.test.01",
        chassis_id="chassis.light.scout_mk1",
        chassis_class="light",
        base_speed=base_speed,
        position=pos,
        facing=90,
        speed=base_speed,
        hp=100,
        hp_max=100,
        armor_value=5,
        armor_max=5,
        current_mode=current_mode,
        boiler=_boiler(pressure=pressure, mech_id=mech_id),
    )


def _match_state(mech: ModelSOMechRuntimeState | None = None) -> ModelSOMatchState:
    m = mech or _mech()
    return ModelSOMatchState(
        match_id=MATCH_ID,
        tick=1,
        status=SOMatchStatus.RUNNING,
        seed=42,
        max_ticks=200,
        mech_states={m.mech_id: m},
    )


def _envelope(
    event_type: SOEventType,
    payload: dict,  # type: ignore[type-arg]
    match_id: str = MATCH_ID,
    mech_id: str = MECH_ID,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEFGX",
        match_id=match_id,
        tick=1,
        sequence_in_tick=0,
        event_type=event_type,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech_id, player_id=PLAYER_ID),
        payload=payload,
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id=match_id,
            emitted_at=datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mech_spawned_sets_position_and_facing() -> None:
    """MECH_SPAWNED positions the mech at the declared spawn point."""
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.MECH_SPAWNED,
        {"position": {"x": 5, "y": 3}, "facing": 180},
    )
    new_state = reducer.apply(event)
    mech = new_state.mech_states[MECH_ID]
    assert mech.position == ModelSOPosition(x=5, y=3)
    assert mech.facing == 180


@pytest.mark.unit
def test_movement_4_cells_speed_2_two_ticks_succeeds() -> None:
    """Moving 4 cells (Chebyshev) at base_speed 2 over 2 ticks is valid.

    Effective cells per tick = base_speed * ticks_consumed = 2 * 2 = 4.
    """
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    # Chebyshev distance from (0,0) to (4,3) = max(4,3) = 4
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 4, "y": 3},
            "ticks_consumed": 2,
            "pressure_consumed": 4,
        },
    )
    new_state = reducer.apply(event)
    mech = new_state.mech_states[MECH_ID]
    assert mech.position == ModelSOPosition(x=4, y=3)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("destination", "obstacles", "error"),
    [
        (ModelSOPosition(x=2, y=0), (ModelSOPosition(x=1, y=0),), "obstacle_blocked"),
        (ModelSOPosition(x=-1, y=0), (), "arena_bounds"),
        (ModelSOPosition(x=1, y=0), (ModelSOPosition(x=1, y=0),), "obstacle_blocked"),
    ],
    ids=["cross-wall-path", "out-of-bounds-destination", "obstacle-endpoint"],
)
def test_movement_rejects_forged_arena_paths(
    destination: ModelSOPosition,
    obstacles: tuple[ModelSOPosition, ...],
    error: str,
) -> None:
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena(*obstacles))
    distance = chebyshev(ModelSOPosition(x=0, y=0), destination)
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": destination.x, "y": destination.y},
            "ticks_consumed": 1,
            "pressure_consumed": distance,
        },
    )

    with pytest.raises(ReducerError, match=error):
        reducer.apply(event)

    assert reducer.state == match_state


@pytest.mark.unit
def test_movement_5_cells_speed_2_raises_speed_exceeded() -> None:
    """Moving 5 cells at base_speed 2 in 2 ticks raises ReducerError("speed_exceeded")."""
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    # Chebyshev distance from (0,0) to (5,0) = 5; 2 ticks * speed 2 = 4 max
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 5, "y": 0},
            "ticks_consumed": 2,
            "pressure_consumed": 5,
        },
    )
    with pytest.raises(ReducerError, match="speed_exceeded"):
        reducer.apply(event)


@pytest.mark.unit
def test_movement_consumes_pressure() -> None:
    """MOVEMENT_RESOLVED subtracts pressure_consumed from the mech's boiler."""
    mech = _mech(pressure=60)
    match_state = _match_state(mech)
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    # Moving 3 cells costs 3 pressure
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 3, "y": 0},
            "ticks_consumed": 2,
            "pressure_consumed": 3,
        },
    )
    new_state = reducer.apply(event)
    mech_after = new_state.mech_states[MECH_ID]
    assert mech_after.boiler.pressure_current == 57


@pytest.mark.unit
def test_pressure_consumed_matches_chebyshev_distance() -> None:
    """pressure_consumed must equal the Chebyshev distance; mismatch raises ReducerError."""
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    # Distance is 3, but payload claims 99 pressure consumed
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 3, "y": 0},
            "ticks_consumed": 2,
            "pressure_consumed": 99,
        },
    )
    with pytest.raises(ReducerError, match="pressure_cost_mismatch"):
        reducer.apply(event)


@pytest.mark.unit
def test_movement_insufficient_pressure_raises() -> None:
    """Moving when pressure < distance cost raises ReducerError("insufficient_pressure")."""
    mech = _mech(pressure=2)  # only 2 pressure, needs 5
    match_state = _match_state(mech)
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 5, "y": 0},
            "ticks_consumed": 5,
            "pressure_consumed": 5,
        },
    )
    with pytest.raises(ReducerError, match="insufficient_pressure"):
        reducer.apply(event)


@pytest.mark.unit
def test_evasion_mode_adds_one_to_effective_speed() -> None:
    """In evasion mode, effective speed is base_speed + 1."""
    mech = _mech(base_speed=2, current_mode=ModeId.EVASION, pressure=60)
    match_state = _match_state(mech)
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    # evasion gives effective_speed = 3; 1 tick * 3 = 3 cells max
    # 3 cells in 1 tick should succeed
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 3, "y": 0},
            "ticks_consumed": 1,
            "pressure_consumed": 3,
        },
    )
    new_state = reducer.apply(event)
    mech_after = new_state.mech_states[MECH_ID]
    assert mech_after.position == ModelSOPosition(x=3, y=0)


@pytest.mark.unit
def test_evasion_mode_3_cells_1_tick_at_base_2_would_fail_without_mode() -> None:
    """At base_speed 2 without evasion, 3 cells in 1 tick raises speed_exceeded."""
    mech = _mech(base_speed=2, current_mode=ModeId.RECON, pressure=60)
    match_state = _match_state(mech)
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 3, "y": 0},
            "ticks_consumed": 1,
            "pressure_consumed": 3,
        },
    )
    with pytest.raises(ReducerError, match="speed_exceeded"):
        reducer.apply(event)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mode", "expected_speed"),
    [
        (ModeId.RECON, 2),
        (ModeId.ASSAULT, 2),
        (ModeId.EVASION, 3),
    ],
)
def test_mode_effective_speed_mapping_is_exhaustive(mode: ModeId, expected_speed: int) -> None:
    assert mode_effective_speed(2, mode) == expected_speed


@pytest.mark.unit
def test_reducer_rejects_wrong_match_id() -> None:
    """Events for a different match_id are rejected with match_id_mismatch."""
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 0, "y": 0},
            "to": {"x": 1, "y": 0},
            "ticks_consumed": 1,
            "pressure_consumed": 1,
        },
        match_id="match.other.999",
    )
    with pytest.raises(ReducerError, match="match_id_mismatch"):
        reducer.apply(event)


@pytest.mark.unit
def test_reducer_ignores_non_movement_events() -> None:
    """Non-movement events are passed through without state change."""
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.BOILER_UPDATED,
        {"pressure": 50, "heat": 20},
    )
    new_state = reducer.apply(event)
    # State must be identical (same object or equal)
    assert new_state == match_state


@pytest.mark.unit
def test_mech_spawned_rejects_invalid_facing() -> None:
    """MECH_SPAWNED with facing outside [0, 360) raises ReducerError."""
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.MECH_SPAWNED,
        {"position": {"x": 0, "y": 0}, "facing": 400},
    )
    with pytest.raises(ReducerError, match="invalid_facing"):
        reducer.apply(event)


@pytest.mark.unit
def test_movement_from_position_must_match_current_position() -> None:
    """MOVEMENT_RESOLVED 'from' must match the mech's current position."""
    # mech is at (0,0), but payload says from=(9,9)
    match_state = _match_state()
    reducer = ReducerMovement(MATCH_ID, match_state, arena=_arena())
    event = _envelope(
        SOEventType.MOVEMENT_RESOLVED,
        {
            "from": {"x": 9, "y": 9},
            "to": {"x": 10, "y": 9},
            "ticks_consumed": 1,
            "pressure_consumed": 1,
        },
    )
    with pytest.raises(ReducerError, match="position_mismatch"):
        reducer.apply(event)
