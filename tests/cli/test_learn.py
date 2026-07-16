"""Tests for `so learn` — Phase 2 Task 5 invariants.

Invariants under test (plan Task 5):

- ``--seeds 0``, ``--holdout 0``, ``--budget 1``, unknown ``--strategy``, and a
  ``--parent`` whose archetype != ``--archetype`` each exit non-zero.
- A completed rejected run exits 0 and prints every rejection reason; the
  summary line always carries p-value, effect size, CI, and decisive n
  (never a bare "better" — addendum §4.3 no-overclaim).
- The record path printed exists and loads via ``load_lineage_records``; its
  evidence seed batteries equal the result's batteries.
- ``recorded_at`` in the persisted envelope is timezone-aware UTC.
- Source-scan: ``cli/learn.py`` is the only wall-clock boundary across
  ``learning/`` + ``cli/learn.py`` (single ``datetime.now`` match, Decision #4).
- Smoke e2e: a real hill-climb run against a shipped loadout completes with
  exit 0 and writes either nothing or a loadable record (outcome-agnostic).

Unit tests stub the DuelEvaluator (scripted outcomes, no real duels); the one
real-duel test is ``integration + slow``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from steel_onslaught.cli import learn as learn_module
from steel_onslaught.cli.main import main
from steel_onslaught.contracts.lineage import ParamDict, SOPromotionStatus
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.lineage_store import load_lineage_records
from steel_onslaught.learning.loop import derive_seed_batteries
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from tests.overlay import complete_test_overlay

_PARENT_SPEC = Path("contracts_data/pilots/template_aggressive.yaml")
_BASE_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_MASTER_SEED = 7
_STATS_TOKENS = ("p-value=", "effect=", "ci=[", "decisive-n=")


def _outcome(seed: int, winner: SOSeedWinner) -> ModelSOSeedOutcome:
    return ModelSOSeedOutcome(seed=seed, winner=winner, candidate_overloads=0, parent_overloads=0)


def _stub_evaluator_class(script: dict[int, ModelSOSeedOutcome]) -> type[object]:
    """A DuelEvaluator stand-in: same constructor keywords, scripted outcomes.

    Unscripted seeds raise KeyError — so a test that scripts only the search
    battery also proves the CLI path never consumes the holdout battery when
    no candidate reaches the gate.
    """

    class _StubDuelEvaluator:
        def __init__(
            self,
            *,
            archetype: str,
            base_loadout: ModelSOLoadout,
            max_ticks: int,
            duel_executor: object,
            artifacts: LearningArtifactStore,
        ) -> None:
            self._script = script

        def evaluate(
            self,
            candidate_params: ParamDict,
            parent_params: ParamDict,
            seeds: Sequence[int],
        ) -> list[ModelSOSeedOutcome]:
            return [self._script[seed] for seed in seeds]

    return _StubDuelEvaluator


def _write_overlay(tmp_path: Path) -> Path:
    overlay_path = tmp_path / "application.json"
    overlay_path.write_text(
        json.dumps(
            complete_test_overlay(
                {
                    "schema_version": "1",
                    "bus": {"kind": "in_process"},
                    "event_ledger": {
                        "kind": "sqlite",
                        "path": str(tmp_path / "global-events.sqlite"),
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "event_schema": "canonical_event_v1",
                    },
                    "leaderboard": {
                        "kind": "sqlite",
                        "path": str(tmp_path / "global-leaderboard.sqlite"),
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "storage_schema": "leaderboard_v1",
                    },
                    "learning_artifacts": {
                        "kind": "filesystem_yaml",
                        "evaluation_root": str(tmp_path / "work"),
                        "lineage_root": str(tmp_path / "lineage"),
                    },
                    "evaluation_storage": {
                        "kind": "sqlite",
                        "root": str(tmp_path / "work"),
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "event_schema": "canonical_event_v1",
                        "leaderboard_schema": "leaderboard_v1",
                    },
                    "contracts": {
                        "catalog_dir": str(Path("contracts_data").resolve()),
                        "pilot_registry_dir": str(Path("contracts_data/pilots").resolve()),
                    },
                    "clock": {"kind": "system_utc"},
                    "identity": {"kind": "system"},
                },
                tmp_path,
            )
        ),
        encoding="utf-8",
    )
    return overlay_path


def _learn_args(tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "--overlay": str(_write_overlay(tmp_path)),
        "--archetype": "aggressive",
        "--parent": str(_PARENT_SPEC),
        "--strategy": "grid",
        "--seeds": "2",
        "--holdout": "2",
        "--budget": "3",
        "--master-seed": str(_MASTER_SEED),
        "--base-loadout": str(_BASE_LOADOUT),
        "--max-ticks": "80",
    }
    options.update(overrides)
    args = ["learn"]
    for flag, value in options.items():
        args.extend([flag, value])
    return args


def _invoke(args: list[str]) -> tuple[int, str]:
    result = CliRunner().invoke(main, args)
    return result.exit_code, result.output


def _scripted_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    search_winner: SOSeedWinner,
    script_holdout: bool,
) -> tuple[int, str]:
    """Run `so learn` with a stubbed evaluator scripting every battery seed."""
    search_seeds, holdout_seeds = derive_seed_batteries(_MASTER_SEED, 2, 2)
    script = {seed: _outcome(seed, search_winner) for seed in search_seeds}
    if script_holdout:
        script.update({seed: _outcome(seed, search_winner) for seed in holdout_seeds})
    monkeypatch.setattr(learn_module, "DuelEvaluator", _stub_evaluator_class(script))
    return _invoke(_learn_args(tmp_path))


def _printed_record_path(output: str) -> str:
    match = re.search(r"^record: (.+)$", output, flags=re.MULTILINE)
    assert match is not None, f"no record line in output:\n{output}"
    return match.group(1)


# ---------------------------------------------------------------------------
# Flag and harness errors exit non-zero (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearnFlagErrors:
    @pytest.mark.parametrize(
        ("flag", "value"),
        [
            ("--seeds", "0"),
            ("--holdout", "0"),
            ("--budget", "1"),
            ("--strategy", "simulated_annealing"),
        ],
    )
    def test_invalid_flag_exits_nonzero(self, tmp_path: Path, flag: str, value: str) -> None:
        exit_code, _ = _invoke(_learn_args(tmp_path, **{flag: value}))
        assert exit_code != 0

    def test_archetype_mismatch_exits_nonzero(self, tmp_path: Path) -> None:
        """An aggressive parent spec under --archetype defensive is a harness error."""
        exit_code, output = _invoke(_learn_args(tmp_path, **{"--archetype": "defensive"}))
        assert exit_code != 0
        assert "archetype" in output

    def test_missing_parent_exits_nonzero(self, tmp_path: Path) -> None:
        exit_code, _ = _invoke(
            _learn_args(tmp_path, **{"--parent": str(tmp_path / "missing.yaml")})
        )
        assert exit_code != 0


# ---------------------------------------------------------------------------
# Completed runs exit 0 — promoted, rejected, AND no-candidate (unit, stubbed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearnCompletedRuns:
    def test_rejected_run_exits_zero_and_prints_every_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All-candidate-wins on a 2-seed battery cannot clear the gate
        (n < 10 is exploratory) — the run completes, exit 0, reasons printed."""
        exit_code, output = _scripted_run(
            tmp_path, monkeypatch, search_winner=SOSeedWinner.CANDIDATE, script_holdout=True
        )
        assert exit_code == 0
        assert "verdict: rejected" in output

        records = load_lineage_records(tmp_path / "lineage")
        assert len(records) == 1
        record = records[0].record
        assert record.promotion.status is SOPromotionStatus.REJECTED
        assert record.promotion.rejection_reasons, "rejected record must carry reasons"
        for reason in record.promotion.rejection_reasons:
            assert reason.value in output, f"rejection reason {reason.value} not printed"

    def test_summary_always_carries_stats_tokens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No-overclaim (§4.3): p-value, effect size, CI, decisive n — never
        a bare 'better'."""
        _, output = _scripted_run(
            tmp_path, monkeypatch, search_winner=SOSeedWinner.CANDIDATE, script_holdout=True
        )
        for token in _STATS_TOKENS:
            assert token in output, f"summary missing {token!r}:\n{output}"

    def test_no_candidate_run_exits_zero_without_holdout_consumption(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All-parent-wins: no direction-positive candidate, no gate call, no
        record — and exit 0 (absence of a candidate is not an error). The
        holdout battery is deliberately UNSCRIPTED: any holdout consumption
        would raise KeyError and fail the run."""
        exit_code, output = _scripted_run(
            tmp_path, monkeypatch, search_winner=SOSeedWinner.PARENT, script_holdout=False
        )
        assert exit_code == 0
        assert "verdict: no-candidate" in output
        assert "record: none" in output
        for token in _STATS_TOKENS:
            assert token in output, f"summary missing {token!r}:\n{output}"
        assert not (tmp_path / "lineage").exists() or not list(
            (tmp_path / "lineage").rglob("*.yaml")
        )

    @pytest.mark.parametrize("preexisting", [False, True])
    def test_learning_never_opens_global_runtime_stores(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        preexisting: bool,
    ) -> None:
        case_root = tmp_path / ("sentinel" if preexisting else "missing")
        case_root.mkdir()
        event_store = case_root / "global-events.sqlite"
        leaderboard_store = case_root / "global-leaderboard.sqlite"
        sentinel = b"not-a-sqlite-runtime-store"
        if preexisting:
            event_store.write_bytes(sentinel)
            leaderboard_store.write_bytes(sentinel)

        exit_code, output = _scripted_run(
            case_root,
            monkeypatch,
            search_winner=SOSeedWinner.PARENT,
            script_holdout=False,
        )

        assert exit_code == 0, output
        if preexisting:
            assert event_store.read_bytes() == sentinel
            assert leaderboard_store.read_bytes() == sentinel
        else:
            assert not event_store.exists()
            assert not leaderboard_store.exists()


# ---------------------------------------------------------------------------
# Persisted record: path printed, loadable, batteries match, recorded_at UTC
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLearnPersistedRecord:
    def test_record_path_exists_and_loads_with_matching_batteries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, output = _scripted_run(
            tmp_path, monkeypatch, search_winner=SOSeedWinner.CANDIDATE, script_holdout=True
        )
        record_path = Path(_printed_record_path(output))
        assert record_path.exists()

        records = load_lineage_records(tmp_path / "lineage")
        assert len(records) == 1
        evidence = records[0].record.evidence
        search_seeds, holdout_seeds = derive_seed_batteries(_MASTER_SEED, 2, 2)
        assert evidence.search_seeds == search_seeds
        assert evidence.holdout_seeds == holdout_seeds

    def test_recorded_at_is_timezone_aware_utc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _scripted_run(
            tmp_path, monkeypatch, search_winner=SOSeedWinner.CANDIDATE, script_holdout=True
        )
        records = load_lineage_records(tmp_path / "lineage")
        recorded_at = records[0].recorded_at
        assert recorded_at.tzinfo is not None
        assert recorded_at.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# Source-scan: injected wall-clock boundary (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInjectedWallClockBoundary:
    def test_learning_and_cli_do_not_construct_wall_clock(self) -> None:
        """Decision #4: composition injects the clock into the CLI boundary."""
        learning_dir = Path("src/steel_onslaught/learning")
        for module_path in sorted(learning_dir.glob("*.py")):
            source = module_path.read_text(encoding="utf-8")
            assert "datetime.now" not in source, f"{module_path} must not read the wall clock"
        learn_source = Path("src/steel_onslaught/cli/learn.py").read_text(encoding="utf-8")
        assert "datetime.now" not in learn_source
        assert "recorded_at=dependencies.clock.now()" in learn_source


# ---------------------------------------------------------------------------
# Smoke e2e on real duels (integration, slow)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
class TestLearnSmokeE2E:
    def test_hill_climb_smoke_run_completes(self, tmp_path: Path) -> None:
        """Outcome-agnostic, mechanics-asserting: a tiny real hill-climb run
        exits 0 and writes either nothing (no candidate) or a loadable record."""
        exit_code, output = _invoke(
            _learn_args(
                tmp_path,
                **{"--strategy": "hill_climb", "--budget": "4", "--max-ticks": "80"},
            )
        )
        assert exit_code == 0, output
        for token in _STATS_TOKENS:
            assert token in output, f"summary missing {token!r}:\n{output}"

        lineage_root = tmp_path / "lineage"
        record_line = _printed_record_path(output)
        records = load_lineage_records(lineage_root)
        if record_line == "none":
            assert records == []
        else:
            assert Path(record_line).exists()
            assert len(records) == 1
        # Evaluation scratch stays inside the overlay-selected artifact root (Decision #6).
        assert (tmp_path / "work").exists()
        assert not (tmp_path / "global-events.sqlite").exists()
        assert not (tmp_path / "global-leaderboard.sqlite").exists()
