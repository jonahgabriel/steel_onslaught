"""SQLite migration runner for the Steel Onslaught event ledger.

Migrations are applied in filename order from the migrations/ directory
relative to the project root. Each migration is idempotent (uses IF NOT EXISTS).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Resolve the migrations directory relative to this file's package tree.
# src/steel_onslaught/ledger/migrate.py → project root is 3 levels up.
_MIGRATIONS_DIR = Path(__file__).parent.parent.parent.parent / "migrations"


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending SQL migrations to *conn* in filename order.

    Each migration file uses ``IF NOT EXISTS`` DDL so the operation is
    idempotent — calling this function multiple times on the same connection
    is safe and produces no duplicate objects or errors.
    """
    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    for migration_file in migration_files:
        sql = migration_file.read_text(encoding="utf-8")
        conn.executescript(sql)
