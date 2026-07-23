"""Unit tests for the deterministic win + damage-differential live evaluator."""

from __future__ import annotations

from uuid import UUID

import pytest

from steel_onslaught.contracts.lineage import ParamDict, SOPromotionStatus, spec_hash
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.payloads import ModelSOPlayerScore
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.live_evaluator import (
    GENERATOR_ID,
    WinDamageDifferentialEvaluator,
)

_LEARNER = "player.red"
_OPPONENT = "player.blue"


def _score(damage_dealt: int, *, victory: int) -> ModelSOPlayerScore:
    return ModelSOPlayerScore(
        victory=victory,
        damage_dealt=damage_dealt,
        damage_efficiency=1.0,
        pressure_efficiency=1.0,
        overload_penalty=0,
        replay_validity=1,
        final_score=damage_dealt,
    )


def _evidence(
    *,
    winner: str = _LEARNER,
    is_draw: bool = False,
    learner_damage: int = 100,
    opponent_damage: int = 40,
    match_id: str = "match.live.001",
) -> ModelSOAfterMatchLearningEvidence:
    return ModelSOAfterMatchLearningEvidence(
        match_id=match_id,
        scored_event_id="01HZY3E9ZTAV5J6BQF8KM2WXSC",
        correlation_id=UUID("00000000-0000-0000-0000-000000000001"),
        duration_ticks=12,
        winner_player_id=winner,
        is_draw=is_draw,
        scores={
            _LEARNER: _score(learner_damage, victory=0 if is_draw else int(winner == _LEARNER)),
            _OPPONENT: _score(opponent_damage, victory=0 if is_draw else int(winner == _OPPONENT)),
        },
        event_counts={"match_scored": 1},
        decision_action_counts={},
        decision_reason_counts={},
    )


def _policy(parameters: ParamDict, *, generation: int = 0) -> ModelSOLiveLearningPolicy:
    return ModelSOLiveLearningPolicy(
        policy_id="policy.aggressive.genesis",
        archetype="aggressive",
        parameters=parameters,
        spec_hash=spec_hash("aggressive", parameters),
        generation=generation,
    )


def _evaluator(**overrides: object) -> WinDamageDifferentialEvaluator:
    defaults: dict[str, object] = {"learning_player_id": _LEARNER}
    defaults.update(overrides)
    return WinDamageDifferentialEvaluator(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
def test_promotes_on_decisive_win_with_positive_damage_differential() -> None:
    policy = _policy({"aggression": 1.0})
    record = _evaluator().evaluate(evidence=_evidence(), policy=policy)

    assert record is not None
    assert record.promotion.status is SOPromotionStatus.PROMOTED
    assert record.archetype == "aggressive"
    assert record.parent_hash == policy.spec_hash
    assert record.parameters["aggression"] == 1.25
    assert record.spec_hash == spec_hash("aggressive", dict(record.parameters))
    assert record.generator.generator_id == GENERATOR_ID
    assert record.performance.decisive_n == 1
    assert record.performance.p_value == 1.0  # single sample: no significance claim


@pytest.mark.unit
def test_evaluation_is_deterministic_for_identical_evidence() -> None:
    policy = _policy({"aggression": 1.0})
    first = _evaluator().evaluate(evidence=_evidence(), policy=policy)
    second = _evaluator().evaluate(evidence=_evidence(), policy=policy)
    assert first is not None
    assert first == second


@pytest.mark.unit
@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (_evidence(winner=_OPPONENT), "loss"),
        (_evidence(is_draw=True), "draw"),
        (_evidence(learner_damage=40, opponent_damage=100), "won on points, out-damaged"),
        (_evidence(learner_damage=50, opponent_damage=50), "zero differential"),
    ],
)
def test_rejects_without_win_and_positive_differential(
    evidence: ModelSOAfterMatchLearningEvidence, reason: str
) -> None:
    assert _evaluator().evaluate(evidence=evidence, policy=_policy({"aggression": 1.0})) is None


@pytest.mark.unit
def test_returns_no_candidate_at_the_parameter_bound() -> None:
    at_cap = _policy({"aggression": 3.0})
    assert _evaluator().evaluate(evidence=_evidence(), policy=at_cap) is None


@pytest.mark.unit
def test_raises_on_non_numeric_learning_parameter() -> None:
    policy = _policy({"aggression": "high"})
    with pytest.raises(ValueError, match="must be numeric"):
        _evaluator().evaluate(evidence=_evidence(), policy=policy)


@pytest.mark.unit
def test_constructor_validates_configuration() -> None:
    with pytest.raises(ValueError, match="learning_player_id"):
        WinDamageDifferentialEvaluator(learning_player_id="")
    with pytest.raises(ValueError, match="step"):
        WinDamageDifferentialEvaluator(learning_player_id=_LEARNER, step=0.0)
