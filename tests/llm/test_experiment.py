"""Pure-logic tests for the LLM-tuner experiment harness (plan §4.5-4.6).

Covers the effect-free half of ``so learn-experiment``: negative-control
enforcement, deterministic K-seed derivation, the per-arm metric roll-up, and
the timezone-aware ``recorded_at`` discipline on the usage sidecar.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from steel_onslaught.llm.context_arms import ContextArm
from steel_onslaught.llm.experiment import (
    NEGATIVE_CONTROL_ARM,
    PROMPT_TEMPLATE_VERSION,
    ModelSOExperimentRow,
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


def _row(
    *,
    arm: str = "llm_off",
    final_success: bool,
    attempt_count: int,
    cost_usd: float,
    first_pass_success: bool | None = None,
    run_order: int = 0,
) -> ModelSOExperimentRow:
    promoted = final_success if first_pass_success is None else first_pass_success
    return ModelSOExperimentRow(
        run_id=run_id_for(1, arm, run_order),
        correlation_id=correlation_id_for(run_id_for(1, arm, run_order)),
        attempt_count=attempt_count,
        first_pass_success=promoted,
        final_success=final_success,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=cost_usd,
        model_id="stub",
        provider="stub",
        context_factor_subset=arm,
        context_manifest_hash=context_manifest_hash(
            context_factor_subset=arm, archetype="aggressive", provider="stub"
        ),
        failure_stage=None if final_success else "gate_rejected",
        endpoint_ref="stub",
        factor_subset_hash=factor_subset_hash(arm),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        routing_overlay_hash=routing_overlay_hash("stub"),
        temperature=0.0,
        run_order=run_order,
    )


@pytest.mark.unit
class TestNegativeControlEnforcement:
    def test_refuses_when_negative_control_excluded(self) -> None:
        arms = [ContextArm.LLM_OFF, ContextArm.LLM_EXEMPLAR]
        with pytest.raises(ValueError, match="negative-control arm"):
            enforce_negative_control(arms)

    def test_accepts_when_negative_control_present(self) -> None:
        arms = [ContextArm.LLM_OFF, NEGATIVE_CONTROL_ARM]
        enforce_negative_control(arms)  # no raise

    def test_negative_control_is_full_design_doc(self) -> None:
        assert NEGATIVE_CONTROL_ARM is ContextArm.LLM_FULL_DESIGN_DOC


@pytest.mark.unit
class TestSeedDerivation:
    def test_deterministic_same_seed_same_seeds(self) -> None:
        a = derive_experiment_seeds(42, 5)
        b = derive_experiment_seeds(42, 5)
        assert a == b

    def test_length_matches_k_and_distinct(self) -> None:
        seeds = derive_experiment_seeds(7, 5)
        assert len(seeds) == 5
        assert len(set(seeds)) == 5  # distinct — baseline variance requires it

    def test_different_experiment_seed_diverges(self) -> None:
        assert derive_experiment_seeds(1, 5) != derive_experiment_seeds(2, 5)

    def test_k_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="k must be"):
            derive_experiment_seeds(1, 0)


@pytest.mark.unit
class TestArmMetrics:
    def test_metrics_from_scripted_outcomes(self) -> None:
        # 5 trials: 2 promoted (attempts 3 and 5), 3 not promoted.
        rows = [
            _row(final_success=True, attempt_count=3, cost_usd=0.10, run_order=0),
            _row(final_success=False, attempt_count=6, cost_usd=0.20, run_order=1),
            _row(final_success=True, attempt_count=5, cost_usd=0.30, run_order=2),
            _row(final_success=False, attempt_count=6, cost_usd=0.40, run_order=3),
            _row(final_success=False, attempt_count=6, cost_usd=0.50, run_order=4),
        ]
        m = compute_arm_metrics("llm_off", rows)
        assert m.k_trials == 5
        assert m.n_promoted == 2
        # attempts_to_promotion: per-trial, None when not promoted.
        assert m.attempts_to_promotion == (3, None, 5, None, None)
        assert m.mean_attempts_to_promotion == pytest.approx(4.0)
        # cost_per_promotion: sum of ALL trials' cost / promotions.
        assert m.total_cost_usd == pytest.approx(1.5)
        assert m.cost_per_promotion == pytest.approx(1.5 / 2)
        assert m.first_batch_promotion_rate == pytest.approx(2 / 5)

    def test_no_promotion_gives_none_metrics(self) -> None:
        rows = [
            _row(final_success=False, attempt_count=6, cost_usd=0.1, run_order=0),
            _row(final_success=False, attempt_count=6, cost_usd=0.1, run_order=1),
        ]
        m = compute_arm_metrics("llm_off", rows)
        assert m.n_promoted == 0
        assert m.attempts_to_promotion == (None, None)
        assert m.mean_attempts_to_promotion is None
        assert m.cost_per_promotion is None
        assert m.first_batch_promotion_rate == pytest.approx(0.0)

    def test_baseline_zero_cost_but_promoted(self) -> None:
        rows = [
            _row(arm="baseline", final_success=True, attempt_count=4, cost_usd=0.0, run_order=0),
        ]
        m = compute_arm_metrics("baseline", rows)
        assert m.total_cost_usd == pytest.approx(0.0)
        assert m.cost_per_promotion == pytest.approx(0.0)  # compute-only baseline
        assert m.first_batch_promotion_rate == pytest.approx(1.0)

    def test_empty_rows_raises(self) -> None:
        with pytest.raises(ValueError, match="no trials"):
            compute_arm_metrics("llm_off", [])


@pytest.mark.unit
class TestUsageSidecarModel:
    def test_requires_timezone_aware_recorded_at(self) -> None:
        with pytest.raises(ValidationError):
            ModelSOTunerUsage(
                run_id="r",
                correlation_id="c",
                arm="llm_off",
                provider="stub",
                model_id="stub",
                prompt_tokens=1,
                completion_tokens=1,
                cost_usd=0.0,
                recorded_at=datetime(2026, 7, 2),  # naive — rejected
            )

    def test_accepts_aware_recorded_at(self) -> None:
        usage = ModelSOTunerUsage(
            run_id="r",
            correlation_id="c",
            arm="llm_off",
            provider="stub",
            model_id="stub",
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
            recorded_at=datetime.now(UTC),
        )
        assert usage.recorded_at.tzinfo is not None
