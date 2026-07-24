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
    "covered_advance",
]
type SOCardSpeed = Literal["full"]
type SOUtilityKind = Literal["smoke", "chaff", "flares"]


class _ClosedCardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SOCardCategory(StrEnum):
    """The complete category vocabulary for pure card-to-action mapping."""

    MOVEMENT = "movement"
    ROTATE = "rotate"
    ATTACK = "attack"
    VENT = "vent"
    SPECIAL = "special"
    # Phase 2 — active counterplay (smoke/chaff/flares).  The first cards whose
    # resolution changes the battlefield; dealt from the split deck's third
    # "utility" pile (``hand_quota.utility``) and partitioned separately.
    UTILITY = "utility"


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
        case SOCardCategory.UTILITY:
            return frozenset(("utility_kind", "radius", "duration_ticks"))
    assert_never(category)


class ModelSOCardEffect(_ClosedCardModel):
    """Power-neutral parameters; exactly one category-specific shape is legal."""

    direction: SOCardDirection | None = Field(default=None)
    speed: SOCardSpeed | None = Field(default=None)
    weapon_slot: StrictInt | None = Field(default=None, ge=0)
    target_mode: ModeId | None = Field(default=None)
    # Utility (Phase 2): which counterplay effect the card deploys, the area
    # radius of the effect, and how long it persists once deployed.  All three
    # are set together on a ``utility`` card and absent on every other category.
    utility_kind: SOUtilityKind | None = Field(default=None)
    radius: StrictInt | None = Field(default=None, ge=0)
    duration_ticks: StrictInt | None = Field(default=None, ge=1)


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
    # Optional human-readable tactical payoff, surfaced to a planning LLM when
    # present.  Utility is the only category whose effect fields (utility_kind/
    # radius/duration_ticks) do not themselves state the tactical outcome, so it
    # is the category that authors this.  ``None`` by default keeps every other
    # card (movement/weapon/vent) byte-identical.
    description: StrictStr | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _effect_matches_category(self) -> Self:
        present = frozenset(
            name
            for name in (
                "direction",
                "speed",
                "weapon_slot",
                "target_mode",
                "utility_kind",
                "radius",
                "duration_ticks",
            )
            if getattr(self.effect, name) is not None
        )
        required = _effect_fields_for_category(self.category)
        if present != required:
            raise ValueError(
                f"{self.category.value} card {self.id!r} requires effect fields "
                f"{sorted(required)}, got {sorted(present)}"
            )
        return self


class CardCatalogError(ValueError):
    """A card id could not be resolved from an explicit injected catalog."""


class ModelSOCardCatalog(_ClosedCardModel):
    """Immutable card definitions supplied explicitly by the composition root.

    This is a value object for pure consumers such as the register reducer. It
    deliberately has no path, loader, default, environment, or filesystem
    authority; an application overlay may resolve content roots, but a caller
    must construct and inject this validated catalog explicitly.
    """

    cards: tuple[ModelSOCard, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _card_ids_are_unique(self) -> Self:
        ids = tuple(card.id for card in self.cards)
        if len(ids) != len(set(ids)):
            raise ValueError("card catalog card ids must be unique")
        return self

    def require(self, card_id: CardId) -> ModelSOCard:
        """Resolve one card from this explicit catalog or fail closed."""
        for card in self.cards:
            if card.id == card_id:
                return card
        raise CardCatalogError(f"unknown card id {card_id!r}")


__all__ = [
    "CardCatalogError",
    "CardId",
    "ModelSOCard",
    "ModelSOCardCatalog",
    "ModelSOCardEffect",
    "SOCardCategory",
    "SOCardDirection",
    "SOCardSpeed",
    "SOUtilityKind",
]
