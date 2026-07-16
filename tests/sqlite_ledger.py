"""Explicit SQLite adapter composition for tests."""

from pathlib import Path

from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger


def open_sqlite_ledger(path: Path) -> SQLiteLedger:
    return SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=path,
            journal_mode="WAL",
            check_same_thread=True,
            transaction_mode="autocommit",
            event_schema="canonical_event_v1",
        )
    )


def open_cross_thread_sqlite_ledger(path: Path) -> SQLiteLedger:
    """Compose the explicitly cross-thread test adapter used by HTTP servers."""
    return SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=path,
            journal_mode="WAL",
            check_same_thread=False,
            transaction_mode="autocommit",
            event_schema="canonical_event_v1",
        )
    )
