"""Tests for learning/stats.py — exact binomial sign test, Wilson CI, paired comparison.

Known-value vectors are pinned, not recomputed by the test. The June 8 platform
experiment reported "p = 0.0042" from 14 context-wins / 2 off-wins / 34 ties;
the exact dyadic rational is 274/65536 = 0.004180908203125 (re-verified for this plan).
"""

from __future__ import annotations

import inspect

import pytest

from steel_onslaught.learning.protocols import (
    ModelSOPairedComparison,
    ModelSOSeedOutcome,
    SOSeedWinner,
)
from steel_onslaught.learning.stats import (
    exact_binomial_sign_test,
    paired_comparison,
    wilson_interval,
)

# ---------------------------------------------------------------------------
# Purity static check
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stats_purity_static_check() -> None:
    """stats.py must import only math, collections.abc, and Task-1 modules."""
    import steel_onslaught.learning.stats as stats_module

    source = inspect.getsource(stats_module)
    # Allowed import roots
    allowed_prefixes = (
        "import math",
        "from math",
        "import collections",
        "from collections",
        "from steel_onslaught",
        "from __future__",
    )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert any(stripped.startswith(p) for p in allowed_prefixes), (
                f"stats.py contains disallowed import: {stripped!r}"
            )


# ---------------------------------------------------------------------------
# exact_binomial_sign_test — known-value pinned vectors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_exact_binomial_june8_vector() -> None:
    """June 8 context experiment: 14 context-wins / 2 off-wins / 34 ties.

    Exact dyadic rational: 274/65536 = 0.004180908203125.
    The published "p = 0.0042" is this value rounded.
    """
    result = exact_binomial_sign_test(14, 2)
    assert abs(result - 274 / 65536) < 1e-15
    assert abs(result - 0.004180908203125) < 1e-15


@pytest.mark.unit
def test_exact_binomial_june8_phase2_vector() -> None:
    """June 8 phase-2 vector: 8 wins / 0 losses. p = 2/256 = 0.0078125."""
    result = exact_binomial_sign_test(8, 0)
    assert result == 0.0078125


@pytest.mark.unit
def test_exact_binomial_symmetry() -> None:
    """Two-sided test is symmetric: (2, 14) == (14, 2)."""
    assert exact_binomial_sign_test(2, 14) == exact_binomial_sign_test(14, 2)


@pytest.mark.unit
def test_exact_binomial_clamp_equal() -> None:
    """(1, 1): raw two-sided value 1.5 clamps to 1.0."""
    assert exact_binomial_sign_test(1, 1) == 1.0


@pytest.mark.unit
def test_exact_binomial_zero_zero() -> None:
    """(0, 0): n == 0 returns 1.0 by convention."""
    assert exact_binomial_sign_test(0, 0) == 1.0


@pytest.mark.unit
def test_exact_binomial_monotonicity() -> None:
    """More extreme wins → lower p-value (spot check)."""
    assert (
        exact_binomial_sign_test(10, 0)
        < exact_binomial_sign_test(9, 1)
        < exact_binomial_sign_test(6, 4)
    )


@pytest.mark.unit
def test_exact_binomial_negative_input_raises() -> None:
    with pytest.raises(ValueError):
        exact_binomial_sign_test(-1, 5)

    with pytest.raises(ValueError):
        exact_binomial_sign_test(5, -1)


# ---------------------------------------------------------------------------
# wilson_interval — known-value vectors (closed-form, z=1.96)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_wilson_interval_june8_decisive() -> None:
    """Wilson(14, 16) ≈ (0.6398, 0.9650) within 5e-4."""
    low, high = wilson_interval(14, 16)
    assert abs(low - 0.6398) < 5e-4
    assert abs(high - 0.9650) < 5e-4


@pytest.mark.unit
def test_wilson_interval_zero_successes() -> None:
    """Wilson(0, 10): low == 0.0 exactly; high ≈ 0.2775 within 5e-4."""
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert abs(high - 0.2775) < 5e-4


@pytest.mark.unit
def test_wilson_interval_all_successes() -> None:
    """Wilson(10, 10): high == 1.0 within 1e-12; mirror of Wilson(0, 10)."""
    low, high = wilson_interval(10, 10)
    assert abs(high - 1.0) < 1e-12
    # Mirror: low of (10,10) == 1 - high of (0,10)
    _, high_zero = wilson_interval(0, 10)
    assert abs(low - (1.0 - high_zero)) < 1e-12


@pytest.mark.unit
def test_wilson_interval_zero_n() -> None:
    """Wilson(0, 0) == (0.0, 1.0)."""
    assert wilson_interval(0, 0) == (0.0, 1.0)


@pytest.mark.unit
def test_wilson_interval_successes_gt_n_raises() -> None:
    with pytest.raises(ValueError):
        wilson_interval(5, 3)


@pytest.mark.unit
def test_wilson_interval_negative_raises() -> None:
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)

    with pytest.raises(ValueError):
        wilson_interval(0, -1)


# ---------------------------------------------------------------------------
# paired_comparison
# ---------------------------------------------------------------------------


def _make_outcomes(
    seeds: list[int],
    winner_map: dict[int, SOSeedWinner],
    candidate_overloads: int = 0,
    parent_overloads: int = 0,
) -> list[ModelSOSeedOutcome]:
    return [
        ModelSOSeedOutcome(
            seed=s,
            winner=winner_map.get(s, SOSeedWinner.DRAW),
            candidate_overloads=candidate_overloads,
            parent_overloads=parent_overloads,
        )
        for s in seeds
    ]


def _june8_battery() -> list[ModelSOSeedOutcome]:
    """50-outcome battery: 14 candidate / 2 parent / 34 draws (seeds 1-50).

    Seeds 1-14 → CANDIDATE, seeds 15-16 → PARENT, seeds 17-50 → DRAW.
    """
    outcomes = []
    for s in range(1, 51):
        if s <= 14:
            winner = SOSeedWinner.CANDIDATE
        elif s <= 16:
            winner = SOSeedWinner.PARENT
        else:
            winner = SOSeedWinner.DRAW
        outcomes.append(
            ModelSOSeedOutcome(
                seed=s,
                winner=winner,
                candidate_overloads=0,
                parent_overloads=0,
            )
        )
    return outcomes


@pytest.mark.unit
def test_paired_comparison_june8_battery() -> None:
    """50-outcome battery: 14/2/34. Verify all known-value pins."""
    result = paired_comparison(_june8_battery())
    assert result.n_seeds == 50
    assert result.candidate_wins == 14
    assert result.parent_wins == 2
    assert result.draws == 34
    # p_value: exact dyadic 274/65536
    assert abs(result.p_value - 0.004180908203125) < 1e-15
    # candidate_win_rate: 14/16 = 0.875 (decisive only)
    assert abs(result.candidate_win_rate - 0.875) < 1e-12
    # effect_size: 0.875 - 0.5 = 0.375
    assert abs(result.effect_size - 0.375) < 1e-12
    # Wilson CI ≈ (0.6398, 0.9650) within 5e-4
    assert abs(result.ci_low - 0.6398) < 5e-4
    assert abs(result.ci_high - 0.9650) < 5e-4


@pytest.mark.unit
def test_paired_comparison_empty() -> None:
    """Empty battery: n_seeds == 0, p == 1.0, win_rate == 0.5, CI == (0.0, 1.0)."""
    result = paired_comparison([])
    assert result.n_seeds == 0
    assert result.p_value == 1.0
    assert result.candidate_win_rate == 0.5
    assert result.ci_low == 0.0
    assert result.ci_high == 1.0
    assert result.effect_size == 0.0


@pytest.mark.unit
def test_paired_comparison_all_draws() -> None:
    """All-draws battery: same decisive stats as empty, draws == n_seeds."""
    outcomes = [
        ModelSOSeedOutcome(
            seed=i, winner=SOSeedWinner.DRAW, candidate_overloads=0, parent_overloads=0
        )
        for i in range(20)
    ]
    result = paired_comparison(outcomes)
    assert result.n_seeds == 20
    assert result.draws == 20
    assert result.candidate_wins == 0
    assert result.parent_wins == 0
    assert result.p_value == 1.0
    assert result.candidate_win_rate == 0.5
    assert result.ci_low == 0.0
    assert result.ci_high == 1.0
    assert result.effect_size == 0.0


@pytest.mark.unit
def test_paired_comparison_duplicate_seeds_raises() -> None:
    """Duplicate seeds in outcomes must raise ValueError."""
    outcomes = [
        ModelSOSeedOutcome(
            seed=1,
            winner=SOSeedWinner.CANDIDATE,
            candidate_overloads=0,
            parent_overloads=0,
        ),
        ModelSOSeedOutcome(
            seed=1,
            winner=SOSeedWinner.PARENT,
            candidate_overloads=0,
            parent_overloads=0,
        ),
    ]
    with pytest.raises(ValueError):
        paired_comparison(outcomes)


@pytest.mark.unit
def test_paired_comparison_model_is_consistent() -> None:
    """ModelSOPairedComparison rejects wins+draws != n_seeds."""
    with pytest.raises(ValueError):
        ModelSOPairedComparison(
            n_seeds=10,
            candidate_wins=6,
            parent_wins=6,
            draws=0,
            p_value=0.5,
            candidate_win_rate=0.5,
            ci_low=0.2,
            ci_high=0.8,
            effect_size=0.0,
        )


@pytest.mark.unit
def test_paired_comparison_model_rejects_bad_ci() -> None:
    """ModelSOPairedComparison rejects ci_low > ci_high."""
    with pytest.raises(ValueError):
        ModelSOPairedComparison(
            n_seeds=10,
            candidate_wins=5,
            parent_wins=5,
            draws=0,
            p_value=1.0,
            candidate_win_rate=0.5,
            ci_low=0.8,
            ci_high=0.2,
            effect_size=0.0,
        )
