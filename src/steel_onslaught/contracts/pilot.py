"""Pilot spec contract models — tunable-pilots Task 1.

New contract kind ``steel_onslaught.pilot`` (design addendum
``docs/plans/2026-06-10-tunable-pilots-design-addendum.md`` §4-§5): every
decision threshold of the three archetype heuristics becomes a bounded,
validated field. The decision tree *structure* stays code-owned; only the
constants are tunable. Bounds are the approval — an out-of-bounds value never
constructs a spec.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PILOT_ID_PATTERN = r"^pilot\.[a-z0-9_]+\.[a-z0-9_]+$"

PilotId = Annotated[str, StringConstraints(pattern=PILOT_ID_PATTERN)]


class SOWeaponPreference(StrEnum):
    """Primary weapon sort policy for the aggressive archetype (addendum §5.1).

    The final equal-score tiebreak (lexicographically lowest weapon id) is
    fixed and NOT tunable under either policy.
    """

    HIGHEST_DAMAGE = "highest_damage"
    LOWEST_HEAT = "lowest_heat"


class ModelSOPilotLineage(BaseModel):
    """Fork ancestry pointer (addendum §8). Templates alone carry a null parent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parent: PilotId | None


class ModelSOAggressivePilotParams(BaseModel):
    """Tunable thresholds for the aggressive archetype (addendum §5.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vent_at_heat_margin: int = Field(ge=2, le=20)
    idle_vent_heat_threshold: int = Field(ge=40, le=96)
    mode_switch_pressure_floor: int = Field(ge=0, le=60)
    mode_switch_heat_ceiling: int = Field(ge=0, le=92)
    weapon_preference: SOWeaponPreference


class ModelSODefensivePilotParams(BaseModel):
    """Tunable thresholds for the defensive archetype (addendum §5.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vent_headroom_below_redline: int = Field(ge=0, le=40)
    fire_confidence_floor: float = Field(ge=0.4, le=0.95)
    fire_heat_headroom: int = Field(ge=0, le=40)
    disengage_hp_pct: int = Field(ge=0, le=60)


class ModelSOPredictivePilotParams(BaseModel):
    """Tunable thresholds for the predictive archetype (addendum §5.3).

    The 3-observation linear extrapolation window is structural and
    deliberately NOT represented here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    lock_confidence_floor: float = Field(ge=0.3, le=0.95)
    predicted_hit_floor: float = Field(ge=0.2, le=0.95)
    preemptive_vent_headroom: int = Field(ge=0, le=30)
    regen_pressure_floor: int = Field(ge=0, le=60)


class ModelSOLlmPilotParams(BaseModel):
    """Identity params for the LLM archetype (categorical, not tunable).

    The LLM's behavior is shaped by its persona prompt, not numeric thresholds.
    These fields identify which persona and provider to use; they are not a
    search space for the learning loop (the tuner tunes heuristic archetypes).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona: str = Field(min_length=1, description="Persona id (berserker|sniper|opportunist|...)")
    provider: str = Field(
        min_length=1,
        description="Provider id selected by the application overlay",
    )
    # Optional static, seat-scoped tactical guidance for whole-round card
    # programming (2026-07-24 prompt-arms ARM G). Declarative-only: this is a
    # config field authored on the pilot spec, never hardcoded prompt text in
    # code. It reuses the exact same code-owned composition seam as the
    # live-learning ``policy_guidance`` block (``programming_system_prompt``
    # appends it AFTER the wire-contract instructions and the persona
    # doctrine), so it is stacked on top of, not a replacement for, the
    # persona's standing doctrine text. ``None`` by default keeps every
    # existing pilot spec's resolved programmer byte-identical.
    programming_guidance: str | None = Field(default=None, min_length=1)
    # Show-dont-tell spatial representation arms R1/R2 (2026-07-24 prompt-
    # content audit follow-up). "none" (default) keeps every existing pilot
    # spec's resolved observation/prompt byte-identical -- zero behavior
    # change unless a spec explicitly opts in. "grid" (ARM R1) adds a
    # rendered viewport map, per-dealt-movement-card consequence previews,
    # and per-dealt-weapon-card in-range flags -- representation only, no
    # strategy advice. "grid_scaffold" (ARM R2) is R1 plus a required
    # one-line spatial-read field in the response format before register
    # selection (schema-tolerant: an omitted field is logged, never aborted).
    spatial_representation: Literal["none", "grid", "grid_scaffold"] = "none"


class ModelSOHumanPilotParams(BaseModel):
    """Identity-only declaration for a future injected browser-command pilot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_source: Literal["browser_command"]


_ARCHETYPE_PARAMS: dict[str, type[BaseModel]] = {
    "aggressive": ModelSOAggressivePilotParams,
    "defensive": ModelSODefensivePilotParams,
    "predictive": ModelSOPredictivePilotParams,
    "llm": ModelSOLlmPilotParams,
    "human": ModelSOHumanPilotParams,
}


class ModelSOPilotSpec(BaseModel):
    """Pilot specification — contract kind ``steel_onslaught.pilot`` (addendum §4.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1.0", "0.2.0"] = "0.1.0"
    kind: Literal["steel_onslaught.pilot"] = "steel_onslaught.pilot"

    id: PilotId
    display_name: str = Field(min_length=1)
    archetype: Literal["aggressive", "defensive", "predictive", "llm", "human"]
    lineage: ModelSOPilotLineage
    parameters: (
        ModelSOAggressivePilotParams
        | ModelSODefensivePilotParams
        | ModelSOPredictivePilotParams
        | ModelSOLlmPilotParams
        | ModelSOHumanPilotParams
    )

    @model_validator(mode="after")
    def _parameters_match_archetype(self) -> Self:
        expected = _ARCHETYPE_PARAMS[self.archetype]
        if type(self.parameters) is not expected:
            raise ValueError(
                f"parameters model {type(self.parameters).__name__} does not match "
                f"archetype {self.archetype!r} (expected {expected.__name__})"
            )
        return self

    @model_validator(mode="after")
    def _schema_version_matches_human_capability(self) -> Self:
        expected = "0.2.0" if self.archetype == "human" else "0.1.0"
        if self.schema_version != expected:
            raise ValueError(
                f"schema_version {self.schema_version!r} does not match "
                f"archetype {self.archetype!r}; expected {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _no_self_parent(self) -> Self:
        if self.lineage.parent == self.id:
            raise ValueError(f"lineage.parent must not equal the spec's own id ({self.id!r})")
        return self
