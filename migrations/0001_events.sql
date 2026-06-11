-- Migration 0001: events table (append-only, canonical-ordered)
-- Created by Task 6 (2026-04-30 plan)
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

-- Append-only enforcement: reject UPDATE and DELETE at the database layer.
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
