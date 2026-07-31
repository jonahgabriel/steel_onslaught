#!/usr/bin/env python3
"""Canary launch gate for the L-GATE-2 battery lane (OMN-15488 leg (a) §6.3).

A battery on this driver costs ~5.5 hours of exclusive MLX-endpoint
occupancy. Leg (a) additionally flies a pairing that has never been flown --
a sniper-vs-sniper mirror of two long-range ironclads -- and its evaluator
binding (``win_damage_differential_v1``) promotes ONLY on a DECISIVE
learning-seat win. A stalemate-dominated regime would therefore exhaust the
15-match promote budget and land the pre-registered §6.1 NO-PROMOTION escape
after burning the whole run.

Leg (a)'s pre-registration answers that with a quarantined n=2 canary and
THREE clauses that must all hold before the battery may be launched:

  1. both matches produce a ``battery_raw.jsonl`` row with
     ``replay_validity == 1`` for BOTH seats;
  2. every provider observed in the lane ledger is one the executing overlay
     declares;
  3. AT LEAST ONE of the two matches terminates DECISIVELY -- a mech
     destroyed -- rather than at the tick bound.

Clause 3 is the new one, and it is the one that converts "discover the
stalemate regime after 5.5 hours" into "discover it in about 20 minutes".
Nothing in the tree checked it. This script does, and it fails CLOSED: a
missing raw file, an unreadable ledger, a short row count, or an
unparseable row is a FAIL, never a silent pass, on exactly the reasoning
``check_preregistration_timing.py`` gives for its own fail-closed posture.

A canary result is NEVER battery evidence in either direction (§6.3). This
script decides one thing only: may the battery be launched.

Usage
-----
    uv run python scripts/check_canary_decisiveness.py \\
        --state-root "$SNAP/battery_state/omn15488_legA_canary" \\
        --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml

Exit codes
----------
0   all three clauses hold -- the battery may be launched.
1   any clause fails, or the evidence needed to check it is missing.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# ``end_reason`` values that mean a mech was destroyed. Deliberately narrow,
# matching §6.3's own words ("a VICTORY_DECLARED with a mech destroyed, not at
# the tick bound") rather than the looser "not a draw": on the ``foundry_60``
# arena leg (a) flies there are no objectives and no ``vp_threshold``, so an
# objective victory cannot occur and the two sets coincide -- but an arena
# swap must not silently widen this gate.
DECISIVE_END_REASONS = frozenset({"last_mech_standing", "pilot_killed"})

# Ledger event types whose payloads carry a ``provider_id`` literal.
_COMPLETION_EVENT_TYPES = (
    "llm_completion_requested",
    "llm_completion_resolved",
    "llm_completion_failed",
)


@dataclass(frozen=True)
class ClauseResult:
    """One §6.3 clause and whether the artifacts satisfy it."""

    name: str
    passed: bool
    detail: str


def load_rows(raw_path: Path) -> list[dict[str, Any]]:
    """Every JSON row the driver appended, or raise if unreadable."""
    if not raw_path.is_file():
        raise FileNotFoundError(f"canary raw evidence not found: {raw_path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{raw_path}:{number} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{raw_path}:{number} is not a JSON object")
        rows.append(parsed)
    return rows


def declared_provider_ids(overlay_path: Path) -> frozenset[str]:
    """The ``llm.providers[].provider_id`` set the executing overlay declares.

    Read from the raw YAML rather than the typed loader so this gate stays
    usable against a snapshot whose package version may differ from the
    checkout running it.
    """
    raw = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{overlay_path} did not parse to a mapping")
    providers = (raw.get("llm") or {}).get("providers") or []
    ids = {str(entry["provider_id"]) for entry in providers if "provider_id" in entry}
    if not ids:
        raise ValueError(f"{overlay_path} declares no llm.providers[].provider_id")
    return frozenset(ids)


def observed_provider_ids(events_db: Path) -> frozenset[str]:
    """Every ``provider_id`` literal the lane ledger recorded."""
    if not events_db.is_file():
        raise FileNotFoundError(f"canary ledger not found: {events_db}")
    placeholders = ",".join("?" for _ in _COMPLETION_EVENT_TYPES)
    connection = sqlite3.connect(f"file:{events_db}?mode=ro&immutable=1", uri=True)
    try:
        query = f"SELECT payload_json FROM events WHERE event_type IN ({placeholders})"
        observed: set[str] = set()
        for (payload_json,) in connection.execute(query, _COMPLETION_EVENT_TYPES):
            payload = json.loads(payload_json)
            provider_id = payload.get("provider_id")
            if provider_id is not None:
                observed.add(str(provider_id))
    finally:
        connection.close()
    return frozenset(observed)


def check_replay_validity(rows: list[dict[str, Any]], *, expected_rows: int) -> ClauseResult:
    """§6.3 clause 1 -- both matches valid-replayed on BOTH seats."""
    if len(rows) != expected_rows:
        return ClauseResult(
            "clause-1-replay-validity",
            False,
            f"expected {expected_rows} canary rows, found {len(rows)}",
        )
    invalid: list[str] = []
    for row in rows:
        validity = row.get("replay_validity")
        if not isinstance(validity, dict) or not validity:
            invalid.append(f"seed {row.get('seed')}: no replay_validity recorded")
            continue
        bad = {player: score for player, score in validity.items() if score != 1}
        if bad:
            invalid.append(f"seed {row.get('seed')}: {bad}")
    if invalid:
        return ClauseResult("clause-1-replay-validity", False, "; ".join(invalid))
    return ClauseResult(
        "clause-1-replay-validity",
        True,
        f"{len(rows)}/{len(rows)} rows replay_validity == 1 on every seat",
    )


def check_providers(observed: frozenset[str], declared: frozenset[str]) -> ClauseResult:
    """§6.3 clause 2 -- providers observed are a subset of those declared."""
    if not observed:
        return ClauseResult(
            "clause-2-providers",
            False,
            "no provider_id literal appears in the canary ledger at all",
        )
    stray = observed - declared
    if stray:
        return ClauseResult(
            "clause-2-providers",
            False,
            f"undeclared provider(s) observed: {sorted(stray)}; declared: {sorted(declared)}",
        )
    return ClauseResult(
        "clause-2-providers",
        True,
        f"observed {sorted(observed)} within declared {sorted(declared)}",
    )


def check_decisiveness(rows: list[dict[str, Any]]) -> ClauseResult:
    """§6.3 clause 3 -- at least one match ended with a mech destroyed."""
    reasons = [str(row.get("end_reason")) for row in rows]
    decisive = [reason for reason in reasons if reason in DECISIVE_END_REASONS]
    if not decisive:
        return ClauseResult(
            "clause-3-decisiveness",
            False,
            (
                f"0/{len(rows)} matches ended decisively; end_reasons={reasons}. "
                "Per §6.3 the battery is NOT launched: report this as an "
                "execution-infrastructure finding (the sniper mirror is "
                "stalemate-dominated at this arena/loadout) and return leg (a) "
                "for redesign under a NEW pre-registration."
            ),
        )
    return ClauseResult(
        "clause-3-decisiveness",
        True,
        f"{len(decisive)}/{len(rows)} matches ended decisively; end_reasons={reasons}",
    )


def evaluate(state_root: Path, overlay: Path, *, expected_rows: int) -> list[ClauseResult]:
    """Run all three clauses; any unreadable input is a FAIL, not a skip."""
    try:
        rows = load_rows(state_root / "battery_raw.jsonl")
    except (FileNotFoundError, ValueError) as exc:
        return [ClauseResult("inputs", False, str(exc))]
    results = [
        check_replay_validity(rows, expected_rows=expected_rows),
        check_decisiveness(rows),
    ]
    try:
        results.insert(
            1,
            check_providers(
                observed_provider_ids(state_root / "events.sqlite3"),
                declared_provider_ids(overlay),
            ),
        )
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        results.insert(1, ClauseResult("clause-2-providers", False, str(exc)))
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root",
        type=Path,
        required=True,
        help="the canary's THROWAWAY state-root (never the battery's)",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        required=True,
        help="the overlay the canary flew; its declared provider set is clause 2's authority",
    )
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=2,
        help="canary match count (§6.3 pre-registers n=2)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    results = evaluate(
        args.state_root.resolve(), args.overlay.resolve(), expected_rows=args.expected_rows
    )
    for result in results:
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.name}: {result.detail}")
    if all(result.passed for result in results):
        print("CANARY GATE PASS -- the battery may be launched.")
        return 0
    print("CANARY GATE FAIL -- do NOT launch the battery.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
