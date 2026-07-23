"""Cross-model B: qwen27 combined utility+asym overlay + driver loadout args.

Guards the SECOND-model (qwen27) re-measure prerequisites (design 2026-07-22 §5,
cross-model B):

- the battery driver ``scripts/run_ogate_objectives_battery.py`` exposes
  ``--red-loadout`` / ``--blue-loadout`` flags whose defaults preserve the
  qwen35 loadouts byte-for-byte (so pre-existing runs are unchanged), and a
  passed loadout is honored through ``_run_match``;
- the NEW combined qwen27 overlay
  ``tactical_split_overdeal_utility_asym_v1_qwen27.yaml`` parses and carries the
  asym objective arena (``foundry_60_asym_v1`` — objectives + vp_threshold), the
  utility pile (per-seat ``utility`` quota + ``utility_deck_id`` +
  ``utility_handler_pack``), a keyless ``none`` secret resolver, and the qwen27
  provider deltas (endpoint :8001, model, max_tokens 4096, timeout 120) with the
  qwen27 pilots + registry.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from scripts.run_ogate_objectives_battery import (
    _ARENA_ID,
    _BLUE_LOADOUT,
    _RED_LOADOUT,
    _build_parser,
    _lane_overlay,
    _run_match,
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
_QWEN27_OVERLAY = _OVERLAYS_DIR / "tactical_split_overdeal_utility_asym_v1_qwen27.yaml"
_QWEN27_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen27/berserker_scout.yaml"
_QWEN27_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen27/sniper_ironclad.yaml"

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Driver --red-loadout / --blue-loadout: default byte-identical, override honored
# ---------------------------------------------------------------------------


def test_loadout_args_default_to_the_qwen35_loadouts_byte_identical() -> None:
    """No --red/--blue-loadout runs the historical qwen35 loadouts unchanged."""
    args = _build_parser().parse_args([])
    assert args.red_loadout == _RED_LOADOUT
    assert args.blue_loadout == _BLUE_LOADOUT
    assert _RED_LOADOUT.name == "llm_qwen35_berserker.yaml"
    assert _BLUE_LOADOUT == _REPO_ROOT / "contracts_data/loadouts/qwen35/sniper_ironclad.yaml"


def test_loadout_args_select_the_qwen27_loadouts() -> None:
    args = _build_parser().parse_args(
        [
            "--red-loadout",
            str(_QWEN27_RED_LOADOUT),
            "--blue-loadout",
            str(_QWEN27_BLUE_LOADOUT),
        ]
    )
    assert args.red_loadout == _QWEN27_RED_LOADOUT
    assert args.blue_loadout == _QWEN27_BLUE_LOADOUT


def test_run_match_threads_loadout_paths_into_assembly() -> None:
    """``_run_match`` accepts per-seat loadout paths (not hardcoded constants),
    defaulting to the qwen35 loadouts so default behavior is unchanged."""
    sig = inspect.signature(_run_match)
    assert sig.parameters["red_loadout_path"].default == _RED_LOADOUT
    assert sig.parameters["blue_loadout_path"].default == _BLUE_LOADOUT


# ---------------------------------------------------------------------------
# Combined qwen27 overlay shape: asym objective arena AND utility pile
# ---------------------------------------------------------------------------


def test_qwen27_overlay_binds_the_asym_objective_arena() -> None:
    overlay = load_application_overlay(_QWEN27_OVERLAY)
    assert overlay.contracts.arena_id == "foundry_60_asym_v1"
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.vp_threshold == 15
    assert {o.objective_id for o in arena.objectives} == {
        "objective.west_yard",
        "objective.north_works",
        "objective.east_gate",
    }


def test_qwen27_overlay_deals_a_utility_pile_that_competes_for_the_registers() -> None:
    overlay = load_application_overlay(_QWEN27_OVERLAY)
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


def test_qwen27_overlay_names_the_full_utility_handler_pack() -> None:
    overlay = load_application_overlay(_QWEN27_OVERLAY)
    pack = overlay.contracts.utility_handler_pack
    assert pack is not None
    assert pack.pack_id == "utility.resolution.v1"
    assert tuple(pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


# ---------------------------------------------------------------------------
# qwen27 provider deltas + pilots
# ---------------------------------------------------------------------------


def test_qwen27_overlay_binds_the_keyless_qwen27_provider_with_declared_deltas() -> None:
    overlay = load_application_overlay(_QWEN27_OVERLAY)
    assert overlay.llm.secret_resolver.kind == "none"
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "qwen27"
    assert provider.model == "Qwen3.6-27B-MTP-IQ4_XS.gguf"
    assert provider.endpoint_url == "http://omninode-pc.tail75df5e.ts.net:8001/v1/chat/completions"
    assert provider.secret_ref is None
    assert provider.max_tokens == 4096
    assert provider.timeout_seconds == 120.0
    assert overlay.llm.model_identities[0].model_identity_id == "model_identity.qwen27"
    assert overlay.llm.model_identities[0].provider_binding_id == "qwen27"


def test_qwen27_overlay_programs_the_qwen27_pilots_and_registry() -> None:
    overlay = load_application_overlay(_QWEN27_OVERLAY)
    catalog = overlay.contracts.card_catalog
    assert catalog is not None
    assert tuple(p.pilot_spec_id for p in catalog.programmers) == (
        "pilot.llm.qwen27_berserker",
        "pilot.llm.qwen27_sniper",
    )
    assert (
        overlay.contracts.pilot_registry_dir
        == (_REPO_ROOT / "contracts_data/pilots/fire_dense_qwen27").resolve()
    )
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    for pilot_id, persona in (
        ("pilot.llm.qwen27_berserker", "berserker"),
        ("pilot.llm.qwen27_sniper", "sniper"),
    ):
        spec = registry.get(pilot_id)
        assert spec is not None
        assert isinstance(spec.parameters, ModelSOLlmPilotParams)
        assert spec.parameters.provider == "qwen27"
        assert spec.parameters.persona == persona


def test_lane_overlay_repoints_surfaces_for_the_qwen27_overlay(tmp_path: Path) -> None:
    overlay = _lane_overlay(tmp_path, _QWEN27_OVERLAY)
    assert overlay.contracts.arena_id == _ARENA_ID
    assert overlay.llm.secret_resolver.kind == "none"
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"
