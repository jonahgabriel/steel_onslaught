"""WebSocket bridge — Task 31.

``WebSocketBridge`` subscribes to the in-process event bus and broadcasts
each published envelope as JSON to every connected WebSocket client.

Byte-identity invariant
-----------------------
Each frame is exactly ``envelope.model_dump_json()``: compact separators,
declaration field order, no whitespace normalization — the same form
``JSON.stringify`` produces after a lossless parse on the TS side.

The ``so serve`` command replays a recorded match from a SQLite ledger:
it starts the bridge (default port 8765), waits for the first client, then
publishes every ledger event for the match onto a fresh bus, streaming the
match to all connected clients.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve

from steel_onslaught.bus.protocol import EventBus, HandlerToken
from steel_onslaught.events.envelope import ModelSOEventEnvelope
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger

DEFAULT_WS_HOST = "127.0.0.1"
DEFAULT_WS_PORT = 8765


class WebSocketBridge:
    """Bus → WebSocket fan-out.

    Lifecycle: ``await start()`` binds the server and subscribes to the bus;
    ``await stop()`` unsubscribes and closes the server.  ``publish`` calls on
    the bus may come from the event loop's thread or any other thread — the
    handler marshals onto the loop via ``call_soon_threadsafe``.
    """

    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = DEFAULT_WS_HOST,
        port: int = DEFAULT_WS_PORT,
    ) -> None:
        self._bus = bus
        self._host = host
        self._port = port
        self._clients: set[ServerConnection] = set()
        self._client_connected = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Server | None = None
        self._token: HandlerToken | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        """Configured port, or the bound port once the server has started.

        ``port=0`` requests an ephemeral port; after ``start()`` this property
        reports the actual port the OS assigned.
        """
        if self._server is not None:
            sockets = list(self._server.sockets)
            if sockets:
                bound_port: int = sockets[0].getsockname()[1]
                return bound_port
        return self._port

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @staticmethod
    def serialize(event: ModelSOEventEnvelope) -> str:
        """Compact JSON wire form — the byte-identity contract of the bridge."""
        return event.model_dump_json()

    async def start(self) -> None:
        """Bind the WebSocket server and subscribe to the bus."""
        self._loop = asyncio.get_running_loop()
        self._server = await serve(self._handle_client, self._host, self._port)
        self._token = self._bus.subscribe(self._on_event)

    async def stop(self) -> None:
        """Unsubscribe from the bus and close the server + all connections."""
        if self._token is not None:
            self._bus.unsubscribe(self._token)
            self._token = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._clients.clear()
        self._loop = None

    async def wait_for_client(self, *, count: int = 1) -> None:
        """Block until at least *count* clients are connected."""
        while len(self._clients) < count:
            self._client_connected.clear()
            await self._client_connected.wait()

    async def _handle_client(self, connection: ServerConnection) -> None:
        self._clients.add(connection)
        self._client_connected.set()
        try:
            await connection.wait_closed()
        finally:
            self._clients.discard(connection)

    def _on_event(self, event: ModelSOEventEnvelope) -> None:
        if self._loop is None:
            raise RuntimeError("WebSocketBridge received an event before start()")
        message = self.serialize(event)
        self._loop.call_soon_threadsafe(self._broadcast, message)

    def _broadcast(self, message: str) -> None:
        broadcast(self._clients, message)


async def _serve_replay(
    events: list[ModelSOEventEnvelope],
    *,
    host: str,
    port: int,
) -> None:
    """Start the bridge, wait for the first client, stream *events*, idle."""
    # Local import: the bus protocol lives in steel_onslaught.bus.protocol;
    # the concrete in-process bus is only needed by this CLI entry point.
    from steel_onslaught.bus.in_process import InProcessEventBus

    bus = InProcessEventBus()
    bridge = WebSocketBridge(bus, host=host, port=port)
    await bridge.start()
    click.echo(f"serving on ws://{bridge.host}:{bridge.port} — waiting for a client", err=True)
    try:
        await bridge.wait_for_client()
        for event in events:
            bus.publish(event)
            await asyncio.sleep(0)  # let the loop flush frames between events
        click.echo(f"streamed {len(events)} events; Ctrl+C to exit", err=True)
        await asyncio.Event().wait()  # serve until interrupted
    finally:
        await bridge.stop()


@click.command(name="serve")
@click.option(
    "--ledger",
    "ledger_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--match", "match_id", required=True)
@click.option("--host", default=DEFAULT_WS_HOST, show_default=True)
@click.option("--port", type=click.IntRange(min=0), default=DEFAULT_WS_PORT, show_default=True)
def serve_command(ledger_path: Path, match_id: str, host: str, port: int) -> None:
    """Stream a recorded match to WebSocket clients (frontend on :5173)."""
    events = list(SQLiteLedger(ledger_path).read_all(match_id))
    if not events:
        raise click.ClickException(f"no events found for match {match_id!r} in {ledger_path}")
    try:
        asyncio.run(_serve_replay(events, host=host, port=port))
    except KeyboardInterrupt:
        click.echo("serve interrupted", err=True)
