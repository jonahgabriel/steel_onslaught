"""Pure, exhaustive mapping from card categories to existing pilot actions."""

from __future__ import annotations

from typing import assert_never

from steel_onslaught.contracts.card import ModelSOCard, SOCardCategory
from steel_onslaught.pilots.schemas import SOPilotAction


def action_for_category(category: SOCardCategory) -> SOPilotAction:
    """Map every closed card category to an already-defined pilot action."""
    match category:
        case SOCardCategory.MOVEMENT | SOCardCategory.ROTATE:
            return SOPilotAction.MOVE
        case SOCardCategory.ATTACK:
            return SOPilotAction.FIRE_WEAPON
        case SOCardCategory.VENT:
            return SOPilotAction.VENT
        case SOCardCategory.SPECIAL:
            return SOPilotAction.SWITCH_MODE
    assert_never(category)


def action_for_card(card: ModelSOCard) -> SOPilotAction:
    """Return the existing action associated with ``card`` without side effects."""
    return action_for_category(card.category)


__all__ = ["action_for_card", "action_for_category"]
