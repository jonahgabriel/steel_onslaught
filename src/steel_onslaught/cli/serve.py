"""WebSocket bridge and REST replay API — Tasks 31 and 33.

``WebSocketBridge`` subscribes to the in-process event bus and broadcasts
each published envelope as JSON to every connected WebSocket client.

Byte-identity invariant
-----------------------
Each frame is exactly ``envelope.model_dump_json()``: compact separators,
declaration field order, no whitespace normalization — the same form
``JSON.stringify`` produces after a lossless parse on the TS side.

The ``so serve`` command replays a recorded match from a SQLite ledger:
it binds a WebSocket server (default port 8765) and streams the full match —
frame-for-frame in canonical ledger order — to every client that connects.

REST endpoint (Task 33)
-----------------------
``create_replay_http_handler(ledgers)`` returns an
``http.server.BaseHTTPRequestHandler`` subclass that serves:

  GET /api/replay/{match_id}/tick/{tick}

  200  JSON array of PILOT_DECISION_MADE envelopes for that tick (may be [])
  400  {"error": "invalid_tick"}  when tick < 0
  404  {"error": "match_not_found"}  when no injected ledger contains
       any event with the requested match_id
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import click
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve

from steel_onslaught.bus.protocol import EventBus, HandlerToken
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.protocol import QueryableEventLedger
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger

DEFAULT_WS_HOST = "127.0.0.1"
DEFAULT_WS_PORT = 8765

# ---------------------------------------------------------------------------
# REST endpoint: GET /api/replay/{match_id}/tick/{tick}  (Task 33)
# ---------------------------------------------------------------------------

_REPLAY_RE = re.compile(r"^/api/replay/([^/]+)/tick/(-?\d+)$")


def _find_ledger_for_match(
    ledgers: Sequence[QueryableEventLedger], match_id: str
) -> QueryableEventLedger | None:
    for ledger in ledgers:
        if ledger.contains_match(match_id):
            return ledger
    return None


def _query_pilot_decisions(
    ledger: QueryableEventLedger, match_id: str, tick: int
) -> list[dict[str, Any]]:
    """Return serialised PILOT_DECISION_MADE envelopes for (*match_id*, *tick*)."""
    return [
        json.loads(event.model_dump_json())
        for event in ledger.read_at(
            match_id,
            tick,
            event_types=frozenset({SOEventType.PILOT_DECISION_MADE}),
        )
    ]


def create_replay_http_handler(
    ledgers: Sequence[QueryableEventLedger],
) -> type[BaseHTTPRequestHandler]:
    """Return an HTTP handler class that serves the replay REST API.

    The returned class reads only through injected storage-neutral query ports.

    Endpoint:
        GET /api/replay/{match_id}/tick/{tick}

    Responses:
        200  list of PILOT_DECISION_MADE envelopes (may be [])
        400  {"error": "invalid_tick"}      — tick < 0
        404  {"error": "match_not_found"}   — no ledger contains match_id
    """

    class _ReplayHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            m = _REPLAY_RE.match(self.path)
            if m is None:
                self._respond(404, {"error": "not_found"})
                return

            match_id_param = m.group(1)
            tick_str = m.group(2)
            tick_val = int(tick_str)

            if tick_val < 0:
                self._respond(400, {"error": "invalid_tick"})
                return

            ledger = _find_ledger_for_match(ledgers, match_id_param)
            if ledger is None:
                self._respond(404, {"error": "match_not_found"})
                return

            decisions = _query_pilot_decisions(ledger, match_id_param, tick_val)
            self._respond(200, decisions)

        def _respond(self, status: int, body: Any) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            # Suppress default stderr logging during tests.
            pass

    return _ReplayHandler


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


async def _stream_match(
    send: Callable[[str], Awaitable[None]],
    paced_frames: Sequence[tuple[int, str]],
    tick_delay: float,
) -> None:
    """Send every frame in ledger order, pausing at tick boundaries.

    *paced_frames* is ``(tick, frame)`` pairs.  With ``tick_delay > 0`` the
    coroutine sleeps *tick_delay* seconds whenever the next frame's tick
    differs from the previous frame's tick; frames within a tick stream
    back-to-back.  With ``tick_delay == 0`` no sleep is ever awaited — the
    prior unpaced behavior.  Pacing never alters frame bytes or order.
    """
    previous_tick: int | None = None
    for tick, frame in paced_frames:
        if tick_delay > 0 and previous_tick is not None and tick != previous_tick:
            await asyncio.sleep(tick_delay)
        await send(frame)
        previous_tick = tick


async def _serve_replay(
    events: list[ModelSOEventEnvelope],
    *,
    host: str,
    port: int,
    tick_delay: float = 0.0,
) -> None:
    """Stream the recorded match to EVERY client that connects, then idle.

    Per-client streaming (rather than a single broadcast to the first client)
    makes the replay robust to client churn — e.g. React StrictMode's
    mount/unmount/mount cycle opens two sockets in quick succession, and both
    must receive the full match (Task 34 Proof of Life).  Pacing is therefore
    also per-connection: each client gets the full match from the start, and
    one client's tick-boundary sleeps never block another client's stream.
    """
    paced_frames = [(event.tick, WebSocketBridge.serialize(event)) for event in events]

    async def _stream_to_client(connection: ServerConnection) -> None:
        await _stream_match(connection.send, paced_frames, tick_delay)
        await connection.wait_closed()

    server = await serve(_stream_to_client, host, port)
    try:
        sockets = list(server.sockets)
        bound_port = sockets[0].getsockname()[1] if sockets else port
        click.echo(
            f"serving on ws://{host}:{bound_port} — streaming {len(paced_frames)} events "
            "to each client; Ctrl+C to exit",
            err=True,
        )
        await asyncio.Event().wait()  # serve until interrupted
    finally:
        server.close()
        await server.wait_closed()


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
@click.option(
    "--tick-delay",
    "tick_delay",
    type=click.FloatRange(min=0),
    default=0.0,
    show_default=True,
    help="Seconds to pause between tick boundaries during replay (0 = no pacing).",
)
def serve_command(
    ledger_path: Path, match_id: str, host: str, port: int, tick_delay: float
) -> None:
    """Stream a recorded match to WebSocket clients (frontend on :5173)."""
    ledger = SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=ledger_path,
            journal_mode="WAL",
            check_same_thread=True,
            transaction_mode="autocommit",
            event_schema="canonical_event_v1",
        )
    )
    events = list(ledger.read_all(match_id))
    if not events:
        raise click.ClickException(f"no events found for match {match_id!r} in {ledger_path}")
    try:
        asyncio.run(_serve_replay(events, host=host, port=port, tick_delay=tick_delay))
    except KeyboardInterrupt:
        click.echo("serve interrupted", err=True)
