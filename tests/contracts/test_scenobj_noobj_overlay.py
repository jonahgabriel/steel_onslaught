"""Single-axis proof for the SO-SCEN-OBJ objectives-toggle control arm.

``tactical_split_overdeal_utility_asym_v1_noobj_qwen.yaml`` +
``foundry_60_asym_v1_noobj.yaml`` exist to answer the follow-up
``docs/evidence/2026-07-23-scenario-variation-qwen35-symmetric.md`` names in its
own "Verdict and caveats": the shipped scenario contrast varies arena GEOMETRY
and OBJECTIVES simultaneously, so the keep-rate magnitude drift between the two
batteries cannot be attributed to either axis.  This arm holds the ASYM geometry
fixed and toggles objectives OFF, completing the third corner of the 2x2.

The claim "geometry is held exactly constant" is the load-bearing one, and prose
cannot carry it -- ``test_noobj_arena_geometry_is_identical_to_asym_v1`` below
compares the two parsed arena contracts field by field, so any future edit that
moves a rect, a spawn, the size, or a sudden-death parameter fails CI rather
than silently invalidating the decomposition.

This suite proves, without a live battery (CI-safe):

  1. the shipped overlay parses + validates as a closed application overlay and
     binds ``foundry_60_asym_v1_noobj``;
  2. that arena is genuinely objective-less (``objectives == ()`` and
     ``vp_threshold is None``), i.e. the toggle actually landed;
  3. the arena's GEOMETRY is field-by-field identical to
     ``foundry_60_asym_v1`` -- size, spawns, obstacles, every rect, and both
     sudden-death parameters;
  4. the overlay still deals a utility pile and selects the same utility
     handler pack (the measured quantity survives the toggle); and
  5. the provider/retry block is inherited verbatim from the ASYM overlay, so
     the only free variable across the two lanes is the arena binding.

Retry note, inherited from ``test_symmetric_utility_overlay.py``: the live
provider-selection path ``SelectedOnlyLlmClientBuilder.select`` HARD-REQUIRES
``max_attempts == 1``, so "the proven-tolerant retry" means exactly that value,
and equality with the ASYM provider block is the assertion that proves genuine
inheritance rather than a divergent, un-runnable retry.
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

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"
_NOOBJ_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_noobj_qwen.yaml"
_ASYM_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"

_ASYM_ARENA_ID = "foundry_60_asym_v1"
_NOOBJ_ARENA_ID = "foundry_60_asym_v1_noobj"
_QWEN35_PROVIDER_ID = "qwen35"

# Every arena field that carries geometry or match-pacing semantics.  Objectives
# and VP threshold are deliberately EXCLUDED -- they are the toggled axis.
# ``arena_id`` and ``display_name`` are identity, not geometry.
_GEOMETRY_FIELDS = (
    "size",
    "spawn_a",
    "spawn_b",
    "obstacles",
    "rects",
    "sudden_death_start_tick",
    "sudden_death_damage_base",
)


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


def test_noobj_overlay_parses_and_binds_objectiveless_asym_arena() -> None:
    """It validates and binds the objectives-stripped ASYM arena."""

    overlay = load_application_overlay(_NOOBJ_OVERLAY)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == _NOOBJ_ARENA_ID

    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    arena = catalog.arenas[overlay.contracts.arena_id]
    # The toggle actually landed: no objective cells, no VP victory path.
    assert arena.objectives == ()
    assert arena.vp_threshold is None

    # And the arena it was cut from still carries them, unmodified.
    asym_arena = catalog.arenas[_ASYM_ARENA_ID]
    assert len(asym_arena.objectives) == 3
    assert asym_arena.vp_threshold == 15


def test_noobj_arena_geometry_is_identical_to_asym_v1() -> None:
    """Geometry is held EXACTLY constant -- the arm's load-bearing claim.

    This is the assertion that makes the drift decomposition valid.  If any
    terrain, spawn, size, or sudden-death field diverges, the arm is no longer a
    single-axis toggle and its objectives/geometry attribution is meaningless.
    """

    catalog = load_match_contract_catalog(Path("contracts_data"))
    asym = catalog.arenas[_ASYM_ARENA_ID]
    noobj = catalog.arenas[_NOOBJ_ARENA_ID]

    for field in _GEOMETRY_FIELDS:
        assert getattr(noobj, field) == getattr(asym, field), (
            f"geometry field {field!r} diverged between {_ASYM_ARENA_ID} and "
            f"{_NOOBJ_ARENA_ID}; the SCEN-OBJ arm requires byte-equal geometry"
        )

    # Derived terrain must match too, not just the authored rect list.
    assert noobj.obstacle_cells == asym.obstacle_cells

    # The ONLY differences are identity + the toggled axis.
    assert noobj.arena_id != asym.arena_id
    assert noobj.objectives != asym.objectives
    assert noobj.vp_threshold != asym.vp_threshold


def test_noobj_overlay_still_deals_a_utility_pile() -> None:
    """Every seat is dealt a positive utility quota and the pack is selected."""

    overlay = load_application_overlay(_NOOBJ_OVERLAY)
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


def test_noobj_overlay_inherits_asym_provider_and_retry_verbatim() -> None:
    """The provider block is the SAME one the ASYM baseline ran 30 matches on."""

    noobj_provider = _qwen35_provider(load_application_overlay(_NOOBJ_OVERLAY))
    asym_provider = _qwen35_provider(load_application_overlay(_ASYM_OVERLAY))

    assert noobj_provider.retry.max_attempts == 1
    assert noobj_provider.retry == asym_provider.retry
    assert noobj_provider.timeout_seconds == asym_provider.timeout_seconds
    assert noobj_provider == asym_provider


def test_noobj_overlay_only_differs_from_asym_by_arena_binding() -> None:
    """The single free variable across the two lanes is the arena binding.

    Everything the match runtime consumes -- providers/retry, the deck policy
    (piles, over-deal quotas), and the utility handler pack -- is identical to
    the ASYM overlay; only ``arena_id`` differs.  The ``.onex_state`` path stems
    also differ, but the battery driver rewrites every durable path from
    ``--state-root``, so those strings never reach the runtime.
    """

    noobj = load_application_overlay(_NOOBJ_OVERLAY)
    asym = load_application_overlay(_ASYM_OVERLAY)

    assert noobj.contracts.arena_id == _NOOBJ_ARENA_ID
    assert asym.contracts.arena_id == _ASYM_ARENA_ID

    assert noobj.llm.providers == asym.llm.providers
    assert noobj.contracts.card_catalog is not None
    assert asym.contracts.card_catalog is not None
    assert noobj.contracts.card_catalog.deck_policy == asym.contracts.card_catalog.deck_policy
    assert noobj.contracts.utility_handler_pack == asym.contracts.utility_handler_pack
    assert noobj.contracts.pilot_registry_dir == asym.contracts.pilot_registry_dir
    assert noobj.contracts.balance_rule_pack == asym.contracts.balance_rule_pack
