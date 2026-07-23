"""Pure deterministic dealer primitives with explicit immutable inputs and outputs.

This module is intentionally unbound from catalogs, events, runners, and I/O.
Mutable RNG instances are derived locally from the current BLAKE2-backed
:class:`MatchRng` scope and never cross the public compute boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from steel_onslaught.contracts.card import CardId
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.contracts.split_deck import ModelSODeckHandQuota
from steel_onslaught.match.rng import MatchRng

_OPEN_SHUFFLE_KIND = "card_open_shuffle"
_RESHUFFLE_KIND = "card_reshuffle"


class _ClosedDealerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSODealerScope(_ClosedDealerModel):
    """Immutable deterministic authority shared by every public dealer operation."""

    match_id: StrictStr = Field(min_length=1)
    match_seed: StrictInt = Field(ge=0)
    tick: StrictInt = Field(ge=0)
    seat: StrictStr = Field(min_length=1)


class ModelSODeckState(_ClosedDealerModel):
    """Immutable draw/discard piles; index zero is the next card drawn."""

    draw_pile: tuple[CardId, ...] = Field(...)
    discard_pile: tuple[CardId, ...] = Field(...)


class ModelSODealResult(_ClosedDealerModel):
    """Immutable draw result with explicit reshuffle and exhaustion truth."""

    hand: tuple[CardId, ...] = Field(...)
    state: ModelSODeckState = Field(...)
    reshuffled: StrictBool = Field(...)
    exhausted: StrictBool = Field(
        ..., description="True when fewer cards existed than the requested draw count."
    )


def _empty_deck_state() -> ModelSODeckState:
    """Return the canonical empty pile used when a seat deals no utility cards."""

    return ModelSODeckState(draw_pile=(), discard_pile=())


class ModelSOSplitDeckState(_ClosedDealerModel):
    """Independent draw/discard state for one seat's card partitions.

    ``utility`` is the Phase 2 third pile.  It defaults to an empty pile so
    every pre-Phase-2 construction (``ModelSOSplitDeckState(movement=...,
    weapon=...)``) stays valid and byte-identical when no utility deck is
    configured.
    """

    movement: ModelSODeckState
    weapon: ModelSODeckState
    utility: ModelSODeckState = Field(default_factory=_empty_deck_state)


class ModelSOSplitDealResult(_ClosedDealerModel):
    """One seat's quota-sized movement, weapon, and (Phase 2) utility deals."""

    movement_hand: tuple[CardId, ...] = Field(...)
    weapon_hand: tuple[CardId, ...] = Field(...)
    utility_hand: tuple[CardId, ...] = ()
    state: ModelSOSplitDeckState
    movement_reshuffled: StrictBool = Field(...)
    weapon_reshuffled: StrictBool = Field(...)
    utility_reshuffled: StrictBool = False
    movement_exhausted: StrictBool = Field(...)
    weapon_exhausted: StrictBool = Field(...)
    utility_exhausted: StrictBool = False

    @property
    def hand(self) -> tuple[CardId, ...]:
        """Return a stable partition order for adapter consumers.

        Utility cards are appended after movement/weapon so the over-dealt hand
        conserves order against the ``movement -> weapon -> utility`` partition
        metadata carried by ``HAND_DEALT``.
        """

        return self.movement_hand + self.weapon_hand + self.utility_hand

    @property
    def exhausted(self) -> bool:
        """Whether any explicitly requested partition could not be filled."""

        return self.movement_exhausted or self.weapon_exhausted or self.utility_exhausted


def _fisher_yates(cards: tuple[CardId, ...], rng: Random) -> tuple[CardId, ...]:
    """Return a shuffled copy; the mutable RNG remains module-private and local."""
    shuffled = list(cards)
    for index in range(len(shuffled) - 1, 0, -1):
        swap_index = rng.randint(0, index)
        shuffled[index], shuffled[swap_index] = shuffled[swap_index], shuffled[index]
    return tuple(shuffled)


@dataclass(frozen=True, slots=True)
class DealerCompute:
    """Stateless compute handler whose public API accepts only immutable inputs."""

    def open_deck_for_seat(
        self,
        *,
        deck: ModelSODeck,
        scope: ModelSODealerScope,
    ) -> ModelSODeckState:
        """Open ``deck`` under the complete immutable match/seat/deck scope."""
        rng = self._operation_rng(
            scope=scope,
            kind=_OPEN_SHUFFLE_KIND,
            material=deck.model_dump_json(),
        )
        return ModelSODeckState(
            draw_pile=_fisher_yates(deck.card_multiset(), rng),
            discard_pile=(),
        )

    def deal_hand_for_seat(
        self,
        *,
        state: ModelSODeckState,
        count: int,
        scope: ModelSODealerScope,
    ) -> ModelSODealResult:
        """Draw from explicit state under the complete immutable state/count scope."""
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"draw count must be a non-negative integer, got {count!r}")

        rng = self._operation_rng(
            scope=scope,
            kind=_RESHUFFLE_KIND,
            material=f"{state.model_dump_json()}|count={count}",
        )
        draw_pile = list(state.draw_pile)
        discard_pile = list(state.discard_pile)
        hand: list[CardId] = []
        reshuffled = False

        for _draw_index in range(count):
            if not draw_pile:
                if not discard_pile:
                    break
                draw_pile = list(_fisher_yates(tuple(discard_pile), rng))
                discard_pile = []
                reshuffled = True
            hand.append(draw_pile.pop(0))

        return ModelSODealResult(
            hand=tuple(hand),
            state=ModelSODeckState(
                draw_pile=tuple(draw_pile),
                discard_pile=tuple(discard_pile),
            ),
            reshuffled=reshuffled,
            exhausted=len(hand) < count,
        )

    def spawn_deal_for_seat(
        self,
        *,
        deck: ModelSODeck,
        scope: ModelSODealerScope,
    ) -> ModelSODealResult:
        """Open and draw ``deck.hand_size`` without defaults or hidden state."""
        state = self.open_deck_for_seat(deck=deck, scope=scope)
        return self.deal_hand_for_seat(
            state=state,
            count=deck.hand_size,
            scope=scope,
        )

    def spawn_split_deal_for_seat(
        self,
        *,
        movement_deck: ModelSODeck,
        weapon_deck: ModelSODeck,
        hand_quota: ModelSODeckHandQuota,
        scope: ModelSODealerScope,
        utility_deck: ModelSODeck | None = None,
    ) -> ModelSOSplitDealResult:
        """Deal the independent piles without sharing mutable dealer state.

        Each partition is opened and drawn through the existing explicit
        single-deck primitive.  Since every operation derives its own RNG from
        the immutable scope and deck value, red/blue call order cannot alter a
        seat's deal.  ``utility_deck`` is the Phase 2 third pile; it is only
        opened when present (a positive ``hand_quota.utility`` requires it, per
        the split-deck contract).
        """

        if movement_deck.id == weapon_deck.id:
            raise ValueError("split-deck deal requires distinct movement and weapon decks")
        if utility_deck is not None and utility_deck.id in {movement_deck.id, weapon_deck.id}:
            raise ValueError("split-deck deal requires a distinct utility deck")
        if hand_quota.utility > 0 and utility_deck is None:
            raise ValueError("a positive utility quota requires an opened utility deck")
        movement_state = self.open_deck_for_seat(
            deck=movement_deck,
            scope=scope.model_copy(update={"seat": f"{scope.seat}:movement"}),
        )
        weapon_state = self.open_deck_for_seat(
            deck=weapon_deck,
            scope=scope.model_copy(update={"seat": f"{scope.seat}:weapon"}),
        )
        utility_state = (
            _empty_deck_state()
            if utility_deck is None
            else self.open_deck_for_seat(
                deck=utility_deck,
                scope=scope.model_copy(update={"seat": f"{scope.seat}:utility"}),
            )
        )
        return self.deal_split_hand_for_seat(
            state=ModelSOSplitDeckState(
                movement=movement_state, weapon=weapon_state, utility=utility_state
            ),
            hand_quota=hand_quota,
            scope=scope,
        )

    def deal_split_hand_for_seat(
        self,
        *,
        state: ModelSOSplitDeckState,
        hand_quota: ModelSODeckHandQuota,
        scope: ModelSODealerScope,
    ) -> ModelSOSplitDealResult:
        """Draw each partition from its own immutable state and quota."""

        movement_scope = scope.model_copy(update={"seat": f"{scope.seat}:movement"})
        weapon_scope = scope.model_copy(update={"seat": f"{scope.seat}:weapon"})
        utility_scope = scope.model_copy(update={"seat": f"{scope.seat}:utility"})
        movement = self.deal_hand_for_seat(
            state=state.movement,
            count=hand_quota.movement,
            scope=movement_scope,
        )
        weapon = self.deal_hand_for_seat(
            state=state.weapon,
            count=hand_quota.weapon,
            scope=weapon_scope,
        )
        utility = self.deal_hand_for_seat(
            state=state.utility,
            count=hand_quota.utility,
            scope=utility_scope,
        )
        return ModelSOSplitDealResult(
            movement_hand=movement.hand,
            weapon_hand=weapon.hand,
            utility_hand=utility.hand,
            state=ModelSOSplitDeckState(
                movement=movement.state, weapon=weapon.state, utility=utility.state
            ),
            movement_reshuffled=movement.reshuffled,
            weapon_reshuffled=weapon.reshuffled,
            utility_reshuffled=utility.reshuffled,
            movement_exhausted=movement.exhausted,
            weapon_exhausted=weapon.exhausted,
            utility_exhausted=utility.exhausted,
        )

    @staticmethod
    def _operation_rng(
        *,
        scope: ModelSODealerScope,
        kind: str,
        material: str,
    ) -> Random:
        """Derive a fresh local RNG from every immutable authority input."""
        return MatchRng(match_seed=scope.match_seed).for_event(
            tick=scope.tick,
            mech_id=scope.model_dump_json(),
            kind=f"{kind}|{material}",
        )


__all__ = [
    "DealerCompute",
    "ModelSODealResult",
    "ModelSODealerScope",
    "ModelSODeckState",
    "ModelSOSplitDealResult",
    "ModelSOSplitDeckState",
]
