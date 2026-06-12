"""Tests for learning/loop.py -- the search -> evaluate -> stats -> gate -> record driver.

All tests are @pytest.mark.unit and use FakeEvaluator/scripted doubles wrapped
in a call recorder; no real duels run here. Every pinned loop-semantics bullet
of the Phase 2 plan (Task 4) has a named test.
"""

from __future__ import annotations

import importlib.util
import random
import re
from collections.abc import Mapping, Sequence

import pytest

from steel_onslaught.contracts.lineage import (
    ParamDict,
    SOPromotionRejection,
    SOPromotionStatus,
    spec_hash,
)
from steel_onslaught.learning.loop import (
    ModelSOLearnConfig,
    ModelSOLearnResult,
    SOSearchStrategy,
    derive_seed_batteries,
    run_learning_loop,
)
from steel_onslaught.learning.promotion import ModelSOPromotionThresholds
from steel_onslaught.learning.protocols import (
    BoundsDict,
    EvaluatorProtocol,
    ModelSONumericBound,
    ModelSOSeedOutcome,
    SOSeedWinner,
)
from steel_onslaught.learning.search import random_restart

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

ARCHETYPE = "aggressive"

C = SOSeedWinner.CANDIDATE
P = SOSeedWinner.PARENT
D = SOSeedWinner.DRAW


def bounds_1d(maximum: int) -> BoundsDict:
    return {"x": ModelSONumericBound(minimum=0, maximum=maximum, step=1)}


class HashScriptedEvaluator:
    """Param-aware scripted EvaluatorProtocol double.

    Outcomes are keyed by spec_hash(archetype, candidate_params); the winner
    sequence is applied positionally to the requested seeds. Unscripted
    candidates fall back to `default` (or raise KeyError when None).
    """

    def __init__(
        self,
        archetype: str,
        script: Mapping[str, Sequence[SOSeedWinner]],
        default: Sequence[SOSeedWinner] | None = None,
    ) -> None:
        self._archetype = archetype
        self._script = {k: tuple(v) for k, v in script.items()}
        self._default = tuple(default) if default is not None else None

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        h = spec_hash(self._archetype, candidate_params)
        winners = self._script.get(h, self._default)
        if winners is None:
            raise KeyError(f"unscripted candidate hash {h}")
        if len(winners) < len(seeds):
            raise ValueError(f"script for {h} has {len(winners)} winners; need {len(seeds)}")
        return [
            ModelSOSeedOutcome(seed=s, winner=winners[i], candidate_overloads=0, parent_overloads=0)
            for i, s in enumerate(seeds)
        ]


class RecordingEvaluator:
    """Call recorder satisfying EvaluatorProtocol; delegates to an inner double."""

    def __init__(self, inner: EvaluatorProtocol) -> None:
        self._inner = inner
        self.calls: list[tuple[ParamDict, ParamDict, tuple[int, ...]]] = []

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        self.calls.append((dict(candidate_params), dict(parent_params), tuple(seeds)))
        return self._inner.evaluate(candidate_params, parent_params, seeds)


def make_config(
    strategy: SOSearchStrategy,
    *,
    master_seed: int = 42,
    n_search_seeds: int = 6,
    n_holdout_seeds: int = 2,
    max_evaluations: int = 20,
    step_schedule: tuple[int, ...] = (1,),
    n_restarts: int = 5,
    thresholds: ModelSOPromotionThresholds | None = None,
) -> ModelSOLearnConfig:
    return ModelSOLearnConfig(
        strategy=strategy,
        master_seed=master_seed,
        n_search_seeds=n_search_seeds,
        n_holdout_seeds=n_holdout_seeds,
        max_evaluations=max_evaluations,
        step_schedule=step_schedule,
        n_restarts=n_restarts,
        thresholds=thresholds if thresholds is not None else ModelSOPromotionThresholds(),
    )


def run(
    config: ModelSOLearnConfig,
    evaluator: EvaluatorProtocol,
    *,
    parent: ParamDict | None = None,
    bounds: BoundsDict | None = None,
) -> ModelSOLearnResult:
    return run_learning_loop(
        archetype=ARCHETYPE,
        parent_params=parent if parent is not None else {"x": 0},
        bounds=bounds if bounds is not None else bounds_1d(3),
        evaluator=evaluator,
        opponent_spec_hashes=[spec_hash(ARCHETYPE, parent if parent is not None else {"x": 0})],
        config=config,
    )


def xh(value: int) -> str:
    return spec_hash(ARCHETYPE, {"x": value})


# ---------------------------------------------------------------------------
# derive_seed_batteries
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_derive_seed_batteries_deterministic() -> None:
    first = derive_seed_batteries(123, 5, 3)
    second = derive_seed_batteries(123, 5, 3)
    assert first == second


@pytest.mark.unit
def test_derive_seed_batteries_disjoint_and_sized() -> None:
    search, holdout = derive_seed_batteries(7, 8, 4)
    assert len(search) == 8
    assert len(holdout) == 4
    assert len(set(search)) == 8
    assert len(set(holdout)) == 4
    assert set(search) & set(holdout) == set()
    for seed in (*search, *holdout):
        assert 1 <= seed < 2**31


@pytest.mark.unit
def test_derive_seed_batteries_stable_under_global_random() -> None:
    baseline = derive_seed_batteries(99, 4, 4)
    random.seed(0)
    random.random()
    random.randint(1, 10)
    interleaved = derive_seed_batteries(99, 4, 4)
    random.seed(31337)
    again = derive_seed_batteries(99, 4, 4)
    assert baseline == interleaved == again


@pytest.mark.unit
def test_derive_seed_batteries_rejects_nonpositive_counts() -> None:
    with pytest.raises(ValueError):
        derive_seed_batteries(1, 0, 4)
    with pytest.raises(ValueError):
        derive_seed_batteries(1, 4, 0)


# ---------------------------------------------------------------------------
# Trajectory determinism
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_trajectory_determinism_grid() -> None:
    script = {xh(1): [C] * 6, xh(2): [C, C, C, C, C, P], xh(3): [C, C, C, C, P, P]}
    config = make_config(SOSearchStrategy.GRID)
    res1 = run(config, HashScriptedEvaluator(ARCHETYPE, script))
    res2 = run(config, HashScriptedEvaluator(ARCHETYPE, script))
    assert res1 == res2


@pytest.mark.unit
def test_trajectory_determinism_hill_climb() -> None:
    script = {xh(1): [C] * 6, xh(0): [P] * 6, xh(2): [P] * 6}
    config = make_config(SOSearchStrategy.HILL_CLIMB, max_evaluations=8)
    res1 = run(config, HashScriptedEvaluator(ARCHETYPE, script), bounds=bounds_1d(2))
    res2 = run(config, HashScriptedEvaluator(ARCHETYPE, script), bounds=bounds_1d(2))
    assert res1 == res2


# ---------------------------------------------------------------------------
# Holdout consumption (Decision #5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_holdout_consumed_by_exactly_one_final_call() -> None:
    # 12 all-candidate search wins: p = 2/4096 < 0.05, decisive 12 >= 10,
    # distance 1.0 over a span-1 bound -> PROMOTED end to end.
    script = {xh(1): [C] * 12}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.GRID, n_search_seeds=12, n_holdout_seeds=4)
    result = run(config, recorder, bounds=bounds_1d(1))

    holdout = result.holdout_seeds
    search = result.search_seeds
    holdout_calls = [call for call in recorder.calls if call[2] == holdout]
    assert len(holdout_calls) == 1
    assert recorder.calls[-1][2] == holdout
    for call in recorder.calls[:-1]:
        assert call[2] == search
        assert set(call[2]) & set(holdout) == set()
    assert result.record is not None
    assert result.record.promotion.status is SOPromotionStatus.PROMOTED


# ---------------------------------------------------------------------------
# Hill-climb semantics
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hill_climb_no_move_when_best_neighbor_not_significant() -> None:
    # 3-1 on 4 seeds: direction-positive but p = 0.625 > 0.05 -> no move,
    # current stays the parent, so no rebase, no gate, record is None.
    script = {xh(1): [C, C, C, P]}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.HILL_CLIMB, n_search_seeds=4, max_evaluations=8)
    result = run(config, recorder, bounds=bounds_1d(1))

    assert result.record is None
    assert len(result.trajectory) == 1
    assert result.trajectory[0].candidate_params == {"x": 1}
    # Only the single neighbor evaluation happened: no rebase, no holdout call.
    assert len(recorder.calls) == 1
    assert recorder.calls[0][2] == result.search_seeds


@pytest.mark.unit
def test_hill_climb_final_rebase_vs_original_parent() -> None:
    # x1 beats anything significantly; x0 and x2 lose as candidates. The climb
    # moves 0 -> 1, finds no further qualifying neighbor, then runs ONE explicit
    # current-vs-ORIGINAL-parent evaluation on the search battery before gating.
    script = {xh(1): [C] * 6, xh(0): [P] * 6, xh(2): [P] * 6}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.HILL_CLIMB, max_evaluations=8)
    result = run(config, recorder, bounds=bounds_1d(2))

    search = result.search_seeds
    holdout = result.holdout_seeds
    # Calls: x1-vs-x0, x0-vs-x1, x2-vs-x1, rebase x1-vs-x0 (search), gate x1-vs-x0 (holdout).
    assert [(call[0], call[1], call[2]) for call in recorder.calls] == [
        ({"x": 1}, {"x": 0}, search),
        ({"x": 0}, {"x": 1}, search),
        ({"x": 2}, {"x": 1}, search),
        ({"x": 1}, {"x": 0}, search),
        ({"x": 1}, {"x": 0}, holdout),
    ]
    # The rebase is a re-measurement, not a candidate proposal: 3 trajectory
    # entries, 5 evaluator calls.
    assert len(result.trajectory) == 3
    assert result.evaluations_consumed == 5
    assert result.record is not None
    assert result.record.spec_hash == xh(1)
    # Trajectory comparisons are vs the baseline at that step (current).
    assert result.trajectory[0].comparison.candidate_wins == 6
    assert result.trajectory[1].comparison.parent_wins == 6
    # Provenance format.
    assert result.trajectory[0].generator.generator_id == "search.hill_climb"
    assert result.trajectory[0].generator.selection_reason == "hill_climb_neighbor:x+1@x1"
    assert result.trajectory[1].generator.selection_reason == "hill_climb_neighbor:x-1@x1"
    assert result.trajectory[2].generator.selection_reason == "hill_climb_neighbor:x+1@x1"
    # Indices are contiguous evaluation order.
    assert [entry.index for entry in result.trajectory] == [0, 1, 2]


@pytest.mark.unit
def test_hill_climb_coarse_multiplier_in_selection_reason() -> None:
    # multiplier 2 on a 0..4 lattice from x=0 proposes only x=2 (upper, 2 steps).
    script = {xh(2): [C, C, C, P]}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(
        SOSearchStrategy.HILL_CLIMB, n_search_seeds=4, max_evaluations=8, step_schedule=(2,)
    )
    result = run(config, recorder, bounds=bounds_1d(4))

    assert len(result.trajectory) == 1
    assert result.trajectory[0].generator.selection_reason == "hill_climb_neighbor:x+2@x2"


# ---------------------------------------------------------------------------
# Grid / restart selection rule: lowest p -> win rate -> lex-smaller hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_grid_selection_lowest_p() -> None:
    # x1: 6-0 (p=0.03125) beats x2: 5-1 (p=0.21875) and x3: 4-2 (p=0.6875).
    script = {xh(1): [C] * 6, xh(2): [C, C, C, C, C, P], xh(3): [C, C, C, C, P, P]}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.GRID)
    result = run(config, recorder)

    assert result.record is not None
    assert result.record.spec_hash == xh(1)
    # The gate's holdout call carries the selected candidate.
    assert recorder.calls[-1][0] == {"x": 1}
    # Grid provenance: canonical enumeration order, skipping the parent point.
    assert [entry.candidate_params for entry in result.trajectory] == [
        {"x": 1},
        {"x": 2},
        {"x": 3},
    ]
    for entry in result.trajectory:
        assert entry.generator.generator_id == "search.grid"
        assert entry.generator.selection_reason == "grid_enumeration"
        assert entry.candidate_hash == spec_hash(ARCHETYPE, entry.candidate_params)


@pytest.mark.unit
def test_grid_selection_equal_p_breaks_on_win_rate() -> None:
    # x1: 1-0-2 draws (p=1.0, win rate 1.0); x2: 2-1 (p=1.0, win rate 2/3).
    script = {xh(1): [C, D, D], xh(2): [C, C, P]}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.GRID, n_search_seeds=3)
    result = run(config, recorder, bounds=bounds_1d(2))

    assert result.record is not None
    assert result.record.spec_hash == xh(1)
    assert recorder.calls[-1][0] == {"x": 1}


@pytest.mark.unit
def test_grid_selection_full_tie_breaks_on_lex_smaller_hash() -> None:
    # Identical 2-0-1 outcomes for both candidates: same p, same win rate.
    script = {xh(1): [C, C, D], xh(2): [C, C, D]}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.GRID, n_search_seeds=3)
    result = run(config, recorder, bounds=bounds_1d(2))

    expected_hash = min(xh(1), xh(2))
    assert result.record is not None
    assert result.record.spec_hash == expected_hash
    assert spec_hash(ARCHETYPE, recorder.calls[-1][0]) == expected_hash


@pytest.mark.unit
def test_random_restart_selection_and_provenance() -> None:
    bounds = bounds_1d(10)
    parent: ParamDict = {"x": 0}
    config = make_config(SOSearchStrategy.RANDOM_RESTART, master_seed=7, n_restarts=5)

    # Mirror the pinned candidate derivation: seeded draws, deduped by hash,
    # the parent's own point skipped.
    seen = {spec_hash(ARCHETYPE, parent)}
    expected: list[tuple[int, ParamDict]] = []
    for seed in range(7, 12):
        draw = random_restart(bounds, seed)
        h = spec_hash(ARCHETYPE, draw)
        if h in seen:
            continue
        seen.add(h)
        expected.append((seed, draw))
    assert expected, "test setup: at least one non-parent draw required"

    target_seed, target = expected[0]
    script = {spec_hash(ARCHETYPE, target): [C] * 6}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script, default=[P] * 6))
    result = run(config, recorder, parent=parent, bounds=bounds)

    assert result.record is not None
    assert result.record.spec_hash == spec_hash(ARCHETYPE, target)
    assert [entry.candidate_params for entry in result.trajectory] == [d for _, d in expected]
    assert [entry.generator.selection_reason for entry in result.trajectory] == [
        f"random_restart:{seed}" for seed, _ in expected
    ]
    for entry in result.trajectory:
        assert entry.generator.generator_id == "search.random_restart"
    assert result.trajectory[0].generator.selection_reason == f"random_restart:{target_seed}"


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_budget_exhaustion_reserves_gate_and_never_exceeds() -> None:
    # 10 grid candidates but budget 4: exactly 3 search evaluations happen,
    # the 4th evaluation is the reserved gate holdout call.
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, {}, default=[C] * 6))
    config = make_config(SOSearchStrategy.GRID, max_evaluations=4)
    result = run(config, recorder, bounds=bounds_1d(10))

    assert len(result.trajectory) == 3
    assert result.evaluations_consumed == 4
    assert len(recorder.calls) == 4
    assert len(recorder.calls) <= config.max_evaluations
    assert recorder.calls[-1][2] == result.holdout_seeds
    assert result.record is not None


@pytest.mark.unit
def test_budget_two_with_single_candidate_end_to_end() -> None:
    script = {xh(1): [C] * 6}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script))
    config = make_config(SOSearchStrategy.GRID, max_evaluations=2)
    result = run(config, recorder, bounds=bounds_1d(1))

    assert result.evaluations_consumed == 2
    assert len(recorder.calls) == 2
    assert result.record is not None
    assert result.record.spec_hash == xh(1)


@pytest.mark.unit
def test_hill_climb_budget_never_exceeded() -> None:
    # Everything wins significantly, so the climb would move forever; the
    # budget (with rebase + gate reserves) must stop it without ever exceeding.
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, {}, default=[C] * 6))
    config = make_config(SOSearchStrategy.HILL_CLIMB, max_evaluations=6)
    result = run(config, recorder, bounds=bounds_1d(10))

    assert result.evaluations_consumed <= config.max_evaluations
    assert len(recorder.calls) == result.evaluations_consumed
    # A move happened, so the rebase and gate both ran: last call is holdout.
    assert recorder.calls[-1][2] == result.holdout_seeds
    assert recorder.calls[-2][2] == result.search_seeds
    assert recorder.calls[-2][1] == {"x": 0}  # rebase is vs the ORIGINAL parent


# ---------------------------------------------------------------------------
# All-losers and rejection records (Decision #7)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_losers_record_none_and_no_holdout_call() -> None:
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, {}, default=[P] * 6))
    config = make_config(SOSearchStrategy.GRID)
    result = run(config, recorder)

    assert result.record is None
    assert len(result.trajectory) == 3  # non-empty: the trajectory is the evidence
    for call in recorder.calls:
        assert call[2] == result.search_seeds
        assert set(call[2]) & set(result.holdout_seeds) == set()
    assert result.evaluations_consumed == 3


@pytest.mark.unit
def test_rejected_by_gate_still_yields_full_rejection_record() -> None:
    # x1 is direction-positive and significant, but its normalized distance
    # (0.1 over the 0..10 span) is below min_param_distance=0.5: TRIVIAL_CLONE.
    script = {xh(1): [C] * 6}
    recorder = RecordingEvaluator(HashScriptedEvaluator(ARCHETYPE, script, default=[P] * 6))
    thresholds = ModelSOPromotionThresholds(min_decisive_n=1, min_param_distance=0.5)
    config = make_config(SOSearchStrategy.GRID, max_evaluations=12, thresholds=thresholds)
    result = run(config, recorder, bounds=bounds_1d(10))

    assert result.record is not None
    assert result.record.promotion.status is SOPromotionStatus.REJECTED
    assert result.record.promotion.rejection_reasons == (SOPromotionRejection.TRIVIAL_CLONE,)
    assert result.record.spec_hash == xh(1)
    assert result.record.evidence.search_seeds == result.search_seeds
    assert result.record.evidence.holdout_seeds == result.holdout_seeds


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_loop_purity_source_scan() -> None:
    spec = importlib.util.find_spec("steel_onslaught.learning.loop")
    assert spec is not None and spec.origin is not None
    with open(spec.origin, encoding="utf-8") as fh:
        source = fh.read()

    assert "import time" not in source, "loop.py must not import time"
    assert "datetime" not in source, "loop.py must not reference wall-clock types"
    assert "pathlib" not in source, "loop.py must not import I/O modules"
    assert re.search(r"^\s*(import|from)\s+(os|io|sys|time)\b", source, re.MULTILINE) is None, (
        "loop.py must not import I/O or clock modules"
    )
    assert "random.seed(" not in source, "loop.py must not touch global random state"
    bare_calls = re.findall(
        r"\brandom\.(random|choice|randint|shuffle|sample|randrange|uniform)\(", source
    )
    assert bare_calls == [], f"loop.py must not call global random functions: {bare_calls}"
    assert "random.Random(" in source, "derive_seed_batteries must use a seeded random.Random"


@pytest.mark.unit
def test_doubles_satisfy_evaluator_protocol() -> None:
    scripted: EvaluatorProtocol = HashScriptedEvaluator(ARCHETYPE, {}, default=[C])
    recorder: EvaluatorProtocol = RecordingEvaluator(scripted)
    assert recorder.evaluate({"x": 1}, {"x": 0}, [5])[0].seed == 5
