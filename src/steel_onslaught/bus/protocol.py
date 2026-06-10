"""EventBus protocol — the sole interface reducers and effects depend on."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

EventHandler = Callable[[ModelSOEventEnvelope], None]
HandlerToken = int


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

    def unsubscribe(self, token: HandlerToken) -> None:
        """Remove the handler identified by *token*.  No-op for unknown tokens."""
        ...
