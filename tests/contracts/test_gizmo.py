"""Tests for ModelSOGizmoSpec — invariants from Task 11."""

from __future__ import annotations

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.gizmo import GizmoCategory, ModelSOGizmoSpec


@pytest.mark.unit
def test_efficient_regulator_loads() -> None:
    """The efficient_regulator YAML validates without errors."""
    with open("contracts_data/gizmos/efficient_regulator.yaml") as f:
        data = yaml.safe_load(f)
    spec = ModelSOGizmoSpec.model_validate(data)
    assert spec.category == GizmoCategory.EFFICIENCY
    assert spec.id.startswith("gizmo.")


@pytest.mark.unit
def test_burst_amplifier_loads() -> None:
    """The burst_amplifier YAML validates without errors."""
    with open("contracts_data/gizmos/burst_amplifier.yaml") as f:
        data = yaml.safe_load(f)
    spec = ModelSOGizmoSpec.model_validate(data)
    assert spec.category == GizmoCategory.AMPLIFIER


@pytest.mark.unit
def test_targeting_assist_loads() -> None:
    """The targeting_assist YAML validates without errors."""
    with open("contracts_data/gizmos/targeting_assist.yaml") as f:
        data = yaml.safe_load(f)
    spec = ModelSOGizmoSpec.model_validate(data)
    assert spec.category == GizmoCategory.CONTROL


@pytest.mark.unit
def test_emergency_condenser_loads_and_matches_design() -> None:
    """The emergency_condenser matches design §14.3 exactly."""
    with open("contracts_data/gizmos/emergency_condenser.yaml") as f:
        data = yaml.safe_load(f)
    spec = ModelSOGizmoSpec.model_validate(data)

    assert spec.id == "gizmo.cooling.emergency_condenser"
    assert spec.display_name == "Emergency Condenser"
    assert spec.category == GizmoCategory.SAFETY
    assert spec.constraints["mass"] == 8
    assert spec.constraints["slots"] == 1
    assert spec.constraints["compatible_chassis"] == ("medium", "heavy")

    # effects.on_redline block from design §14.3
    on_redline = spec.effects["on_redline"]
    assert on_redline["vent_bonus"] == 12
    assert on_redline["duration_ticks"] == 2
    assert on_redline["pressure_cost"] == 18
    assert on_redline["cooldown_ticks"] == 25

    # tradeoffs block
    assert spec.tradeoffs["max_pressure_penalty"] == 5
    assert spec.tradeoffs["mode_switch_latency_delta"] == pytest.approx(0.1)

    # forbidden_stacking
    assert spec.forbidden_stacking == ("gizmo.cooling.pressure_dump_valve",)


@pytest.mark.unit
def test_forbidden_stacking_cannot_contain_own_id() -> None:
    """A gizmo that lists itself in forbidden_stacking is rejected."""
    with pytest.raises(ValueError, match="forbidden_stacking"):
        ModelSOGizmoSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.gizmo",
            id="gizmo.test.self_ref",
            display_name="Self Ref",
            category=GizmoCategory.SAFETY,
            constraints={"mass": 4, "slots": 1, "compatible_chassis": ["medium"]},
            effects={},
            tradeoffs={},
            forbidden_stacking=("gizmo.test.self_ref",),  # own id — must reject
        )


@pytest.mark.unit
def test_unknown_category_rejected() -> None:
    """A gizmo with a category not in the enum is rejected."""
    with pytest.raises(ValueError):
        ModelSOGizmoSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.gizmo",
            id="gizmo.test.bad_cat",
            display_name="Bad Cat",
            category="unknown_cat",  # type: ignore[arg-type]
            constraints={"mass": 4, "slots": 1, "compatible_chassis": ["medium"]},
            effects={},
            tradeoffs={},
            forbidden_stacking=(),
        )


@pytest.mark.unit
def test_all_four_specs_have_non_empty_id() -> None:
    """Each of the 4 YAML specs has a non-empty id."""
    spec_files = [
        "contracts_data/gizmos/efficient_regulator.yaml",
        "contracts_data/gizmos/burst_amplifier.yaml",
        "contracts_data/gizmos/targeting_assist.yaml",
        "contracts_data/gizmos/emergency_condenser.yaml",
    ]
    for path in spec_files:
        with open(path) as f:
            data = yaml.safe_load(f)
        spec = ModelSOGizmoSpec.model_validate(data)
        assert spec.id, f"id should be non-empty for {path}"


@pytest.mark.unit
def test_gizmo_schema_version_and_kind() -> None:
    """All 4 specs have the canonical schema_version and kind fields."""
    spec_files = [
        "contracts_data/gizmos/efficient_regulator.yaml",
        "contracts_data/gizmos/burst_amplifier.yaml",
        "contracts_data/gizmos/targeting_assist.yaml",
        "contracts_data/gizmos/emergency_condenser.yaml",
    ]
    for path in spec_files:
        with open(path) as f:
            data = yaml.safe_load(f)
        spec = ModelSOGizmoSpec.model_validate(data)
        assert spec.schema_version == "0.1.0", f"Bad schema_version in {path}"
        assert spec.kind == "steel_onslaught.gizmo", f"Bad kind in {path}"
