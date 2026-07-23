"""O-GATE objectives battery driver: --overlay selection + combined overlay shape.

Guards the P1 U-GATE/O-GATE re-measure prerequisites (design 2026-07-22 §5):

- the battery driver ``scripts/run_ogate_objectives_battery.py`` exposes an
  ``--overlay`` flag whose default preserves the asym-only battery byte-for-byte,
  so pre-existing runs are unchanged, and a passed ``--overlay`` selects the
  combined asym+utility overlay;
- the NEW combined overlay
  ``tactical_split_overdeal_utility_asym_v1_qwen.yaml`` parses and carries BOTH
  the asym objective arena (``foundry_60_asym_v1`` — objectives + vp_threshold)
  AND the utility pile (per-seat ``utility`` quota + ``utility_deck_id`` +
  ``utility_handler_pack``), with a keyless ``none`` secret resolver so
  ``so run --overlay`` and the driver can launch it without a resolver capability;
- the previously-shipped utility overlay's ``so run`` header works again
  (``secret_resolver`` regressed from ``injected`` to keyless ``none``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_ogate_objectives_battery import _ARENA_ID, _OVERLAY, _build_parser, _lane_overlay
from steel_onslaught.contracts.application import ModelSOOpenAICompatibleProviderBinding
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_match_contract_catalog,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAYS_DIR = _REPO_ROOT / "contracts_data/overlays"
_COMBINED_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"
_UTILITY_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_v1_qwen.yaml"

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# --overlay CLI selection
# ---------------------------------------------------------------------------


def test_default_overlay_arg_preserves_the_asym_battery() -> None:
    """Byte-identical default: passing no --overlay runs the asym-only overlay."""
    args = _build_parser().parse_args([])
    assert args.overlay == _OVERLAY
    assert _OVERLAY.name == "tactical_split_overdeal_asym_v1_qwen.yaml"


def test_overlay_arg_selects_the_combined_asym_utility_overlay() -> None:
    args = _build_parser().parse_args(["--overlay", str(_COMBINED_OVERLAY)])
    assert args.overlay == _COMBINED_OVERLAY


def test_lane_overlay_loads_the_selected_overlay_and_repoints_surfaces(tmp_path: Path) -> None:
    overlay = _lane_overlay(tmp_path, _COMBINED_OVERLAY)
    assert overlay.contracts.arena_id == _ARENA_ID
    # Durable surfaces repointed into the battery lane, not the overlay's paths.
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"


def test_lane_overlay_default_is_the_asym_overlay(tmp_path: Path) -> None:
    """The _lane_overlay default arg matches the driver's asym default."""
    overlay = _lane_overlay(tmp_path)
    assert overlay.contracts.arena_id == _ARENA_ID
    assert overlay.llm.secret_resolver.kind == "injected"


# ---------------------------------------------------------------------------
# Combined overlay shape: asym objective arena AND utility pile
# ---------------------------------------------------------------------------


def test_combined_overlay_binds_the_asym_objective_arena() -> None:
    overlay = load_application_overlay(_COMBINED_OVERLAY)
    assert overlay.contracts.arena_id == "foundry_60_asym_v1"
    # The objectives + vp_threshold live on the arena contract this overlay
    # references, so a match can end on VP, not only elimination.
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.vp_threshold == 15
    assert {o.objective_id for o in arena.objectives} == {
        "objective.west_yard",
        "objective.north_works",
        "objective.east_gate",
    }


def test_combined_overlay_deals_a_utility_pile_that_competes_for_the_registers() -> None:
    overlay = load_application_overlay(_COMBINED_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert catalog.deck_policy is not None
    seats = catalog.deck_policy.seats
    assert {s.side for s in seats} == {"red", "blue"}
    for seat in seats:
        # Over-deal stays the mechanism: 4 movement + 4 weapon + 2 utility = 10
        # dealt, program 5 — utility competes for the SAME 5 registers.
        assert seat.hand_quota.movement == 4
        assert seat.hand_quota.weapon == 4
        assert seat.hand_quota.utility == 2
        assert seat.register_count == 5
        assert seat.utility_deck_id == "deck.utility.v1"


def test_combined_overlay_names_the_full_utility_handler_pack() -> None:
    overlay = load_application_overlay(_COMBINED_OVERLAY)
    pack = overlay.contracts.utility_handler_pack
    assert pack is not None
    assert pack.pack_id == "utility.resolution.v1"
    assert tuple(pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


def test_combined_overlay_uses_a_keyless_cli_launchable_secret_resolver() -> None:
    """`none` (not `injected`) lets `so run --overlay` and the driver launch it
    without a resolver capability; the sole provider is keyless."""
    overlay = load_application_overlay(_COMBINED_OVERLAY)
    assert overlay.llm.secret_resolver.kind == "none"
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "qwen35"
    assert provider.secret_ref is None


# ---------------------------------------------------------------------------
# Shipped utility overlay regression: its `so run` header must launch keyless
# ---------------------------------------------------------------------------


def test_shipped_utility_overlay_secret_resolver_is_keyless() -> None:
    overlay = load_application_overlay(_UTILITY_OVERLAY)
    assert overlay.llm.secret_resolver.kind == "none"
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.secret_ref is None
