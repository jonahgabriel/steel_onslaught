"""Tests for InProcessEventBus — Task 5 invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)

# 26-char ULID-shaped test IDs (base32, exactly 26 chars each)
_E1 = "01JABCDE0123456789ABCDEF01"
_E2 = "01JABCDE0123456789ABCDEF02"
_E3 = "01JABCDE0123456789ABCDEF03"
_E4 = "01JABCDE0123456789ABCDEF04"
_E5 = "01JABCDE0123456789ABCDEF05"
_E6 = "01JABCDE0123456789ABCDEF06"
_DEFAULT = "01JABCDE0123456789ABCDEFG0"


def _envelope(
    match_id: str = "m",
    emitted_at: datetime = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
) -> ModelEnvelope:
    """Composed ONEX ModelEnvelope (message_id/correlation_id/causation_id/entity_id/emitted_at)."""
    return ModelEnvelope(
        message_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        entity_id=match_id,
        emitted_at=emitted_at,
    )


def _env(t: SOEventType, eid: str = _DEFAULT) -> ModelSOEventEnvelope:
    # sequence_in_tick=0 here is a placeholder; the bus reassigns it on publish.
    return ModelSOEventEnvelope(
        event_id=eid,
        match_id="m",
        tick=0,
        sequence_in_tick=0,
        event_type=t,
        producer_node="p",
        subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={},
        envelope=_envelope(),
    )


# ---------------------------------------------------------------------------
# Filtered subscription: handler only sees its registered types
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_filtered_subscription() -> None:
    bus = InProcessEventBus()
    seen: list[SOEventType] = []
    bus.subscribe(lambda e: seen.append(e.event_type), event_types=[SOEventType.MATCH_STARTED])
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, _E2))
    assert seen == [SOEventType.MATCH_STARTED]


# ---------------------------------------------------------------------------
# Multiple subscribers on the same type all fire
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_multiple_subscribers_all_fire() -> None:
    bus = InProcessEventBus()
    seen_a: list[int] = []
    seen_b: list[int] = []
    bus.subscribe(lambda e: seen_a.append(1), event_types=[SOEventType.MATCH_STARTED])
    bus.subscribe(lambda e: seen_b.append(2), event_types=[SOEventType.MATCH_STARTED])
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))
    assert seen_a == [1]
    assert seen_b == [2]


# ---------------------------------------------------------------------------
# Publish order is preserved per subscriber
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_publish_order_preserved() -> None:
    bus = InProcessEventBus()
    seen: list[SOEventType] = []
    bus.subscribe(lambda e: seen.append(e.event_type))
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, _E2))
    bus.publish(_env(SOEventType.WEAPON_FIRED, _E3))
    assert seen == [
        SOEventType.MATCH_STARTED,
        SOEventType.PILOT_DECISION_MADE,
        SOEventType.WEAPON_FIRED,
    ]


# ---------------------------------------------------------------------------
# Unsubscribe removes the handler before the next publish
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unsubscribe_removes_handler() -> None:
    bus = InProcessEventBus()
    seen: list[SOEventType] = []
    token = bus.subscribe(lambda e: seen.append(e.event_type))
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))
    bus.unsubscribe(token)
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, _E2))
    assert seen == [SOEventType.MATCH_STARTED]


# ---------------------------------------------------------------------------
# A handler raising does NOT stop other handlers; errors re-raised after
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_error_isolation() -> None:
    bus = InProcessEventBus()
    seen: list[int] = []

    def boom(e: ModelSOEventEnvelope) -> None:
        raise RuntimeError("handler exploded")

    bus.subscribe(boom, event_types=[SOEventType.MATCH_STARTED])
    bus.subscribe(lambda e: seen.append(1), event_types=[SOEventType.MATCH_STARTED])

    with pytest.raises(ExceptionGroup) as exc_info:
        bus.publish(_env(SOEventType.MATCH_STARTED, _E1))

    assert seen == [1], "second handler must have fired despite first handler error"
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], RuntimeError)


# ---------------------------------------------------------------------------
# publish() is synchronous — handlers complete before publish returns
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_publish_is_synchronous() -> None:
    bus = InProcessEventBus()
    order: list[str] = []

    def handler(e: ModelSOEventEnvelope) -> None:
        order.append("handler")

    bus.subscribe(handler, event_types=[SOEventType.MATCH_STARTED])
    order.append("before")
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))
    order.append("after")
    assert order == ["before", "handler", "after"]


# ---------------------------------------------------------------------------
# Bus assigns sequence_in_tick; resets on MATCH_TICK boundary
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sequence_in_tick_resets_per_tick() -> None:
    bus = InProcessEventBus()
    seen: list[tuple[int, int]] = []
    bus.subscribe(lambda e: seen.append((e.tick, e.sequence_in_tick)))

    # Tick 1: emit MATCH_TICK(tick=1) then 2 events
    tick1 = ModelSOEventEnvelope(
        event_id=_E1,
        match_id="m",
        tick=1,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="p",
        subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={},
        envelope=_envelope(),
    )
    bus.publish(tick1)
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, _E2))
    bus.publish(_env(SOEventType.WEAPON_FIRED, _E3))

    # Tick 2 boundary
    tick2 = ModelSOEventEnvelope(
        event_id=_E4,
        match_id="m",
        tick=2,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="p",
        subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={},
        envelope=_envelope(),
    )
    bus.publish(tick2)
    bus.publish(_env(SOEventType.BOILER_UPDATED, _E5))

    # MATCH_TICK(1) → seq=0 at tick=1; next two events → seq=1, seq=2
    # MATCH_TICK(2) resets counter → seq=0 at tick=2; next event → seq=1
    assert seen == [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1)]


# ---------------------------------------------------------------------------
# Bus overwrites sequence_in_tick regardless of producer-supplied value
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bus_overwrites_sequence_in_tick() -> None:
    bus = InProcessEventBus()
    seen_seq: list[int] = []
    bus.subscribe(lambda e: seen_seq.append(e.sequence_in_tick))

    # Producer supplies sequence_in_tick=99 — bus must ignore it
    env_with_fake_seq = ModelSOEventEnvelope(
        event_id=_E1,
        match_id="m",
        tick=0,
        sequence_in_tick=99,
        event_type=SOEventType.MATCH_STARTED,
        producer_node="p",
        subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={},
        envelope=_envelope(),
    )
    bus.publish(env_with_fake_seq)
    assert seen_seq == [0], "bus must assign sequence=0 for the first event, not 99"


# ---------------------------------------------------------------------------
# Wildcard subscription (event_types=None) receives all events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_wildcard_subscription_receives_all() -> None:
    bus = InProcessEventBus()
    seen: list[SOEventType] = []
    bus.subscribe(lambda e: seen.append(e.event_type))  # no event_types filter
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))
    bus.publish(_env(SOEventType.PILOT_DECISION_MADE, _E2))
    bus.publish(_env(SOEventType.WEAPON_FIRED, _E3))
    assert seen == [
        SOEventType.MATCH_STARTED,
        SOEventType.PILOT_DECISION_MADE,
        SOEventType.WEAPON_FIRED,
    ]


# ---------------------------------------------------------------------------
# Unsubscribe with unknown token is a no-op (does not raise)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unsubscribe_unknown_token_is_noop() -> None:
    bus = InProcessEventBus()
    bus.unsubscribe(9999)  # must not raise


# ---------------------------------------------------------------------------
# Bus current_tick tracks MATCH_TICK events; non-tick events inherit current_tick
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_current_tick_advances_on_match_tick() -> None:
    bus = InProcessEventBus()
    seen_ticks: list[int] = []
    bus.subscribe(lambda e: seen_ticks.append(e.tick))

    # Before any MATCH_TICK, current_tick == 0
    bus.publish(_env(SOEventType.MATCH_STARTED, _E1))

    tick3 = ModelSOEventEnvelope(
        event_id=_E2,
        match_id="m",
        tick=3,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="p",
        subject=ModelSOEventSubject(mech_id="m", player_id="p"),
        payload={},
        envelope=_envelope(),
    )
    bus.publish(tick3)
    bus.publish(_env(SOEventType.BOILER_UPDATED, _E3))

    assert seen_ticks == [0, 3, 3]
