"""Closed contracts for opt-in movement/weapon deck composition.

The original card runtime intentionally has one selected deck.  This module
describes the next composition slice without changing that reducer contract:
each seat names its own movement and weapon decks, quotas for each partition,
register count, and archetype label.  A composition root may inject the
policy into an adapter; callers that omit it keep the existing single-deck
behavior.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.deck import DeckId
from steel_onslaught.contracts.player_selection import Side


class _ClosedSplitDeckModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSODeckHandQuota(_ClosedSplitDeckModel):
    """Per-hand card quotas for the independent movement/weapon piles."""

    movement: StrictInt = Field(ge=0)
    weapon: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _requires_one_card(self) -> Self:
        if self.movement + self.weapon < 1:
            raise ValueError("deck hand quota must contain at least one card")
        return self

    @property
    def hand_size(self) -> int:
        """Return the authoritative total represented by the two quotas."""

        return self.movement + self.weapon


class ModelSOSeatDeckPolicy(_ClosedSplitDeckModel):
    """One side's explicit split-deck selection and tactical quotas."""

    side: Side
    archetype: StrictStr = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    movement_deck_id: DeckId
    weapon_deck_id: DeckId
    hand_quota: ModelSODeckHandQuota
    register_count: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def _decks_are_independent(self) -> Self:
        if self.movement_deck_id == self.weapon_deck_id:
            raise ValueError("movement_deck_id and weapon_deck_id must be distinct")
        if self.register_count > self.hand_quota.hand_size:
            raise ValueError("register_count cannot exceed the split-deck hand quota total")
        return self


class ModelSOCardDeckPolicy(_ClosedSplitDeckModel):
    """Opt-in closed policy for independent per-seat movement/weapon decks."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.card_deck_policy"] = Field(...)
    seats: tuple[ModelSOSeatDeckPolicy, ...] = Field(min_length=2)

    @field_validator("seats", mode="before")
    @classmethod
    def _normalize_yaml_sequence(cls, value: object) -> object:
        """Accept YAML's list representation while retaining tuple authority."""

        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _contains_exactly_one_policy_per_side(self) -> Self:
        sides = tuple(seat.side for seat in self.seats)
        if len(sides) != len(set(sides)):
            raise ValueError("split-deck policy must declare each side at most once")
        if set(sides) != {"red", "blue"}:
            raise ValueError("split-deck policy must declare both red and blue sides")
        return self

    def for_side(self, side: Side) -> ModelSOSeatDeckPolicy:
        """Resolve one explicitly configured seat or fail closed."""

        for seat in self.seats:
            if seat.side == side:
                return seat
        raise KeyError(f"split-deck policy has no configuration for side {side!r}")


# Naming aliases keep the contract discoverable for callers that refer to the
# behavior as a split deck rather than a card deck policy.
ModelSOSplitDeckPolicy = ModelSOCardDeckPolicy
ModelSODeckQuota = ModelSODeckHandQuota


__all__ = [
    "ModelSOCardDeckPolicy",
    "ModelSODeckHandQuota",
    "ModelSODeckQuota",
    "ModelSOSeatDeckPolicy",
    "ModelSOSplitDeckPolicy",
]
