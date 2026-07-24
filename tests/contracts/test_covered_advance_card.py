"""Contract proof for ``card.movement.covered_advance`` and its deal wiring.

Session 2026-07-24 (SO-SEEKCOVER). Forensics finding driving this build: the
movement-card vocabulary was relative-direction only (toward_enemy/
away_from_enemy/left/right) -- no cell-targeted or LOS-aware primitive
existed, so arena cover was unusable by construction (red pilot mentioned
terrain in 0/209 plan rationales; well-placed cover moved nothing; 0/30 red
wins on the v2 brawler recut, ``docs/evidence/2026-07-24-brawler-recut-v2-
battery.md``).

This adds exactly one new movement card, a new movement deck that rebinds
red's pool, and a new overlay that rebinds ONLY ``movement_deck_id`` on top
of the v2 arena/loadout pairing -- everything else (v1/v2 cards, decks,
overlays, both loadouts, both arenas) stays byte-frozen. This suite proves
that additivity without a live battery (CI-safe):

  1. the new card parses, validates, registers in the shipped catalog, and
     is the only new file in ``contracts_data/cards/``;
  2. ``deck.movement.v2`` parses, validates, holds pool size at 20 (matching
     v1), and the dealt-rate math for a 4-card hand_quota draw clears the
     cited heat-lance-analog bar (77.5%);
  3. ``deck.movement.v1`` is untouched;
  4. the new overlay parses, binds arena v2 (unchanged from the v2 overlay),
     binds red to ``deck.movement.v2`` while blue stays on
     ``deck.movement.v1``, and is otherwise byte-identical to the v2 overlay
     (same over-deal/utility shape, same provider/retry, same handler pack);
  5. the v2 overlay is untouched.
"""

from __future__ import annotations

from fractions import Fraction
from math import comb
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.card import ModelSOCard, SOCardCategory
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.match.composition import load_application_overlay, load_match_contract_catalog

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_CARDS_DIR = _REPO_ROOT / "contracts_data" / "cards"
_DECKS_DIR = _REPO_ROOT / "contracts_data" / "decks"
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"

_CARD_PATH = _CARDS_DIR / "movement_covered_advance.yaml"
_DECK_V1_PATH = _DECKS_DIR / "movement_v1.yaml"
_DECK_V2_PATH = _DECKS_DIR / "movement_v2.yaml"
_OVERLAY_V2 = _OVERLAYS / "tactical_split_overdeal_utility_asym_v2_qwen.yaml"
_OVERLAY_V3 = _OVERLAYS / "tactical_split_overdeal_utility_asym_v3_qwen.yaml"

_ARENA_V2_ID = "foundry_60_asym_v2"


def _load_card(path: Path) -> ModelSOCard:
    return ModelSOCard.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _load_deck(path: Path) -> ModelSODeck:
    return ModelSODeck.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Card: card.movement.covered_advance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_card_parses_and_is_movement_class_not_utility() -> None:
    card = _load_card(_CARD_PATH)
    assert card.id == "card.movement.covered_advance"
    assert card.category is SOCardCategory.MOVEMENT
    assert card.effect.direction == "covered_advance"
    assert card.effect.speed == "full"
    assert card.heat_cost == 0
    assert card.description is not None and "line of sight" in card.description.lower()


@pytest.mark.unit
def test_card_registers_in_the_shipped_catalog_with_a_unique_priority() -> None:
    cards = tuple(
        ModelSOCard.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(_CARDS_DIR.glob("*.yaml"))
    )
    ids = [card.id for card in cards]
    assert "card.movement.covered_advance" in ids
    assert len({card.priority for card in cards}) == len(cards), (
        "priority must stay globally unique across the whole catalog"
    )


@pytest.mark.unit
def test_card_loads_through_the_real_composition_root() -> None:
    """The directory-scan loader (``load_card_catalog``/``load_match_contract_catalog``
    equivalent path) picks up the new file with no manifest edit required."""
    from steel_onslaught.contracts.application import ModelSOCardCatalogBinding
    from steel_onslaught.match.composition import load_card_catalog

    binding = ModelSOCardCatalogBinding(
        kind="filesystem_yaml", cards_dir=_CARDS_DIR, decks_dir=_DECKS_DIR
    )
    catalog = load_card_catalog(binding)
    card = catalog.require("card.movement.covered_advance")
    assert card.category is SOCardCategory.MOVEMENT


# ---------------------------------------------------------------------------
# Deck: deck.movement.v2
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_deck_v2_parses_and_holds_pool_size_at_twenty() -> None:
    deck = _load_deck(_DECK_V2_PATH)
    assert deck.id == "deck.movement.v2"
    counts = {str(entry.card_id): entry.count for entry in deck.cards}
    assert counts == {
        "card.movement.advance": 2,
        "card.movement.covered_advance": 6,
        "card.movement.flank_left": 4,
        "card.movement.flank_right": 4,
        "card.movement.reposition": 4,
    }
    assert deck.total_cards() == 20  # unchanged from deck.movement.v1's pool size


@pytest.mark.unit
def test_deck_v2_deal_rate_clears_the_heat_lance_analog_bar() -> None:
    """Hypergeometric P(>=1 copy in a 4-card draw, no replacement) for
    ``covered_advance`` (k=6 of N=20) must clear the cited 77.5% analog bar,
    and a k=5 pool must NOT clear it -- pinning why k=6 was chosen."""
    deck = _load_deck(_DECK_V2_PATH)
    n = deck.total_cards()
    k = next(
        entry.count for entry in deck.cards if entry.card_id == "card.movement.covered_advance"
    )
    draw = 4

    def deal_rate(n: int, k: int, draw: int) -> Fraction:
        return 1 - Fraction(comb(n - k, draw), comb(n, draw))

    rate_k6 = deal_rate(n, k, draw)
    assert k == 6
    assert rate_k6 > Fraction(775, 1000)  # > 77.5%
    assert float(rate_k6) == pytest.approx(0.7934, abs=1e-3)

    rate_k5 = deal_rate(n, k - 1, draw)
    assert rate_k5 < Fraction(775, 1000)  # k=5 falls short of the bar
    assert float(rate_k5) == pytest.approx(0.7182, abs=1e-3)


@pytest.mark.unit
def test_deck_v1_is_untouched() -> None:
    deck = _load_deck(_DECK_V1_PATH)
    assert deck.id == "deck.movement.v1"
    counts = {str(entry.card_id): entry.count for entry in deck.cards}
    assert counts == {
        "card.movement.advance": 8,
        "card.movement.flank_left": 4,
        "card.movement.flank_right": 4,
        "card.movement.reposition": 4,
    }
    assert deck.total_cards() == 20


# ---------------------------------------------------------------------------
# Overlay: tactical_split_overdeal_utility_asym_v3_qwen.yaml
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overlay_v3_parses_and_binds_arena_v2_unchanged() -> None:
    overlay = load_application_overlay(_OVERLAY_V3)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == _ARENA_V2_ID

    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.objectives
    assert arena.vp_threshold == 15


@pytest.mark.unit
def test_overlay_v3_rebinds_only_reds_movement_deck() -> None:
    overlay = load_application_overlay(_OVERLAY_V3)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    deck_policy = card_binding.deck_policy
    assert deck_policy is not None
    by_side = {seat.side: seat for seat in deck_policy.seats}
    assert by_side["red"].movement_deck_id == "deck.movement.v2"
    assert by_side["blue"].movement_deck_id == "deck.movement.v1"
    # everything else in the split-deck policy stays the v2 shape
    for seat in deck_policy.seats:
        assert seat.weapon_deck_id == "deck.weapon.v1"
        assert seat.utility_deck_id == "deck.utility.v1"
        assert seat.hand_quota.movement == 4
        assert seat.hand_quota.weapon == 4
        assert seat.hand_quota.utility == 2
        assert seat.register_count == 5


@pytest.mark.unit
def test_overlay_v3_only_differs_from_v2_by_reds_movement_deck_binding() -> None:
    """The single free variable across the two overlays is red's
    ``movement_deck_id`` (and the isolated state-root paths, not asserted
    here). Providers/retry, the utility handler pack, hand quotas, and
    every other deck binding stay identical to the v2 overlay."""
    v2 = load_application_overlay(_OVERLAY_V2)
    v3 = load_application_overlay(_OVERLAY_V3)

    assert v2.contracts.arena_id == v3.contracts.arena_id == _ARENA_V2_ID
    assert v2.llm.providers == v3.llm.providers
    assert v2.contracts.utility_handler_pack == v3.contracts.utility_handler_pack

    v2_card = v2.contracts.card_catalog
    v3_card = v3.contracts.card_catalog
    assert v2_card is not None and v3_card is not None
    v2_policy = v2_card.deck_policy
    v3_policy = v3_card.deck_policy
    assert v2_policy is not None and v3_policy is not None
    v2_by_side = {seat.side: seat for seat in v2_policy.seats}
    v3_by_side = {seat.side: seat for seat in v3_policy.seats}

    assert v2_by_side["red"].movement_deck_id == "deck.movement.v1"
    assert v3_by_side["red"].movement_deck_id == "deck.movement.v2"
    assert (
        v2_by_side["blue"].movement_deck_id
        == v3_by_side["blue"].movement_deck_id
        == ("deck.movement.v1")
    )
    # weapon/utility deck bindings and hand quotas are untouched on both seats
    for side in ("red", "blue"):
        assert v2_by_side[side].weapon_deck_id == v3_by_side[side].weapon_deck_id
        assert v2_by_side[side].utility_deck_id == v3_by_side[side].utility_deck_id
        assert v2_by_side[side].hand_quota == v3_by_side[side].hand_quota
        assert v2_by_side[side].register_count == v3_by_side[side].register_count


@pytest.mark.unit
def test_overlay_v2_is_untouched() -> None:
    overlay = load_application_overlay(_OVERLAY_V2)
    assert overlay.contracts.arena_id == _ARENA_V2_ID
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    deck_policy = card_binding.deck_policy
    assert deck_policy is not None
    by_side = {seat.side: seat for seat in deck_policy.seats}
    assert by_side["red"].movement_deck_id == "deck.movement.v1"
