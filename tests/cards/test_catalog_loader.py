"""Composition-root card catalog loading and snapshot invariants."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.application import ModelSOCardCatalogBinding
from steel_onslaught.contracts.card_runtime import canonical_card_runtime_sha256
from steel_onslaught.match.composition import (
    load_card_catalog,
    load_card_runtime_snapshot,
    load_deck_catalog,
)

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


def _write_runtime_content(root: Path) -> ModelSOCardCatalogBinding:
    cards_dir = root / "cards"
    decks_dir = root / "decks"
    cards_dir.mkdir()
    decks_dir.mkdir()
    (cards_dir / "advance.yaml").write_text(yaml.safe_dump(_CARD), encoding="utf-8")
    vent = dict(_CARD, id="card.test.vent", display_name="Vent", category="vent", effect={})
    (cards_dir / "vent.yaml").write_text(yaml.safe_dump(vent), encoding="utf-8")
    deck = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.deck",
        "id": "deck.test.standard",
        "display_name": "Test standard",
        "hand_size": 2,
        "register_count": 2,
        "cards": [
            {"card_id": "card.test.advance", "count": 1},
            {"card_id": "card.test.vent", "count": 1},
        ],
    }
    (decks_dir / "standard.yaml").write_text(yaml.safe_dump(deck), encoding="utf-8")
    return ModelSOCardCatalogBinding(
        kind="filesystem_yaml",
        cards_dir=cards_dir,
        decks_dir=decks_dir,
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


@pytest.mark.unit
def test_runtime_snapshot_has_deterministic_digest_and_is_source_isolated(tmp_path: Path) -> None:
    binding = _write_runtime_content(tmp_path)
    snapshot = load_card_runtime_snapshot(binding, deck_id="deck.test.standard")
    again = load_card_runtime_snapshot(binding, deck_id="deck.test.standard")

    assert snapshot.content_sha256 == again.content_sha256
    assert snapshot.content_sha256 == canonical_card_runtime_sha256(
        snapshot.card_catalog, snapshot.decks
    )
    assert snapshot.selected_deck.id == "deck.test.standard"
    assert snapshot.provenance is not None
    assert snapshot.provenance.content_sha256 == snapshot.content_sha256

    (binding.cards_dir / "advance.yaml").write_text(
        yaml.safe_dump(dict(_CARD, priority=999)), encoding="utf-8"
    )
    assert snapshot.card_catalog.require("card.test.advance").priority == 100
    assert snapshot.content_sha256 == again.content_sha256


@pytest.mark.unit
def test_runtime_loader_rejects_missing_empty_duplicate_and_unknown_decks(tmp_path: Path) -> None:
    binding = _write_runtime_content(tmp_path)
    cards = load_card_catalog(binding)

    missing = tmp_path / "missing-decks"
    with pytest.raises(FileNotFoundError, match="card deck directory"):
        load_deck_catalog(missing, card_catalog=cards)

    empty = tmp_path / "empty-decks"
    empty.mkdir()
    with pytest.raises(ValueError, match="no YAML specs"):
        load_deck_catalog(empty, card_catalog=cards)

    unknown = tmp_path / "unknown-decks"
    unknown.mkdir()
    deck = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.deck",
        "id": "deck.test.unknown",
        "display_name": "Unknown",
        "hand_size": 1,
        "register_count": 1,
        "cards": [{"card_id": "card.test.missing", "count": 1}],
    }
    (unknown / "unknown.yaml").write_text(yaml.safe_dump(deck), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown card"):
        load_deck_catalog(unknown, card_catalog=cards)

    duplicate = tmp_path / "duplicate-decks"
    duplicate.mkdir()
    duplicate_deck = dict(
        deck,
        id="deck.test.standard",
        cards=[{"card_id": "card.test.advance", "count": 1}],
    )
    (duplicate / "a.yaml").write_text(yaml.safe_dump(duplicate_deck), encoding="utf-8")
    (duplicate / "b.yaml").write_text(yaml.safe_dump(duplicate_deck), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate deck id"):
        load_deck_catalog(duplicate, card_catalog=cards)

    extra = tmp_path / "extra-decks"
    extra.mkdir()
    (extra / "extra.yaml").write_text(
        yaml.safe_dump(dict(duplicate_deck, unknown_field=True)), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="unknown_field"):
        load_deck_catalog(extra, card_catalog=cards)


@pytest.mark.unit
def test_card_mode_requires_explicit_deck_id_and_no_implicit_selection(tmp_path: Path) -> None:
    binding = _write_runtime_content(tmp_path)
    with pytest.raises(ValidationError, match="requires an explicit deck_id"):
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=binding.cards_dir,
            decks_dir=binding.decks_dir,
            card_mode_enabled=True,
        )
    with pytest.raises(ValidationError, match="requires card_mode_enabled"):
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=binding.cards_dir,
            decks_dir=binding.decks_dir,
            deck_id="deck.test.standard",
        )
    enabled = binding.model_copy(
        update={"card_mode_enabled": True, "deck_id": "deck.test.standard"}
    )
    assert load_card_runtime_snapshot(enabled).selected_deck_id == "deck.test.standard"

    snapshot = load_card_runtime_snapshot(binding)
    with pytest.raises(ValueError, match="no explicitly selected deck_id"):
        _ = snapshot.selected_deck
    assert snapshot.provenance is None
    with pytest.raises(ValueError, match="unknown selected deck_id"):
        load_card_runtime_snapshot(binding, deck_id="deck.test.missing")


@pytest.mark.unit
def test_paced_card_cadence_is_explicitly_card_mode_only() -> None:
    with pytest.raises(ValidationError, match="paced card cadence"):
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=Path("cards"),
            decks_dir=Path("decks"),
            card_cadence="paced",
        )

    enabled = ModelSOCardCatalogBinding(
        kind="filesystem_yaml",
        cards_dir=Path("cards"),
        decks_dir=Path("decks"),
        card_mode_enabled=True,
        deck_id="deck.test.standard",
        card_cadence="paced",
    )
    assert enabled.card_cadence == "paced"
