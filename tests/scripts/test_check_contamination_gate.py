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

The third-orphan-class cases below (OMN-15377) are modeled on the real
2026-07-29 OMN-15172 acceptance battery false positive: the ``prominent``
lane's real orphan match_ids
(``match.01KYMGQVF450DZNKH3BWJEW6HC``/seed 5018,
``match.01KYMJNP2R28BSH4ZDFEZD0PVB``/seed 5019, per the ticket and the
2026-07-29T04:22Z rolling-ledger entry) and the real ``skipped_seeds`` row
shape (``{"error": str, "seed": str}``, taken verbatim from a real
``battery_summary.json`` on this machine) are used literally. The battery's
own ``battery_raw.jsonl``/``events.sqlite3`` from that run are gitignored,
per-machine, ephemeral artifacts (see the gate's own module docstring) and
are gone from disk by the time this ticket was picked up -- the surrounding
fixture rows are therefore synthetic, built to the project's real schemas,
around those real ids/seeds.
"""

from __future__ import annotations

import json
import os
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
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from tests.sqlite_ledger import open_sqlite_ledger

pytestmark = pytest.mark.integration

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)

# Real orphan match_ids from the 2026-07-29 OMN-15172 acceptance battery
# (prominent lane) that the pre-fix gate false-positived on -- see OMN-15377.
_REAL_ORPHAN_MATCH_ID_5018 = "match.01KYMGQVF450DZNKH3BWJEW6HC"
_REAL_ORPHAN_MATCH_ID_5019 = "match.01KYMJNP2R28BSH4ZDFEZD0PVB"


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


def _append_event(
    ledger: SQLiteLedger,
    *,
    match_id: str,
    event_type: SOEventType,
    emitted_at: datetime,
    counter: int,
    seed: int | None = None,
) -> None:
    """Append a single real ledger event. ``seed`` is only meaningful on
    ``MATCH_STARTED`` -- it becomes ``payload["seed"]``, exactly like the
    real ``ModelSOMatchStartedPayload.seed`` field the runner writes."""
    payload: dict[str, object] = {"seed": seed} if seed is not None else {}
    ledger.append(
        make_event(
            match_id=match_id,
            tick=0 if event_type is SOEventType.MATCH_STARTED else 1,
            sequence_in_tick=0,
            event_type=event_type,
            producer_node="node.test",
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
            payload=payload,
            correlation_id=uuid4(),
            causation_id=None,
            event_id=_event_id(counter),
            message_id=uuid4(),
            emitted_at=emitted_at,
        )
    )


def _write_skip_artifact(path: Path, *, seeds: list[int], mtime: datetime) -> None:
    """Write a ``battery_summary*.json``-shaped skip artifact naming
    ``seeds`` in ``skipped_seeds`` (real row shape: ``{"error": str, "seed":
    str}``, per a real ``battery_summary.json`` on this machine), then pin
    its mtime so RED/GREEN cases can control whether it predates a later
    ledger event."""
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "skipped_seeds": [
            {
                "seed": str(seed),
                "error": (
                    "KafkaException: KafkaError{code=_MSG_TIMED_OUT,val=-192,"
                    'str="Local: Message timed out"} forwarding match_ended '
                    "terminal events post-match"
                ),
            }
            for seed in seeds
        ],
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


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


# --------------------------------------------------------------------------
# main() — third orphan class (OMN-15377): ledger-persisted-before-forward-
# -failure orphans, reconciled against a preserved skip record.
# --------------------------------------------------------------------------


def test_main_reconciles_ledger_persisted_forward_failed_orphans(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """RED-before-fix / GREEN-after-fix: the real 2026-07-29 OMN-15172
    ``prominent``-lane false positive (32 started / 32 ended vs 30 rows).
    Seeds 5018 and 5019 each completed and ledger-persisted (real match_ids
    match.01KYMGQVF450DZNKH3BWJEW6HC / match.01KYMJNP2R28BSH4ZDFEZD0PVB)
    before their post-match Kafka forward failed; the driver correctly
    withheld their battery_raw.jsonl rows and recorded the failure in a
    preserved skip artifact (battery_summary_main_run.json, per the real
    2026-07-29T04:22Z ledger entry); both seeds were then re-run to
    completion under fresh match_ids that DO have battery_raw rows.

    Pre-OMN-15377 the gate exits 1 on exactly this shape -- a false
    positive, discharged by hand in the real incident. Post-fix it must
    exit 0, reporting both orphans as the ``ledger_persisted_forward_failed``
    third class (INFO), never CONTAMINATION.
    """
    state_root = tmp_path / "lane"
    n = 30
    seed_base = 5000
    seeds = list(range(seed_base + 1, seed_base + n + 1))  # 5001..5030

    orphan_match_id_by_seed = {
        5018: _REAL_ORPHAN_MATCH_ID_5018,
        5019: _REAL_ORPHAN_MATCH_ID_5019,
    }
    makeup_match_id_by_seed = {
        5018: "match.01KYMK0000000000MAKEUP18",
        5019: "match.01KYMK0000000000MAKEUP19",
    }

    def raw_match_id(seed: int) -> str:
        return makeup_match_id_by_seed.get(seed, f"match.fixture.{seed}")

    _write_battery_raw(state_root, [_row(seed, raw_match_id(seed)) for seed in seeds])

    main_run_started_at = _BASE_TIME
    main_run_ended_at = main_run_started_at + timedelta(minutes=35)
    skip_artifact_written_at = main_run_ended_at + timedelta(seconds=20)
    makeup_run_started_at = main_run_started_at + timedelta(hours=12)

    ledger = open_sqlite_ledger(state_root / "events.sqlite3")
    counter = 0
    for seed in seeds:
        if seed in orphan_match_id_by_seed:
            orphan_match_id = orphan_match_id_by_seed[seed]
            _append_event(
                ledger,
                match_id=orphan_match_id,
                seed=seed,
                event_type=SOEventType.MATCH_STARTED,
                emitted_at=main_run_started_at,
                counter=counter,
            )
            counter += 1
            _append_event(
                ledger,
                match_id=orphan_match_id,
                event_type=SOEventType.MATCH_ENDED,
                emitted_at=main_run_started_at + timedelta(minutes=1),
                counter=counter,
            )
            counter += 1

            makeup_match_id = makeup_match_id_by_seed[seed]
            _append_event(
                ledger,
                match_id=makeup_match_id,
                seed=seed,
                event_type=SOEventType.MATCH_STARTED,
                emitted_at=makeup_run_started_at,
                counter=counter,
            )
            counter += 1
            _append_event(
                ledger,
                match_id=makeup_match_id,
                event_type=SOEventType.MATCH_ENDED,
                emitted_at=makeup_run_started_at + timedelta(minutes=1),
                counter=counter,
            )
            counter += 1
        else:
            match_id = raw_match_id(seed)
            _append_event(
                ledger,
                match_id=match_id,
                seed=seed,
                event_type=SOEventType.MATCH_STARTED,
                emitted_at=main_run_started_at,
                counter=counter,
            )
            counter += 1
            _append_event(
                ledger,
                match_id=match_id,
                event_type=SOEventType.MATCH_ENDED,
                emitted_at=main_run_started_at + timedelta(minutes=1),
                counter=counter,
            )
            counter += 1

    _write_skip_artifact(
        state_root / "battery_summary_main_run.json",
        seeds=[5018, 5019],
        mtime=skip_artifact_written_at,
    )

    exit_code = main(
        ["--state-root", str(state_root), "--n", str(n), "--seed-base", str(seed_base)]
    )
    out = capsys.readouterr().out
    assert exit_code == 0, out
    assert "ledger_persisted_forward_failed" in out
    assert _REAL_ORPHAN_MATCH_ID_5018 in out
    assert _REAL_ORPHAN_MATCH_ID_5019 in out
    assert "CONTAMINATION" not in out


def test_main_fails_on_orphan_seed_not_reconciled_by_any_skip_artifact(
    tmp_path: Path,
) -> None:
    """Seeded RED: an ``ended_not_in_raw`` orphan whose seed does NOT appear
    in any skip artifact under state_root -- genuine contamination, must
    stay FAIL even though an (unrelated-seed) skip artifact is present."""
    state_root = tmp_path / "lane"
    seeds = (5001, 5002, 5003)
    match_ids = [f"match.fixture.{seed}" for seed in seeds]
    _write_battery_raw(
        state_root, [_row(seed, mid) for seed, mid in zip(seeds, match_ids, strict=True)]
    )

    ledger = open_sqlite_ledger(state_root / "events.sqlite3")
    counter = 0
    for seed, match_id in zip(seeds, match_ids, strict=True):
        _append_event(
            ledger,
            match_id=match_id,
            seed=seed,
            event_type=SOEventType.MATCH_STARTED,
            emitted_at=_BASE_TIME,
            counter=counter,
        )
        counter += 1
        _append_event(
            ledger,
            match_id=match_id,
            event_type=SOEventType.MATCH_ENDED,
            emitted_at=_BASE_TIME + timedelta(minutes=1),
            counter=counter,
        )
        counter += 1

    # A genuinely lost match: completed in the ledger, no battery_raw row,
    # and its seed (9999) never appears in the skip artifact below.
    _append_event(
        ledger,
        match_id="match.lost",
        seed=9999,
        event_type=SOEventType.MATCH_STARTED,
        emitted_at=_BASE_TIME,
        counter=counter,
    )
    counter += 1
    _append_event(
        ledger,
        match_id="match.lost",
        event_type=SOEventType.MATCH_ENDED,
        emitted_at=_BASE_TIME + timedelta(minutes=1),
        counter=counter,
    )
    counter += 1

    _write_skip_artifact(
        state_root / "battery_summary_main_run.json",
        seeds=[4242],  # unrelated seed -- does not cover 9999
        mtime=_BASE_TIME - timedelta(days=1),
    )

    exit_code = main(["--state-root", str(state_root), "--n", "3", "--seed-base", "5000"])
    assert exit_code == 1


def test_main_fails_when_skip_artifact_postdates_the_makeup_run(tmp_path: Path) -> None:
    """Seeded RED: the skip artifact exists and names the orphan's seed, but
    its mtime is AFTER the makeup run's match_started -- it cannot have
    predated the recovery, so it does not prove the withheld-row story and
    the orphan stays contamination (fail-closed guard against a
    retroactively fabricated skip record laundering a real anomaly)."""
    state_root = tmp_path / "lane"
    orphan_match_id = "match.orphan.late-skip"
    makeup_match_id = "match.fixture.5001"
    _write_battery_raw(state_root, [_row(5001, makeup_match_id)])

    ledger = open_sqlite_ledger(state_root / "events.sqlite3")
    counter = 0
    _append_event(
        ledger,
        match_id=orphan_match_id,
        seed=5001,
        event_type=SOEventType.MATCH_STARTED,
        emitted_at=_BASE_TIME,
        counter=counter,
    )
    counter += 1
    _append_event(
        ledger,
        match_id=orphan_match_id,
        event_type=SOEventType.MATCH_ENDED,
        emitted_at=_BASE_TIME + timedelta(minutes=1),
        counter=counter,
    )
    counter += 1

    makeup_started_at = _BASE_TIME + timedelta(hours=1)
    _append_event(
        ledger,
        match_id=makeup_match_id,
        seed=5001,
        event_type=SOEventType.MATCH_STARTED,
        emitted_at=makeup_started_at,
        counter=counter,
    )
    counter += 1
    _append_event(
        ledger,
        match_id=makeup_match_id,
        event_type=SOEventType.MATCH_ENDED,
        emitted_at=makeup_started_at + timedelta(minutes=1),
        counter=counter,
    )
    counter += 1

    _write_skip_artifact(
        state_root / "battery_summary_main_run.json",
        seeds=[5001],
        mtime=makeup_started_at + timedelta(hours=1),  # AFTER the makeup run
    )

    exit_code = main(["--state-root", str(state_root), "--n", "1", "--seed-base", "5000"])
    assert exit_code == 1
