"""Strict SQLite adapter for the canonical Steel event-ledger protocol."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.codec import (
    LegacyLedgerFormatError,
    PersistedEventFormatError,
    dump_persisted_event,
    load_persisted_event,
)
from steel_onslaught.ledger.migrate import SQLiteEventSchema, run_migrations
from steel_onslaught.ledger.protocol import QueryableEventLedger


class ModelSOSQLiteLedgerConfig(BaseModel):
    """Complete, immutable SQLite adapter configuration.

    Every operational policy is explicit. The adapter does not select a path,
    transaction mode, threading policy, journal mode, or schema on behalf of
    its caller.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    event_schema: SQLiteEventSchema


_INSERT_SQL = """
INSERT INTO events
    (event_id, match_id, tick, sequence_in_tick, event_type,
     correlation_id, causation_id, producer_node,
     subject_json, payload_json, emitted_at, schema_version,
     envelope_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_COLUMNS = """
event_id, match_id, tick, sequence_in_tick, event_type, envelope_json
"""


def _decode_row(row: tuple[object, ...]) -> ModelSOEventEnvelope:
    event_id, match_id, tick, sequence_in_tick, event_type, event_json = row
    if event_json is None:
        raise LegacyLedgerFormatError(
            f"legacy event row {event_id!r} has no canonical envelope_json; "
            "runtime migration is forbidden"
        )
    try:
        event = load_persisted_event(str(event_json))
    except PersistedEventFormatError as exc:
        raise PersistedEventFormatError(
            f"event row {event_id!r} is not a canonical persisted event: {exc}"
        ) from exc
    projection = (
        str(event_id),
        str(match_id),
        int(str(tick)),
        int(str(sequence_in_tick)),
        str(event_type),
    )
    canonical = (
        event.event_id,
        event.match_id,
        event.tick,
        event.sequence_in_tick,
        event.event_type.value,
    )
    if projection != canonical:
        raise PersistedEventFormatError(
            f"event row {event_id!r} index projection differs from canonical envelope_json"
        )
    return event


class SQLiteLedger(QueryableEventLedger):
    """Append-only SQLite implementation of the storage-neutral ledger ports."""

    def __init__(self, config: ModelSOSQLiteLedgerConfig) -> None:
        self._config = config
        self._conn = sqlite3.connect(
            config.path,
            check_same_thread=config.check_same_thread,
            isolation_level=None,
        )
        try:
            if self._conn.isolation_level is not None:
                raise RuntimeError("SQLite connection did not apply required autocommit policy")
            journal_mode = self._conn.execute(
                f"PRAGMA journal_mode={config.journal_mode}"
            ).fetchone()
            if journal_mode is None or str(journal_mode[0]).upper() != config.journal_mode:
                raise RuntimeError(
                    f"SQLite refused required journal mode {config.journal_mode!r}: "
                    f"{journal_mode!r}"
                )
            run_migrations(self._conn, schema=config.event_schema)
            self._validate_existing_rows()
        except BaseException:
            self._conn.close()
            raise

    @property
    def config(self) -> ModelSOSQLiteLedgerConfig:
        return self._config

    def _validate_existing_rows(self) -> None:
        cursor = self._conn.execute(f"SELECT {_SELECT_COLUMNS} FROM events")
        for row in cursor:
            _decode_row(row)

    def append(self, event: ModelSOEventEnvelope) -> None:
        """Append one complete canonical event and commit it immediately."""
        canonical_json = dump_persisted_event(event)
        self._conn.execute(
            _INSERT_SQL,
            (
                event.event_id,
                event.match_id,
                event.tick,
                event.sequence_in_tick,
                event.event_type.value,
                str(event.correlation_id),
                str(event.causation_id) if event.causation_id is not None else None,
                event.producer_node,
                event.subject.model_dump_json(),
                json.dumps(event.payload, separators=(",", ":"), ensure_ascii=False),
                event.emitted_at,
                event.schema_version,
                canonical_json,
            ),
        )

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        cursor = self._conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM events "
            "WHERE match_id = ? ORDER BY tick ASC, sequence_in_tick ASC, event_id ASC",
            (match_id,),
        )
        for row in cursor:
            yield _decode_row(row)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        cursor = self._conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM events "
            "WHERE match_id = ? AND tick > ? "
            "ORDER BY tick ASC, sequence_in_tick ASC, event_id ASC",
            (match_id, after_tick),
        )
        for row in cursor:
            yield _decode_row(row)

    def contains_match(self, match_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM events WHERE match_id = ? LIMIT 1", (match_id,)
        ).fetchone()
        return row is not None

    def read_at(
        self,
        match_id: str,
        tick: int,
        *,
        event_types: frozenset[SOEventType] | None,
    ) -> Iterator[ModelSOEventEnvelope]:
        params: list[object] = [match_id, tick]
        event_filter = ""
        if event_types is not None:
            if not event_types:
                return
            ordered_types = sorted(event_type.value for event_type in event_types)
            placeholders = ", ".join("?" for _ in ordered_types)
            event_filter = f" AND event_type IN ({placeholders})"
            params.extend(ordered_types)
        cursor = self._conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM events "
            f"WHERE match_id = ? AND tick = ?{event_filter} "
            "ORDER BY sequence_in_tick ASC, event_id ASC",
            params,
        )
        for row in cursor:
            yield _decode_row(row)


__all__ = ["ModelSOSQLiteLedgerConfig", "SQLiteLedger"]
