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

from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from steel_onslaught.immutable import FrozenJSONMapping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RUPTURE_THRESHOLD = 100  # design §10.3 canonical rupture threshold for guard checks


class ModeId(StrEnum):
    """Closed canonical combat-mode identifier used across every boundary."""

    RECON = "recon"
    ASSAULT = "assault"
    EVASION = "evasion"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ModelSOModeTransitionCosts(BaseModel):
    """Costs incurred when switching modes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pressure: StrictInt = Field(ge=0, description="Pressure consumed on switch")
    heat: StrictInt = Field(ge=0, description="Heat added on switch")
    transition_ticks: StrictInt = Field(
        ge=1, description="Ticks the mech spends in transition state"
    )


class ModelSOModeTransitionRestrictions(BaseModel):
    """Conditions that block a mode switch from firing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_lock_ticks_after_switch: StrictInt = Field(
        ge=0, description="Ticks the mode is locked after switching into it"
    )
    cannot_switch_if_heat_above: StrictInt | None = Field(
        default=None,
        description=(
            "Block switch if current heat exceeds this value. "
            "Must be strictly less than rupture_threshold (100) so the guard can actually fire."
        ),
    )
    cannot_switch_if_boiler_disabled: StrictBool = Field(
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

    evasion_penalty_during_transition: StrictFloat = Field(
        ge=0.0,
        description=(
            "Multiplicative evasion penalty applied while in transition (0 = no penalty added)"
        ),
    )
    sensor_dropout_ticks: StrictInt = Field(
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
    active_systems: tuple[str, ...] = Field(
        min_length=1,
        description="Module categories that are powered/active in this mode (non-empty)",
    )
    passive_modifiers: FrozenJSONMapping = Field(
        default_factory=dict,
        validate_default=True,
        description="Stat multipliers/addends applied while this mode is active",
    )
    default_priorities: tuple[str, ...] = Field(
        min_length=1,
        description="Ordered pilot priority hints for this mode (non-empty)",
    )

    @field_validator("id")
    @classmethod
    def id_matches_pattern(cls, v: str) -> str:
        prefix, separator, raw_mode = v.partition(".")
        try:
            mode = ModeId(raw_mode)
        except ValueError:
            mode = None
        if prefix != "mode" or separator != "." or mode is None:
            raise ValueError(
                f"id={v!r} must identify one of the closed combat modes: "
                f"{[f'mode.{item.value}' for item in ModeId]}"
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
    from_mode: ModeId = Field(description="Closed source mode identifier")
    to_mode: ModeId = Field(description="Closed destination mode identifier")
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


class ModelSOModeSwitchIntentPayload(BaseModel):
    """Closed payload emitted by the canonical pilot-to-runner intent path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_mode: ModeId


class ModelSOModeTransitionStartedPayload(BaseModel):
    """Closed canonical MODE_TRANSITION_STARTED payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_mode: ModeId
    to_mode: ModeId
    costs: ModelSOModeTransitionCosts
    sensor_dropout_ticks: StrictInt = Field(ge=0)
    evasion_penalty: StrictFloat = Field(ge=0.0)


class ModelSOModeTransitionCompletedPayload(BaseModel):
    """Closed canonical MODE_TRANSITION_COMPLETED payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_mode: ModeId
    new_mode: ModeId
    mode_lock_until: StrictInt = Field(ge=0)
