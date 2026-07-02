"""Weapon contract model — Task 9."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WeaponDamageType(StrEnum):
    """Damage type classification — drives armor effectiveness (Task 25).

    Declared on the weapon contract so each weapon names its damage type
    explicitly (rather than inferring it by substring of the id, which is
    brittle: a ``sheet_metal_cannon`` would wrongly read as heat).

    - STANDARD: baseline armor efficiency (1.0 multiplier).
    - HEAT:     armor is less effective (lower efficiency coefficient).
    - PRESSURE: armor is more effective (higher efficiency coefficient).
    """

    STANDARD = "standard"
    HEAT = "heat"
    PRESSURE = "pressure"


class ModelSOAccuracyPoint(BaseModel):
    """A single point on the accuracy curve: hit probability at a given range bin."""

    model_config = ConfigDict(frozen=True)

    range: int = Field(ge=0)
    hit_probability: float = Field(ge=0.0, le=1.0)


class ModelSOWeaponCompatibility(BaseModel):
    """Chassis classes that can mount this weapon."""

    model_config = ConfigDict(frozen=True)

    compatible_chassis_classes: list[str] = Field(min_length=1)


class ModelSOWeaponSpec(BaseModel):
    """Weapon specification — design §13.2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.weapon"] = "steel_onslaught.weapon"

    id: str
    display_name: str

    # Weapon class determines slot budget and chassis compatibility.
    weapon_class: Literal["light", "medium", "heavy", "siege"]

    # Combat stats — all non-negative.
    range: int = Field(ge=0)
    damage: int = Field(ge=0)
    pressure_cost: int = Field(ge=0)
    heat_generated: int = Field(ge=0)
    cooldown_ticks: int = Field(ge=0)

    # Accuracy at range bins; interpolated linearly by the combat resolver (Task 24).
    accuracy_curve: list[ModelSOAccuracyPoint] = Field(min_length=1)

    # Multiplier applied to base damage against each chassis class.
    target_class_effectiveness: dict[str, float]

    # Damage type used to resolve armor effectiveness on a hit (Task 25).
    # Defaults to STANDARD so existing weapons that omit the field behave
    # unchanged; declared explicitly per weapon rather than inferred by id.
    damage_type: WeaponDamageType = WeaponDamageType.STANDARD

    compatibility: ModelSOWeaponCompatibility
