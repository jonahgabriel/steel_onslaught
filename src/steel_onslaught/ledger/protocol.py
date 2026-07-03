"""Storage-neutral event-ledger ports.

Every adapter persists and returns the same canonical
``ModelSOEventEnvelope``. Physical database layout is an adapter concern; it
must never introduce a second event protocol.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType


class EventLedger(Protocol):
    """Append and replay the canonical Steel event stream."""

    def append(self, event: ModelSOEventEnvelope) -> None:
        """Durably append one canonical event."""
        ...

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        """Read one match in canonical event order."""
        ...

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        """Read canonical events whose tick is greater than ``after_tick``."""
        ...


class ReplayEventCatalog(Protocol):
    """Read-only catalog used to source one or every recorded match."""

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        """Read one match in canonical event order."""
        ...

    def read_match_ids(self) -> Iterator[str]:
        """Read every recorded match identifier in deterministic order."""
        ...


class QueryableEventLedger(EventLedger, ReplayEventCatalog, Protocol):
    """Separate read capability needed by replay HTTP projections."""

    def contains_match(self, match_id: str) -> bool:
        """Return whether at least one event exists for ``match_id``."""
        ...

    def read_at(
        self,
        match_id: str,
        tick: int,
        *,
        event_types: frozenset[SOEventType] | None,
    ) -> Iterator[ModelSOEventEnvelope]:
        """Read a canonical tick, optionally restricted to event types."""
        ...


__all__ = ["EventLedger", "QueryableEventLedger", "ReplayEventCatalog"]
