"""Tests for the multi-axis loadout budget validator — Task 13 invariants."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.budget import (
    PRESSURE_HEADROOM_FRACTION,
    BudgetViolation,
    EnumBudgetViolationKind,
    ModelSOModuleBudget,
    compute_loadout_budget_usage,
    validate_loadout_budgets,
)
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.loadout import (
    ModelSOLoadout,
    ModelSOLoadoutBudgets,
    ModelSOLoadoutModules,
)

_DATA = Path(__file__).parent.parent.parent / "contracts_data"


def _load_chassis(fname: str) -> ModelSOChassisSpec:
    raw = (_DATA / "chassis" / fname).read_text()
    return ModelSOChassisSpec.model_validate(yaml.safe_load(raw))


def _load_boiler(fname: str) -> ModelSOBoilerSpec:
    raw = (_DATA / "boilers" / fname).read_text()
    return ModelSOBoilerSpec.model_validate(yaml.safe_load(raw))


def _load_loadout(fname: str) -> ModelSOLoadout:
    raw = (_DATA / "loadouts" / fname).read_text()
    return ModelSOLoadout.model_validate(yaml.safe_load(raw))


def _make_loadout(module_ids: list[str], chassis_id: str, boiler_id: str) -> ModelSOLoadout:
    """Build a loadout declaring the given module ids (all as weapons for simplicity)."""
    return ModelSOLoadout(
        id="loadout.test.synthetic",
        chassis_id=chassis_id,
        boiler_id=boiler_id,
        pilot_id="pilot.test.synthetic_v1",
        modules=ModelSOLoadoutModules(weapons=module_ids),
        budgets=ModelSOLoadoutBudgets(
            points_used=0,
            points_max=100,
            mass_used=0,
            mass_max=1,
            slots_used=0,
            slots_max=1,
            expected_heat_peak=0,
            expected_signature=0,
        ),
    )


def _module(
    module_id: str,
    *,
    mass: int = 0,
    slots: int = 1,
    pressure_draw: float = 0.0,
    heat_output: float = 0.0,
    signature_impact: float = 0.0,
    active_modes: tuple[str, ...] = ("assault",),
) -> ModelSOModuleBudget:
    return ModelSOModuleBudget(
        module_id=module_id,
        mass=mass,
        slots=slots,
        pressure_draw=pressure_draw,
        heat_output=heat_output,
        signature_impact=signature_impact,
        active_modes=active_modes,
    )


def _aggressive_light_modules() -> list[ModelSOModuleBudget]:
    """Module budgets for the example_aggressive_light.yaml loadout."""
    return [
        _module(
            "weapon.light.machine_gun",
            mass=18,
            pressure_draw=4.0,
            heat_output=3.0,
            active_modes=("assault",),
        ),
        _module(
            "weapon.light.shrapnel_thrower",
            mass=12,
            pressure_draw=6.0,
            heat_output=5.0,
            active_modes=("assault",),
        ),
        _module(
            "sensor.short_range_scanner",
            mass=8,
            pressure_draw=2.0,
            heat_output=0.5,
            signature_impact=4.0,
            active_modes=("assault", "recon"),
        ),
        _module(
            "gizmo.control.targeting_assist",
            mass=3,
            pressure_draw=1.0,
            active_modes=("assault",),
        ),
    ]


# ---------------------------------------------------------------------------
# Invariant 1: a valid loadout passes all budgets
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_loadout_passes_all_budgets() -> None:
    loadout = _load_loadout("example_aggressive_light.yaml")
    chassis = _load_chassis("light_scout_mk1.yaml")
    boiler = _load_boiler("compact_v1.yaml")
    violations = validate_loadout_budgets(loadout, chassis, boiler, _aggressive_light_modules())
    assert violations == []


# ---------------------------------------------------------------------------
# Invariant 2: mass overflow returns BudgetViolation(kind="mass", used, max)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mass_overflow_returns_mass_violation() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")  # max_mass=60
    boiler = _load_boiler("compact_v1.yaml")
    loadout = _make_loadout(["weapon.test.anvil"], chassis.id, boiler.id)
    modules = [_module("weapon.test.anvil", mass=70)]

    violations = validate_loadout_budgets(loadout, chassis, boiler, modules)

    assert violations == [BudgetViolation.model_validate({"kind": "mass", "used": 70, "max": 60})]
    assert violations[0].kind is EnumBudgetViolationKind.MASS


# ---------------------------------------------------------------------------
# Invariant 3: 9 modules on an 8-slot chassis returns a slot violation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nine_modules_on_eight_slot_chassis_returns_slot_violation() -> None:
    chassis = _load_chassis("heavy_ironclad_mk1.yaml")  # max_module_slots=8
    assert chassis.constraints.max_module_slots == 8
    boiler = _load_boiler("industrial_bessemer_90.yaml")
    module_ids = [f"weapon.test.filler_{i}" for i in range(9)]
    loadout = _make_loadout(module_ids, chassis.id, boiler.id)
    modules = [_module(mid, slots=1) for mid in module_ids]

    violations = validate_loadout_budgets(loadout, chassis, boiler, modules)

    assert violations == [BudgetViolation.model_validate({"kind": "slots", "used": 9, "max": 8})]


# ---------------------------------------------------------------------------
# Invariant 4: multi-violation — 3 different overflows return 3 violations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_three_overflows_return_three_violations_not_first_fail() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")  # max_mass=60, max_module_slots=4
    boiler = _load_boiler("compact_v1.yaml")  # pressure_capacity=50 -> cap 35.0
    module_ids = [f"weapon.test.overload_{i}" for i in range(5)]
    loadout = _make_loadout(module_ids, chassis.id, boiler.id)
    modules = [_module(mid, mass=20, slots=1, pressure_draw=8.0) for mid in module_ids]

    violations = validate_loadout_budgets(loadout, chassis, boiler, modules)

    assert len(violations) == 3
    assert {v.kind for v in violations} == {
        EnumBudgetViolationKind.MASS,
        EnumBudgetViolationKind.SLOTS,
        EnumBudgetViolationKind.PRESSURE,
    }


# ---------------------------------------------------------------------------
# Pressure headroom: reject only above 70% of boiler pressure_capacity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pressure_at_exactly_seventy_percent_passes() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")
    boiler = _load_boiler("compact_v1.yaml")  # pressure_capacity=50
    cap = boiler.pressure_capacity * PRESSURE_HEADROOM_FRACTION
    loadout = _make_loadout(["sensor.test.at_cap"], chassis.id, boiler.id)
    modules = [_module("sensor.test.at_cap", pressure_draw=cap)]

    assert validate_loadout_budgets(loadout, chassis, boiler, modules) == []


@pytest.mark.unit
def test_pressure_above_seventy_percent_returns_pressure_violation() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")
    boiler = _load_boiler("compact_v1.yaml")  # pressure_capacity=50 -> cap 35.0
    loadout = _make_loadout(["sensor.test.greedy"], chassis.id, boiler.id)
    modules = [_module("sensor.test.greedy", pressure_draw=36.0)]

    violations = validate_loadout_budgets(loadout, chassis, boiler, modules)

    assert violations == [
        BudgetViolation(kind=EnumBudgetViolationKind.PRESSURE, used=36.0, max=35.0)
    ]


# ---------------------------------------------------------------------------
# Computed usage: heat peak and signature formulas
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expected_heat_peak_is_max_over_modes_not_total_sum() -> None:
    """Heat peak is the max over any single mode, not the sum across all modes."""
    chassis = _load_chassis("light_scout_mk1.yaml")
    modules = [
        _module("weapon.test.hot", heat_output=10.0, active_modes=("assault",)),
        _module("sensor.test.warm", heat_output=2.0, active_modes=("recon",)),
        _module("sensor.test.dual", heat_output=1.0, active_modes=("assault", "recon")),
    ]

    usage = compute_loadout_budget_usage(chassis, modules)

    # assault: 10 + 1 = 11; recon: 2 + 1 = 3 -> peak is 11, not 13.
    assert usage.expected_heat_peak == pytest.approx(11.0)


@pytest.mark.unit
def test_expected_signature_is_base_plus_peak_mode_active_impact() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")  # base_signature=30
    modules = [
        _module("sensor.test.loud", signature_impact=8.0, active_modes=("recon",)),
        _module("sensor.test.quiet", signature_impact=4.0, active_modes=("assault",)),
    ]

    usage = compute_loadout_budget_usage(chassis, modules)

    # recon: 30 + 8 = 38; assault: 30 + 4 = 34 -> expected signature is the peak.
    assert usage.expected_signature == pytest.approx(38.0)


@pytest.mark.unit
def test_empty_module_list_usage_is_chassis_baseline() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")

    usage = compute_loadout_budget_usage(chassis, [])

    assert usage.mass_used == 0
    assert usage.slots_used == 0
    assert usage.pressure_steady_state == pytest.approx(0.0)
    assert usage.expected_heat_peak == pytest.approx(0.0)
    assert usage.expected_signature == pytest.approx(float(chassis.constraints.base_signature))


# ---------------------------------------------------------------------------
# Fail-fast: declared module ids and provided budgets must match exactly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_missing_module_budget_raises() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")
    boiler = _load_boiler("compact_v1.yaml")
    loadout = _make_loadout(
        ["weapon.test.declared", "weapon.test.forgotten"], chassis.id, boiler.id
    )
    modules = [_module("weapon.test.declared")]  # forgot weapon.test.forgotten

    with pytest.raises(ValueError, match=r"weapon\.test\.forgotten"):
        validate_loadout_budgets(loadout, chassis, boiler, modules)


@pytest.mark.unit
def test_undeclared_module_budget_raises() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")
    boiler = _load_boiler("compact_v1.yaml")
    loadout = _make_loadout(["weapon.test.declared"], chassis.id, boiler.id)
    modules = [_module("weapon.test.declared"), _module("weapon.test.stowaway")]

    with pytest.raises(ValueError, match=r"weapon\.test\.stowaway"):
        validate_loadout_budgets(loadout, chassis, boiler, modules)


@pytest.mark.unit
def test_duplicate_module_budget_ids_raise() -> None:
    chassis = _load_chassis("light_scout_mk1.yaml")
    boiler = _load_boiler("compact_v1.yaml")
    loadout = _make_loadout(["weapon.test.twice"], chassis.id, boiler.id)
    modules = [_module("weapon.test.twice"), _module("weapon.test.twice")]

    with pytest.raises(ValueError, match="duplicate"):
        validate_loadout_budgets(loadout, chassis, boiler, modules)
