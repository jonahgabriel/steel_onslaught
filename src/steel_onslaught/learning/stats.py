"""Exact binomial sign test, Wilson CI, and paired comparison summary.

All arithmetic uses stdlib only (math module). No scipy, no numpy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from steel_onslaught.learning.protocols import (
    ModelSOPairedComparison,
    ModelSOSeedOutcome,
    SOSeedWinner,
)


def exact_binomial_sign_test(wins_a: int, wins_b: int) -> float:
    """Two-sided exact binomial sign test on tie-excluded paired wins.

    H0: P(a beats b) = 0.5. With n = wins_a + wins_b and k = max(wins_a,
    wins_b), returns min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2**n).
    n == 0 returns 1.0. Negative inputs raise ValueError. stdlib only.
    """
    if wins_a < 0 or wins_b < 0:
        raise ValueError(
            f"wins_a and wins_b must be non-negative; got wins_a={wins_a}, wins_b={wins_b}"
        )
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = max(wins_a, wins_b)
    tail_sum: int = 0
    for i in range(k, n + 1):
        tail_sum += math.comb(n, i)
    denom: int = 1 << n  # 2**n as an explicit int shift, unambiguously int
    p: float = 2 * tail_sum / denom
    return min(1.0, p)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval on successes/n (default 95%). n == 0 returns
    (0.0, 1.0). successes > n or negative inputs raise ValueError.
    """
    if successes < 0 or n < 0:
        raise ValueError(f"successes and n must be non-negative; got successes={successes}, n={n}")
    if successes > n:
        raise ValueError(f"successes ({successes}) must not exceed n ({n})")
    if n == 0:
        return (0.0, 1.0)
    p_hat = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p_hat + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n)) / denom
    low = max(0.0, centre - margin)
    high = min(1.0, centre + margin)
    return (low, high)


def paired_comparison(outcomes: Sequence[ModelSOSeedOutcome]) -> ModelSOPairedComparison:
    """Fold per-seed outcomes into the Task-1 summary model.

    candidate_win_rate is over decisive (non-draw) trials only; with zero
    decisive trials it is 0.5 with CI (0.0, 1.0) and p 1.0. Duplicate seeds
    raise ValueError.
    """
    seen_seeds: set[int] = set()
    for outcome in outcomes:
        if outcome.seed in seen_seeds:
            raise ValueError(f"duplicate seed {outcome.seed} in outcomes")
        seen_seeds.add(outcome.seed)

    n_seeds = len(outcomes)
    candidate_wins = sum(1 for o in outcomes if o.winner is SOSeedWinner.CANDIDATE)
    parent_wins = sum(1 for o in outcomes if o.winner is SOSeedWinner.PARENT)
    draws = sum(1 for o in outcomes if o.winner is SOSeedWinner.DRAW)

    decisive_n = candidate_wins + parent_wins

    if decisive_n == 0:
        p_value = 1.0
        candidate_win_rate = 0.5
        ci_low = 0.0
        ci_high = 1.0
        effect_size = 0.0
    else:
        p_value = exact_binomial_sign_test(candidate_wins, parent_wins)
        candidate_win_rate = candidate_wins / decisive_n
        ci_low, ci_high = wilson_interval(candidate_wins, decisive_n)
        effect_size = candidate_win_rate - 0.5

    return ModelSOPairedComparison(
        n_seeds=n_seeds,
        candidate_wins=candidate_wins,
        parent_wins=parent_wins,
        draws=draws,
        p_value=p_value,
        candidate_win_rate=candidate_win_rate,
        ci_low=ci_low,
        ci_high=ci_high,
        effect_size=effect_size,
    )
