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


class ModelSOChassisCompatibility(BaseModel):
    """Lists of module/boiler/mobility class strings this chassis supports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    weapon_classes: list[str] = Field(min_length=1)
    boiler_classes: list[str] = Field(min_length=1)
    mobility_classes: list[str] = Field(min_length=1)


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
