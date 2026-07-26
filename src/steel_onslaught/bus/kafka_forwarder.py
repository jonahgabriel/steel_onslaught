"""Terminal-event Kafka-forwarding subscriber (OMN-15167).

Forwards exactly the 4 terminal ``SOEventType`` members --
``MATCH_STARTED``/``MATCH_ENDED``/``MATCH_SCORED``/``VICTORY_DECLARED`` -- from
the in-process match bus onto ONE shared external topic, discriminated by the
envelope's own ``event_type`` field (plan §4b gate ruling: one shared topic
keeps the allowlist diff, consumer wiring, and ledger legibility to a single
surface for 4 low-volume event classes;
``omni_home/docs/plans/2026-07-26-steel-node-dispatch-integration-plan.md``
§2 step 5, §3 P2, §4b). Partition/message key is ``match_id`` (plan §4b gate
ruling -- per-match ordering is the only ordering that matters here; battery
volume is low and cross-match ordering is not a contract).

TOPIC LITERAL: ``onex.evt.steel-onslaught.match-terminal.v1``

This is the exact governed-registration literal OMN-15168 must bind
``node_ledger_projection_compute``'s ``subscribe_topics`` allowlist to
(paired with a ``handler_routing`` entry, OMN-14594 pattern -- a bare
``subscribe_topics`` addition is "subscribed but never dispatched", the
NO_DISPATCHER class). Declared here as ``STEEL_MATCH_TERMINAL_TOPIC`` --
never re-typed as a free string at any call site -- per the platform's
``onex.<kind>.<producer>.<event-name>.v<n>`` convention, studied read-only
from the canonical clone: ``omnibase_core.topics.TopicBase`` /
``omnibase_core.topics._CANONICAL_TOPIC_PATTERN``
(``^onex\\.(cmd|evt|dlq|snapshot|intent)\\.[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+``
``(?:\\.[a-zA-Z0-9_-]+)*\\.v\\d+$``). Steel does not import
``omnibase_core.topics`` itself (that module is core/infra-resident registry
plumbing, not a steel runtime dependency) -- this constant only follows the
same wire-format convention.

Transport-injected (DI-confinement, ``tests/test_di_enforcement.py`` --
this repo forbids ``os.environ``/``os.getenv`` anywhere and confines
effectful construction to ``match/composition.py``):
:class:`KafkaTerminalEventForwarder` never constructs a Kafka client itself
-- it wraps an injected :class:`ProtocolTerminalEventTransport` capability.
Composition (``steel_onslaught.match.composition.build_runtime_dependencies``)
accepts an optional ``kafka_transport``; ``None`` (the default) means the
forwarder is never built and never subscribed onto the bus -- byte-identical,
golden-stable behavior to before this ticket landed (see
``tests/match/test_kafka_forwarder_wiring_omn15167.py``).

**Scope note:** a live Kafka-backed implementation of
``ProtocolTerminalEventTransport`` does not exist in this repo (steel's
``pyproject.toml`` deliberately excludes Kafka client dependencies -- "Infra
is intentionally excluded from this engine", see
``steel_onslaught.llm.client_delegation``'s module docstring for the same
boundary applied to the delegation client). Building and driving one against
live infrastructure is explicitly OMN-15170's scope (the steel-side driver
test, plan §2 step 8 hostile-finding-#1 split); this module proves only the
wiring + serialization + whitelist seam, against a fake transport.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

# Platform convention: onex.<cmd|evt|dlq|snapshot|intent>.<producer>.<event-name>.v<n>
# (omnibase_core.topics.TopicBase / _CANONICAL_TOPIC_PATTERN, studied read-only
# from the canonical omnibase_core clone). This is the literal OMN-15168 must
# register on node_ledger_projection_compute's subscribe_topics allowlist --
# see this module's docstring "TOPIC LITERAL" line, which is the load-bearing
# cross-ticket contract; keep the two in sync if this value ever changes.
STEEL_MATCH_TERMINAL_TOPIC: str = "onex.evt.steel-onslaught.match-terminal.v1"

# The ONLY SOEventType members ever permitted to cross the platform-bus
# boundary. Every other member (intent/telemetry/LLM-completion-evidence
# events) stays match-internal -- already fold-documented as
# informational/no-op for the canonical fold. A tuple, not a mutable
# module-level list, so it cannot be mutated at import time.
TERMINAL_EVENT_TYPES: tuple[SOEventType, ...] = (
    SOEventType.MATCH_STARTED,
    SOEventType.MATCH_ENDED,
    SOEventType.MATCH_SCORED,
    SOEventType.VICTORY_DECLARED,
)

_TERMINAL_EVENT_TYPE_SET: frozenset[SOEventType] = frozenset(TERMINAL_EVENT_TYPES)


@runtime_checkable
class ProtocolTerminalEventTransport(Protocol):
    """The injected capability -- steel never imports a Kafka client directly.

    A future ticket's live composition wiring supplies a concrete
    implementation (OMN-15170); this repo's own tests use a fake. No
    implementation of this protocol lives in this repo today.
    """

    def publish(self, *, topic: str, key: str, value: bytes) -> None:
        """Publish one already-serialized message to *topic*, keyed by *key*."""
        ...


class NonTerminalEventForwardedError(ValueError):
    """Raised if the forwarder is ever invoked with a non-terminal event.

    Defense-in-depth: ``EventBus.subscribe(forwarder.publish,
    event_types=TERMINAL_EVENT_TYPES)`` already filters delivery at the bus
    (see ``steel_onslaught.bus.in_process.InProcessEventBus.publish``), so
    this is unreachable through the composition-wired path -- but the
    forwarder must never trust its caller silently. A future direct or
    mis-wired call (e.g. a wildcard subscribe) is exactly the
    "leaked onto the platform bus" failure this ticket exists to prevent.
    """


class KafkaTerminalEventForwarder:
    """Bus subscriber: forwards the 4 terminal event classes onto one topic.

    ``.publish`` is the ``EventHandler`` callable passed to
    ``EventBus.subscribe`` (see ``steel_onslaught.bus.protocol.EventHandler``)
    -- the name matches the transport method it wraps, not the bus's own
    ``publish``, deliberately: this object *is* the bus-side subscriber and
    the transport-side publisher in one, per the wiring call site
    (``dependencies.bus.subscribe(kafka_forwarder.publish, event_types=...)``).
    """

    def __init__(self, *, transport: ProtocolTerminalEventTransport) -> None:
        self._transport = transport

    def publish(self, event: ModelSOEventEnvelope) -> None:
        if event.event_type not in _TERMINAL_EVENT_TYPE_SET:
            allowed = sorted(member.value for member in TERMINAL_EVENT_TYPES)
            raise NonTerminalEventForwardedError(
                f"KafkaTerminalEventForwarder received non-terminal "
                f"event_type {event.event_type.value!r} for match_id "
                f"{event.match_id!r}; only {allowed} may cross the "
                "platform-bus boundary"
            )
        self._transport.publish(
            topic=STEEL_MATCH_TERMINAL_TOPIC,
            key=event.match_id,
            value=event.model_dump_json().encode("utf-8"),
        )


__all__ = [
    "STEEL_MATCH_TERMINAL_TOPIC",
    "TERMINAL_EVENT_TYPES",
    "KafkaTerminalEventForwarder",
    "NonTerminalEventForwardedError",
    "ProtocolTerminalEventTransport",
]
