"""Admission-scoped ledger facade — OMN-15490 AC1.

Withholds an event from durable storage until the canonical-state fold has
admitted it, WITHOUT changing dispatch order and WITHOUT holding a storage
transaction open across foreign writers.

The problem
-----------
``composition`` subscribes ``ledger.append`` before the runner subscribes
``fold.handle``; ``InProcessEventBus.publish`` runs every subscriber before
raising the collected ``ExceptionGroup``; ``SQLiteLedger.append`` autocommits.
So a ``ReducerError`` raised by the fold arrives AFTER the event is durably
committed.  The events table refuses UPDATE and DELETE at the storage layer and
the ledger protocol exposes no retract, so that row is permanent: an event
canonical state rejected sits in the canonical log forever.

Why not simply move ``append`` after the fold
---------------------------------------------
Because ledger-first is load-bearing.  Subscribers that run later read the
ledger DURING dispatch and must see their own event: the scoring reducer's
replay-validity check and the learning after-match handler both project from
``read_all`` inside the delivery.  A missing event does not merely fail — the
after-match projection derives ``event_counts`` from the stream, so it would
silently record the wrong evidence.

Why not a storage transaction over the publish tree
---------------------------------------------------
Tried and rejected: holding the ledger's write transaction open for the whole
tree blocks the leaderboard projection, which writes from inside the same tree
on a different connection (``sqlite3.OperationalError: database is locked``).
Durability must not be bought with a lock spanning other participants' writes.

The mechanism
-------------
``append`` stages the event in a pending buffer instead of writing it, and
every read merges the pending buffer with durable storage in canonical order —
so a subscriber still reads its own writes.  The bus reports the admission
verdict for each event once its dispatch finishes:

* admitted -> mark it, then flush the longest fully-admitted PREFIX of the
  buffer.  Because a parent is staged before the children it publishes, and is
  only admitted after their subtrees complete, the prefix rule writes parents
  before children, preserving the exact insertion order the previous
  ledger-first registration produced.
* refused  -> drop that event and everything staged after it (its own derived
  events).  Events admitted BEFORE it are untouched, so a refusal costs exactly
  the failing event and its consequences.

Every write reaching real storage has therefore already been admitted, and the
writes happen in autocommit bursts, holding no lock across another writer.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.protocol import QueryableEventLedger


@dataclass
class _Staged:
    event: ModelSOEventEnvelope
    admitted: bool = False


def _canonical(events: Iterable[ModelSOEventEnvelope]) -> list[ModelSOEventEnvelope]:
    """Sort by the ledger's canonical read order (tick, sequence, event id)."""
    return sorted(events, key=lambda event: (event.tick, event.sequence_in_tick, event.event_id))


@dataclass
class AdmissionScopedLedger:
    """``QueryableEventLedger`` facade that defers writes until admission.

    Wrap the real ledger once at composition time and use the wrapper for BOTH
    the bus subscription and every in-process reader, so readers see staged
    events.  Readers on another connection see a tick appear atomically.
    """

    _ledger: QueryableEventLedger
    _pending: list[_Staged] = field(default_factory=list)

    @property
    def durable_ledger(self) -> QueryableEventLedger:
        """The wrapped port.  Reads it directly and you bypass staging."""
        return self._ledger

    # ------------------------------------------------------------------
    # Bus surfaces
    # ------------------------------------------------------------------

    def append(self, event: ModelSOEventEnvelope) -> None:
        """Stage one event.  Subscribe this in the ledger's usual first slot."""
        self._pending.append(_Staged(event=event))

    def on_event_admitted(self, event: ModelSOEventEnvelope) -> None:
        """Canonical state accepted *event*; flush everything now admissible."""
        for staged in reversed(self._pending):
            # Identity, not event_id: the bus hands the same envelope object to
            # the subscriber and to this callback, so this cannot mis-resolve
            # even if a producer reused an id.
            if staged.event is event:
                staged.admitted = True
                break
        self._flush_admitted_prefix()

    def on_event_refused(self, event: ModelSOEventEnvelope) -> None:
        """Canonical state rejected *event*; drop it and everything it caused."""
        for index, staged in enumerate(self._pending):
            if staged.event is event:
                del self._pending[index:]
                return

    def _flush_admitted_prefix(self) -> None:
        flushed = 0
        for staged in self._pending:
            if not staged.admitted:
                break
            self._ledger.append(staged.event)
            flushed += 1
        if flushed:
            del self._pending[:flushed]

    @property
    def pending_events(self) -> tuple[ModelSOEventEnvelope, ...]:
        """Staged-but-not-yet-durable events, in staging order (diagnostics)."""
        return tuple(staged.event for staged in self._pending)

    # ------------------------------------------------------------------
    # QueryableEventLedger — durable rows merged with the pending buffer
    # ------------------------------------------------------------------

    def _staged_for(self, match_id: str) -> list[ModelSOEventEnvelope]:
        return [s.event for s in self._pending if s.event.match_id == match_id]

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return iter(_canonical([*self._ledger.read_all(match_id), *self._staged_for(match_id)]))

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        staged = [event for event in self._staged_for(match_id) if event.tick > after_tick]
        return iter(_canonical([*self._ledger.read_after(match_id, after_tick), *staged]))

    def read_match_ids(self) -> Iterator[str]:
        return iter(
            sorted({*self._ledger.read_match_ids(), *(s.event.match_id for s in self._pending)})
        )

    def contains_match(self, match_id: str) -> bool:
        return self._ledger.contains_match(match_id) or any(
            s.event.match_id == match_id for s in self._pending
        )

    def read_at(
        self,
        match_id: str,
        tick: int,
        *,
        event_types: frozenset[SOEventType] | None,
    ) -> Iterator[ModelSOEventEnvelope]:
        if event_types is not None and not event_types:
            return iter(())
        staged = [
            event
            for event in self._staged_for(match_id)
            if event.tick == tick and (event_types is None or event.event_type in event_types)
        ]
        durable = self._ledger.read_at(match_id, tick, event_types=event_types)
        return iter(_canonical([*durable, *staged]))


__all__ = ["AdmissionScopedLedger"]
