#!/usr/bin/env python3
"""Battery contamination gate for a lane's evidence rows (SO-METHOD-MECH).

Every evidence-bearing battery pre-declares a seed plan (``n`` seeds,
``seed_base + 1 .. seed_base + n``, one process invocation per seed) and
every evidence doc under ``docs/evidence/`` hand-verifies that
``battery_raw.jsonl`` holds exactly that plan before citing any aggregate
from it ("Battery validity and the contamination guard" section). This
script makes that check mechanical.

2026-07-25 lesson (SO-COMP-CA / SO-COMP-R1 / SO-UTIL-REWARD), the reason this
gate reads ``battery_raw.jsonl`` and NOT the ledger's ``match_started``
count: the battery driver (``scripts/run_ogate_objectives_battery.py``)
retries a seed in-process on a transport error, so one seed can produce
several ``match_started`` events in the ledger for matches that were
abandoned mid-flight and never scored -- the composition_ca_only_dmg16 lane
has 34 ``match_started`` events but exactly 30 completed, scored rows in
``battery_raw.jsonl`` (4 orphaned retries). A gate keyed on
``match_started`` count would have force-failed that lane even though it is
a clean, citable 30/30 battery. The gate this script implements is: does
``battery_raw.jsonl`` hold exactly one COMPLETED row per expected seed, with
no duplicates and no gaps? Orphaned ``match_started`` rows are retry residue
and are reported for visibility (INFO), never as a failure by themselves.

A row's mere presence in ``battery_raw.jsonl`` *is* "COMPLETED" -- the driver
only appends a row after a match runs to a scored terminal (see
``_run_match``/``main`` in ``run_ogate_objectives_battery.py``); a seed that
raises is recorded in ``skipped_seeds`` and never gets a row. There is no
separate per-row status field to check.

Usage
-----
    uv run python scripts/check_contamination_gate.py \\
        --state-root .onex_state/steel_onslaught/<lane> \\
        --n 30 --seed-base 5000

``--n``/``--seed-base`` default to 30/5000 (seeds 5001-5030), the program's
standard battery shape.

Exit codes
----------
0   ``battery_raw.jsonl`` holds exactly the expected COMPLETED rows (each
    expected seed exactly once, no dupes, no gaps, no out-of-range seeds),
    and the ledger's completed-match set agrees with ``battery_raw.jsonl``'s
    match_id set.
1   genuine contamination (wrong row count, duplicate seed, missing seed,
    out-of-range seed, or the ledger's completed-match set disagrees with
    ``battery_raw.jsonl``) OR any required input is missing/unusable
    (fail-closed).

CI wiring: a deliberate non-goal
---------------------------------
``.onex_state/`` (the lane state-root this script reads) is gitignored --
battery ledgers are local, per-machine artifacts of a live LLM run, never
committed. There is therefore no repo-tracked lane data for a CI job to run
this check against, unlike ``check_sanitization.py --all`` or
``check_evidence_schema.py``, which sweep files that ARE tracked. This
script is invoked manually, once per arm, right after a battery finishes and
before its evidence doc is written -- its printed row/seed/orphan counts are
exactly the numbers the evidence doc's "Battery validity and the
contamination guard" section already quotes by hand.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path


class ContaminationCheckError(Exception):
    """Raised for any fail-closed condition (missing/unusable input)."""


@dataclass(frozen=True)
class BatteryRow:
    seed: int
    match_id: str


@dataclass(frozen=True)
class SeedCoverageResult:
    expected: frozenset[int]
    actual: tuple[int, ...]  # as read, in file order, duplicates preserved
    duplicates: frozenset[int]
    missing: frozenset[int]
    out_of_range: frozenset[int]

    @property
    def clean(self) -> bool:
        return not (self.duplicates or self.missing or self.out_of_range)


@dataclass(frozen=True)
class LedgerReconciliation:
    match_started_ids: frozenset[str]
    match_ended_ids: frozenset[str]
    battery_raw_ids: frozenset[str]

    @property
    def orphaned_match_started(self) -> frozenset[str]:
        """Started but never ended -- retry residue. INFO, not a failure."""
        return self.match_started_ids - self.match_ended_ids

    @property
    def orphaned_match_ended(self) -> frozenset[str]:
        """Ended but never started -- should be structurally impossible;
        reported as a genuine anomaly if it ever occurs."""
        return self.match_ended_ids - self.match_started_ids

    @property
    def ended_not_in_raw(self) -> frozenset[str]:
        """Ledger says COMPLETED but no evidence row exists -- genuine
        contamination (a row was lost after the match finished)."""
        return self.match_ended_ids - self.battery_raw_ids

    @property
    def raw_not_in_ended(self) -> frozenset[str]:
        """Evidence row exists with no matching ledger completion -- genuine
        contamination (a row was fabricated, edited, or copied from another
        lane's ledger)."""
        return self.battery_raw_ids - self.match_ended_ids

    @property
    def clean(self) -> bool:
        return not (self.ended_not_in_raw or self.raw_not_in_ended)


@dataclass
class GateReport:
    rows_read: int
    seed_coverage: SeedCoverageResult
    reconciliation: LedgerReconciliation
    duplicate_match_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def clean(self) -> bool:
        return (
            self.seed_coverage.clean and self.reconciliation.clean and not self.duplicate_match_ids
        )


def load_battery_rows(raw_path: Path) -> list[BatteryRow]:
    if not raw_path.exists():
        raise ContaminationCheckError(f"battery_raw.jsonl not found: {raw_path}")
    rows: list[BatteryRow] = []
    for line_no, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContaminationCheckError(f"{raw_path}:{line_no}: invalid JSON ({exc})") from exc
        try:
            rows.append(BatteryRow(seed=int(payload["seed"]), match_id=str(payload["match_id"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise ContaminationCheckError(
                f"{raw_path}:{line_no}: row missing/invalid 'seed' or 'match_id' ({exc})"
            ) from exc
    return rows


def check_seed_coverage(rows: list[BatteryRow], *, seed_base: int, n: int) -> SeedCoverageResult:
    expected = frozenset(seed_base + i for i in range(1, n + 1))
    actual = tuple(row.seed for row in rows)
    seen: set[int] = set()
    duplicates: set[int] = set()
    for seed in actual:
        if seed in seen:
            duplicates.add(seed)
        seen.add(seed)
    missing = frozenset(expected - seen)
    out_of_range = frozenset(seen - expected)
    return SeedCoverageResult(
        expected=expected,
        actual=actual,
        duplicates=frozenset(duplicates),
        missing=missing,
        out_of_range=out_of_range,
    )


def load_ledger_match_ids(events_db: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Return (match_started match_ids, match_ended match_ids), each deduped."""
    if not events_db.exists():
        raise ContaminationCheckError(f"events ledger not found: {events_db}")
    con = sqlite3.connect(f"file:{events_db}?mode=ro", uri=True)
    try:
        started = frozenset(
            row[0]
            for row in con.execute(
                "SELECT DISTINCT match_id FROM events WHERE event_type = 'match_started'"
            )
        )
        ended = frozenset(
            row[0]
            for row in con.execute(
                "SELECT DISTINCT match_id FROM events WHERE event_type = 'match_ended'"
            )
        )
        return started, ended
    finally:
        con.close()


def build_report(state_root: Path, *, seed_base: int, n: int) -> GateReport:
    raw_path = state_root / "battery_raw.jsonl"
    events_db = state_root / "events.sqlite3"

    rows = load_battery_rows(raw_path)
    seed_coverage = check_seed_coverage(rows, seed_base=seed_base, n=n)

    match_ids = [row.match_id for row in rows]
    duplicate_match_ids = frozenset(
        match_id for match_id in match_ids if match_ids.count(match_id) > 1
    )

    started_ids, ended_ids = load_ledger_match_ids(events_db)
    reconciliation = LedgerReconciliation(
        match_started_ids=started_ids,
        match_ended_ids=ended_ids,
        battery_raw_ids=frozenset(match_ids),
    )

    return GateReport(
        rows_read=len(rows),
        seed_coverage=seed_coverage,
        reconciliation=reconciliation,
        duplicate_match_ids=duplicate_match_ids,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root",
        type=Path,
        required=True,
        help="lane state-root, e.g. .onex_state/steel_onslaught/<lane> "
        "(its battery_raw.jsonl and events.sqlite3 are read)",
    )
    parser.add_argument("--n", type=int, default=30, help="expected battery size (default: 30)")
    parser.add_argument(
        "--seed-base",
        type=int,
        default=5000,
        help="expected seeds are seed_base+1 .. seed_base+n (default: 5000)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state_root = args.state_root.resolve()

    try:
        report = build_report(state_root, seed_base=args.seed_base, n=args.n)
    except ContaminationCheckError as exc:
        print(f"CONTAMINATION GATE FAILED (fail-closed): {exc}", file=sys.stderr)
        return 1

    sc = report.seed_coverage
    rec = report.reconciliation

    seed_end = args.seed_base + args.n
    print(f"State root:                  {state_root}")
    print(f"Expected seeds:               {args.seed_base + 1}..{seed_end} (n={args.n})")
    print(f"battery_raw.jsonl rows:       {report.rows_read}")
    print(f"Distinct seeds:               {len(set(sc.actual))}")
    print(f"Duplicate seeds:              {sorted(sc.duplicates) if sc.duplicates else 0}")
    print(f"Missing seeds (gaps):         {sorted(sc.missing) if sc.missing else 0}")
    print(f"Out-of-range seeds:           {sorted(sc.out_of_range) if sc.out_of_range else 0}")
    dup_match_ids = sorted(report.duplicate_match_ids) if report.duplicate_match_ids else 0
    print(f"Duplicate match_id collisions: {dup_match_ids}")
    print(f"Unfiltered ledger match_started: {len(rec.match_started_ids)}")
    print(f"Unfiltered ledger match_ended:   {len(rec.match_ended_ids)}")
    print(
        f"INFO -- orphaned match_started (retry residue, no match_ended): "
        f"{len(rec.orphaned_match_started)}"
    )
    if rec.orphaned_match_started:
        for match_id in sorted(rec.orphaned_match_started):
            print(f"  INFO   {match_id}")
    if rec.orphaned_match_ended:
        print(
            f"ANOMALY -- match_ended with no match_started (should be structurally "
            f"impossible): {sorted(rec.orphaned_match_ended)}"
        )
    print(
        f"Ledger match_ended vs battery_raw match_id sets bijective: {'yes' if rec.clean else 'NO'}"
    )
    if rec.ended_not_in_raw:
        print(
            f"  CONTAMINATION: ledger shows COMPLETED matches with no battery_raw row: "
            f"{sorted(rec.ended_not_in_raw)}"
        )
    if rec.raw_not_in_ended:
        print(
            f"  CONTAMINATION: battery_raw rows with no matching ledger completion: "
            f"{sorted(rec.raw_not_in_ended)}"
        )

    if not report.clean:
        print("\nCONTAMINATION GATE FAILED: see CONTAMINATION lines above.", file=sys.stderr)
        return 1

    print(
        f"\nOK: battery_raw.jsonl holds exactly the {args.n} expected COMPLETED rows "
        f"(seeds {args.seed_base + 1}..{args.seed_base + args.n}), no dupes, no gaps, "
        f"and the ledger's completed-match set agrees with it."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
