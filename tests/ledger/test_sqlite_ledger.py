"""Tests for the append-only SQLite event ledger (Task 6)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.ledger.migrate import run_migrations
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger

# 26-character ULID-shaped IDs used across all tests
_EID1 = "01JABCDE0123456789ABCDEF01"
_EID2 = "01JABCDE0123456789ABCDEF02"
_EID3 = "01JABCDE0123456789ABCDEF03"
_EID4 = "01JABCDE0123456789ABCDEF04"
_EID5 = "01JABCDE0123456789ABCDEF05"


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
        emitted_at="2026-04-30T16:00:00Z",
    )


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
            emitted_at="2026-04-30T16:00:00Z",
        )
    )

    results = list(ledger.read_all("match.test.001"))
    assert len(results) == 1
    assert results[0].event_id == _EID1


@pytest.mark.unit
def test_correlation_and_causation_preserved(tmp_path: Path) -> None:
    """append/read preserves optional correlation_id and causation_id fields."""
    ledger = SQLiteLedger(tmp_path / "test.sqlite")
    env = ModelSOEventEnvelope(
        event_id=_EID1,
        match_id="match.test.001",
        tick=0,
        sequence_in_tick=0,
        event_type=SOEventType.PILOT_DECISION_MADE,
        correlation_id="corr.abc",
        causation_id="evt.prev",
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.1"),
        payload={},
        emitted_at="2026-04-30T16:00:00Z",
    )
    ledger.append(env)
    result = next(iter(ledger.read_all("match.test.001")))
    assert result.correlation_id == "corr.abc"
    assert result.causation_id == "evt.prev"


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
