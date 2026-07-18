"""Closed, immutable card contracts for the unbound Phase-1 domain surface."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.contracts.mode import ModeId

_CARD_ID_PATTERN = r"^card\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$"

type CardId = Annotated[StrictStr, Field(pattern=_CARD_ID_PATTERN)]
type SOCardDirection = Literal[
    "toward_enemy",
    "away_from_enemy",
    "left",
    "right",
]
type SOCardSpeed = Literal["full"]


class _ClosedCardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SOCardCategory(StrEnum):
    """The complete category vocabulary for pure card-to-action mapping."""

    MOVEMENT = "movement"
    ROTATE = "rotate"
    ATTACK = "attack"
    VENT = "vent"
    SPECIAL = "special"


def _effect_fields_for_category(category: SOCardCategory) -> frozenset[str]:
    match category:
        case SOCardCategory.MOVEMENT:
            return frozenset(("direction", "speed"))
        case SOCardCategory.ROTATE:
            return frozenset(("direction",))
        case SOCardCategory.ATTACK:
            return frozenset(("weapon_slot",))
        case SOCardCategory.VENT:
            return frozenset()
        case SOCardCategory.SPECIAL:
            return frozenset(("target_mode",))
    assert_never(category)


class ModelSOCardEffect(_ClosedCardModel):
    """Power-neutral parameters; exactly one category-specific shape is legal."""

    direction: SOCardDirection | None = Field(default=None)
    speed: SOCardSpeed | None = Field(default=None)
    weapon_slot: StrictInt | None = Field(default=None, ge=0)
    target_mode: ModeId | None = Field(default=None)


class ModelSOCard(_ClosedCardModel):
    """One authored card definition; data only, with no catalog or runtime binding."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.card"] = Field(...)
    id: CardId
    display_name: StrictStr = Field(min_length=1)
    category: SOCardCategory = Field(...)
    priority: StrictInt = Field(ge=0)
    heat_cost: StrictInt = Field(ge=0)
    effect: ModelSOCardEffect = Field(...)

    @model_validator(mode="after")
    def _effect_matches_category(self) -> Self:
        present = frozenset(
            name
            for name in ("direction", "speed", "weapon_slot", "target_mode")
            if getattr(self.effect, name) is not None
        )
        required = _effect_fields_for_category(self.category)
        if present != required:
            raise ValueError(
                f"{self.category.value} card {self.id!r} requires effect fields "
                f"{sorted(required)}, got {sorted(present)}"
            )
        return self


__all__ = [
    "CardId",
    "ModelSOCard",
    "ModelSOCardEffect",
    "SOCardCategory",
    "SOCardDirection",
    "SOCardSpeed",
]
