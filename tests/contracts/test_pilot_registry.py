"""Exact injected pilot-registry resolution tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.contracts.pilot_registry import PilotResolutionError, PilotSpecRegistry
from steel_onslaught.match.composition import load_pilot_registry, load_pilot_spec

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PILOTS_DIR = _REPO_ROOT / "contracts_data" / "pilots"
_LOADOUTS_DIR = _REPO_ROOT / "contracts_data" / "loadouts"

_PINNED_LOADOUT_PILOT_IDS: dict[str, str] = {
    "example_aggressive_light.yaml": "pilot.template.aggressive",
    "example_llm_berserker_light.yaml": "pilot.llm.berserker",
    "example_llm_sniper_light.yaml": "pilot.llm.sniper",
    "example_predictive_heavy.yaml": "pilot.template.predictive",
    "live_glm_opportunist_hunter.yaml": "pilot.glm.opportunist",
    "live_glm_sniper_ironclad.yaml": "pilot.glm.sniper",
    "llm_qwen27_sniper.yaml": "pilot.llm.qwen27",
    "llm_qwen35_berserker.yaml": "pilot.llm.qwen35",
    "llm_qwen35_berserker_v2.yaml": "pilot.llm.qwen35",
    "llm_qwen35_berserker_dmg3.yaml": "pilot.llm.qwen35",
    "llm_qwen35_berserker_dmg55.yaml": "pilot.llm.qwen35",
    "proof_blue_aggressive_hunter.yaml": "pilot.template.aggressive",
    "proof_blue_defensive_passive.yaml": "pilot.template.defensive",
    "proof_red_defensive_passive.yaml": "pilot.template.defensive",
    "proof_red_predictive_ironclad.yaml": "pilot.template.predictive",
    "tuned_aggressive_hunter.yaml": "pilot.tuned.aggressive_hot_v1",
}


def _load_loadout_dict(name: str) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((_LOADOUTS_DIR / name).read_text(encoding="utf-8"))
    return raw


def _loadout_with(pilot_id: str, *, pilot_spec_path: str | None = None) -> ModelSOLoadout:
    """A real loadout (proof blue) re-keyed to the pilot under test."""
    raw = _load_loadout_dict("proof_blue_aggressive_hunter.yaml")
    raw["pilot_id"] = pilot_id
    if pilot_spec_path is not None:
        raw["pilot_spec_path"] = pilot_spec_path
    return ModelSOLoadout.model_validate(raw)


@pytest.fixture(scope="module")
def registry() -> PilotSpecRegistry:
    return load_pilot_registry(_PILOTS_DIR)


# ---------------------------------------------------------------------------
# Registry scan (resolution step 2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registry_scans_pilots_dir_and_resolves_template(registry: PilotSpecRegistry) -> None:
    loadout = _loadout_with("pilot.template.aggressive")
    spec = registry.resolve(loadout)
    assert spec.id == "pilot.template.aggressive"
    assert spec.archetype == "aggressive"
    assert spec == load_pilot_spec(_PILOTS_DIR / "template_aggressive.yaml")


@pytest.mark.unit
def test_registry_resolves_tuned_fork_by_pilot_id(registry: PilotSpecRegistry) -> None:
    loadout = _loadout_with("pilot.tuned.aggressive_hot_v1")
    spec = registry.resolve(loadout)
    assert spec.id == "pilot.tuned.aggressive_hot_v1"
    assert spec.lineage.parent == "pilot.template.aggressive"


# ---------------------------------------------------------------------------
# pilot_spec_path is an outer-ingress concern
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pilot_spec_path_is_rejected_by_pure_registry(registry: PilotSpecRegistry) -> None:
    loadout = _loadout_with("pilot.tuned.aggressive_hot_v1", pilot_spec_path="fork.yaml")
    with pytest.raises(PilotResolutionError, match="ingress concern"):
        registry.resolve(loadout)


# ---------------------------------------------------------------------------
# Shipped loadouts declare exact registered ids
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("loadout_yaml", "pilot_id"), sorted(_PINNED_LOADOUT_PILOT_IDS.items()))
def test_shipped_loadout_filename_has_pinned_exact_pilot_id(
    registry: PilotSpecRegistry, loadout_yaml: str, pilot_id: str
) -> None:
    raw = _load_loadout_dict(loadout_yaml)
    loadout = ModelSOLoadout.model_validate(raw)
    spec = registry.resolve(loadout)
    assert loadout.pilot_id == pilot_id
    assert spec.id == pilot_id


@pytest.mark.unit
def test_unknown_exact_pilot_id_raises(registry: PilotSpecRegistry) -> None:
    loadout = _loadout_with("pilot.proof.mystery_v1")
    with pytest.raises(PilotResolutionError, match="unknown exact pilot_id"):
        registry.resolve(loadout)


@pytest.mark.unit
def test_archetype_substrings_do_not_create_implicit_aliases(
    registry: PilotSpecRegistry,
) -> None:
    loadout = _loadout_with("pilot.weird.defensive_aggressive_v1")
    with pytest.raises(PilotResolutionError, match="unknown exact pilot_id"):
        registry.resolve(loadout)


# ---------------------------------------------------------------------------
# Existing loadout YAMLs are untouched by the new optional field
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_shipped_loadouts_have_exact_registered_provenance(
    registry: PilotSpecRegistry,
) -> None:
    yaml_paths = sorted(_LOADOUTS_DIR.glob("*.yaml"))
    assert {path.name for path in yaml_paths} == set(_PINNED_LOADOUT_PILOT_IDS)
    for path in yaml_paths:
        loadout = ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        assert loadout.pilot_id == _PINNED_LOADOUT_PILOT_IDS[path.name]
        assert loadout.pilot_spec_path is None  # no shipped YAML uses the field
        spec = registry.resolve(loadout)
        assert isinstance(spec, ModelSOPilotSpec)
        assert spec.id == loadout.pilot_id
        if spec.id.startswith("pilot.template."):
            assert spec.lineage.parent is None
        else:
            assert spec.lineage.parent is not None
