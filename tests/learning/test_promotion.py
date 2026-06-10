"""Tests for learning/promotion.py -- design s18 minting rules + s23.1 holdout gate.

All tests are @pytest.mark.unit. Known-value vectors are pinned, not recomputed.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.lineage import (
    ModelSOLineageGenerator,
    ParamDict,
    SOPromotionRejection,
    SOPromotionStatus,
    meta_hash,
    spec_hash,
)
from steel_onslaught.learning.promotion import (
    ModelSOPromotionThresholds,
    evaluate_promotion,
    param_distance,
)
from steel_onslaught.learning.protocols import (
    BoundsDict,
    ModelSOCategoricalBound,
    ModelSONumericBound,
    ModelSOPairedComparison,
    ModelSOSeedOutcome,
    SOSeedWinner,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

ARCHETYPE = "aggressive"
CANDIDATE_PARAMS: ParamDict = {"speed": 3, "aggression": 8}
PARENT_PARAMS: ParamDict = {"speed": 2, "aggression": 6}
BOUNDS: BoundsDict = {
    "speed": ModelSONumericBound(minimum=1, maximum=10, step=1),
    "aggression": ModelSONumericBound(minimum=1, maximum=10, step=1),
}

# Opponent pool
_OPPONENT_PARAMS: ParamDict = {"speed": 5, "aggression": 5}
OPPONENT_HASHES = [spec_hash("standard", _OPPONENT_PARAMS)]

GENERATOR = ModelSOLineageGenerator(
    generator_id="search.hill_climb",
    selection_reason="max win-rate neighbor",
)

# Thresholds (defaults)
THRESHOLDS = ModelSOPromotionThresholds()

# June 8 platform vector: 14 candidate / 2 parent / 34 ties -> p = 274/65536
# For the happy path we use 20-seed battery (14/2/4 draws) to keep draw_rate=0.2 <= 0.5.
# search_comparison uses the same decisive p-value as June 8 (14/2 decisive).
HAPPY_SEARCH_COMPARISON = ModelSOPairedComparison(
    n_seeds=20,
    candidate_wins=14,
    parent_wins=2,
    draws=4,
    p_value=0.004180908203125,  # 274/65536, verified arithmetic
    candidate_win_rate=0.875,  # 14/16 decisive
    ci_low=0.6398,
    ci_high=0.9650,
    effect_size=0.375,  # 0.875 - 0.5
)


def _make_search_outcomes(
    candidate_wins: int,
    parent_wins: int,
    draws: int,
    start_seed: int = 1,
    candidate_overloads: int = 0,
    parent_overloads: int = 0,
) -> list[ModelSOSeedOutcome]:
    """Build a flat list of outcomes: candidate wins first, then parent wins, then draws."""
    outcomes: list[ModelSOSeedOutcome] = []
    seed = start_seed
    for _ in range(candidate_wins):
        outcomes.append(
            ModelSOSeedOutcome(
                seed=seed,
                winner=SOSeedWinner.CANDIDATE,
                candidate_overloads=candidate_overloads,
                parent_overloads=parent_overloads,
            )
        )
        seed += 1
    for _ in range(parent_wins):
        outcomes.append(
            ModelSOSeedOutcome(
                seed=seed,
                winner=SOSeedWinner.PARENT,
                candidate_overloads=candidate_overloads,
                parent_overloads=parent_overloads,
            )
        )
        seed += 1
    for _ in range(draws):
        outcomes.append(
            ModelSOSeedOutcome(
                seed=seed,
                winner=SOSeedWinner.DRAW,
                candidate_overloads=candidate_overloads,
                parent_overloads=parent_overloads,
            )
        )
        seed += 1
    return outcomes


# Happy-path search outcomes: seeds 1-20 (14 cw / 2 pw / 4 draws)
HAPPY_SEARCH_OUTCOMES = _make_search_outcomes(14, 2, 4, start_seed=1)

# Holdout: seeds 101-110 (3 cw / 1 pw / 6 draws) - candidate leads
HAPPY_HOLDOUT_OUTCOMES = _make_search_outcomes(3, 1, 6, start_seed=101)


# ---------------------------------------------------------------------------
# ModelSOPromotionThresholds
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_thresholds_defaults() -> None:
    t = ModelSOPromotionThresholds()
    assert t.p_value_max == 0.05
    assert t.min_decisive_n == 10
    assert t.max_overload_rate_increase == 0.05
    assert t.max_draw_rate == 0.5
    assert t.min_param_distance == 0.05


@pytest.mark.unit
def test_thresholds_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelSOPromotionThresholds(p_value_max=0.0)  # gt=0
    with pytest.raises(ValidationError):
        ModelSOPromotionThresholds(p_value_max=1.1)  # le=1
    with pytest.raises(ValidationError):
        ModelSOPromotionThresholds(min_decisive_n=0)  # ge=1
    with pytest.raises(ValidationError):
        ModelSOPromotionThresholds(max_draw_rate=1.1)  # le=1


# ---------------------------------------------------------------------------
# param_distance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_param_distance_identical() -> None:
    assert param_distance(CANDIDATE_PARAMS, CANDIDATE_PARAMS, BOUNDS) == 0.0


@pytest.mark.unit
def test_param_distance_one_step_int() -> None:
    # speed 3 vs 2 across range 1-19 (width=18): |3-2|/18 = 1/18
    candidate: ParamDict = {"speed": 3, "aggression": 6}
    parent: ParamDict = {"speed": 2, "aggression": 6}
    bounds: BoundsDict = {
        "speed": ModelSONumericBound(minimum=1, maximum=19, step=1),
        "aggression": ModelSONumericBound(minimum=1, maximum=10, step=1),
    }
    # |3-2| / (19-1) = 1/18
    dist = param_distance(candidate, parent, bounds)
    assert abs(dist - 1 / 18) < 1e-9


@pytest.mark.unit
def test_param_distance_categorical_flip_dominates() -> None:
    bounds: BoundsDict = {
        "mode": ModelSOCategoricalBound(choices=("fast", "slow")),
        "speed": ModelSONumericBound(minimum=1, maximum=10, step=1),
    }
    candidate: ParamDict = {"mode": "fast", "speed": 2}
    parent: ParamDict = {"mode": "slow", "speed": 2}
    # categorical flip = 1.0 dominates numeric (0.0)
    assert param_distance(candidate, parent, bounds) == 1.0


@pytest.mark.unit
def test_param_distance_zero_width_numeric() -> None:
    bounds: BoundsDict = {
        "fixed": ModelSONumericBound(minimum=5, maximum=5, step=1),
    }
    p1: ParamDict = {"fixed": 5}
    p2: ParamDict = {"fixed": 5}
    assert param_distance(p1, p2, bounds) == 0.0


@pytest.mark.unit
def test_param_distance_key_mismatch_raises() -> None:
    px: ParamDict = {"x": 1}
    py: ParamDict = {"y": 1}
    with pytest.raises(ValueError):
        param_distance(px, py, BOUNDS)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_happy_path_promoted() -> None:
    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.PROMOTED
    assert record.promotion.rejection_reasons == ()


@pytest.mark.unit
def test_happy_path_spec_hash() -> None:
    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.spec_hash == spec_hash(ARCHETYPE, CANDIDATE_PARAMS)
    assert record.parent_hash == spec_hash(ARCHETYPE, PARENT_PARAMS)
    assert record.meta_hash == meta_hash(OPPONENT_HASHES)


@pytest.mark.unit
def test_happy_path_evidence_seeds() -> None:
    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.evidence.search_seeds == tuple(range(1, 21))
    assert record.evidence.holdout_seeds == tuple(range(101, 111))


@pytest.mark.unit
def test_happy_path_performance() -> None:
    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    perf = record.performance
    assert abs(perf.p_value - 0.004180908203125) < 1e-15
    assert abs(perf.candidate_win_rate - 0.875) < 1e-9
    assert perf.decisive_n == 16
    # draw_rate = 4/20 = 0.2
    assert abs(perf.draw_rate - 0.2) < 1e-9
    # no overloads in happy path -> delta = 0.0
    assert perf.overload_rate_delta == 0.0


# ---------------------------------------------------------------------------
# Rejection rules -- each one individually
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_wrong_direction_rejected() -> None:
    """Flip candidate_wins / parent_wins; direction fails independently of significance."""
    # Swap: 2 cw / 14 pw -> candidate loses. p stays 0.00418 (symmetric sign test) so
    # significance would pass if direction were not checked; proves they are independent.
    flipped_comparison = ModelSOPairedComparison(
        n_seeds=20,
        candidate_wins=2,
        parent_wins=14,
        draws=4,
        p_value=0.004180908203125,
        candidate_win_rate=2 / 16,
        ci_low=0.02,
        ci_high=0.40,
        effect_size=2 / 16 - 0.5,
    )
    flipped_outcomes = _make_search_outcomes(2, 14, 4, start_seed=1)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=flipped_comparison,
        search_outcomes=flipped_outcomes,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    assert SOPromotionRejection.WRONG_DIRECTION in record.promotion.rejection_reasons


@pytest.mark.unit
def test_not_significant_rejected() -> None:
    """6/4 decisive over 10 seeds -> p ~= 0.754 > 0.05; direction and n-floor pass."""
    # p for 6/4: 2 * sum(C(10,k) for k in 6..10) / 2^10
    # = 2*(210+120+45+10+1)/1024 = 2*386/1024 = 772/1024 = 193/256 ~= 0.75390625
    p_6_4 = 772 / 1024  # = 0.75390625
    comparison = ModelSOPairedComparison(
        n_seeds=10,
        candidate_wins=6,
        parent_wins=4,
        draws=0,
        p_value=p_6_4,
        candidate_win_rate=0.6,
        ci_low=0.3,
        ci_high=0.85,
        effect_size=0.1,
    )
    outcomes = _make_search_outcomes(6, 4, 0, start_seed=1)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=comparison,
        search_outcomes=outcomes,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    reasons = record.promotion.rejection_reasons
    assert SOPromotionRejection.NOT_SIGNIFICANT in reasons
    # direction passes (6 > 4), n-floor passes (10 >= 10)
    assert SOPromotionRejection.WRONG_DIRECTION not in reasons
    assert SOPromotionRejection.INSUFFICIENT_DECISIVE_N not in reasons


@pytest.mark.unit
def test_insufficient_decisive_n_rejected() -> None:
    """9/0 decisive -> p = 2/512 = 0.00390625 <= 0.05 (significant), yet n=9 < 10."""
    # p for 9/0: 2*(C(9,9))/2^9 = 2/512 = 0.00390625
    p_9_0 = 2 / 512
    comparison = ModelSOPairedComparison(
        n_seeds=9,
        candidate_wins=9,
        parent_wins=0,
        draws=0,
        p_value=p_9_0,
        candidate_win_rate=1.0,
        ci_low=0.7,
        ci_high=1.0,
        effect_size=0.5,
    )
    outcomes = _make_search_outcomes(9, 0, 0, start_seed=1)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=comparison,
        search_outcomes=outcomes,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    reasons = record.promotion.rejection_reasons
    assert SOPromotionRejection.INSUFFICIENT_DECISIVE_N in reasons
    # significant and in right direction, so these must NOT appear
    assert SOPromotionRejection.WRONG_DIRECTION not in reasons
    assert SOPromotionRejection.NOT_SIGNIFICANT not in reasons


@pytest.mark.unit
def test_overload_regression_rejected() -> None:
    """Candidate overloads per match exceed parent -> OVERLOAD_REGRESSION."""
    # candidate_overloads=1, parent_overloads=0 per match -> delta=1.0 > 0.05
    search_outcomes = [
        ModelSOSeedOutcome(
            seed=i,
            winner=SOSeedWinner.CANDIDATE
            if i <= 14
            else SOSeedWinner.PARENT
            if i <= 16
            else SOSeedWinner.DRAW,
            candidate_overloads=1,
            parent_overloads=0,
        )
        for i in range(1, 21)
    ]
    holdout_outcomes = [
        ModelSOSeedOutcome(
            seed=100 + i,
            winner=SOSeedWinner.CANDIDATE
            if i <= 3
            else SOSeedWinner.PARENT
            if i <= 4
            else SOSeedWinner.DRAW,
            candidate_overloads=1,
            parent_overloads=0,
        )
        for i in range(1, 11)
    ]

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=search_outcomes,
        holdout_outcomes=holdout_outcomes,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    assert SOPromotionRejection.OVERLOAD_REGRESSION in record.promotion.rejection_reasons


@pytest.mark.unit
def test_draw_rate_exceeded_rejected() -> None:
    """40-seed battery: 14/2/24 draws -> draw_rate = 0.6 > 0.5."""
    comparison = ModelSOPairedComparison(
        n_seeds=40,
        candidate_wins=14,
        parent_wins=2,
        draws=24,
        p_value=0.004180908203125,
        candidate_win_rate=0.875,
        ci_low=0.6398,
        ci_high=0.9650,
        effect_size=0.375,
    )
    outcomes = _make_search_outcomes(14, 2, 24, start_seed=1)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=comparison,
        search_outcomes=outcomes,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    assert SOPromotionRejection.DRAW_RATE_EXCEEDED in record.promotion.rejection_reasons


@pytest.mark.unit
def test_trivial_clone_rejected() -> None:
    """Candidate == parent -> distance 0.0 < 0.05 -> TRIVIAL_CLONE."""
    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=PARENT_PARAMS,  # same as parent
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    assert SOPromotionRejection.TRIVIAL_CLONE in record.promotion.rejection_reasons


@pytest.mark.unit
def test_holdout_regression_rejected() -> None:
    """Holdout: candidate 1 / parent 3 -> holdout_cw < holdout_pw -> HOLDOUT_REGRESSION."""
    holdout_outcomes = _make_search_outcomes(1, 3, 6, start_seed=101)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=holdout_outcomes,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    assert SOPromotionRejection.HOLDOUT_REGRESSION in record.promotion.rejection_reasons


# ---------------------------------------------------------------------------
# Multi-failure: all failing rules reported in a single record
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_multi_failure_not_significant_and_trivial_clone() -> None:
    """Fail significance (p=0.754) and clone distance (0.0) -> both reasons in record."""
    p_6_4 = 772 / 1024
    comparison = ModelSOPairedComparison(
        n_seeds=10,
        candidate_wins=6,
        parent_wins=4,
        draws=0,
        p_value=p_6_4,
        candidate_win_rate=0.6,
        ci_low=0.3,
        ci_high=0.85,
        effect_size=0.1,
    )
    outcomes = _make_search_outcomes(6, 4, 0, start_seed=1)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=PARENT_PARAMS,  # clone
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=comparison,
        search_outcomes=outcomes,
        holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    reasons = record.promotion.rejection_reasons
    assert SOPromotionRejection.NOT_SIGNIFICANT in reasons
    assert SOPromotionRejection.TRIVIAL_CLONE in reasons


# ---------------------------------------------------------------------------
# Rejection records carry full lineage data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rejection_record_has_intact_hashes_and_evidence() -> None:
    """Rejected records are s19 evidence: hashes and evidence must be populated."""
    holdout_outcomes = _make_search_outcomes(1, 3, 6, start_seed=101)

    record = evaluate_promotion(
        archetype=ARCHETYPE,
        candidate_params=CANDIDATE_PARAMS,
        parent_params=PARENT_PARAMS,
        bounds=BOUNDS,
        search_comparison=HAPPY_SEARCH_COMPARISON,
        search_outcomes=HAPPY_SEARCH_OUTCOMES,
        holdout_outcomes=holdout_outcomes,
        opponent_spec_hashes=OPPONENT_HASHES,
        generator=GENERATOR,
        thresholds=THRESHOLDS,
    )

    assert record.promotion.status == SOPromotionStatus.REJECTED
    assert record.spec_hash == spec_hash(ARCHETYPE, CANDIDATE_PARAMS)
    assert record.parent_hash == spec_hash(ARCHETYPE, PARENT_PARAMS)
    assert record.meta_hash == meta_hash(OPPONENT_HASHES)
    assert record.evidence.search_seeds == tuple(range(1, 21))
    assert record.evidence.holdout_seeds == tuple(range(101, 111))


# ---------------------------------------------------------------------------
# Fail-fast raises (harness bugs -- must not produce REJECTED records)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_out_of_range_candidate_raises() -> None:
    bad_params: ParamDict = {"speed": 100, "aggression": 8}  # 100 > max=10
    with pytest.raises(ValueError):
        evaluate_promotion(
            archetype=ARCHETYPE,
            candidate_params=bad_params,
            parent_params=PARENT_PARAMS,
            bounds=BOUNDS,
            search_comparison=HAPPY_SEARCH_COMPARISON,
            search_outcomes=HAPPY_SEARCH_OUTCOMES,
            holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
            opponent_spec_hashes=OPPONENT_HASHES,
            generator=GENERATOR,
            thresholds=THRESHOLDS,
        )


@pytest.mark.unit
def test_overlapping_search_holdout_seeds_raises() -> None:
    # seeds 1-10 overlap with search seeds 1-20
    overlap_holdout = _make_search_outcomes(3, 1, 6, start_seed=1)

    with pytest.raises(ValueError, match="overlap"):
        evaluate_promotion(
            archetype=ARCHETYPE,
            candidate_params=CANDIDATE_PARAMS,
            parent_params=PARENT_PARAMS,
            bounds=BOUNDS,
            search_comparison=HAPPY_SEARCH_COMPARISON,
            search_outcomes=HAPPY_SEARCH_OUTCOMES,
            holdout_outcomes=overlap_holdout,
            opponent_spec_hashes=OPPONENT_HASHES,
            generator=GENERATOR,
            thresholds=THRESHOLDS,
        )


@pytest.mark.unit
def test_search_comparison_mismatch_raises() -> None:
    """search_comparison.candidate_wins disagrees with search_outcomes -> ValueError."""
    stale_comparison = ModelSOPairedComparison(
        n_seeds=20,
        candidate_wins=10,  # wrong: outcomes have 14
        parent_wins=6,
        draws=4,
        p_value=0.118,
        candidate_win_rate=10 / 16,
        ci_low=0.39,
        ci_high=0.82,
        effect_size=10 / 16 - 0.5,
    )

    with pytest.raises(ValueError):
        evaluate_promotion(
            archetype=ARCHETYPE,
            candidate_params=CANDIDATE_PARAMS,
            parent_params=PARENT_PARAMS,
            bounds=BOUNDS,
            search_comparison=stale_comparison,
            search_outcomes=HAPPY_SEARCH_OUTCOMES,
            holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
            opponent_spec_hashes=OPPONENT_HASHES,
            generator=GENERATOR,
            thresholds=THRESHOLDS,
        )


@pytest.mark.unit
def test_duplicate_seeds_in_search_outcomes_raises() -> None:
    dup_outcomes = list(HAPPY_SEARCH_OUTCOMES)
    # Replace last entry with seed=1 (duplicate of first)
    dup_outcomes[-1] = ModelSOSeedOutcome(
        seed=1,
        winner=SOSeedWinner.DRAW,
        candidate_overloads=0,
        parent_overloads=0,
    )

    with pytest.raises(ValueError, match="duplicate"):
        evaluate_promotion(
            archetype=ARCHETYPE,
            candidate_params=CANDIDATE_PARAMS,
            parent_params=PARENT_PARAMS,
            bounds=BOUNDS,
            search_comparison=HAPPY_SEARCH_COMPARISON,
            search_outcomes=dup_outcomes,
            holdout_outcomes=HAPPY_HOLDOUT_OUTCOMES,
            opponent_spec_hashes=OPPONENT_HASHES,
            generator=GENERATOR,
            thresholds=THRESHOLDS,
        )


# ---------------------------------------------------------------------------
# Purity static check: promotion.py must not import stats.py or search.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_promotion_does_not_import_stats_or_search() -> None:
    """Architectural Decision #4: the gate consumes precomputed inputs; it never
    calls stats.py or search.py. Composition is Phase 2's job."""
    import steel_onslaught.learning.promotion as _mod

    source = inspect.getsource(_mod)
    assert "from steel_onslaught.learning.stats" not in source
    assert "import steel_onslaught.learning.stats" not in source
    assert "from steel_onslaught.learning.search" not in source
    assert "import steel_onslaught.learning.search" not in source
