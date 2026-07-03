"""Learning loop driver: search -> evaluate -> stats -> gate -> record.

This is the composition Phase 1 deliberately deferred: the ONLY module that
imports search.py, stats.py, AND promotion.py together.

PURE module (enforced by source-scan test):
- no wall-clock (clock attribution happens at persistence, in the CLI)
- no I/O (persistence is the CLI's job)
- no global random state; the only randomness is derive_seed_batteries's
  seeded random.Random

Budget discipline: ``evaluations_consumed`` counts every evaluator.evaluate
call including the gate's holdout call, and the loop never exceeds
``config.max_evaluations``. The gate evaluation is always reserved; hill-climb
additionally reserves the final explicit candidate-vs-original-parent
re-basing evaluation before spending budget on a neighbor.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.contracts.lineage import (
    ModelSOLineageGenerator,
    ModelSOLineageRecord,
    ParamDict,
    spec_hash,
)
from steel_onslaught.learning.promotion import (
    ModelSOPromotionThresholds,
    evaluate_promotion,
)
from steel_onslaught.learning.protocols import (
    BoundsDict,
    EvaluatorProtocol,
    ModelSONumericBound,
    ModelSOPairedComparison,
    ModelSOSeedOutcome,
)
from steel_onslaught.learning.search import (
    hill_climb_neighbors,
    iter_grid,
    random_restart,
)
from steel_onslaught.learning.stats import paired_comparison


class SOSearchStrategy(StrEnum):
    GRID = "grid"
    HILL_CLIMB = "hill_climb"
    RANDOM_RESTART = "random_restart"
    EXTERNAL = "external"  # Phase 3: candidates provided externally (e.g. LLM tuner)


class ModelSOLearnConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy: SOSearchStrategy
    master_seed: int
    n_search_seeds: int = Field(ge=1)
    n_holdout_seeds: int = Field(ge=1)
    max_evaluations: int = Field(ge=2)  # >= 1 search evaluation + the gate evaluation
    step_schedule: tuple[int, ...] = (4, 2, 1)  # hill-climb coarse -> fine multipliers
    n_restarts: int = Field(default=8, ge=1)  # random_restart draws
    thresholds: ModelSOPromotionThresholds = ModelSOPromotionThresholds()


class ModelSOTrajectoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    index: int = Field(ge=0)  # evaluation order, 0-based
    generator: ModelSOLineageGenerator  # generator_id + selection_reason (addendum section 7)
    candidate_params: ParamDict
    candidate_hash: str  # spec_hash(archetype, candidate_params)
    comparison: ModelSOPairedComparison  # vs the comparison baseline at that step


class ModelSOLearnResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    config: ModelSOLearnConfig
    archetype: str
    parent_params: ParamDict
    search_seeds: tuple[int, ...]
    holdout_seeds: tuple[int, ...]
    trajectory: tuple[ModelSOTrajectoryEntry, ...]
    evaluations_consumed: int = Field(ge=0)  # Phase 3's baseline-arm floor (attempts metric)
    record: ModelSOLineageRecord | None  # None when no candidate beat the parent (Decision #7)


def derive_seed_batteries(
    master_seed: int, n_search: int, n_holdout: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """rng = random.Random(master_seed); draw distinct ints from
    range(1, 2**31) until n_search + n_holdout unique values exist; first
    n_search are the search battery, the rest the holdout battery. Disjoint by
    construction, deterministic forever, no wall-clock.
    """
    if n_search < 1 or n_holdout < 1:
        raise ValueError(
            f"battery sizes must be >= 1; got n_search={n_search}, n_holdout={n_holdout}"
        )
    rng = random.Random(master_seed)
    drawn: list[int] = []
    seen: set[int] = set()
    total = n_search + n_holdout
    while len(drawn) < total:
        value = rng.randrange(1, 2**31)
        if value not in seen:
            seen.add(value)
            drawn.append(value)
    return tuple(drawn[:n_search]), tuple(drawn[n_search:])


def _neighbor_selection_reason(
    neighbor: ParamDict, current: ParamDict, bounds: BoundsDict, multiplier: int
) -> str:
    """`hill_climb_neighbor:<param><+/-><k>@x<multiplier>` for the single
    parameter the neighbor changed (categorical: `<param>=<choice>@x<m>`)."""
    for name in sorted(bounds.keys()):
        if neighbor[name] == current[name]:
            continue
        bound = bounds[name]
        if isinstance(bound, ModelSONumericBound):
            delta_steps = (float(neighbor[name]) - float(current[name])) / bound.step
            k = round(abs(delta_steps))
            sign = "+" if delta_steps > 0 else "-"
            return f"hill_climb_neighbor:{name}{sign}{k}@x{multiplier}"
        return f"hill_climb_neighbor:{name}={neighbor[name]}@x{multiplier}"
    raise ValueError("neighbor does not differ from current in any parameter")


class _EvaluatedCandidate(BaseModel):
    """Internal pairing of a trajectory entry with its raw outcomes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    entry: ModelSOTrajectoryEntry
    outcomes: tuple[ModelSOSeedOutcome, ...]


def _is_direction_positive(comparison: ModelSOPairedComparison) -> bool:
    return comparison.candidate_wins > comparison.parent_wins


def _select_best(candidates: Sequence[_EvaluatedCandidate]) -> _EvaluatedCandidate | None:
    """Lowest p among direction-positive candidates; ties broken by higher
    candidate_win_rate, then lexicographically smaller candidate_hash."""
    positive = [c for c in candidates if _is_direction_positive(c.entry.comparison)]
    if not positive:
        return None
    return min(
        positive,
        key=lambda c: (
            c.entry.comparison.p_value,
            -c.entry.comparison.candidate_win_rate,
            c.entry.candidate_hash,
        ),
    )


def run_learning_loop(
    *,
    archetype: str,
    parent_params: ParamDict,
    bounds: BoundsDict,
    evaluator: EvaluatorProtocol,
    opponent_spec_hashes: Sequence[str],
    config: ModelSOLearnConfig,
    candidates: Sequence[tuple[ParamDict, str]] | None = None,
    generator_id: str | None = None,
) -> ModelSOLearnResult:
    search_seeds, holdout_seeds = derive_seed_batteries(
        config.master_seed, config.n_search_seeds, config.n_holdout_seeds
    )
    parent_hash = spec_hash(archetype, parent_params)
    trajectory: list[ModelSOTrajectoryEntry] = []
    consumed = 0

    def evaluate_on_search(
        candidate: ParamDict, baseline: ParamDict
    ) -> tuple[tuple[ModelSOSeedOutcome, ...], ModelSOPairedComparison]:
        nonlocal consumed
        outcomes = tuple(evaluator.evaluate(candidate, baseline, search_seeds))
        consumed += 1
        return outcomes, paired_comparison(outcomes)

    def record_entry(
        candidate: ParamDict,
        candidate_hash: str,
        generator: ModelSOLineageGenerator,
        comparison: ModelSOPairedComparison,
    ) -> ModelSOTrajectoryEntry:
        entry = ModelSOTrajectoryEntry(
            index=len(trajectory),
            generator=generator,
            candidate_params=dict(candidate),
            candidate_hash=candidate_hash,
            comparison=comparison,
        )
        trajectory.append(entry)
        return entry

    def run_gate(
        candidate: ParamDict,
        generator: ModelSOLineageGenerator,
        search_comparison: ModelSOPairedComparison,
        search_outcomes: tuple[ModelSOSeedOutcome, ...],
    ) -> ModelSOLineageRecord:
        nonlocal consumed
        holdout_outcomes = evaluator.evaluate(candidate, parent_params, holdout_seeds)
        consumed += 1
        return evaluate_promotion(
            archetype=archetype,
            candidate_params=candidate,
            parent_params=parent_params,
            bounds=bounds,
            search_comparison=search_comparison,
            search_outcomes=search_outcomes,
            holdout_outcomes=holdout_outcomes,
            opponent_spec_hashes=opponent_spec_hashes,
            generator=generator,
            thresholds=config.thresholds,
        )

    def run_enumeration(
        candidates: Iterable[tuple[ParamDict, str]], generator_id: str
    ) -> ModelSOLineageRecord | None:
        """Grid / random-restart shape: evaluate each candidate vs the parent
        until the budget leaves exactly one evaluation for the gate; gate the
        best direction-positive candidate (rejections are evidence too)."""
        evaluated: list[_EvaluatedCandidate] = []
        seen_hashes = {parent_hash}  # skip the parent's own point; dedupe draws
        for candidate, reason in candidates:
            candidate_hash = spec_hash(archetype, candidate)
            if candidate_hash in seen_hashes:
                continue
            seen_hashes.add(candidate_hash)
            if consumed + 1 > config.max_evaluations - 1:  # reserve the gate evaluation
                break
            outcomes, comparison = evaluate_on_search(candidate, parent_params)
            generator = ModelSOLineageGenerator(generator_id=generator_id, selection_reason=reason)
            entry = record_entry(candidate, candidate_hash, generator, comparison)
            evaluated.append(_EvaluatedCandidate(entry=entry, outcomes=outcomes))
        best = _select_best(evaluated)
        if best is None:
            return None  # no candidate beat the parent: the trajectory is the evidence
        return run_gate(
            best.entry.candidate_params,
            best.entry.generator,
            best.entry.comparison,
            best.outcomes,
        )

    def run_hill_climb() -> ModelSOLineageRecord | None:
        current = dict(parent_params)
        current_generator: ModelSOLineageGenerator | None = None
        for multiplier in config.step_schedule:
            while True:
                evaluated: list[_EvaluatedCandidate] = []
                for neighbor in hill_climb_neighbors(current, bounds, multiplier):
                    # Reserve this evaluation + the final re-basing evaluation
                    # + the gate evaluation.
                    if consumed + 3 > config.max_evaluations:
                        break
                    outcomes, comparison = evaluate_on_search(neighbor, current)
                    generator = ModelSOLineageGenerator(
                        generator_id="search.hill_climb",
                        selection_reason=_neighbor_selection_reason(
                            neighbor, current, bounds, multiplier
                        ),
                    )
                    entry = record_entry(
                        neighbor, spec_hash(archetype, neighbor), generator, comparison
                    )
                    evaluated.append(_EvaluatedCandidate(entry=entry, outcomes=outcomes))
                qualifying = [
                    c
                    for c in evaluated
                    if _is_direction_positive(c.entry.comparison)
                    and c.entry.comparison.p_value <= config.thresholds.p_value_max
                ]
                best = _select_best(qualifying)
                if best is None:
                    break  # refine to the next multiplier
                current = dict(best.entry.candidate_params)
                current_generator = best.entry.generator
        if spec_hash(archetype, current) == parent_hash or current_generator is None:
            return None  # the climb never left the parent
        # ONE explicit current-vs-ORIGINAL-parent evaluation on the search
        # battery: the gate's search_comparison is always candidate-vs-the-
        # lineage-parent, never vs an intermediate.
        final_outcomes, final_comparison = evaluate_on_search(current, parent_params)
        if not _is_direction_positive(final_comparison):
            return None  # never gate a candidate that lost (Decision #7)
        return run_gate(current, current_generator, final_comparison, final_outcomes)

    record: ModelSOLineageRecord | None
    if config.strategy is SOSearchStrategy.GRID:
        record = run_enumeration(
            ((candidate, "grid_enumeration") for candidate in iter_grid(bounds)),
            "search.grid",
        )
    elif config.strategy is SOSearchStrategy.HILL_CLIMB:
        record = run_hill_climb()
    elif config.strategy is SOSearchStrategy.EXTERNAL:
        # Phase 3: externally-provided candidates (e.g. LLM tuner). The
        # candidates must be fully materialized before this call (no lazy I/O
        # inside the pure loop — adversarial verdict C3). Fail loud if missing.
        if candidates is None or generator_id is None:
            raise ValueError("EXTERNAL strategy requires both `candidates` and `generator_id`")
        record = run_enumeration(candidates, generator_id)
    else:
        record = run_enumeration(
            (
                (random_restart(bounds, seed), f"random_restart:{seed}")
                for seed in range(config.master_seed, config.master_seed + config.n_restarts)
            ),
            "search.random_restart",
        )

    return ModelSOLearnResult(
        config=config,
        archetype=archetype,
        parent_params=dict(parent_params),
        search_seeds=search_seeds,
        holdout_seeds=holdout_seeds,
        trajectory=tuple(trajectory),
        evaluations_consumed=consumed,
        record=record,
    )
