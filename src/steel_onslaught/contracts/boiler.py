"""Boiler contract model — Task 8.

ModelSOBoilerSpec captures the static loadout-time specification for a boiler.
ModelSOBoilerState captures the runtime state per design §10.3.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelSOBoilerCompatibility(BaseModel):
    """Chassis classes compatible with this boiler."""

    model_config = ConfigDict(frozen=True)

    compatible_chassis_classes: tuple[str, ...] = Field(min_length=1)


class ModelSOBoilerSpec(BaseModel):
    """Boiler specification — design §10.1.

    Invariants enforced at construction time:
      - redline_threshold < rupture_threshold (rupture is worse than redline)
      - instability_curve: linear | quadratic | exponential
      - repairability: none | partial | full
      - mass > 0
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.boiler"] = "steel_onslaught.boiler"

    id: str
    display_name: str

    # Pressure economy.
    pressure_capacity: int = Field(gt=0)
    regen_per_tick: int = Field(ge=0)

    # Heat economy.
    heat_capacity: int = Field(gt=0)
    heat_multiplier: float = Field(gt=0.0)
    vent_rate: int = Field(ge=0)

    # Failure thresholds — redline_threshold < rupture_threshold enforced below.
    redline_threshold: int = Field(gt=0)
    rupture_threshold: int = Field(gt=0)

    # Shape of the instability probability curve.
    instability_curve: Literal["linear", "quadratic", "exponential"]

    # How repairable the boiler is after overload damage.
    repairability: Literal["none", "partial", "full"]

    # Physical cost.
    mass: int = Field(gt=0)

    # Chassis class compatibility.
    compatibility: ModelSOBoilerCompatibility

    @model_validator(mode="after")
    def _redline_less_than_rupture(self) -> ModelSOBoilerSpec:
        if self.redline_threshold >= self.rupture_threshold:
            raise ValueError(
                f"redline_threshold ({self.redline_threshold}) must be strictly less than "
                f"rupture_threshold ({self.rupture_threshold})"
            )
        return self


class ModelSOBoilerState(BaseModel):
    """Boiler runtime state — design §10.3.

    Mirrors the YAML contract example:
      pressure: { current, maximum, regeneration_per_tick }
      heat: { current, redline_threshold, rupture_threshold, vent_rate }
      status: { redline, rupture_warning, disabled, ruptured }
      modifiers: { heat_weapon_pressure, venting_penalty, mode_switch_heat_delta }

    Flattened into typed fields (no nested dicts) for strong typing + mypy --strict.

    Invariant: current_heat > rupture_threshold is invalid — rupture is terminal,
    not a steady state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.boiler_state"] = "steel_onslaught.boiler_state"

    match_id: str
    mech_id: str
    tick: int = Field(ge=0)

    # Pressure section.
    pressure_current: int = Field(ge=0)
    pressure_maximum: int = Field(gt=0)
    regeneration_per_tick: int = Field(ge=0)

    # Heat section.
    heat_current: int = Field(ge=0)
    heat_redline_threshold: int = Field(gt=0)
    heat_rupture_threshold: int = Field(gt=0)
    heat_vent_rate: int = Field(ge=0)

    # Status flags.
    status_redline: bool
    status_rupture_warning: bool
    status_disabled: bool
    status_ruptured: bool

    # Modifiers.
    modifier_heat_weapon_pressure: float = Field(ge=0.0)
    modifier_venting_penalty: float = Field(ge=0.0)
    modifier_mode_switch_heat_delta: int

    @model_validator(mode="after")
    def _heat_current_cannot_exceed_rupture(self) -> ModelSOBoilerState:
        """Rupture is a terminal event — the mech is destroyed, not in a ruptured state."""
        if self.heat_current > self.heat_rupture_threshold:
            raise ValueError(
                f"heat_current ({self.heat_current}) must not exceed "
                f"heat_rupture_threshold ({self.heat_rupture_threshold}): "
                "rupture is terminal, not a persistent state"
            )
        return self
