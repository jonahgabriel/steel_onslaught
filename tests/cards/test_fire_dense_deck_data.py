"""Contract checks for the fire-density balance experiment deck."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_card_runtime_snapshot,
)

_DECK_DIR = Path(__file__).resolve().parents[2] / "contracts_data/decks"


def _load_deck(filename: str) -> ModelSODeck:
    raw: object = yaml.safe_load((_DECK_DIR / filename).read_text(encoding="utf-8"))
    return ModelSODeck.model_validate(raw)


@pytest.mark.unit
def test_fire_dense_v1_is_a_closed_thirty_card_experiment_deck() -> None:
    deck = _load_deck("fire_dense_v1.yaml")

    assert deck.id == "deck.fire_dense.v1"
    assert deck.hand_size == 5
    assert deck.register_count == 5
    assert deck.total_cards() == 30
    assert Counter(deck.card_multiset()) == Counter(
        {
            "card.attack.fire_primary": 8,
            "card.attack.fire_secondary": 6,
            "card.movement.advance": 4,
            "card.movement.flank_left": 1,
            "card.movement.flank_right": 1,
            "card.movement.reposition": 2,
            "card.vent.emergency_vent": 4,
            "card.special.mode_assault": 2,
            "card.special.mode_evasion": 1,
            "card.special.mode_recon": 1,
        }
    )


@pytest.mark.unit
def test_fire_dense_v1_increases_attack_density_without_removing_movement() -> None:
    standard = _load_deck("standard_v1.yaml")
    fire_dense = _load_deck("fire_dense_v1.yaml")

    def category_counts(deck: ModelSODeck) -> Counter[str]:
        return Counter(
            card_id.rsplit(".", 2)[1]
            for card_id in deck.card_multiset()
            if card_id.startswith("card.")
        )

    standard_counts = category_counts(standard)
    fire_dense_counts = category_counts(fire_dense)
    assert standard_counts["attack"] == 9
    assert fire_dense_counts["attack"] == 14
    assert standard_counts["movement"] == 13
    assert fire_dense_counts["movement"] == 8
    assert fire_dense_counts["movement"] > 0


@pytest.mark.unit
def test_qwen_overlay_selects_fire_dense_deck_and_isolated_evidence_roots() -> None:
    overlay_path = (
        Path(__file__).resolve().parents[2] / "contracts_data/overlays/fire_dense_v1_qwen.yaml"
    )
    overlay = load_application_overlay(overlay_path)

    assert overlay.contracts.card_catalog is not None
    binding = overlay.contracts.card_catalog
    assert binding.card_mode_enabled is True
    assert binding.deck_id == "deck.fire_dense.v1"
    assert binding.card_cadence == "paced"
    assert tuple(programmer.pilot_spec_id for programmer in binding.programmers) == (
        "pilot.llm.qwen35",
        "pilot.llm.qwen35_sniper",
    )
    provider = overlay.llm.providers[0]
    assert provider.kind == "openai_compatible"
    assert provider.provider_id == "qwen35"
    assert provider.secret_ref is None
    assert overlay.event_ledger.path.parts[-2:] == ("fire_dense_v1_qwen", "events.sqlite3")

    snapshot = load_card_runtime_snapshot(binding)
    assert snapshot.selected_deck_id == "deck.fire_dense.v1"
    assert snapshot.selected_deck is not None
    assert snapshot.selected_deck.total_cards() == 30
