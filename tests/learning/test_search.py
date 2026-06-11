"""Tests for learning/search.py — deterministic bounded search strategies.

Task 3 of the Phase-1 learning-loop plan.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import (
    BoundsDict,
    ModelSOCategoricalBound,
    ModelSONumericBound,
)
from steel_onslaught.learning.search import (
    hill_climb_neighbors,
    iter_grid,
    lattice_values,
    random_restart,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def small_bounds() -> BoundsDict:
    """One int, one float, one categorical — small and fast."""
    return {
        "count": ModelSONumericBound(minimum=2, maximum=6, step=2),  # lattice: 2,4,6
        "rate": ModelSONumericBound(minimum=0.3, maximum=0.5, step=0.1),  # 0.3,0.4,0.5
        "mode": ModelSOCategoricalBound(choices=("fast", "slow")),
    }


@pytest.fixture()
def float_only_bounds() -> BoundsDict:
    """Float-only bounds for lattice integrity checks."""
    return {
        "lock_confidence_floor": ModelSONumericBound(minimum=0.3, maximum=0.95, step=0.05),
    }


@pytest.fixture()
def two_numeric_one_cat() -> BoundsDict:
    """Used for hill_climb_neighbors interior-point checks."""
    return {
        "alpha": ModelSONumericBound(minimum=1, maximum=5, step=1),  # lattice: 1,2,3,4,5
        "beta": ModelSONumericBound(minimum=0.0, maximum=1.0, step=0.5),  # 0.0,0.5,1.0
        "gamma": ModelSOCategoricalBound(choices=("x", "y")),
    }


# ---------------------------------------------------------------------------
# lattice_values
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lattice_int_values(small_bounds: BoundsDict) -> None:
    """Integer bounds emit int values in ascending order."""
    bound = small_bounds["count"]
    assert isinstance(bound, ModelSONumericBound)
    vals = lattice_values(bound)
    assert vals == [2, 4, 6]
    assert all(type(v) is int for v in vals)


@pytest.mark.unit
def test_lattice_float_values(small_bounds: BoundsDict) -> None:
    """Float bounds emit float values."""
    bound = small_bounds["rate"]
    assert isinstance(bound, ModelSONumericBound)
    vals = lattice_values(bound)
    assert len(vals) == 3
    assert type(vals[0]) is float
    assert abs(vals[0] - 0.3) < 1e-9
    assert abs(vals[2] - 0.5) < 1e-9


@pytest.mark.unit
def test_lattice_real_float_bound(float_only_bounds: BoundsDict) -> None:
    """lock_confidence_floor 0.3-0.95 step 0.05 -> 14 entries, first 0.3, last 0.95."""
    bound = float_only_bounds["lock_confidence_floor"]
    assert isinstance(bound, ModelSONumericBound)
    vals = lattice_values(bound)
    assert len(vals) == 14
    assert abs(vals[0] - 0.3) < 1e-9
    assert abs(vals[-1] - 0.95) < 1e-9
    # All distinct after rounding to 9 decimals
    rounded = [round(v, 9) for v in vals]
    assert len(set(rounded)) == 14


@pytest.mark.unit
def test_lattice_ascending(small_bounds: BoundsDict) -> None:
    """All lattice outputs are in ascending order."""
    for name, bound in small_bounds.items():
        if isinstance(bound, ModelSONumericBound):
            vals = lattice_values(bound)
            assert vals == sorted(vals), f"{name} is not ascending"


@pytest.mark.unit
def test_lattice_single_point() -> None:
    """minimum == maximum with any step emits a single-element lattice."""
    bound = ModelSONumericBound(minimum=3, maximum=3, step=1)
    assert lattice_values(bound) == [3]
    assert type(lattice_values(bound)[0]) is int


@pytest.mark.unit
def test_lattice_int_vs_float_distinction() -> None:
    """Integral bounds (all whole-number parameters) emit int; fractional step emits float.

    Note: Pydantic coerces minimum/maximum/step to float regardless of whether the
    Python literal was int or float — so both ModelSONumericBound(minimum=1, ...) and
    ModelSONumericBound(minimum=1.0, ...) are internally identical after coercion.
    The int/float distinction is determined by whether all stored values are whole numbers.
    """
    # All whole numbers → int output
    bound_int = ModelSONumericBound(minimum=1, maximum=3, step=1)
    vals_int = lattice_values(bound_int)
    assert all(type(v) is int for v in vals_int)

    # Also whole numbers after Pydantic coercion of float literals → also int
    bound_float_whole = ModelSONumericBound(minimum=1.0, maximum=3.0, step=1.0)
    vals_float_whole = lattice_values(bound_float_whole)
    assert all(type(v) is int for v in vals_float_whole)

    # Fractional step → float output
    bound_frac = ModelSONumericBound(minimum=0.0, maximum=1.0, step=0.5)
    vals_frac = lattice_values(bound_frac)
    assert all(type(v) is float for v in vals_frac)


# ---------------------------------------------------------------------------
# iter_grid
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_iter_grid_size(small_bounds: BoundsDict) -> None:
    """Product size: 3 (count) * 3 (rate) * 2 (mode) = 18."""
    result = list(iter_grid(small_bounds))
    assert len(result) == 18


@pytest.mark.unit
def test_iter_grid_sorted_name_order(small_bounds: BoundsDict) -> None:
    """Parameter names iterate in sorted order: count, mode, rate."""
    result = list(iter_grid(small_bounds))
    assert len(result) == 18
    sorted_keys = sorted(small_bounds.keys())
    for row in result:
        assert list(row.keys()) == sorted_keys


@pytest.mark.unit
def test_iter_grid_last_sorted_varies_fastest(small_bounds: BoundsDict) -> None:
    """The last-sorted parameter (rate) varies fastest."""
    result = list(iter_grid(small_bounds))
    # rate values cycle fastest: 0.3, 0.4, 0.5, 0.3, 0.4, 0.5, ...
    # (for the first group of 3, count=2, mode=fast)
    first_group_rates = [row["rate"] for row in result[:3]]
    assert all(isinstance(r, (int, float)) for r in first_group_rates)
    r0, r1, r2 = first_group_rates
    assert isinstance(r0, (int, float))
    assert isinstance(r1, (int, float))
    assert isinstance(r2, (int, float))
    assert abs(r0 - 0.3) < 1e-9
    assert abs(r1 - 0.4) < 1e-9
    assert abs(r2 - 0.5) < 1e-9


@pytest.mark.unit
def test_iter_grid_first_element(small_bounds: BoundsDict) -> None:
    """First element: minimum numeric values, first categorical choice."""
    result = list(iter_grid(small_bounds))
    first = result[0]
    # count=2 (min), mode=fast (first choice), rate=0.3 (min float)
    assert first["count"] == 2
    assert first["mode"] == "fast"
    rate0 = first["rate"]
    assert isinstance(rate0, (int, float))
    assert abs(rate0 - 0.3) < 1e-9


@pytest.mark.unit
def test_iter_grid_last_element(small_bounds: BoundsDict) -> None:
    """Last element: maximum numeric values, last categorical choice."""
    result = list(iter_grid(small_bounds))
    last = result[-1]
    assert last["count"] == 6
    assert last["mode"] == "slow"
    rate_last = last["rate"]
    assert isinstance(rate_last, (int, float))
    assert abs(rate_last - 0.5) < 1e-9


@pytest.mark.unit
def test_iter_grid_all_bounds_satisfied(small_bounds: BoundsDict) -> None:
    """Every emitted dict satisfies its bounds."""
    for row in iter_grid(small_bounds):
        for name, bound in small_bounds.items():
            v = row[name]
            if isinstance(bound, ModelSONumericBound):
                assert isinstance(v, (int, float))
                assert bound.minimum - 1e-9 <= v <= bound.maximum + 1e-9
            else:
                assert v in bound.choices


@pytest.mark.unit
def test_iter_grid_all_on_lattice(small_bounds: BoundsDict) -> None:
    """Every numeric value equals a lattice_values entry exactly."""
    for row in iter_grid(small_bounds):
        for name, bound in small_bounds.items():
            if isinstance(bound, ModelSONumericBound):
                lattice = lattice_values(bound)
                v = row[name]
                assert isinstance(v, (int, float))
                assert any(abs(v - lv) < 1e-9 for lv in lattice), (
                    f"{name}={v} not on lattice {lattice}"
                )


@pytest.mark.unit
def test_iter_grid_reproducible() -> None:
    """Same bounds → same output on two separate calls (lazy iterator)."""
    bounds: BoundsDict = {
        "x": ModelSONumericBound(minimum=0, maximum=2, step=1),
        "y": ModelSOCategoricalBound(choices=("a", "b")),
    }
    first = list(iter_grid(bounds))
    second = list(iter_grid(bounds))
    assert first == second


# ---------------------------------------------------------------------------
# hill_climb_neighbors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hill_climb_interior_5_neighbors(two_numeric_one_cat: BoundsDict) -> None:
    """Interior numeric point + 2-choice categorical → exactly 5 neighbors."""
    # alpha lattice: 1,2,3,4,5 → interior at 3
    # beta lattice: 0.0, 0.5, 1.0 → interior at 0.5
    # gamma: x,y → current x → 1 other neighbor (y)
    current: ParamDict = {"alpha": 3, "beta": 0.5, "gamma": "x"}
    neighbors = hill_climb_neighbors(current, two_numeric_one_cat)
    assert len(neighbors) == 5
    # Each differs in exactly one key
    for nb in neighbors:
        diffs = [k for k in current if nb[k] != current[k]]
        assert len(diffs) == 1, f"Neighbor {nb} differs in {diffs}"


@pytest.mark.unit
def test_hill_climb_boundary_drops_oob(two_numeric_one_cat: BoundsDict) -> None:
    """At the lower boundary of alpha (value=1), no lower neighbor generated."""
    current: ParamDict = {"alpha": 1, "beta": 0.5, "gamma": "x"}
    neighbors = hill_climb_neighbors(current, two_numeric_one_cat)
    alpha_neighbors = [nb["alpha"] for nb in neighbors if nb["alpha"] != current["alpha"]]
    # Only the upper neighbor for alpha (value=2)
    assert all(isinstance(v, (int, float)) and v > 1 for v in alpha_neighbors)
    assert 2 in alpha_neighbors


@pytest.mark.unit
def test_hill_climb_boundary_upper(two_numeric_one_cat: BoundsDict) -> None:
    """At the upper boundary of alpha (value=5), no upper neighbor generated."""
    current: ParamDict = {"alpha": 5, "beta": 0.5, "gamma": "x"}
    neighbors = hill_climb_neighbors(current, two_numeric_one_cat)
    alpha_neighbors = [nb["alpha"] for nb in neighbors if nb["alpha"] != current["alpha"]]
    # Only the lower neighbor for alpha (value=4)
    assert all(isinstance(v, (int, float)) and v < 5 for v in alpha_neighbors)
    assert 4 in alpha_neighbors


@pytest.mark.unit
def test_hill_climb_step_multiplier_2(two_numeric_one_cat: BoundsDict) -> None:
    """step_multiplier=2 moves 2 lattice indices; clamps at boundary if overshoot."""
    # alpha interior at 3: multiplier 2 → indices ±2 → values 1 and 5
    current: ParamDict = {"alpha": 3, "beta": 0.5, "gamma": "x"}
    neighbors = hill_climb_neighbors(current, two_numeric_one_cat, step_multiplier=2)
    alpha_neighbors = [nb["alpha"] for nb in neighbors if nb["alpha"] != current["alpha"]]
    assert 1 in alpha_neighbors
    assert 5 in alpha_neighbors


@pytest.mark.unit
def test_hill_climb_step_multiplier_overshoot_clamp(two_numeric_one_cat: BoundsDict) -> None:
    """step_multiplier=3 from alpha=4 (index 3) overshoots lattice end; clamps to 5."""
    # lattice: 1,2,3,4,5 (indices 0..4); from 4 (idx 3):
    # upper = idx 3+3=6 → clamped to 4 (idx 4, value 5); value 5 != 4 → included
    # lower = idx 3-3=0 → value 1 != 4 → included
    current: ParamDict = {"alpha": 4, "beta": 0.5, "gamma": "x"}
    neighbors = hill_climb_neighbors(current, two_numeric_one_cat, step_multiplier=3)
    alpha_neighbors = [nb["alpha"] for nb in neighbors if nb["alpha"] != current["alpha"]]
    assert 1 in alpha_neighbors
    assert 5 in alpha_neighbors


@pytest.mark.unit
def test_hill_climb_all_neighbors_on_lattice(small_bounds: BoundsDict) -> None:
    """All neighbor values are on the lattice."""
    current: ParamDict = {"count": 4, "rate": 0.4, "mode": "fast"}
    neighbors = hill_climb_neighbors(current, small_bounds)
    for nb in neighbors:
        for name, bound in small_bounds.items():
            v = nb[name]
            if isinstance(bound, ModelSONumericBound):
                assert isinstance(v, (int, float))
                lattice = lattice_values(bound)
                assert any(abs(v - lv) < 1e-9 for lv in lattice)
            else:
                assert v in bound.choices


@pytest.mark.unit
def test_hill_climb_categorical_all_other_choices() -> None:
    """Categorical with 3 choices → 2 neighbors per categorical parameter."""
    bounds: BoundsDict = {
        "x": ModelSONumericBound(minimum=1, maximum=3, step=1),
        "mode": ModelSOCategoricalBound(choices=("a", "b", "c")),
    }
    current: ParamDict = {"x": 2, "mode": "b"}
    neighbors = hill_climb_neighbors(current, bounds)
    mode_neighbors = [nb["mode"] for nb in neighbors if nb["mode"] != "b"]
    assert set(mode_neighbors) == {"a", "c"}


@pytest.mark.unit
def test_hill_climb_key_mismatch_raises(small_bounds: BoundsDict) -> None:
    """Keys in current not matching bounds raises ValueError."""
    partial: ParamDict = {"count": 4, "rate": 0.4}
    with pytest.raises(ValueError):
        hill_climb_neighbors(partial, small_bounds)  # missing 'mode'


@pytest.mark.unit
def test_hill_climb_extra_key_raises(small_bounds: BoundsDict) -> None:
    """Extra key in current not in bounds raises ValueError."""
    extra: ParamDict = {"count": 4, "rate": 0.4, "mode": "fast", "extra": 99}
    with pytest.raises(ValueError):
        hill_climb_neighbors(extra, small_bounds)


@pytest.mark.unit
def test_hill_climb_off_lattice_raises(small_bounds: BoundsDict) -> None:
    """Off-lattice numeric value raises ValueError (tol 1e-9)."""
    # count lattice is 2, 4, 6 — value 3 is off-lattice
    off_lattice: ParamDict = {"count": 3, "rate": 0.4, "mode": "fast"}
    with pytest.raises(ValueError):
        hill_climb_neighbors(off_lattice, small_bounds)


@pytest.mark.unit
def test_hill_climb_unknown_categorical_raises(small_bounds: BoundsDict) -> None:
    """Unknown categorical value raises ValueError."""
    bad_cat: ParamDict = {"count": 4, "rate": 0.4, "mode": "turbo"}
    with pytest.raises(ValueError):
        hill_climb_neighbors(bad_cat, small_bounds)


@pytest.mark.unit
def test_hill_climb_step_multiplier_zero_raises(small_bounds: BoundsDict) -> None:
    """step_multiplier=0 raises ValueError."""
    valid: ParamDict = {"count": 4, "rate": 0.4, "mode": "fast"}
    with pytest.raises(ValueError):
        hill_climb_neighbors(valid, small_bounds, step_multiplier=0)


# ---------------------------------------------------------------------------
# random_restart
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_random_restart_determinism(small_bounds: BoundsDict) -> None:
    """Same seed → same result across two independent calls."""
    a = random_restart(small_bounds, seed=42)
    b = random_restart(small_bounds, seed=42)
    assert a == b


@pytest.mark.unit
def test_random_restart_sequence_determinism(small_bounds: BoundsDict) -> None:
    """Sequence of seeds produces identical results across two constructions."""
    seq1 = [random_restart(small_bounds, s) for s in range(10)]
    seq2 = [random_restart(small_bounds, s) for s in range(10)]
    assert seq1 == seq2


@pytest.mark.unit
def test_random_restart_no_global_state_pollution(small_bounds: BoundsDict) -> None:
    """Interleaving global random calls does not change random_restart results."""
    r1 = random_restart(small_bounds, seed=7)
    # Perturb global random state
    for _ in range(100):
        random.random()
    r2 = random_restart(small_bounds, seed=7)
    assert r1 == r2


@pytest.mark.unit
def test_random_restart_bounds_satisfied(small_bounds: BoundsDict) -> None:
    """All 200 restarts produce values within bounds."""
    for seed in range(200):
        result = random_restart(small_bounds, seed=seed)
        for name, bound in small_bounds.items():
            v = result[name]
            if isinstance(bound, ModelSONumericBound):
                assert isinstance(v, (int, float))
                assert bound.minimum - 1e-9 <= v <= bound.maximum + 1e-9
            else:
                assert v in bound.choices


@pytest.mark.unit
def test_random_restart_on_lattice(small_bounds: BoundsDict) -> None:
    """All 200 restarts produce numeric values on the lattice."""
    for seed in range(200):
        result = random_restart(small_bounds, seed=seed)
        for name, bound in small_bounds.items():
            if isinstance(bound, ModelSONumericBound):
                lattice = lattice_values(bound)
                v = result[name]
                assert isinstance(v, (int, float))
                assert any(abs(v - lv) < 1e-9 for lv in lattice), (
                    f"seed={seed} {name}={v} not on lattice"
                )


@pytest.mark.unit
def test_random_restart_int_type_preserved(small_bounds: BoundsDict) -> None:
    """Integer bounds emit int from random_restart."""
    for seed in range(20):
        result = random_restart(small_bounds, seed=seed)
        assert type(result["count"]) is int


@pytest.mark.unit
def test_random_restart_float_type_preserved(small_bounds: BoundsDict) -> None:
    """Float bounds emit float from random_restart."""
    for seed in range(20):
        result = random_restart(small_bounds, seed=seed)
        assert type(result["rate"]) is float


@pytest.mark.unit
def test_random_restart_different_seeds_vary(small_bounds: BoundsDict) -> None:
    """Different seeds should not all produce the same result (birthday check)."""
    results = [random_restart(small_bounds, seed=s) for s in range(50)]
    # With 18 grid points, 50 restarts should have some variation
    unique = {tuple(sorted(r.items())) for r in results}
    assert len(unique) > 1


# ---------------------------------------------------------------------------
# Purity static check
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_search_purity_no_wall_clock_or_global_random() -> None:
    """search.py must not use time, datetime, random.seed, or bare module-level random.

    Source-scan test (MVP Task 23 pattern) — ensures no hidden global state.
    """
    import importlib.util
    import pathlib

    spec = importlib.util.find_spec("steel_onslaught.learning.search")
    assert spec is not None
    assert spec.origin is not None
    source = pathlib.Path(spec.origin).read_text()

    assert "import time" not in source, "search.py must not import time"
    assert "import datetime" not in source, "search.py must not import datetime"
    assert "datetime" not in source, "search.py must not reference datetime"
    assert "random.seed(" not in source, "search.py must not call random.seed()"
    # No bare module-level random.random() or random.choice() — only via Random instances
    # (allow random.Random but not plain random.random or random.choice or random.randint)
    import re

    bare_calls = re.findall(r"\brandom\.(random|choice|randint|shuffle|sample)\(", source)
    assert not bare_calls, (
        f"search.py contains bare global random calls: {bare_calls}; "
        "all randomness must flow through random.Random(seed) instances"
    )
