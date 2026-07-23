"""Cross-family B: deepseek combined utility+asym overlay + driver loadout args.

Guards the CROSS-FAMILY (deepseek-v4-flash) arm prerequisites — the deepseek
twin of ``test_ogate_objectives_battery_qwen27_driver.py``:

- the NEW combined deepseek overlay
  ``tactical_split_overdeal_utility_asym_v1_deepseek.yaml`` parses and carries the
  asym objective arena (``foundry_60_asym_v1`` — objectives + vp_threshold), the
  utility pile (per-seat ``utility`` quota + ``utility_deck_id`` +
  ``utility_handler_pack``), a keyless ``none`` secret resolver, and the deepseek
  provider deltas (endpoint :8101, model ``deepseek-v4-flash``, max_tokens 4096,
  timeout 240) with the deepseek pilots + registry;
- the driver ``--red-loadout`` / ``--blue-loadout`` flags select the deepseek
  loadouts, and ``_lane_overlay`` repoints its state surfaces cleanly.

The winning live config (from the 2026-07-23 probe) is baked into the overlay:
``response_format: json_object`` is always sent by the programming path, and the
overlay tunes ``max_tokens: 4096`` / ``timeout_seconds: 240`` so the reasoning
span (~1680 tokens) never truncates the register JSON.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_ogate_objectives_battery import (
    _ARENA_ID,
    _build_parser,
    _lane_overlay,
)
from steel_onslaught.contracts.application import ModelSOOpenAICompatibleProviderBinding
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_match_contract_catalog,
    load_pilot_registry,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAYS_DIR = _REPO_ROOT / "contracts_data/overlays"
_DEEPSEEK_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_deepseek.yaml"
_DEEPSEEK_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/deepseek/berserker_scout.yaml"
_DEEPSEEK_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/deepseek/sniper_ironclad.yaml"

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Driver --red-loadout / --blue-loadout: deepseek loadouts selectable
# ---------------------------------------------------------------------------


def test_loadout_args_select_the_deepseek_loadouts() -> None:
    args = _build_parser().parse_args(
        [
            "--red-loadout",
            str(_DEEPSEEK_RED_LOADOUT),
            "--blue-loadout",
            str(_DEEPSEEK_BLUE_LOADOUT),
        ]
    )
    assert args.red_loadout == _DEEPSEEK_RED_LOADOUT
    assert args.blue_loadout == _DEEPSEEK_BLUE_LOADOUT


# ---------------------------------------------------------------------------
# Combined deepseek overlay shape: asym objective arena AND utility pile
# ---------------------------------------------------------------------------


def test_deepseek_overlay_binds_the_asym_objective_arena() -> None:
    overlay = load_application_overlay(_DEEPSEEK_OVERLAY)
    assert overlay.contracts.arena_id == "foundry_60_asym_v1"
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.vp_threshold == 15
    assert {o.objective_id for o in arena.objectives} == {
        "objective.west_yard",
        "objective.north_works",
        "objective.east_gate",
    }


def test_deepseek_overlay_deals_a_utility_pile_that_competes_for_the_registers() -> None:
    overlay = load_application_overlay(_DEEPSEEK_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert catalog.deck_policy is not None
    seats = catalog.deck_policy.seats
    assert {s.side for s in seats} == {"red", "blue"}
    for seat in seats:
        assert seat.hand_quota.movement == 4
        assert seat.hand_quota.weapon == 4
        assert seat.hand_quota.utility == 2
        assert seat.register_count == 5
        assert seat.utility_deck_id == "deck.utility.v1"


def test_deepseek_overlay_names_the_full_utility_handler_pack() -> None:
    overlay = load_application_overlay(_DEEPSEEK_OVERLAY)
    pack = overlay.contracts.utility_handler_pack
    assert pack is not None
    assert pack.pack_id == "utility.resolution.v1"
    assert tuple(pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


# ---------------------------------------------------------------------------
# deepseek provider deltas (winning probe config) + pilots
# ---------------------------------------------------------------------------


def test_deepseek_overlay_binds_the_keyless_deepseek_provider_with_declared_deltas() -> None:
    overlay = load_application_overlay(_DEEPSEEK_OVERLAY)
    assert overlay.llm.secret_resolver.kind == "none"
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "deepseek"
    assert provider.model == "deepseek-v4-flash"
    assert (
        provider.endpoint_url
        == "http://stickybeatz-studio.tail75df5e.ts.net:8101/v1/chat/completions"
    )
    assert provider.secret_ref is None
    # Winning probe config: max_tokens must clear the ~1680-token reasoning span,
    # timeout must clear the ~131s worst-case completion at ~18.5 tok/s.
    assert provider.max_tokens == 4096
    assert provider.timeout_seconds == 240.0
    assert provider.retry.max_attempts == 1
    assert overlay.llm.model_identities[0].model_identity_id == "model_identity.deepseek"
    assert overlay.llm.model_identities[0].provider_binding_id == "deepseek"


def test_deepseek_overlay_programs_the_deepseek_pilots_and_registry() -> None:
    overlay = load_application_overlay(_DEEPSEEK_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert tuple(p.pilot_spec_id for p in catalog.programmers) == (
        "pilot.llm.deepseek_berserker",
        "pilot.llm.deepseek_sniper",
    )
    assert (
        overlay.contracts.pilot_registry_dir
        == (_REPO_ROOT / "contracts_data/pilots/fire_dense_deepseek").resolve()
    )
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    for pilot_id, persona in (
        ("pilot.llm.deepseek_berserker", "berserker"),
        ("pilot.llm.deepseek_sniper", "sniper"),
    ):
        spec = registry.get(pilot_id)
        assert spec is not None
        assert isinstance(spec.parameters, ModelSOLlmPilotParams)
        assert spec.parameters.provider == "deepseek"
        assert spec.parameters.persona == persona


# ---------------------------------------------------------------------------
# deepseek loadouts resolve to the deepseek pilots
# ---------------------------------------------------------------------------


def test_deepseek_loadouts_bind_the_deepseek_pilots() -> None:
    from steel_onslaught.match.composition import load_loadout

    red = load_loadout(_DEEPSEEK_RED_LOADOUT)
    blue = load_loadout(_DEEPSEEK_BLUE_LOADOUT)
    assert red.id == "loadout.llm.deepseek_berserker"
    assert red.pilot_id == "pilot.llm.deepseek_berserker"
    assert blue.id == "loadout.llm.deepseek_sniper_ironclad"
    assert blue.pilot_id == "pilot.llm.deepseek_sniper"


def test_lane_overlay_repoints_surfaces_for_the_deepseek_overlay(tmp_path: Path) -> None:
    overlay = _lane_overlay(tmp_path, _DEEPSEEK_OVERLAY)
    assert overlay.contracts.arena_id == _ARENA_ID
    assert overlay.llm.secret_resolver.kind == "none"
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"
