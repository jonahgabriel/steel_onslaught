from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from steel_onslaught.contracts.card_learning import ModelSOCardLearningMetric
from steel_onslaught.immutable import FrozenMapping

ParamValue = int | float | str
ParamDict = dict[str, ParamValue]


def spec_hash(archetype: str, parameters: Mapping[str, ParamValue]) -> str:
    """Canonical content hash of a pilot spec's tunable identity.

    Identity = (archetype, parameters) serialized as canonical JSON
    (sorted keys, compact separators). A changed spec is a new identity;
    history does not transfer (design addendum section 6).
    """
    payload = {"archetype": archetype, "parameters": dict(parameters)}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def meta_hash(opponent_spec_hashes: Iterable[str]) -> str:
    """Hash of the opponent pool ('meta') a record's evidence covers."""
    blob = json.dumps(sorted(set(opponent_spec_hashes)), separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class SOPromotionStatus(StrEnum):
    PROMOTED = "promoted"
    REJECTED = "rejected"


class SOPromotionRejection(StrEnum):
    WRONG_DIRECTION = "wrong_direction"
    NOT_SIGNIFICANT = "not_significant"
    INSUFFICIENT_DECISIVE_N = "insufficient_decisive_n"
    OVERLOAD_REGRESSION = "overload_regression"
    DRAW_RATE_EXCEEDED = "draw_rate_exceeded"
    TRIVIAL_CLONE = "trivial_clone"
    HOLDOUT_REGRESSION = "holdout_regression"


class ModelSOLineageEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    search_seeds: tuple[int, ...] = Field(min_length=1)
    holdout_seeds: tuple[int, ...] = Field(min_length=1)
    candidate_card_learning_metrics: tuple[ModelSOCardLearningMetric, ...] = ()
    parent_card_learning_metrics: tuple[ModelSOCardLearningMetric, ...] = ()

    @model_validator(mode="after")
    def _disjoint(self) -> ModelSOLineageEvidence:
        overlap = set(self.search_seeds) & set(self.holdout_seeds)
        if overlap:
            raise ValueError(f"holdout seeds overlap search seeds: {sorted(overlap)}")
        return self


class ModelSOLineagePerformance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    candidate_win_rate: float = Field(ge=0.0, le=1.0)  # decisive trials only
    win_rate_delta: float = Field(ge=-0.5, le=0.5)  # candidate_win_rate - 0.5
    overload_rate_delta: float  # candidate minus parent, per evaluated match
    draw_rate: float = Field(ge=0.0, le=1.0)  # draws / total search seeds
    p_value: float = Field(ge=0.0, le=1.0)
    decisive_n: int = Field(ge=0)


class ModelSOLineageGenerator(BaseModel):
    """Search-authority provenance (design addendum section 7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    generator_id: str = Field(min_length=1)  # e.g. "search.hill_climb"
    selection_reason: str = Field(min_length=1)
    cohort: str | None = None


class ModelSOLineagePromotion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: SOPromotionStatus
    rejection_reasons: tuple[SOPromotionRejection, ...] = ()

    @model_validator(mode="after")
    def _status_matches_reasons(self) -> ModelSOLineagePromotion:
        if self.status is SOPromotionStatus.PROMOTED and self.rejection_reasons:
            raise ValueError("promoted record cannot carry rejection reasons")
        if self.status is SOPromotionStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("rejected record must carry at least one reason")
        return self


class ModelSOLineageRecord(BaseModel):
    """Design section 18.2 lineage record + capsule-identity discipline.

    Deliberately carries no timestamp: the gate is pure; wall-clock
    attribution is added at persistence time (Phase 2), never defaulted
    inside the pure model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.lineage_record"] = "steel_onslaught.lineage_record"
    archetype: str = Field(min_length=1)
    parameters: FrozenMapping[ParamValue]
    spec_hash: str = Field(min_length=64, max_length=64)
    parent_hash: str = Field(min_length=64, max_length=64)
    meta_hash: str = Field(min_length=64, max_length=64)
    evidence: ModelSOLineageEvidence
    performance: ModelSOLineagePerformance
    generator: ModelSOLineageGenerator
    promotion: ModelSOLineagePromotion

    @model_validator(mode="after")
    def _hash_consistent(self) -> ModelSOLineageRecord:
        expected = spec_hash(self.archetype, self.parameters)
        if self.spec_hash != expected:
            raise ValueError("spec_hash does not match canonical hash of (archetype, parameters)")
        return self
