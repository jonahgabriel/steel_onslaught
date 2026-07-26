"""Terminal-event Kafka-forwarding subscriber -- unit tests (OMN-15167).

Covers the seam declared in ``steel_onslaught.bus.kafka_forwarder``:

1. **4-class whitelist, full-enum enumeration.** Every ``SOEventType`` member
   is exercised (via ``tests.fixtures.event_samples.build_sample_envelopes``,
   which is asserted elsewhere -- ``tests/fixtures/test_event_samples.py`` --
   to cover exactly one sample per member). The 4 terminal members forward
   successfully; every other member is rejected with
   ``NonTerminalEventForwardedError`` and never reaches the transport. A
   future ``SOEventType`` member addition that ``build_sample_envelopes``
   does not also cover fails loudly (``KeyError`` on lookup below) -- this is
   the "forces a decision" property the ticket requires.
2. **Byte-for-byte envelope preservation.** The serialized value round-trips
   through ``ModelSOEventEnvelope.model_validate_json`` back to an object
   equal to the original -- correlation_id/causation_id/entity_id/message_id/
   emitted_at (the composed ``omnibase_core.ModelEnvelope`` fields) included.
3. **match_id keying.**  The transport receives ``key == event.match_id``.
4. **Topic literal format.**  ``STEEL_MATCH_TERMINAL_TOPIC`` matches the
   platform's ``onex.<kind>.<producer>.<event-name>.v<n>`` canonical pattern.
5. **Bus-level "never receives".**  A real ``InProcessEventBus`` subscribed
   exactly the way composition wires it
   (``bus.subscribe(forwarder.publish, event_types=TERMINAL_EVENT_TYPES)``)
   only ever calls the forwarder for the 4 terminal classes when every
   ``SOEventType`` member is published -- proving the bus-level filter, not
   just the forwarder's own defense-in-depth check.

Live Kafka publish is explicitly NOT claimed here (OMN-15170's scope) -- the
transport in every test below is a fake.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.bus.kafka_forwarder import (
    STEEL_MATCH_TERMINAL_TOPIC,
    TERMINAL_EVENT_TYPES,
    KafkaTerminalEventForwarder,
    NonTerminalEventForwardedError,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from tests.fixtures.event_samples import build_sample_envelopes

pytestmark = pytest.mark.unit

# Mirrors omnibase_core.topics._CANONICAL_TOPIC_PATTERN (studied read-only
# from the canonical omnibase_core clone at build time) -- duplicated here as
# a literal string-format assertion, not a runtime import dependency on that
# module (steel does not depend on omnibase_core.topics).
_CANONICAL_TOPIC_PATTERN = re.compile(
    r"^onex\.(cmd|evt|dlq|snapshot|intent)\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"
    r"(?:\.[a-zA-Z0-9_-]+)*\.v\d+$"
)


@dataclass
class _RecordedMessage:
    topic: str
    key: str
    value: bytes


@dataclass
class _FakeTransport:
    """The injected ``ProtocolTerminalEventTransport`` fake for these tests."""

    published: list[_RecordedMessage] = field(default_factory=list)

    def publish(self, *, topic: str, key: str, value: bytes) -> None:
        self.published.append(_RecordedMessage(topic=topic, key=key, value=value))


def test_topic_literal_matches_canonical_platform_pattern() -> None:
    assert _CANONICAL_TOPIC_PATTERN.match(STEEL_MATCH_TERMINAL_TOPIC)
    assert STEEL_MATCH_TERMINAL_TOPIC == "onex.evt.steel-onslaught.match-terminal.v1"


def test_terminal_event_types_are_exactly_the_four_declared_classes() -> None:
    assert set(TERMINAL_EVENT_TYPES) == {
        SOEventType.MATCH_STARTED,
        SOEventType.MATCH_ENDED,
        SOEventType.MATCH_SCORED,
        SOEventType.VICTORY_DECLARED,
    }
    assert len(TERMINAL_EVENT_TYPES) == 4


def test_whitelist_enumerates_the_full_enum_terminal_forwards_rest_reject() -> None:
    """The ticket's explicit bar: every SOEventType member is exercised."""
    envelopes = build_sample_envelopes()
    assert set(envelopes) == set(SOEventType)  # completeness precondition

    for event_type in SOEventType:
        transport = _FakeTransport()
        forwarder = KafkaTerminalEventForwarder(transport=transport)
        envelope = envelopes[event_type]

        if event_type in TERMINAL_EVENT_TYPES:
            forwarder.publish(envelope)
            assert len(transport.published) == 1
            assert transport.published[0].topic == STEEL_MATCH_TERMINAL_TOPIC
        else:
            with pytest.raises(NonTerminalEventForwardedError):
                forwarder.publish(envelope)
            assert transport.published == []


def test_terminal_events_preserve_envelope_fields_byte_for_byte() -> None:
    envelopes = build_sample_envelopes()
    transport = _FakeTransport()
    forwarder = KafkaTerminalEventForwarder(transport=transport)

    for event_type in TERMINAL_EVENT_TYPES:
        forwarder.publish(envelopes[event_type])

    assert len(transport.published) == len(TERMINAL_EVENT_TYPES)
    for message, event_type in zip(transport.published, TERMINAL_EVENT_TYPES, strict=True):
        original = envelopes[event_type]
        restored = ModelSOEventEnvelope.model_validate_json(message.value)

        assert restored == original  # full structural equality, not just IDs
        assert restored.envelope.correlation_id == original.envelope.correlation_id
        assert restored.envelope.causation_id == original.envelope.causation_id
        assert restored.envelope.entity_id == original.envelope.entity_id
        assert restored.envelope.message_id == original.envelope.message_id
        assert restored.envelope.emitted_at == original.envelope.emitted_at
        assert message.key == original.match_id
        assert message.topic == STEEL_MATCH_TERMINAL_TOPIC


def test_match_id_is_the_partition_key_for_every_terminal_class() -> None:
    envelopes = build_sample_envelopes()
    transport = _FakeTransport()
    forwarder = KafkaTerminalEventForwarder(transport=transport)

    for event_type in TERMINAL_EVENT_TYPES:
        forwarder.publish(envelopes[event_type])

    expected_match_id = envelopes[SOEventType.MATCH_STARTED].match_id
    for message in transport.published:
        assert message.key == expected_match_id


def test_bus_wiring_never_delivers_non_terminal_events_to_the_forwarder() -> None:
    """The exact composition wiring shape: bus.subscribe(fwd.publish, event_types=...)."""
    envelopes = build_sample_envelopes()
    transport = _FakeTransport()
    forwarder = KafkaTerminalEventForwarder(transport=transport)
    bus = InProcessEventBus()
    bus.subscribe(forwarder.publish, event_types=list(TERMINAL_EVENT_TYPES))

    for event_type in SOEventType:
        bus.publish(envelopes[event_type])

    forwarded_event_types = {
        ModelSOEventEnvelope.model_validate_json(message.value).event_type
        for message in transport.published
    }
    assert forwarded_event_types == set(TERMINAL_EVENT_TYPES)
    assert len(transport.published) == len(TERMINAL_EVENT_TYPES)
