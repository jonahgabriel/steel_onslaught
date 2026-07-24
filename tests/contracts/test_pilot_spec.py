"""Tests for ModelSOPilotSpec + bounded archetype parameter models — tunable-pilots Task 1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.pilot import (
    ModelSOLlmPilotParams,
    ModelSOPilotSpec,
    SOWeaponPreference,
)

PILOTS_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "pilots"
DEFENSIVE_GOLDEN = Path(__file__).parent.parent / "pilots" / "golden" / "defensive_golden.json"

TEMPLATE_FILES = [
    "template_aggressive.yaml",
    "template_defensive.yaml",
    "template_predictive.yaml",
]

TEMPLATE_IDS = {
    "pilot.template.aggressive",
    "pilot.template.defensive",
    "pilot.template.predictive",
    "pilot.template.llm",
}


def _load(filename: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((PILOTS_DATA / filename).read_text())
    return data


def _aggressive_spec_dict(**overrides: Any) -> dict[str, Any]:
    """A valid aggressive spec dict; keyword overrides patch top-level keys."""
    spec: dict[str, Any] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.pilot",
        "id": "pilot.test.aggressive",
        "display_name": "Test Aggressive",
        "archetype": "aggressive",
        "lineage": {"parent": "pilot.template.aggressive"},
        "parameters": {
            "vent_at_heat_margin": 5,
            "idle_vent_heat_threshold": 90,
            "mode_switch_pressure_floor": 12,
            "mode_switch_heat_ceiling": 80,
            "weapon_preference": "highest_damage",
        },
    }
    spec.update(overrides)
    return spec


def _human_spec_dict(**overrides: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "schema_version": "0.2.0",
        "kind": "steel_onslaught.pilot",
        "id": "pilot.human.browser",
        "display_name": "Browser Human",
        "archetype": "human",
        "lineage": {"parent": None},
        "parameters": {"input_source": "browser_command"},
    }
    spec.update(overrides)
    return spec


@pytest.mark.unit
def test_human_pilot_is_a_first_class_closed_typed_spec() -> None:
    spec = ModelSOPilotSpec.model_validate(_human_spec_dict())

    assert spec.archetype == "human"
    assert spec.parameters.input_source == "browser_command"  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(
            _human_spec_dict(parameters={"input_source": "llm_completion"})
        )
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(
            _human_spec_dict(parameters={"input_source": "browser_command", "model": None})
        )


@pytest.mark.unit
def test_human_capability_requires_bumped_schema_without_relabeling_legacy_specs() -> None:
    with pytest.raises(ValidationError, match=r"expected '0\.2\.0'"):
        ModelSOPilotSpec.model_validate(_human_spec_dict(schema_version="0.1.0"))
    with pytest.raises(ValidationError, match=r"expected '0\.1\.0'"):
        ModelSOPilotSpec.model_validate(_aggressive_spec_dict(schema_version="0.2.0"))


def _defensive_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "vent_headroom_below_redline": 8,
        "fire_confidence_floor": 0.7,
        "fire_heat_headroom": 12,
        "disengage_hp_pct": 30,
    }
    params.update(overrides)
    return params


def _predictive_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "lock_confidence_floor": 0.65,
        "predicted_hit_floor": 0.55,
        "preemptive_vent_headroom": 5,
        "regen_pressure_floor": 30,
    }
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# Template YAML loading + round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("filename", TEMPLATE_FILES)
def test_template_yaml_validates(filename: str) -> None:
    spec = ModelSOPilotSpec.model_validate(_load(filename))
    assert spec.id in TEMPLATE_IDS


@pytest.mark.unit
@pytest.mark.parametrize("filename", TEMPLATE_FILES)
def test_template_yaml_round_trips_losslessly(filename: str) -> None:
    data = _load(filename)
    spec = ModelSOPilotSpec.model_validate(data)
    # model_dump round-trip is lossless: revalidating the dump yields an equal model,
    # and the JSON-mode dump is exactly the YAML content.
    assert ModelSOPilotSpec.model_validate(spec.model_dump()) == spec
    assert spec.model_dump(mode="json") == data


# ---------------------------------------------------------------------------
# Template values — exactly the MVP hardcoded constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_template_aggressive_values() -> None:
    spec = ModelSOPilotSpec.model_validate(_load("template_aggressive.yaml"))
    assert spec.id == "pilot.template.aggressive"
    params = spec.parameters
    assert params.vent_at_heat_margin == 5  # type: ignore[union-attr]
    assert params.idle_vent_heat_threshold == 90  # type: ignore[union-attr]
    assert params.mode_switch_pressure_floor == 12  # type: ignore[union-attr]
    assert params.mode_switch_heat_ceiling == 80  # type: ignore[union-attr]
    assert params.weapon_preference == SOWeaponPreference.HIGHEST_DAMAGE  # type: ignore[union-attr]


@pytest.mark.unit
def test_template_predictive_values() -> None:
    spec = ModelSOPilotSpec.model_validate(_load("template_predictive.yaml"))
    assert spec.id == "pilot.template.predictive"
    assert spec.parameters.lock_confidence_floor == 0.65  # type: ignore[union-attr]
    assert spec.parameters.predicted_hit_floor == 0.55  # type: ignore[union-attr]


@pytest.mark.unit
def test_template_defensive_fire_confidence_floor_matches_landed_constant() -> None:
    """The template carries the pre-refactor defensive.py constant verbatim.

    Post-refactor, defensive.py no longer exports the literal — the frozen
    golden fixture metadata (generated against the hardcoded pilot at commit
    748d499) is the non-circular source of the landed constant.
    """
    spec = ModelSOPilotSpec.model_validate(_load("template_defensive.yaml"))
    assert spec.id == "pilot.template.defensive"
    golden_meta = json.loads(DEFENSIVE_GOLDEN.read_text())["_meta"]["constants"]
    assert spec.parameters.fire_confidence_floor == golden_meta["HIGH_CONFIDENCE_THRESHOLD"]  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Bounds enforcement
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("value", [1, 21])
def test_aggressive_vent_at_heat_margin_out_of_bounds_rejected(value: int) -> None:
    spec = _aggressive_spec_dict()
    spec["parameters"]["vent_at_heat_margin"] = value
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(spec)


@pytest.mark.unit
def test_defensive_fire_confidence_floor_below_bound_rejected() -> None:
    spec = _aggressive_spec_dict(
        id="pilot.test.defensive",
        archetype="defensive",
        lineage={"parent": "pilot.template.defensive"},
        parameters=_defensive_params(fire_confidence_floor=0.3),
    )
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(spec)


@pytest.mark.unit
def test_predictive_lock_confidence_floor_above_bound_rejected() -> None:
    spec = _aggressive_spec_dict(
        id="pilot.test.predictive",
        archetype="predictive",
        lineage={"parent": "pilot.template.predictive"},
        parameters=_predictive_params(lock_confidence_floor=0.96),
    )
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(spec)


# ---------------------------------------------------------------------------
# Cross-field and shape validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unknown_archetype_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(_aggressive_spec_dict(archetype="opportunistic"))


@pytest.mark.unit
def test_mismatched_parameters_rejected() -> None:
    # archetype: aggressive carrying defensive parameter fields must not validate.
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(_aggressive_spec_dict(parameters=_defensive_params()))


@pytest.mark.unit
def test_self_parent_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(
            _aggressive_spec_dict(id="pilot.x.y", lineage={"parent": "pilot.x.y"})
        )


@pytest.mark.unit
def test_unknown_parameter_field_rejected() -> None:
    spec = _aggressive_spec_dict()
    params = spec["parameters"]
    del params["vent_at_heat_margin"]
    params["vent_at_heat_margn"] = 5  # typo — extra="forbid" must reject it
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(spec)


@pytest.mark.unit
@pytest.mark.parametrize("bad_id", ["pilot.UPPER.case", "pilot.only_two"])
def test_bad_id_shape_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(_aggressive_spec_dict(id=bad_id))


@pytest.mark.unit
def test_bad_parent_shape_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelSOPilotSpec.model_validate(_aggressive_spec_dict(lineage={"parent": "not_a_pilot_id"}))


# ---------------------------------------------------------------------------
# Null-parent census (addendum §8): templates are the ONLY null-parent specs
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# LLM archetype: ``programming_guidance`` (2026-07-24 prompt-arms ARM G)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_llm_pilot_params_programming_guidance_defaults_to_none() -> None:
    """Every existing pilot spec (no ``programming_guidance`` authored) is unaffected."""
    params = ModelSOLlmPilotParams(persona="berserker", provider="qwen35")
    assert params.programming_guidance is None


@pytest.mark.unit
def test_llm_pilot_params_accepts_authored_programming_guidance() -> None:
    params = ModelSOLlmPilotParams(
        persona="berserker",
        provider="qwen35",
        programming_guidance="BRAWLER SEAT TACTICAL GUIDANCE: prefer flanking.",
    )
    assert params.programming_guidance == "BRAWLER SEAT TACTICAL GUIDANCE: prefer flanking."


@pytest.mark.unit
def test_llm_pilot_params_rejects_blank_programming_guidance() -> None:
    with pytest.raises(ValidationError):
        ModelSOLlmPilotParams(persona="berserker", provider="qwen35", programming_guidance="")


@pytest.mark.unit
def test_null_parent_census() -> None:
    yaml_paths = sorted(PILOTS_DATA.glob("*.yaml"))
    assert yaml_paths, "contracts_data/pilots/ must contain the template specs"
    for path in yaml_paths:
        spec = ModelSOPilotSpec.model_validate(yaml.safe_load(path.read_text()))
        if spec.lineage.parent is None:
            assert spec.id in TEMPLATE_IDS, (
                f"{path.name}: null lineage.parent is only permitted for the "
                f"pilot.template.* specs, got {spec.id}"
            )
