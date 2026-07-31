"""Loadout compatibility validator — OMN-15594.

Three contract fields declare class compatibility between the parts a loadout
fields.  Before this module they were declared and consumed by nothing, so a
loadout pairing a siege mortar with a light scout chassis assembled, ran, and
produced match evidence that looked legitimate:

- ``ModelSOWeaponCompatibility.compatible_chassis_classes``  (weapon → chassis)
- ``ModelSOChassisCompatibility.weapon_classes``             (chassis → weapon)
- ``ModelSOBoilerCompatibility.compatible_chassis_classes``  (boiler → chassis)

``validate_loadout_compatibility`` is the single consumer of all three.  It
mirrors ``validate_loadout_budgets``: it computes every direction and returns
one ``CompatibilityViolation`` per failed pairing — multi-violation, never
first-fail — so a caller reports the whole illegal loadout at once rather than
one axis per fix cycle.  ``_require_legal_loadout`` in ``match.runner`` turns a
non-empty result into a typed ``LoadoutCompatibilityError`` at match assembly,
which is fail-closed: there is no advisory mode and no per-loadout exemption.

Violation order is deterministic: weapons in the order the loadout declares
them (weapon→chassis before chassis→weapon for each weapon), then the boiler.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec


class EnumCompatibilityViolationKind(StrEnum):
    """Declared compatibility directions that can hard-reject a loadout.

    One member per declared contract field, so a violation names which
    declaration rejected the pairing rather than a generic "incompatible".
    """

    WEAPON_CHASSIS_CLASS = "weapon_chassis_class"
    CHASSIS_WEAPON_CLASS = "chassis_weapon_class"
    BOILER_CHASSIS_CLASS = "boiler_chassis_class"


class CompatibilityViolation(BaseModel):
    """One failed pairing: who declared the rule, who violated it, and how."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EnumCompatibilityViolationKind
    declaring_id: str = Field(
        min_length=1, description="Contract id whose declared compatibility list rejected."
    )
    offending_id: str = Field(
        min_length=1, description="Contract id of the counterpart that is not accepted."
    )
    declared: tuple[str, ...] = Field(
        min_length=1, description="The classes the declaring contract accepts."
    )
    actual: str = Field(min_length=1, description="The class the counterpart actually is.")

    def describe(self) -> str:
        """Stable one-line rendering used in the assembly-time error message."""
        return (
            f"{self.kind.value}: {self.declaring_id!r} accepts {list(self.declared)} "
            f"but {self.offending_id!r} is {self.actual!r}"
        )


class LoadoutCompatibilityError(ValueError):
    """A loadout fields a part pairing that a declared compatibility list rejects.

    Typed (not a bare ``ValueError``) so callers and tests can distinguish an
    illegal pairing from a budget overrun or an unknown contract id.
    """

    def __init__(self, loadout_id: str, violations: Sequence[CompatibilityViolation]) -> None:
        self.loadout_id = loadout_id
        self.violations = tuple(violations)
        details = "; ".join(violation.describe() for violation in self.violations)
        super().__init__(f"loadout {loadout_id!r} violates part compatibility: {details}")


def validate_loadout_compatibility(
    loadout: ModelSOLoadout,
    chassis: ModelSOChassisSpec,
    boiler: ModelSOBoilerSpec,
    weapons: Sequence[ModelSOWeaponSpec],
) -> list[CompatibilityViolation]:
    """Validate every declared compatibility direction; return ALL violations found.

    ``chassis`` and ``boiler`` must be the specs the loadout names, and
    ``weapons`` must contain exactly one spec per weapon id declared in
    ``loadout.modules.weapons`` — a mismatched, missing, extra, or duplicated
    spec is a caller programming error and raises ``ValueError`` (fail fast,
    never silently skip a pairing).
    """
    if chassis.id != loadout.chassis_id:
        raise ValueError(
            f"chassis spec {chassis.id!r} is not the chassis fielded by loadout "
            f"{loadout.id!r} ({loadout.chassis_id!r})"
        )
    if boiler.id != loadout.boiler_id:
        raise ValueError(
            f"boiler spec {boiler.id!r} is not the boiler fielded by loadout "
            f"{loadout.id!r} ({loadout.boiler_id!r})"
        )

    provided_ids = [weapon.id for weapon in weapons]
    duplicates = sorted({wid for wid in provided_ids if provided_ids.count(wid) > 1})
    if duplicates:
        raise ValueError(f"duplicate weapon specs supplied: {duplicates}")
    declared_ids = set(loadout.modules.weapons)
    if declared_ids != set(provided_ids):
        missing = sorted(declared_ids - set(provided_ids))
        extra = sorted(set(provided_ids) - declared_ids)
        raise ValueError(
            f"weapon specs do not match loadout {loadout.id!r}: "
            f"missing specs for {missing}, undeclared specs for {extra}"
        )

    by_id = {weapon.id: weapon for weapon in weapons}
    violations: list[CompatibilityViolation] = []

    for weapon_id in loadout.modules.weapons:
        weapon = by_id[weapon_id]
        if chassis.chassis_class not in weapon.compatibility.compatible_chassis_classes:
            violations.append(
                CompatibilityViolation(
                    kind=EnumCompatibilityViolationKind.WEAPON_CHASSIS_CLASS,
                    declaring_id=weapon.id,
                    offending_id=chassis.id,
                    declared=weapon.compatibility.compatible_chassis_classes,
                    actual=chassis.chassis_class,
                )
            )
        if weapon.weapon_class not in chassis.compatibility.weapon_classes:
            violations.append(
                CompatibilityViolation(
                    kind=EnumCompatibilityViolationKind.CHASSIS_WEAPON_CLASS,
                    declaring_id=chassis.id,
                    offending_id=weapon.id,
                    declared=chassis.compatibility.weapon_classes,
                    actual=weapon.weapon_class,
                )
            )

    if chassis.chassis_class not in boiler.compatibility.compatible_chassis_classes:
        violations.append(
            CompatibilityViolation(
                kind=EnumCompatibilityViolationKind.BOILER_CHASSIS_CLASS,
                declaring_id=boiler.id,
                offending_id=chassis.id,
                declared=boiler.compatibility.compatible_chassis_classes,
                actual=chassis.chassis_class,
            )
        )

    return violations
