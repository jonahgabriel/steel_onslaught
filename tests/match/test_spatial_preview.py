"""Pure proof for the show-dont-tell renderer/preview functions (ARM R1/R2)."""

from __future__ import annotations

import pytest

from steel_onslaught.contracts.card import ModelSOCard, ModelSOCardEffect, SOCardCategory
from steel_onslaught.match.spatial_preview import (
    compute_movement_previews,
    compute_weapon_range_flags,
    render_ascii_grid,
)
from steel_onslaught.pilots.schemas import (
    ModelSOObjectiveView,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

pytestmark = pytest.mark.unit


def _card(
    card_id: str,
    category: SOCardCategory,
    effect: ModelSOCardEffect,
) -> ModelSOCard:
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=category,
        priority=10,
        heat_cost=0,
        effect=effect,
    )


# ---------------------------------------------------------------------------
# render_ascii_grid
# ---------------------------------------------------------------------------


def test_render_ascii_grid_marks_self_enemy_and_obstacle() -> None:
    grid = render_ascii_grid(
        self_pos=ModelSOPosition(x=10, y=10),
        enemy_pos=ModelSOPosition(x=12, y=10),
        obstacles=frozenset({(11, 12)}),
        objectives=(),
        arena_size=30,
        radius=3,
    )
    assert grid.radius == 3
    assert grid.origin == ModelSOPosition(x=7, y=7)
    assert len(grid.rows) == 7  # 2*radius + 1
    assert all(len(row) == 7 for row in grid.rows)

    # self at (10,10) -> row 3 (y=10-7), col 3 (x=10-7)
    assert grid.rows[3][3] == "S"
    # enemy at (12,10) -> row 3, col 5
    assert grid.rows[3][5] == "E"
    # obstacle at (11,12) -> row 5, col 4
    assert grid.rows[5][4] == "#"


def test_render_ascii_grid_marks_objective_and_out_of_bounds() -> None:
    grid = render_ascii_grid(
        self_pos=ModelSOPosition(x=1, y=1),
        enemy_pos=None,
        obstacles=frozenset(),
        objectives=(
            ModelSOObjectiveView(
                objective_id="objective.center",
                cell=ModelSOPosition(x=2, y=1),
                vp_per_round=1,
                control="unclaimed",
                own_distance_chebyshev=1,
            ),
        ),
        arena_size=10,
        radius=2,
    )
    # origin = (-1, -1); self at (1,1) -> row 2, col 2
    assert grid.rows[2][2] == "S"
    # objective at (2,1) -> row 2, col 3
    assert grid.rows[2][3] == "O"
    # negative-coordinate cells (outside the 0..9 arena) render as "~"
    assert grid.rows[0][0] == "~"


def test_render_ascii_grid_marks_enemy_los_shadow_behind_obstacle() -> None:
    # Enemy directly east of an obstacle; cells on the FAR (self) side of that
    # obstacle from the enemy have their line of sight to the enemy blocked.
    grid = render_ascii_grid(
        self_pos=ModelSOPosition(x=5, y=5),
        enemy_pos=ModelSOPosition(x=10, y=5),
        obstacles=frozenset({(7, 5)}),
        objectives=(),
        arena_size=20,
        radius=5,
    )
    # origin = (0, 0); cell (6,5) sits between self and the obstacle, on the
    # obstacle's far side from the enemy -> its LOS to the enemy is blocked.
    assert grid.rows[5][6] == "x"
    # cell (9,5) sits adjacent to the enemy, with no obstacle between them ->
    # clear line of sight.
    assert grid.rows[5][9] == "."


def test_render_ascii_grid_is_deterministic() -> None:
    kwargs = {
        "self_pos": ModelSOPosition(x=4, y=4),
        "enemy_pos": ModelSOPosition(x=8, y=4),
        "obstacles": frozenset({(6, 4)}),
        "objectives": (),
        "arena_size": 20,
        "radius": 4,
    }
    first = render_ascii_grid(**kwargs)  # type: ignore[arg-type]
    second = render_ascii_grid(**kwargs)  # type: ignore[arg-type]
    assert first == second


def test_render_ascii_grid_rejects_nonpositive_radius() -> None:
    with pytest.raises(ValueError, match="radius"):
        render_ascii_grid(
            self_pos=ModelSOPosition(x=0, y=0),
            enemy_pos=None,
            obstacles=frozenset(),
            objectives=(),
            arena_size=10,
            radius=0,
        )


# ---------------------------------------------------------------------------
# compute_movement_previews
# ---------------------------------------------------------------------------


def test_compute_movement_previews_covers_movement_and_rotate_only() -> None:
    hand = (
        _card(
            "card.test.advance",
            SOCardCategory.MOVEMENT,
            ModelSOCardEffect(direction="toward_enemy", speed="full"),
        ),
        _card(
            "card.test.pivot",
            SOCardCategory.ROTATE,
            ModelSOCardEffect(direction="left"),
        ),
        _card("card.test.attack", SOCardCategory.ATTACK, ModelSOCardEffect(weapon_slot=0)),
        _card("card.test.vent", SOCardCategory.VENT, ModelSOCardEffect()),
    )
    previews = compute_movement_previews(
        hand_cards=hand,
        from_pos=ModelSOPosition(x=0, y=0),
        budget=3,
        enemy_pos=ModelSOPosition(x=10, y=0),
        obstacles=frozenset(),
        arena_size=20,
    )
    card_ids = {preview.card_id for preview in previews}
    assert card_ids == {"card.test.advance", "card.test.pivot"}


def test_compute_movement_previews_resulting_cell_matches_direction() -> None:
    hand = (
        _card(
            "card.test.advance",
            SOCardCategory.MOVEMENT,
            ModelSOCardEffect(direction="toward_enemy", speed="full"),
        ),
    )
    previews = compute_movement_previews(
        hand_cards=hand,
        from_pos=ModelSOPosition(x=0, y=0),
        budget=3,
        enemy_pos=ModelSOPosition(x=10, y=0),
        obstacles=frozenset(),
        arena_size=20,
    )
    assert len(previews) == 1
    preview = previews[0]
    assert preview.direction == "toward_enemy"
    assert preview.resulting_cell == ModelSOPosition(x=3, y=0)
    assert preview.enemy_los_after == "clear"
    assert preview.distance_to_enemy_after == 7


def test_compute_movement_previews_no_living_enemy() -> None:
    hand = (
        _card(
            "card.test.advance",
            SOCardCategory.MOVEMENT,
            ModelSOCardEffect(direction="toward_enemy", speed="full"),
        ),
    )
    previews = compute_movement_previews(
        hand_cards=hand,
        from_pos=ModelSOPosition(x=0, y=0),
        budget=3,
        enemy_pos=None,
        obstacles=frozenset(),
        arena_size=20,
    )
    assert len(previews) == 1
    assert previews[0].resulting_cell == ModelSOPosition(x=0, y=0)
    assert previews[0].enemy_los_after == "no_living_enemy"
    assert previews[0].distance_to_enemy_after is None


def test_compute_movement_previews_dedupes_duplicate_card_ids() -> None:
    card = _card(
        "card.test.advance",
        SOCardCategory.MOVEMENT,
        ModelSOCardEffect(direction="toward_enemy", speed="full"),
    )
    previews = compute_movement_previews(
        hand_cards=(card, card),
        from_pos=ModelSOPosition(x=0, y=0),
        budget=3,
        enemy_pos=ModelSOPosition(x=10, y=0),
        obstacles=frozenset(),
        arena_size=20,
    )
    assert len(previews) == 1


# ---------------------------------------------------------------------------
# compute_weapon_range_flags
# ---------------------------------------------------------------------------


def test_compute_weapon_range_flags_in_and_out_of_range() -> None:
    hand = (
        _card("card.test.attack_near", SOCardCategory.ATTACK, ModelSOCardEffect(weapon_slot=0)),
        _card("card.test.attack_far", SOCardCategory.ATTACK, ModelSOCardEffect(weapon_slot=1)),
        _card(
            "card.test.advance",
            SOCardCategory.MOVEMENT,
            ModelSOCardEffect(direction="toward_enemy", speed="full"),
        ),
    )
    weapon_views = [
        ModelSOPilotWeaponView(
            weapon_id="weapon.near",
            damage=10,
            range=20,
            pressure_cost=1,
            heat_generated=1,
            cooldown_remaining_ticks=0,
        ),
        ModelSOPilotWeaponView(
            weapon_id="weapon.far",
            damage=10,
            range=5,
            pressure_cost=1,
            heat_generated=1,
            cooldown_remaining_ticks=0,
        ),
    ]
    flags = compute_weapon_range_flags(
        hand_cards=hand,
        weapon_ids=("weapon.near", "weapon.far"),
        weapon_views=weapon_views,
        distance_current=12,
    )
    assert len(flags) == 2
    by_card = {flag.card_id: flag for flag in flags}
    assert by_card["card.test.attack_near"].in_range is True
    assert by_card["card.test.attack_far"].in_range is False
    assert by_card["card.test.attack_near"].range == 20
    assert by_card["card.test.attack_far"].distance_current == 12


def test_compute_weapon_range_flags_skips_unfielded_slot() -> None:
    hand = (_card("card.test.attack", SOCardCategory.ATTACK, ModelSOCardEffect(weapon_slot=5)),)
    flags = compute_weapon_range_flags(
        hand_cards=hand,
        weapon_ids=("weapon.near",),
        weapon_views=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.near",
                damage=10,
                range=20,
                pressure_cost=1,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            )
        ],
        distance_current=5,
    )
    assert flags == ()


def test_compute_weapon_range_flags_no_living_enemy_never_in_range() -> None:
    hand = (_card("card.test.attack", SOCardCategory.ATTACK, ModelSOCardEffect(weapon_slot=0)),)
    flags = compute_weapon_range_flags(
        hand_cards=hand,
        weapon_ids=("weapon.near",),
        weapon_views=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.near",
                damage=10,
                range=20,
                pressure_cost=1,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            )
        ],
        distance_current=None,
    )
    assert len(flags) == 1
    assert flags[0].in_range is False
    assert flags[0].distance_current is None
