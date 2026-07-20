"""Closed contracts for the live learning policy boundary.

The learning loop may produce a promoted lineage record, but a running match
must never start reading a different policy halfway through its event stream.
These contracts make that boundary explicit: a policy is an immutable snapshot
fielded when a match starts, and a later promotion can only be observed by a
subsequent match.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

from steel_onslaught.contracts.lineage import ParamValue, spec_hash
from steel_onslaught.immutable import FrozenMapping

Sha256Digest = Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ModelSOLiveLearningPolicy(BaseModel):
    """One immutable policy snapshot that can be fielded by a new match."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.live_learning_policy"] = "steel_onslaught.live_learning_policy"
    policy_id: StrictStr = Field(min_length=1)
    archetype: StrictStr = Field(min_length=1)
    parameters: FrozenMapping[ParamValue]
    spec_hash: Sha256Digest
    generation: StrictInt = Field(ge=0)
    source_lineage_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def _hash_matches_parameters(self) -> ModelSOLiveLearningPolicy:
        expected = spec_hash(self.archetype, self.parameters)
        if self.spec_hash != expected:
            raise ValueError("spec_hash does not match canonical policy parameters")
        return self


class ModelSOLiveMatchPolicySnapshot(BaseModel):
    """The policy captured at match admission; it never changes in place."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.live_match_policy_snapshot"] = (
        "steel_onslaught.live_match_policy_snapshot"
    )
    match_id: StrictStr = Field(min_length=1)
    policy: ModelSOLiveLearningPolicy


class ModelSOLiveLearningOutcome(BaseModel):
    """Terminal result of evaluating one completed match for promotion."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.live_learning_outcome"] = "steel_onslaught.live_learning_outcome"
    match_id: StrictStr = Field(min_length=1)
    status: Literal["promoted", "rejected", "stale"]
    policy_before: ModelSOLiveLearningPolicy
    policy_after: ModelSOLiveLearningPolicy | None = None
    reason: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def _status_matches_policy(self) -> ModelSOLiveLearningOutcome:
        if self.status == "promoted" and self.policy_after is None:
            raise ValueError("promoted live outcome requires policy_after")
        if self.status != "promoted" and self.policy_after is not None:
            raise ValueError("only promoted live outcomes may carry policy_after")
        return self


__all__ = [
    "ModelSOLiveLearningOutcome",
    "ModelSOLiveLearningPolicy",
    "ModelSOLiveMatchPolicySnapshot",
    "Sha256Digest",
]
