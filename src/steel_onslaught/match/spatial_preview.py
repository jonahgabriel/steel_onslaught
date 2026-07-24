"""Pure spatial-representation computation -- show-dont-tell arms R1/R2.

Everything here is a pure function over already-resolved values (positions,
obstacles, dealt cards). It calls the SAME resolver/LOS primitives the live
match uses (``match.move_resolution.resolve_move_destination``,
``match.geometry.line_of_sight_clear``) rather than reimplementing any of
that math, so a rendered map or consequence preview can never show a pilot
something the engine would not actually do. No fold/reducer/bus/runner
authority: this module has zero side effects and zero I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from steel_onslaught.contracts.card import ModelSOCard, SOCardCategory
from steel_onslaught.match.geometry import line_of_sight_clear
from steel_onslaught.match.move_resolution import chebyshev, resolve_move_destination
from steel_onslaught.pilots.schemas import (
    ModelSOObjectiveView,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    SOMoveDirection,
)
from steel_onslaught.pilots.spatial_view import (
    SPATIAL_GRID_LEGEND,
    ModelSOMovementPreview,
    ModelSOSpatialGridView,
    ModelSOWeaponRangeFlag,
)

Cell = tuple[int, int]

# Reachable-this-round default viewport radius (25x25 render). Sized to the
# longest weapon range in the brawler loadout this arm targets (machine_gun
# range=12 / heat_lance range=20) plus a round's movement budget, not the
# sniper's ~35-50-range weapons -- a wider radius would blow the token budget
# for a marginal gain in "what can the sniper hit me with" legibility that the
# existing ``enemy_weapon_threat`` structured list already covers.
DEFAULT_GRID_RADIUS = 12

# The card's own effect vocabulary uses "away_from_enemy"/"left"/"right";
# the movement resolver's vocabulary uses "defensive"/"flank_left"/
# "flank_right". This is the EXACT mapping ``match.card_adapter.
# CardRunnerAdapter._intent_for_translation`` already applies when compiling
# a resolved register into a MOVE_INTENT -- reused here verbatim so a preview
# can never pick a different direction than the one the card will actually
# resolve to.
_CARD_DIRECTION_TO_MOVE_DIRECTION: dict[str, SOMoveDirection] = {
    "away_from_enemy": "defensive",
    "left": "flank_left",
    "right": "flank_right",
}


def _move_direction(card_direction: str) -> SOMoveDirection:
    mapped = _CARD_DIRECTION_TO_MOVE_DIRECTION.get(card_direction, card_direction)
    if mapped not in (
        "toward_enemy",
        "defensive",
        "flank_left",
        "flank_right",
        "toward_cover",
        "hold_position",
    ):
        raise ValueError(f"unmapped card movement direction: {card_direction!r}")
    return mapped  # type: ignore[return-value]


def render_ascii_grid(
    *,
    self_pos: ModelSOPosition,
    enemy_pos: ModelSOPosition | None,
    obstacles: frozenset[Cell],
    objectives: Sequence[ModelSOObjectiveView],
    arena_size: int,
    radius: int = DEFAULT_GRID_RADIUS,
) -> ModelSOSpatialGridView:
    """Render a deterministic fixed-radius ASCII viewport centered on ``self_pos``.

    Marker precedence per cell (documented on ``SPATIAL_GRID_LEGEND``): own
    mech > enemy mech > objective > obstacle > enemy-LOS-blocked shadow >
    open. ``line_of_sight_clear`` is called once per in-bounds, non-mech,
    non-obstacle cell against the true enemy position -- the exact function
    ``own_observation.has_line_of_sight_to_enemy`` is already built from -- so
    the shadow marker can never disagree with that existing single-bit fact
    at the enemy's own cell.
    """

    if radius < 1:
        raise ValueError("grid radius must be >= 1")
    origin_x = self_pos.x - radius
    origin_y = self_pos.y - radius
    side = 2 * radius + 1
    objective_cells = {(o.cell.x, o.cell.y) for o in objectives}
    self_cell = (self_pos.x, self_pos.y)
    enemy_cell = None if enemy_pos is None else (enemy_pos.x, enemy_pos.y)

    rows: list[str] = []
    for row in range(side):
        y = origin_y + row
        chars: list[str] = []
        for col in range(side):
            x = origin_x + col
            cell = (x, y)
            if x < 0 or y < 0 or x >= arena_size or y >= arena_size:
                chars.append("~")
            elif cell == self_cell:
                chars.append("S")
            elif cell == enemy_cell:
                chars.append("E")
            elif cell in objective_cells:
                chars.append("O")
            elif cell in obstacles:
                chars.append("#")
            elif enemy_pos is not None and not line_of_sight_clear(
                ModelSOPosition(x=x, y=y), enemy_pos, obstacles
            ):
                chars.append("x")
            else:
                chars.append(".")
        rows.append("".join(chars))

    return ModelSOSpatialGridView(
        radius=radius,
        origin=ModelSOPosition(x=origin_x, y=origin_y),
        rows=tuple(rows),
    )


def compute_movement_previews(
    *,
    hand_cards: Sequence[ModelSOCard],
    from_pos: ModelSOPosition,
    budget: int,
    enemy_pos: ModelSOPosition | None,
    obstacles: frozenset[Cell],
    arena_size: int,
) -> tuple[ModelSOMovementPreview, ...]:
    """Compute one consequence preview per distinct dealt movement/rotate card.

    Both ``SOCardCategory.MOVEMENT`` and ``SOCardCategory.ROTATE`` cards
    compile to a ``MOVE_INTENT`` (``CardRunnerAdapter._intent_for_translation``)
    and resolve through ``MatchRunner._resolve_move``, so both categories get a
    preview. ``resolve_move_destination`` is the exact function that resolver
    calls -- see ``match.move_resolution`` module docstring.
    """

    previews: list[ModelSOMovementPreview] = []
    seen: set[str] = set()
    for card in hand_cards:
        if card.category not in (SOCardCategory.MOVEMENT, SOCardCategory.ROTATE):
            continue
        if card.id in seen:
            continue
        seen.add(card.id)
        card_direction = card.effect.direction
        if card_direction is None:
            raise ValueError(f"movement/rotate card {card.id!r} has no effect.direction")
        direction = _move_direction(card_direction)
        resulting_cell = resolve_move_destination(
            from_pos=from_pos,
            direction=direction,
            budget=budget,
            enemy_pos=enemy_pos,
            obstacles=obstacles,
            arena_size=arena_size,
        )
        if enemy_pos is None:
            enemy_los_after: str = "no_living_enemy"
            distance_after = None
        else:
            enemy_los_after = (
                "clear" if line_of_sight_clear(resulting_cell, enemy_pos, obstacles) else "blocked"
            )
            distance_after = chebyshev(resulting_cell, enemy_pos)
        previews.append(
            ModelSOMovementPreview(
                card_id=card.id,
                direction=direction,
                resulting_cell=resulting_cell,
                enemy_los_after=enemy_los_after,  # type: ignore[arg-type]
                distance_to_enemy_after=distance_after,
            )
        )
    return tuple(sorted(previews, key=lambda preview: preview.card_id))


def compute_weapon_range_flags(
    *,
    hand_cards: Sequence[ModelSOCard],
    weapon_ids: Sequence[str],
    weapon_views: Sequence[ModelSOPilotWeaponView],
    distance_current: int | None,
) -> tuple[ModelSOWeaponRangeFlag, ...]:
    """Compute one in-range/out-of-range flag per distinct dealt attack card.

    ``range`` is read from the pilot's own ``weapons`` view (the same
    ``ModelSOPilotWeaponView.range`` field already rendered in
    ``own_observation.weapons``); ``distance_current`` is the same Chebyshev
    distance ``validate_weapon_fire_intent`` compares against. A card naming a
    weapon slot the mech does not field is silently skipped -- it resolves to
    an inert, unfireable register the same way ``CardRunnerAdapter.
    _intent_for_translation`` already treats it (``unavailable_reason=
    "weapon_slot_absent"``), not a new failure mode.
    """

    range_by_weapon_id: Mapping[str, int] = {view.weapon_id: view.range for view in weapon_views}
    flags: list[ModelSOWeaponRangeFlag] = []
    seen: set[str] = set()
    for card in hand_cards:
        if card.category is not SOCardCategory.ATTACK:
            continue
        if card.id in seen:
            continue
        seen.add(card.id)
        slot = card.effect.weapon_slot
        if slot is None or slot >= len(weapon_ids):
            continue
        weapon_id = weapon_ids[slot]
        weapon_range = range_by_weapon_id.get(weapon_id)
        if weapon_range is None:
            continue
        in_range = distance_current is not None and distance_current <= weapon_range
        flags.append(
            ModelSOWeaponRangeFlag(
                card_id=card.id,
                weapon_id=weapon_id,
                range=weapon_range,
                distance_current=distance_current,
                in_range=in_range,
            )
        )
    return tuple(sorted(flags, key=lambda flag: flag.card_id))


__all__ = [
    "DEFAULT_GRID_RADIUS",
    "SPATIAL_GRID_LEGEND",
    "compute_movement_previews",
    "compute_weapon_range_flags",
    "render_ascii_grid",
]
