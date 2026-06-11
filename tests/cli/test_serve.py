"""Tests for the WebSocket bridge — Task 31 invariants.

The critical invariant: the bridge re-emits envelopes byte-identically —
each broadcast frame is exactly ``envelope.model_dump_json()`` (compact,
declaration field order, no whitespace normalization).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import websockets

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cli.serve import DEFAULT_WS_HOST, DEFAULT_WS_PORT, WebSocketBridge
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)

_RECV_TIMEOUT = 5.0


def _env(
    event_type: SOEventType = SOEventType.BOILER_UPDATED,
    *,
    tick: int = 3,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id="01HZX5J9V0Q4R8T2W6Y1B3D5F7",
        match_id="match.test.serve",
        tick=tick,
        sequence_in_tick=0,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        event_type=event_type,
        payload={
            "pressure_before": 40,
            "pressure_after": 38,
            "heat_before": 10,
            "heat_after": 12,
        },
        emitted_at=datetime(2026, 4, 30, tzinfo=UTC).isoformat(),
    )


@pytest.mark.unit
def test_default_host_and_port() -> None:
    """Plan invariant: WebSocket server defaults to port 8765."""
    assert DEFAULT_WS_PORT == 8765
    bridge = WebSocketBridge(InProcessEventBus())
    assert bridge.host == DEFAULT_WS_HOST
    assert bridge.port == DEFAULT_WS_PORT


@pytest.mark.unit
def test_serialize_is_compact_model_dump_json() -> None:
    event = _env()
    assert WebSocketBridge.serialize(event) == event.model_dump_json()
    # Compact form: no spaces after separators (JSON.stringify-compatible).
    assert ": " not in WebSocketBridge.serialize(event)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_broadcasts_published_event_byte_identically() -> None:
    bus = InProcessEventBus()
    bridge = WebSocketBridge(bus, port=0)  # ephemeral port for test isolation
    await bridge.start()
    try:
        async with websockets.connect(f"ws://{bridge.host}:{bridge.port}") as client:
            await bridge.wait_for_client()
            event = _env()
            bus.publish(event)
            received = await asyncio.wait_for(client.recv(), timeout=_RECV_TIMEOUT)
            # The bus re-stamps tick/sequence; serialize the stamped envelope.
            stamped = event.model_copy(update={"tick": 0, "sequence_in_tick": 0})
            assert received == stamped.model_dump_json()
            # Round-trip: the frame parses back into an identical envelope.
            assert ModelSOEventEnvelope.model_validate_json(str(received)) == stamped
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_broadcasts_to_all_connected_clients() -> None:
    bus = InProcessEventBus()
    bridge = WebSocketBridge(bus, port=0)
    await bridge.start()
    try:
        url = f"ws://{bridge.host}:{bridge.port}"
        async with websockets.connect(url) as one, websockets.connect(url) as two:
            await bridge.wait_for_client(count=2)
            bus.publish(_env())
            got_one = await asyncio.wait_for(one.recv(), timeout=_RECV_TIMEOUT)
            got_two = await asyncio.wait_for(two.recv(), timeout=_RECV_TIMEOUT)
            assert got_one == got_two
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_preserves_bus_event_order() -> None:
    bus = InProcessEventBus()
    bridge = WebSocketBridge(bus, port=0)
    await bridge.start()
    try:
        async with websockets.connect(f"ws://{bridge.host}:{bridge.port}") as client:
            await bridge.wait_for_client()
            for event_type in (
                SOEventType.MATCH_TICK,
                SOEventType.BOILER_UPDATED,
                SOEventType.WEAPON_FIRED,
            ):
                bus.publish(_env(event_type, tick=1))
            received_types = []
            for _ in range(3):
                frame = await asyncio.wait_for(client.recv(), timeout=_RECV_TIMEOUT)
                received_types.append(
                    ModelSOEventEnvelope.model_validate_json(str(frame)).event_type
                )
            assert received_types == [
                SOEventType.MATCH_TICK,
                SOEventType.BOILER_UPDATED,
                SOEventType.WEAPON_FIRED,
            ]
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stop_unsubscribes_from_bus() -> None:
    bus = InProcessEventBus()
    bridge = WebSocketBridge(bus, port=0)
    await bridge.start()
    await bridge.stop()
    # Publishing after stop must not raise (no dangling handler on the bus).
    bus.publish(_env())
