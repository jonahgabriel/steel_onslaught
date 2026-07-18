"""Closed, immutable deck contracts for explicit deterministic dealing."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.contracts.card import CardId

_DECK_ID_PATTERN = r"^deck\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$"


class _ClosedDeckModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSODeckEntry(_ClosedDeckModel):
    """A card id and the number of physical copies declared by a deck."""

    card_id: CardId
    count: StrictInt = Field(ge=1)


class ModelSODeck(_ClosedDeckModel):
    """Explicit deck composition; no default deck, loader, or package-path authority."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.deck"] = Field(...)
    id: StrictStr = Field(pattern=_DECK_ID_PATTERN)
    display_name: StrictStr = Field(min_length=1)
    hand_size: StrictInt = Field(ge=1)
    register_count: StrictInt = Field(ge=1)
    cards: tuple[ModelSODeckEntry, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_composition(self) -> Self:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for entry in self.cards:
            if entry.card_id in seen:
                duplicates.add(entry.card_id)
            seen.add(entry.card_id)
        if duplicates:
            raise ValueError(
                f"deck {self.id!r} declares duplicate card entries: {sorted(duplicates)}"
            )
        if self.total_cards() < self.hand_size:
            raise ValueError(
                f"deck {self.id!r} has {self.total_cards()} cards but hand_size is {self.hand_size}"
            )
        if self.register_count > self.hand_size:
            raise ValueError(
                f"deck {self.id!r} register_count {self.register_count} exceeds "
                f"hand_size {self.hand_size}"
            )
        return self

    def card_multiset(self) -> tuple[CardId, ...]:
        """Expand counts in declaration order into an immutable physical-card multiset."""
        return tuple(entry.card_id for entry in self.cards for _copy_index in range(entry.count))

    def total_cards(self) -> int:
        """Return the number of physical cards declared by this deck."""
        return sum(entry.count for entry in self.cards)


__all__ = ["ModelSODeck", "ModelSODeckEntry"]
