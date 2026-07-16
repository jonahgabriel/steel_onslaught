"""Tests for the append-only SQLite event ledger (Task 6)."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    legacy_identity_uuid,
)
from steel_onslaught.ledger.migrate import run_migrations
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.replay.engine import ReplayEngine

# 26-character ULID-shaped IDs used across all tests
_EID1 = "01JABCDE0123456789ABCDEF01"
_EID2 = "01JABCDE0123456789ABCDEF02"
_EID3 = "01JABCDE0123456789ABCDEF03"
_EID4 = "01JABCDE0123456789ABCDEF04"
_EID5 = "01JABCDE0123456789ABCDEF05"


def _onex_envelope(
    entity_id: str,
    emitted_at: datetime = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
) -> ModelEnvelope:
    """Composed ONEX ModelEnvelope."""
    return ModelEnvelope(
        message_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        entity_id=entity_id,
        emitted_at=emitted_at,
    )


def _make_env(
    event_id: str,
    tick: int = 0,
    sequence_in_tick: int = 0,
    event_type: SOEventType = SOEventType.PILOT_DECISION_MADE,
    match_id: str = "match.test.001",
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=event_id,
        match_id=match_id,
        tick=tick,
        sequence_in_tick=sequence_in_tick,
        event_type=event_type,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.1"),
        payload={"test": True},
        envelope=_onex_envelope(match_id),
    )


def _insert_legacy_event(
    ledger: SQLiteLedger,
    *,
    event_id: str = _EID1,
    match_id: str = "match.legacy.001",
    correlation_id: str = "match.legacy.001",
    causation_id: str = "01JABCDE0123456789ABCDEF00",
) -> None:
    """Insert one row in the schema shape that predates envelope_json."""
    ledger._conn.execute(
        """
        INSERT INTO events
            (event_id, match_id, tick, sequence_in_tick, event_type,
             correlation_id, causation_id, producer_node,
             subject_json, payload_json, emitted_at, schema_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            match_id,
            0,
            0,
            SOEventType.PILOT_DECISION_MADE.value,
            correlation_id,
            causation_id,
            "node.legacy",
            json.dumps({"mech_id": "mech.legacy", "player_id": "player.legacy"}),
            json.dumps({"action": "remain"}),
            "2026-04-30T16:00:00+00:00",
            "0.1.0",
        ),
    )
    ledger._conn.commit()


@pytest.mark.unit
def test_migrate_creates_events_table(tmp_path: Path) -> None:
    """Migrating a fresh DB creates the events table with the expected schema."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)

    cursor = conn.execute("PRAGMA table_info(events)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    assert "event_id" in columns
    assert "match_id" in columns
    assert "tick" in columns
    assert "sequence_in_tick" in columns
    assert "event_type" in columns
    assert "correlation_id" in columns
    assert "causation_id" in columns
    assert "producer_node" in columns
    assert "subject_json" in columns
    assert "payload_json" in columns
    assert "emitted_at" in columns
    assert "schema_version" in columns
    conn.close()


@pytest.mark.unit
def test_migrate_creates_append_only_triggers(tmp_path: Path) -> None:
    """Migration creates the two append-only triggers."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")
    trigger_names = {row[0] for row in cursor.fetchall()}

    assert "events_no_update" in trigger_names
    assert "events_no_delete" in trigger_names
    conn.close()


@pytest.mark.unit
def test_migrate_is_idempotent(tmp_path: Path) -> None:
    """Running migrations twice is idempotent — no errors, no duplicate objects."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    run_migrations(conn)  # second run must not raise

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    trigger_names = [row[0] for row in cursor.fetchall()]
    assert trigger_names.count("events_no_update") == 1
    assert trigger_names.count("events_no_delete") == 1
    conn.close()


@pytest.mark.unit
def test_append_and_read_all_round_trip(tmp_path: Path) -> None:
    """append() inserts one row; read_all() returns it as an equivalent envelope."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env = _make_env(_EID1)

    ledger.append(env)
    results = list(ledger.read_all("match.test.001"))

    assert len(results) == 1
    result = results[0]
    assert result.event_id == env.event_id
    assert result.match_id == env.match_id
    assert result.tick == env.tick
    assert result.sequence_in_tick == env.sequence_in_tick
    assert result.event_type == env.event_type
    assert result.producer_node == env.producer_node
    assert result.subject == env.subject
    assert result.payload == env.payload
    assert result.emitted_at == env.emitted_at
    assert result.schema_version == env.schema_version


@pytest.mark.unit
def test_append_rejects_duplicate_event_id(tmp_path: Path) -> None:
    """append() is rejected if event_id already exists (PRIMARY KEY violation)."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env = _make_env(_EID1)
    ledger.append(env)

    with pytest.raises(sqlite3.IntegrityError):
        ledger.append(env)


@pytest.mark.unit
def test_append_rejects_duplicate_tick_sequence(tmp_path: Path) -> None:
    """append() is rejected if (match_id, tick, sequence_in_tick) already exists."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env1 = _make_env(_EID1, tick=0, sequence_in_tick=0)
    env2 = _make_env(
        _EID2,  # different event_id
        tick=0,
        sequence_in_tick=0,  # same (match_id, tick, seq) — UNIQUE constraint
    )
    ledger.append(env1)

    with pytest.raises(sqlite3.IntegrityError):
        ledger.append(env2)


@pytest.mark.unit
def test_update_trigger_raises(tmp_path: Path) -> None:
    """A direct UPDATE on events raises IntegrityError with 'append-only' message."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env = _make_env(_EID1)
    ledger.append(env)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger._conn.execute("UPDATE events SET tick = 99")
        ledger._conn.commit()


@pytest.mark.unit
def test_delete_trigger_raises(tmp_path: Path) -> None:
    """A direct DELETE on events raises IntegrityError with 'append-only' message."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env = _make_env(_EID1)
    ledger.append(env)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger._conn.execute("DELETE FROM events WHERE 1=1")
        ledger._conn.commit()


@pytest.mark.unit
def test_read_all_canonical_order(tmp_path: Path) -> None:
    """read_all() returns events in (tick ASC, sequence_in_tick ASC, event_id ASC)."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")

    # Insert out of natural order to prove sorting
    envs = [
        _make_env(_EID3, tick=1, sequence_in_tick=1),
        _make_env(_EID1, tick=0, sequence_in_tick=0),
        _make_env(_EID2, tick=1, sequence_in_tick=0),
        _make_env(_EID4, tick=2, sequence_in_tick=0),
    ]
    for env in envs:
        ledger.append(env)

    results = list(ledger.read_all("match.test.001"))
    assert len(results) == 4
    assert results[0].event_id == _EID1  # tick=0, seq=0
    assert results[1].event_id == _EID2  # tick=1, seq=0
    assert results[2].event_id == _EID3  # tick=1, seq=1
    assert results[3].event_id == _EID4  # tick=2, seq=0


@pytest.mark.unit
def test_read_after_filters_by_tick(tmp_path: Path) -> None:
    """read_after(match_id, after_tick) returns only events with tick > after_tick."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")

    tick_seq_pairs = [(0, 0), (1, 0), (2, 0), (3, 0)]
    for i, (tick, seq) in enumerate(tick_seq_pairs):
        eid = f"01JABCDE0123456789ABCD{i:04d}"  # 26 chars: 22-char prefix + 4-digit suffix
        ledger.append(_make_env(eid, tick=tick, sequence_in_tick=seq))

    results = list(ledger.read_after("match.test.001", after_tick=1))
    assert len(results) == 2
    assert all(r.tick > 1 for r in results)


@pytest.mark.unit
def test_read_all_isolates_by_match_id(tmp_path: Path) -> None:
    """read_all() only returns events matching the given match_id."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")

    ledger.append(_make_env(_EID1, match_id="match.test.001"))
    ledger.append(
        ModelSOEventEnvelope(
            event_id=_EID2,
            match_id="match.test.002",
            tick=0,
            sequence_in_tick=0,
            event_type=SOEventType.PILOT_DECISION_MADE,
            producer_node="node.test",
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.1"),
            payload={},
            envelope=_onex_envelope("match.test.002"),
        )
    )

    results = list(ledger.read_all("match.test.001"))
    assert len(results) == 1
    assert results[0].event_id == _EID1


@pytest.mark.unit
def test_correlation_and_causation_preserved(tmp_path: Path) -> None:
    """append/read preserves the ONEX correlation_id and causation_id (UUIDs)."""
    corr = uuid4()
    caus = uuid4()
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env = ModelSOEventEnvelope(
        event_id=_EID1,
        match_id="match.test.001",
        tick=0,
        sequence_in_tick=0,
        event_type=SOEventType.PILOT_DECISION_MADE,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.1"),
        payload={},
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=corr,
            causation_id=caus,
            entity_id="match.test.001",
            emitted_at=datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
        ),
    )
    ledger.append(env)
    result = next(iter(ledger.read_all("match.test.001")))
    assert result.correlation_id == corr
    assert result.causation_id == caus


@pytest.mark.unit
def test_null_envelope_legacy_row_reads_and_replays_with_stable_identity(tmp_path: Path) -> None:
    """Pre-ONEX rows reconstruct identically across reads and hash-seeded processes."""
    db_path = tmp_path / "legacy.sqlite"
    match_id = "match.legacy.001"
    legacy_cause = "01JABCDE0123456789ABCDEF00"
    ledger = SQLiteLedger(db_path)
    _insert_legacy_event(ledger, match_id=match_id, causation_id=legacy_cause)

    envelope_json = ledger._conn.execute(
        "SELECT envelope_json FROM events WHERE event_id = ?", (_EID1,)
    ).fetchone()
    assert envelope_json == (None,)

    first = next(ledger.read_all(match_id))
    second = next(ledger.read_all(match_id))
    assert first.envelope == second.envelope
    assert first.envelope.message_id == legacy_identity_uuid(_EID1)
    assert first.correlation_id == legacy_identity_uuid(match_id)
    assert first.causation_id == legacy_identity_uuid(legacy_cause)

    replay = ReplayEngine(ledger, match_id)
    replayed = replay.reconstruct_at_tick(0)
    assert replayed.match_id == match_id
    assert replay.events_at_tick(0) == [first]

    script = """
import json
import sys
from pathlib import Path
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger

event = next(SQLiteLedger(Path(sys.argv[1])).read_all(sys.argv[2]))
print(json.dumps({
    "message_id": str(event.envelope.message_id),
    "correlation_id": str(event.correlation_id),
    "causation_id": str(event.causation_id),
}, sort_keys=True))
"""
    process_results: list[str] = []
    for hash_seed in ("1", "2"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = hash_seed
        result = subprocess.run(
            [sys.executable, "-c", script, str(db_path), match_id],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        process_results.append(result.stdout.strip())

    assert process_results[0] == process_results[1]
    process_identity = json.loads(process_results[0])
    assert UUID(process_identity["message_id"]) == first.envelope.message_id
    assert UUID(process_identity["correlation_id"]) == first.correlation_id
    assert UUID(process_identity["causation_id"]) == first.causation_id


@pytest.mark.unit
def test_no_mutation_api() -> None:
    """SQLiteLedger public API is frozen to the allowlist — no update/delete/truncate."""
    allowed_public_methods = frozenset({"append", "read_all", "read_after"})

    public_methods = {
        name
        for name in dir(SQLiteLedger)
        if not name.startswith("_") and callable(getattr(SQLiteLedger, name))
    }

    forbidden = public_methods - allowed_public_methods
    assert forbidden == set(), (
        f"SQLiteLedger exposes forbidden public methods: {forbidden}. "
        f"Allowed: {allowed_public_methods}"
    )
