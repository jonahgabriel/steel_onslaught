"""Typed evaluation-evidence allocation ports and SQLite filesystem adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol

from steel_onslaught.contracts.application import ModelSOSQLiteEvaluationStorageBinding
from steel_onslaught.match.duel import ModelSOEvaluationStorageKey


@dataclass(frozen=True)
class EvaluationStorageClaim:
    """Exclusively claimed SQLite evidence target plus its selected policies."""

    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    event_schema: Literal["canonical_event_v1"]
    leaderboard_schema: Literal["leaderboard_v1"]


class EvaluationStorageAllocator(Protocol):
    """Resolve a logical duel key to one never-before-used evidence target."""

    def claim(self, storage: ModelSOEvaluationStorageKey) -> EvaluationStorageClaim: ...


class SQLiteEvaluationStorageAllocator:
    """Atomically claim SQLite evidence files beneath an operator-selected root."""

    def __init__(self, binding: ModelSOSQLiteEvaluationStorageBinding) -> None:
        self._binding = binding
        self._namespace_roots: dict[str, Path] = {}
        self._lock = Lock()

    def claim(self, storage: ModelSOEvaluationStorageKey) -> EvaluationStorageClaim:
        """Claim one empty database with exclusive-create, never an existence check."""
        with self._lock:
            owned_root = self._namespace_roots.get(storage.namespace)
            if owned_root is not None:
                path = owned_root / f"{storage.duel}.sqlite3"
                self._claim_exact_file(path)
                return self._claim(path)

            base = self._binding.root / storage.namespace
            suffix = 1
            while True:
                candidate = base if suffix == 1 else base.with_name(f"{base.name}_{suffix:04d}")
                try:
                    candidate.mkdir(parents=True, exist_ok=False)
                except FileExistsError:
                    if candidate.is_symlink() or not candidate.is_dir():
                        suffix += 1
                        continue

                path = candidate / f"{storage.duel}.sqlite3"
                try:
                    self._claim_exact_file(path)
                except FileExistsError:
                    suffix += 1
                    continue
                self._namespace_roots[storage.namespace] = candidate
                return self._claim(path)

    @staticmethod
    def _claim_exact_file(path: Path) -> None:
        """Create an empty SQLite target atomically; an existing path always wins."""
        with path.open("xb"):
            pass

    def _claim(self, path: Path) -> EvaluationStorageClaim:
        return EvaluationStorageClaim(
            path=path,
            journal_mode=self._binding.journal_mode,
            check_same_thread=self._binding.check_same_thread,
            transaction_mode=self._binding.transaction_mode,
            event_schema=self._binding.event_schema,
            leaderboard_schema=self._binding.leaderboard_schema,
        )


__all__ = [
    "EvaluationStorageAllocator",
    "EvaluationStorageClaim",
    "SQLiteEvaluationStorageAllocator",
]
