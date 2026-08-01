"""Chassis contract model — fields from design §9.4."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelSOChassisConstraints(BaseModel):
    """Hard numeric limits and base stats for a chassis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_mass: int = Field(gt=0, description="Maximum total loadout mass (kg equivalent).")
    max_module_slots: int = Field(gt=0, description="Total module slot count available.")
    max_boiler_volume: int = Field(gt=0, description="Max boiler volume this chassis accepts.")
    base_speed: int = Field(gt=0, description="Base movement speed (hexes/tick).")
    base_turn_rate: int = Field(gt=0, description="Base turning rate (degrees/tick, discretised).")
    base_signature: int = Field(gt=0, description="Passive sensor signature emitted at idle.")
    base_vent_rate: int = Field(gt=0, description="Passive heat venting per tick (baseline).")
    base_hp: int = Field(gt=0, description="Base hull hit points fielded at match start.")
    base_armor: int = Field(
        ge=0, description="Base armor capacity fielded at match start (armor_value's max)."
    )
    base_armor_regen: int = Field(
        ge=0, description="Armor regenerated per tick toward base_armor (degrading-armor model)."
    )


class ModelSOChassisCompatibility(BaseModel):
    """Lists of module/boiler/mobility class strings this chassis supports.

    Only ``weapon_classes`` is binding today.  The other two lists have no
    counterpart to compare against — nothing in the contract set declares a
    boiler class or a mobility class — so they are marked NON-BINDING at the
    declaration site rather than left to read as if they were enforced
    (OMN-15594 acceptance criterion 1).  ``tests/contracts/
    test_loadout_compatibility.py`` fails if a compatibility field is added
    without being classified either way.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    weapon_classes: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "BINDING (OMN-15594) — consumed by "
            "steel_onslaught.contracts.compatibility.validate_loadout_compatibility, "
            "which rejects a loadout fielding a weapon whose weapon_class is absent "
            "from this list with EnumCompatibilityViolationKind.CHASSIS_WEAPON_CLASS."
        ),
    )
    boiler_classes: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "NON-BINDING (OMN-15594) — declarative only. ModelSOBoilerSpec declares no "
            "boiler_class field, so there is no un-brittle value to test membership "
            "against (inferring the class from the boiler id is the substring "
            "inference WeaponDamageType's docstring rejects). The enforced "
            "boiler<->chassis direction is boiler.compatibility."
            "compatible_chassis_classes. Making this list binding requires first "
            "adding a declared class to the boiler contract."
        ),
    )
    mobility_classes: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "NON-BINDING (OMN-15594) — declarative only. No mobility module contract "
            "exists under contracts_data/ and no loadout can field one, so there is "
            "nothing for this list to accept or reject."
        ),
    )


class ModelSOChassisPenalties(BaseModel):
    """Multiplicative penalties applied to this chassis in specific conditions.

    All values must be >= 1.0 — a penalty of exactly 1.0 is neutral (no effect).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode_switch_latency_modifier: float = Field(
        ge=1.0,
        description="Multiplier applied to mode transition tick cost.",
    )
    sensor_lock_penalty: float = Field(
        ge=1.0,
        description="Multiplier applied to sensor lock time when this chassis is the target.",
    )
    heat_weapon_vulnerability: float = Field(
        ge=1.0,
        description="Multiplier applied to heat damage taken from heat-based weapons.",
    )


_ID_PATTERN = re.compile(r"^chassis\.(light|medium|heavy)\.[a-z0-9_]+$")


class ModelSOChassisSpec(BaseModel):
    """Contract spec for a Steel Onslaught chassis — the structural frame of a mech."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.chassis"] = "steel_onslaught.chassis"
    id: str = Field(
        description="Unique chassis id matching ^chassis.(light|medium|heavy).[a-z0-9_]+$"
    )
    display_name: str
    chassis_class: Literal["light", "medium", "heavy"]
    constraints: ModelSOChassisConstraints
    compatibility: ModelSOChassisCompatibility
    penalties: ModelSOChassisPenalties

    @field_validator("id")
    @classmethod
    def _validate_id_pattern(cls, v: str) -> str:
        if not _ID_PATTERN.match(v):
            raise ValueError(
                f"chassis id {v!r} does not match required pattern "
                r"^chassis.(light|medium|heavy).[a-z0-9_]+$"
            )
        return v
