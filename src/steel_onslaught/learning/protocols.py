from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from steel_onslaught.contracts.card_learning import ModelSOCardLearningMetric
from steel_onslaught.contracts.lineage import ParamDict


class ModelSONumericBound(BaseModel):
    """Inclusive numeric range quantized to a step lattice."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    minimum: float
    maximum: float
    step: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> ModelSONumericBound:
        if self.minimum > self.maximum:
            raise ValueError("minimum must be <= maximum")
        return self


class ModelSOCategoricalBound(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    choices: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> ModelSOCategoricalBound:
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("choices must be unique")
        return self


BoundsDict = dict[str, ModelSONumericBound | ModelSOCategoricalBound]


class SpecLike(Protocol):
    """Structural view of a tunable pilot spec (no game-engine import).

    Phase 2 supplies an adapter over ModelSOPilotSpec (parameters via
    model_dump, bounds derived from the parameter models' field
    constraints). Phase 1 codes only against this shape.
    """

    @property
    def archetype(self) -> str: ...

    @property
    def parameters(self) -> ParamDict: ...

    @property
    def bounds(self) -> BoundsDict: ...


class SOSeedWinner(StrEnum):
    CANDIDATE = "candidate"
    PARENT = "parent"
    DRAW = "draw"


class ModelSOSeedOutcome(BaseModel):
    """Outcome of one paired candidate-vs-parent trial on one seed."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    seed: int
    winner: SOSeedWinner
    candidate_overloads: int = Field(ge=0)
    parent_overloads: int = Field(ge=0)
    candidate_card_learning_metrics: tuple[ModelSOCardLearningMetric, ...] = ()
    parent_card_learning_metrics: tuple[ModelSOCardLearningMetric, ...] = ()


class ModelSOPairedComparison(BaseModel):
    """Summary of a paired seed battery (produced by stats, consumed by the gate)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    n_seeds: int = Field(ge=0)
    candidate_wins: int = Field(ge=0)
    parent_wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    p_value: float = Field(ge=0.0, le=1.0)
    candidate_win_rate: float = Field(ge=0.0, le=1.0)  # decisive only; 0.5 if none
    ci_low: float = Field(ge=0.0, le=1.0)  # Wilson 95% on candidate_win_rate
    ci_high: float = Field(ge=0.0, le=1.0)
    effect_size: float = Field(ge=-0.5, le=0.5)  # candidate_win_rate - 0.5

    @model_validator(mode="after")
    def _consistent(self) -> ModelSOPairedComparison:
        if self.candidate_wins + self.parent_wins + self.draws != self.n_seeds:
            raise ValueError("wins + draws must equal n_seeds")
        if self.ci_low > self.ci_high:
            raise ValueError("ci_low must be <= ci_high")
        return self


class EvaluatorProtocol(Protocol):
    """Seam to the match engine. Phase 1 ships only FakeEvaluator; Phase 2
    binds the balance-harness machinery behind this exact signature."""

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        """One outcome per seed, in the given seed order."""
        ...
