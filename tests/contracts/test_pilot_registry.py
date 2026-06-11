"""PilotSpecRegistry resolution tests — tunable-pilots Task 5.

Resolution order under test is Architectural Decision #5 (addendum §7):

1. ``loadout.pilot_spec_path`` (player-supplied; loaded spec id must equal
   ``loadout.pilot_id``; spec must carry a non-null ``lineage.parent``),
2. else the registry built from ``contracts_data/pilots/*.yaml`` keyed by
   spec ``id``,
3. else the MVP archetype fallback: first archetype name appearing as a
   substring of ``pilot_id`` (checked in the fixed order aggressive,
   defensive, predictive) resolves to that archetype's canonical template
   spec; no match is a resolution error.

Step-0 characterization baseline (captured from the merged MVP
``match.runner._pilot_for`` BEFORE this refactor, 2026-06-11):

    example_aggressive_light.yaml   pilot.example.aggressive_v1  AggressivePilot
    example_predictive_heavy.yaml   pilot.example.predictive_v1  PredictivePilot
    proof_blue_aggressive_hunter.yaml pilot.proof.aggressive_v1  AggressivePilot
    proof_blue_defensive_passive.yaml pilot.proof.defensive_v1   DefensivePilot
    proof_red_defensive_passive.yaml  pilot.proof.defensive_v1   DefensivePilot
    proof_red_predictive_ironclad.yaml pilot.proof.predictive_v1 PredictivePilot
    pilot.proof.mystery_v1 -> ValueError("unknown pilot archetype in pilot_id ...")

Every pilot was constructed from its archetype's template spec; the registry
fallback (step 3) must reproduce this mapping exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.contracts.pilot_registry import (
    PilotResolutionError,
    PilotSpecRegistry,
    load_pilot_spec,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PILOTS_DIR = _REPO_ROOT / "contracts_data" / "pilots"
_LOADOUTS_DIR = _REPO_ROOT / "contracts_data" / "loadouts"

# Characterization baseline: loadout YAML -> archetype the MVP `_pilot_for`
# resolved its pilot_id to (see module docstring).
_CHARACTERIZATION: dict[str, str] = {
    "example_aggressive_light.yaml": "aggressive",
    "example_predictive_heavy.yaml": "predictive",
    "proof_blue_aggressive_hunter.yaml": "aggressive",
    "proof_blue_defensive_passive.yaml": "defensive",
    "proof_red_defensive_passive.yaml": "defensive",
    "proof_red_predictive_ironclad.yaml": "predictive",
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


def _write_spec_yaml(path: Path, *, spec_id: str, parent: str | None) -> None:
    spec = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.pilot",
        "id": spec_id,
        "display_name": "Test Fork",
        "archetype": "aggressive",
        "lineage": {"parent": parent},
        "parameters": {
            "vent_at_heat_margin": 2,
            "idle_vent_heat_threshold": 90,
            "mode_switch_pressure_floor": 12,
            "mode_switch_heat_ceiling": 80,
            "weapon_preference": "highest_damage",
        },
    }
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")


@pytest.fixture(scope="module")
def registry() -> PilotSpecRegistry:
    return PilotSpecRegistry.load(_PILOTS_DIR)


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
# pilot_spec_path (resolution step 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pilot_spec_path_takes_precedence_over_registry(
    registry: PilotSpecRegistry, tmp_path: Path
) -> None:
    # Same id as a registry entry, but a different display_name proves the
    # path-loaded spec (step 1) wins over the registry entry (step 2).
    _write_spec_yaml(
        tmp_path / "fork.yaml",
        spec_id="pilot.tuned.aggressive_hot_v1",
        parent="pilot.template.aggressive",
    )
    loadout = _loadout_with("pilot.tuned.aggressive_hot_v1", pilot_spec_path="fork.yaml")
    spec = registry.resolve(loadout, base_dir=tmp_path)
    assert spec.display_name == "Test Fork"
    registry_spec = registry.resolve(_loadout_with("pilot.tuned.aggressive_hot_v1"))
    assert registry_spec.display_name != "Test Fork"


@pytest.mark.unit
def test_pilot_spec_path_id_mismatch_raises(registry: PilotSpecRegistry, tmp_path: Path) -> None:
    _write_spec_yaml(
        tmp_path / "fork.yaml",
        spec_id="pilot.player.other_id",
        parent="pilot.template.aggressive",
    )
    loadout = _loadout_with("pilot.player.hot_v9", pilot_spec_path="fork.yaml")
    with pytest.raises(PilotResolutionError, match="spec_id_mismatch"):
        registry.resolve(loadout, base_dir=tmp_path)


@pytest.mark.unit
def test_pilot_spec_path_null_parent_raises(registry: PilotSpecRegistry, tmp_path: Path) -> None:
    # Addendum §7 rule 1 / §8: player-supplied specs MUST name a parent.
    _write_spec_yaml(tmp_path / "fork.yaml", spec_id="pilot.player.hot_v9", parent=None)
    loadout = _loadout_with("pilot.player.hot_v9", pilot_spec_path="fork.yaml")
    with pytest.raises(PilotResolutionError, match="player_spec_requires_parent"):
        registry.resolve(loadout, base_dir=tmp_path)


@pytest.mark.unit
def test_relative_pilot_spec_path_without_base_dir_raises(
    registry: PilotSpecRegistry,
) -> None:
    # Fail fast: a relative path is meaningless without the loadout's directory.
    loadout = _loadout_with("pilot.player.hot_v9", pilot_spec_path="fork.yaml")
    with pytest.raises(PilotResolutionError, match="base_dir"):
        registry.resolve(loadout)


# ---------------------------------------------------------------------------
# Archetype fallback (resolution step 3) — characterization parity
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("loadout_yaml", "archetype"), sorted(_CHARACTERIZATION.items()))
def test_archetype_fallback_reproduces_mvp_mapping(
    registry: PilotSpecRegistry, loadout_yaml: str, archetype: str
) -> None:
    raw = _load_loadout_dict(loadout_yaml)
    loadout = ModelSOLoadout.model_validate(raw)
    spec = registry.resolve(loadout)
    assert spec.id == f"pilot.template.{archetype}"
    assert spec.archetype == archetype


@pytest.mark.unit
def test_archetype_fallback_unknown_pilot_id_raises(registry: PilotSpecRegistry) -> None:
    # Characterization: the MVP raised ValueError("unknown pilot archetype in
    # pilot_id ...").  PilotResolutionError subclasses ValueError, preserving
    # the contract for callers that caught the MVP error.
    loadout = _loadout_with("pilot.proof.mystery_v1")
    with pytest.raises(ValueError, match="unknown pilot archetype"):
        registry.resolve(loadout)


@pytest.mark.unit
def test_archetype_fallback_substring_order_is_aggressive_first(
    registry: PilotSpecRegistry,
) -> None:
    # The MVP checked substrings in the order aggressive -> defensive ->
    # predictive; an id naming two archetypes resolves to the first.
    loadout = _loadout_with("pilot.weird.defensive_aggressive_v1")
    assert registry.resolve(loadout).id == "pilot.template.aggressive"


# ---------------------------------------------------------------------------
# Existing loadout YAMLs are untouched by the new optional field
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_existing_loadouts_validate_unchanged(registry: PilotSpecRegistry) -> None:
    yaml_paths = sorted(_LOADOUTS_DIR.glob("*.yaml"))
    assert len(yaml_paths) >= 7  # 4 PoL + 2 examples + the tuned fork loadout
    for path in yaml_paths:
        loadout = ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        assert loadout.pilot_spec_path is None  # no shipped YAML uses the field
        spec = registry.resolve(loadout, base_dir=path.parent)
        assert isinstance(spec, ModelSOPilotSpec)
