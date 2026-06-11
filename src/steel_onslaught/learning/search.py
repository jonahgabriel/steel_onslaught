"""Deterministic bounded search strategies for the learning loop.

Three strategies:
- iter_grid: full cartesian product over the quantized parameter lattice
- hill_climb_neighbors: single-parameter neighbors of a current point
- random_restart: seeded random assignment on the lattice

Design constraints (enforced by purity static-check test):
- No wall-clock, no time module
- No global random state (no random.seed, no bare random.random/choice)
- All randomness via random.Random(seed) instances
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Iterator

from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import (
    BoundsDict,
    ModelSONumericBound,
)


def lattice_values(bound: ModelSONumericBound) -> list[int | float]:
    """The quantized value lattice: minimum + k*step for k = 0, 1, ... while
    value <= maximum + 1e-9. Values rounded to 9 decimals. Emitted as int when
    minimum, maximum, and step are all integral; else float. Ascending order.
    """
    # Pydantic coerces field values to float, so we cannot use isinstance(..., int).
    # A bound is "integral" when all three parameters are whole numbers (no fractional part).
    emit_int = (
        float(bound.minimum).is_integer()
        and float(bound.maximum).is_integer()
        and float(bound.step).is_integer()
    )
    result: list[int | float] = []
    k = 0
    while True:
        raw = bound.minimum + k * bound.step
        if raw > bound.maximum + 1e-9:
            break
        rounded = round(raw, 9)
        if emit_int:
            result.append(int(rounded))
        else:
            result.append(float(rounded))
        k += 1
    return result


def iter_grid(bounds: BoundsDict) -> Iterator[ParamDict]:
    """Full cartesian product over the lattice. Parameter names iterate in
    sorted order; numeric values ascending; categorical choices in declared
    order; the last-sorted name varies fastest. Deterministic, lazy.
    """
    sorted_names = sorted(bounds.keys())
    per_param: list[list[int | float | str]] = []
    for name in sorted_names:
        bound = bounds[name]
        if isinstance(bound, ModelSONumericBound):
            per_param.append(lattice_values(bound))  # type: ignore[arg-type]
        else:
            per_param.append(list(bound.choices))

    for combo in itertools.product(*per_param):
        yield dict(zip(sorted_names, combo, strict=True))


def _find_lattice_index(value: int | float, lattice: list[int | float]) -> int:
    """Return the index of `value` in `lattice` (tolerance 1e-9), or raise ValueError."""
    for i, lv in enumerate(lattice):
        if abs(float(value) - float(lv)) < 1e-9:
            return i
    raise ValueError(
        f"value {value!r} is off-lattice (no lattice entry within 1e-9); lattice={lattice}"
    )


def hill_climb_neighbors(
    current: ParamDict,
    bounds: BoundsDict,
    step_multiplier: int = 1,
) -> list[ParamDict]:
    """Single-parameter neighbors of `current`: for each numeric parameter
    (sorted name order), the lattice values `step_multiplier` indices below
    then above the current index (clamped to the lattice ends; dropped when
    clamping lands back on the current index); for each categorical
    parameter, every other choice in declared order. Each neighbor differs
    from `current` in exactly one parameter. Raises ValueError when
    `current`'s keys do not exactly match `bounds`' keys, when a numeric
    value is off-lattice (tolerance 1e-9), when a categorical value is not a
    declared choice, or when step_multiplier < 1.
    """
    if step_multiplier < 1:
        raise ValueError(f"step_multiplier must be >= 1, got {step_multiplier}")

    if set(current.keys()) != set(bounds.keys()):
        raise ValueError(
            f"current keys {set(current.keys())} do not match bounds keys {set(bounds.keys())}"
        )

    neighbors: list[ParamDict] = []
    sorted_names = sorted(bounds.keys())

    for name in sorted_names:
        bound = bounds[name]
        cur_val = current[name]

        if isinstance(bound, ModelSONumericBound):
            lattice = lattice_values(bound)
            idx = _find_lattice_index(cur_val, lattice)  # type: ignore[arg-type]

            # Lower neighbor (clamped)
            lower_idx = max(0, idx - step_multiplier)
            if lower_idx != idx:
                neighbor = dict(current)
                neighbor[name] = lattice[lower_idx]
                neighbors.append(neighbor)

            # Upper neighbor (clamped)
            upper_idx = min(len(lattice) - 1, idx + step_multiplier)
            if upper_idx != idx:
                neighbor = dict(current)
                neighbor[name] = lattice[upper_idx]
                neighbors.append(neighbor)

        else:
            # Categorical: every other choice in declared order
            if cur_val not in bound.choices:
                raise ValueError(
                    f"current[{name!r}]={cur_val!r} is not a declared choice in {bound.choices}"
                )
            for choice in bound.choices:
                if choice != cur_val:
                    neighbor = dict(current)
                    neighbor[name] = choice
                    neighbors.append(neighbor)

    return neighbors


def random_restart(bounds: BoundsDict, seed: int) -> ParamDict:
    """Seeded full assignment on the lattice: rng = random.Random(seed); for
    each parameter in sorted name order, numeric -> rng.choice(lattice_values),
    categorical -> rng.choice(choices). No wall-clock, no global random state.
    """
    rng = random.Random(seed)
    result: ParamDict = {}
    for name in sorted(bounds.keys()):
        bound = bounds[name]
        if isinstance(bound, ModelSONumericBound):
            vals = lattice_values(bound)
            result[name] = rng.choice(vals)
        else:
            result[name] = rng.choice(bound.choices)
    return result
