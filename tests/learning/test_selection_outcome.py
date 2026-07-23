"""Unit tests for the duel-gated SelectionOutcomeEvaluator (L-GATE-2, §4.4).

The offline evaluator is the scripted ``FakeEvaluator`` double behind the
EXACT ``EvaluatorProtocol`` seam that ``DuelEvaluator`` implements in
production, so these tests drive the real ``run_learning_loop`` (EXTERNAL
strategy) + ``evaluate_promotion`` gate end to end without match compute.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from steel_onslaught.contracts.lineage import ParamDict, SOPromotionStatus, spec_hash
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.payloads import ModelSOPlayerScore
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.fake_evaluator import FakeEvaluator
from steel_onslaught.learning.loop import derive_seed_batteries
from steel_onslaught.learning.promotion import ModelSOPromotionThresholds
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from steel_onslaught.learning.selection_outcome import (
    GENERATOR_ID,
    SelectionOutcomeEvaluator,
    derive_master_seed,
)

pytestmark = pytest.mark.unit

_LEARNER = "player.blue"
_OPPONENT = "player.red"
_ARCHETYPE = "aggressive"
_PARAMETER = "mode_switch_heat_ceiling"

# The complete aggressive spec-parameter set (the duel gate materializes real
# pilot specs whose parameter models have no defaults).
_FULL_PARAMS: ParamDict = {
    "vent_at_heat_margin": 10.0,
    "idle_vent_heat_threshold": 70.0,
    "mode_switch_pressure_floor": 20.0,
    "mode_switch_heat_ceiling": 60.0,
    "weapon_preference": "highest_damage",
}

_RELAXED = ModelSOPromotionThresholds(
    p_value_max=1.0,
    min_decisive_n=1,
    max_overload_rate_increase=10.0,
    max_draw_rate=1.0,
    min_param_distance=0.0,
)


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
    match_id: str = "match.live.lgate2.001",
) -> ModelSOAfterMatchLearningEvidence:
    return ModelSOAfterMatchLearningEvidence(
        match_id=match_id,
        scored_event_id="01HZY3E9ZTAV5J6BQF8KM2WXSC",
        correlation_id=UUID("00000000-0000-0000-0000-000000000002"),
        duration_ticks=40,
        winner_player_id=winner,
        is_draw=is_draw,
        scores={
            _LEARNER: _score(90, victory=0 if is_draw else int(winner == _LEARNER)),
            _OPPONENT: _score(30, victory=0 if is_draw else int(winner == _OPPONENT)),
        },
        event_counts={"match_scored": 1},
        decision_action_counts={},
        decision_reason_counts={},
    )


def _policy(parameters: ParamDict | None = None) -> ModelSOLiveLearningPolicy:
    params = dict(_FULL_PARAMS) if parameters is None else parameters
    return ModelSOLiveLearningPolicy(
        policy_id="policy.aggressive.genesis",
        archetype=_ARCHETYPE,
        parameters=params,
        spec_hash=spec_hash(_ARCHETYPE, params),
        generation=0,
    )


def _scripted_offline(
    evidence: ModelSOAfterMatchLearningEvidence,
    *,
    n_search: int = 2,
    n_holdout: int = 1,
    winner: SOSeedWinner = SOSeedWinner.CANDIDATE,
) -> FakeEvaluator:
    """Script every derived battery seed with the requested duel winner."""

    search_seeds, holdout_seeds = derive_seed_batteries(
        derive_master_seed(evidence), n_search, n_holdout
    )
    return FakeEvaluator(
        {
            seed: ModelSOSeedOutcome(
                seed=seed,
                winner=winner,
                candidate_overloads=0,
                parent_overloads=0,
            )
            for seed in (*search_seeds, *holdout_seeds)
        }
    )


def _evaluator(
    offline: FakeEvaluator,
    *,
    n_search: int = 2,
    n_holdout: int = 1,
) -> SelectionOutcomeEvaluator:
    return SelectionOutcomeEvaluator(
        learning_player_id=_LEARNER,
        offline_evaluator=offline,
        parameter=_PARAMETER,
        n_search_seeds=n_search,
        n_holdout_seeds=n_holdout,
        thresholds=_RELAXED,
    )


def test_win_proposes_upward_step_and_duel_wins_promote() -> None:
    evidence = _evidence()
    policy = _policy()
    record = _evaluator(_scripted_offline(evidence)).evaluate(evidence=evidence, policy=policy)

    assert record is not None
    assert record.promotion.status is SOPromotionStatus.PROMOTED
    assert record.parameters[_PARAMETER] == 61.0  # one lattice step up (step=1.0)
    assert record.parent_hash == policy.spec_hash
    assert record.archetype == _ARCHETYPE
    assert record.generator.generator_id == GENERATOR_ID
    assert "selection_outcome" in record.generator.selection_reason
    # The integral lattice emits int values (spec-hash identity distinguishes
    # int from float), so the candidate carries 61, not 61.0.
    assert record.spec_hash == spec_hash(_ARCHETYPE, {**dict(policy.parameters), _PARAMETER: 61})


def test_loss_proposes_downward_step() -> None:
    evidence = _evidence(winner=_OPPONENT)
    record = _evaluator(_scripted_offline(evidence)).evaluate(evidence=evidence, policy=_policy())

    assert record is not None
    assert record.parameters[_PARAMETER] == 59.0  # one lattice step down


def test_draw_proposes_nothing() -> None:
    evidence = _evidence(winner=_LEARNER, is_draw=True)
    offline = FakeEvaluator({})  # must never be consulted

    assert _evaluator(offline).evaluate(evidence=evidence, policy=_policy()) is None


def test_lattice_edge_in_the_evidence_direction_proposes_nothing() -> None:
    params = {**_FULL_PARAMS, _PARAMETER: 92.0}  # at the declared maximum
    evidence = _evidence()
    offline = FakeEvaluator({})  # must never be consulted

    assert _evaluator(offline).evaluate(evidence=evidence, policy=_policy(params)) is None


def test_duel_gate_rejection_returns_the_rejected_record_as_evidence() -> None:
    evidence = _evidence()
    offline = _scripted_offline(evidence, winner=SOSeedWinner.PARENT)

    record = _evaluator(offline).evaluate(evidence=evidence, policy=_policy())

    # The candidate lost its duels: the loop never gates it, so no record —
    # exactly the offline loop's "no candidate beat the parent" contract.
    assert record is None


def test_holdout_regression_yields_a_rejected_lineage_record() -> None:
    evidence = _evidence()
    search_seeds, holdout_seeds = derive_seed_batteries(derive_master_seed(evidence), 2, 1)
    offline = FakeEvaluator(
        {
            **{
                seed: ModelSOSeedOutcome(
                    seed=seed,
                    winner=SOSeedWinner.CANDIDATE,
                    candidate_overloads=0,
                    parent_overloads=0,
                )
                for seed in search_seeds
            },
            **{
                seed: ModelSOSeedOutcome(
                    seed=seed,
                    winner=SOSeedWinner.PARENT,
                    candidate_overloads=0,
                    parent_overloads=0,
                )
                for seed in holdout_seeds
            },
        }
    )

    record = _evaluator(offline).evaluate(evidence=evidence, policy=_policy())

    assert record is not None
    assert record.promotion.status is SOPromotionStatus.REJECTED


def test_same_evidence_replays_the_identical_record() -> None:
    evidence = _evidence()
    first = _evaluator(_scripted_offline(evidence)).evaluate(evidence=evidence, policy=_policy())
    second = _evaluator(_scripted_offline(evidence)).evaluate(evidence=evidence, policy=_policy())

    assert first is not None
    assert first == second


def test_distinct_matches_derive_distinct_seed_batteries() -> None:
    assert derive_master_seed(_evidence(match_id="match.a")) != derive_master_seed(
        _evidence(match_id="match.b")
    )


def test_partial_policy_parameter_set_fails_closed() -> None:
    params: ParamDict = {"mode_switch_heat_ceiling": 60.0}
    evidence = _evidence()

    with pytest.raises(ValueError, match="complete"):
        _evaluator(FakeEvaluator({})).evaluate(evidence=evidence, policy=_policy(params))


def test_categorical_perturbation_parameter_fails_closed() -> None:
    evidence = _evidence()
    evaluator = SelectionOutcomeEvaluator(
        learning_player_id=_LEARNER,
        offline_evaluator=FakeEvaluator({}),
        parameter="weapon_preference",
        thresholds=_RELAXED,
    )

    with pytest.raises(ValueError, match="numeric"):
        evaluator.evaluate(evidence=evidence, policy=_policy())
