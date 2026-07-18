"""Injected clock, identity, and canonical event-construction ports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    make_event,
)


class Clock(Protocol):
    """Wall-clock dependency used only for event and projection metadata."""

    def now(self) -> datetime:
        """Return one timezone-aware timestamp."""
        ...


class IdentityProvider(Protocol):
    """Match and envelope identity dependency."""

    def new_match_id(self) -> str:
        """Return a new canonical match id."""
        ...

    def new_correlation_id(self) -> UUID:
        """Return a new workflow correlation id."""
        ...

    def new_event_id(self) -> str:
        """Return a new 26-character event ULID."""
        ...

    def new_message_id(self) -> UUID:
        """Return a new ONEX message UUID."""
        ...


class EventFactory:
    """Canonical envelope factory bound to explicit clock and identity ports."""

    def __init__(self, *, clock: Clock, identities: IdentityProvider) -> None:
        self._clock = clock
        self._identities = identities

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def identities(self) -> IdentityProvider:
        return self._identities

    def make(
        self,
        *,
        match_id: str,
        tick: int,
        sequence_in_tick: int,
        event_type: SOEventType,
        producer_node: str,
        subject: ModelSOEventSubject,
        payload: dict[str, Any],
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> ModelSOEventEnvelope:
        return make_event(
            match_id=match_id,
            tick=tick,
            sequence_in_tick=sequence_in_tick,
            event_type=event_type,
            producer_node=producer_node,
            subject=subject,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            event_id=self._identities.new_event_id(),
            message_id=self._identities.new_message_id(),
            emitted_at=self._clock.now(),
        )

    def make_with_message_id(
        self,
        *,
        message_id: UUID,
        match_id: str,
        tick: int,
        sequence_in_tick: int,
        event_type: SOEventType,
        producer_node: str,
        subject: ModelSOEventSubject,
        payload: dict[str, Any],
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> ModelSOEventEnvelope:
        """Build an event with a caller-allocated canonical message UUID.

        Pure event-spec adapters allocate a complete causal UUID chain before
        publication.  This effect-boundary helper preserves those IDs while
        keeping event ULIDs and timestamps owned by the injected factory.
        """

        if not isinstance(message_id, UUID):
            raise TypeError("message_id must be a UUID")
        return make_event(
            match_id=match_id,
            tick=tick,
            sequence_in_tick=sequence_in_tick,
            event_type=event_type,
            producer_node=producer_node,
            subject=subject,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            event_id=self._identities.new_event_id(),
            message_id=message_id,
            emitted_at=self._clock.now(),
        )

    def caused_by(
        self,
        parent: ModelSOEventEnvelope,
        *,
        match_id: str,
        tick: int,
        sequence_in_tick: int,
        event_type: SOEventType,
        producer_node: str,
        subject: ModelSOEventSubject,
        payload: dict[str, Any],
    ) -> ModelSOEventEnvelope:
        return self.make(
            match_id=match_id,
            tick=tick,
            sequence_in_tick=sequence_in_tick,
            event_type=event_type,
            producer_node=producer_node,
            subject=subject,
            payload=payload,
            correlation_id=parent.correlation_id,
            causation_id=parent.envelope.message_id,
        )


__all__ = ["Clock", "EventFactory", "IdentityProvider"]
