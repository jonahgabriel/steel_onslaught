"""Pre-registration timing gate (SO-METHOD-MECH) — real RED and GREEN cases.

Builds a throwaway git repo (for the overlay's commit history, with
``GIT_AUTHOR_DATE``/``GIT_COMMITTER_DATE`` set explicitly so both dates are
under test control) and a real SQLite event ledger (via the project's own
``SQLiteLedger`` -- the actual artifact ``run_ogate_objectives_battery.py``
writes to, not a hand-rolled stand-in) for every case, and drives the real
``scripts.check_preregistration_timing.main`` entrypoint end to end. Every
RED case is a seeded fixture proving the gate actually fires, not merely
inspecting return values in isolation.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.check_preregistration_timing import (
    find_latest_touch_commit,
    main,
    resolve_repo_root,
)
from steel_onslaught.events.envelope import ModelSOEventSubject, SOEventType, make_event
from tests.sqlite_ledger import open_sqlite_ledger

pytestmark = pytest.mark.integration

_PATH = os.environ.get("PATH", "/usr/bin:/bin")


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _commit_overlay(
    repo: Path,
    relpath: str,
    *,
    content: str,
    author_date: str,
    committer_date: str,
    amend: bool = False,
) -> str:
    """Write ``relpath`` and commit it with explicit author/committer dates.

    Returns the new commit sha. ``amend=True`` amends the previous commit
    (simulating a rebase: same content, new commit object, and — unless the
    caller also changes ``author_date`` — the same author identity/date but
    a new committer date), exactly reproducing the real 2026-07-25 SO-COMP-CA
    rebase shape.
    """
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", relpath)
    args = ["commit", "-q", "-m", f"commit {relpath}"]
    if amend:
        args = ["commit", "-q", "--amend", "--no-edit"]
    env = {
        "GIT_AUTHOR_DATE": author_date,
        "GIT_COMMITTER_DATE": committer_date,
        # subprocess env replaces the whole environment unless we carry PATH etc.
        "PATH": _PATH,
        "HOME": str(Path.home()),
    }
    _git(repo, *args, env=env)
    return _git(repo, "log", "-1", "--format=%H").strip()


def _make_lane(state_root: Path, *, match_started_at: list[datetime]) -> None:
    """Build a real events.sqlite3 with one match_started per timestamp given."""
    state_root.mkdir(parents=True, exist_ok=True)
    ledger = open_sqlite_ledger(state_root / "events.sqlite3")
    for index, started_at in enumerate(match_started_at):
        match_id = f"match.fixture.{index:03d}"
        ledger.append(
            make_event(
                match_id=match_id,
                tick=0,
                sequence_in_tick=0,
                event_type=SOEventType.MATCH_STARTED,
                producer_node="node.test",
                subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
                payload={},
                correlation_id=uuid4(),
                causation_id=None,
                event_id=f"{index:026d}",  # 26-char ULID-shaped id; uniqueness only
                message_id=uuid4(),
                emitted_at=started_at,
            )
        )


# --------------------------------------------------------------------------
# find_latest_touch_commit / resolve_repo_root — unit-level
# --------------------------------------------------------------------------


def test_resolve_repo_root_finds_toplevel(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    assert resolve_repo_root(nested).resolve() == repo.resolve()


def test_find_latest_touch_commit_none_when_never_committed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "untracked.yaml").write_text("x: 1\n", encoding="utf-8")
    assert find_latest_touch_commit(repo, "untracked.yaml") is None


def test_find_latest_touch_commit_returns_latest_not_first(tmp_path: Path) -> None:
    """2026-07-25 SO-UTIL-REWARD shape: overlay committed, then amended by a
    second commit before the battery ran. The checker must anchor on the
    LATEST touch, since that is the binding "locked in before the battery"
    constraint.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    first_sha = _commit_overlay(
        repo,
        "overlay.yaml",
        content="criterion: v1\n",
        author_date="2026-01-01T09:00:00-07:00",
        committer_date="2026-01-01T09:00:00-07:00",
    )
    second_sha = _commit_overlay(
        repo,
        "overlay.yaml",
        content="criterion: v1\namendment: discard-rule\n",
        author_date="2026-01-01T09:30:00-07:00",
        committer_date="2026-01-01T09:30:00-07:00",
    )
    assert first_sha != second_sha
    commit = find_latest_touch_commit(repo, "overlay.yaml")
    assert commit is not None
    assert commit.sha == second_sha
    assert commit.author_iso.startswith("2026-01-01T09:30:00")


# --------------------------------------------------------------------------
# main() — GREEN cases
# --------------------------------------------------------------------------


def test_main_passes_when_author_date_precedes_first_match_started(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_overlay(
        repo,
        "contracts_data/overlays/lane.yaml",
        content="criterion: threshold 31.5\n",
        author_date="2026-01-01T09:00:00-07:00",
        committer_date="2026-01-01T09:00:00-07:00",
    )
    state_root = tmp_path / "state"
    _make_lane(state_root, match_started_at=[datetime(2026, 1, 1, 16, 55, tzinfo=UTC)])

    exit_code = main(
        [
            "--state-root",
            str(state_root),
            "--overlay",
            str(repo / "contracts_data/overlays/lane.yaml"),
        ]
    )
    assert exit_code == 0


def test_main_passes_across_a_rebase_using_author_date_not_committer_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The load-bearing regression: reproduces the 2026-07-25 SO-COMP-CA
    rebase exactly. Author date precedes the first match_started; the
    REBASED committer date (simulated via --amend) lands AFTER it. If this
    script used committer date for the decision, it would wrongly fail here.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_overlay(
        repo,
        "contracts_data/overlays/lane.yaml",
        content="criterion: threshold 31.5\n",
        author_date="2026-01-01T09:00:00-07:00",
        committer_date="2026-01-01T09:00:00-07:00",
    )
    # Simulate the rebase: same content, same author date, NEW committer date
    # (the moment of the rebase) landing AFTER the earliest match_started.
    _commit_overlay(
        repo,
        "contracts_data/overlays/lane.yaml",
        content="criterion: threshold 31.5\n",
        author_date="2026-01-01T09:00:00-07:00",
        committer_date="2026-01-01T14:00:00-07:00",
        amend=True,
    )
    commit = find_latest_touch_commit(repo, "contracts_data/overlays/lane.yaml")
    assert commit is not None
    # Sanity: the committer date really is after the match_started we're about
    # to use, and the author date really is before it -- otherwise this test
    # would not be exercising the regression it claims to.
    assert commit.committer_iso.startswith("2026-01-01T14:00:00")
    assert commit.author_iso.startswith("2026-01-01T09:00:00")

    state_root = tmp_path / "state"
    # 10:00 local (-07:00) == 17:00 UTC: after the author date (09:00 local /
    # 16:00 UTC) but before the rebased committer date (14:00 local / 21:00 UTC).
    _make_lane(state_root, match_started_at=[datetime(2026, 1, 1, 17, 0, tzinfo=UTC)])

    exit_code = main(
        [
            "--state-root",
            str(state_root),
            "--overlay",
            str(repo / "contracts_data/overlays/lane.yaml"),
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0, out
    assert "OK" in out


# --------------------------------------------------------------------------
# main() — RED / seeded-violation cases
# --------------------------------------------------------------------------


def test_main_fails_when_overlay_committed_after_first_match_started(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seeded RED: a backdated / late pre-registration -- the overlay's
    commit lands AFTER the battery's first match_started.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_overlay(
        repo,
        "contracts_data/overlays/lane.yaml",
        content="criterion: threshold 31.5\n",
        author_date="2026-01-01T20:00:00-07:00",
        committer_date="2026-01-01T20:00:00-07:00",
    )
    state_root = tmp_path / "state"
    _make_lane(state_root, match_started_at=[datetime(2026, 1, 1, 16, 0, tzinfo=UTC)])

    exit_code = main(
        [
            "--state-root",
            str(state_root),
            "--overlay",
            str(repo / "contracts_data/overlays/lane.yaml"),
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "VIOLATION" in err


def test_main_fails_closed_on_missing_overlay_file(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    _make_lane(state_root, match_started_at=[datetime(2026, 1, 1, 16, 0, tzinfo=UTC)])
    exit_code = main(
        [
            "--state-root",
            str(state_root),
            "--overlay",
            str(tmp_path / "does" / "not" / "exist.yaml"),
        ]
    )
    assert exit_code == 1


def test_main_fails_closed_on_overlay_never_committed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    untracked = repo / "contracts_data/overlays/lane.yaml"
    untracked.parent.mkdir(parents=True)
    untracked.write_text("criterion: x\n", encoding="utf-8")

    state_root = tmp_path / "state"
    _make_lane(state_root, match_started_at=[datetime(2026, 1, 1, 16, 0, tzinfo=UTC)])

    exit_code = main(["--state-root", str(state_root), "--overlay", str(untracked)])
    assert exit_code == 1


def test_main_fails_closed_on_missing_state_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_overlay(
        repo,
        "contracts_data/overlays/lane.yaml",
        content="criterion: x\n",
        author_date="2026-01-01T09:00:00-07:00",
        committer_date="2026-01-01T09:00:00-07:00",
    )
    exit_code = main(
        [
            "--state-root",
            str(tmp_path / "no-such-lane"),
            "--overlay",
            str(repo / "contracts_data/overlays/lane.yaml"),
        ]
    )
    assert exit_code == 1


def test_main_fails_closed_on_no_match_started_rows(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_overlay(
        repo,
        "contracts_data/overlays/lane.yaml",
        content="criterion: x\n",
        author_date="2026-01-01T09:00:00-07:00",
        committer_date="2026-01-01T09:00:00-07:00",
    )
    state_root = tmp_path / "state"
    _make_lane(state_root, match_started_at=[])  # empty ledger, no match_started at all

    exit_code = main(
        [
            "--state-root",
            str(state_root),
            "--overlay",
            str(repo / "contracts_data/overlays/lane.yaml"),
        ]
    )
    assert exit_code == 1
