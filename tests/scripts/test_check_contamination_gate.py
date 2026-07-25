"""Contamination gate (SO-METHOD-MECH) — real RED and GREEN cases.

Builds a real ``battery_raw.jsonl`` and a real SQLite event ledger (via the
project's own ``SQLiteLedger`` -- the actual artifact
``run_ogate_objectives_battery.py`` writes to) for every case, and drives the
real ``scripts.check_contamination_gate.main`` entrypoint end to end. Every
RED case is a seeded fixture proving the gate actually fires -- not merely
inspecting the pure-function return values in isolation -- and the retry
-residue GREEN case pins the 2026-07-25 lesson this gate exists to encode:
gate on completed rows in ``battery_raw.jsonl``, never on raw
``match_started`` counts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.check_contamination_gate import (
    check_seed_coverage,
    load_battery_rows,
    main,
)
from steel_onslaught.events.envelope import ModelSOEventSubject, SOEventType, make_event
from tests.sqlite_ledger import open_sqlite_ledger

pytestmark = pytest.mark.integration

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _event_id(n: int) -> str:
    return f"{n:026d}"  # 26-char ULID-shaped id; uniqueness only


def _write_battery_raw(state_root: Path, rows: list[dict[str, object]]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / "battery_raw.jsonl"
    with path.open("w", encoding="utf-8") as sink:
        for row in rows:
            sink.write(json.dumps(row, sort_keys=True) + "\n")


def _row(seed: int, match_id: str) -> dict[str, object]:
    return {"seed": seed, "match_id": match_id, "duration_ticks": 10}


def _build_ledger(
    state_root: Path,
    *,
    started_match_ids: list[str],
    ended_match_ids: list[str],
) -> None:
    """A real events.sqlite3 with a match_started for every id in
    ``started_match_ids`` and a match_ended for every id in
    ``ended_match_ids`` (independently -- callers can create orphans in
    either direction on purpose).
    """
    state_root.mkdir(parents=True, exist_ok=True)
    ledger = open_sqlite_ledger(state_root / "events.sqlite3")
    counter = 0
    for match_id in started_match_ids:
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
                event_id=_event_id(counter),
                message_id=uuid4(),
                emitted_at=_BASE_TIME + timedelta(seconds=counter),
            )
        )
        counter += 1
    for match_id in ended_match_ids:
        ledger.append(
            make_event(
                match_id=match_id,
                tick=1,
                sequence_in_tick=0,
                event_type=SOEventType.MATCH_ENDED,
                producer_node="node.test",
                subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
                payload={},
                correlation_id=uuid4(),
                causation_id=None,
                event_id=_event_id(counter),
                message_id=uuid4(),
                emitted_at=_BASE_TIME + timedelta(seconds=counter),
            )
        )
        counter += 1


def _clean_lane(state_root: Path, *, seed_base: int, n: int, extra_started: int = 0) -> None:
    """A fully clean n-row battery: each expected seed exactly once, ledger
    match_ended set exactly equal to battery_raw's match_id set.
    ``extra_started`` adds N additional match_started-only (orphaned retry
    residue) events with no corresponding row or match_ended.
    """
    seeds = [seed_base + i for i in range(1, n + 1)]
    match_ids = [f"match.fixture.{seed}" for seed in seeds]
    _write_battery_raw(
        state_root, [_row(seed, mid) for seed, mid in zip(seeds, match_ids, strict=True)]
    )
    orphan_ids = [f"match.orphan.{i}" for i in range(extra_started)]
    _build_ledger(
        state_root,
        started_match_ids=match_ids + orphan_ids,
        ended_match_ids=match_ids,
    )


# --------------------------------------------------------------------------
# Pure-function unit coverage
# --------------------------------------------------------------------------


def test_check_seed_coverage_clean() -> None:
    from scripts.check_contamination_gate import BatteryRow

    rows = [BatteryRow(seed=s, match_id=f"m{s}") for s in range(101, 104)]
    result = check_seed_coverage(rows, seed_base=100, n=3)
    assert result.clean
    assert result.missing == frozenset()
    assert result.duplicates == frozenset()
    assert result.out_of_range == frozenset()


def test_check_seed_coverage_detects_duplicate_missing_and_out_of_range() -> None:
    from scripts.check_contamination_gate import BatteryRow

    # expected {101, 102, 103}; actual has 101 twice, 103 missing, 999 extra
    rows = [
        BatteryRow(seed=101, match_id="m101a"),
        BatteryRow(seed=101, match_id="m101b"),
        BatteryRow(seed=102, match_id="m102"),
        BatteryRow(seed=999, match_id="m999"),
    ]
    result = check_seed_coverage(rows, seed_base=100, n=3)
    assert not result.clean
    assert result.duplicates == frozenset({101})
    assert result.missing == frozenset({103})
    assert result.out_of_range == frozenset({999})


def test_load_battery_rows_missing_file_fails_closed(tmp_path: Path) -> None:
    from scripts.check_contamination_gate import ContaminationCheckError

    with pytest.raises(ContaminationCheckError):
        load_battery_rows(tmp_path / "battery_raw.jsonl")


def test_load_battery_rows_invalid_json_fails_closed(tmp_path: Path) -> None:
    from scripts.check_contamination_gate import ContaminationCheckError

    path = tmp_path / "battery_raw.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ContaminationCheckError):
        load_battery_rows(path)


# --------------------------------------------------------------------------
# main() — GREEN cases
# --------------------------------------------------------------------------


def test_main_passes_on_a_clean_battery(tmp_path: Path) -> None:
    state_root = tmp_path / "lane"
    _clean_lane(state_root, seed_base=5000, n=5)
    exit_code = main(["--state-root", str(state_root), "--n", "5", "--seed-base", "5000"])
    assert exit_code == 0


def test_main_passes_with_orphaned_match_started_retry_residue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The load-bearing 2026-07-25 lesson: a lane like composition_ca_only_dmg16
    has MORE match_started events than completed rows (in-process retries
    that never reached match_ended). That must be reported as INFO, not fail
    the gate -- gate on battery_raw.jsonl's completed rows, not raw
    match_started counts.
    """
    state_root = tmp_path / "lane"
    _clean_lane(state_root, seed_base=5000, n=5, extra_started=4)
    exit_code = main(["--state-root", str(state_root), "--n", "5", "--seed-base", "5000"])
    out = capsys.readouterr().out
    assert exit_code == 0, out
    assert "INFO" in out
    assert "match.orphan." in out


# --------------------------------------------------------------------------
# main() — RED / seeded-contamination cases
# --------------------------------------------------------------------------


def test_main_fails_on_missing_seed_gap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Seeded RED: one expected seed's row never landed (a gap)."""
    state_root = tmp_path / "lane"
    seeds = [5001, 5002, 5004, 5005, 5006]  # 5003 missing; n=6 expected (5001..5006)
    match_ids = [f"match.fixture.{seed}" for seed in seeds]
    _write_battery_raw(
        state_root, [_row(seed, mid) for seed, mid in zip(seeds, match_ids, strict=True)]
    )
    _build_ledger(state_root, started_match_ids=match_ids, ended_match_ids=match_ids)

    exit_code = main(["--state-root", str(state_root), "--n", "6", "--seed-base", "5000"])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "CONTAMINATION GATE FAILED" in err


def test_main_fails_on_duplicate_seed(tmp_path: Path) -> None:
    """Seeded RED: the same seed appears twice in battery_raw.jsonl."""
    state_root = tmp_path / "lane"
    rows = [
        _row(5001, "match.a"),
        _row(5001, "match.b"),  # duplicate seed, distinct match_id
        _row(5002, "match.c"),
    ]
    _write_battery_raw(state_root, rows)
    _build_ledger(
        state_root,
        started_match_ids=["match.a", "match.b", "match.c"],
        ended_match_ids=["match.a", "match.b", "match.c"],
    )
    exit_code = main(["--state-root", str(state_root), "--n", "2", "--seed-base", "5000"])
    assert exit_code == 1


def test_main_fails_when_ledger_completed_match_has_no_battery_raw_row(tmp_path: Path) -> None:
    """Seeded RED: the ledger shows a completed (match_ended) match that never
    produced a battery_raw.jsonl row -- a row was lost after the match
    finished.
    """
    state_root = tmp_path / "lane"
    match_ids = [f"match.fixture.{seed}" for seed in (5001, 5002, 5003)]
    _write_battery_raw(
        state_root,
        [_row(seed, mid) for seed, mid in zip((5001, 5002, 5003), match_ids, strict=True)],
    )
    # Ledger completed a 4th match that has no corresponding evidence row.
    _build_ledger(
        state_root,
        started_match_ids=[*match_ids, "match.lost"],
        ended_match_ids=[*match_ids, "match.lost"],
    )
    exit_code = main(["--state-root", str(state_root), "--n", "3", "--seed-base", "5000"])
    assert exit_code == 1


def test_main_fails_when_battery_raw_row_has_no_ledger_completion(tmp_path: Path) -> None:
    """Seeded RED: a battery_raw.jsonl row whose match_id was never actually
    completed in the ledger -- a fabricated, hand-edited, or cross-lane-
    copied row.
    """
    state_root = tmp_path / "lane"
    real_ids = [f"match.fixture.{seed}" for seed in (5001, 5002)]
    _write_battery_raw(
        state_root,
        [
            _row(5001, real_ids[0]),
            _row(5002, real_ids[1]),
            _row(5003, "match.fabricated"),
        ],
    )
    # Ledger only ever completed the first two matches.
    _build_ledger(state_root, started_match_ids=real_ids, ended_match_ids=real_ids)
    exit_code = main(["--state-root", str(state_root), "--n", "3", "--seed-base", "5000"])
    assert exit_code == 1


def test_main_fails_closed_on_missing_battery_raw(tmp_path: Path) -> None:
    state_root = tmp_path / "lane"
    state_root.mkdir(parents=True)
    (state_root / "events.sqlite3").touch()
    exit_code = main(["--state-root", str(state_root), "--n", "3", "--seed-base", "5000"])
    assert exit_code == 1


def test_main_fails_closed_on_missing_events_ledger(tmp_path: Path) -> None:
    state_root = tmp_path / "lane"
    state_root.mkdir(parents=True)
    _write_battery_raw(state_root, [_row(5001, "match.a")])
    exit_code = main(["--state-root", str(state_root), "--n", "1", "--seed-base", "5000"])
    assert exit_code == 1
