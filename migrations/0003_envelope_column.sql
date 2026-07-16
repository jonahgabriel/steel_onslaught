-- Migration 0003: add the canonical ModelSOEventEnvelope JSON column.
-- New writes persist the complete Steel event, including its nested ONEX
-- ModelEnvelope, and must never write NULL. Existing rows with NULL are
-- rejected by adapter initialization and require an explicit offline migration.
--
-- NOTE: SQLite's ALTER TABLE ADD COLUMN has no IF NOT EXISTS clause, so
-- migrate.py checks the table schema before applying this statement.
ALTER TABLE events ADD COLUMN envelope_json TEXT;

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
