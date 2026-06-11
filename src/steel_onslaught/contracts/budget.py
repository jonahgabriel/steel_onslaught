"""Multi-axis loadout budget validator — Task 13.

``validate_loadout_budgets`` computes every budget axis and returns one
``BudgetViolation`` per exceeded axis (multi-violation, never first-fail):

- ``mass_used``             = sum of module masses; violation if > chassis max_mass
- ``slots_used``            = sum of module slot counts; violation if > max_module_slots
- ``pressure_steady_state`` = sum of module pressure draws; violation if
  > boiler.pressure_capacity * 0.7 (over 70% leaves no combat headroom)
- ``expected_heat_peak``    = max total module heat output in any single mode (computed)
- ``expected_signature``    = chassis base_signature + peak mode-active signature impact
  (computed)

Module category specs (weapons, sensors, gizmos) expose their costs under
different field names, so callers normalize each fielded module into a
``ModelSOModuleBudget`` before validation.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout

# Steady-state pressure draw above this fraction of boiler capacity leaves no
# headroom for weapons fire or mode switches and is rejected outright.
PRESSURE_HEADROOM_FRACTION = 0.7


class EnumBudgetViolationKind(StrEnum):
    """Budget axes that can hard-reject a loadout."""

    MASS = "mass"
    SLOTS = "slots"
    PRESSURE = "pressure"


class BudgetViolation(BaseModel):
    """One exceeded budget axis: the amount used and the maximum allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EnumBudgetViolationKind
    used: float
    max: float


class ModelSOModuleBudget(BaseModel):
    """Per-module budget contributions, normalized from the module's spec."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module_id: str = Field(min_length=1)
    mass: int = Field(ge=0, description="Mass units consumed in the loadout budget.")
    slots: int = Field(ge=0, description="Module slot count consumed.")
    pressure_draw: float = Field(
        ge=0.0, description="Steady-state boiler pressure drawn per tick while active."
    )
    heat_output: float = Field(ge=0.0, description="Heat output per tick while active.")
    signature_impact: float = Field(
        ge=0.0, description="Additive signature contribution while active."
    )
    active_modes: tuple[str, ...] = Field(
        min_length=1,
        description="Mode names in which this module is active (e.g. 'assault', 'recon').",
    )


class ModelSOBudgetUsage(BaseModel):
    """Computed budget usage across all five axes for a set of fielded modules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mass_used: int = Field(ge=0)
    slots_used: int = Field(ge=0)
    pressure_steady_state: float = Field(ge=0.0)
    expected_heat_peak: float = Field(ge=0.0)
    expected_signature: float = Field(ge=0.0)


def compute_loadout_budget_usage(
    chassis: ModelSOChassisSpec,
    modules: Sequence[ModelSOModuleBudget],
) -> ModelSOBudgetUsage:
    """Compute budget usage for the given modules on the given chassis.

    Heat peak and signature are mode-aware: for each mode named by any module,
    only modules active in that mode contribute, and the worst (peak) mode wins.
    """
    all_modes = sorted({mode for module in modules for mode in module.active_modes})

    heat_by_mode = [
        sum(m.heat_output for m in modules if mode in m.active_modes) for mode in all_modes
    ]
    signature_by_mode = [
        chassis.constraints.base_signature
        + sum(m.signature_impact for m in modules if mode in m.active_modes)
        for mode in all_modes
    ]

    return ModelSOBudgetUsage(
        mass_used=sum(m.mass for m in modules),
        slots_used=sum(m.slots for m in modules),
        pressure_steady_state=sum(m.pressure_draw for m in modules),
        expected_heat_peak=max(heat_by_mode, default=0.0),
        expected_signature=max(
            signature_by_mode, default=float(chassis.constraints.base_signature)
        ),
    )


def validate_loadout_budgets(
    loadout: ModelSOLoadout,
    chassis: ModelSOChassisSpec,
    boiler: ModelSOBoilerSpec,
    modules: Sequence[ModelSOModuleBudget],
) -> list[BudgetViolation]:
    """Validate every budget axis for a loadout; return ALL violations found.

    ``modules`` must contain exactly one budget entry per module id declared in
    ``loadout.modules`` — a missing, extra, or duplicated entry is a caller
    programming error and raises ``ValueError`` (fail fast, never silently skip).
    """
    provided_ids = [m.module_id for m in modules]
    duplicates = sorted({mid for mid in provided_ids if provided_ids.count(mid) > 1})
    if duplicates:
        raise ValueError(f"duplicate module budget entries: {duplicates}")

    declared = set(loadout.modules.all_module_ids())
    provided = set(provided_ids)
    if declared != provided:
        missing = sorted(declared - provided)
        extra = sorted(provided - declared)
        raise ValueError(
            f"module budgets do not match loadout {loadout.id!r}: "
            f"missing budgets for {missing}, undeclared budgets for {extra}"
        )

    usage = compute_loadout_budget_usage(chassis, modules)
    pressure_cap = boiler.pressure_capacity * PRESSURE_HEADROOM_FRACTION

    violations: list[BudgetViolation] = []
    if usage.mass_used > chassis.constraints.max_mass:
        violations.append(
            BudgetViolation(
                kind=EnumBudgetViolationKind.MASS,
                used=usage.mass_used,
                max=chassis.constraints.max_mass,
            )
        )
    if usage.slots_used > chassis.constraints.max_module_slots:
        violations.append(
            BudgetViolation(
                kind=EnumBudgetViolationKind.SLOTS,
                used=usage.slots_used,
                max=chassis.constraints.max_module_slots,
            )
        )
    if usage.pressure_steady_state > pressure_cap:
        violations.append(
            BudgetViolation(
                kind=EnumBudgetViolationKind.PRESSURE,
                used=usage.pressure_steady_state,
                max=pressure_cap,
            )
        )
    return violations
