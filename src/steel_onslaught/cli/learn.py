"""`so learn` — bounded pilot-spec search with promotion gate (Phase 2 Task 5).

Thin CLI: ``learn_command`` parses flags, reads the wall clock ONCE (the only
wall-clock read in the whole learning feature — Architectural Decision #4),
and delegates to the testable ``_run_learn`` composition: parent spec →
``PilotSpecView`` (Task 1) → ``DuelEvaluator`` (Task 2) → ``run_learning_loop``
(Task 4) → ``write_lineage_record`` (Task 3) when a record exists.

Exit code 0 covers every completed loop run — promoted, rejected, AND
no-candidate; rejection is evidence, not error (Decision #7). Non-zero exits
are harness errors only (bad flags, archetype mismatch, missing files, gate
ValueErrors).

The summary never overclaims (addendum §4.3): every run prints p-value,
effect size, Wilson CI, and decisive n — never a bare "better".

``opponent_spec_hashes`` for the gate is the parent's own spec hash: the
Phase 2 meta is the parent pairing; pool-wide metas arrive with populations
(Phase 3+).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from pydantic import ValidationError

from steel_onslaught.contracts.lineage import spec_hash
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.duel_evaluator import DuelEvaluator
from steel_onslaught.learning.loop import (
    ModelSOLearnConfig,
    ModelSOLearnResult,
    SOSearchStrategy,
    run_learning_loop,
)
from steel_onslaught.learning.protocols import ModelSOPairedComparison
from steel_onslaught.learning.spec_adapter import PilotSpecView
from steel_onslaught.learning.stats import wilson_interval
from steel_onslaught.match.composition import (
    build_duel_executor,
    build_runtime_dependencies,
    load_application_overlay,
    load_loadout,
    load_pilot_spec,
)
from steel_onslaught.match.duel import DuelExecutor

_EXISTING_FILE = click.Path(exists=True, dir_okay=False, path_type=Path)


def _run_learn(
    *,
    archetype: str,
    parent_spec: ModelSOPilotSpec,
    strategy: SOSearchStrategy,
    n_search_seeds: int,
    n_holdout_seeds: int,
    max_evaluations: int,
    master_seed: int,
    base_loadout: ModelSOLoadout,
    max_ticks: int,
    recorded_at: datetime,
    duel_executor: DuelExecutor,
    artifacts: LearningArtifactStore,
) -> tuple[ModelSOLearnResult, Path | None]:
    """The testable composition; the caller injects the clock.

    Raises ValueError on harness errors (archetype mismatch, gate input
    bugs); pydantic ValidationError on malformed specs/loadouts.
    """
    if parent_spec.archetype != archetype:
        raise ValueError(
            f"parent spec archetype {parent_spec.archetype!r} does not match "
            f"--archetype {archetype!r} ({parent_spec.id})"
        )
    view = PilotSpecView(parent_spec)
    parent_params = view.parameters
    evaluator = DuelEvaluator(
        archetype=archetype,
        base_loadout=base_loadout,
        max_ticks=max_ticks,
        duel_executor=duel_executor,
        artifacts=artifacts,
    )
    config = ModelSOLearnConfig(
        strategy=strategy,
        master_seed=master_seed,
        n_search_seeds=n_search_seeds,
        n_holdout_seeds=n_holdout_seeds,
        max_evaluations=max_evaluations,
    )
    result = run_learning_loop(
        archetype=archetype,
        parent_params=parent_params,
        bounds=view.bounds,
        evaluator=evaluator,
        opponent_spec_hashes=[spec_hash(archetype, parent_params)],
        config=config,
    )
    record_path: Path | None = None
    if result.record is not None:
        record_path = artifacts.write_lineage(
            result.record,
            recorded_at=recorded_at,
        )
    return result, record_path


def _best_comparison(result: ModelSOLearnResult) -> ModelSOPairedComparison | None:
    """The trajectory comparison closest to significance (same tie-break as
    the loop's candidate selection) — the no-overclaim stats source when no
    record exists."""
    if not result.trajectory:
        return None
    best = min(
        result.trajectory,
        key=lambda entry: (
            entry.comparison.p_value,
            -entry.comparison.candidate_win_rate,
            entry.candidate_hash,
        ),
    )
    return best.comparison


def _summary_stats_line(result: ModelSOLearnResult) -> str:
    """Always p-value, effect size, Wilson CI, decisive n (§4.3) — never a
    bare 'better'."""
    if result.record is not None:
        performance = result.record.performance
        decisive_n = performance.decisive_n
        decisive_wins = round(performance.candidate_win_rate * decisive_n)
        ci_low, ci_high = wilson_interval(decisive_wins, decisive_n)
        return (
            f"stats: p-value={performance.p_value:.6g} "
            f"effect={performance.win_rate_delta:+.4f} "
            f"ci=[{ci_low:.4f}, {ci_high:.4f}] decisive-n={decisive_n}"
        )
    comparison = _best_comparison(result)
    if comparison is None:
        return "stats: p-value=n/a effect=n/a ci=[n/a, n/a] decisive-n=0 (no evaluations)"
    decisive_n = comparison.candidate_wins + comparison.parent_wins
    return (
        f"stats: p-value={comparison.p_value:.6g} "
        f"effect={comparison.effect_size:+.4f} "
        f"ci=[{comparison.ci_low:.4f}, {comparison.ci_high:.4f}] decisive-n={decisive_n}"
    )


def _print_summary(result: ModelSOLearnResult, record_path: Path | None) -> None:
    click.echo(f"strategy: {result.config.strategy.value}")
    click.echo(f"evaluations consumed: {result.evaluations_consumed}")
    if result.record is None:
        click.echo("candidate: none (no candidate beat the parent)")
        click.echo("verdict: no-candidate")
    else:
        click.echo(f"candidate: {result.record.spec_hash}")
        click.echo(f"verdict: {result.record.promotion.status.value}")
        if result.record.promotion.rejection_reasons:
            reasons = ", ".join(r.value for r in result.record.promotion.rejection_reasons)
            click.echo(f"rejection reasons: {reasons}")
    click.echo(_summary_stats_line(result))
    click.echo(f"record: {record_path if record_path is not None else 'none'}")


@click.command(name="learn")
@click.option(
    "--overlay",
    "overlay_path",
    type=_EXISTING_FILE,
    required=True,
)
@click.option(
    "--archetype",
    type=click.Choice(["aggressive", "defensive", "predictive"]),
    required=True,
)
@click.option(
    "--parent",
    "parent_path",
    type=_EXISTING_FILE,
    required=True,
    help="Parent pilot spec YAML; its archetype must match --archetype.",
)
@click.option(
    "--strategy",
    "strategy_name",
    type=click.Choice([s.value for s in SOSearchStrategy]),
    required=True,
)
@click.option(
    "--seeds",
    "n_search_seeds",
    type=click.IntRange(min=1),
    required=True,
    help="Search battery size (derive_seed_batteries).",
)
@click.option(
    "--holdout",
    "n_holdout_seeds",
    type=click.IntRange(min=1),
    required=True,
    help="Holdout battery size (hidden seeds, design §23.1).",
)
@click.option(
    "--budget",
    "max_evaluations",
    type=click.IntRange(min=2),
    required=True,
    help="Max evaluator calls, including the gate's holdout call.",
)
@click.option("--master-seed", type=int, required=True)
@click.option(
    "--base-loadout",
    type=_EXISTING_FILE,
    required=True,
    help="Loadout both sides field; only the pilot parameters differ.",
)
@click.option("--max-ticks", type=click.IntRange(min=1), default=200, show_default=True)
def learn_command(
    overlay_path: Path,
    archetype: str,
    parent_path: Path,
    strategy_name: str,
    n_search_seeds: int,
    n_holdout_seeds: int,
    max_evaluations: int,
    master_seed: int,
    base_loadout: Path,
    max_ticks: int,
) -> None:
    """Bounded pilot-spec search with promotion gate and hidden-seed holdout."""
    try:
        overlay = load_application_overlay(overlay_path)
        dependencies = build_runtime_dependencies(overlay)
        result, record_path = _run_learn(
            archetype=archetype,
            parent_spec=load_pilot_spec(parent_path),
            strategy=SOSearchStrategy(strategy_name),
            n_search_seeds=n_search_seeds,
            n_holdout_seeds=n_holdout_seeds,
            max_evaluations=max_evaluations,
            master_seed=master_seed,
            base_loadout=load_loadout(base_loadout),
            max_ticks=max_ticks,
            recorded_at=dependencies.clock.now(),
            duel_executor=build_duel_executor(overlay),
            artifacts=dependencies.learning_artifacts,
        )
    except (ValueError, ValidationError) as exc:
        raise click.ClickException(str(exc)) from exc
    _print_summary(result, record_path)
