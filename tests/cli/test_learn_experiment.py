"""Tests for `so learn-experiment` — the LLM-tuner effectiveness harness.

Everything runs offline against the ``StubLlmClient`` provider and a scripted
evaluator (no real duels). Invariants under test (plan §4.5-4.6):

- The command REFUSES to run when the negative-control arm
  (``llm_full_design_doc``) is excluded — a hard requirement.
- The K per-trial master seeds are derived deterministically from one
  ``--experiment-seed`` (same seed => same summary seeds).
- A full run writes ``summary.yaml`` + ``rows.yaml`` + per-run usage sidecars,
  with every ROI-row field and every sidecar field present.
- The comparison table lists all five LLM arms + the deterministic baseline.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from click.testing import CliRunner

from steel_onslaught.cli import learn as learn_module
from steel_onslaught.cli.main import main
from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from steel_onslaught.llm.context_arms import ContextArm
from steel_onslaught.llm.experiment import ModelSOTunerUsage

_PARENT_SPEC = Path("contracts_data/pilots/template_aggressive.yaml")
_BASE_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")

_ROW_FIELDS = {
    "run_id",
    "correlation_id",
    "attempt_count",
    "first_pass_success",
    "final_success",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "model_id",
    "provider",
    "context_factor_subset",
    "context_manifest_hash",
    "failure_stage",
    "endpoint_ref",
    "factor_subset_hash",
    "prompt_template_version",
    "routing_overlay_hash",
    "temperature",
    "run_order",
}


class _ForcedCandidateEvaluator:
    """DuelEvaluator stand-in: the candidate wins every requested seed.

    Robust across trials (different master seeds => different batteries) because
    it is not keyed on specific seeds. A gated candidate therefore always reaches
    the gate and a lineage record (promoted or rejected) is minted — so a usage
    sidecar is written next to it.
    """

    def __init__(
        self,
        *,
        archetype: str,
        base_loadout: Path,
        workdir: Path,
        max_ticks: int,
        contracts_data_dir: Path | None = None,
    ) -> None:
        pass

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        return [
            ModelSOSeedOutcome(
                seed=seed,
                winner=SOSeedWinner.CANDIDATE,
                candidate_overloads=0,
                parent_overloads=0,
            )
            for seed in seeds
        ]


def _experiment_args(tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "--archetype": "aggressive",
        "--parent": str(_PARENT_SPEC),
        "--base-loadout": str(_BASE_LOADOUT),
        "--experiment-seed": "1234",
        "--seeds": "12",
        "--holdout": "12",
        "--budget": "3",
        "--k": "2",
        "--max-ticks": "40",
        "--llm-provider": "stub",
        "--lineage-root": str(tmp_path / "lineage"),
        "--workdir": str(tmp_path / "work"),
        "--output-dir": str(tmp_path / "out"),
    }
    options.update(overrides)
    args = ["learn-experiment"]
    for flag, value in options.items():
        args.extend([flag, value])
    return args


def _invoke(args: list[str]) -> tuple[int, str]:
    result = CliRunner().invoke(main, args)
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    return result.exit_code, result.output


@pytest.mark.unit
class TestNegativeControlRefusal:
    def test_refuses_without_negative_control(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(learn_module, "DuelEvaluator", _ForcedCandidateEvaluator)
        # A single --arm that is NOT the negative control.
        exit_code, output = _invoke(
            [*_experiment_args(tmp_path), "--arm", ContextArm.LLM_OFF.value]
        )
        assert exit_code != 0
        assert "negative-control arm" in output
        # Refused before writing any artifacts.
        assert not (tmp_path / "out" / "summary.yaml").exists()

    def test_runs_when_negative_control_explicitly_included(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(learn_module, "DuelEvaluator", _ForcedCandidateEvaluator)
        exit_code, _ = _invoke(
            [
                *_experiment_args(tmp_path),
                "--arm",
                ContextArm.LLM_OFF.value,
                "--arm",
                ContextArm.LLM_FULL_DESIGN_DOC.value,
            ]
        )
        assert exit_code == 0


@pytest.mark.unit
class TestFullMatrixRun:
    def test_writes_summary_rows_and_sidecars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(learn_module, "DuelEvaluator", _ForcedCandidateEvaluator)
        exit_code, output = _invoke(_experiment_args(tmp_path))
        assert exit_code == 0, output

        # --- summary.yaml: 5 LLM arms + baseline, K=2 ---
        summary_path = tmp_path / "out" / "summary.yaml"
        assert summary_path.exists()
        summary = yaml.safe_load(summary_path.read_text())
        assert summary["k_trials"] == 2
        assert len(summary["master_seeds"]) == 2
        assert len(summary["arm_metrics"]) == 6  # 5 arms + baseline
        arms = set(summary["arms"])
        assert "baseline" in arms
        assert ContextArm.LLM_FULL_DESIGN_DOC.value in arms
        assert summary["negative_control_arm"] == ContextArm.LLM_FULL_DESIGN_DOC.value

        # --- rows.yaml: one row per run, every required field present ---
        rows = yaml.safe_load((tmp_path / "out" / "rows.yaml").read_text())
        assert len(rows) == 12  # 6 arms x 2 trials
        for row in rows:
            assert _ROW_FIELDS.issubset(row.keys()), (
                f"row missing fields: {_ROW_FIELDS - set(row.keys())}"
            )
            assert len(row["context_manifest_hash"]) == 64
            assert len(row["factor_subset_hash"]) == 64
            assert row["prompt_template_version"] == "so-tuner-v1"

        # --- usage sidecar written next to a lineage record, valid + complete ---
        sidecars = list((tmp_path / "lineage").rglob("*.usage.yaml"))
        assert sidecars, "expected at least one usage sidecar next to a lineage record"
        loaded = ModelSOTunerUsage.model_validate(yaml.safe_load(sidecars[0].read_text()))
        assert loaded.recorded_at.tzinfo is not None
        assert loaded.run_id
        assert loaded.model_id

        # --- comparison table lists all arms + headline columns ---
        assert "baseline" in output
        assert ContextArm.LLM_FULL_DESIGN_DOC.value in output
        assert "cost/promotion" in output
        assert "first_batch_rate" in output

    def test_seed_derivation_is_deterministic_across_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(learn_module, "DuelEvaluator", _ForcedCandidateEvaluator)
        run_a = tmp_path / "a"
        run_b = tmp_path / "b"
        code_a, _ = _invoke(_experiment_args(run_a, **{"--experiment-seed": "999"}))
        code_b, _ = _invoke(_experiment_args(run_b, **{"--experiment-seed": "999"}))
        assert code_a == 0 and code_b == 0
        seeds_a = yaml.safe_load((run_a / "out" / "summary.yaml").read_text())["master_seeds"]
        seeds_b = yaml.safe_load((run_b / "out" / "summary.yaml").read_text())["master_seeds"]
        assert seeds_a == seeds_b
