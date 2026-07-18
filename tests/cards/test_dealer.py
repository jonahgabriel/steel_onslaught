"""Determinism, immutability, reshuffle, and exhaustion tests for DealerCompute."""

from __future__ import annotations

from collections import Counter
from typing import cast

import pytest
from pydantic import ValidationError

from steel_onslaught.cards.dealer import (
    DealerCompute,
    ModelSODealerScope,
    ModelSODealResult,
    ModelSODeckState,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry


def _deck(*, hand_size: int = 5, deck_id: str = "deck.test.v1") -> ModelSODeck:
    ids = (
        "card.attack.fire_primary",
        "card.attack.fire_secondary",
        "card.movement.advance",
        "card.movement.reposition",
        "card.special.mode_assault",
        "card.special.mode_evasion",
        "card.special.mode_recon",
        "card.vent.emergency_vent",
    )
    return ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id=deck_id,
        display_name="Test Deck",
        hand_size=hand_size,
        register_count=min(3, hand_size),
        cards=tuple(ModelSODeckEntry(card_id=card_id, count=2) for card_id in ids),
    )


def _scope(
    *,
    match_id: str = "match.test.a",
    match_seed: int = 42,
    tick: int = 0,
    seat: str = "seat.a",
) -> ModelSODealerScope:
    return ModelSODealerScope(match_id=match_id, match_seed=match_seed, tick=tick, seat=seat)


@pytest.mark.unit
def test_spawn_deal_is_contract_sized_deterministic_and_input_only() -> None:
    deck = _deck(hand_size=5)
    scope = _scope()
    dealer = DealerCompute()
    first = dealer.spawn_deal_for_seat(deck=deck, scope=scope)
    second = dealer.spawn_deal_for_seat(deck=deck, scope=scope)
    assert first == second
    assert len(first.hand) == deck.hand_size
    assert len(first.state.draw_pile) == deck.total_cards() - deck.hand_size
    assert first.state.discard_pile == ()
    assert first.reshuffled is False
    assert first.exhausted is False


@pytest.mark.unit
def test_opening_shuffle_scope_includes_match_seed_id_tick_seat_and_deck() -> None:
    dealer = DealerCompute()
    deck = _deck()
    results = (
        dealer.open_deck_for_seat(deck=deck, scope=_scope()),
        dealer.open_deck_for_seat(deck=deck, scope=_scope(match_id="match.test.b")),
        dealer.open_deck_for_seat(deck=deck, scope=_scope(match_seed=43)),
        dealer.open_deck_for_seat(deck=deck, scope=_scope(tick=1)),
        dealer.open_deck_for_seat(deck=deck, scope=_scope(seat="seat.b")),
        dealer.open_deck_for_seat(deck=_deck(deck_id="deck.test.v2"), scope=_scope()),
    )
    assert len({result.draw_pile for result in results}) == len(results)
    assert all(Counter(result.draw_pile) == Counter(deck.card_multiset()) for result in results)


@pytest.mark.unit
def test_opening_shuffle_does_not_mutate_the_explicit_deck() -> None:
    deck = _deck()
    original = deck.model_copy(deep=True)
    state = DealerCompute().open_deck_for_seat(deck=deck, scope=_scope())
    assert deck == original
    assert Counter(state.draw_pile) == Counter(deck.card_multiset())


@pytest.mark.unit
def test_draw_declares_reshuffle_without_mutating_input() -> None:
    state = ModelSODeckState(
        draw_pile=("card.test.a",),
        discard_pile=("card.test.b", "card.test.c", "card.test.d"),
    )
    original = state.model_copy(deep=True)
    result = DealerCompute().deal_hand_for_seat(state=state, count=3, scope=_scope())
    assert state == original
    assert len(result.hand) == 3
    assert result.reshuffled is True
    assert result.exhausted is False
    assert Counter(result.hand + result.state.draw_pile) == Counter(
        ("card.test.a", "card.test.b", "card.test.c", "card.test.d")
    )


@pytest.mark.unit
def test_reshuffle_scope_includes_state_and_count() -> None:
    state = ModelSODeckState(
        draw_pile=(),
        discard_pile=("card.test.a", "card.test.b", "card.test.c", "card.test.d"),
    )
    changed_state = ModelSODeckState(
        draw_pile=(),
        discard_pile=("card.test.d", "card.test.c", "card.test.b", "card.test.a"),
    )
    dealer = DealerCompute()
    count_two = dealer.deal_hand_for_seat(state=state, count=2, scope=_scope())
    repeat = dealer.deal_hand_for_seat(state=state, count=2, scope=_scope())
    count_three = dealer.deal_hand_for_seat(state=state, count=3, scope=_scope())
    other_state = dealer.deal_hand_for_seat(state=changed_state, count=2, scope=_scope())
    assert count_two == repeat
    assert count_two.hand + count_two.state.draw_pile != (
        count_three.hand + count_three.state.draw_pile
    )
    assert count_two.hand != other_state.hand


@pytest.mark.unit
def test_draw_declares_exhaustion_instead_of_inventing_cards() -> None:
    state = ModelSODeckState(draw_pile=("card.test.a", "card.test.b"), discard_pile=())
    result = DealerCompute().deal_hand_for_seat(state=state, count=5, scope=_scope())
    assert result.hand == ("card.test.a", "card.test.b")
    assert result.state == ModelSODeckState(draw_pile=(), discard_pile=())
    assert result.reshuffled is False
    assert result.exhausted is True


@pytest.mark.unit
def test_zero_draw_is_not_exhaustion_and_bad_counts_fail() -> None:
    state = ModelSODeckState(draw_pile=(), discard_pile=())
    result = DealerCompute().deal_hand_for_seat(state=state, count=0, scope=_scope())
    assert result.hand == ()
    assert result.exhausted is False
    for invalid in (-1, True, cast(int, "1")):
        with pytest.raises(ValueError, match="non-negative integer"):
            DealerCompute().deal_hand_for_seat(state=state, count=invalid, scope=_scope())


@pytest.mark.unit
def test_scope_state_and_results_are_strict_and_frozen() -> None:
    for invalid_scope in (
        {"match_id": "", "match_seed": 1, "tick": 0, "seat": "seat.a"},
        {"match_id": "match.test", "match_seed": True, "tick": 0, "seat": "seat.a"},
        {"match_id": "match.test", "match_seed": 1, "tick": -1, "seat": "seat.a"},
        {"match_id": "match.test", "match_seed": 1, "tick": 0, "seat": ""},
    ):
        with pytest.raises(ValidationError):
            ModelSODealerScope.model_validate(invalid_scope)

    scope = _scope()
    with pytest.raises(ValidationError):
        scope.tick = 1
    with pytest.raises(ValidationError):
        ModelSODeckState(draw_pile=("not-a-card-id",), discard_pile=())
    with pytest.raises(ValidationError):
        ModelSODealResult(
            hand=("not-a-card-id",),
            state=ModelSODeckState(draw_pile=(), discard_pile=()),
            reshuffled=False,
            exhausted=False,
        )

    result = DealerCompute().deal_hand_for_seat(
        state=ModelSODeckState(draw_pile=("card.test.a",), discard_pile=()),
        count=1,
        scope=scope,
    )
    with pytest.raises(ValidationError):
        result.hand = ()
