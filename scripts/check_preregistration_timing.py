#!/usr/bin/env python3
"""Pre-registration timing gate for a battery lane's overlay (SO-METHOD-MECH).

Every evidence-bearing battery in this program pre-registers its overlay
(the header block: the ONE changed field, the comparison anchors, the single
formal criterion) in a git commit *before* running the first match. Every
evidence doc under ``docs/evidence/`` states the commit hash, its timestamp,
and the first ``match_started`` timestamp, then asserts the gap is positive
-- by hand, per document. This script makes that check mechanical: point it
at a lane's state-root and the overlay it pre-registered, and it fails
closed if the ordering is wrong or the inputs needed to check it are
missing.

Usage
-----
    uv run python scripts/check_preregistration_timing.py \\
        --state-root .onex_state/steel_onslaught/<lane> \\
        --overlay contracts_data/overlays/<lane>_qwen.yaml

Exit codes
----------
0   pre-registration commit's AUTHOR timestamp strictly precedes the lane's
    earliest ``match_started`` event.
1   violation (the commit's author timestamp is at or after the earliest
    ``match_started``) OR any required input is missing/unusable
    (fail-closed: this script never reports "OK" on absent evidence).

CI wiring: a deliberate non-goal
---------------------------------
``.onex_state/`` (the lane state-root this script reads) is gitignored --
battery ledgers are local, per-machine artifacts of a live LLM run, never
committed. There is therefore no repo-tracked lane data for a CI job to run
this check against, unlike ``check_sanitization.py --all`` or
``check_evidence_schema.py``, which sweep files that ARE tracked. This
script is invoked manually, once per arm, right after a battery finishes and
before its evidence doc is written -- its printed commit hash, timestamps,
and gap are exactly the numbers the evidence doc's "Pre-registration"
section already quotes by hand.

Why the commit's AUTHOR date, not its COMMITTER date
-----------------------------------------------------
2026-07-25 finding (SO-COMP-CA): the overlay
``tactical_split_overdeal_utility_asym_composition_ca_only_dmg16_qwen.yaml``
was pre-registered in a commit at author time ``2026-07-25T09:38:58-07:00``
(``2026-07-25T16:38:58Z``). Before the branch was pushed, a sibling arm's
commit landed on the same base and the branch was rebased onto it -- git
preserves the original AUTHOR identity/timestamp across a rebase but stamps
a NEW committer timestamp (the moment of the rebase), producing a commit
whose author date is unchanged (``2026-07-25T09:38:58-07:00``) but whose
committer date jumped to ``2026-07-25T10:34:07-07:00``
(``2026-07-25T17:34:07Z``). The battery's first ``match_started`` was
``2026-07-25T16:54:41.687280+00:00``. Checking the AUTHOR date gives a
correct, positive gap of +15m43s (author precedes match_started); checking
the COMMITTER date would give a negative gap of about -39m (the rebased
committer timestamp lands AFTER the first match started) and wrongly report
a pre-registration violation on a battery that was, in fact, pre-registered
before any match ran. This script therefore reads and prints the committer
date for visibility only -- the pass/fail decision is made on the AUTHOR
date alone.

What "the pre-registration commit" means here
----------------------------------------------
The MOST RECENT commit on ``HEAD``'s ancestry that touched the given overlay
path -- not the first. 2026-07-25 finding (SO-UTIL-REWARD): that lane's
overlay was pre-registered in one commit (the hypotheses + the formal
criterion, author time ``2026-07-25T17:26:48Z``) and then AMENDED in a
second commit before the battery ran (an outcome-independent discard rule,
author time ``2026-07-25T18:00:44Z``, only 11 seconds before the first
``match_started`` at ``2026-07-25T18:00:55.864143Z``). Checking only the
first touch would miss a criterion amendment made after that first commit
-- including, in the worst case, one made after seeing match results. The
binding constraint is the LATEST touch: if it precedes the earliest
``match_started``, every earlier touch necessarily does too.

Deliberately NOT ``--follow``: these overlays are near-byte-copies of each
other (a new arm's overlay is typically forked from a prior arm's overlay
with one field changed), so git's content-similarity rename detection can
attribute a brand-new overlay to an unrelated, much older ancestor file and
walk history that has nothing to do with this lane's own pre-registration.
Only the single latest commit at the exact given path is needed here, so
``--follow`` is both unnecessary and actively wrong in this repo's shape.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


class PreregistrationCheckError(Exception):
    """Raised for any fail-closed condition (missing/unusable input)."""


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    author_iso: str
    committer_iso: str


def _run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PreregistrationCheckError(
            f"git {' '.join(args)} failed (cwd={cwd}): {result.stderr.strip()}"
        )
    return result.stdout


def resolve_repo_root(anchor: Path) -> Path:
    """Return the git repo root containing ``anchor`` (a file or directory)."""
    directory = anchor if anchor.is_dir() else anchor.parent
    if not directory.exists():
        raise PreregistrationCheckError(f"path does not exist: {directory}")
    out = _run_git(directory, "rev-parse", "--show-toplevel")
    return Path(out.strip())


def _has_any_commit(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def find_latest_touch_commit(repo_root: Path, relpath: str) -> CommitInfo | None:
    """The most recent commit on HEAD's ancestry that touched ``relpath``.

    Returns ``None`` if the path has no commit history at all -- either the
    repo has no commits yet (an unborn HEAD, which ``git log`` refuses
    outright rather than returning empty output) or HEAD exists but never
    touched this path -- rather than raising, so the caller can produce a
    single, uniform fail-closed error message. No ``--follow``: see the
    module docstring for why rename-following is wrong for this repo's
    near-byte-copy overlay files.
    """
    if not _has_any_commit(repo_root):
        return None
    out = _run_git(
        repo_root,
        "log",
        "-1",
        "--format=%H%x1f%aI%x1f%cI",
        "--",
        relpath,
    )
    line = out.strip()
    if not line:
        return None
    sha, author_iso, committer_iso = line.split("\x1f")
    return CommitInfo(sha=sha, author_iso=author_iso, committer_iso=committer_iso)


def _parse_iso(value: str) -> datetime:
    # Both `git log %aI`/%cI` and the events ledger's `emitted_at` already
    # carry an explicit UTC or local offset (never a bare 'Z' in practice for
    # either source), but normalize defensively so a 'Z'-suffixed value from
    # either surface never raises.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def earliest_match_started(events_db: Path) -> str | None:
    """The earliest ``emitted_at`` among ``match_started`` events, or ``None``."""
    if not events_db.exists():
        raise PreregistrationCheckError(f"events ledger not found: {events_db}")
    con = sqlite3.connect(f"file:{events_db}?mode=ro", uri=True)
    try:
        cur = con.execute("SELECT MIN(emitted_at) FROM events WHERE event_type = 'match_started'")
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None
    finally:
        con.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root",
        type=Path,
        required=True,
        help="lane state-root, e.g. .onex_state/steel_onslaught/<lane> "
        "(its events.sqlite3 is read)",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        required=True,
        help="the overlay yaml this lane pre-registered (must be tracked by git)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        overlay_path = args.overlay.resolve()
        if not overlay_path.exists():
            raise PreregistrationCheckError(f"overlay file not found: {overlay_path}")

        repo_root = resolve_repo_root(overlay_path)
        try:
            relpath = overlay_path.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise PreregistrationCheckError(
                f"overlay {overlay_path} is not inside its own repo root {repo_root}"
            ) from exc

        commit = find_latest_touch_commit(repo_root, relpath)
        if commit is None:
            raise PreregistrationCheckError(
                f"overlay {relpath!r} has no commit history on the current branch "
                "-- it was never committed, so no pre-registration timestamp exists"
            )

        state_root = args.state_root.resolve()
        events_db = state_root / "events.sqlite3"
        earliest_started = earliest_match_started(events_db)
        if earliest_started is None:
            raise PreregistrationCheckError(
                f"no match_started events found in {events_db} -- lane has not run "
                "any matches, nothing to check the pre-registration commit against"
            )
    except PreregistrationCheckError as exc:
        print(f"PRE-REGISTRATION TIMING GATE FAILED (fail-closed): {exc}", file=sys.stderr)
        return 1

    author_dt = _parse_iso(commit.author_iso)
    started_dt = _parse_iso(earliest_started)
    gap: timedelta = started_dt - author_dt

    print(f"Overlay:                    {relpath}")
    print(f"Pre-registration commit:    {commit.sha}")
    print(f"  author timestamp:         {commit.author_iso}   (load-bearing)")
    print(f"  committer timestamp:      {commit.committer_iso}   (NOT authoritative -- ")
    print("                              a rebase/squash can move this without changing ")
    print("                              when the overlay's content was actually authored)")
    print(f"First match_started:        {earliest_started}")
    print(f"Gap (match_started - author date): {gap}")

    if gap <= timedelta(0):
        print(
            "\nVIOLATION: the pre-registration commit's AUTHOR timestamp is at or after "
            "the lane's earliest match_started. The overlay's criterion was not locked "
            "in before the battery began.",
            file=sys.stderr,
        )
        return 1

    print("\nOK: pre-registration commit's author timestamp precedes the first match_started.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
