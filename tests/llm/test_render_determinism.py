"""Determinism + content-correctness tests for the deterministic arena renderer.

``render_observation_png`` is the platform non-negotiable for the V-IMG arm
of the 2026-07-24 vision-representation experiment: same state -> byte-
identical PNG, sha256 stable across runs, and no PNG metadata chunks that
could vary by wall-clock or encoder run.
"""

from __future__ import annotations

import hashlib
import io
import struct

import pytest
from PIL import Image

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.llm.render import render_blank_png, render_observation_png
from steel_onslaught.pilots.schemas import (
    ModelSOObjectiveView,
    ModelSOPilotObservation,
    ModelSOPosition,
    ModelSOSensorReading,
    ModelSOVictoryPointsView,
    SOCompassDirection,
)

_CELL_PX = 12


def _boiler() -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id="m",
        mech_id="mech.a",
        tick=3,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=10,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _observation(
    *,
    position: ModelSOPosition | None = None,
    under_sensor_lock: bool = False,
    blocked_directions: tuple[SOCompassDirection, ...] = (),
    cover_cells: tuple[ModelSOPosition, ...] = (),
    enemy_observations: list[ModelSOSensorReading] | None = None,
    objectives: tuple[ModelSOObjectiveView, ...] = (),
    victory_points: ModelSOVictoryPointsView | None = None,
) -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id="m1",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=3,
        match_elapsed_ticks=3,
        boiler=_boiler(),
        weapons=[],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=position if position is not None else ModelSOPosition(x=5, y=5),
        hp_percent=80.0,
        under_sensor_lock=under_sensor_lock,
        has_line_of_sight_to_enemy=True,
        blocked_directions=blocked_directions,
        cover_cells=cover_cells,
        enemy_observations=enemy_observations if enemy_observations is not None else [],
        objectives=objectives,
        victory_points=victory_points,
    )


def _chunk_types(png_bytes: bytes) -> list[str]:
    pos = 8  # PNG signature
    types: list[str] = []
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos : pos + 4])[0]
        ctype = png_bytes[pos + 4 : pos + 8].decode("ascii")
        types.append(ctype)
        pos += 8 + length + 4
    return types


@pytest.mark.unit
def test_same_state_renders_byte_identical_png_twice() -> None:
    obs = _observation(cover_cells=(ModelSOPosition(x=2, y=2),))
    first = render_observation_png(obs, arena_size=20)
    second = render_observation_png(obs, arena_size=20)
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


@pytest.mark.unit
def test_sha256_is_stable_across_repeated_calls() -> None:
    obs = _observation(
        blocked_directions=(SOCompassDirection.N,),
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id="mech.blue.01", tick=3, distance_estimate=6.0, confidence=0.7
            )
        ],
    )
    digests = {
        hashlib.sha256(render_observation_png(obs, arena_size=20)).hexdigest() for _ in range(5)
    }
    assert len(digests) == 1


@pytest.mark.unit
def test_different_state_renders_different_bytes() -> None:
    obs_a = _observation(position=ModelSOPosition(x=1, y=1))
    obs_b = _observation(position=ModelSOPosition(x=9, y=9))
    assert render_observation_png(obs_a, arena_size=20) != render_observation_png(
        obs_b, arena_size=20
    )


@pytest.mark.unit
def test_png_carries_no_timestamp_or_text_metadata_chunks() -> None:
    obs = _observation()
    png_bytes = render_observation_png(obs, arena_size=20)
    chunk_types = _chunk_types(png_bytes)
    assert "tIME" not in chunk_types
    assert "tEXt" not in chunk_types
    assert "zTXt" not in chunk_types
    assert "iTXt" not in chunk_types


@pytest.mark.unit
def test_output_dimensions_match_arena_size_times_cell_px() -> None:
    obs = _observation()
    png_bytes = render_observation_png(obs, arena_size=15)
    image = Image.open(io.BytesIO(png_bytes))
    assert image.size == (15 * _CELL_PX, 15 * _CELL_PX)


@pytest.mark.unit
def test_cover_cell_pixel_is_distinct_from_background() -> None:
    obs = _observation(cover_cells=(ModelSOPosition(x=7, y=7),))
    png_bytes = render_observation_png(obs, arena_size=20)
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    cx = 7 * _CELL_PX + _CELL_PX // 2
    cy = 7 * _CELL_PX + _CELL_PX // 2
    cover_pixel = image.getpixel((cx, cy))
    background_pixel = image.getpixel((_CELL_PX // 2, _CELL_PX // 2))
    assert cover_pixel != background_pixel


@pytest.mark.unit
def test_self_position_pixel_reflects_sensor_lock_color() -> None:
    obs_free = _observation(position=ModelSOPosition(x=4, y=4), under_sensor_lock=False)
    obs_locked = _observation(position=ModelSOPosition(x=4, y=4), under_sensor_lock=True)
    png_free = render_observation_png(obs_free, arena_size=20)
    png_locked = render_observation_png(obs_locked, arena_size=20)
    image_free = Image.open(io.BytesIO(png_free)).convert("RGB")
    image_locked = Image.open(io.BytesIO(png_locked)).convert("RGB")
    cx = 4 * _CELL_PX + _CELL_PX // 2
    cy = 4 * _CELL_PX + _CELL_PX // 2
    assert image_free.getpixel((cx, cy)) != image_locked.getpixel((cx, cy))


@pytest.mark.unit
def test_objective_cell_color_reflects_control_state() -> None:
    own_objective = ModelSOObjectiveView(
        objective_id="objective.a",
        cell=ModelSOPosition(x=10, y=10),
        vp_per_round=1,
        control="own",
        own_distance_chebyshev=0,
    )
    enemy_objective = ModelSOObjectiveView(
        objective_id="objective.b",
        cell=ModelSOPosition(x=11, y=11),
        vp_per_round=1,
        control="enemy",
        own_distance_chebyshev=1,
    )
    obs_own = _observation(
        objectives=(own_objective,),
        victory_points=ModelSOVictoryPointsView(own_vp=1, enemy_vp=0, vp_threshold=5),
    )
    obs_enemy = _observation(
        objectives=(enemy_objective,),
        victory_points=ModelSOVictoryPointsView(own_vp=0, enemy_vp=1, vp_threshold=5),
    )
    png_own = render_observation_png(obs_own, arena_size=20)
    png_enemy = render_observation_png(obs_enemy, arena_size=20)
    image_own = Image.open(io.BytesIO(png_own)).convert("RGB")
    image_enemy = Image.open(io.BytesIO(png_enemy)).convert("RGB")
    own_pixel = image_own.getpixel((10 * _CELL_PX + _CELL_PX // 2, 10 * _CELL_PX + _CELL_PX // 2))
    enemy_pixel = image_enemy.getpixel(
        (11 * _CELL_PX + _CELL_PX // 2, 11 * _CELL_PX + _CELL_PX // 2)
    )
    assert own_pixel != enemy_pixel


@pytest.mark.unit
def test_non_positive_arena_size_raises() -> None:
    obs = _observation()
    with pytest.raises(ValueError, match="arena_size must be positive"):
        render_observation_png(obs, arena_size=0)


# ---------------------------------------------------------------------------
# Blank-image control arm (2026-07-24) -- render_blank_png
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_blank_png_is_deterministic_across_repeated_calls() -> None:
    first = render_blank_png(arena_size=20)
    second = render_blank_png(arena_size=20)
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


@pytest.mark.unit
def test_blank_png_dimensions_match_arena_render() -> None:
    """Same canvas formula as render_observation_png -- pixel dims must match exactly."""
    obs = _observation()
    real_png = render_observation_png(obs, arena_size=15)
    blank_png = render_blank_png(arena_size=15)
    real_image = Image.open(io.BytesIO(real_png))
    blank_image = Image.open(io.BytesIO(blank_png))
    assert blank_image.size == real_image.size == (15 * _CELL_PX, 15 * _CELL_PX)


@pytest.mark.unit
def test_blank_png_is_a_single_flat_color() -> None:
    blank_png = render_blank_png(arena_size=10)
    image = Image.open(io.BytesIO(blank_png)).convert("RGB")
    colors = image.getcolors(maxcolors=10)
    assert colors is not None
    assert len(colors) == 1


@pytest.mark.unit
def test_blank_png_differs_from_any_arena_render() -> None:
    obs = _observation(cover_cells=(ModelSOPosition(x=2, y=2),))
    real_png = render_observation_png(obs, arena_size=20)
    blank_png = render_blank_png(arena_size=20)
    assert real_png != blank_png


@pytest.mark.unit
def test_blank_png_carries_no_timestamp_or_text_metadata_chunks() -> None:
    blank_png = render_blank_png(arena_size=20)
    chunk_types = _chunk_types(blank_png)
    assert "tIME" not in chunk_types
    assert "tEXt" not in chunk_types
    assert "zTXt" not in chunk_types
    assert "iTXt" not in chunk_types


@pytest.mark.unit
def test_blank_png_non_positive_arena_size_raises() -> None:
    with pytest.raises(ValueError, match="arena_size must be positive"):
        render_blank_png(arena_size=0)
