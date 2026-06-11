"""Tests for the `so` CLI — Task 28 invariants.

The critical invariant: running the same `so run` twice with the same seed
produces byte-identical stdout.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from steel_onslaught.cli.main import main

LOADOUT_A = "contracts_data/loadouts/example_aggressive_light.yaml"
LOADOUT_B = "contracts_data/loadouts/example_predictive_heavy.yaml"


def _run_args(
    *, seed: int = 12345, max_ticks: int = 10, extra: list[str] | None = None
) -> list[str]:
    args = [
        "run",
        "--loadout-a",
        LOADOUT_A,
        "--loadout-b",
        LOADOUT_B,
        "--seed",
        str(seed),
        "--max-ticks",
        str(max_ticks),
    ]
    return args + (extra or [])


def _extract_match_id(stderr: str) -> str:
    match = re.search(r"^match_id: (\S+)$", stderr, flags=re.MULTILINE)
    assert match is not None, f"match_id line missing from stderr: {stderr!r}"
    return match.group(1)


# ---------------------------------------------------------------------------
# so run
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_run_same_seed_byte_identical_stdout() -> None:
    runner = CliRunner()
    one = runner.invoke(main, _run_args(), catch_exceptions=False)
    two = runner.invoke(main, _run_args(), catch_exceptions=False)
    assert one.exit_code == 0
    assert two.exit_code == 0
    assert one.stdout != ""
    assert one.stdout == two.stdout


@pytest.mark.integration
def test_run_renders_match_started_and_ended() -> None:
    runner = CliRunner()
    result = runner.invoke(main, _run_args(seed=99, max_ticks=5), catch_exceptions=False)
    assert result.exit_code == 0
    assert "[Tick 0] MATCH STARTED (seed 99, max_ticks 5)" in result.stdout
    assert "MATCH ENDED (draw max ticks)" in result.stdout


@pytest.mark.integration
def test_run_emits_match_id_on_stderr_not_stdout() -> None:
    runner = CliRunner()
    result = runner.invoke(main, _run_args(max_ticks=3), catch_exceptions=False)
    assert result.exit_code == 0
    match_id = _extract_match_id(result.stderr)
    assert match_id.startswith("match.")
    assert match_id not in result.stdout


# ---------------------------------------------------------------------------
# so replay
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_replay_reproduces_run_stdout(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    runner = CliRunner()
    live = runner.invoke(
        main,
        _run_args(extra=["--ledger-path", str(ledger)]),
        catch_exceptions=False,
    )
    assert live.exit_code == 0
    match_id = _extract_match_id(live.stderr)

    replayed = runner.invoke(
        main,
        ["replay", "--ledger", str(ledger), "--match", match_id],
        catch_exceptions=False,
    )
    assert replayed.exit_code == 0
    assert replayed.stdout == live.stdout


@pytest.mark.integration
def test_replay_tick_window_filters_lines(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    runner = CliRunner()
    live = runner.invoke(
        main,
        _run_args(extra=["--ledger-path", str(ledger)]),
        catch_exceptions=False,
    )
    match_id = _extract_match_id(live.stderr)

    replayed = runner.invoke(
        main,
        [
            "replay",
            "--ledger",
            str(ledger),
            "--match",
            match_id,
            "--from",
            "3",
            "--to",
            "5",
        ],
        catch_exceptions=False,
    )
    assert replayed.exit_code == 0
    lines = replayed.stdout.splitlines()
    assert lines, "tick window 3-5 should render at least one line"
    for line in lines:
        tick_match = re.match(r"^\[Tick (\d+)\]", line)
        assert tick_match is not None, f"unexpected line format: {line!r}"
        assert 3 <= int(tick_match.group(1)) <= 5


@pytest.mark.integration
def test_replay_unknown_match_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    runner = CliRunner()
    runner.invoke(
        main,
        _run_args(max_ticks=3, extra=["--ledger-path", str(ledger)]),
        catch_exceptions=False,
    )
    result = runner.invoke(
        main,
        ["replay", "--ledger", str(ledger), "--match", "match.does-not-exist"],
    )
    assert result.exit_code != 0
    assert "no events" in result.stderr


# ---------------------------------------------------------------------------
# so leaderboard
# ---------------------------------------------------------------------------

_LEADERBOARD_DDL = """
CREATE TABLE IF NOT EXISTS leaderboard_entries (
    match_id          TEXT PRIMARY KEY,
    winner_player_id  TEXT NOT NULL,
    winner_loadout_id TEXT NOT NULL,
    winner_score      INTEGER NOT NULL,
    loser_player_id   TEXT NOT NULL,
    loser_score       INTEGER NOT NULL,
    duration_ticks    INTEGER NOT NULL,
    scored_at         TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    is_draw           INTEGER NOT NULL DEFAULT 0
);
"""


def _seed_leaderboard(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_LEADERBOARD_DDL)
    rows = [
        ("match.001", "player.a", "loadout.example.a", 1500, "player.b", 200, 120, 0),
        ("match.002", "player.b", "loadout.example.b", 2400, "player.a", 100, 90, 0),
        ("match.003", "player.c", "loadout.example.c", 900, "player.a", 300, 200, 0),
        ("match.004", "player.a", "loadout.example.a", 9999, "player.b", 9999, 200, 1),
    ]
    for match_id, winner, loadout, score, loser, loser_score, ticks, is_draw in rows:
        conn.execute(
            "INSERT INTO leaderboard_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                match_id,
                winner,
                loadout,
                score,
                loser,
                loser_score,
                ticks,
                "2026-04-30T00:00:00+00:00",
                "2026-04-30T00:00:00+00:00",
                is_draw,
            ),
        )
    conn.commit()
    conn.close()


@pytest.mark.integration
def test_leaderboard_top_n_orders_by_score_and_skips_draws(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite"
    _seed_leaderboard(db)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["leaderboard", "--ledger", str(db), "--top", "2"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    body = result.stdout
    # Highest score first; draw row (match.004) excluded despite top score.
    assert body.index("player.b") < body.index("player.a")
    assert "match.004" not in body
    assert "match.003" not in body  # top 2 only


@pytest.mark.integration
def test_leaderboard_missing_table_fails(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    runner = CliRunner()
    result = runner.invoke(main, ["leaderboard", "--ledger", str(db), "--top", "5"])
    assert result.exit_code != 0
    assert "leaderboard" in result.stderr
