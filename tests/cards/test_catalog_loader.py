"""Composition-root card catalog loading and snapshot invariants."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.application import ModelSOCardCatalogBinding
from steel_onslaught.match.composition import load_card_catalog

_CARD = {
    "schema_version": "0.1.0",
    "kind": "steel_onslaught.card",
    "id": "card.test.advance",
    "display_name": "Advance",
    "category": "movement",
    "priority": 100,
    "heat_cost": 0,
    "effect": {"direction": "toward_enemy", "speed": "full"},
}


def _binding(cards_dir: Path, decks_dir: Path | None = None) -> ModelSOCardCatalogBinding:
    return ModelSOCardCatalogBinding(
        kind="filesystem_yaml",
        cards_dir=cards_dir,
        decks_dir=decks_dir or cards_dir.parent / "missing-decks",
    )


@pytest.mark.unit
def test_loader_returns_sorted_immutable_snapshot_and_ignores_inert_deck_root(
    tmp_path: Path,
) -> None:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    (cards_dir / "z.yaml").write_text(yaml.safe_dump(_CARD), encoding="utf-8")
    second = dict(_CARD, id="card.test.vent", category="vent", effect={})
    (cards_dir / "a.yaml").write_text(yaml.safe_dump(second), encoding="utf-8")

    catalog = load_card_catalog(_binding(cards_dir))

    assert tuple(card.id for card in catalog.cards) == ("card.test.advance", "card.test.vent")
    assert isinstance(catalog.cards, tuple)
    with pytest.raises(ValidationError):
        catalog.cards += (catalog.cards[0],)

    # A source-file edit cannot mutate the already validated value object.
    (cards_dir / "z.yaml").write_text(yaml.safe_dump(dict(_CARD, priority=999)), encoding="utf-8")
    assert catalog.require("card.test.advance").priority == 100


@pytest.mark.unit
def test_loader_fails_closed_for_missing_empty_duplicate_and_unknown_card_data(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError, match="card catalog directory"):
        load_card_catalog(_binding(missing))

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no YAML specs"):
        load_card_catalog(_binding(empty))

    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "a.yaml").write_text(yaml.safe_dump(_CARD), encoding="utf-8")
    (duplicate / "b.yaml").write_text(yaml.safe_dump(_CARD), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate card id"):
        load_card_catalog(_binding(duplicate))

    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / "a.yaml").write_text(
        yaml.safe_dump(dict(_CARD, deck_ref="deck.test")), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="deck_ref"):
        load_card_catalog(_binding(unknown))


@pytest.mark.unit
def test_loader_rejects_relative_catalog_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="must be absolute"):
        load_card_catalog(_binding(Path("cards")))
