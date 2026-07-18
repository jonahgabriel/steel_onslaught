"""Pure integer geometry for deterministic arena terrain."""

from __future__ import annotations

from steel_onslaught.pilots.schemas import ModelSOPosition, SOCompassDirection

Cell = tuple[int, int]

DIRECTION_OFFSETS: tuple[tuple[SOCompassDirection, Cell], ...] = (
    (SOCompassDirection.N, (0, -1)),
    (SOCompassDirection.NE, (1, -1)),
    (SOCompassDirection.E, (1, 0)),
    (SOCompassDirection.SE, (1, 1)),
    (SOCompassDirection.S, (0, 1)),
    (SOCompassDirection.SW, (-1, 1)),
    (SOCompassDirection.W, (-1, 0)),
    (SOCompassDirection.NW, (-1, -1)),
)


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def chebyshev_line(origin: ModelSOPosition, target: ModelSOPosition) -> tuple[Cell, ...]:
    """Return king-move cells after *origin* through and including *target*."""

    x, y = origin.x, origin.y
    cells: list[Cell] = []
    while (x, y) != (target.x, target.y):
        x += _sign(target.x - x)
        y += _sign(target.y - y)
        cells.append((x, y))
    return tuple(cells)


def bresenham_line(origin: ModelSOPosition, target: ModelSOPosition) -> tuple[Cell, ...]:
    """Return the inclusive deterministic integer line between two cells."""

    cells: list[Cell] = []
    dx = abs(target.x - origin.x)
    dy = abs(target.y - origin.y)
    sx = _sign(target.x - origin.x)
    sy = _sign(target.y - origin.y)
    error = dx - dy
    x, y = origin.x, origin.y
    while True:
        cells.append((x, y))
        if (x, y) == (target.x, target.y):
            return tuple(cells)
        doubled = 2 * error
        if doubled > -dy:
            error -= dy
            x += sx
        if doubled < dx:
            error += dx
            y += sy


def line_of_sight_clear(
    origin: ModelSOPosition,
    target: ModelSOPosition,
    obstacles: frozenset[Cell],
) -> bool:
    """Return whether no obstacle lies strictly between two endpoint cells."""

    return all(cell not in obstacles for cell in bresenham_line(origin, target)[1:-1])


def blocked_directions(
    position: ModelSOPosition,
    *,
    size: int,
    obstacles: frozenset[Cell],
) -> tuple[SOCompassDirection, ...]:
    blocked: list[SOCompassDirection] = []
    for direction, (dx, dy) in DIRECTION_OFFSETS:
        cell = (position.x + dx, position.y + dy)
        if cell[0] < 0 or cell[1] < 0 or cell[0] >= size or cell[1] >= size or cell in obstacles:
            blocked.append(direction)
    return tuple(blocked)


def cover_directions(
    position: ModelSOPosition,
    *,
    obstacles: frozenset[Cell],
) -> tuple[SOCompassDirection, ...]:
    """Return deterministic directions whose adjacent cell is cover.

    Current arena contracts treat obstacle cells as impassable terrain.  The
    move verb therefore uses this signal to choose a path *toward* cover and
    stops at the legal cell immediately before it; it never invents a move
    into an obstacle.
    """
    return tuple(
        direction
        for direction, (dx, dy) in DIRECTION_OFFSETS
        if (position.x + dx, position.y + dy) in obstacles
    )


def greedy_sidestep(
    origin: ModelSOPosition,
    target: ModelSOPosition,
    *,
    obstacles: frozenset[Cell],
    size: int,
    toward: bool,
    forbidden: frozenset[Cell],
) -> ModelSOPosition:
    """Choose one deterministic legal lateral step around blocked terrain."""

    current = max(abs(target.x - origin.x), abs(target.y - origin.y))
    ranked: list[tuple[int, int, ModelSOPosition]] = []
    for priority, (_, (dx, dy)) in enumerate(DIRECTION_OFFSETS):
        candidate = ModelSOPosition(x=origin.x + dx, y=origin.y + dy)
        cell = (candidate.x, candidate.y)
        if (
            candidate.x < 0
            or candidate.y < 0
            or candidate.x >= size
            or candidate.y >= size
            or cell in obstacles
            or cell in forbidden
        ):
            continue
        distance = max(abs(target.x - candidate.x), abs(target.y - candidate.y))
        if toward and distance > current:
            continue
        if not toward and distance < current:
            continue
        ranked.append((distance if toward else -distance, priority, candidate))
    if not ranked:
        return origin
    return min(ranked, key=lambda item: (item[0], item[1]))[2]


__all__ = [
    "DIRECTION_OFFSETS",
    "blocked_directions",
    "bresenham_line",
    "chebyshev_line",
    "cover_directions",
    "greedy_sidestep",
    "line_of_sight_clear",
]
