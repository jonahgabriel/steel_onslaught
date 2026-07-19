"""Strict post-match evidence contract consumed by the learning substrate.

The match event stream remains authoritative.  This model is a materialized,
read-only summary of one terminal ``MATCH_SCORED`` stream and is deliberately
separate from the tunable pilot lineage records produced by ``so learn``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from steel_onslaught.events.payloads import ModelSOPlayerScore
from steel_onslaught.pilots.programming import ModelSOCardRulePackProvenance


class ModelSOAfterMatchLearningEvidence(BaseModel):
    """Canonical post-match evidence projection.

    All counters are derived from the canonical ledger, never from UI state or
    pilot-local bookkeeping.  ``extra=forbid`` keeps the evidence envelope
    closed as the projection evolves.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.match_learning_evidence"] = (
        "steel_onslaught.match_learning_evidence"
    )
    match_id: str
    scored_event_id: str
    correlation_id: UUID
    duration_ticks: StrictInt = Field(gt=0)
    winner_player_id: str
    is_draw: StrictBool
    scores: Mapping[str, ModelSOPlayerScore]
    event_counts: Mapping[str, StrictInt]
    decision_action_counts: Mapping[str, StrictInt]
    decision_reason_counts: Mapping[str, StrictInt]
    card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


__all__ = ["ModelSOAfterMatchLearningEvidence"]
