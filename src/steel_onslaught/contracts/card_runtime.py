"""Immutable, composition-owned card/deck runtime snapshots.

The card and deck contracts are deliberately data-only.  This module adds the
small value object that a composition root can hand to live and replay code:
validated card definitions, validated deck definitions, an optional explicitly
selected deck, and a digest of the canonical content.  It has no filesystem,
default-deck, provider, or event-bus authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from steel_onslaught.contracts.card import ModelSOCard, ModelSOCardCatalog
from steel_onslaught.contracts.deck import DeckId, ModelSODeck
from steel_onslaught.contracts.player_selection import Sha256Digest


class _ClosedCardRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOCardRuntimeProvenance(_ClosedCardRuntimeModel):
    """The card/deck identity persisted with a match start when selected."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.card_runtime_provenance"] = Field(...)
    deck_id: DeckId
    content_sha256: Sha256Digest


def canonical_card_runtime_sha256(
    card_catalog: ModelSOCardCatalog,
    decks: tuple[ModelSODeck, ...],
) -> Sha256Digest:
    """Hash canonical model content, independent of source file names/order."""

    canonical = json.dumps(
        {
            "cards": [
                card.model_dump(mode="json")
                for card in sorted(card_catalog.cards, key=lambda item: str(item.id))
            ],
            "decks": [
                deck.model_dump(mode="json")
                for deck in sorted(decks, key=lambda item: str(item.id))
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ModelSOCardRuntimeSnapshot(_ClosedCardRuntimeModel):
    """Immutable card/deck content selected by one composition root."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.card_runtime_snapshot"] = Field(...)
    card_catalog: ModelSOCardCatalog
    decks: tuple[ModelSODeck, ...] = Field(min_length=1)
    selected_deck_id: DeckId | None = None
    content_sha256: Sha256Digest

    @model_validator(mode="after")
    def _validate_snapshot(self) -> Self:
        deck_ids = tuple(deck.id for deck in self.decks)
        if len(deck_ids) != len(set(deck_ids)):
            raise ValueError("card runtime snapshot deck ids must be unique")
        if deck_ids != tuple(sorted(deck_ids)):
            raise ValueError("card runtime snapshot decks must be sorted by id")
        card_ids = tuple(str(card.id) for card in self.card_catalog.cards)
        if card_ids != tuple(sorted(card_ids)):
            raise ValueError("card runtime snapshot cards must be sorted by id")
        if self.selected_deck_id is not None and self.selected_deck_id not in deck_ids:
            raise ValueError(f"selected card runtime deck {self.selected_deck_id!r} is not present")
        for deck in self.decks:
            for entry in deck.cards:
                if entry.card_id not in card_ids:
                    raise ValueError(f"deck {deck.id!r} references unknown card {entry.card_id!r}")
        expected = canonical_card_runtime_sha256(self.card_catalog, self.decks)
        if self.content_sha256 != expected:
            raise ValueError(
                "card runtime content_sha256 does not match canonical card/deck content"
            )
        return self

    @property
    def cards(self) -> tuple[ModelSOCard, ...]:
        """Expose the immutable card tuple without duplicating ownership."""

        return self.card_catalog.cards

    def require_deck(self, deck_id: str) -> ModelSODeck:
        """Resolve only an explicitly named deck; no default is inferred."""

        if not isinstance(deck_id, str) or not deck_id:
            raise ValueError("deck_id must be a non-empty string")
        for deck in self.decks:
            if deck.id == deck_id:
                return deck
        raise KeyError(f"unknown card runtime deck {deck_id!r}")

    @property
    def selected_deck(self) -> ModelSODeck:
        """Return the selected deck or fail closed when card mode is unbound."""

        if self.selected_deck_id is None:
            raise ValueError("card runtime snapshot has no explicitly selected deck_id")
        return self.require_deck(self.selected_deck_id)

    @property
    def provenance(self) -> ModelSOCardRuntimeProvenance | None:
        """Return start provenance only when a deck was explicitly selected."""

        if self.selected_deck_id is None:
            return None
        return ModelSOCardRuntimeProvenance(
            schema_version="0.1.0",
            kind="steel_onslaught.card_runtime_provenance",
            deck_id=self.selected_deck_id,
            content_sha256=self.content_sha256,
        )


__all__ = [
    "ModelSOCardRuntimeProvenance",
    "ModelSOCardRuntimeSnapshot",
    "canonical_card_runtime_sha256",
]
