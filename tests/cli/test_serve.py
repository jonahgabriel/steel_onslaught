"""Tests for the WebSocket bridge — Task 31 invariants.

The critical invariant: the bridge re-emits envelopes byte-identically —
each broadcast frame is exactly ``envelope.model_dump_json()`` (compact,
declaration field order, no whitespace normalization).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import click
import pytest
import websockets
from click.testing import CliRunner
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cli.serve import (
    DEFAULT_WS_HOST,
    DEFAULT_WS_PORT,
    WebSocketBridge,
    _stream_match,
    serve_command,
)
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
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id="match.test.serve",
            emitted_at=datetime(2026, 4, 30, tzinfo=UTC),
        ),
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


# ---------------------------------------------------------------------------
# Paced replay: so serve --tick-delay
# ---------------------------------------------------------------------------


def _paced_events() -> list[ModelSOEventEnvelope]:
    """Five events over ticks [0, 0, 1, 1, 2] — exactly 2 tick transitions."""
    return [
        _env(SOEventType.MATCH_TICK, tick=0),
        _env(SOEventType.BOILER_UPDATED, tick=0),
        _env(SOEventType.MATCH_TICK, tick=1),
        _env(SOEventType.WEAPON_FIRED, tick=1),
        _env(SOEventType.MATCH_TICK, tick=2),
    ]


def _paced_frames(events: list[ModelSOEventEnvelope]) -> list[tuple[int, str]]:
    return [(event.tick, WebSocketBridge.serialize(event)) for event in events]


@pytest.mark.unit
def test_tick_delay_option_defaults_to_zero() -> None:
    """Plan invariant: --tick-delay defaults to 0.0 (no pacing, prior behavior)."""
    param = next(p for p in serve_command.params if p.name == "tick_delay")
    assert param.default == 0.0
    assert isinstance(param.type, click.FloatRange)
    assert param.type.min == 0


@pytest.mark.unit
def test_negative_tick_delay_rejected_by_click(tmp_path: Path) -> None:
    ledger = tmp_path / "match.sqlite"
    ledger.touch()
    result = CliRunner().invoke(
        serve_command,
        ["--ledger", str(ledger), "--match", "m", "--tick-delay", "-0.5"],
    )
    assert result.exit_code == 2
    assert "--tick-delay" in result.output
    assert "is not in the range" in result.output


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_match_sleeps_once_per_tick_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With delay > 0, sleep fires exactly (distinct tick transitions) times."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("steel_onslaught.cli.serve.asyncio.sleep", fake_sleep)

    sent: list[str] = []

    async def fake_send(frame: str) -> None:
        sent.append(frame)

    events = _paced_events()
    await _stream_match(fake_send, _paced_frames(events), 0.25)

    # Ticks [0, 0, 1, 1, 2] → transitions 0→1 and 1→2 only.
    assert sleeps == [0.25, 0.25]
    assert sent == [event.model_dump_json() for event in events]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_match_zero_delay_never_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default delay 0.0 must not invoke sleep at all — prior behavior intact."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("steel_onslaught.cli.serve.asyncio.sleep", fake_sleep)

    sent: list[str] = []

    async def fake_send(frame: str) -> None:
        sent.append(frame)

    events = _paced_events()
    await _stream_match(fake_send, _paced_frames(events), 0.0)

    assert sleeps == []
    assert sent == [event.model_dump_json() for event in events]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_match_frames_identical_with_and_without_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pacing must not alter frame bytes or order — pacing only."""

    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("steel_onslaught.cli.serve.asyncio.sleep", fake_sleep)

    events = _paced_events()

    unpaced: list[str] = []

    async def collect_unpaced(frame: str) -> None:
        unpaced.append(frame)

    paced: list[str] = []

    async def collect_paced(frame: str) -> None:
        paced.append(frame)

    await _stream_match(collect_unpaced, _paced_frames(events), 0.0)
    await _stream_match(collect_paced, _paced_frames(events), 0.5)

    assert paced == unpaced
    assert paced == [event.model_dump_json() for event in events]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_paced_stream_over_websocket_delivers_full_match() -> None:
    """Each connecting client receives the whole match in order, even paced."""
    from websockets.asyncio.server import ServerConnection, serve

    events = _paced_events()
    frames = _paced_frames(events)

    async def handler(connection: ServerConnection) -> None:
        await _stream_match(connection.send, frames, 0.01)

    async with serve(handler, "127.0.0.1", 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
            received = [
                await asyncio.wait_for(client.recv(), timeout=_RECV_TIMEOUT)
                for _ in range(len(events))
            ]
    assert received == [event.model_dump_json() for event in events]
