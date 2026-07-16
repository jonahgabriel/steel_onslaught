"""Replay engine — Tasks 27 + 34.

Reads events from an ``EventLedger`` in canonical order
``(tick ASC, sequence_in_tick ASC, event_id ASC)`` and folds them through
``MatchStateFold`` — the SAME fold the live match runner subscribes to the
bus — producing a ``ModelSOMatchState`` that is ``==`` to the live final
state by construction (R9 / Architectural Decision #6).

The fold consumes only canonical resolved events; intent / telemetry events
in the ledger pass through it as no-ops, and fold-internal emissions are
suppressed on the replay path (``bus=None``) because the live copies of those
events arrive from the ledger as idempotent re-statements.

API
---
``ReplayEngine`` is stateful: it tracks a ``_cursor_tick`` that is advanced by
``step_forward`` / ``step_backward`` and reset by ``reconstruct_at_tick``.

Usage::

    replay = ReplayEngine(ledger, match_id="match.2026-04-30.001", catalog=catalog)
    final  = replay.reconstruct_at_tick(200)   # fold through all events
    state3 = replay.reconstruct_at_tick(3)      # fold only through tick 3
    t4     = replay.step_forward()              # advance one tick
    t3_    = replay.step_backward()             # retreat one tick
"""

from __future__ import annotations

from steel_onslaught.events.envelope import ModelSOEventEnvelope
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.ledger.protocol import EventLedger
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.state import ModelSOMatchState


class ReplayEngine:
    """Reconstruct ``ModelSOMatchState`` at any tick from a ledger.

    Args:
        ledger:   Event ledger holding the target match's canonical events.
        match_id: The match identifier whose events are replayed.
        catalog:  Already resolved static contract catalog for the fold.

    The engine caches the full ordered event list on first construction to
    avoid repeated ledger scans.  The ledger is expected to be complete
    (match has ended) before replay is meaningful, though partial replays
    for running matches are supported.
    """

    def __init__(
        self,
        ledger: EventLedger,
        match_id: str,
        *,
        catalog: MatchContractCatalog,
        event_factory: EventFactory,
    ) -> None:
        self._ledger = ledger
        self._match_id = match_id
        self._catalog = catalog
        self._event_factory = event_factory
        # Cache the full canonical event list once.
        self._events: list[ModelSOEventEnvelope] = list(ledger.read_all(match_id))
        if not self._events:
            raise ValueError(f"no events for match_id={match_id!r}")
        # ONEX workflow correlation id shared across every event of this match.
        # Derived from the ledger (the replay path never emits, so the fold's
        # bus=None; correlation_id is threaded only to satisfy the factory
        # signature and stays unused on this path). All events of one match
        # share it (the runner generates one per match).
        self._correlation_id = self._events[0].correlation_id
        # Current cursor position — updated by reconstruct_at_tick / step_*.
        self._cursor_tick: int = 0

    # ------------------------------------------------------------------
    # Public API (matches the plan's spec)
    # ------------------------------------------------------------------

    def reconstruct_at_tick(self, tick: int) -> ModelSOMatchState:
        """Fold all events up to and including *tick* through the reducer stack.

        Sets the internal cursor to *tick* (clamped to [0, all_ticks()[-1]]).
        Returns the reconstructed ``ModelSOMatchState``.

        Args:
            tick: Target tick number (0 = initial state after MATCH_STARTED).

        Returns:
            ``ModelSOMatchState`` after folding all events with tick <= *tick*.
        """
        all_t = self.all_ticks()
        if not all_t:
            raise ValueError(f"no events for match_id={self._match_id!r}")
        clamped = max(all_t[0], min(tick, all_t[-1]))
        self._cursor_tick = clamped
        return self._fold_up_to(clamped)

    def step_forward(self) -> ModelSOMatchState:
        """Advance one tick and return the reconstructed state.

        Clamps at the final tick — if already at the end, returns the current
        (final) state unchanged.
        """
        all_t = self.all_ticks()
        if not all_t:
            raise ValueError(f"no events for match_id={self._match_id!r}")
        final_tick = all_t[-1]
        next_tick = min(self._cursor_tick + 1, final_tick)
        self._cursor_tick = next_tick
        return self._fold_up_to(next_tick)

    def step_backward(self) -> ModelSOMatchState:
        """Retreat one tick and return the reconstructed state.

        Clamps at tick 0 — if already at the start, returns the tick-0 state.
        """
        prev_tick = max(self._cursor_tick - 1, 0)
        self._cursor_tick = prev_tick
        return self._fold_up_to(prev_tick)

    def all_ticks(self) -> list[int]:
        """Return a sorted list of all distinct tick numbers in the ledger.

        Tick 0 is always present (MATCH_STARTED is emitted at tick 0 by
        ``InProcessEventBus`` before the first ``MATCH_TICK``).
        """
        seen: dict[int, None] = {}  # ordered-set via dict insertion order
        for e in self._events:
            seen[e.tick] = None
        return list(seen)

    def events_at_tick(self, tick: int) -> list[ModelSOEventEnvelope]:
        """Return all events for *tick* in canonical order
        ``(sequence_in_tick ASC, event_id ASC)``.

        Returns an empty list if *tick* is not present in the ledger.
        """
        at_tick = [e for e in self._events if e.tick == tick]
        return sorted(at_tick, key=lambda e: (e.sequence_in_tick, e.event_id))

    # ------------------------------------------------------------------
    # Internal fold implementation
    # ------------------------------------------------------------------

    def _fold_up_to(self, target_tick: int) -> ModelSOMatchState:
        """Fold events with tick <= *target_tick* through ``MatchStateFold``.

        A fresh fold per call keeps reconstruction stateless and exact: the
        result is a pure function of the canonical event prefix.
        """
        fold = MatchStateFold(
            self._match_id,
            self._correlation_id,
            bus=None,
            event_factory=self._event_factory,
            catalog=self._catalog,
        )
        for event in self._events:
            if event.tick > target_tick:
                break
            fold.apply(event)
        return fold.state
