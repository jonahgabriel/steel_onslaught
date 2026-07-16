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


class UnknownWeaponError(ValueError):
    """A referenced weapon id is absent from the injected contract catalog."""

    def __init__(self, weapon_id: str, *, owner_id: str) -> None:
        self.weapon_id = weapon_id
        self.owner_id = owner_id
        super().__init__(
            f"unknown_weapon_id: weapon {weapon_id!r} referenced by {owner_id!r} "
            "is absent from the injected weapon catalog"
        )


class ModelSOAccuracyPoint(BaseModel):
    """A single point on the accuracy curve: hit probability at a given range bin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    range: int = Field(ge=0)
    hit_probability: float = Field(ge=0.0, le=1.0)


class ModelSOWeaponCompatibility(BaseModel):
    """Chassis classes that can mount this weapon."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compatible_chassis_classes: tuple[str, ...] = Field(min_length=1)


class ModelSOTargetClassEffectiveness(BaseModel):
    """Closed, positive damage multipliers for every supported chassis class."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    light: float = Field(gt=0.0)
    medium: float = Field(gt=0.0)
    heavy: float = Field(gt=0.0)

    def __getitem__(self, chassis_class: Literal["light", "medium", "heavy"]) -> float:
        """Resolve a required multiplier without a permissive runtime fallback."""
        try:
            return float(getattr(self, chassis_class))
        except AttributeError as exc:
            # Validated instances always contain all three fields.  A KeyError
            # keeps corrupted/unvalidated runtime objects fail-closed too.
            raise KeyError(chassis_class) from exc


class ModelSOWeaponSpec(BaseModel):
    """Weapon specification — design §13.2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"]
    kind: Literal["steel_onslaught.weapon"]

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
    accuracy_curve: tuple[ModelSOAccuracyPoint, ...] = Field(min_length=1)

    # Multiplier applied to base damage against each chassis class.
    target_class_effectiveness: ModelSOTargetClassEffectiveness

    # Damage type used to resolve armor effectiveness on a hit (Task 25).
    damage_type: WeaponDamageType

    compatibility: ModelSOWeaponCompatibility
