"""SQLite migration runner for the Steel Onslaught event ledger.

Migrations are applied in filename order from the migrations/ directory
relative to the project root. Each migration is idempotent (uses IF NOT EXISTS).
``ALTER TABLE ... ADD COLUMN`` statements (which SQLite lacks an IF NOT EXISTS
clause for) are guarded at apply time by checking ``pragma_table_info``.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

# Resolve the migrations directory relative to this file's package tree.
# src/steel_onslaught/ledger/migrate.py → project root is 3 levels up.
_MIGRATIONS_DIR = Path(__file__).parent.parent.parent.parent / "migrations"

# Matches "ALTER TABLE <t> ADD COLUMN <c> <type>;" — guarded, since SQLite has
# no IF NOT EXISTS clause for ADD COLUMN and re-running would error.
_ADD_COLUMN_RE = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names currently on *table*."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending SQL migrations to *conn* in filename order.

    Each migration file uses ``IF NOT EXISTS`` DDL so the operation is
    idempotent — calling this function multiple times on the same connection
    is safe and produces no duplicate objects or errors. ``ALTER TABLE ...
    ADD COLUMN`` statements are guarded (skipped if the column already exists).
    """
    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    for migration_file in migration_files:
        sql = migration_file.read_text(encoding="utf-8")
        # Split on the ADD COLUMN statements so each can be guarded; run the
        # rest as a script. This keeps idempotency without special SQL syntax.
        add_column_stmts = _ADD_COLUMN_RE.findall(sql)
        existing_add_columns = {m.group(0) for m in _ADD_COLUMN_RE.finditer(sql)}
        if not add_column_stmts:
            conn.executescript(sql)
            continue
        # Strip the ADD COLUMN lines from the script body, run the remainder,
        # then apply only the missing columns.
        stripped = _ADD_COLUMN_RE.sub("-- guarded ADD COLUMN (applied below)", sql)
        conn.executescript(stripped)
        for table, column in add_column_stmts:
            if column not in _table_columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        conn.commit()
        _ = existing_add_columns  # for clarity; the regex findall drives the loop
