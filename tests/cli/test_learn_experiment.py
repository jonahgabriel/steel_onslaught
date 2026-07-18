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

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from click.testing import CliRunner

from steel_onslaught.cli import learn as learn_module
from steel_onslaught.cli.main import main
from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.learning.artifacts import LearningArtifactStore, LearningContextArtifacts
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from steel_onslaught.llm.context_arms import ContextArm
from steel_onslaught.llm.experiment import ModelSOTunerUsage
from tests.overlay import complete_test_overlay

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
        base_loadout: ModelSOLoadout,
        max_ticks: int,
        duel_executor: object,
        artifacts: LearningArtifactStore,
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


def _write_overlay(tmp_path: Path) -> Path:
    overlay_path = tmp_path / "application.json"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(
        json.dumps(
            complete_test_overlay(
                {
                    "schema_version": "1",
                    "bus": {"kind": "in_process"},
                    "event_ledger": {
                        "kind": "sqlite",
                        "path": tmp_path / "events.sqlite",
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "event_schema": "canonical_event_v1",
                    },
                    "leaderboard": {
                        "kind": "sqlite",
                        "path": tmp_path / "leaderboard.sqlite",
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "storage_schema": "leaderboard_v1",
                    },
                    "learning_artifacts": {
                        "kind": "filesystem_yaml",
                        "evaluation_root": tmp_path / "work",
                        "lineage_root": tmp_path / "lineage",
                    },
                    "evaluation_storage": {
                        "kind": "sqlite",
                        "root": tmp_path / "work",
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "event_schema": "canonical_event_v1",
                        "leaderboard_schema": "leaderboard_v1",
                    },
                    "contracts": {
                        "catalog_dir": Path("contracts_data").resolve(),
                        "pilot_registry_dir": Path("contracts_data/pilots").resolve(),
                    },
                    "clock": {"kind": "system_utc"},
                    "identity": {"kind": "system"},
                },
                tmp_path,
            ),
            default=str,
        ),
        encoding="utf-8",
    )
    return overlay_path


def _experiment_args(tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "--overlay": str(_write_overlay(tmp_path)),
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
        "--design-doc": str(Path("docs/plans/2026-04-30-steel-onslaught-design.md").resolve()),
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
        assert not list((tmp_path / "experiments").glob("summaries/*.yaml"))

    def test_runs_when_negative_control_explicitly_included(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(learn_module, "DuelEvaluator", _ForcedCandidateEvaluator)
        monkeypatch.setattr(
            "steel_onslaught.learning.filesystem_artifacts.YamlFilesystemLearningArtifactStore.read_context_artifacts",
            lambda _store, *, archetype, limit=5: LearningContextArtifacts(
                replay_traces=(f"trace:{archetype}",),
                decision_diffs=(f"diff:{archetype}",),
                exemplars=(f"exemplar:{archetype}",),
            ),
        )
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
        monkeypatch.setattr(
            "steel_onslaught.learning.filesystem_artifacts.YamlFilesystemLearningArtifactStore.read_context_artifacts",
            lambda _store, *, archetype, limit=5: LearningContextArtifacts(
                replay_traces=(f"trace:{archetype}",),
                decision_diffs=(f"diff:{archetype}",),
                exemplars=(f"exemplar:{archetype}",),
            ),
        )
        exit_code, output = _invoke(_experiment_args(tmp_path))
        assert exit_code == 0, output

        # --- summary.yaml: 5 LLM arms + baseline, K=2 ---
        summary_path = next((tmp_path / "experiments").glob("summaries/*.yaml"))
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
        rows_path = next((tmp_path / "experiments").glob("rows/*.yaml"))
        rows = yaml.safe_load(rows_path.read_text())
        assert len(rows) == 12  # 6 arms x 2 trials
        for row in rows:
            assert _ROW_FIELDS.issubset(row.keys()), (
                f"row missing fields: {_ROW_FIELDS - set(row.keys())}"
            )
            assert len(row["context_manifest_hash"]) == 64
            assert len(row["factor_subset_hash"]) == 64
            assert row["prompt_template_version"] == "so-tuner-v1"
        llm_manifest_by_arm = {
            arm: {
                row["context_manifest_hash"] for row in rows if row["context_factor_subset"] == arm
            }
            for arm in (context.value for context in ContextArm)
        }
        assert all(len(hashes) == 1 for hashes in llm_manifest_by_arm.values())
        assert len({next(iter(hashes)) for hashes in llm_manifest_by_arm.values()}) == len(
            llm_manifest_by_arm
        )

        # --- usage sidecar written next to a lineage record, valid + complete ---
        sidecars = list((tmp_path / "lineage").rglob("*.usage.yaml"))
        assert sidecars, "expected at least one usage sidecar next to a lineage record"
        loaded = ModelSOTunerUsage.model_validate(yaml.safe_load(sidecars[0].read_text()))
        assert loaded.recorded_at.tzinfo is not None
        assert loaded.run_id
        assert loaded.model_id
        matching_row = next(row for row in rows if row["run_id"] == loaded.run_id)
        assert loaded.context_manifest_hash == matching_row["context_manifest_hash"]

        # --- comparison table lists all arms + headline columns ---
        assert "baseline" in output
        assert ContextArm.LLM_FULL_DESIGN_DOC.value in output
        assert "cost/promotion" in output
        assert "first_batch_rate" in output

    def test_seed_derivation_is_deterministic_across_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(learn_module, "DuelEvaluator", _ForcedCandidateEvaluator)
        monkeypatch.setattr(
            "steel_onslaught.learning.filesystem_artifacts.YamlFilesystemLearningArtifactStore.read_context_artifacts",
            lambda _store, *, archetype, limit=5: LearningContextArtifacts(
                replay_traces=(f"trace:{archetype}",),
                decision_diffs=(f"diff:{archetype}",),
                exemplars=(f"exemplar:{archetype}",),
            ),
        )
        run_a = tmp_path / "a"
        run_b = tmp_path / "b"
        code_a, _ = _invoke(_experiment_args(run_a, **{"--experiment-seed": "999"}))
        code_b, _ = _invoke(_experiment_args(run_b, **{"--experiment-seed": "999"}))
        assert code_a == 0 and code_b == 0
        summary_a = next((run_a / "experiments").glob("summaries/*.yaml"))
        summary_b = next((run_b / "experiments").glob("summaries/*.yaml"))
        seeds_a = yaml.safe_load(summary_a.read_text())["master_seeds"]
        seeds_b = yaml.safe_load(summary_b.read_text())["master_seeds"]
        assert seeds_a == seeds_b
