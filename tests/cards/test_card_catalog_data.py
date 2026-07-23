"""Hermetic validation of the ten fixed, unbound card data files."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.cards.actions import action_for_card
from steel_onslaught.contracts.card import ModelSOCard, SOCardCategory
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.pilots.schemas import SOPilotAction

_CARD_DIR = Path(__file__).resolve().parents[2] / "contracts_data/cards"
_CARD_FILES = (
    "attack_fire_primary.yaml",
    "attack_fire_secondary.yaml",
    "movement_advance.yaml",
    "movement_flank_left.yaml",
    "movement_flank_right.yaml",
    "movement_reposition.yaml",
    "special_mode_assault.yaml",
    "special_mode_evasion.yaml",
    "special_mode_recon.yaml",
    "utility_chaff.yaml",
    "utility_flares.yaml",
    "utility_smoke.yaml",
    "vent_emergency.yaml",
)


def _load_card(filename: str) -> ModelSOCard:
    raw: object = yaml.safe_load((_CARD_DIR / filename).read_text(encoding="utf-8"))
    return ModelSOCard.model_validate(raw)


@pytest.mark.unit
def test_fixed_card_files_validate_without_a_production_catalog() -> None:
    cards = tuple(_load_card(filename) for filename in _CARD_FILES)
    assert tuple(card.id for card in cards) == (
        "card.attack.fire_primary",
        "card.attack.fire_secondary",
        "card.movement.advance",
        "card.movement.flank_left",
        "card.movement.flank_right",
        "card.movement.reposition",
        "card.special.mode_assault",
        "card.special.mode_evasion",
        "card.special.mode_recon",
        "card.utility.chaff",
        "card.utility.flares",
        "card.utility.smoke",
        "card.vent.emergency_vent",
    )
    assert len({card.priority for card in cards}) == len(cards)
    # Movement/weapon/special cards stay power-neutral (heat comes from the
    # weapon contract).  Utility cards author an acquire price (Phase 3 heat
    # drafting) that stays inert until Phase 3 — a valid, non-zero heat_cost.
    non_utility = tuple(card for card in cards if card.category is not SOCardCategory.UTILITY)
    utility = tuple(card for card in cards if card.category is SOCardCategory.UTILITY)
    assert all(card.heat_cost == 0 for card in non_utility)
    assert all(card.heat_cost > 0 for card in utility)


@pytest.mark.unit
def test_fixed_card_data_stays_power_neutral_and_action_mapped() -> None:
    cards = tuple(_load_card(filename) for filename in _CARD_FILES)
    expected_categories = (
        SOCardCategory.ATTACK,
        SOCardCategory.ATTACK,
        SOCardCategory.MOVEMENT,
        SOCardCategory.MOVEMENT,
        SOCardCategory.MOVEMENT,
        SOCardCategory.MOVEMENT,
        SOCardCategory.SPECIAL,
        SOCardCategory.SPECIAL,
        SOCardCategory.SPECIAL,
        SOCardCategory.UTILITY,
        SOCardCategory.UTILITY,
        SOCardCategory.UTILITY,
        SOCardCategory.VENT,
    )
    assert tuple(card.category for card in cards) == expected_categories
    assert all(action_for_card(card) is not SOPilotAction.REMAIN for card in cards)


@pytest.mark.unit
def test_fixed_file_set_is_explicit_and_deck_is_declared_separately() -> None:
    assert tuple(sorted(path.name for path in _CARD_DIR.glob("*.yaml"))) == _CARD_FILES
    deck_path = Path(__file__).resolve().parents[2] / "contracts_data/decks/standard_v1.yaml"
    deck = ModelSODeck.model_validate(yaml.safe_load(deck_path.read_text(encoding="utf-8")))
    assert deck.id == "deck.standard.v1"
    assert deck.hand_size == 5
    assert deck.register_count == 5
    counts = {str(entry.card_id): entry.count for entry in deck.cards}
    assert counts["card.movement.flank_left"] == 2
    assert counts["card.movement.flank_right"] == 2
