"""Acceptance tests for the terminal-only live learning boundary."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from steel_onslaught.contracts.lineage import (
    ModelSOLineageEvidence,
    ModelSOLineageGenerator,
    ModelSOLineagePerformance,
    ModelSOLineagePromotion,
    ModelSOLineageRecord,
    ParamDict,
    SOPromotionRejection,
    SOPromotionStatus,
    meta_hash,
    spec_hash,
)
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import CURRENT_CONSUMED_PAYLOAD_MODELS, ModelSOPlayerScore
from steel_onslaught.learning.after_match import AfterMatchLearningHandler
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.live import LiveLearningCoordinator, LiveLearningPromotionPort
from steel_onslaught.ledger.protocol import EventLedger
from tests.fixtures.event_samples import build_sample_envelopes


def _evidence(match_id: str) -> ModelSOAfterMatchLearningEvidence:
    score = ModelSOPlayerScore(
        victory=1,
        damage_dealt=10,
        damage_efficiency=1.0,
        pressure_efficiency=1.0,
        overload_penalty=0,
        replay_validity=1,
        final_score=10,
    )
    loser = score.model_copy(update={"victory": 0, "final_score": 0})
    return ModelSOAfterMatchLearningEvidence(
        match_id=match_id,
        scored_event_id=f"event.score.{match_id}",
        correlation_id=UUID("00000000-0000-0000-0000-000000000001"),
        duration_ticks=10,
        winner_player_id="player.red",
        is_draw=False,
        scores={"player.red": score, "player.blue": loser},
        event_counts={"match_scored": 1},
        decision_action_counts={},
        decision_reason_counts={},
    )


def _record(parameters: ParamDict, *, promoted: bool = True) -> ModelSOLineageRecord:
    parent = {"aggression": 1.0}
    return ModelSOLineageRecord(
        archetype="aggressive",
        parameters=parameters,
        spec_hash=spec_hash("aggressive", parameters),
        parent_hash=spec_hash("aggressive", parent),
        meta_hash=meta_hash(("opponent.base",)),
        evidence=ModelSOLineageEvidence(search_seeds=(1,), holdout_seeds=(2,)),
        performance=ModelSOLineagePerformance(
            candidate_win_rate=1.0,
            win_rate_delta=0.5,
            overload_rate_delta=0.0,
            draw_rate=0.0,
            p_value=0.01,
            decisive_n=10,
        ),
        generator=ModelSOLineageGenerator(
            generator_id="test.evaluator",
            selection_reason="typed fixture",
        ),
        promotion=ModelSOLineagePromotion(
            status=(SOPromotionStatus.PROMOTED if promoted else SOPromotionStatus.REJECTED),
            rejection_reasons=() if promoted else (SOPromotionRejection.WRONG_DIRECTION,),
        ),
    )


class _Evaluator:
    def __init__(self, records: Sequence[ModelSOLineageRecord | None]) -> None:
        self.records = list(records)
        self.calls: list[ModelSOLiveLearningPolicy] = []

    def evaluate(
        self,
        *,
        evidence: ModelSOAfterMatchLearningEvidence,
        policy: ModelSOLiveLearningPolicy,
    ) -> ModelSOLineageRecord | None:
        self.calls.append(policy)
        return self.records.pop(0)


def _policy(parameters: ParamDict) -> ModelSOLiveLearningPolicy:
    return ModelSOLiveLearningPolicy(
        policy_id="policy.aggressive.initial",
        archetype="aggressive",
        parameters=parameters,
        spec_hash=spec_hash("aggressive", parameters),
        generation=0,
    )


@pytest.mark.unit
def test_promotion_changes_next_match_but_not_active_snapshot() -> None:
    initial = _policy({"aggression": 1.0})
    candidate = _record({"aggression": 2.0})
    evaluator = _Evaluator([candidate, None])
    coordinator = LiveLearningCoordinator(current_policy=initial, evaluator=evaluator)

    active = coordinator.begin_match("match.active")
    learning = coordinator.begin_match("match.learning")
    outcome = coordinator.handle_after_match(_evidence("match.learning"))

    assert outcome.status == "promoted"
    assert outcome.policy_after is not None
    assert outcome.policy_after.spec_hash == candidate.spec_hash
    assert active.policy == initial
    assert learning.policy == initial

    next_match = coordinator.begin_match("match.next")
    assert next_match.policy.spec_hash == candidate.spec_hash
    assert next_match.policy.generation == 1
    assert evaluator.calls == [initial]


@pytest.mark.unit
def test_late_completion_from_old_snapshot_is_stale_and_cannot_roll_back() -> None:
    initial = _policy({"aggression": 1.0})
    first = _record({"aggression": 2.0})
    second = _record({"aggression": 3.0})
    evaluator = _Evaluator([first, second])
    coordinator = LiveLearningCoordinator(current_policy=initial, evaluator=evaluator)

    older = coordinator.begin_match("match.older")
    newer = coordinator.begin_match("match.newer")
    promoted = coordinator.handle_after_match(_evidence("match.newer"))
    stale = coordinator.handle_after_match(_evidence("match.older"))

    assert promoted.status == "promoted"
    assert stale.status == "stale"
    assert stale.policy_after is None
    assert older.policy == initial
    assert newer.policy == initial
    assert coordinator.current_policy.spec_hash == first.spec_hash


@pytest.mark.unit
def test_rejected_candidate_does_not_change_policy() -> None:
    initial = _policy({"aggression": 1.0})
    evaluator = _Evaluator([_record({"aggression": 2.0}, promoted=False)])
    coordinator = LiveLearningCoordinator(current_policy=initial, evaluator=evaluator)

    coordinator.begin_match("match.rejected")
    outcome = coordinator.handle_after_match(_evidence("match.rejected"))

    assert outcome.status == "rejected"
    assert outcome.policy_after is None
    assert coordinator.current_policy == initial


@pytest.mark.unit
def test_match_admission_is_single_use_for_active_and_completed_ids() -> None:
    coordinator = LiveLearningCoordinator(
        current_policy=_policy({"aggression": 1.0}),
        evaluator=_Evaluator([None]),
    )
    coordinator.begin_match("match.once")
    with pytest.raises(ValueError, match="already been admitted"):
        coordinator.begin_match("match.once")

    coordinator.handle_after_match(_evidence("match.once"))
    with pytest.raises(ValueError, match="already been admitted"):
        coordinator.begin_match("match.once")


@pytest.mark.unit
def test_failed_evaluation_keeps_active_snapshot_retryable() -> None:
    class _FlakyEvaluator(_Evaluator):
        def __init__(self) -> None:
            super().__init__([_record({"aggression": 2.0})])
            self.fail = True

        def evaluate(
            self,
            *,
            evidence: ModelSOAfterMatchLearningEvidence,
            policy: ModelSOLiveLearningPolicy,
        ) -> ModelSOLineageRecord | None:
            if self.fail:
                self.fail = False
                raise RuntimeError("temporary evaluator failure")
            return super().evaluate(evidence=evidence, policy=policy)

    evaluator = _FlakyEvaluator()
    coordinator = LiveLearningCoordinator(
        current_policy=_policy({"aggression": 1.0}), evaluator=evaluator
    )
    admitted = coordinator.begin_match("match.retry")
    with pytest.raises(RuntimeError, match="temporary evaluator failure"):
        coordinator.handle_after_match(_evidence("match.retry"))

    outcome = coordinator.handle_after_match(_evidence("match.retry"))
    assert outcome.status == "promoted"
    assert outcome.policy_before == admitted.policy


@pytest.mark.unit
def test_after_match_promotion_port_is_terminal_only() -> None:
    samples = build_sample_envelopes()
    events = [samples[event_type] for event_type in CURRENT_CONSUMED_PAYLOAD_MODELS]

    class _Ledger:
        def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
            return iter(event for event in events if event.match_id == match_id)

    class _Artifacts:
        def write_after_match_evidence(self, evidence: ModelSOAfterMatchLearningEvidence) -> Path:
            return Path(f"{evidence.match_id}.yaml")

    class _Promotion:
        def __init__(self) -> None:
            self.evidence: list[ModelSOAfterMatchLearningEvidence] = []

        def handle_after_match(self, evidence: ModelSOAfterMatchLearningEvidence) -> object:
            self.evidence.append(evidence)
            return object()

    promotion = _Promotion()
    handler = AfterMatchLearningHandler(
        ledger=cast(EventLedger, _Ledger()),
        artifacts=cast(LearningArtifactStore, _Artifacts()),
        promotion=cast(LiveLearningPromotionPort, promotion),
    )
    handler.handle(samples[SOEventType.MATCH_TICK])
    assert promotion.evidence == []
    handler.handle(samples[SOEventType.MATCH_SCORED])
    assert len(promotion.evidence) == 1
