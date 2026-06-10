"""Mode contract models: ModelSOModeSpec and ModelSOModeTransition.

Invariants enforced at validation time:
- id must match ^mode\\.[a-z][a-z0-9_]*$
- kind must be steel_onslaught.mode / steel_onslaught.mode_transition
- active_systems must be non-empty
- default_priorities must be non-empty
- ModelSOModeTransition: from_mode != to_mode (no self-loops)
- ModelSOModeTransitionCosts: transition_ticks >= 1
- ModelSOModeTransitionRestrictions: cannot_switch_if_heat_above < 100 (rupture_threshold)
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RUPTURE_THRESHOLD = 100  # design §10.3 canonical rupture threshold for guard checks
_MODE_ID_PATTERN = re.compile(r"^mode\.[a-z][a-z0-9_]*$")

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ModelSOModeTransitionCosts(BaseModel):
    """Costs incurred when switching modes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pressure: int = Field(ge=0, description="Pressure consumed on switch")
    heat: int = Field(ge=0, description="Heat added on switch")
    transition_ticks: int = Field(ge=1, description="Ticks the mech spends in transition state")


class ModelSOModeTransitionRestrictions(BaseModel):
    """Conditions that block a mode switch from firing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_lock_ticks_after_switch: int = Field(
        ge=0, description="Ticks the mode is locked after switching into it"
    )
    cannot_switch_if_heat_above: int | None = Field(
        default=None,
        description=(
            "Block switch if current heat exceeds this value. "
            "Must be strictly less than rupture_threshold (100) so the guard can actually fire."
        ),
    )
    cannot_switch_if_boiler_disabled: bool = Field(
        default=False, description="Block switch when boiler is disabled/ruptured"
    )

    @field_validator("cannot_switch_if_heat_above")
    @classmethod
    def heat_guard_below_rupture(cls, v: int | None) -> int | None:
        if v is not None and v >= _RUPTURE_THRESHOLD:
            raise ValueError(
                f"cannot_switch_if_heat_above={v} must be < rupture_threshold "
                f"({_RUPTURE_THRESHOLD}); a value at or above rupture makes the guard "
                "unreachable and would never fire."
            )
        return v


class ModelSOModeTransitionVulnerability(BaseModel):
    """Vulnerability window opened during a mode transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evasion_penalty_during_transition: float = Field(
        ge=0.0,
        description=(
            "Multiplicative evasion penalty applied while in transition (0 = no penalty added)"
        ),
    )
    sensor_dropout_ticks: int = Field(
        ge=0, description="Ticks that sensors go dark at the start of the transition"
    )


# ---------------------------------------------------------------------------
# ModelSOModeSpec
# ---------------------------------------------------------------------------


class ModelSOModeSpec(BaseModel):
    """Contract spec for a combat mode (recon / assault / evasion)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.mode"]
    id: str = Field(description="Canonical mode identifier, e.g. mode.recon")
    display_name: str
    active_systems: list[str] = Field(
        min_length=1,
        description="Module categories that are powered/active in this mode (non-empty)",
    )
    passive_modifiers: dict[str, Any] = Field(
        default_factory=dict,
        description="Stat multipliers/addends applied while this mode is active",
    )
    default_priorities: list[str] = Field(
        min_length=1,
        description="Ordered pilot priority hints for this mode (non-empty)",
    )

    @field_validator("id")
    @classmethod
    def id_matches_pattern(cls, v: str) -> str:
        if not _MODE_ID_PATTERN.match(v):
            raise ValueError(
                f"id={v!r} must match ^mode\\.[a-z][a-z0-9_]*$ (e.g. 'mode.recon', 'mode.assault')"
            )
        return v


# ---------------------------------------------------------------------------
# ModelSOModeTransition
# ---------------------------------------------------------------------------


class ModelSOModeTransition(BaseModel):
    """Defines cost, restrictions, and vulnerability for one directed mode switch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.mode_transition"]
    from_mode: str = Field(description="Mode name (without 'mode.' prefix, e.g. 'recon')")
    to_mode: str = Field(description="Mode name (without 'mode.' prefix, e.g. 'assault')")
    costs: ModelSOModeTransitionCosts
    restrictions: ModelSOModeTransitionRestrictions
    vulnerability: ModelSOModeTransitionVulnerability

    @model_validator(mode="after")
    def no_self_transition(self) -> ModelSOModeTransition:
        if self.from_mode == self.to_mode:
            raise ValueError(
                f"Self-transition {self.from_mode!r}→{self.to_mode!r} is not allowed; "
                "from_mode and to_mode must differ."
            )
        return self
