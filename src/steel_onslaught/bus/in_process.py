"""In-process synchronous EventBus implementation."""

from __future__ import annotations

from dataclasses import dataclass, field

from steel_onslaught.bus.protocol import AdmissionObserver, EventHandler, HandlerToken
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType


@dataclass
class _Subscription:
    token: HandlerToken
    handler: EventHandler
    event_types: frozenset[SOEventType] | None  # None = wildcard (all events)
    admission: bool = False  # refusal voids the publish tree's durability


@dataclass
class InProcessEventBus:
    """Synchronous, in-process publish/subscribe bus.

    Ordering authority
    ------------------
    The bus is the sole authority for ``sequence_in_tick``.  Every published
    envelope has its ``sequence_in_tick`` (and ``tick``) overwritten with the
    bus-managed values before delivery to subscribers — the producer-supplied
    values are ignored.

    Tick boundary
    -------------
    When a ``MATCH_TICK`` event is published the bus advances ``current_tick``
    to ``event.tick`` and resets the per-tick sequence counter to 0.  All
    subsequent events — including the ``MATCH_TICK`` itself — are stamped with
    the new tick.

    Error isolation
    ---------------
    If one or more subscribers raise, the bus collects all exceptions and
    re-raises them as a single ``ExceptionGroup`` *after* every subscriber has
    been given a chance to run.

    Admission-scoped durability (OMN-15490)
    ---------------------------------------
    Exactly one canonical-admission verdict is reported per published event,
    after its dispatch finishes, to every observer registered through
    ``enlist_admission_observer``.  The verdict is REFUSED when a subscriber
    registered through ``subscribe_admission`` — the canonical-state fold —
    raised while handling it, and ADMITTED otherwise (including when no
    admission subscriber exists, so an observer can never wait forever).

    That verdict is what lets the ledger facade withhold an event it must not
    persist.  Dispatch order is untouched: the ledger stays the first
    subscriber so later subscribers of the same event still read their own
    writes.  Previously ``append`` autocommitted while the fold ran later in
    the same dispatch, so a ``ReducerError`` during fold admission arrived
    AFTER the event was durably committed — permanent, because the events table
    refuses UPDATE/DELETE and the ledger protocol has no retract.

    Only an ADMISSION failure produces a REFUSED verdict.  A downstream failure
    (scoring, projection, learning) still surfaces as an ``ExceptionGroup`` but
    leaves the canonical events durable: the match happened, and discarding its
    ledger because a learning-lane battery failed would destroy match truth over
    a non-match fact.
    """

    _subs: list[_Subscription] = field(default_factory=list)
    _admission_observers: list[AdmissionObserver] = field(default_factory=list)
    _next_token: HandlerToken = field(default=0)
    _current_tick: int = field(default=0)
    _next_seq_in_tick: int = field(default=0)  # resets each tick boundary

    def publish(self, event: ModelSOEventEnvelope) -> None:
        # Tick boundary: MATCH_TICK advances current_tick and resets sequence.
        if event.event_type == SOEventType.MATCH_TICK:
            if event.tick <= self._current_tick:
                raise ValueError(
                    "MATCH_TICK must advance the bus tick: "
                    f"current_tick={self._current_tick}, received={event.tick}"
                )
            self._current_tick = event.tick
            self._next_seq_in_tick = 0

        # Re-issue the envelope with bus-managed tick + sequence so producers
        # cannot fabricate canonical ordering.
        sequenced = event.model_copy(
            update={
                "tick": self._current_tick,
                "sequence_in_tick": self._next_seq_in_tick,
            }
        )
        self._next_seq_in_tick += 1

        errors: list[Exception] = []
        refused = False
        # Snapshot the subscriber list so unsubscribe during dispatch is safe.
        for sub in list(self._subs):
            if sub.event_types is None or sequenced.event_type in sub.event_types:
                try:
                    sub.handler(sequenced)
                except Exception as exc:
                    errors.append(exc)
                    # An admission subscriber raising is a REFUSAL of this
                    # event.  An ExceptionGroup here never is: this bus is the
                    # only producer of one, so it can only have propagated up
                    # from a NESTED publish, where it was already classified
                    # against the event it actually concerned.  Re-reading it
                    # as a refusal of the parent would let a downstream
                    # learning failure erase admitted match truth.
                    if sub.admission and not isinstance(exc, ExceptionGroup):
                        refused = True

        for observer in list(self._admission_observers):
            try:
                if refused:
                    observer.on_event_refused(sequenced)
                else:
                    observer.on_event_admitted(sequenced)
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise ExceptionGroup("subscriber errors", errors)

    def subscribe(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> HandlerToken:
        return self._register(handler, event_types, admission=False)

    def subscribe_admission(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> HandlerToken:
        """Register the canonical-admission subscriber (the match-state fold).

        Dispatch position is unchanged — an admission subscriber runs in
        registration order like any other.  What the flag adds is authority: if
        this handler raises, the event is reported REFUSED to every admission
        observer, which is what keeps it out of durable storage.
        """
        return self._register(handler, event_types, admission=True)

    def enlist_admission_observer(self, observer: AdmissionObserver) -> None:
        """Receive the canonical-admission verdict for every published event."""
        self._admission_observers.append(observer)

    def _register(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None,
        *,
        admission: bool,
    ) -> HandlerToken:
        token = self._next_token
        self._next_token += 1
        self._subs.append(
            _Subscription(
                token=token,
                handler=handler,
                event_types=frozenset(event_types) if event_types is not None else None,
                admission=admission,
            )
        )
        return token

    def unsubscribe(self, token: HandlerToken) -> None:
        self._subs = [s for s in self._subs if s.token != token]
