"""Pure card-effect compilation into typed pilot-action parameters.

The category-to-action mapping is intentionally not the complete translation:
an attack card must retain its declared ``weapon_slot``, a special card its
``target_mode``, and movement cards their direction/speed.  This module keeps
those parameters in a frozen value object so a later runner adapter can resolve
them against live observation without making the card compiler depend on a
runner, event bus, or provider.
"""

from __future__ import annotations

from typing import Annotated, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from steel_onslaught.contracts.card import (
    CardId,
    ModelSOCard,
    SOCardCategory,
    SOCardDirection,
    SOCardSpeed,
)
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.pilots.schemas import SOPilotAction


class _ClosedCardActionModel(BaseModel):
    """Strict immutable boundary for compiled card actions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOCardMovementParameters(_ClosedCardActionModel):
    """Parameters for a movement card, including defensive direction."""

    kind: Literal["movement"] = "movement"
    direction: SOCardDirection
    speed: SOCardSpeed


class ModelSOCardRotateParameters(_ClosedCardActionModel):
    """Parameters for a rotate card that must not be reduced to a bare move."""

    kind: Literal["rotate"] = "rotate"
    direction: SOCardDirection


class ModelSOCardAttackParameters(_ClosedCardActionModel):
    """Parameters for an attack card before weapon-slot resolution."""

    kind: Literal["attack"] = "attack"
    weapon_slot: StrictInt = Field(ge=0)


class ModelSOCardVentParameters(_ClosedCardActionModel):
    """The closed, parameterless vent card effect."""

    kind: Literal["vent"] = "vent"


class ModelSOCardSpecialParameters(_ClosedCardActionModel):
    """Parameters for a special card's explicit mode transition."""

    kind: Literal["special"] = "special"
    target_mode: ModeId


type ModelSOCardActionParameters = Annotated[
    ModelSOCardMovementParameters
    | ModelSOCardRotateParameters
    | ModelSOCardAttackParameters
    | ModelSOCardVentParameters
    | ModelSOCardSpecialParameters,
    Field(discriminator="kind"),
]


class ModelSOCardActionTranslation(_ClosedCardActionModel):
    """A card's action plus every effect parameter needed by a later adapter.

    ``action`` is only the pilot action family.  The typed ``parameters``
    preserve the card-specific behavior, so callers cannot accidentally turn
    every attack into an unqualified ``FIRE_WEAPON`` or every movement into an
    unqualified ``MOVE``.
    """

    card_id: CardId
    category: SOCardCategory
    action: SOPilotAction
    parameters: ModelSOCardActionParameters

    @model_validator(mode="after")
    def _action_matches_parameters(self) -> ModelSOCardActionTranslation:
        expected: dict[str, tuple[SOCardCategory, SOPilotAction]] = {
            "movement": (SOCardCategory.MOVEMENT, SOPilotAction.MOVE),
            "rotate": (SOCardCategory.ROTATE, SOPilotAction.MOVE),
            "attack": (SOCardCategory.ATTACK, SOPilotAction.FIRE_WEAPON),
            "vent": (SOCardCategory.VENT, SOPilotAction.VENT),
            "special": (SOCardCategory.SPECIAL, SOPilotAction.SWITCH_MODE),
        }
        expected_category, expected_action = expected[self.parameters.kind]
        if self.category is not expected_category or self.action is not expected_action:
            raise ValueError(
                f"compiled card action {self.card_id!r} does not match parameter kind "
                f"{self.parameters.kind!r}"
            )
        return self

    @property
    def is_defensive(self) -> bool:
        """Whether this movement effect explicitly opens distance."""

        return isinstance(self.parameters, ModelSOCardMovementParameters) and (
            self.parameters.direction == "away_from_enemy"
        )

    @classmethod
    def from_card(cls, card: ModelSOCard) -> ModelSOCardActionTranslation:
        """Compile one validated card without observation or runtime effects."""

        effect = card.effect
        match card.category:
            case SOCardCategory.MOVEMENT:
                if effect.direction is None or effect.speed is None:
                    raise CardActionCompileError(
                        f"movement card {card.id!r} is missing direction/speed effect"
                    )
                parameters: ModelSOCardActionParameters = ModelSOCardMovementParameters(
                    direction=effect.direction,
                    speed=effect.speed,
                )
                action = SOPilotAction.MOVE
            case SOCardCategory.ROTATE:
                if effect.direction is None:
                    raise CardActionCompileError(
                        f"rotate card {card.id!r} is missing direction effect"
                    )
                parameters = ModelSOCardRotateParameters(direction=effect.direction)
                action = SOPilotAction.MOVE
            case SOCardCategory.ATTACK:
                if effect.weapon_slot is None:
                    raise CardActionCompileError(
                        f"attack card {card.id!r} is missing weapon_slot effect"
                    )
                parameters = ModelSOCardAttackParameters(weapon_slot=effect.weapon_slot)
                action = SOPilotAction.FIRE_WEAPON
            case SOCardCategory.VENT:
                parameters = ModelSOCardVentParameters()
                action = SOPilotAction.VENT
            case SOCardCategory.SPECIAL:
                if effect.target_mode is None:
                    raise CardActionCompileError(
                        f"special card {card.id!r} is missing target_mode effect"
                    )
                parameters = ModelSOCardSpecialParameters(target_mode=effect.target_mode)
                action = SOPilotAction.SWITCH_MODE
        return cls(card_id=card.id, category=card.category, action=action, parameters=parameters)


class CardActionCompileError(ValueError):
    """A validated card could not be compiled into a typed action."""


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


def compile_card_action(card: ModelSOCard) -> ModelSOCardActionTranslation:
    """Compile card effects while preserving all typed behavior parameters."""

    return ModelSOCardActionTranslation.from_card(card)


__all__ = [
    "CardActionCompileError",
    "ModelSOCardActionParameters",
    "ModelSOCardActionTranslation",
    "ModelSOCardAttackParameters",
    "ModelSOCardMovementParameters",
    "ModelSOCardRotateParameters",
    "ModelSOCardSpecialParameters",
    "ModelSOCardVentParameters",
    "action_for_card",
    "action_for_category",
    "compile_card_action",
]
