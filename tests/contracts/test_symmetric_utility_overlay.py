"""Scenario-axis proof for the tolerant symmetric utility overlay.

``tactical_split_overdeal_utility_sym_v1_qwen.yaml`` exists to run the qwen35
sub-chance utility deprioritization probe on the SYMMETRIC, objective-less arena
(``foundry_60``) while holding EVERYTHING ELSE identical to the asym overlay
(``tactical_split_overdeal_utility_asym_v1_qwen.yaml``) that already completed 30
matches.  That "everything else identical" is the whole design: the only free
variable across the two lanes is the arena (asymmetric+objectives vs
symmetric+no-objectives), so a difference in the utility-deprioritization signal
is attributable to the arena axis and nothing else.

This suite proves, without a live battery (CI-safe):

  1. the shipped overlay parses + validates as a closed application overlay;
  2. it binds the symmetric arena ``foundry_60``, which is genuinely
     objective-less (``objectives == ()`` and ``vp_threshold is None``);
  3. it still deals a utility pile (each seat has a utility deck + a positive
     utility hand quota, and the utility handler pack is selected); and
  4. its retry config is the SAME proven-tolerant retry the asym overlay ran 30
     matches on.

Note on retry (deviation from the dispatch's literal spec, documented here as
the load-bearing fact): the dispatch asked to assert ``max_attempts > 1``.  That
is impossible for a *runnable* live overlay.  The asym overlay that "proved
tolerant" actually runs at ``max_attempts == 1`` (verified below), and the live
provider-selection path ``SelectedOnlyLlmClientBuilder.select`` HARD-REQUIRES
``max_attempts == 1`` -- setting it to 4 would make this overlay raise
``"selected live provider requires max_attempts=1"`` at battery launch, i.e. be
un-runnable live, defeating the scenario test.  So genuine "inherit the asym
overlay's proven-tolerant retry" means inheriting ``max_attempts == 1``, and
this test asserts the retry EQUALS the asym overlay's retry rather than a value
the runtime forbids.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOOpenAICompatibleProviderBinding,
)
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_match_contract_catalog,
)

pytestmark = pytest.mark.unit

_OVERLAYS = Path(__file__).parent.parent.parent / "contracts_data" / "overlays"
_SYM_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_sym_v1_qwen.yaml"
_ASYM_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"

_QWEN35_PROVIDER_ID = "qwen35"


def _qwen35_provider(
    overlay: ModelSOApplicationOverlay,
) -> ModelSOOpenAICompatibleProviderBinding:
    selected = [
        provider
        for provider in overlay.llm.providers
        if provider.provider_id == _QWEN35_PROVIDER_ID
    ]
    assert len(selected) == 1, "overlay must declare exactly one qwen35 provider"
    provider = selected[0]
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    return provider


def test_symmetric_utility_overlay_parses_and_binds_objectiveless_arena() -> None:
    """It validates and binds the symmetric, objective-less arena foundry_60."""

    overlay = load_application_overlay(_SYM_OVERLAY)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == "foundry_60"

    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    arena = catalog.arenas[overlay.contracts.arena_id]
    # Symmetric arena: no objective cells, no VP victory path (unlike the asym
    # lane, which carries 3 objectives + vp_threshold).
    assert arena.objectives == ()
    assert arena.vp_threshold is None


def test_symmetric_utility_overlay_still_deals_a_utility_pile() -> None:
    """Every seat is dealt a positive utility quota and the pack is selected."""

    overlay = load_application_overlay(_SYM_OVERLAY)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    deck_policy = card_binding.deck_policy
    assert deck_policy is not None
    assert deck_policy.seats, "the deck policy must declare seats"
    for seat in deck_policy.seats:
        assert seat.utility_deck_id is not None
        assert seat.hand_quota.utility > 0

    utility_pack = overlay.contracts.utility_handler_pack
    assert utility_pack is not None
    assert tuple(utility_pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


def test_symmetric_utility_overlay_inherits_asym_proven_tolerant_retry() -> None:
    """The retry config is the SAME one the asym overlay ran 30 matches on.

    ``max_attempts == 1`` is the proven-tolerant value AND the only value the
    live provider-selection path accepts (see module docstring).  Asserting
    equality with the asym provider block proves genuine inheritance rather than
    a divergent, un-runnable retry.
    """

    sym_provider = _qwen35_provider(load_application_overlay(_SYM_OVERLAY))
    asym_provider = _qwen35_provider(load_application_overlay(_ASYM_OVERLAY))

    # Proven-tolerant retry: exactly what the asym overlay carries.
    assert sym_provider.retry.max_attempts == 1
    assert sym_provider.retry == asym_provider.retry
    assert sym_provider.timeout_seconds == asym_provider.timeout_seconds
    # The provider block as a whole is inherited verbatim from the asym overlay.
    assert sym_provider == asym_provider


def test_symmetric_overlay_only_differs_from_asym_by_arena_binding() -> None:
    """The single free variable across the two lanes is the arena binding.

    Everything the match runtime consumes -- providers/retry, the deck policy
    (piles, over-deal quotas), and the utility handler pack -- is identical to
    the asym overlay; only ``arena_id`` differs (asym: ``foundry_60_asym_v1``).
    """

    sym = load_application_overlay(_SYM_OVERLAY)
    asym = load_application_overlay(_ASYM_OVERLAY)

    assert sym.contracts.arena_id == "foundry_60"
    assert asym.contracts.arena_id == "foundry_60_asym_v1"
    assert sym.contracts.arena_id != asym.contracts.arena_id

    assert sym.llm.providers == asym.llm.providers
    assert sym.contracts.card_catalog is not None
    assert asym.contracts.card_catalog is not None
    assert sym.contracts.card_catalog.deck_policy == asym.contracts.card_catalog.deck_policy
    assert sym.contracts.utility_handler_pack == asym.contracts.utility_handler_pack
