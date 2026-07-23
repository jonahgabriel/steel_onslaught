"""Composition-owned adapter for the opt-in split-deck policy.

This is a construction seam only.  It does not alter the register reducer or
emit events; a later card runner can inject it alongside the existing single
deck adapter while retaining the same declarative reducer boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from steel_onslaught.cards.dealer import (
    DealerCompute,
    ModelSODealerScope,
    ModelSOSplitDealResult,
    ModelSOSplitDeckState,
)
from steel_onslaught.contracts.card import SOCardCategory
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.contracts.player_selection import Side
from steel_onslaught.contracts.split_deck import ModelSOCardDeckPolicy

_MOVEMENT_CATEGORIES = frozenset({SOCardCategory.MOVEMENT, SOCardCategory.ROTATE})
_WEAPON_CATEGORIES = frozenset({SOCardCategory.ATTACK, SOCardCategory.VENT, SOCardCategory.SPECIAL})
# Phase 2 — the third pile is category-exclusive to utility cards, so a utility
# card cannot leak into the movement/weapon piles (and vice versa).
_UTILITY_CATEGORIES = frozenset({SOCardCategory.UTILITY})


@dataclass(frozen=True, slots=True)
class SplitDeckDealerAdapter:
    """Resolve policy-selected decks and delegate pure dealing operations."""

    snapshot: ModelSOCardRuntimeSnapshot
    policy: ModelSOCardDeckPolicy
    dealer: DealerCompute = field(default_factory=DealerCompute)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, ModelSOCardRuntimeSnapshot):
            raise TypeError("split-deck adapter requires ModelSOCardRuntimeSnapshot")
        if not isinstance(self.policy, ModelSOCardDeckPolicy):
            raise TypeError("split-deck adapter requires ModelSOCardDeckPolicy")
        for seat in self.policy.seats:
            movement = self.snapshot.require_deck(seat.movement_deck_id)
            weapon = self.snapshot.require_deck(seat.weapon_deck_id)
            self._validate_partition(movement, _MOVEMENT_CATEGORIES, "movement")
            self._validate_partition(weapon, _WEAPON_CATEGORIES, "weapon")
            if seat.utility_deck_id is not None:
                utility = self.snapshot.require_deck(seat.utility_deck_id)
                self._validate_partition(utility, _UTILITY_CATEGORIES, "utility")

    def deal_for_side(
        self,
        *,
        side: Side,
        scope: ModelSODealerScope,
        state: ModelSOSplitDeckState | None = None,
    ) -> ModelSOSplitDealResult:
        """Deal a side's configured quotas from independent pile state."""

        seat = self.policy.for_side(side)
        movement_deck = self.snapshot.require_deck(seat.movement_deck_id)
        weapon_deck = self.snapshot.require_deck(seat.weapon_deck_id)
        # Phase 2 third pile: resolve the utility deck only when the seat
        # declares one.  The split-deck contract guarantees a positive
        # ``hand_quota.utility`` implies a ``utility_deck_id``, so a None deck
        # here means a zero utility quota and an empty utility pile.
        utility_deck = (
            None
            if seat.utility_deck_id is None
            else self.snapshot.require_deck(seat.utility_deck_id)
        )
        if state is None:
            return self.dealer.spawn_split_deal_for_seat(
                movement_deck=movement_deck,
                weapon_deck=weapon_deck,
                hand_quota=seat.hand_quota,
                scope=scope,
                utility_deck=utility_deck,
            )
        return self.dealer.deal_split_hand_for_seat(
            state=state,
            hand_quota=seat.hand_quota,
            scope=scope,
        )

    def _validate_partition(
        self,
        deck: ModelSODeck,
        categories: frozenset[SOCardCategory],
        name: str,
    ) -> None:
        cards = self.snapshot.card_catalog
        for entry in deck.cards:
            card = cards.require(entry.card_id)
            if card.category not in categories:
                raise ValueError(
                    f"{name} deck {deck.id!r} contains card {card.id!r} "
                    f"from category {card.category.value!r}"
                )


__all__ = ["SplitDeckDealerAdapter"]
