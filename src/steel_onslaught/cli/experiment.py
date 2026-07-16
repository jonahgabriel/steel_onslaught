"""`so learn-experiment` — the LLM-tuner effectiveness harness (plan §4.5-4.6).

Runs the full arm matrix (all five ``ContextArm``s) plus the deterministic
baseline arm, K trials per arm, and emits (1) a plain-text comparison table on
stdout and (2) a machine-readable YAML summary + ROI-compatible row export +
per-run usage sidecars under ``--output-dir``.

This is the CLI *effect boundary*: the wall clock is read exactly once here
(mirroring ``cli/learn.py``'s ``recorded_at`` precedent — the ``ModelSOTunerUsage``
sidecar's ``recorded_at`` is injected from it), and all file I/O and LLM I/O live
here. The pure computation (seeds, metrics, models, negative-control enforcement)
lives in ``llm/experiment.py``.

Enforced negative control: if the requested arm set excludes
``llm_full_design_doc`` the command refuses to run — a run without the
negative-control arm is not a valid effectiveness experiment (addendum).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

import click
from pydantic import ValidationError

from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.cli.learn import _run_learn
from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.loop import ModelSOLearnResult, SOSearchStrategy
from steel_onslaught.learning.spec_adapter import PilotSpecView
from steel_onslaught.llm.context_arms import ContextArm
from steel_onslaught.llm.experiment import (
    ALL_LLM_ARMS,
    BASELINE_ARM,
    PROMPT_TEMPLATE_VERSION,
    ModelSOArmMetrics,
    ModelSOExperimentRow,
    ModelSOExperimentSummary,
    ModelSOTunerUsage,
    compute_arm_metrics,
    context_manifest_hash,
    correlation_id_for,
    derive_experiment_seeds,
    enforce_negative_control,
    factor_subset_hash,
    routing_overlay_hash,
    run_id_for,
)
from steel_onslaught.llm.schemas import LlmUsage, ModelSOLlmEvidenceContext
from steel_onslaught.llm.tuner import ProtocolTunerGenerator
from steel_onslaught.match.composition import (
    LearningDependencies,
    load_application_overlay,
    load_loadout,
    load_pilot_spec,
)
from steel_onslaught.match.duel import DuelExecutor

_EXISTING_FILE = click.Path(exists=True, dir_okay=False, path_type=Path)

# Baseline arm uses a deterministic non-LLM generator; the search seed batteries
# still vary per trial (derived from the varying master seed), so the arm has
# genuine cross-trial variance without any nondeterminism in the generator.
_BASELINE_STRATEGY = SOSearchStrategy.GRID
_BASELINE_PROVIDER = "compute"
_BASELINE_MODEL_ID = "baseline"
_TEMPERATURE = 0.0


def _promoted(result: ModelSOLearnResult) -> bool:
    return result.record is not None and result.record.promotion.status.value == "promoted"


def _failure_stage(result: ModelSOLearnResult) -> str | None:
    if _promoted(result):
        return None
    if result.record is not None:
        return "gate_rejected"
    return "no_candidate"


def _model_id_from_generator(generator_id: str | None) -> str:
    """``llm.<model>@<arm>`` -> ``<model>`` (falls back to the raw id)."""
    if not generator_id:
        return "unknown"
    return generator_id.removeprefix("llm.").split("@", 1)[0] or "unknown"


def _build_row(
    *,
    run_id: str,
    correlation_id: str,
    arm_value: str,
    archetype: str,
    provider: str,
    endpoint_ref: str,
    model_id: str,
    usage: LlmUsage,
    result: ModelSOLearnResult,
    run_order: int,
) -> ModelSOExperimentRow:
    promoted = _promoted(result)
    return ModelSOExperimentRow(
        run_id=run_id,
        correlation_id=correlation_id,
        attempt_count=result.evaluations_consumed,
        first_pass_success=promoted,  # single proposal batch => first == final
        final_success=promoted,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cost_usd=usage.cost_usd,
        model_id=model_id,
        provider=provider,
        context_factor_subset=arm_value,
        context_manifest_hash=context_manifest_hash(
            context_factor_subset=arm_value, archetype=archetype, provider=provider
        ),
        failure_stage=_failure_stage(result),
        endpoint_ref=endpoint_ref,
        factor_subset_hash=factor_subset_hash(arm_value),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        routing_overlay_hash=routing_overlay_hash(provider),
        temperature=_TEMPERATURE,
        run_order=run_order,
    )


def _run_trial(
    *,
    arm_value: str,
    is_baseline: bool,
    master_seed: int,
    run_order: int,
    experiment_seed: int,
    trial: int,
    archetype: str,
    parent_spec: ModelSOPilotSpec,
    base_loadout: ModelSOLoadout,
    n_search_seeds: int,
    n_holdout_seeds: int,
    max_evaluations: int,
    max_ticks: int,
    provider: str,
    design_doc_path: Path | None,
    recorded_at: datetime,
    duel_executor: DuelExecutor,
    artifacts: LearningArtifactStore,
    tuner_generator: ProtocolTunerGenerator,
) -> ModelSOExperimentRow:
    """Materialize candidates (LLM I/O), run the pure loop, persist artifacts.

    Returns the ROI row; writes the usage sidecar next to the lineage record
    when a record exists, else into ``output_dir``.
    """
    run_id = run_id_for(experiment_seed, arm_value, trial)
    correlation_id = correlation_id_for(run_id)
    candidates: tuple[tuple[ParamDict, str], ...] | None
    if is_baseline:
        strategy = _BASELINE_STRATEGY
        candidates = None
        generator_id: str | None = None
        usage = LlmUsage(prompt_tokens=0, completion_tokens=0, cost_usd=0.0)
        provider_name = _BASELINE_PROVIDER
        endpoint_ref = _BASELINE_PROVIDER
        model_id = _BASELINE_MODEL_ID
    else:
        strategy = SOSearchStrategy.EXTERNAL
        view = PilotSpecView(parent_spec)
        generation = tuner_generator.generate(
            provider_id=provider,
            arm=ContextArm(arm_value),
            archetype=archetype,
            parent_params=view.parameters,
            bounds=view.bounds,
            n_proposals=max_evaluations - 1,
            evidence_context=ModelSOLlmEvidenceContext(
                match_id=run_id,
                mech_id=f"tuner.{archetype}",
                player_id="experiment.operator",
                tick=0,
                correlation_id=UUID(correlation_id),
            ),
            design_doc_path=design_doc_path,
        )
        candidates = generation.candidates
        generator_id = generation.generator_id
        usage = generation.usage
        provider_name = provider
        endpoint_ref = provider
        model_id = _model_id_from_generator(generator_id)

    result, record_path = _run_learn(
        archetype=archetype,
        parent_spec=parent_spec,
        strategy=strategy,
        n_search_seeds=n_search_seeds,
        n_holdout_seeds=n_holdout_seeds,
        max_evaluations=max_evaluations,
        master_seed=master_seed,
        base_loadout=base_loadout,
        max_ticks=max_ticks,
        recorded_at=recorded_at,
        duel_executor=duel_executor,
        artifacts=artifacts,
        candidates=candidates,
        generator_id=generator_id,
    )

    row = _build_row(
        run_id=run_id,
        correlation_id=correlation_id,
        arm_value=arm_value,
        archetype=archetype,
        provider=provider_name,
        endpoint_ref=endpoint_ref,
        model_id=model_id,
        usage=usage,
        result=result,
        run_order=run_order,
    )

    sidecar = ModelSOTunerUsage(
        run_id=run_id,
        correlation_id=correlation_id,
        arm=arm_value,
        provider=provider_name,
        model_id=model_id,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cost_usd=usage.cost_usd,
        recorded_at=recorded_at,
    )
    artifacts.write_tuner_usage(sidecar, lineage_record=record_path)

    return row


def _format_table(summary: ModelSOExperimentSummary) -> str:
    def _fmt_float(value: float | None) -> str:
        return f"{value:.4g}" if value is not None else "n/a"

    header = (
        f"{'arm':<22} {'K':>3} {'promoted':>9} "
        f"{'first_batch_rate':>17} {'mean_attempts':>14} {'cost/promotion':>15}"
    )
    lines = [header, "-" * len(header)]
    for metrics in summary.arm_metrics:
        lines.append(
            f"{metrics.arm:<22} {metrics.k_trials:>3} "
            f"{metrics.n_promoted:>9} "
            f"{metrics.first_batch_promotion_rate:>17.4f} "
            f"{_fmt_float(metrics.mean_attempts_to_promotion):>14} "
            f"{_fmt_float(metrics.cost_per_promotion):>15}"
        )
    return "\n".join(lines)


def _execute_experiment(
    *,
    dependencies: LearningDependencies,
    archetype: str,
    parent_path: Path,
    base_loadout: Path,
    experiment_seed: int,
    n_search_seeds: int,
    n_holdout_seeds: int,
    max_evaluations: int,
    k_trials: int,
    max_ticks: int,
    llm_provider: str,
    arm_names: tuple[str, ...],
    design_doc_path: Path | None,
) -> None:
    recorded_at = dependencies.clock.now()
    parent_spec = load_pilot_spec(parent_path)
    loaded_base_loadout = load_loadout(base_loadout)
    selected_arms: tuple[ContextArm, ...] = (
        ALL_LLM_ARMS if not arm_names else tuple(ContextArm(name) for name in arm_names)
    )
    try:
        enforce_negative_control(selected_arms)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    arm_matrix: list[tuple[str, bool]] = [(arm.value, False) for arm in selected_arms]
    arm_matrix.append((BASELINE_ARM, True))
    master_seeds = derive_experiment_seeds(experiment_seed, k_trials)
    arm_metrics_list: list[ModelSOArmMetrics] = []
    all_rows: list[ModelSOExperimentRow] = []
    run_order = 0
    try:
        for arm_value, is_baseline in arm_matrix:
            arm_rows: list[ModelSOExperimentRow] = []
            for trial, master_seed in enumerate(master_seeds):
                row = _run_trial(
                    arm_value=arm_value,
                    is_baseline=is_baseline,
                    master_seed=master_seed,
                    run_order=run_order,
                    experiment_seed=experiment_seed,
                    trial=trial,
                    archetype=archetype,
                    parent_spec=parent_spec,
                    base_loadout=loaded_base_loadout,
                    n_search_seeds=n_search_seeds,
                    n_holdout_seeds=n_holdout_seeds,
                    max_evaluations=max_evaluations,
                    max_ticks=max_ticks,
                    provider=llm_provider,
                    design_doc_path=design_doc_path,
                    recorded_at=recorded_at,
                    duel_executor=dependencies.duel_executor,
                    artifacts=dependencies.artifacts,
                    tuner_generator=dependencies.tuner_generator,
                )
                arm_rows.append(row)
                all_rows.append(row)
                run_order += 1
            arm_metrics_list.append(compute_arm_metrics(arm_value, arm_rows))
    except (ValueError, ValidationError) as exc:
        raise click.ClickException(str(exc)) from exc

    summary = ModelSOExperimentSummary(
        experiment_seed=experiment_seed,
        archetype=archetype,
        provider=llm_provider,
        k_trials=k_trials,
        master_seeds=master_seeds,
        arms=tuple(arm_value for arm_value, _ in arm_matrix),
        arm_metrics=tuple(arm_metrics_list),
    )
    summary_path = dependencies.artifacts.write_experiment_summary(summary)
    rows_path = dependencies.artifacts.write_experiment_rows(tuple(all_rows))
    click.echo(_format_table(summary))
    click.echo(f"summary: {summary_path}")
    click.echo(f"rows: {rows_path}")


@click.command(name="learn-experiment")
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
    "--base-loadout",
    type=_EXISTING_FILE,
    required=True,
    help="Loadout both sides field; only the pilot parameters differ.",
)
@click.option(
    "--experiment-seed",
    type=int,
    required=True,
    help="Single seed the K per-trial master seeds are derived from.",
)
@click.option(
    "--seeds",
    "n_search_seeds",
    type=click.IntRange(min=1),
    required=True,
    help="Search battery size (per trial).",
)
@click.option(
    "--holdout",
    "n_holdout_seeds",
    type=click.IntRange(min=1),
    required=True,
    help="Holdout battery size (per trial).",
)
@click.option(
    "--budget",
    "max_evaluations",
    type=click.IntRange(min=2),
    required=True,
    help="Max evaluator calls per trial, including the gate's holdout call.",
)
@click.option(
    "--k",
    "k_trials",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    help="Trials per arm (plan §4.5 pins K=5).",
)
@click.option("--max-ticks", type=click.IntRange(min=1), default=200, show_default=True)
@click.option(
    "--llm-provider",
    required=True,
    help="Provider id declared by the application overlay.",
)
@click.option(
    "--arm",
    "arm_names",
    type=click.Choice([a.value for a in ContextArm]),
    multiple=True,
    help="LLM arms to run (default: all five). Excluding llm_full_design_doc "
    "is refused — it is the mandatory negative control.",
)
@click.option(
    "--design-doc",
    "design_doc_path",
    type=_EXISTING_FILE,
    default=None,
    help="Design doc for the llm_full_design_doc (negative-control) arm context.",
)
def learn_experiment_command(
    overlay_path: Path,
    archetype: str,
    parent_path: Path,
    base_loadout: Path,
    experiment_seed: int,
    n_search_seeds: int,
    n_holdout_seeds: int,
    max_evaluations: int,
    k_trials: int,
    max_ticks: int,
    llm_provider: str,
    arm_names: tuple[str, ...],
    design_doc_path: Path | None,
) -> None:
    """Run the LLM-tuner arm matrix + deterministic baseline, K trials per arm."""
    overlay = load_application_overlay(overlay_path)
    with CliApplicationFactory.packaged().learning(overlay) as dependencies:
        _execute_experiment(
            dependencies=dependencies,
            archetype=archetype,
            parent_path=parent_path,
            base_loadout=base_loadout,
            experiment_seed=experiment_seed,
            n_search_seeds=n_search_seeds,
            n_holdout_seeds=n_holdout_seeds,
            max_evaluations=max_evaluations,
            k_trials=k_trials,
            max_ticks=max_ticks,
            llm_provider=llm_provider,
            arm_names=arm_names,
            design_doc_path=design_doc_path,
        )


__all__ = ["learn_experiment_command"]
