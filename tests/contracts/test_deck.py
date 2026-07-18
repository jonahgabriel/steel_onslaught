"""Strict, closed, frozen deck contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry


def _deck(**overrides: object) -> ModelSODeck:
    data: dict[str, object] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.deck",
        "id": "deck.test.v1",
        "display_name": "Test Deck",
        "hand_size": 5,
        "register_count": 3,
        "cards": (
            {"card_id": "card.attack.fire_primary", "count": 4},
            {"card_id": "card.movement.advance", "count": 3},
        ),
    }
    data.update(overrides)
    return ModelSODeck.model_validate(data)


@pytest.mark.unit
def test_multiset_and_total_are_deterministic_and_immutable() -> None:
    deck = _deck()
    assert deck.card_multiset() == (
        "card.attack.fire_primary",
        "card.attack.fire_primary",
        "card.attack.fire_primary",
        "card.attack.fire_primary",
        "card.movement.advance",
        "card.movement.advance",
        "card.movement.advance",
    )
    assert deck.total_cards() == 7
    with pytest.raises(ValidationError):
        deck.hand_size = 4
    with pytest.raises(ValidationError):
        deck.cards[0].count = 2


@pytest.mark.unit
def test_duplicate_short_empty_and_overregistered_decks_fail_closed() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        _deck(
            cards=(
                {"card_id": "card.attack.fire_primary", "count": 4},
                {"card_id": "card.attack.fire_primary", "count": 3},
            )
        )
    with pytest.raises(ValidationError, match="hand_size"):
        _deck(cards=({"card_id": "card.attack.fire_primary", "count": 2},))
    with pytest.raises(ValidationError):
        _deck(cards=())
    with pytest.raises(ValidationError, match="register_count"):
        _deck(register_count=6)


@pytest.mark.unit
def test_deck_tags_ids_counts_and_numbers_are_strict() -> None:
    for overrides in (
        {"schema_version": None},
        {"kind": "wrong"},
        {"id": "standard"},
        {"display_name": ""},
        {"hand_size": "5"},
        {"hand_size": True},
        {"register_count": 0},
        {"cards": ({"card_id": "not-a-card-id", "count": 5},)},
        {"cards": ({"card_id": "card.attack.fire_primary", "count": 0},)},
    ):
        with pytest.raises(ValidationError):
            _deck(**overrides)


@pytest.mark.unit
def test_required_tags_and_unknown_fields_fail_closed() -> None:
    base = _deck().model_dump()
    for field in ("schema_version", "kind", "cards"):
        data = dict(base)
        del data[field]
        with pytest.raises(ValidationError):
            ModelSODeck.model_validate(data)
    with pytest.raises(ValidationError):
        _deck(unknown=True)
    with pytest.raises(ValidationError):
        ModelSODeckEntry.model_validate({"card_id": "card.attack.fire_primary", "count": 1, "x": 1})
