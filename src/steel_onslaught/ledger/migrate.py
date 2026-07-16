"""Deterministic SQLite schema installation for the canonical event ledger.

Schema SQL is implementation code, not discovered runtime configuration. The
adapter therefore neither scans package paths nor guesses a migration source.
The checked-in ``migrations/*.sql`` files remain the reviewable DDL record.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

SQLiteEventSchema = Literal["canonical_event_v1"]

_EVENTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id          TEXT PRIMARY KEY,
    match_id          TEXT NOT NULL,
    tick              INTEGER NOT NULL CHECK (tick >= 0),
    sequence_in_tick  INTEGER NOT NULL CHECK (sequence_in_tick >= 0),
    event_type        TEXT NOT NULL,
    correlation_id    TEXT,
    causation_id      TEXT,
    producer_node     TEXT NOT NULL,
    subject_json      TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    emitted_at        TEXT NOT NULL,
    schema_version    TEXT NOT NULL DEFAULT '0.1.0',
    UNIQUE (match_id, tick, sequence_in_tick)
);
CREATE INDEX IF NOT EXISTS idx_events_order
    ON events (match_id, tick ASC, sequence_in_tick ASC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'events table is append-only');
END;
CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'events table is append-only');
END;
"""

_CANONICAL_ENVELOPE_GUARD_SQL = """
CREATE TRIGGER IF NOT EXISTS events_require_canonical_envelope
BEFORE INSERT ON events
WHEN CASE
  WHEN NEW.envelope_json IS NULL THEN 1
  WHEN json_valid(NEW.envelope_json) = 0 THEN 1
  ELSE
    json_type(NEW.envelope_json, '$.envelope') IS NULL
    OR json_type(NEW.envelope_json, '$.envelope.message_id') IS NULL
    OR json_type(NEW.envelope_json, '$.envelope.correlation_id') IS NULL
    OR json_type(NEW.envelope_json, '$.envelope.causation_id') IS NULL
    OR json_type(NEW.envelope_json, '$.envelope.emitted_at') IS NULL
    OR json_type(NEW.envelope_json, '$.envelope.entity_id') IS NULL
    OR json_type(NEW.envelope_json, '$.schema_version') IS NULL
    OR json_type(NEW.envelope_json, '$.producer_node') IS NULL
    OR json_type(NEW.envelope_json, '$.subject') IS NOT 'object'
    OR json_type(NEW.envelope_json, '$.payload') IS NOT 'object'
    OR json_extract(NEW.envelope_json, '$.event_id') IS NOT NEW.event_id
    OR json_extract(NEW.envelope_json, '$.match_id') IS NOT NEW.match_id
    OR json_extract(NEW.envelope_json, '$.tick') IS NOT NEW.tick
    OR json_extract(NEW.envelope_json, '$.sequence_in_tick') IS NOT NEW.sequence_in_tick
    OR json_extract(NEW.envelope_json, '$.event_type') IS NOT NEW.event_type
END
BEGIN
  SELECT RAISE(ABORT, 'complete canonical envelope_json is required');
END;
"""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def run_migrations(conn: sqlite3.Connection, *, schema: SQLiteEventSchema) -> None:
    """Install exactly the explicitly selected canonical event schema."""
    if schema != "canonical_event_v1":  # defensive for untyped external callers
        raise ValueError(f"unsupported SQLite event schema: {schema!r}")
    conn.executescript(_EVENTS_SCHEMA_SQL)
    if "envelope_json" not in _table_columns(conn, "events"):
        # Nullable only for SQLite ALTER compatibility. The forward-write
        # trigger below rejects NULL, and adapter initialization rejects any
        # rows that existed before this canonical column was added.
        conn.execute("ALTER TABLE events ADD COLUMN envelope_json TEXT")
    conn.executescript(_CANONICAL_ENVELOPE_GUARD_SQL)
    conn.commit()


__all__ = ["SQLiteEventSchema", "run_migrations"]
