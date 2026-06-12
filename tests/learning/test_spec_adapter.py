"""Tests for learning/spec_adapter.py — Task 1 of the Phase 2 plan.

Invariants per 2026-06-11-learning-loop-phase2-plan.md Task 1:

1. bounds_for_archetype reproduces constraints from model_fields metadata (no retyped literals).
   Spot-pins: aggressive vent_at_heat_margin (2,20,1); predictive lock_confidence_floor
   (0.3,0.95,0.05); aggressive weapon_preference choices (highest_damage, lowest_heat).

2. FLOAT_STEPS completeness in both directions.

3. Every numeric bound's minimum/maximum lie on its own step lattice.

4. params_from_spec yields native types (int, float, str) and spec_hash is stable.

5. Round-trip identity in both directions.

6. spec_from_params raises ValidationError on out-of-bounds or wrong-archetype field set.

7. PilotSpecView satisfies SpecLike structurally (mypy-enforced) and bounds validate.

8. Template-spec lattices are searchable: random_restart and hill_climb_neighbors succeed
   for all three archetypes.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: load template specs from YAML on disk
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.pilot import (
    ModelSOAggressivePilotParams,
    ModelSODefensivePilotParams,
    ModelSOPilotSpec,
    ModelSOPredictivePilotParams,
)
from steel_onslaught.contracts.pilot_registry import load_pilot_spec
from steel_onslaught.learning.protocols import (
    ModelSOCategoricalBound,
    ModelSONumericBound,
    SpecLike,
)
from steel_onslaught.learning.search import hill_climb_neighbors, lattice_values, random_restart
from steel_onslaught.learning.spec_adapter import (
    FLOAT_STEPS,
    PilotSpecView,
    bounds_for_archetype,
    params_from_spec,
    spec_from_params,
)

_CONTRACTS_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "pilots"


@pytest.fixture
def aggressive_template() -> ModelSOPilotSpec:
    return load_pilot_spec(_CONTRACTS_DATA / "template_aggressive.yaml")


@pytest.fixture
def defensive_template() -> ModelSOPilotSpec:
    return load_pilot_spec(_CONTRACTS_DATA / "template_defensive.yaml")


@pytest.fixture
def predictive_template() -> ModelSOPilotSpec:
    return load_pilot_spec(_CONTRACTS_DATA / "template_predictive.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# 1. bounds_for_archetype — derived from model_fields, never retyped literals
# ─────────────────────────────────────────────────────────────────────────────


_ParamModelType = (
    type[ModelSOAggressivePilotParams]
    | type[ModelSODefensivePilotParams]
    | type[ModelSOPredictivePilotParams]
)
ARCHETYPE_PARAM_MODELS: dict[str, _ParamModelType] = {
    "aggressive": ModelSOAggressivePilotParams,
    "defensive": ModelSODefensivePilotParams,
    "predictive": ModelSOPredictivePilotParams,
}


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_bounds_derived_from_model_fields_metadata(archetype: str) -> None:
    """bounds_for_archetype must match the ge/le/StrEnum metadata on each model."""
    import typing
    from enum import EnumMeta

    bounds = bounds_for_archetype(archetype)
    param_model = ARCHETYPE_PARAM_MODELS[archetype]
    # Use get_type_hints to resolve string annotations (pilot.py uses future annotations)
    resolved_hints = typing.get_type_hints(param_model)

    for field_name, field_info in param_model.model_fields.items():
        assert field_name in bounds, f"field {field_name!r} missing from bounds"
        bound = bounds[field_name]
        resolved_type = resolved_hints[field_name]

        if isinstance(bound, ModelSOCategoricalBound):
            # Must be a StrEnum field
            assert isinstance(resolved_type, EnumMeta), (
                f"{field_name}: got CategoricalBound but resolved type is not EnumMeta"
            )
        else:
            assert isinstance(bound, ModelSONumericBound), (
                f"{field_name}: expected NumericBound, got {type(bound)}"
            )
            # Verify ge/le from metadata
            metadata = field_info.metadata
            ge_vals = [m.ge for m in metadata if hasattr(m, "ge") and m.ge is not None]
            le_vals = [m.le for m in metadata if hasattr(m, "le") and m.le is not None]
            if ge_vals:
                assert abs(bound.minimum - ge_vals[0]) < 1e-9, (
                    f"{field_name}: minimum {bound.minimum} != ge {ge_vals[0]}"
                )
            if le_vals:
                assert abs(bound.maximum - le_vals[0]) < 1e-9, (
                    f"{field_name}: maximum {bound.maximum} != le {le_vals[0]}"
                )


@pytest.mark.unit
def test_bounds_spot_pin_aggressive_vent_at_heat_margin() -> None:
    """Spot-pin: aggressive vent_at_heat_margin -> NumericBound(2, 20, 1)."""
    bounds = bounds_for_archetype("aggressive")
    bound = bounds["vent_at_heat_margin"]
    assert isinstance(bound, ModelSONumericBound)
    assert bound.minimum == 2
    assert bound.maximum == 20
    assert bound.step == 1


@pytest.mark.unit
def test_bounds_spot_pin_predictive_lock_confidence_floor() -> None:
    """Spot-pin: predictive lock_confidence_floor -> NumericBound(0.3, 0.95, 0.05)."""
    bounds = bounds_for_archetype("predictive")
    bound = bounds["lock_confidence_floor"]
    assert isinstance(bound, ModelSONumericBound)
    assert abs(bound.minimum - 0.3) < 1e-9
    assert abs(bound.maximum - 0.95) < 1e-9
    assert abs(bound.step - 0.05) < 1e-9


@pytest.mark.unit
def test_bounds_spot_pin_aggressive_weapon_preference_choices() -> None:
    """Spot-pin: aggressive weapon_preference -> choices (highest_damage, lowest_heat)."""
    bounds = bounds_for_archetype("aggressive")
    bound = bounds["weapon_preference"]
    assert isinstance(bound, ModelSOCategoricalBound)
    assert bound.choices == ("highest_damage", "lowest_heat")


@pytest.mark.unit
def test_bounds_for_unknown_archetype_raises() -> None:
    with pytest.raises(ValueError, match="unknown archetype"):
        bounds_for_archetype("bogus")


# ─────────────────────────────────────────────────────────────────────────────
# 2. FLOAT_STEPS completeness — both directions
# ─────────────────────────────────────────────────────────────────────────────


def _all_float_param_fields() -> set[str]:
    """Return the set of float-typed parameter field names across all three archetypes.

    Uses typing.get_type_hints() to resolve string annotations from pilot.py's
    `from __future__ import annotations`.
    """
    import typing

    result: set[str] = set()
    for param_model in ARCHETYPE_PARAM_MODELS.values():
        resolved = typing.get_type_hints(param_model)
        for field_name in param_model.model_fields:
            if resolved[field_name] is float:
                result.add(field_name)
    return result


@pytest.mark.unit
def test_float_steps_completeness_every_float_field_has_entry() -> None:
    """Every float-typed parameter field across all three models has an entry."""
    all_float_fields = _all_float_param_fields()
    missing = all_float_fields - set(FLOAT_STEPS.keys())
    assert not missing, f"FLOAT_STEPS missing entries for float fields: {missing}"


@pytest.mark.unit
def test_float_steps_no_spurious_entries() -> None:
    """Every FLOAT_STEPS entry names an actual float-typed field (no drift)."""
    all_float_fields = _all_float_param_fields()
    spurious = set(FLOAT_STEPS.keys()) - all_float_fields
    assert not spurious, f"FLOAT_STEPS has entries for non-float fields: {spurious}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Every numeric bound's minimum/maximum lie on its own step lattice
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_bounds_lattice_contains_min_and_max(archetype: str) -> None:
    """Bounds minimum and maximum must be lattice members (hill-climb can reach them)."""
    bounds = bounds_for_archetype(archetype)
    for field_name, bound in bounds.items():
        if isinstance(bound, ModelSONumericBound):
            lattice = lattice_values(bound)
            lattice_floats = [float(v) for v in lattice]
            assert any(abs(float(bound.minimum) - v) < 1e-9 for v in lattice_floats), (
                f"{archetype}.{field_name}: minimum {bound.minimum} not in lattice {lattice}"
            )
            assert any(abs(float(bound.maximum) - v) < 1e-9 for v in lattice_floats), (
                f"{archetype}.{field_name}: maximum {bound.maximum} not in lattice {lattice}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. params_from_spec native types + spec_hash stability
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_params_from_spec_native_types_aggressive(aggressive_template: ModelSOPilotSpec) -> None:
    """int fields yield int, float fields yield float, StrEnum fields yield str."""
    params = params_from_spec(aggressive_template)

    # int fields
    assert type(params["vent_at_heat_margin"]) is int
    assert type(params["idle_vent_heat_threshold"]) is int
    assert type(params["mode_switch_pressure_floor"]) is int
    assert type(params["mode_switch_heat_ceiling"]) is int
    # StrEnum -> str
    assert type(params["weapon_preference"]) is str


@pytest.mark.unit
def test_params_from_spec_native_types_defensive(defensive_template: ModelSOPilotSpec) -> None:
    params = params_from_spec(defensive_template)

    assert type(params["vent_headroom_below_redline"]) is int
    assert type(params["fire_confidence_floor"]) is float
    assert type(params["fire_heat_headroom"]) is int
    assert type(params["disengage_hp_pct"]) is int


@pytest.mark.unit
def test_params_from_spec_native_types_predictive(predictive_template: ModelSOPilotSpec) -> None:
    params = params_from_spec(predictive_template)

    assert type(params["lock_confidence_floor"]) is float
    assert type(params["predicted_hit_floor"]) is float
    assert type(params["preemptive_vent_headroom"]) is int
    assert type(params["regen_pressure_floor"]) is int


@pytest.mark.unit
def test_params_from_spec_spec_hash_stable(aggressive_template: ModelSOPilotSpec) -> None:
    """spec_hash(archetype, params_from_spec(spec)) is stable across two calls."""
    params1 = params_from_spec(aggressive_template)
    params2 = params_from_spec(aggressive_template)
    h1 = spec_hash(aggressive_template.archetype, params1)
    h2 = spec_hash(aggressive_template.archetype, params2)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


# ─────────────────────────────────────────────────────────────────────────────
# 5. Round-trip identity
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_spec_from_params_round_trip_from_template(
    archetype: str,
    aggressive_template: ModelSOPilotSpec,
    defensive_template: ModelSOPilotSpec,
    predictive_template: ModelSOPilotSpec,
) -> None:
    """spec_from_params(params_from_spec(spec), ...) reproduces equal parameters."""
    template = {
        "aggressive": aggressive_template,
        "defensive": defensive_template,
        "predictive": predictive_template,
    }[archetype]

    original_params = params_from_spec(template)
    rebuilt_spec = spec_from_params(
        archetype=archetype,
        params=original_params,
        spec_id=f"pilot.learn.rebuilt_{archetype}",
        parent_id="pilot.template." + archetype,
        display_name=f"Rebuilt {archetype}",
    )
    rebuilt_params = params_from_spec(rebuilt_spec)
    assert rebuilt_params == original_params, (
        f"{archetype}: round-trip params differ: {rebuilt_params} != {original_params}"
    )
    assert rebuilt_spec.parameters == template.parameters


@pytest.mark.unit
@pytest.mark.parametrize(
    "archetype,params",
    [
        (
            "aggressive",
            {
                "vent_at_heat_margin": 3,
                "idle_vent_heat_threshold": 75,
                "mode_switch_pressure_floor": 10,
                "mode_switch_heat_ceiling": 70,
                "weapon_preference": "lowest_heat",
            },
        ),
        (
            "defensive",
            {
                "vent_headroom_below_redline": 5,
                "fire_confidence_floor": 0.6,
                "fire_heat_headroom": 20,
                "disengage_hp_pct": 20,
            },
        ),
        (
            "predictive",
            {
                "lock_confidence_floor": 0.5,
                "predicted_hit_floor": 0.4,
                "preemptive_vent_headroom": 10,
                "regen_pressure_floor": 20,
            },
        ),
    ],
)
def test_params_from_spec_from_params_round_trip_synthetic(
    archetype: str, params: ParamDict
) -> None:
    """params_from_spec(spec_from_params(p)) == p for in-bounds synthetic ParamDict."""
    spec = spec_from_params(
        archetype=archetype,
        params=params,
        spec_id=f"pilot.learn.synth_{archetype}",
        parent_id="pilot.template." + archetype,
        display_name=f"Synth {archetype}",
    )
    recovered = params_from_spec(spec)
    assert recovered == params, f"Round-trip failed for {archetype}: {recovered} != {params}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. spec_from_params raises on out-of-bounds or wrong archetype
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_spec_from_params_out_of_bounds_raises() -> None:
    """vent_at_heat_margin=1 is below the ge=2 constraint."""
    bad_params: ParamDict = {
        "vent_at_heat_margin": 1,  # out of bounds: ge=2
        "idle_vent_heat_threshold": 90,
        "mode_switch_pressure_floor": 12,
        "mode_switch_heat_ceiling": 80,
        "weapon_preference": "highest_damage",
    }
    with pytest.raises(ValidationError):
        spec_from_params(
            archetype="aggressive",
            params=bad_params,
            spec_id="pilot.learn.bad_agg",
            parent_id="pilot.template.aggressive",
            display_name="Bad aggressive",
        )


@pytest.mark.unit
def test_spec_from_params_wrong_archetype_field_set_raises() -> None:
    """Predictive params passed with archetype='aggressive' must raise ValidationError."""
    wrong_params: ParamDict = {
        "lock_confidence_floor": 0.5,
        "predicted_hit_floor": 0.4,
        "preemptive_vent_headroom": 10,
        "regen_pressure_floor": 20,
    }
    with pytest.raises((ValidationError, ValueError)):
        spec_from_params(
            archetype="aggressive",
            params=wrong_params,
            spec_id="pilot.learn.wrong_agg",
            parent_id="pilot.template.aggressive",
            display_name="Wrong archetype",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. PilotSpecView satisfies SpecLike structurally
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pilot_spec_view_satisfies_spec_like(aggressive_template: ModelSOPilotSpec) -> None:
    """PilotSpecView must be assignable to SpecLike (structural)."""
    view = PilotSpecView(aggressive_template)
    # Runtime structural check (mypy --strict enforces statically)
    spec_like_var: SpecLike = view
    assert spec_like_var.archetype == "aggressive"
    assert isinstance(spec_like_var.parameters, dict)
    assert isinstance(spec_like_var.bounds, dict)


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_pilot_spec_view_bounds_validate_as_bound_models(
    archetype: str,
    aggressive_template: ModelSOPilotSpec,
    defensive_template: ModelSOPilotSpec,
    predictive_template: ModelSOPilotSpec,
) -> None:
    """PilotSpecView.bounds values must all be valid bound model instances."""
    template = {
        "aggressive": aggressive_template,
        "defensive": defensive_template,
        "predictive": predictive_template,
    }[archetype]
    view = PilotSpecView(template)
    for field_name, bound in view.bounds.items():
        assert isinstance(bound, (ModelSONumericBound, ModelSOCategoricalBound)), (
            f"{archetype}.{field_name}: bound {bound!r} is not a bound model"
        )


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_pilot_spec_view_archetype_property(
    archetype: str,
    aggressive_template: ModelSOPilotSpec,
    defensive_template: ModelSOPilotSpec,
    predictive_template: ModelSOPilotSpec,
) -> None:
    template = {
        "aggressive": aggressive_template,
        "defensive": defensive_template,
        "predictive": predictive_template,
    }[archetype]
    view = PilotSpecView(template)
    assert view.archetype == archetype


# ─────────────────────────────────────────────────────────────────────────────
# 8. Template-spec lattices are searchable
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_random_restart_succeeds_for_all_archetypes(
    archetype: str,
    aggressive_template: ModelSOPilotSpec,
    defensive_template: ModelSOPilotSpec,
    predictive_template: ModelSOPilotSpec,
) -> None:
    """random_restart with bounds_for_archetype must succeed for all archetypes."""
    bounds = bounds_for_archetype(archetype)
    result = random_restart(bounds, seed=42)
    assert isinstance(result, dict)
    assert set(result.keys()) == set(bounds.keys())


@pytest.mark.unit
@pytest.mark.parametrize("archetype", ["aggressive", "defensive", "predictive"])
def test_hill_climb_neighbors_succeeds_for_all_archetypes(
    archetype: str,
    aggressive_template: ModelSOPilotSpec,
    defensive_template: ModelSOPilotSpec,
    predictive_template: ModelSOPilotSpec,
) -> None:
    """hill_climb_neighbors on template params + bounds_for_archetype must succeed."""
    template = {
        "aggressive": aggressive_template,
        "defensive": defensive_template,
        "predictive": predictive_template,
    }[archetype]
    params = params_from_spec(template)
    bounds = bounds_for_archetype(archetype)
    neighbors = hill_climb_neighbors(params, bounds, 1)
    assert isinstance(neighbors, list)
    # At minimum there should be some neighbors (templates are not at extremes on all dims)
    assert len(neighbors) >= 1
