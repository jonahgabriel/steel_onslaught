"""LLM-tuner experiment harness — models + pure computation (plan §4.5-4.6).

This module owns the *pure* half of ``so learn-experiment``: the experiment
config, the seed-derivation, the negative-control enforcement, the ROI-row and
usage-sidecar models, and the per-arm metric roll-up. All wall-clock reads and
file I/O live in the CLI boundary (``cli/experiment.py``), never here — this
module has no wall-clock and no side effects, so its outputs are a pure function
of its inputs.

Design decisions (pinned by plan §4.5, not re-derived):

- **K trials per arm**, with the K master seeds derived deterministically from a
  single ``experiment_seed`` (:func:`derive_experiment_seeds`). Baseline-arm
  variance requires a *varying* master seed per trial — a single seed yields
  zero variance by construction.
- **Enforced negative control**: an experiment that excludes
  ``llm_full_design_doc`` is not a valid effectiveness experiment
  (:func:`enforce_negative_control` raises).
- **Headline metrics per arm**: ``attempts_to_promotion`` (per-trial
  ``evaluations_consumed`` until promotion, ``None`` when never promoted),
  ``cost_per_promotion`` (summed usage / promotions; compute-only 0 for the
  baseline arm), and ``first_batch_promotion_rate`` (fraction of trials whose
  single proposal batch produced a promoted candidate).
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from steel_onslaught.llm.context_arms import ContextArm

# The deterministic non-LLM generator arm (Phase-2 baseline floor). Not a
# ``ContextArm`` — it consumes no LLM context and spends no tokens.
BASELINE_ARM = "baseline"

# The negative-control arm is mandatory in every valid experiment (addendum).
NEGATIVE_CONTROL_ARM = ContextArm.LLM_FULL_DESIGN_DOC

# All five §3.3 context arms, in declared order.
ALL_LLM_ARMS: tuple[ContextArm, ...] = tuple(ContextArm)

# Version tag for the tuner prompt template, carried on every ROI row so a
# later re-analysis can bucket rows by the prompt that produced them.
PROMPT_TEMPLATE_VERSION = "so-tuner-v1"

_SEED_UPPER = 2**31


def derive_experiment_seeds(experiment_seed: int, k: int) -> tuple[int, ...]:
    """Derive K distinct master seeds deterministically from one experiment seed.

    ``random.Random(experiment_seed)`` draws distinct positive ints until K
    unique values exist. Deterministic forever, no wall-clock. Varying the
    master seed per trial is what gives the *baseline* arm non-zero variance.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1; got {k}")
    rng = random.Random(experiment_seed)
    seen: set[int] = set()
    drawn: list[int] = []
    while len(drawn) < k:
        value = rng.randrange(1, _SEED_UPPER)
        if value not in seen:
            seen.add(value)
            drawn.append(value)
    return tuple(drawn)


def enforce_negative_control(arms: Sequence[ContextArm]) -> None:
    """Raise unless the negative-control arm (``llm_full_design_doc``) is present.

    Addendum hard requirement: "a run without one is not a valid effectiveness
    experiment." The experiment refuses to run rather than silently produce an
    uninterpretable result.
    """
    if NEGATIVE_CONTROL_ARM not in arms:
        raise ValueError(
            "experiment refuses to run without the negative-control arm "
            f"({NEGATIVE_CONTROL_ARM.value}): a run that excludes it is not a "
            "valid effectiveness experiment (addendum hard requirement). "
            f"Arms requested: {[a.value for a in arms]}"
        )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def factor_subset_hash(context_factor_subset: str) -> str:
    """Stable content hash of the arm's factor subset (ROI-row field)."""
    return _sha256_hex(context_factor_subset)


def context_manifest_hash(*, context_factor_subset: str, archetype: str, provider: str) -> str:
    """Stable content hash of the full context manifest for a run.

    Pins the factor subset + archetype + provider + prompt-template version, so
    two rows with the same manifest hash were produced under identical context
    conditions.
    """
    manifest = f"{context_factor_subset}|{archetype}|{provider}|{PROMPT_TEMPLATE_VERSION}"
    return _sha256_hex(manifest)


def routing_overlay_hash(provider: str) -> str:
    """Stable content hash of the routing overlay in effect (ROI-row field)."""
    return _sha256_hex(f"routing:{provider}")


class ModelSOTunerUsage(BaseModel):
    """Per-run token/cost sidecar, persisted next to the lineage record.

    Mirrors the ``ModelSOPersistedLineageRecord`` precedent: ``recorded_at`` is
    a required, timezone-aware wall-clock field injected by the CLI boundary
    (never defaulted inside the model). The learning loop and the frozen lineage
    schema stay untouched — cost lives on this sidecar, not on the record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    arm: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(ge=0.0)
    recorded_at: datetime  # timezone-aware required; injected by the CLI clock

    @field_validator("recorded_at")
    @classmethod
    def _require_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware (tzinfo required)")
        return v


class ModelSOExperimentRow(BaseModel):
    """One ROI-compatible row per run (``node_context_roi_compute`` schema).

    Carries the addendum's own field list PLUS the seven platform-required
    fields the addendum's summary omits (``failure_stage``, ``endpoint_ref``,
    ``factor_subset_hash``, ``prompt_template_version``, ``routing_overlay_hash``,
    ``temperature``, ``run_order``). Live export into the platform node is out of
    scope — the game emits schema-compatible rows only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- addendum fields ---
    run_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    attempt_count: int = Field(ge=0)  # evaluations consumed
    first_pass_success: bool  # first (single) proposal batch produced a promotion
    final_success: bool  # run ultimately promoted
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(ge=0.0)
    model_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    context_factor_subset: str = Field(min_length=1)  # the arm
    context_manifest_hash: str = Field(min_length=64, max_length=64)

    # --- seven platform-required fields (addendum omits, schema requires) ---
    failure_stage: str | None  # None on success; e.g. "gate_rejected"/"no_candidate"
    endpoint_ref: str = Field(min_length=1)
    factor_subset_hash: str = Field(min_length=64, max_length=64)
    prompt_template_version: str = Field(min_length=1)
    routing_overlay_hash: str = Field(min_length=64, max_length=64)
    temperature: float = Field(ge=0.0)
    run_order: int = Field(ge=0)


class ModelSOArmMetrics(BaseModel):
    """Roll-up of the K trials of a single arm."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    arm: str = Field(min_length=1)
    k_trials: int = Field(ge=1)
    n_promoted: int = Field(ge=0)
    # Per-trial attempts_to_promotion: evaluations_consumed when promoted, else None.
    attempts_to_promotion: tuple[int | None, ...]
    mean_attempts_to_promotion: float | None  # over promoted trials; None if none
    total_cost_usd: float | None = Field(ge=0.0)
    cost_per_promotion: float | None  # total_cost / n_promoted; None if none promoted
    first_batch_promotion_rate: float = Field(ge=0.0, le=1.0)


class ModelSOExperimentSummary(BaseModel):
    """Machine-readable experiment summary (YAML-serialized by the CLI)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: str = "0.1.0"
    kind: str = "steel_onslaught.experiment_summary"
    experiment_seed: int
    archetype: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    k_trials: int = Field(ge=1)
    master_seeds: tuple[int, ...]
    arms: tuple[str, ...]
    baseline_arm: str = BASELINE_ARM
    negative_control_arm: str = NEGATIVE_CONTROL_ARM.value
    arm_metrics: tuple[ModelSOArmMetrics, ...]


def compute_arm_metrics(arm: str, rows: Sequence[ModelSOExperimentRow]) -> ModelSOArmMetrics:
    """Roll a single arm's per-trial ROI rows up into headline metrics.

    Pure: a deterministic function of the rows. ``attempts_to_promotion`` is
    per-trial (``None`` when that trial never promoted); ``cost_per_promotion``
    sums cost across *all* trials and divides by the promotion count (``None``
    when nothing promoted); ``first_batch_promotion_rate`` is the fraction of
    trials whose single proposal batch produced a promotion.
    """
    if not rows:
        raise ValueError(f"arm {arm!r} has no trials to roll up")
    k = len(rows)
    attempts: tuple[int | None, ...] = tuple(
        row.attempt_count if row.final_success else None for row in rows
    )
    promoted_attempts = [row.attempt_count for row in rows if row.final_success]
    n_promoted = len(promoted_attempts)
    mean_attempts = sum(promoted_attempts) / n_promoted if n_promoted else None
    costs = tuple(row.cost_usd for row in rows)
    total_cost = sum(cost for cost in costs if cost is not None) if None not in costs else None
    cost_per_promotion = total_cost / n_promoted if total_cost is not None and n_promoted else None
    first_batch_promotion_rate = sum(1 for row in rows if row.first_pass_success) / k
    return ModelSOArmMetrics(
        arm=arm,
        k_trials=k,
        n_promoted=n_promoted,
        attempts_to_promotion=attempts,
        mean_attempts_to_promotion=mean_attempts,
        total_cost_usd=total_cost,
        cost_per_promotion=cost_per_promotion,
        first_batch_promotion_rate=first_batch_promotion_rate,
    )


def run_id_for(experiment_seed: int, arm: str, trial: int) -> str:
    """Deterministic run id — no ULID/wall-clock, so offline runs are stable."""
    return f"exp{experiment_seed}.{arm}.trial{trial}"


def correlation_id_for(run_id: str) -> str:
    """Deterministic canonical correlation UUID derived from the run id."""
    return str(uuid5(NAMESPACE_URL, f"steel-onslaught:{run_id}"))


__all__ = [
    "ALL_LLM_ARMS",
    "BASELINE_ARM",
    "NEGATIVE_CONTROL_ARM",
    "PROMPT_TEMPLATE_VERSION",
    "ModelSOArmMetrics",
    "ModelSOExperimentRow",
    "ModelSOExperimentSummary",
    "ModelSOTunerUsage",
    "compute_arm_metrics",
    "context_manifest_hash",
    "correlation_id_for",
    "derive_experiment_seeds",
    "enforce_negative_control",
    "factor_subset_hash",
    "routing_overlay_hash",
    "run_id_for",
]
