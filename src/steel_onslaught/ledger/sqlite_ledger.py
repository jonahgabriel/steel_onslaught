"""Append-only SQLite event ledger for Steel Onslaught.

Provides ``SQLiteLedger``, the sole write path for match events.
The public API is intentionally restricted to ``append``, ``read_all``,
and ``read_after`` — there is no ``update``, ``delete``, ``truncate``,
``clear``, or ``reset`` method. Append-only enforcement is duplicated at
the database layer via BEFORE UPDATE / BEFORE DELETE triggers (migration
0001_events.sql) so that even raw SQL connections cannot mutate history.

Canonical replay ordering is ``(tick ASC, sequence_in_tick ASC, event_id ASC)``.
``emitted_at`` is stored as metadata but MUST NOT be used for ordering.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.ledger.migrate import run_migrations

_INSERT_SQL = """
INSERT INTO events
    (event_id, match_id, tick, sequence_in_tick, event_type,
     correlation_id, causation_id, producer_node,
     subject_json, payload_json, emitted_at, schema_version)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_ALL_SQL = """
SELECT event_id, match_id, tick, sequence_in_tick, event_type,
       correlation_id, causation_id, producer_node,
       subject_json, payload_json, emitted_at, schema_version
  FROM events
 WHERE match_id = ?
 ORDER BY tick ASC, sequence_in_tick ASC, event_id ASC
"""

_SELECT_AFTER_SQL = """
SELECT event_id, match_id, tick, sequence_in_tick, event_type,
       correlation_id, causation_id, producer_node,
       subject_json, payload_json, emitted_at, schema_version
  FROM events
 WHERE match_id = ?
   AND tick > ?
 ORDER BY tick ASC, sequence_in_tick ASC, event_id ASC
"""


def _row_to_envelope(row: tuple[object, ...]) -> ModelSOEventEnvelope:
    (
        event_id,
        match_id,
        tick,
        sequence_in_tick,
        event_type,
        correlation_id,
        causation_id,
        producer_node,
        subject_json,
        payload_json,
        emitted_at,
        schema_version,
    ) = row
    subject_data = json.loads(str(subject_json))
    subject = ModelSOEventSubject(
        mech_id=subject_data["mech_id"],
        player_id=subject_data["player_id"],
    )
    return ModelSOEventEnvelope(
        event_id=str(event_id),
        match_id=str(match_id),
        tick=int(str(tick)),
        sequence_in_tick=int(str(sequence_in_tick)),
        event_type=SOEventType(str(event_type)),
        correlation_id=str(correlation_id) if correlation_id is not None else None,
        causation_id=str(causation_id) if causation_id is not None else None,
        producer_node=str(producer_node),
        subject=subject,
        payload=json.loads(str(payload_json)),
        emitted_at=str(emitted_at),
        schema_version=str(schema_version),
    )


class SQLiteLedger:
    """Append-only SQLite-backed event ledger.

    All writes go through ``append``; there is intentionally no ``update``,
    ``delete``, ``truncate``, ``clear``, or ``reset`` method.  The database
    triggers enforce the same invariant at the SQL layer.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        run_migrations(self._conn)

    def append(self, env: ModelSOEventEnvelope) -> None:
        """Insert *env* as a new row.  Raises ``sqlite3.IntegrityError`` on
        duplicate ``event_id`` or duplicate ``(match_id, tick, sequence_in_tick)``."""
        self._conn.execute(
            _INSERT_SQL,
            (
                env.event_id,
                env.match_id,
                env.tick,
                env.sequence_in_tick,
                env.event_type.value,
                env.correlation_id,
                env.causation_id,
                env.producer_node,
                env.subject.model_dump_json(),
                json.dumps(env.payload),
                env.emitted_at,
                env.schema_version,
            ),
        )
        self._conn.commit()

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        """Yield all events for *match_id* in canonical order
        ``(tick ASC, sequence_in_tick ASC, event_id ASC)``."""
        cursor = self._conn.execute(_SELECT_ALL_SQL, (match_id,))
        for row in cursor:
            yield _row_to_envelope(row)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        """Yield events for *match_id* with ``tick > after_tick`` in canonical order."""
        cursor = self._conn.execute(_SELECT_AFTER_SQL, (match_id, after_tick))
        for row in cursor:
            yield _row_to_envelope(row)
