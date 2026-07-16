"""Loadout contract model — Task 13 (design §15.3).

A loadout fields one chassis, one boiler, one pilot, and a constrained set of
modules grouped by category. The ``budgets`` block records the player-declared
budget usage; the authoritative check is ``validate_loadout_budgets`` in
``steel_onslaught.contracts.budget``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_LOADOUT_ID_PATTERN = re.compile(r"^loadout\.[a-z0-9_]+(\.[a-z0-9_]+)*$")


class ModelSOLoadoutModules(BaseModel):
    """Module ids fielded by a loadout, grouped by category — design §15.3.

    A module id may appear at most once across all categories: the same
    physical module cannot be fielded twice.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    weapons: tuple[str, ...] = ()
    sensors: tuple[str, ...] = ()
    cooling: tuple[str, ...] = ()
    armor: tuple[str, ...] = ()
    gizmos: tuple[str, ...] = ()

    def all_module_ids(self) -> tuple[str, ...]:
        """Every fielded module id, in category order (weapons first, gizmos last)."""
        return (*self.weapons, *self.sensors, *self.cooling, *self.armor, *self.gizmos)

    @model_validator(mode="after")
    def _no_duplicate_module_ids(self) -> ModelSOLoadoutModules:
        all_ids = self.all_module_ids()
        duplicates = sorted({mid for mid in all_ids if all_ids.count(mid) > 1})
        if duplicates:
            raise ValueError(f"duplicate module ids fielded in loadout: {duplicates}")
        return self


class ModelSOLoadoutBudgets(BaseModel):
    """Declared budget usage for a loadout — design §15.3 ``budgets`` block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    points_used: int = Field(ge=0)
    points_max: int = Field(gt=0)
    mass_used: int = Field(ge=0)
    mass_max: int = Field(gt=0)
    slots_used: int = Field(ge=0)
    slots_max: int = Field(gt=0)
    expected_heat_peak: int = Field(ge=0)
    expected_signature: int = Field(ge=0)


class ModelSOLoadout(BaseModel):
    """Contract spec for a fielded loadout — design §15.3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.loadout"] = "steel_onslaught.loadout"

    id: str = Field(description="Unique loadout id, e.g. loadout.example.aggressive_light")
    chassis_id: str = Field(pattern=r"^chassis\.")
    boiler_id: str = Field(pattern=r"^boiler\.")
    pilot_id: str = Field(pattern=r"^pilot\.")
    pilot_spec_path: str | None = Field(
        default=None,
        description=(
            "Optional player-supplied pilot spec YAML, resolved relative to the "
            "loadout file's directory (tunable-pilots addendum §7 rule 1). The "
            "spec's id must equal pilot_id and must name a non-null lineage.parent."
        ),
    )
    modules: ModelSOLoadoutModules
    budgets: ModelSOLoadoutBudgets

    @field_validator("id")
    @classmethod
    def _validate_id_pattern(cls, v: str) -> str:
        if not _LOADOUT_ID_PATTERN.match(v):
            raise ValueError(
                f"loadout id {v!r} does not match required pattern "
                r"^loadout.[a-z0-9_]+(.[a-z0-9_]+)*$"
            )
        return v
