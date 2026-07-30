"""EventBus protocol — the sole interface reducers and effects depend on."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

EventHandler = Callable[[ModelSOEventEnvelope], None]
HandlerToken = int


class AdmissionObserver(Protocol):
    """Learns each event's canonical-admission verdict (OMN-15490).

    The bus reports exactly one verdict per published event, once its dispatch
    has finished.  An event with no admission subscriber registered is reported
    as admitted — nothing refused it — so an observer can never strand events by
    waiting for a verdict that will not arrive.
    """

    def on_event_admitted(self, event: ModelSOEventEnvelope) -> None:
        """No admission subscriber refused *event*."""
        ...

    def on_event_refused(self, event: ModelSOEventEnvelope) -> None:
        """An admission subscriber refused *event*; it is not canonical."""
        ...


class EventBus(Protocol):
    """Synchronous publish/subscribe contract.

    The in-process implementation is the MVP default.  A Kafka adapter may
    implement this protocol post-MVP without touching reducer code.
    """

    def publish(self, event: ModelSOEventEnvelope) -> None:
        """Deliver *event* to all matching subscribers synchronously.

        The bus is the sole authority for ``sequence_in_tick``: it overwrites
        the producer-supplied value before delivery.  Raises ``ExceptionGroup``
        if one or more handlers raise; all handlers fire regardless.
        """
        ...

    def subscribe(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> HandlerToken:
        """Register *handler* and return an opaque token for later removal.

        If *event_types* is ``None`` the handler receives every event.
        """
        ...

    def subscribe_admission(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> HandlerToken:
        """Register the CANONICAL-ADMISSION subscriber — the fold (OMN-15490).

        Same dispatch position as any other subscriber; the difference is
        authority.  If an admission subscriber raises, the event is reported to
        every ``AdmissionObserver`` as REFUSED, which is what keeps it out of
        durable storage.

        Without this the ledger wrote first (it must, so later subscribers of
        the same event can read their own writes) and the fold's
        ``ReducerError`` arrived afterwards against an append-only store with no
        retract — permanent contamination.
        """
        ...

    def enlist_admission_observer(self, observer: AdmissionObserver) -> None:
        """Receive the canonical-admission verdict for every published event."""
        ...

    def unsubscribe(self, token: HandlerToken) -> None:
        """Remove the handler identified by *token*.  No-op for unknown tokens."""
        ...
