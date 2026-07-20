"""Determinism and seat-order proofs for the split-deck dealer seam."""

from __future__ import annotations

import pytest

from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope
from steel_onslaught.cards.split_deck import SplitDeckDealerAdapter
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.player_selection import Side
from steel_onslaught.contracts.split_deck import (
    ModelSOCardDeckPolicy,
    ModelSODeckHandQuota,
    ModelSOSeatDeckPolicy,
)

_SIDES: tuple[Side, ...] = ("red", "blue")


def _deck(deck_id: str, *card_ids: str) -> ModelSODeck:
    hand_size = min(3, len(card_ids) * 2)
    return ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id=deck_id,
        display_name=deck_id,
        hand_size=hand_size,
        register_count=hand_size,
        cards=tuple(ModelSODeckEntry(card_id=card_id, count=2) for card_id in card_ids),
    )


def _scope(seat: str) -> ModelSODealerScope:
    return ModelSODealerScope(match_id="match.split-deck", match_seed=77, tick=0, seat=seat)


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.attack.fire_primary",
                display_name="Fire primary",
                category=SOCardCategory.ATTACK,
                priority=10,
                heat_cost=1,
                effect=ModelSOCardEffect(weapon_slot=0),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.movement.advance",
                display_name="Advance",
                category=SOCardCategory.MOVEMENT,
                priority=10,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
        )
    )
    decks = tuple(
        _deck(deck_id, card_id)
        for deck_id, card_id in (
            ("deck.movement.blue", "card.movement.advance"),
            ("deck.movement.red", "card.movement.advance"),
            ("deck.weapon.blue", "card.attack.fire_primary"),
            ("deck.weapon.red", "card.attack.fire_primary"),
        )
    )
    digest = canonical_card_runtime_sha256(cards, decks)
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=decks,
        selected_deck_id=None,
        content_sha256=digest,
    )


def _policy(*, movement_red: str = "deck.movement.red") -> ModelSOCardDeckPolicy:
    return ModelSOCardDeckPolicy(
        schema_version="0.1.0",
        kind="steel_onslaught.card_deck_policy",
        seats=tuple(
            ModelSOSeatDeckPolicy(
                side=side,
                archetype="berserker" if side == "red" else "sniper",
                movement_deck_id=movement_red if side == "red" else "deck.movement.blue",
                weapon_deck_id="deck.weapon.red" if side == "red" else "deck.weapon.blue",
                hand_quota=ModelSODeckHandQuota(movement=2, weapon=1),
                register_count=3,
            )
            for side in _SIDES
        ),
    )


@pytest.mark.unit
def test_split_deal_honors_independent_partition_quotas() -> None:
    movement = _deck(
        "deck.movement.berserker",
        "card.movement.advance",
        "card.movement.flank_left",
    )
    weapon = _deck(
        "deck.weapon.berserker",
        "card.attack.fire_primary",
        "card.attack.fire_secondary",
    )
    result = DealerCompute().spawn_split_deal_for_seat(
        movement_deck=movement,
        weapon_deck=weapon,
        hand_quota=ModelSODeckHandQuota(movement=3, weapon=2),
        scope=_scope("red"),
    )
    assert len(result.movement_hand) == 3
    assert len(result.weapon_hand) == 2
    assert all(card_id.startswith("card.movement.") for card_id in result.movement_hand)
    assert all(card_id.startswith("card.attack.") for card_id in result.weapon_hand)
    assert len(result.state.movement.draw_pile) == 1
    assert len(result.state.weapon.draw_pile) == 2


@pytest.mark.unit
def test_split_deal_is_independent_of_seat_call_order() -> None:
    movement = _deck(
        "deck.movement.shared",
        "card.movement.advance",
        "card.movement.flank_left",
    )
    weapon = _deck(
        "deck.weapon.shared",
        "card.attack.fire_primary",
        "card.attack.fire_secondary",
    )
    dealer = DealerCompute()
    quota = ModelSODeckHandQuota(movement=2, weapon=3)
    red_first = dealer.spawn_split_deal_for_seat(
        movement_deck=movement,
        weapon_deck=weapon,
        hand_quota=quota,
        scope=_scope("red"),
    )
    blue_after_red = dealer.spawn_split_deal_for_seat(
        movement_deck=movement,
        weapon_deck=weapon,
        hand_quota=quota,
        scope=_scope("blue"),
    )
    blue_first = dealer.spawn_split_deal_for_seat(
        movement_deck=movement,
        weapon_deck=weapon,
        hand_quota=quota,
        scope=_scope("blue"),
    )
    red_after_blue = dealer.spawn_split_deal_for_seat(
        movement_deck=movement,
        weapon_deck=weapon,
        hand_quota=quota,
        scope=_scope("red"),
    )
    assert red_first == red_after_blue
    assert blue_after_red == blue_first


@pytest.mark.unit
def test_split_deal_requires_distinct_deck_values() -> None:
    deck = _deck("deck.movement.only", "card.movement.advance", "card.movement.flank_left")
    with pytest.raises(ValueError, match="distinct"):
        DealerCompute().spawn_split_deal_for_seat(
            movement_deck=deck,
            weapon_deck=deck,
            hand_quota=ModelSODeckHandQuota(movement=1, weapon=1),
            scope=_scope("red"),
        )


@pytest.mark.unit
def test_split_adapter_injects_policy_and_rejects_wrong_partition() -> None:
    snapshot = _snapshot()
    adapter = SplitDeckDealerAdapter(snapshot=snapshot, policy=_policy())
    result = adapter.deal_for_side(side="red", scope=_scope("red"))
    assert len(result.movement_hand) == 2
    assert len(result.weapon_hand) == 1

    with pytest.raises(ValueError, match="movement deck"):
        SplitDeckDealerAdapter(
            snapshot=snapshot,
            policy=_policy(movement_red="deck.weapon.blue"),
        )
