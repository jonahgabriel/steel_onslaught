"""Pure movement-destination resolution shared by the live resolver and prompt previews.

Extracted verbatim from ``MatchRunner._resolve_move``/``_walk_to`` (2026-07-24
show-dont-tell spatial representation arms, R1/R2). Before this extraction the
movement math lived only as a private method on ``MatchRunner``; a
prompt-facing "what happens if I play this card" consequence preview had no
way to call it without either reimplementing the math (a drift risk this
module exists to close) or reaching into runner-private state.

``resolve_move_destination`` is now the SINGLE place this math is expressed.
``MatchRunner._resolve_move`` calls it for live resolution; the card-adapter
spatial-preview computation (``match.spatial_preview``) calls it for the
per-dealt-card consequence preview. A unit test asserts the two call sites can
never diverge by construction (same function, same inputs -> same output).
"""

from __future__ import annotations

from steel_onslaught.match.geometry import chebyshev_line, greedy_sidestep, line_of_sight_clear
from steel_onslaught.pilots.schemas import ModelSOPosition, SOMoveDirection

Cell = tuple[int, int]


def clamp_to_magnitude(value: int, magnitude: int) -> int:
    """Clamp *value* into ``[-magnitude, magnitude]`` (identical to the runner's ``_clamp``)."""

    return max(-magnitude, min(magnitude, value))


def sign(value: int) -> int:
    """Return -1/0/1 for negative/zero/positive *value*."""

    return (value > 0) - (value < 0)


def chebyshev(a: ModelSOPosition, b: ModelSOPosition) -> int:
    """Chebyshev (king-move) distance between two grid positions."""

    return max(abs(b.x - a.x), abs(b.y - a.y))


def walk_to(
    from_pos: ModelSOPosition,
    intended: ModelSOPosition,
    *,
    obstacles: frozenset[Cell],
) -> ModelSOPosition:
    """Walk the Chebyshev line from *from_pos* toward *intended*, stopping at terrain."""

    last = from_pos
    for x, y in chebyshev_line(from_pos, intended):
        if (x, y) in obstacles:
            break
        last = ModelSOPosition(x=x, y=y)
    return last


def _covered_advance_step(
    from_pos: ModelSOPosition,
    enemy_pos: ModelSOPosition,
    budget: int,
    *,
    obstacles: frozenset[Cell],
    arena_size: int,
) -> tuple[int, int]:
    """Pure dx/dy for ``covered_advance``: close distance via an LOS shadow.

    Extracted verbatim from ``MatchRunner._covered_advance_step`` (PR #165).
    Enumerates every reachable cell within the Chebyshev ``budget`` disk
    (reachable = an unobstructed straight king-move path from ``from_pos``,
    matching how ``walk_to`` actually resolves movement), keeps only cells
    that (a) strictly reduce distance to the enemy and (b) the enemy has no
    line of sight to (terrain obstacles only -- smoke is a separate
    counterplay card and deliberately not folded in here, so this card's
    value never depends on a second card being played). Among survivors,
    picks the fixed lexicographic minimum ``(distance_to_enemy, x, y)`` --
    deterministic, no iteration-order dependence on set/dict ordering. If no
    cell qualifies, degrades to a plain ``toward_enemy`` advance (identical
    math to that branch in ``resolve_move_destination``).
    """

    distance_now = chebyshev(from_pos, enemy_pos)
    best: ModelSOPosition | None = None
    best_key: tuple[int, int, int] | None = None
    min_x = max(0, from_pos.x - budget)
    max_x = min(arena_size - 1, from_pos.x + budget)
    min_y = max(0, from_pos.y - budget)
    max_y = min(arena_size - 1, from_pos.y + budget)
    for cx in range(min_x, max_x + 1):
        for cy in range(min_y, max_y + 1):
            if max(abs(cx - from_pos.x), abs(cy - from_pos.y)) > budget:
                continue
            if (cx, cy) == (enemy_pos.x, enemy_pos.y):
                continue  # never resolve a move into the enemy's cell
            candidate = ModelSOPosition(x=cx, y=cy)
            candidate_distance = chebyshev(candidate, enemy_pos)
            if candidate_distance >= distance_now:
                continue  # must be a strict advance, not a lateral/backward move
            if line_of_sight_clear(enemy_pos, candidate, obstacles):
                continue  # enemy can see this cell -- not covered
            if walk_to(from_pos, candidate, obstacles=obstacles) != candidate:
                continue  # not reachable: terrain blocks the straight path there
            key = (candidate_distance, cx, cy)
            if best_key is None or key < best_key:
                best_key, best = key, candidate
    if best is not None:
        return best.x - from_pos.x, best.y - from_pos.y
    # Degrade: no LOS-shadowed cell reduces distance -- plain toward_enemy.
    step = min(budget, max(0, distance_now - 1))
    return (
        clamp_to_magnitude(enemy_pos.x - from_pos.x, step),
        clamp_to_magnitude(enemy_pos.y - from_pos.y, step),
    )


def resolve_move_destination(
    *,
    from_pos: ModelSOPosition,
    direction: SOMoveDirection,
    budget: int,
    enemy_pos: ModelSOPosition | None,
    obstacles: frozenset[Cell],
    arena_size: int,
) -> ModelSOPosition:
    """Return the resulting cell for one movement direction and pressure budget.

    Mirrors ``MatchRunner._resolve_move`` exactly: obstacle-aware walk plus the
    greedy-sidestep fallback when the direct walk is fully blocked. A
    ``hold_position`` direction, a non-positive budget, or no living enemy is
    a deterministic no-op, matching the runner's own early returns -- the
    runner requires a living enemy before resolving ANY direction, including
    ``toward_cover``, even though that branch does not read the enemy's
    position.
    """

    if direction == "hold_position" or budget <= 0 or enemy_pos is None:
        return from_pos

    if direction == "toward_enemy":
        assert enemy_pos is not None
        distance = chebyshev(from_pos, enemy_pos)
        step = min(budget, max(0, distance - 1))  # never enter the enemy's cell
        dx = clamp_to_magnitude(enemy_pos.x - from_pos.x, step)
        dy = clamp_to_magnitude(enemy_pos.y - from_pos.y, step)
    elif direction == "defensive":  # open distance from the enemy
        assert enemy_pos is not None
        step = budget
        dx = clamp_to_magnitude(from_pos.x - enemy_pos.x, step)
        dy = clamp_to_magnitude(from_pos.y - enemy_pos.y, step)
    elif direction in ("flank_left", "flank_right"):
        assert enemy_pos is not None
        # Rotate the sign-clamped mech->enemy axis by 90 degrees, exactly as
        # the runner does, so a flank preview can never collapse into the
        # toward/away beeline the runner itself refuses to produce.
        axis_x = sign(enemy_pos.x - from_pos.x)
        axis_y = sign(enemy_pos.y - from_pos.y)
        if direction == "flank_left":
            perp_x, perp_y = axis_y, -axis_x
        else:
            perp_x, perp_y = -axis_y, axis_x
        dx = perp_x * budget
        dy = perp_y * budget
    elif direction == "covered_advance":
        assert enemy_pos is not None
        dx, dy = _covered_advance_step(
            from_pos, enemy_pos, budget, obstacles=obstacles, arena_size=arena_size
        )
    else:  # toward_cover
        cover_targets = sorted(
            obstacles,
            key=lambda cell: (
                max(abs(cell[0] - from_pos.x), abs(cell[1] - from_pos.y)),
                cell[0],
                cell[1],
            ),
        )
        if not cover_targets:
            return from_pos
        cover = ModelSOPosition(x=cover_targets[0][0], y=cover_targets[0][1])
        distance = chebyshev(from_pos, cover)
        step = min(budget, max(0, distance - 1))
        dx = clamp_to_magnitude(cover.x - from_pos.x, step)
        dy = clamp_to_magnitude(cover.y - from_pos.y, step)

    intended = ModelSOPosition(
        x=min(max(from_pos.x + dx, 0), arena_size - 1),
        y=min(max(from_pos.y + dy, 0), arena_size - 1),
    )
    to_pos = walk_to(from_pos, intended, obstacles=obstacles)
    moved = chebyshev(from_pos, to_pos)
    if moved == 0 and obstacles and enemy_pos is not None:
        to_pos = greedy_sidestep(
            from_pos,
            enemy_pos,
            obstacles=obstacles,
            size=arena_size,
            toward=direction == "toward_enemy",
            forbidden=frozenset({(enemy_pos.x, enemy_pos.y)}),
        )
    return to_pos


__all__ = [
    "chebyshev",
    "clamp_to_magnitude",
    "resolve_move_destination",
    "sign",
    "walk_to",
]
