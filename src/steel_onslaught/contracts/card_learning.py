"""Strict card-level learning metrics derived from canonical event streams."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from steel_onslaught.contracts.card import CardId
from steel_onslaught.immutable import FrozenMapping


class _ClosedCardLearningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOCardLearningMetric(_ClosedCardLearningModel):
    """Usage and resolution outcomes for one card id in one match/evaluation."""

    card_id: CardId
    dealt_count: StrictInt = Field(ge=0)
    planned_count: StrictInt = Field(ge=0)
    resolved_count: StrictInt = Field(ge=0)
    outcome_counts: FrozenMapping[int] = Field(default_factory=dict)
    action_counts: FrozenMapping[int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _counts_are_canonical(self) -> Self:
        if tuple(self.outcome_counts) != tuple(sorted(self.outcome_counts)):
            raise ValueError("outcome_counts keys must be sorted")
        if tuple(self.action_counts) != tuple(sorted(self.action_counts)):
            raise ValueError("action_counts keys must be sorted")
        for name, counts in (
            ("outcome_counts", self.outcome_counts),
            ("action_counts", self.action_counts),
        ):
            if any(value < 0 for value in counts.values()):
                raise ValueError(f"{name} values must be non-negative")
        if sum(self.outcome_counts.values()) != self.resolved_count:
            raise ValueError("outcome_counts must sum to resolved_count")
        if sum(self.action_counts.values()) != self.resolved_count:
            raise ValueError("action_counts must sum to resolved_count")
        return self


def merge_card_learning_metrics(
    metrics: Mapping[str, ModelSOCardLearningMetric],
) -> tuple[ModelSOCardLearningMetric, ...]:
    """Return metrics in canonical card-id order after validating identities."""

    result = tuple(sorted(metrics.values(), key=lambda metric: str(metric.card_id)))
    ids = tuple(str(metric.card_id) for metric in result)
    if len(ids) != len(set(ids)):
        raise ValueError("card learning metrics must contain unique card ids")
    return result


def aggregate_card_learning_metrics(
    groups: Sequence[Sequence[ModelSOCardLearningMetric]],
) -> tuple[ModelSOCardLearningMetric, ...]:
    """Sum metric groups while preserving canonical card-id ordering."""

    totals: dict[str, _MutableCardLearningMetric] = {}
    for group in groups:
        for metric in group:
            card_id = str(metric.card_id)
            state = totals.setdefault(card_id, _MutableCardLearningMetric())
            state.dealt_count += metric.dealt_count
            state.planned_count += metric.planned_count
            state.resolved_count += metric.resolved_count
            state.outcome_counts.update(metric.outcome_counts)
            state.action_counts.update(metric.action_counts)

    return merge_card_learning_metrics(
        {
            card_id: ModelSOCardLearningMetric(
                card_id=card_id,
                dealt_count=state.dealt_count,
                planned_count=state.planned_count,
                resolved_count=state.resolved_count,
                outcome_counts=dict(sorted(state.outcome_counts.items())),
                action_counts=dict(sorted(state.action_counts.items())),
            )
            for card_id, state in totals.items()
        }
    )


@dataclass
class _MutableCardLearningMetric:
    dealt_count: int = 0
    planned_count: int = 0
    resolved_count: int = 0
    outcome_counts: Counter[str] = field(default_factory=Counter)
    action_counts: Counter[str] = field(default_factory=Counter)


__all__ = [
    "ModelSOCardLearningMetric",
    "aggregate_card_learning_metrics",
    "merge_card_learning_metrics",
]
