"""Contract and overlay validation for opt-in split decks."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.application import ModelSOCardCatalogBinding
from steel_onslaught.contracts.split_deck import (
    ModelSOCardDeckPolicy,
    ModelSODeckHandQuota,
    ModelSOSeatDeckPolicy,
)


def _policy() -> ModelSOCardDeckPolicy:
    return ModelSOCardDeckPolicy(
        schema_version="0.1.0",
        kind="steel_onslaught.card_deck_policy",
        seats=(
            ModelSOSeatDeckPolicy(
                side="red",
                archetype="berserker",
                movement_deck_id="deck.movement.berserker",
                weapon_deck_id="deck.weapon.berserker",
                hand_quota=ModelSODeckHandQuota(movement=3, weapon=2),
                register_count=5,
            ),
            ModelSOSeatDeckPolicy(
                side="blue",
                archetype="sniper",
                movement_deck_id="deck.movement.sniper",
                weapon_deck_id="deck.weapon.sniper",
                hand_quota=ModelSODeckHandQuota(movement=2, weapon=3),
                register_count=5,
            ),
        ),
    )


@pytest.mark.unit
def test_split_policy_is_closed_and_resolves_each_side() -> None:
    policy = _policy()
    assert policy.for_side("red").hand_quota.hand_size == 5
    assert policy.for_side("blue").archetype == "sniper"
    with pytest.raises(ValidationError):
        ModelSODeckHandQuota(movement=0, weapon=0)
    with pytest.raises(ValidationError):
        ModelSOCardDeckPolicy.model_validate({**policy.model_dump(), "unexpected": True})


@pytest.mark.unit
def test_split_policy_requires_distinct_sides_and_decks() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        ModelSOSeatDeckPolicy(
            side="red",
            archetype="berserker",
            movement_deck_id="deck.same",
            weapon_deck_id="deck.same",
            hand_quota=ModelSODeckHandQuota(movement=3, weapon=2),
            register_count=5,
        )
    policy = _policy()
    with pytest.raises(ValidationError, match="each side"):
        ModelSOCardDeckPolicy(
            schema_version="0.1.0",
            kind="steel_onslaught.card_deck_policy",
            seats=(policy.seats[0], policy.seats[0]),
        )


@pytest.mark.unit
def test_card_catalog_binding_keeps_single_deck_default_and_requires_opt_in() -> None:
    inert = ModelSOCardCatalogBinding(
        kind="filesystem_yaml",
        cards_dir=Path("cards"),
        decks_dir=Path("decks"),
    )
    assert inert.deck_policy is None
    with pytest.raises(ValidationError, match="selected deck_id"):
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=Path("cards"),
            decks_dir=Path("decks"),
            card_mode_enabled=True,
            deck_policy=_policy(),
            deck_id="deck.tactical.v1",
        )
    enabled = ModelSOCardCatalogBinding(
        kind="filesystem_yaml",
        cards_dir=Path("cards"),
        decks_dir=Path("decks"),
        card_mode_enabled=True,
        deck_policy=_policy(),
    )
    assert enabled.deck_policy == _policy()
