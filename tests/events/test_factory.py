"""Injected event-factory proof with no clock or identity fallbacks."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from steel_onslaught.events.envelope import ModelSOEventSubject, SOEventType
from steel_onslaught.events.factory import EventFactory

_NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
_CORRELATION = UUID("11111111-1111-1111-1111-111111111111")
_MESSAGE = UUID("22222222-2222-2222-2222-222222222222")


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Identities:
    def new_match_id(self) -> str:
        return "match.injected.001"

    def new_correlation_id(self) -> UUID:
        return _CORRELATION

    def new_event_id(self) -> str:
        return "01JABCDE0123456789ABCDEF01"

    def new_message_id(self) -> UUID:
        return _MESSAGE


@pytest.mark.unit
def test_factory_uses_only_injected_clock_and_identity_values() -> None:
    event = EventFactory(clock=_Clock(), identities=_Identities()).make(
        match_id="match.injected.001",
        tick=3,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        payload={"kind": "steel_onslaught.match_tick", "tick": 3},
        correlation_id=_CORRELATION,
    )

    assert event.event_id == "01JABCDE0123456789ABCDEF01"
    assert event.envelope.message_id == _MESSAGE
    assert event.envelope.correlation_id == _CORRELATION
    assert event.envelope.emitted_at == _NOW
    assert event.envelope.entity_id == event.match_id
