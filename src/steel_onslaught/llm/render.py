"""Deterministic per-tick arena render for the vision-language pilot arm.

``render_observation_png`` is a pure function of ``ModelSOPilotObservation``
state -> PNG bytes: the same observation and ``arena_size`` always produce
byte-identical output (verified by a golden determinism test in
``tests/llm/test_render_determinism.py``). It renders strictly the same
information the text serializer already exposes to the pilot
(``pilot.py::_serialize_observation``) -- own position, static cover cells,
blocked directions, objective cells, and a distance-only enemy annulus --
and never enemy ground-truth position, which the pilot is never given. This
keeps the V-IMG arm's information content equal to V-TEXT's; only the
modality differs.

Determinism discipline (2026-07-24 vision-pilot experiment):
- No ``datetime.now()``/``time.time()``/randomness anywhere in this module.
- A fixed, bundled bitmap font is never used (no text is rendered at all,
  sidestepping system-font-resolution drift entirely).
- Flat colors only; no anti-aliased gradients, no ``resize``/``filter``
  operations.
- PNG encoding uses an explicit ``compress_level`` so the same Pillow
  version + same pixels always produces the same compressed byte stream.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from steel_onslaught.pilots.schemas import ModelSOPilotObservation, SOCompassDirection

_CELL_PX = 12
_BG = (235, 235, 230)
_GRID = (200, 200, 195)
_COVER = (90, 90, 90)
_SELF = (30, 90, 200)
_SELF_LOCKED = (200, 40, 40)
_ENEMY_RING = (200, 60, 30)
_BLOCKED = (170, 40, 40)

_OBJECTIVE_COLOR: dict[str, tuple[int, int, int]] = {
    "own": (40, 160, 60),
    "enemy": (190, 60, 60),
    "contested": (210, 150, 30),
    "unclaimed": (140, 140, 140),
}

_COMPASS_OFFSET: dict[SOCompassDirection, tuple[int, int]] = {
    SOCompassDirection.N: (0, -1),
    SOCompassDirection.NE: (1, -1),
    SOCompassDirection.E: (1, 0),
    SOCompassDirection.SE: (1, 1),
    SOCompassDirection.S: (0, 1),
    SOCompassDirection.SW: (-1, 1),
    SOCompassDirection.W: (-1, 0),
    SOCompassDirection.NW: (-1, -1),
}


_BLANK_FILL = (128, 128, 128)


def render_blank_png(*, arena_size: int) -> bytes:
    """Render a deterministic, content-free control image (2026-07-24 blank-image arm).

    Same canvas formula (``arena_size * _CELL_PX`` square) and identical PNG
    encoding parameters (``optimize=True, compress_level=6``) as
    ``render_observation_png``, so pixel dimensions match exactly -- but zero
    observation-dependent content: one flat mid-grey fill, no grid, no cells,
    no shapes, no enemy ring. This isolates the "an image content-part is
    present" variable from "the image depicts task-relevant information,"
    the two competing explanations left undistinguished by the V-TEXT/V-IMG
    OpenRouter rerun (docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md
    §6): if red's win rate recovers under this arm despite an attached image
    of matched pixel dimensions, the original collapse was driven by image
    *content*, not merely image *presence*/token cost.
    """
    if arena_size <= 0:
        raise ValueError("arena_size must be positive")
    dim = arena_size * _CELL_PX
    image = Image.new("RGB", (dim, dim), color=_BLANK_FILL)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=6)
    return buffer.getvalue()


def render_observation_png(observation: ModelSOPilotObservation, *, arena_size: int) -> bytes:
    """Render one deterministic PNG for the given observation.

    ``arena_size`` is a config-declared constant (the static arena the match
    is configured to play; see
    ``ModelSOLlmImageAttachmentBinding.arena_size``), never resolved
    dynamically from a live ``ModelSOArenaSpec``.
    """
    if arena_size <= 0:
        raise ValueError("arena_size must be positive")

    dim = arena_size * _CELL_PX
    image = Image.new("RGB", (dim, dim), color=_BG)
    draw = ImageDraw.Draw(image)

    for i in range(arena_size + 1):
        p = i * _CELL_PX
        draw.line([(p, 0), (p, dim)], fill=_GRID, width=1)
        draw.line([(0, p), (dim, p)], fill=_GRID, width=1)

    for cell in observation.cover_cells:
        _fill_cell(draw, cell.x, cell.y, color=_COVER)

    for objective in observation.objectives:
        _fill_cell(
            draw,
            objective.cell.x,
            objective.cell.y,
            color=_OBJECTIVE_COLOR[objective.control],
            margin=2,
        )

    self_x, self_y = observation.position.x, observation.position.y
    self_cx = self_x * _CELL_PX + _CELL_PX // 2
    self_cy = self_y * _CELL_PX + _CELL_PX // 2

    if observation.enemy_observations:
        # Newest reading only -- an annulus centered on OWN position at the
        # noisy distance estimate. Never a point: the pilot has no enemy
        # ground-truth position, so the render must not imply one either.
        latest = observation.enemy_observations[-1]
        radius_px = latest.distance_estimate * _CELL_PX
        draw.ellipse(
            [
                self_cx - radius_px,
                self_cy - radius_px,
                self_cx + radius_px,
                self_cy + radius_px,
            ],
            outline=_ENEMY_RING,
            width=1,
        )

    for direction in observation.blocked_directions:
        dx, dy = _COMPASS_OFFSET[direction]
        draw.line(
            [
                (self_cx, self_cy),
                (self_cx + dx * (_CELL_PX // 2), self_cy + dy * (_CELL_PX // 2)),
            ],
            fill=_BLOCKED,
            width=2,
        )

    self_color = _SELF_LOCKED if observation.under_sensor_lock else _SELF
    _fill_cell(draw, self_x, self_y, color=self_color, margin=1, shape="ellipse")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=6)
    return buffer.getvalue()


def _fill_cell(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    *,
    color: tuple[int, int, int],
    margin: int = 0,
    shape: str = "rectangle",
) -> None:
    x0 = x * _CELL_PX + margin
    y0 = y * _CELL_PX + margin
    x1 = (x + 1) * _CELL_PX - 1 - margin
    y1 = (y + 1) * _CELL_PX - 1 - margin
    if shape == "ellipse":
        draw.ellipse([x0, y0, x1, y1], fill=color)
    else:
        draw.rectangle([x0, y0, x1, y1], fill=color)


__all__ = ["render_blank_png", "render_observation_png"]
