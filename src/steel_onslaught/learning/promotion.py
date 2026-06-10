"""Promotion gate: design §18 minting rules + §23.1 hidden-seed holdout.

Every minting rule is evaluated; all failures are collected before the record is
built (no first-fail short-circuit). Rejections emit full lineage records because
rejections are §19 evidence. Harness bugs (inconsistent inputs, out-of-range
parameters, seed overlaps) raise ValueError, never produce verdicts.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

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
from steel_onslaught.learning.protocols import (
    BoundsDict,
    ModelSONumericBound,
    ModelSOPairedComparison,
    ModelSOSeedOutcome,
    SOSeedWinner,
)


class ModelSOPromotionThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    p_value_max: float = Field(default=0.05, gt=0.0, le=1.0)
    min_decisive_n: int = Field(default=10, ge=1)  # n < 10 is exploratory (no-overclaim)
    max_overload_rate_increase: float = Field(default=0.05, ge=0.0)
    max_draw_rate: float = Field(default=0.5, ge=0.0, le=1.0)
    min_param_distance: float = Field(default=0.05, ge=0.0, le=1.0)


def param_distance(candidate: ParamDict, parent: ParamDict, bounds: BoundsDict) -> float:
    """Normalized L-infinity distance: per numeric parameter
    |c - p| / (maximum - minimum) (0.0 when maximum == minimum); per
    categorical parameter 0.0 if equal else 1.0; distance = max over
    parameters. Key sets of candidate, parent, and bounds must all match;
    mismatch raises ValueError.
    """
    if set(candidate.keys()) != set(bounds.keys()):
        raise ValueError(
            f"candidate keys {set(candidate.keys())} do not match bounds keys {set(bounds.keys())}"
        )
    if set(parent.keys()) != set(bounds.keys()):
        raise ValueError(
            f"parent keys {set(parent.keys())} do not match bounds keys {set(bounds.keys())}"
        )

    max_dist = 0.0
    for key, bound in bounds.items():
        c_val = candidate[key]
        p_val = parent[key]
        if isinstance(bound, ModelSONumericBound):
            span = bound.maximum - bound.minimum
            if span == 0.0:
                dist = 0.0
            else:
                dist = abs(float(c_val) - float(p_val)) / span
        else:
            # categorical
            dist = 0.0 if c_val == p_val else 1.0
        if dist > max_dist:
            max_dist = dist

    return max_dist


def _check_params_in_bounds(params: ParamDict, bounds: BoundsDict, label: str) -> None:
    """Raise ValueError if params keys mismatch bounds or any value is out of range."""
    if set(params.keys()) != set(bounds.keys()):
        raise ValueError(
            f"{label} keys {set(params.keys())} do not match bounds keys {set(bounds.keys())}"
        )
    for key, bound in bounds.items():
        val = params[key]
        if isinstance(bound, ModelSONumericBound):
            fval = float(val)
            if fval < bound.minimum - 1e-9 or fval > bound.maximum + 1e-9:
                raise ValueError(
                    f"{label} parameter {key!r}={val!r} is out of range "
                    f"[{bound.minimum}, {bound.maximum}]"
                )
        else:
            if val not in bound.choices:
                raise ValueError(
                    f"{label} parameter {key!r}={val!r} is not in choices {bound.choices}"
                )


def _check_no_duplicate_seeds(outcomes: Sequence[ModelSOSeedOutcome], label: str) -> None:
    seeds = [o.seed for o in outcomes]
    seen: set[int] = set()
    for s in seeds:
        if s in seen:
            raise ValueError(f"duplicate seed {s} in {label}")
        seen.add(s)


def _recompute_wins(
    outcomes: Sequence[ModelSOSeedOutcome],
) -> tuple[int, int, int]:
    """Return (candidate_wins, parent_wins, draws)."""
    cw = pw = draws = 0
    for o in outcomes:
        if o.winner is SOSeedWinner.CANDIDATE:
            cw += 1
        elif o.winner is SOSeedWinner.PARENT:
            pw += 1
        else:
            draws += 1
    return cw, pw, draws


def _compute_overload_rate_delta(
    search_outcomes: Sequence[ModelSOSeedOutcome],
    holdout_outcomes: Sequence[ModelSOSeedOutcome],
) -> float:
    """Overload-rate delta: (candidate overloads - parent overloads) / total outcomes."""
    all_outcomes = list(search_outcomes) + list(holdout_outcomes)
    n = len(all_outcomes)
    if n == 0:
        return 0.0
    candidate_total = sum(o.candidate_overloads for o in all_outcomes)
    parent_total = sum(o.parent_overloads for o in all_outcomes)
    return (candidate_total - parent_total) / n


def evaluate_promotion(
    *,
    archetype: str,
    candidate_params: ParamDict,
    parent_params: ParamDict,
    bounds: BoundsDict,
    search_comparison: ModelSOPairedComparison,
    search_outcomes: Sequence[ModelSOSeedOutcome],
    holdout_outcomes: Sequence[ModelSOSeedOutcome],
    opponent_spec_hashes: Sequence[str],
    generator: ModelSOLineageGenerator,
    thresholds: ModelSOPromotionThresholds,
) -> ModelSOLineageRecord:
    """Apply every minting rule; emit a lineage record for EVERY verdict
    (rejections are evidence too). All failed rules are reported, not
    first-fail (MVP budget-validator style).
    """
    # ---- Fail-fast harness checks (raise, never produce a verdict) ----

    # 1. Bounds checks
    _check_params_in_bounds(candidate_params, bounds, "candidate")
    _check_params_in_bounds(parent_params, bounds, "parent")

    # 2. No duplicate seeds
    _check_no_duplicate_seeds(search_outcomes, "search_outcomes")
    _check_no_duplicate_seeds(holdout_outcomes, "holdout_outcomes")

    # 3. Neither outcome list is empty
    if not search_outcomes:
        raise ValueError("search_outcomes must not be empty")
    if not holdout_outcomes:
        raise ValueError("holdout_outcomes must not be empty")

    # 4. Search / holdout seed sets must not overlap
    search_seed_set = {o.seed for o in search_outcomes}
    holdout_seed_set = {o.seed for o in holdout_outcomes}
    overlap = search_seed_set & holdout_seed_set
    if overlap:
        raise ValueError(f"search and holdout seeds overlap: {sorted(overlap)}")

    # 5. search_comparison must be consistent with search_outcomes
    recomputed_cw, recomputed_pw, recomputed_draws = _recompute_wins(search_outcomes)
    recomputed_n = len(search_outcomes)
    if (
        recomputed_cw != search_comparison.candidate_wins
        or recomputed_pw != search_comparison.parent_wins
        or recomputed_draws != search_comparison.draws
        or recomputed_n != search_comparison.n_seeds
    ):
        raise ValueError(
            f"search_comparison is inconsistent with search_outcomes: "
            f"outcomes give ({recomputed_cw}/{recomputed_pw}/{recomputed_draws}/{recomputed_n}) "
            f"but comparison has "
            f"({search_comparison.candidate_wins}/{search_comparison.parent_wins}/"
            f"{search_comparison.draws}/{search_comparison.n_seeds})"
        )

    # ---- Collect rejection reasons (all rules, no short-circuit) ----
    reasons: list[SOPromotionRejection] = []

    # Rule: direction — candidate must win more than parent
    if search_comparison.candidate_wins <= search_comparison.parent_wins:
        reasons.append(SOPromotionRejection.WRONG_DIRECTION)

    # Rule: significance
    if search_comparison.p_value > thresholds.p_value_max:
        reasons.append(SOPromotionRejection.NOT_SIGNIFICANT)

    # Rule: no-overclaim floor (decisive n)
    decisive_n = search_comparison.candidate_wins + search_comparison.parent_wins
    if decisive_n < thresholds.min_decisive_n:
        reasons.append(SOPromotionRejection.INSUFFICIENT_DECISIVE_N)

    # Rule: overload regression (search + holdout combined)
    overload_rate_delta = _compute_overload_rate_delta(search_outcomes, holdout_outcomes)
    if overload_rate_delta > thresholds.max_overload_rate_increase:
        reasons.append(SOPromotionRejection.OVERLOAD_REGRESSION)

    # Rule: draw rate (search only, n_seeds guaranteed > 0 from fail-fast above)
    draw_rate = search_comparison.draws / search_comparison.n_seeds
    if draw_rate > thresholds.max_draw_rate:
        reasons.append(SOPromotionRejection.DRAW_RATE_EXCEEDED)

    # Rule: trivial clone
    distance = param_distance(candidate_params, parent_params, bounds)
    if distance < thresholds.min_param_distance:
        reasons.append(SOPromotionRejection.TRIVIAL_CLONE)

    # Rule: §23.1 holdout hidden-seed evaluation — candidate wins >= parent wins
    holdout_cw, holdout_pw, _ = _recompute_wins(holdout_outcomes)
    if holdout_cw < holdout_pw:
        reasons.append(SOPromotionRejection.HOLDOUT_REGRESSION)

    # ---- Build the lineage record ----
    status = SOPromotionStatus.PROMOTED if not reasons else SOPromotionStatus.REJECTED

    promotion = ModelSOLineagePromotion(
        status=status,
        rejection_reasons=tuple(reasons),
    )

    evidence = ModelSOLineageEvidence(
        search_seeds=tuple(o.seed for o in search_outcomes),
        holdout_seeds=tuple(o.seed for o in holdout_outcomes),
    )

    performance = ModelSOLineagePerformance(
        candidate_win_rate=search_comparison.candidate_win_rate,
        win_rate_delta=search_comparison.effect_size,
        overload_rate_delta=overload_rate_delta,
        draw_rate=draw_rate,
        p_value=search_comparison.p_value,
        decisive_n=decisive_n,
    )

    candidate_spec_hash = spec_hash(archetype, candidate_params)
    parent_spec_hash = spec_hash(archetype, parent_params)
    opponent_meta_hash = meta_hash(opponent_spec_hashes)

    return ModelSOLineageRecord(
        archetype=archetype,
        parameters=candidate_params,
        spec_hash=candidate_spec_hash,
        parent_hash=parent_spec_hash,
        meta_hash=opponent_meta_hash,
        evidence=evidence,
        performance=performance,
        generator=generator,
        promotion=promotion,
    )
