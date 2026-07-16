"""Tests for `so balance` — tunable-pilots Task 6 invariants.

Invariants under test (plan Task 6):

- Matrix shape: for L loadouts x 3 template pilots = C combatant configs, the
  matrix has exactly C*(C-1)/2 pairing rows, and ``wins_a + wins_b + draws == N``
  for every row.
- Determinism: two runs with ``--seeds 3`` produce byte-identical CSV output.
- The CLI never writes to any match ledger directory implicitly (matches run
  against temp ledgers).
- ``--seeds 0`` exits non-zero with a usage error.

Tests use ``--seeds 2`` and a reduced loadout fixture set (the shipped example
loadouts copied into a temp dir), marked ``slow``.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from steel_onslaught.cli.main import main
from steel_onslaught.projections.balance.matrix import (
    ModelSOBalanceMatrix,
    ModelSOBalancePairing,
)
from tests.overlay import complete_test_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_LOADOUTS = _REPO_ROOT / "contracts_data/loadouts"
_REDUCED_LOADOUT_FILES = (
    "example_aggressive_light.yaml",
    "example_predictive_heavy.yaml",
)
_TEMPLATE_PILOT_COUNT = 3


@pytest.fixture()
def reduced_loadouts_dir(tmp_path: Path) -> Path:
    """A reduced fixture set: 2 shipped non-proof loadouts in their own dir."""
    fixture_dir = tmp_path / "loadouts"
    fixture_dir.mkdir()
    for name in _REDUCED_LOADOUT_FILES:
        shutil.copy(_REPO_LOADOUTS / name, fixture_dir / name)
    return fixture_dir


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_overlay(tmp_path: Path, *, name: str) -> tuple[Path, Path, Path, Path]:
    event_store = tmp_path / f"{name}-global-events.sqlite"
    leaderboard_store = tmp_path / f"{name}-global-leaderboard.sqlite"
    evaluation_root = tmp_path / f"{name}-evaluation"
    overlay_path = tmp_path / f"{name}-application.json"
    overlay_path.write_text(
        json.dumps(
            complete_test_overlay(
                {
                    "schema_version": "1",
                    "bus": {"kind": "in_process"},
                    "event_ledger": {
                        "kind": "sqlite",
                        "path": str(event_store),
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "event_schema": "canonical_event_v1",
                    },
                    "leaderboard": {
                        "kind": "sqlite",
                        "path": str(leaderboard_store),
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "storage_schema": "leaderboard_v1",
                    },
                    "learning_artifacts": {
                        "kind": "filesystem_yaml",
                        "evaluation_root": str(tmp_path / f"{name}-artifacts"),
                        "lineage_root": str(tmp_path / f"{name}-lineage"),
                    },
                    "evaluation_storage": {
                        "kind": "sqlite",
                        "root": str(evaluation_root),
                        "journal_mode": "WAL",
                        "check_same_thread": False,
                        "transaction_mode": "autocommit",
                        "event_schema": "canonical_event_v1",
                        "leaderboard_schema": "leaderboard_v1",
                    },
                    "contracts": {
                        "catalog_dir": str(_REPO_ROOT / "contracts_data"),
                        "pilot_registry_dir": str(_REPO_ROOT / "contracts_data/pilots"),
                    },
                    "clock": {"kind": "system_utc"},
                    "identity": {"kind": "system"},
                },
                tmp_path,
            )
        ),
        encoding="utf-8",
    )
    return overlay_path, event_store, leaderboard_store, evaluation_root


# ---------------------------------------------------------------------------
# Model invariants (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pairing_must_account_for_every_seed() -> None:
    """wins_a + wins_b + draws must equal the seed count for every pairing."""
    good = ModelSOBalancePairing(config_a="cfg.a", config_b="cfg.b", wins_a=1, wins_b=0, draws=1)
    ModelSOBalanceMatrix(seeds=2, pairings=(good,))  # sums to 2: accepted

    short = ModelSOBalancePairing(config_a="cfg.a", config_b="cfg.b", wins_a=1, wins_b=0, draws=0)
    with pytest.raises(ValidationError, match="wins_a \\+ wins_b \\+ draws"):
        ModelSOBalanceMatrix(seeds=2, pairings=(short,))


@pytest.mark.unit
def test_matrix_requires_at_least_one_pairing() -> None:
    with pytest.raises(ValidationError):
        ModelSOBalanceMatrix(seeds=1, pairings=())


@pytest.mark.unit
def test_draw_rate_is_total_draws_over_total_matches() -> None:
    matrix = ModelSOBalanceMatrix(
        seeds=2,
        pairings=(
            ModelSOBalancePairing(config_a="cfg.a", config_b="cfg.b", wins_a=2, wins_b=0, draws=0),
            ModelSOBalancePairing(config_a="cfg.a", config_b="cfg.c", wins_a=0, wins_b=1, draws=1),
        ),
    )
    assert matrix.total_matches == 4
    assert matrix.total_draws == 1
    assert matrix.draw_rate == 0.25


# ---------------------------------------------------------------------------
# CLI usage errors (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_seeds_zero_is_a_usage_error() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["balance", "--seeds", "0"])
    assert result.exit_code != 0
    assert "--seeds" in result.output


@pytest.mark.unit
def test_seeds_is_required() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["balance"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Round-robin matrix (integration, slow)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
def test_matrix_shape_row_sums_and_no_implicit_ledger_writes(
    reduced_loadouts_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C=L*3 configs -> C*(C-1)/2 rows, each accounting for all N seeds.

    Run from an empty working directory: the only file the command may create
    is the explicitly requested ``--csv`` target — no ledger files, no ledger
    directories (matches run against temp ledgers).
    """
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    seeds = 2
    csv_path = workdir / "out.csv"
    overlay_path, event_store, leaderboard_store, evaluation_root = _write_overlay(
        tmp_path, name="matrix"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "balance",
            "--overlay",
            str(overlay_path),
            "--seeds",
            str(seeds),
            "--loadouts-dir",
            str(reduced_loadouts_dir),
            "--csv",
            str(csv_path),
            "--max-ticks",
            "80",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    config_count = len(_REDUCED_LOADOUT_FILES) * _TEMPLATE_PILOT_COUNT
    expected_rows = config_count * (config_count - 1) // 2

    rows = _read_csv_rows(csv_path)
    assert len(rows) == expected_rows
    for row in rows:
        assert int(row["wins_a"]) + int(row["wins_b"]) + int(row["draws"]) == seeds

    # Every config appears in at least one pairing, and pairings are unordered
    # (no row is repeated with the sides flipped).
    pairs = {(row["config_a"], row["config_b"]) for row in rows}
    assert len(pairs) == expected_rows
    assert not any((b, a) in pairs for a, b in pairs)

    # Overall draw rate is reported on stdout.
    assert "draw rate" in result.output

    # No implicit writes: the working directory holds ONLY the requested CSV.
    assert {p.name for p in workdir.iterdir()} == {"out.csv"}
    assert not event_store.exists()
    assert not leaderboard_store.exists()
    assert list(evaluation_root.rglob("*.sqlite3"))


@pytest.mark.integration
@pytest.mark.slow
def test_two_runs_with_seeds_3_produce_byte_identical_csv(
    reduced_loadouts_dir: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    outputs: list[bytes] = []
    overlay_path, event_store, leaderboard_store, evaluation_root = _write_overlay(
        tmp_path, name="determinism"
    )
    for run_index in (1, 2):
        csv_path = tmp_path / f"matrix_{run_index}.csv"
        result = runner.invoke(
            main,
            [
                "balance",
                "--overlay",
                str(overlay_path),
                "--seeds",
                "3",
                "--loadouts-dir",
                str(reduced_loadouts_dir),
                "--csv",
                str(csv_path),
                "--max-ticks",
                "80",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert not event_store.exists()
        assert not leaderboard_store.exists()
        outputs.append(csv_path.read_bytes())

    assert outputs[0] == outputs[1]
    assert outputs[0] != b""
    assert {path.name for path in evaluation_root.iterdir()} == {"balance", "balance_0002"}


@pytest.mark.integration
@pytest.mark.slow
def test_proof_loadouts_are_excluded(tmp_path: Path) -> None:
    """A loadouts dir holding only proof_* files yields a usage failure, not a run."""
    fixture_dir = tmp_path / "loadouts"
    fixture_dir.mkdir()
    shutil.copy(
        _REPO_LOADOUTS / "proof_blue_aggressive_hunter.yaml",
        fixture_dir / "proof_blue_aggressive_hunter.yaml",
    )

    runner = CliRunner()
    overlay_path, _, _, _ = _write_overlay(tmp_path, name="proof-only")
    result = runner.invoke(
        main,
        [
            "balance",
            "--overlay",
            str(overlay_path),
            "--seeds",
            "1",
            "--loadouts-dir",
            str(fixture_dir),
        ],
    )
    assert result.exit_code != 0
    assert "no non-proof loadouts" in result.output
