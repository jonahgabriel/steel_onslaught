"""In-process synchronous EventBus implementation."""

from __future__ import annotations

from dataclasses import dataclass, field

from steel_onslaught.bus.protocol import EventHandler, HandlerToken
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType


@dataclass
class _Subscription:
    token: HandlerToken
    handler: EventHandler
    event_types: frozenset[SOEventType] | None  # None = wildcard (all events)


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
    """

    _subs: list[_Subscription] = field(default_factory=list)
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
        # Snapshot the subscriber list so unsubscribe during dispatch is safe.
        for sub in list(self._subs):
            if sub.event_types is None or sequenced.event_type in sub.event_types:
                try:
                    sub.handler(sequenced)
                except Exception as exc:
                    errors.append(exc)

        if errors:
            raise ExceptionGroup("subscriber errors", errors)

    def subscribe(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> HandlerToken:
        token = self._next_token
        self._next_token += 1
        self._subs.append(
            _Subscription(
                token=token,
                handler=handler,
                event_types=frozenset(event_types) if event_types is not None else None,
            )
        )
        return token

    def unsubscribe(self, token: HandlerToken) -> None:
        self._subs = [s for s in self._subs if s.token != token]
