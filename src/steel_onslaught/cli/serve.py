"""WebSocket bridge and REST replay API — Tasks 31 and 33.

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

REST endpoint (Task 33)
-----------------------
``create_replay_http_handler(ledger_dir)`` returns an
``http.server.BaseHTTPRequestHandler`` subclass that serves:

  GET /api/replay/{match_id}/tick/{tick}

  200  JSON array of PILOT_DECISION_MADE envelopes for that tick (may be [])
  400  {"error": "invalid_tick"}  when tick < 0
  404  {"error": "match_not_found"}  when no ledger in *ledger_dir* contains
       any event with the requested match_id
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import click
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve

from steel_onslaught.bus.protocol import EventBus, HandlerToken
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger

DEFAULT_WS_HOST = "127.0.0.1"
DEFAULT_WS_PORT = 8765

# ---------------------------------------------------------------------------
# REST endpoint: GET /api/replay/{match_id}/tick/{tick}  (Task 33)
# ---------------------------------------------------------------------------

_REPLAY_RE = re.compile(r"^/api/replay/([^/]+)/tick/(-?\d+)$")

_SELECT_DECISIONS_SQL = """
SELECT event_id, match_id, tick, sequence_in_tick, event_type,
       correlation_id, causation_id, producer_node,
       subject_json, payload_json, emitted_at, schema_version
  FROM events
 WHERE match_id = ?
   AND tick = ?
   AND event_type = ?
 ORDER BY sequence_in_tick ASC, event_id ASC
"""

_CHECK_MATCH_SQL = "SELECT 1 FROM events WHERE match_id = ? LIMIT 1"


def _find_ledger_for_match(ledger_dir: Path, match_id: str) -> Path | None:
    """Return the first ``*.sqlite`` file under *ledger_dir* that contains
    at least one event row for *match_id*, or ``None`` if none exists."""
    for db_path in sorted(ledger_dir.glob("*.sqlite")):
        try:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(_CHECK_MATCH_SQL, (match_id,)).fetchone()
                if row is not None:
                    return db_path
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            continue
    return None


def _query_pilot_decisions(db_path: Path, match_id: str, tick: int) -> list[dict[str, Any]]:
    """Return serialised PILOT_DECISION_MADE envelopes for (*match_id*, *tick*)."""
    from steel_onslaught.ledger.sqlite_ledger import _row_to_envelope

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            _SELECT_DECISIONS_SQL,
            (match_id, tick, SOEventType.PILOT_DECISION_MADE.value),
        ).fetchall()
    finally:
        conn.close()

    result: list[dict[str, Any]] = []
    for row in rows:
        env = _row_to_envelope(row)
        result.append(json.loads(env.model_dump_json()))
    return result


def create_replay_http_handler(ledger_dir: Path) -> type[BaseHTTPRequestHandler]:
    """Return an HTTP handler class that serves the replay REST API.

    The returned class reads from ``*.sqlite`` files under *ledger_dir*.
    Each handler instance is stateless; *ledger_dir* is captured by closure.

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

            db_path = _find_ledger_for_match(ledger_dir, match_id_param)
            if db_path is None:
                self._respond(404, {"error": "match_not_found"})
                return

            decisions = _query_pilot_decisions(db_path, match_id_param, tick_val)
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
