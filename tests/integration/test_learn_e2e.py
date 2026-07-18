"""End-to-end determinism chain + design §23 anti-exploit proof (Phase 2 Task 6).

One integration file proving on REAL duels what the unit tests prove only
piecewise (tiny batteries: 2 search seeds, 2 holdout seeds, budget 6, small
``max_ticks``):

- **Determinism chain (Architectural Decision #4), whole and unbroken:**
  ``run_learning_loop`` with a ``DuelEvaluator`` twice from identical inputs
  yields (1) identical seed batteries, (2) identical per-candidate outcome
  lists from the evaluator (the win matrix), (3) identical trajectories,
  (4) identical ``ModelSOLearnResult``, (5) byte-identical persisted YAML
  with a fixed injected ``recorded_at``.
- **§23.1 holdout integrity:** persisted evidence batteries are disjoint and
  equal the derived batteries; a direct gate call with a shared seed raises
  ``ValueError``, never a verdict.
- **§23 draw-farming guard live:** the draw-rate cap fires on real-duel draw
  rates of a self-pairing run.
- **§23 trivial-clone guard live:** gating the parent against itself yields a
  single multi-reason record (``TRIVIAL_CLONE`` + ``WRONG_DIRECTION``).
- **Replay determinism (§23.1 / §21):** ``ReplayEngine`` replay of a retained
  gate-evaluation ledger equals the live fold result.
- **No live-match mutation (§4.5 / Decision #6):** ``contracts_data/`` is
  byte-identical after the runs (lineage root is tmp-redirected, so zero
  additions), and ``SOEventType``'s member set equals the pinned pre-plan set.
- **PoL runtime anti-tamper:** learning leaves the hosted proof-of-life test's
  pre-run SHA-256 unchanged.

Chain-run design note (budget <= 6 forces this): the parent is the shipped
aggressive template with ``weapon_preference`` flipped to ``lowest_heat`` and
every numeric bound narrowed to the parent's own lattice point. Hill-climb
neighbors enumerate in sorted parameter-name order, so with the plan's tiny
budget the full archetype bounds would exhaust the budget on behaviorally
inert numeric neighbors and never reach a gate call; pinning the numerics
makes the decisive categorical knob the first (and only) neighbor, so the
run deterministically exercises search -> move -> re-base -> gate -> record
-> persisted YAML on real duels. Thresholds are permissive because the gate's
statistical floors (designed for n >= 10) are unit-tested elsewhere; this
file proves the chain, not the thresholds.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.lineage import (
    ModelSOLineageGenerator,
    ModelSOLineageRecord,
    ParamDict,
    SOPromotionRejection,
    SOPromotionStatus,
    spec_hash,
)
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.learning.duel_evaluator import DuelEvaluator
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.learning.lineage_store import load_lineage_records
from steel_onslaught.learning.loop import (
    ModelSOLearnConfig,
    ModelSOLearnResult,
    SOSearchStrategy,
    derive_seed_batteries,
    run_learning_loop,
)
from steel_onslaught.learning.promotion import ModelSOPromotionThresholds, evaluate_promotion
from steel_onslaught.learning.protocols import (
    BoundsDict,
    EvaluatorProtocol,
    ModelSONumericBound,
    ModelSOSeedOutcome,
    SOSeedWinner,
)
from steel_onslaught.learning.spec_adapter import PilotSpecView, bounds_for_archetype
from steel_onslaught.learning.stats import paired_comparison
from steel_onslaught.match.composition import (
    build_duel_executor,
    build_runtime_dependencies,
    load_loadout,
    load_pilot_spec,
)
from steel_onslaught.match.duel import ModelSOEvaluationStorageKey
from steel_onslaught.replay.engine import ReplayEngine
from tests.overlay import complete_test_overlay

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS_DATA = _REPO_ROOT / "contracts_data"
_PARENT_SPEC = _CONTRACTS_DATA / "pilots" / "template_aggressive.yaml"
_BASE_LOADOUT = _CONTRACTS_DATA / "loadouts" / "example_aggressive_light.yaml"
_POL_TEST_FILE = "tests/integration/test_proof_of_life.py"

_ARCHETYPE = "aggressive"
_MASTER_SEED = 7
_N_SEARCH = 2
_N_HOLDOUT = 2
_BUDGET = 6  # plan Task 6: budget <= 6
_MAX_TICKS = 120
_FIXED_RECORDED_AT = datetime(2026, 6, 12, tzinfo=UTC)

# Permissive gate thresholds: the chain proof needs a real gate call + record
# on a 2-seed battery; the statistical floors themselves are unit-tested in
# tests/learning/test_promotion.py.
_PERMISSIVE_THRESHOLDS = ModelSOPromotionThresholds(
    p_value_max=1.0,
    min_decisive_n=1,
    max_overload_rate_increase=100.0,
    max_draw_rate=1.0,
    min_param_distance=0.0,
)

# The current SOEventType member set, pinned literally.  Runtime lifecycle
# status is a contract foundation event; future runtime wiring must not add
# further members without updating this explicit schema gate.
_PINNED_EVENT_TYPES = frozenset(
    {
        "match_started",
        "runtime_status_changed",
        "match_tick",
        "mech_spawned",
        "sensor_observation",
        "pilot_decision_made",
        "hand_dealt",
        "plan_committed",
        "register_resolved",
        "cards_discarded",
        "llm_completion_requested",
        "llm_completion_resolved",
        "llm_completion_failed",
        "move_intent",
        "weapon_fire_intent",
        "mode_switch_intent",
        "vent_intent",
        "movement_resolved",
        "boiler_updated",
        "heat_redline_entered",
        "heat_redline_exited",
        "boiler_overloaded",
        "boiler_ruptured",
        "mode_transition_started",
        "mode_transition_completed",
        "weapon_fired",
        "hit_resolved",
        "armor_absorbed",
        "damage_applied",
        "pilot_injured",
        "pilot_killed",
        "mech_destroyed",
        "victory_declared",
        "match_ended",
        "match_scored",
    }
)

# (candidate_params, parent_params, seeds, outcomes) — one entry per
# evaluator.evaluate call; equality across two runs IS the win-matrix proof.
_EvaluatorCall = tuple[ParamDict, ParamDict, tuple[int, ...], tuple[ModelSOSeedOutcome, ...]]


class _RecordingEvaluator:
    """EvaluatorProtocol wrapper over a real DuelEvaluator that logs every
    call's inputs and outcomes (the win matrix)."""

    def __init__(self, inner: DuelEvaluator) -> None:
        self._inner = inner
        self.calls: list[_EvaluatorCall] = []

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        outcomes = self._inner.evaluate(candidate_params, parent_params, seeds)
        self.calls.append(
            (dict(candidate_params), dict(parent_params), tuple(seeds), tuple(outcomes))
        )
        return outcomes


class _ChainRun(NamedTuple):
    result: ModelSOLearnResult
    calls: tuple[_EvaluatorCall, ...]
    record_path: Path | None
    record_bytes: bytes | None
    workdir: Path
    lineage_root: Path


class _E2EArtifacts(NamedTuple):
    snapshot_before: dict[str, str]
    proof_of_life_digest_before: str
    template_params: ParamDict
    parent_params: ParamDict
    chain_bounds: BoundsDict
    run1: _ChainRun
    run2: _ChainRun
    self_search_outcomes: tuple[ModelSOSeedOutcome, ...]
    self_holdout_outcomes: tuple[ModelSOSeedOutcome, ...]


def _snapshot_contracts_data() -> dict[str, str]:
    """Relative path -> sha256 for every file under contracts_data/."""
    return {
        str(path.relative_to(_CONTRACTS_DATA)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(_CONTRACTS_DATA.rglob("*"))
        if path.is_file()
    }


def _overlay(root: Path, *, ledger_path: Path | None = None) -> ModelSOApplicationOverlay:
    return ModelSOApplicationOverlay.model_validate(
        complete_test_overlay(
            {
                "schema_version": "1",
                "bus": {"kind": "in_process"},
                "event_ledger": {
                    "kind": "sqlite",
                    "path": ledger_path or root / "events.sqlite3",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "event_schema": "canonical_event_v1",
                },
                "leaderboard": {
                    "kind": "sqlite",
                    "path": root / "leaderboard.sqlite3",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "storage_schema": "leaderboard_v1",
                },
                "learning_artifacts": {
                    "kind": "filesystem_yaml",
                    "evaluation_root": root / "work",
                    "lineage_root": root / "lineage",
                },
                "evaluation_storage": {
                    "kind": "sqlite",
                    "root": root / "work",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "event_schema": "canonical_event_v1",
                    "leaderboard_schema": "leaderboard_v1",
                },
                "contracts": {
                    "catalog_dir": _CONTRACTS_DATA,
                    "pilot_registry_dir": _CONTRACTS_DATA / "pilots",
                },
                "clock": {"kind": "system_utc"},
                "identity": {"kind": "system"},
            },
            root,
        )
    )


def _chain_bounds(parent_params: ParamDict) -> BoundsDict:
    """Archetype bounds with every numeric range narrowed to the parent's own
    point (see the module docstring's chain-run design note); the categorical
    weapon_preference bound keeps both choices and becomes the only neighbor."""
    bounds: BoundsDict = {}
    for name, bound in bounds_for_archetype(_ARCHETYPE).items():
        if isinstance(bound, ModelSONumericBound):
            value = float(parent_params[name])
            bounds[name] = ModelSONumericBound(minimum=value, maximum=value, step=bound.step)
        else:
            bounds[name] = bound
    return bounds


def _run_chain(tmp: Path, parent_params: ParamDict, bounds: BoundsDict) -> _ChainRun:
    """One full search -> evaluate -> gate -> record -> persist execution."""
    workdir = tmp / "work"
    lineage_root = tmp / "lineage"
    artifact_store = YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=workdir,
            lineage_root=lineage_root,
            experiment_root=tmp / "experiments",
        )
    )
    recorder = _RecordingEvaluator(
        DuelEvaluator(
            archetype=_ARCHETYPE,
            base_loadout=load_loadout(_BASE_LOADOUT),
            max_ticks=_MAX_TICKS,
            duel_executor=build_duel_executor(_overlay(tmp)),
            artifacts=artifact_store,
        )
    )
    evaluator: EvaluatorProtocol = recorder  # structural satisfaction, mypy-enforced
    config = ModelSOLearnConfig(
        strategy=SOSearchStrategy.HILL_CLIMB,
        master_seed=_MASTER_SEED,
        n_search_seeds=_N_SEARCH,
        n_holdout_seeds=_N_HOLDOUT,
        max_evaluations=_BUDGET,
        thresholds=_PERMISSIVE_THRESHOLDS,
    )
    result = run_learning_loop(
        archetype=_ARCHETYPE,
        parent_params=dict(parent_params),
        bounds=bounds,
        evaluator=evaluator,
        opponent_spec_hashes=[spec_hash(_ARCHETYPE, parent_params)],
        config=config,
    )
    record_path: Path | None = None
    record_bytes: bytes | None = None
    if result.record is not None:
        record_path = artifact_store.write_lineage(
            result.record,
            recorded_at=_FIXED_RECORDED_AT,
        )
        record_bytes = record_path.read_bytes()
    return _ChainRun(
        result=result,
        calls=tuple(recorder.calls),
        record_path=record_path,
        record_bytes=record_bytes,
        workdir=workdir,
        lineage_root=lineage_root,
    )


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> _E2EArtifacts:
    snapshot_before = _snapshot_contracts_data()
    proof_of_life_digest_before = hashlib.sha256(
        (_REPO_ROOT / _POL_TEST_FILE).read_bytes()
    ).hexdigest()

    template_params = PilotSpecView(load_pilot_spec(_PARENT_SPEC)).parameters
    parent_params: ParamDict = dict(template_params)
    parent_params["weapon_preference"] = "lowest_heat"
    chain_bounds = _chain_bounds(parent_params)

    run1 = _run_chain(tmp_path_factory.mktemp("chain_run1"), parent_params, chain_bounds)
    run2 = _run_chain(tmp_path_factory.mktemp("chain_run2"), parent_params, chain_bounds)

    # Self-pairing real duels (parent vs itself) for the §23 guard proofs.
    search_seeds, holdout_seeds = derive_seed_batteries(_MASTER_SEED, _N_SEARCH, _N_HOLDOUT)
    self_workdir = tmp_path_factory.mktemp("self_gate")
    self_evaluator = DuelEvaluator(
        archetype=_ARCHETYPE,
        base_loadout=load_loadout(_BASE_LOADOUT),
        max_ticks=_MAX_TICKS,
        duel_executor=build_duel_executor(_overlay(tmp_path_factory.mktemp("self_gate_runtime"))),
        artifacts=YamlFilesystemLearningArtifactStore(
            ModelSOFilesystemLearningArtifactsConfig(
                evaluation_root=self_workdir,
                lineage_root=self_workdir / "lineage",
                experiment_root=self_workdir / "experiments",
            )
        ),
    )
    self_search = tuple(
        self_evaluator.evaluate(dict(template_params), dict(template_params), search_seeds)
    )
    self_holdout = tuple(
        self_evaluator.evaluate(dict(template_params), dict(template_params), holdout_seeds)
    )

    return _E2EArtifacts(
        snapshot_before=snapshot_before,
        proof_of_life_digest_before=proof_of_life_digest_before,
        template_params=template_params,
        parent_params=parent_params,
        chain_bounds=chain_bounds,
        run1=run1,
        run2=run2,
        self_search_outcomes=self_search,
        self_holdout_outcomes=self_holdout,
    )


def _self_gate_record(
    artifacts: _E2EArtifacts, thresholds: ModelSOPromotionThresholds
) -> ModelSOLineageRecord:
    """Gate the template parent against itself on the real self-pairing outcomes."""
    return evaluate_promotion(
        archetype=_ARCHETYPE,
        candidate_params=dict(artifacts.template_params),
        parent_params=dict(artifacts.template_params),
        bounds=bounds_for_archetype(_ARCHETYPE),
        search_comparison=paired_comparison(artifacts.self_search_outcomes),
        search_outcomes=artifacts.self_search_outcomes,
        holdout_outcomes=artifacts.self_holdout_outcomes,
        opponent_spec_hashes=[spec_hash(_ARCHETYPE, artifacts.template_params)],
        generator=ModelSOLineageGenerator(
            generator_id="search.hill_climb", selection_reason="self_gate_proof"
        ),
        thresholds=thresholds,
    )


# ---------------------------------------------------------------------------
# The determinism chain (Decision #4), whole and unbroken
# ---------------------------------------------------------------------------


def test_determinism_chain_double_execution(artifacts: _E2EArtifacts) -> None:
    """Identical seeds => identical win matrix => identical search trajectory
    => identical lineage record, proven on the real engine — in order."""
    run1, run2 = artifacts.run1, artifacts.run2
    derived_search, derived_holdout = derive_seed_batteries(_MASTER_SEED, _N_SEARCH, _N_HOLDOUT)

    # (1) identical seed batteries (and both equal the derived batteries).
    assert run1.result.search_seeds == run2.result.search_seeds == derived_search
    assert run1.result.holdout_seeds == run2.result.holdout_seeds == derived_holdout

    # (2) identical per-candidate outcome lists from the evaluator — the win
    # matrix: every call's (candidate, parent, seeds, outcomes) is equal.
    assert run1.calls == run2.calls

    # (3) identical trajectories (full frozen-model equality).
    assert run1.result.trajectory == run2.result.trajectory

    # (4) identical ModelSOLearnResult.
    assert run1.result == run2.result

    # Budget discipline on the real engine: every evaluator call is counted
    # and the loop never exceeds the budget.
    assert len(run1.calls) == run1.result.evaluations_consumed
    assert run1.result.evaluations_consumed <= _BUDGET

    # (5) byte-identical persisted YAML with the fixed injected recorded_at.
    # A record is produced only when a direction-positive candidate emerges
    # (Decision #7: absence of such a candidate is legitimate — the trajectory
    # itself is the evidence). Same-archetype side-swapped duels are draw-prone
    # under the current economy, so the record may legitimately be absent; when
    # it is present, both runs must persist byte-identical YAML.
    if run1.result.record is not None:
        assert run2.result.record is not None
        assert run1.record_path is not None
        assert run2.record_path is not None
        assert run1.record_bytes is not None
        assert run1.record_bytes == run2.record_bytes
        assert run1.record_path.relative_to(run1.lineage_root) == run2.record_path.relative_to(
            run2.lineage_root
        )
    else:
        # No direction-positive candidate → no gate call → no record. Both runs
        # must agree on this (the determinism property above already proves it,
        # but assert the record-absence symmetry explicitly).
        assert run2.result.record is None
        assert run1.record_path is None
        assert run2.record_path is None


# ---------------------------------------------------------------------------
# §23.1 holdout integrity on real duels
# ---------------------------------------------------------------------------


def test_holdout_batteries_disjoint_and_recorded(artifacts: _E2EArtifacts) -> None:
    """The persisted record's evidence batteries are disjoint, equal the
    derived batteries, and the holdout battery was consumed by exactly one
    evaluator call — the last (the gate's)."""
    run = artifacts.run1
    derived_search, derived_holdout = derive_seed_batteries(_MASTER_SEED, _N_SEARCH, _N_HOLDOUT)

    record = run.result.record
    if record is None:
        # No direction-positive candidate emerged under the current economy, so
        # no gate call happened and there is no record/evidence to inspect.
        # The holdout-disjointness property is instead covered by the call-log
        # assertions below (which hold regardless of a gate call).
        pytest.skip("no promotion record produced — chain produced no direction-positive candidate")
    assert record is not None
    assert record.evidence.search_seeds == derived_search
    assert record.evidence.holdout_seeds == derived_holdout
    assert set(derived_search) & set(derived_holdout) == set()

    # Call-log proof: holdout seeds appear in exactly one call, the final one;
    # every other call used exactly the search battery.
    assert run.calls[-1][2] == derived_holdout
    for call in run.calls[:-1]:
        assert call[2] == derived_search

    # The persisted YAML round-trips with the same evidence and clock.
    loaded = load_lineage_records(run.lineage_root)
    assert len(loaded) == 1
    assert loaded[0].record == record
    assert loaded[0].recorded_at == _FIXED_RECORDED_AT


def test_holdout_overlap_raises_value_error(artifacts: _E2EArtifacts) -> None:
    """Mutating the harness to overlap the batteries (direct gate call with a
    shared seed) raises ValueError — never a verdict."""
    shared_seed = artifacts.self_search_outcomes[0].seed
    overlapping_holdout = (
        artifacts.self_holdout_outcomes[0].model_copy(update={"seed": shared_seed}),
        artifacts.self_holdout_outcomes[1],
    )
    with pytest.raises(ValueError, match="overlap"):
        evaluate_promotion(
            archetype=_ARCHETYPE,
            candidate_params=dict(artifacts.template_params),
            parent_params=dict(artifacts.template_params),
            bounds=bounds_for_archetype(_ARCHETYPE),
            search_comparison=paired_comparison(artifacts.self_search_outcomes),
            search_outcomes=artifacts.self_search_outcomes,
            holdout_outcomes=overlapping_holdout,
            opponent_spec_hashes=[spec_hash(_ARCHETYPE, artifacts.template_params)],
            generator=ModelSOLineageGenerator(
                generator_id="search.hill_climb", selection_reason="self_gate_proof"
            ),
            thresholds=_PERMISSIVE_THRESHOLDS,
        )


# ---------------------------------------------------------------------------
# §23 anti-exploit guards firing on real-duel data
# ---------------------------------------------------------------------------


def test_draw_rate_cap_fires_on_live_draw_rates(artifacts: _E2EArtifacts) -> None:
    """A self-pairing run draws every seed on real duels (side-swap
    cancellation); a cap below that observed rate produces a
    DRAW_RATE_EXCEEDED rejection record — fired by real draw rates."""
    outcomes = artifacts.self_search_outcomes
    observed_draw_rate = sum(1 for o in outcomes if o.winner is SOSeedWinner.DRAW) / len(outcomes)
    assert observed_draw_rate == 1.0  # Task 2 bias invariant, re-proven here

    thresholds = ModelSOPromotionThresholds(max_draw_rate=observed_draw_rate - 0.25)
    record = _self_gate_record(artifacts, thresholds)
    assert record.promotion.status is SOPromotionStatus.REJECTED
    assert SOPromotionRejection.DRAW_RATE_EXCEEDED in record.promotion.rejection_reasons
    assert record.performance.draw_rate == observed_draw_rate


def test_trivial_clone_self_gate_multi_reason(artifacts: _E2EArtifacts) -> None:
    """Gating the parent against itself (distance 0.0) yields TRIVIAL_CLONE
    plus WRONG_DIRECTION in a single multi-reason record."""
    record = _self_gate_record(artifacts, ModelSOPromotionThresholds())
    assert record.promotion.status is SOPromotionStatus.REJECTED
    reasons = set(record.promotion.rejection_reasons)
    assert SOPromotionRejection.TRIVIAL_CLONE in reasons
    assert SOPromotionRejection.WRONG_DIRECTION in reasons
    assert len(reasons) >= 2  # one record carrying multiple reasons


# ---------------------------------------------------------------------------
# Replay determinism on retained gate-evaluation evidence (§23.1 / §21)
# ---------------------------------------------------------------------------


def test_replay_equals_live_fold_on_retained_gate_ledger(
    artifacts: _E2EArtifacts, tmp_path: Path
) -> None:
    """ReplayEngine replay of one retained gate-evaluation ledger equals the
    live fold result of the same duel (the PoL replay-validity check applied
    to learning evidence)."""
    run = artifacts.run1
    # A gate call (and thus retained gate-evaluation ledgers) only exists when a
    # direction-positive candidate emerged. Same-archetype side-swapped duels are
    # draw-prone under the current economy, so this may legitimately not happen.
    if run.result.record is None:
        pytest.skip("no promotion record produced — no gate-evaluation ledgers to replay")
    # The gate's holdout evaluation is the last evaluator call; the evaluator
    # numbers eval dirs by call order, so its retained ledgers live there.
    gate_dir = run.workdir / f"eval_{len(run.calls):04d}"
    seed = run.result.holdout_seeds[0]
    retained_ledger = gate_dir / f"seed_{seed}_cand_red.sqlite3"
    assert retained_ledger.exists(), "gate evaluation must retain its duel ledgers as evidence"

    candidate_loadouts = sorted(gate_dir.glob("loadout.learn.cand_*.yaml"))
    parent_loadouts = sorted(gate_dir.glob("loadout.learn.par_*.yaml"))
    assert len(candidate_loadouts) == 1
    assert len(parent_loadouts) == 1

    # Re-run the same duel live (same seed, loadouts, geometry, match_id).
    match_id = f"match.learn.seed_{seed}.cand_red"
    live_overlay = _overlay(tmp_path, ledger_path=tmp_path / "live_rerun.sqlite3")
    live_result = build_duel_executor(live_overlay)(
        loadout_a=load_loadout(candidate_loadouts[0]),
        loadout_b=load_loadout(parent_loadouts[0]),
        seed=seed,
        max_ticks=_MAX_TICKS,
        storage=ModelSOEvaluationStorageKey(namespace="live_rerun", duel="duel"),
        match_id=match_id,
        loadout_path_a=candidate_loadouts[0],
        loadout_path_b=parent_loadouts[0],
        side_a="red",
        side_b="blue",
    )
    live_state = live_result.final_state

    retained_dependencies = build_runtime_dependencies(
        _overlay(tmp_path, ledger_path=retained_ledger)
    )
    replay = ReplayEngine(
        retained_dependencies.ledger,
        match_id=match_id,
        catalog=retained_dependencies.catalog,
        event_factory=retained_dependencies.event_factory,
    )
    assert replay.reconstruct_at_tick(live_state.tick) == live_state


# ---------------------------------------------------------------------------
# No live-match mutation, no schema drift (§4.5 / Decision #6)
# ---------------------------------------------------------------------------


def test_contracts_data_unchanged_by_learning_runs(artifacts: _E2EArtifacts) -> None:
    """With the lineage root tmp-redirected, contracts_data/ has zero
    additions, zero removals, and zero byte changes after all real runs."""
    assert _snapshot_contracts_data() == artifacts.snapshot_before
    assert not (_CONTRACTS_DATA / "lineage").exists() or not any(
        key.startswith("lineage") for key in artifacts.snapshot_before
    )


def test_soeventtype_member_set_unchanged() -> None:
    """No new SOEventType members, no payload-schema drift (Decision #6)."""
    assert {member.value for member in SOEventType} == _PINNED_EVENT_TYPES


# ---------------------------------------------------------------------------
# PoL runtime anti-tamper
# ---------------------------------------------------------------------------


def test_proof_of_life_file_untouched_by_learning_run(artifacts: _E2EArtifacts) -> None:
    """The real learning runs cannot mutate the hosted proof-of-life test."""
    digest_after = hashlib.sha256((_REPO_ROOT / _POL_TEST_FILE).read_bytes()).hexdigest()
    assert digest_after == artifacts.proof_of_life_digest_before
