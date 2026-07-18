"""Pure and exhaustive card-category action mapping tests."""

from __future__ import annotations

import pytest

from steel_onslaught.cards.actions import action_for_card, action_for_category
from steel_onslaught.contracts.card import ModelSOCard, ModelSOCardEffect, SOCardCategory
from steel_onslaught.pilots.schemas import SOPilotAction

_EXPECTED = {
    SOCardCategory.MOVEMENT: SOPilotAction.MOVE,
    SOCardCategory.ROTATE: SOPilotAction.MOVE,
    SOCardCategory.ATTACK: SOPilotAction.FIRE_WEAPON,
    SOCardCategory.VENT: SOPilotAction.VENT,
    SOCardCategory.SPECIAL: SOPilotAction.SWITCH_MODE,
}


@pytest.mark.unit
def test_category_mapping_is_exhaustive_and_never_remain() -> None:
    assert set(_EXPECTED) == set(SOCardCategory)
    for category, expected in _EXPECTED.items():
        action = action_for_category(category)
        assert action is expected
        assert action is not SOPilotAction.REMAIN


@pytest.mark.unit
def test_action_for_card_is_only_a_pure_category_projection() -> None:
    card = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.attack.fire_primary",
        display_name="Fire Primary",
        category=SOCardCategory.ATTACK,
        priority=600,
        heat_cost=0,
        effect=ModelSOCardEffect(weapon_slot=0),
    )
    assert action_for_card(card) is SOPilotAction.FIRE_WEAPON
    assert action_for_card(card) is action_for_card(card)
