"""Process-local browser play session composition.

This module is deliberately below the transport boundary.  It composes an
already injected selected-match stack with the browser command controller,
using the stack's existing authenticated human inbox.  No socket, HTTP
client, secret resolver, or provider discovery is performed here.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import UUID

import click
import ulid
import yaml  # type: ignore[import-untyped]
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from steel_onslaught.bus.protocol import EventBus, HandlerToken
from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.cli.serve import _bootstrap_process_request, build_frontend_bootstrap
from steel_onslaught.commands.authority import (
    AuthenticatedSessionCapability,
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    SessionId,
    canonical_overlay_sha256,
)
from steel_onslaught.commands.browser_gateway import (
    BrowserCommandGateway,
    ModelSOBrowserActionAccepted,
    ModelSOBrowserActionRequest,
    ModelSOBrowserRequestContext,
    ModelSOBrowserRuntimeAccepted,
    ModelSOBrowserStartAccepted,
    ModelSOBrowserStartMatchRequest,
)
from steel_onslaught.commands.inbox import HumanDecisionCancelledError
from steel_onslaught.commands.live_provider import (
    ModelSOLiveProviderLaunchGrant,
    ProcessLocalOneShotLiveProviderCapability,
)
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOFrontendBootstrap,
    ModelSOFrontendCommandGatewayBinding,
    ModelSOSecretRef,
)
from steel_onslaught.contracts.commands import (
    ModelSOHumanTurnPrompt,
    ModelSOPlayerActionCommand,
    ModelSOStartMatchCommand,
    canonical_command_sha256,
)
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.model_catalog import ModelSOModelCatalog
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.contracts.player_selection import (
    ModelSOMatchLaunchProvenance,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
)
from steel_onslaught.contracts.runtime import (
    ModelSORuntimeCommand,
    SORuntimeAction,
    SORuntimeMode,
    SORuntimeStatus,
)
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmTransportError,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    ProtocolHttpTransport,
    ProtocolSecretResolver,
    ProtocolSleeper,
)
from steel_onslaught.match.composition import (
    LiveMatchStack,
    RuntimeDependencies,
    assemble_selected_match_live,
    load_application_overlay,
    load_loadout,
    load_model_catalog_loadouts,
    load_model_catalog_pilot_registry,
    load_model_catalog_runtime_overlay,
    load_model_catalog_runtime_sources,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.state import ModelSOMatchState

BrowserLiveProviderCapability = (
    ProcessLocalOneShotLiveProviderCapability
    | Mapping[str, ProcessLocalOneShotLiveProviderCapability]
)

BrowserLiveProviderCapabilityFactory = Callable[
    [
        ModelSOBrowserStartMatchRequest,
        ModelSOStartMatchAuthorityContext,
        ModelSOApplicationOverlay,
        ModelSOPlayerRosterBinding,
    ],
    BrowserLiveProviderCapability,
]


class _InjectedSecretResolver:
    """Resolve explicitly supplied live-provider secrets at the CLI edge.

    Composition never reads the environment.  This tiny adapter is only used
    by ``so play-live`` after the operator has selected the live command.  The
    Click options may be populated from documented environment variables, but
    the composition graph receives only these injected values.  References are
    the overlay's opaque ``secret://`` names; no provider key is inferred from
    provider or model naming.
    """

    def __init__(self, secrets: Mapping[str, str]) -> None:
        normalized: dict[str, str] = {}
        for reference, secret in secrets.items():
            if not secret:
                raise ValueError(f"live credential for {reference!r} must not be empty")
            normalized[str(ModelSOSecretRef(kind="opaque", ref=reference).ref)] = secret
        self._secrets = MappingProxyType(normalized)

    @classmethod
    def from_cli(
        cls,
        *,
        glm_api_key: str | None,
        openrouter_api_key: str | None,
        gemini_api_key: str | None,
    ) -> _InjectedSecretResolver:
        """Build a resolver from explicit provider credential options."""

        candidates = {
            "secret://llm/glm": glm_api_key,
            "secret://llm/openrouter": openrouter_api_key,
            "secret://llm/gemini": gemini_api_key,
        }
        return cls({reference: secret for reference, secret in candidates.items() if secret})

    def resolve(self, reference: ModelSOSecretRef) -> str:
        try:
            return self._secrets[str(reference.ref)]
        except KeyError:
            raise ValueError(f"no live secret mapping for {reference.ref!r}") from None


class _UrllibJsonTransport:
    """Small injected HTTP port for the explicit live CLI command."""

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        wire = json.dumps(request.model_dump(mode="json", exclude_none=True)).encode("utf-8")
        try:
            with urlopen(
                UrlRequest(url, data=wire, headers=headers, method="POST"),
                timeout=timeout_seconds,
            ) as response:
                return ModelSOOpenAIChatResponse.model_validate_json(response.read())
        except TimeoutError:
            raise LlmCompletionBoundaryError("timeout", retryable=True) from None
        except HTTPError as exc:
            raise LlmTransportError(
                f"LLM provider returned HTTP {exc.code}",
                retryable=exc.code in {408, 429} or exc.code >= 500,
            ) from None
        except URLError:
            raise LlmTransportError("LLM transport request failed", retryable=True) from None
        except (TypeError, ValueError):
            raise LlmTransportError(
                "LLM provider returned an invalid response contract", retryable=False
            ) from None


@dataclass
class BrowserPlaySession:
    """One selected match plus its transport-independent browser controller."""

    stack: LiveMatchStack
    gateway: BrowserCommandGateway
    start_result: ModelSOBrowserStartAccepted
    _closed: bool = False

    @property
    def match_id(self) -> str:
        return self.stack.match_id

    @property
    def launch_provenance(self) -> ModelSOMatchLaunchProvenance:
        return self.stack.launch_provenance

    def submit_action(
        self,
        request: ModelSOBrowserActionRequest,
        *,
        transport: ModelSOBrowserRequestContext,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOBrowserActionAccepted:
        """Admit one browser action into the stack's existing human inbox."""

        return self.gateway.submit_action(
            request,
            transport=transport,
            principal_id=principal_id,
            session_id=session_id,
        )

    def run(self) -> ModelSOMatchState:
        """Run the assembled match; callers own the session lifetime."""

        if self._closed:
            raise RuntimeError("browser play session is closed")
        runtime = getattr(self.stack, "runtime", None)
        if runtime is not None:
            result = runtime.run()
            if not isinstance(result, ModelSOMatchState):
                raise TypeError("injected runtime worker returned an invalid match state")
            return result
        return self.stack.runner.run()

    def close(self) -> None:
        """Close the stack and cancel any blocked human prompt waits."""

        if self._closed:
            return
        self._closed = True
        self.stack.close()

    def __enter__(self) -> BrowserPlaySession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class _PreadmittedStartCoordinator:
    """Expose one already admitted launch to the authenticated browser gateway."""

    def __init__(
        self,
        *,
        command: ModelSOStartMatchCommand,
        context: ModelSOStartMatchAuthorityContext,
        provenance: ModelSOMatchLaunchProvenance,
    ) -> None:
        self._command = command
        self._context = context
        self._provenance = provenance

    def admit_start_match(
        self,
        command: ModelSOStartMatchCommand,
        *,
        context: ModelSOStartMatchAuthorityContext,
        match_id: str,
    ) -> ModelSOMatchLaunchProvenance:
        if (
            command != self._command
            or context != self._context
            or match_id != self._provenance.match_id
        ):
            raise ValueError("browser start does not match the admitted launch")
        return self._provenance


def launch_browser_play_session(
    *,
    overlay: ModelSOApplicationOverlay,
    canonical_overlay: ModelSOApplicationOverlay | None = None,
    roster: ModelSOPlayerRosterBinding,
    pilot_registry: PilotSpecRegistry | None = None,
    sessions: AuthenticatedSessionCapability,
    request: ModelSOBrowserStartMatchRequest,
    transport: ModelSOBrowserRequestContext,
    principal_id: PrincipalId,
    session_id: SessionId,
    context: ModelSOStartMatchAuthorityContext,
    identity: MatchIdentity,
    loadouts: Mapping[str, ModelSOLoadout],
    runtime_factory: Callable[[ModelSOApplicationOverlay], RuntimeDependencies],
    live_provider_capability: BrowserLiveProviderCapability | None = None,
    live_runtime_factory: Callable[
        [ModelSOApplicationOverlay, str | tuple[str, ...], tuple[str, ...]], RuntimeDependencies
    ]
    | None = None,
    seed: int,
    max_ticks: int | None,
    allowed_origins: tuple[str, ...],
) -> BrowserPlaySession:
    """Compose a selected match and admit its browser start before ``run``.

    ``assemble_selected_match_live`` remains the sole match root.  The
    browser gateway is attached only after that root has bound its human pilot
    to its own process-local inbox, so action delivery cannot create a second
    inbox or a second source of pilot truth.  A fresh process-local start
    coordinator performs the gateway's idempotent/authenticated start receipt;
    it does not construct runtime dependencies or provider clients.
    """

    if identity.match_id != request.match_id:
        raise ValueError("request.match_id must equal identity.match_id")

    stack = assemble_selected_match_live(
        overlay=overlay,
        canonical_overlay=canonical_overlay,
        roster=roster,
        pilot_registry=pilot_registry,
        sessions=sessions,
        command=request.command,
        context=context,
        identity=identity,
        loadouts=loadouts,
        runtime_factory=runtime_factory,
        live_provider_capability=live_provider_capability,
        live_runtime_factory=live_runtime_factory,
        seed=seed,
        max_ticks=max_ticks,
    )
    try:
        gateway = BrowserCommandGateway(
            sessions=sessions,
            roster=roster,
            start_coordinator=_PreadmittedStartCoordinator(
                command=request.command,
                context=context,
                provenance=stack.launch_provenance,
            ),
            human_coordinator=stack.human_inbox,
            runtime=getattr(stack, "runtime", None),
            runtime_authority=(principal_id, session_id),
            allowed_origins=allowed_origins,
        )
        start_result = gateway.start_match(
            request,
            transport=transport,
            principal_id=principal_id,
            session_id=session_id,
        )
        if (
            start_result.match_id != stack.launch_provenance.match_id
            or start_result.command_sha256 != stack.launch_provenance.launch_command_sha256
            or start_result.overlay_sha256 != stack.launch_provenance.overlay_sha256
            or start_result.roster_sha256 != stack.launch_provenance.roster_sha256
        ):
            raise RuntimeError("browser start receipt does not match assembled launch provenance")
        return BrowserPlaySession(
            stack=stack,
            gateway=gateway,
            start_result=start_result,
        )
    except Exception:
        stack.close()
        raise


class BrowserPlayServer:
    """Ephemeral loopback adapter for one receive stream and one command stream.

    Authentication is an injected capability keyed by the browser Origin; no
    ambient cookie, bearer token, provider, or secret resolver is consulted.
    The event endpoint never accepts client frames.  Command frames are
    decoded into the closed Python gateway contracts and return only the
    gateway's closed result models.
    """

    def __init__(
        self,
        *,
        bootstrap: ModelSOFrontendBootstrap,
        gateway: BrowserCommandGateway | None,
        bus: EventBus | None,
        authenticate: Callable[[str], tuple[PrincipalId, SessionId] | None],
        host: str = "127.0.0.1",
        port: int = 0,
        session: BrowserPlaySession | None = None,
        session_factory: Callable[
            [
                ModelSOBrowserStartMatchRequest,
                ModelSOBrowserRequestContext,
                PrincipalId,
                SessionId,
            ],
            BrowserPlaySession,
        ]
        | None = None,
        match_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("browser play server must bind a loopback host")
        if session is not None:
            raise ValueError(
                "browser play server must start with no admitted match; "
                "the Start Match command is the sole launch authority"
            )
        self._bootstrap_template = bootstrap
        self._gateway = gateway
        self._bus = bus
        self._authenticate = authenticate
        self._host = host
        self._port = port
        self._session: BrowserPlaySession | None = None
        self._session_factory = session_factory
        self._match_id_factory = match_id_factory
        self._server: Server | None = None
        self._event_clients: set[ServerConnection] = set()
        self._event_queues: dict[ServerConnection, asyncio.Queue[str | None]] = {}
        # Browser startup and command admission are independent WebSocket
        # handshakes. Keep the canonical prefix so a late event subscriber
        # still receives MATCH_STARTED before any tick events.
        self._event_history: list[ModelSOEventEnvelope] = []
        self._event_history_ids: set[str] = set()
        # A browser can admit a fast match before its independent /events
        # handshake reaches this process. Keep one completed prefix for that
        # specific admission so the first late subscriber can recover it.
        # This is intentionally one-shot: ordinary refreshes after a retired
        # match must still receive an empty stream.
        self._late_replay_match_id: str | None = None
        self._late_replay_pending = False
        self._event_client_seen_since_admission = False
        # Match ids retired after MATCH_ENDED are quarantined from late
        # cross-thread callbacks. A browser refresh after retirement must not
        # resurrect the completed prefix as a fresh-looking match.
        self._retired_match_ids: set[str] = set()
        self._pending_events: dict[str, list[ModelSOEventEnvelope]] = {}
        self._pending_ticks: dict[str, int] = {}
        self._pending_event_ids: set[str] = set()
        # Event-bus callbacks can arrive after a later tick has already been
        # published to the browser. Keep those callbacks quarantined so a
        # transport race can never append an out-of-order live frame (or be
        # reconsidered repeatedly by a duplicate callback).
        self._quarantined_event_ids: set[str] = set()
        self._runtime_status_event_ids: set[str] = set()
        self._command_clients: set[ServerConnection] = set()
        self._command_authorities: dict[ServerConnection, tuple[PrincipalId, SessionId]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._token: HandlerToken | None = None
        self._bootstrap: ModelSOFrontendBootstrap | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._retire_task: asyncio.Task[None] | None = None
        self._prompt_watch_tasks: set[asyncio.Task[None]] = set()
        self._pending_prompts: dict[tuple[PrincipalId, SessionId, str], str] = {}
        self._session_owner: tuple[PrincipalId, SessionId] | None = None
        self._start_records: dict[UUID, tuple[tuple[PrincipalId, SessionId], str, str]] = {}
        self._generated_match_ids: dict[UUID, str] = {}
        self._start_lock = asyncio.Lock()
        self._terminal_failure: str | None = None
        self._closed = False

    @property
    def bootstrap(self) -> ModelSOFrontendBootstrap:
        if self._bootstrap is None:
            raise RuntimeError("browser play server has not started")
        return self._bootstrap

    @property
    def event_url(self) -> str:
        return self.bootstrap.frontend_transport.websocket_url

    @property
    def command_url(self) -> str:
        gateway = self.bootstrap.command_gateway
        if gateway is None:
            raise RuntimeError("browser play server has no command binding")
        return gateway.websocket_url

    @property
    def bootstrap_url(self) -> str:
        endpoint = urlsplit(self.event_url)
        return f"http://{endpoint.netloc}/steel-onslaught/bootstrap.json"

    @property
    def closed(self) -> bool:
        return self._closed

    @staticmethod
    def _bound_port(server: Server) -> int:
        sockets = list(server.sockets)
        if not sockets:
            raise RuntimeError("browser play server did not expose a bound socket")
        return int(sockets[0].getsockname()[1])

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("browser play server is already started")
        self._loop = asyncio.get_running_loop()
        self._closed = False
        self._server = await serve(
            self._handle_client,
            self._host,
            self._port,
            process_request=self._process_request,
        )
        port = self._bound_port(self._server)
        template_transport = self._bootstrap_template.frontend_transport
        event_transport = template_transport.model_copy(
            update={"websocket_url": f"ws://{self._host}:{port}/events"}
        )
        command_binding = ModelSOFrontendCommandGatewayBinding(
            kind="websocket",
            contract="steel_onslaught.browser_command_gateway.v1",
            websocket_url=f"ws://{self._host}:{port}/commands",
            authority_scope="injected_process_session",
        )
        self._bootstrap = self._bootstrap_template.model_copy(
            update={
                "frontend_transport": event_transport,
                "command_gateway": command_binding,
            }
        )
        if self._bus is not None:
            self._token = self._bus.subscribe(self._on_event)

    async def stop(self) -> None:
        if self._token is not None and self._bus is not None:
            self._bus.unsubscribe(self._token)
            self._token = None
        if self._session is not None:
            self._session.close()
        tasks = (*self._prompt_watch_tasks, self._run_task, self._retire_task)
        for task in tasks:
            if task is not None and not task.done():
                task.cancel()
        for task in tasks:
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    self._report_terminal_failure()
        self._prompt_watch_tasks.clear()
        self._run_task = None
        self._retire_task = None
        for connection in (*self._event_clients, *self._command_clients):
            await connection.close(code=1001, reason="server shutdown")
        self._event_clients.clear()
        self._command_clients.clear()
        self._command_authorities.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        self._server = None
        self._loop = None
        self._closed = True

    async def _process_request(
        self,
        connection: ServerConnection,
        request: Request,
    ) -> Response | None:
        if self._bootstrap is None:
            return Response(503, "Service Unavailable", Headers(), b'{"error":"not_ready"}')
        if urlsplit(request.path).path == "/commands":
            origin = request.headers.get("Origin")
            host = request.headers.get("Host")
            try:
                if origin is None or host is None:
                    raise ValueError("missing authenticated loopback headers")
                ModelSOBrowserRequestContext(origin=origin, host=host)
                if self._authenticate(origin) is None:
                    raise ValueError("unauthenticated browser origin")
            except ValueError:
                body = b'{"error":"authenticated_loopback_required"}'
                return Response(
                    403,
                    "Forbidden",
                    Headers(
                        {
                            "Content-Type": "application/json",
                            "Content-Length": str(len(body)),
                        }
                    ),
                    body,
                )
        return _bootstrap_process_request(
            self._bootstrap,
            additional_websocket_paths=("/commands",),
        )(connection, request)

    async def _handle_client(self, connection: ServerConnection) -> None:
        request = connection.request
        path = urlsplit(request.path).path if request is not None else ""
        if path == "/events":
            await self._handle_event_client(connection)
        elif path == "/commands":
            await self._handle_command_client(connection)
        else:
            await connection.close(code=1008, reason="unsupported browser path")

    async def _handle_event_client(self, connection: ServerConnection) -> None:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._event_clients.add(connection)
        self._event_queues[connection] = queue
        if self._session is not None:
            self._event_client_seen_since_admission = True
        sender = asyncio.create_task(self._send_event_queue(connection, queue))
        try:
            # Add before taking the snapshot. The event loop cannot run a
            # queued _on_event callback between these statements, so events
            # after the snapshot arrive through broadcast and events before
            # it are included in this replay prefix.
            history = tuple(
                sorted(
                    self._event_history,
                    key=lambda event: (
                        event.match_id,
                        event.tick,
                        event.sequence_in_tick,
                        event.event_id,
                    ),
                )
            )
            for event in history:
                queue.put_nowait(event.model_dump_json())
            # A launch may finish before this receive-only socket completes its
            # handshake. Its retained prefix is consumed by this first late
            # subscriber and then discarded, preserving refresh-as-readiness.
            if self._late_replay_pending and self._session is None:
                self._late_replay_pending = False
                self._late_replay_match_id = None
                self._event_history.clear()
                self._event_history_ids.clear()
            async for _frame in connection:
                await connection.close(code=1008, reason="event stream is receive-only")
                break
        finally:
            self._event_queues.pop(connection, None)
            self._event_clients.discard(connection)
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass

    @staticmethod
    async def _send_event_queue(
        connection: ServerConnection, queue: asyncio.Queue[str | None]
    ) -> None:
        """Serialize event frames per connection to preserve canonical order."""
        while True:
            frame = await queue.get()
            if frame is None:
                return
            try:
                await connection.send(frame)
            except Exception:
                return

    async def _handle_command_client(self, connection: ServerConnection) -> None:
        request = connection.request
        origin = request.headers.get("Origin") if request is not None else None
        host = request.headers.get("Host") if request is not None else None
        if origin is None or host is None:
            await connection.close(code=1008, reason="authenticated loopback origin required")
            return
        try:
            transport = ModelSOBrowserRequestContext(origin=origin, host=host)
        except ValueError:
            await connection.close(code=1008, reason="authenticated loopback origin required")
            return
        authority = self._authenticate(origin)
        if authority is None:
            await connection.close(code=1008, reason="authenticated session required")
            return
        principal_id, session_id = authority
        self._command_clients.add(connection)
        self._command_authorities[connection] = authority
        await self._flush_pending_prompts(connection, authority)
        try:
            async for frame in connection:
                if not isinstance(frame, str):
                    await connection.close(code=1003, reason="text command frames required")
                    break
                response = await self._dispatch_command(
                    frame,
                    transport=transport,
                    principal_id=principal_id,
                    session_id=session_id,
                )
                if response is None:
                    await connection.close(code=1000, reason="cancelled")
                    break
                await connection.send(response)
                try:
                    is_cancel = json.loads(frame).get("kind") == "steel_onslaught.browser_cancel"
                except (TypeError, ValueError):
                    is_cancel = False
                if is_cancel:
                    await connection.close(code=1000, reason="cancelled")
                    break
        finally:
            self._command_clients.discard(connection)
            self._command_authorities.pop(connection, None)

    @staticmethod
    def _closed_keys(payload: Mapping[str, Any], expected: set[str]) -> None:
        if set(payload) != expected:
            raise ValueError("command frame contains unknown or missing fields")

    def _start_request(self, payload: Mapping[str, Any]) -> ModelSOBrowserStartMatchRequest:
        self._closed_keys(payload, {"schema_version", "kind", "request_id", "intent"})
        if payload["schema_version"] != "1":
            raise ValueError("unsupported command schema")
        request_id = UUID(str(payload["request_id"]))
        intent = payload["intent"]
        if not isinstance(intent, dict):
            raise ValueError("start intent must be an object")
        self._closed_keys(
            intent,
            {"expected_overlay_sha256", "roster_id", "expected_roster_sha256", "selections"},
        )
        selections = intent["selections"]
        if not isinstance(selections, list) or len(selections) != 2:
            raise ValueError("start intent requires exactly two selections")
        command = ModelSOStartMatchCommand(
            schema_version="1",
            kind="steel_onslaught.start_match",
            command_id=request_id,
            expected_overlay_sha256=str(intent["expected_overlay_sha256"]),
            expected_roster_sha256=str(intent["expected_roster_sha256"]),
            selections=tuple(selections),
        )
        match_id = self._generated_match_ids.get(request_id)
        if match_id is None:
            match_id = (
                self._match_id_factory()
                if self._match_id_factory is not None
                else f"match.{ulid.from_uuid(request_id).str}"
            )
            self._generated_match_ids[request_id] = match_id
        return ModelSOBrowserStartMatchRequest(match_id=match_id, command=command)

    @staticmethod
    def _action_request(payload: Mapping[str, Any]) -> ModelSOBrowserActionRequest:
        if set(payload) != {"schema_version", "kind", "request_id", "action"}:
            raise ValueError("action frame contains unknown or missing fields")
        if payload["schema_version"] != "1":
            raise ValueError("unsupported command schema")
        action = payload["action"]
        if not isinstance(action, dict):
            raise ValueError("action intent must be an object")
        if set(action) != {
            "match_id",
            "side",
            "turn_id",
            "expected_tick",
            "observation_sha256",
            "action",
        }:
            raise ValueError("action intent contains unknown or missing fields")
        command = ModelSOPlayerActionCommand(
            schema_version="1",
            kind="steel_onslaught.player_action",
            command_id=UUID(str(payload["request_id"])),
            match_id=action["match_id"],
            turn_id=action["turn_id"],
            expected_tick=action["expected_tick"],
            observation_sha256=action["observation_sha256"],
            action=action["action"],
        )
        return ModelSOBrowserActionRequest(side=action["side"], command=command)

    async def _run_session(self) -> None:
        if self._session is not None:
            await asyncio.to_thread(self._session.run)

    async def _admit_start(
        self,
        request: ModelSOBrowserStartMatchRequest,
        *,
        transport: ModelSOBrowserRequestContext,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> str:
        command_id = request.command.command_id
        fingerprint = request.model_dump_json()
        owner = (principal_id, session_id)
        async with self._start_lock:
            existing = self._start_records.get(command_id)
            if existing is not None:
                existing_owner, existing_fingerprint, response = existing
                if existing_owner != owner or existing_fingerprint != fingerprint:
                    raise ValueError("start request id was reused with different content")
                return response
            if self._session is not None and not self._closed:
                raise ValueError("one active browser match is already admitted")
            # A new admission starts a new canonical event prefix. Existing
            # clients retain their prior match in the frontend transport, but
            # late subscribers should receive only this match's prefix.
            self._event_history.clear()
            self._event_history_ids.clear()
            self._retired_match_ids.discard(request.match_id)
            self._pending_events.clear()
            self._pending_ticks.clear()
            self._pending_event_ids.clear()
            self._quarantined_event_ids.clear()
            self._runtime_status_event_ids.clear()
            candidate: BrowserPlaySession | None = None
            try:
                if self._session_factory is not None:
                    candidate = self._session_factory(request, transport, principal_id, session_id)
                    self._session = candidate
                    self._gateway = candidate.gateway
                    self._bus = self._session.stack.bus
                    if self._token is None:
                        self._token = self._bus.subscribe(self._on_event)
                    self._session_owner = owner
                if self._gateway is None:
                    raise ValueError("browser session has not been started")
                result = self._gateway.start_match(
                    request,
                    transport=transport,
                    principal_id=principal_id,
                    session_id=session_id,
                )
                response = result.model_dump_json()
                # Record whether this admitted launch had an event subscriber
                # already attached. If not, retain one completed prefix for a
                # late handshake; a client that connects before retirement
                # receives the live broadcast and disables this fallback.
                self._event_client_seen_since_admission = bool(self._event_clients)
                self._late_replay_match_id = (
                    None if self._event_client_seen_since_admission else request.match_id
                )
                self._late_replay_pending = False
                # Admit the command before starting the runner.  A runner can
                # publish MATCH_STARTED synchronously in its first call; if it
                # starts before the gateway receipt, the event can race the
                # browser's event socket and the UI sees MATCH_TICK as the
                # first frame, violating the canonical prefix contract.
                if candidate is not None:
                    runtime = getattr(candidate.stack, "runtime", None)
                    dispatch_runtime = getattr(candidate.gateway, "dispatch_runtime", None)
                    if runtime is not None:
                        if dispatch_runtime is None:
                            raise ValueError("browser gateway has no runtime command port")
                        runtime_status = runtime.status
                        dispatch_runtime(
                            ModelSORuntimeCommand(
                                schema_version="1",
                                kind="steel_onslaught.runtime_command",
                                command_id=command_id,
                                expected_revision=runtime_status.revision,
                                owner_id=runtime_status.owner_id,
                                action=SORuntimeAction.START,
                                mode=SORuntimeMode.ONE_GAME,
                            ),
                            transport=transport,
                            principal_id=principal_id,
                            session_id=session_id,
                        )
                    self._start_run_task()
                    self._start_prompt_watchers()
            except Exception:
                if candidate is not None:
                    candidate.close()
                    if self._run_task is not None and not self._run_task.done():
                        self._run_task.cancel()
                    self._run_task = None
                    self._session = None
                    self._gateway = None
                raise
            self._start_records[command_id] = (owner, fingerprint, response)
            return response

    async def _dispatch_command(
        self,
        frame: str,
        *,
        transport: ModelSOBrowserRequestContext,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> str | None:
        try:
            payload: Any = json.loads(frame)
            if not isinstance(payload, dict):
                raise ValueError("command frame must be an object")
            kind = payload.get("kind")
            start_request: ModelSOBrowserStartMatchRequest | None = None
            if kind == "steel_onslaught.browser_start_intent":
                start_request = self._start_request(payload)
            elif kind == "steel_onslaught.browser_start_match":
                start_request = ModelSOBrowserStartMatchRequest.model_validate(payload)
            elif kind == "steel_onslaught.runtime_command":
                runtime_command = ModelSORuntimeCommand.model_validate(payload)
                if self._gateway is None:
                    raise ValueError("browser session has not been started")
                if self._session_owner is not None and self._session_owner != (
                    principal_id,
                    session_id,
                ):
                    raise ValueError("runtime commands belong to the admitted launch authority")
                dispatch_runtime = getattr(self._gateway, "dispatch_runtime", None)
                if dispatch_runtime is None:
                    raise ValueError("browser gateway has no runtime command port")
                result = cast(
                    ModelSOBrowserRuntimeAccepted,
                    dispatch_runtime(
                        runtime_command,
                        transport=transport,
                        principal_id=principal_id,
                        session_id=session_id,
                    ),
                )
                if runtime_command.action is SORuntimeAction.PAUSE and self._session is not None:
                    runtime = getattr(self._session.stack, "runtime", None)
                    if runtime is None:
                        raise ValueError("browser session has no injected runtime")
                    tick = await asyncio.to_thread(
                        runtime.wait_for_pause_boundary,
                        runtime_command.command_id,
                    )
                    self._enqueue_runtime_status(tick=tick)
                    # A pause boundary is a complete tick boundary.  There
                    # may be no subsequent MATCH_TICK while paused to trigger
                    # the normal one-tick ordering flush, so release this
                    # status (and any same-tick game events) now.
                    self._flush_pending_tick(self._session.match_id)
                elif runtime_command.action is SORuntimeAction.RESUME:
                    self._enqueue_runtime_status()
                return result.model_dump_json()
            elif kind == "steel_onslaught.browser_player_action":
                if set(payload) == {"schema_version", "kind", "side", "command"}:
                    action_command = ModelSOPlayerActionCommand.model_validate(payload["command"])
                    action_request = ModelSOBrowserActionRequest(
                        side=payload["side"], command=action_command
                    )
                else:
                    action_request = self._action_request(payload)
                if self._gateway is None:
                    raise ValueError("browser session has not been started")
                action_result = self._gateway.submit_action(
                    action_request,
                    transport=transport,
                    principal_id=principal_id,
                    session_id=session_id,
                )
                self._clear_pending_prompts(
                    (principal_id, session_id),
                    turn_id=action_request.command.turn_id,
                )
                return action_result.model_dump_json()
            elif kind == "steel_onslaught.browser_cancel":
                self._closed_keys(payload, {"schema_version", "kind", "request_id"})
                if payload["schema_version"] != "1" or not isinstance(payload["request_id"], str):
                    raise ValueError("invalid cancel request")
                self._clear_pending_prompts((principal_id, session_id))
                if self._session is not None:
                    self._session.close()
                return json.dumps(
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.browser_cancelled",
                        "authority_scope": "process_lifetime",
                        "outcome": "cancelled",
                        "request_id": payload["request_id"],
                    },
                    separators=(",", ":"),
                )
            elif kind not in {
                "steel_onslaught.browser_start_intent",
                "steel_onslaught.browser_start_match",
            }:
                raise ValueError("unsupported command kind")
            if start_request is None:
                raise ValueError("start request is missing")
            return await self._admit_start(
                start_request,
                transport=transport,
                principal_id=principal_id,
                session_id=session_id,
            )
        except Exception:
            return json.dumps(
                {
                    "schema_version": "1",
                    "kind": "steel_onslaught.browser_command_failed",
                    "authority_scope": "process_lifetime",
                    "outcome": "failed",
                    "error_code": "invalid_or_unauthorized_command",
                },
                separators=(",", ":"),
            )

    def _clear_pending_prompts(
        self,
        authority: tuple[PrincipalId, SessionId],
        *,
        turn_id: str | None = None,
    ) -> None:
        for key in tuple(self._pending_prompts):
            principal_id, session_id, pending_turn_id = key
            if (principal_id, session_id) == authority and (
                turn_id is None or pending_turn_id == turn_id
            ):
                del self._pending_prompts[key]

    def _start_run_task(self) -> None:
        if self._run_task is not None and not self._run_task.done():
            return
        self._run_task = asyncio.create_task(self._run_session())
        self._run_task.add_done_callback(self._run_task_done)

    def _run_task_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            self._report_terminal_failure()
        # A completed match is no longer an active admission. Retire its
        # process-local stack so the next browser start command can create a
        # fresh match without restarting the server.
        if self._loop is not None:
            self._retire_task = asyncio.create_task(self._retire_completed_session())

    async def _retire_completed_session(self) -> None:
        # Drain callbacks funnelled from the worker thread before clearing the
        # session.  In particular, MATCH_ENDED must reach the browser queue so
        # its server-only runtime ``ended`` projection can sort immediately
        # before the terminal envelope.
        await asyncio.sleep(0)
        session = self._session
        if session is None:
            return
        retired_match_id = session.match_id
        session.close()
        if self._token is not None and self._bus is not None:
            self._bus.unsubscribe(self._token)
            self._token = None
        self._session = None
        self._gateway = None
        self._bus = None
        self._session_owner = None
        self._pending_prompts.clear()
        self._retired_match_ids.add(retired_match_id)
        retain_for_late_subscriber = (
            self._late_replay_match_id == retired_match_id
            and not self._event_client_seen_since_admission
        )
        self._late_replay_pending = retain_for_late_subscriber
        if not retain_for_late_subscriber:
            self._late_replay_match_id = None
            self._event_history.clear()
            self._event_history_ids.clear()
        self._pending_events.clear()
        self._pending_ticks.clear()
        self._pending_event_ids.clear()
        self._quarantined_event_ids.clear()
        self._runtime_status_event_ids.clear()
        watchers = tuple(self._prompt_watch_tasks)
        for watcher in watchers:
            if not watcher.done():
                watcher.cancel()
        for watcher in watchers:
            try:
                await watcher
            except asyncio.CancelledError:
                pass
        self._prompt_watch_tasks.clear()

    def _start_prompt_watchers(self) -> None:
        if self._session is None or self._session_owner is None:
            return
        principal_id, session_id = self._session_owner
        for assignment in self._session.launch_provenance.seat_assignments:
            if assignment.kind != "human":
                continue
            existing = {task.get_name() for task in self._prompt_watch_tasks if not task.done()}
            name = f"prompt:{principal_id}:{session_id}:{assignment.side}"
            if name in existing:
                continue
            task = asyncio.create_task(
                self._watch_prompt(
                    principal_id=principal_id,
                    session_id=session_id,
                    side=assignment.side,
                    match_id=self._session.match_id,
                ),
                name=name,
            )
            self._prompt_watch_tasks.add(task)

    @staticmethod
    def _wait_for_prompt(
        session: BrowserPlaySession,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Any,
        match_id: str,
        after_tick: int,
    ) -> ModelSOHumanTurnPrompt:
        return session.stack.human_inbox.wait_for_prompt(
            principal_id=principal_id,
            session_id=session_id,
            side=side,
            match_id=match_id,
            after_tick=after_tick,
        )

    async def _watch_prompt(
        self,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Any,
        match_id: str,
    ) -> None:
        after_tick = -1
        try:
            while True:
                if self._session is None:
                    return
                prompt = await asyncio.to_thread(
                    self._wait_for_prompt,
                    self._session,
                    principal_id=principal_id,
                    session_id=session_id,
                    side=side,
                    match_id=match_id,
                    after_tick=after_tick,
                )
                after_tick = prompt.expected_tick
                key = (principal_id, session_id, prompt.turn_id)
                self._pending_prompts[key] = prompt.model_dump_json()
                for connection, authority in tuple(self._command_authorities.items()):
                    if authority == (principal_id, session_id):
                        await connection.send(prompt.model_dump_json())
        except HumanDecisionCancelledError:
            return
        except Exception:
            self._report_terminal_failure()

    async def _flush_pending_prompts(
        self,
        connection: ServerConnection,
        authority: tuple[PrincipalId, SessionId],
    ) -> None:
        principal_id, session_id = authority
        for (owner_principal, owner_session, _turn_id), message in tuple(
            self._pending_prompts.items()
        ):
            if (owner_principal, owner_session) == (principal_id, session_id):
                await connection.send(message)

    def _report_terminal_failure(self) -> None:
        if self._terminal_failure is not None:
            return
        self._terminal_failure = "play_session_failed"
        if self._session is not None:
            self._session.close()
        message = json.dumps(
            {
                "schema_version": "1",
                "kind": "steel_onslaught.browser_command_failed",
                "authority_scope": "process_lifetime",
                "outcome": "failed",
                "error_code": self._terminal_failure,
            },
            separators=(",", ":"),
        )
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(lambda: broadcast(self._command_clients, message))

    def _on_event(self, event: ModelSOEventEnvelope) -> None:
        if self._loop is None:
            return
        if (
            event.event_type is SOEventType.MATCH_ENDED
            and self._session is not None
            and event.match_id == self._session.match_id
        ):
            # The ledger subscriber is installed before the browser subscriber
            # in the composition root.  Marking the runtime here therefore
            # proves durable terminal evidence before the server projects an
            # ``ended`` status into the browser stream.
            runtime = getattr(self._session.stack, "runtime", None)
            if runtime is not None:
                try:
                    runtime.mark_match_ended()
                except Exception:
                    # Preserve canonical terminal delivery even when a test or
                    # legacy stack cannot prove the evidence.  The projection
                    # helper will omit a false ``ended`` status in that case.
                    self._report_terminal_failure()
        # Runner events can be emitted from a worker thread. Funnel callbacks
        # through the event loop, then hold one tick until its next tick (or
        # terminal) arrives so same-tick sequence numbers can be sorted before
        # any per-connection sender puts bytes on the wire.
        self._loop.call_soon_threadsafe(self._enqueue_event, event)

    def _enqueue_event(self, event: ModelSOEventEnvelope) -> None:
        # A completed run may still have a queued cross-thread callback when
        # the next admission clears the prefix. Never let that stale match
        # contaminate the new browser stream.
        if event.match_id in self._retired_match_ids:
            return
        if self._session is not None and event.match_id != self._session.match_id:
            return
        if (
            event.event_id in self._event_history_ids
            or event.event_id in self._pending_event_ids
            or event.event_id in self._quarantined_event_ids
        ):
            return
        if event.event_type is SOEventType.MATCH_STARTED:
            self._publish_ordered_events((event,))
            self._pending_ticks[event.match_id] = event.tick
            self._enqueue_runtime_status(tick=event.tick)
            return

        current_tick = self._pending_ticks.get(event.match_id)
        if current_tick is None:
            self._pending_ticks[event.match_id] = event.tick
            current_tick = event.tick
        if event.tick < current_tick:
            # This is a transport-late event for a tick that has already
            # drained (or is ahead in the current buffer). Publishing it
            # directly would violate the live browser's canonical order;
            # quarantine it instead. A stable id also prevents repeated
            # cross-thread callbacks for the same stale event from doing
            # additional work.
            self._quarantined_event_ids.add(event.event_id)
            return
        if event.tick > current_tick:
            self._flush_pending_tick(event.match_id)
            self._pending_ticks[event.match_id] = event.tick
        if event.event_type is SOEventType.MATCH_ENDED:
            # Runtime ENDED is server-stream metadata, not canonical ledger
            # truth.  Give it the same tick/sequence as MATCH_ENDED and a
            # lexically minimal event id so it sorts immediately before the
            # terminal envelope without changing the game ledger.
            self._enqueue_runtime_status(tick=event.tick, terminal=event)
        self._pending_events.setdefault(event.match_id, []).append(event)
        self._pending_event_ids.add(event.event_id)
        if event.event_type is SOEventType.MATCH_ENDED:
            self._flush_pending_tick(event.match_id)

    def _runtime_sequence(self, match_id: str, tick: int) -> int:
        events = [
            *self._event_history,
            *self._pending_events.get(match_id, []),
        ]
        same_tick = [
            event.sequence_in_tick
            for event in events
            if event.match_id == match_id and event.tick == tick
        ]
        return max(same_tick, default=-1) + 1

    def _enqueue_runtime_status(
        self,
        *,
        tick: int | None = None,
        terminal: ModelSOEventEnvelope | None = None,
    ) -> None:
        """Project injected runtime state into the browser event stream.

        Runtime status is deliberately not published on the event bus: it is
        a transport projection, while the ledger remains the sole source of
        canonical game truth.  Status frames still use the regular envelope
        factory so the frontend can apply the same closed parser and ordering
        checks as every other event.
        """

        if self._session is None:
            return
        runtime = getattr(self._session.stack, "runtime", None)
        if runtime is None:
            return
        status = runtime.status
        if status.status is SORuntimeStatus.READY:
            return
        match_id = self._session.match_id
        if match_id in self._pending_ticks and tick is None:
            selected_tick = self._pending_ticks[match_id]
        elif tick is not None:
            selected_tick = tick
        else:
            selected_tick = int(getattr(self._session.stack.runner.fold.state, "tick", 0))
        key = f"{match_id}:{status.revision}:{status.status.value}"
        if key in self._runtime_status_event_ids:
            return
        sequence = (
            terminal.sequence_in_tick
            if terminal is not None
            else self._runtime_sequence(match_id, selected_tick)
        )
        event = self._session.stack.event_factory.make(
            match_id=match_id,
            tick=selected_tick,
            sequence_in_tick=sequence,
            event_type=SOEventType.RUNTIME_STATUS_CHANGED,
            producer_node="node.browser.play.runtime",
            subject=ModelSOEventSubject(mech_id="*", player_id="*"),
            payload=status.model_dump(mode="json"),
            correlation_id=self._session.stack.runner.identity.correlation_id,
        )
        if terminal is not None:
            event = event.model_copy(update={"event_id": "0" * 26})
        self._runtime_status_event_ids.add(key)
        self._enqueue_event(event)

    def _flush_pending_tick(self, match_id: str) -> None:
        events = self._pending_events.pop(match_id, [])
        self._pending_ticks.pop(match_id, None)
        if not events:
            return
        ordered = tuple(
            sorted(
                events,
                key=lambda item: (item.tick, item.sequence_in_tick, item.event_id),
            )
        )
        self._publish_ordered_events(ordered)
        for event in events:
            self._pending_event_ids.discard(event.event_id)

    def _publish_ordered_events(self, events: tuple[ModelSOEventEnvelope, ...]) -> None:
        for event in events:
            if event.event_id in self._event_history_ids:
                continue
            self._event_history_ids.add(event.event_id)
            self._event_history.append(event)
            frame = event.model_dump_json()
            for queue in tuple(self._event_queues.values()):
                queue.put_nowait(frame)


class _ConfiguredSessionCapability:
    def __init__(self, session: ModelSOAuthenticatedSession) -> None:
        self._session = session

    def resolve(
        self,
        *,
        principal_id: str,
        session_id: str,
    ) -> ModelSOAuthenticatedSession | None:
        if (principal_id, session_id) != (self._session.principal_id, self._session.session_id):
            return None
        return self._session


def _load_yaml_model(path: Any, model: Any) -> Any:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model.model_validate_json(json.dumps(raw, separators=(",", ":")))


def _selects_non_stub_provider(
    request: ModelSOBrowserStartMatchRequest,
    *,
    overlay: ModelSOApplicationOverlay,
    roster: ModelSOPlayerRosterBinding,
) -> bool:
    options = {option.option_id: option for option in roster.options}
    identities = {identity.model_identity_id: identity for identity in overlay.llm.model_identities}
    providers = {provider.provider_id: provider for provider in overlay.llm.providers}
    return any(
        isinstance(option := options[selection.option_id], ModelSOModelPlayerOptionBinding)
        and providers[identities[option.model_identity_id].provider_binding_id].kind != "stub"
        for selection in request.command.selections
    )


def _loopback_origin_aliases(origin: str) -> tuple[str, ...]:
    """Return only the two safe browser origins for the local Vite deck."""

    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.port is None:
        raise ValueError("browser origin must include an explicit HTTP(S) port")
    if parsed.username is not None or parsed.password is not None or parsed.path not in {"", "/"}:
        raise ValueError("browser origin must be a bare loopback origin")
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("browser origin must be loopback")
    hosts = ("localhost", "127.0.0.1")
    return tuple(f"{parsed.scheme}://{host}:{parsed.port}" for host in hosts)


def _injected_live_provider_capability_factory(
    *,
    max_completions: int,
    canonical_overlay: ModelSOApplicationOverlay | None = None,
) -> BrowserLiveProviderCapabilityFactory:
    """Bind a fresh, bounded launch grant for each browser start.

    The grant contains only canonical launch hashes and model/provider ids.
    Endpoint and credential authority remains in the injected application
    factory's transport and secret-resolver ports.
    """

    if max_completions <= 1:
        raise ValueError("live browser completion budget must allow multiple completions")

    def build_capability(
        request: ModelSOBrowserStartMatchRequest,
        context: ModelSOStartMatchAuthorityContext,
        overlay: ModelSOApplicationOverlay,
        roster: ModelSOPlayerRosterBinding,
    ) -> BrowserLiveProviderCapability:
        options = {option.option_id: option for option in roster.options}
        identities = {
            identity.model_identity_id: identity for identity in overlay.llm.model_identities
        }
        providers = {provider.provider_id: provider for provider in overlay.llm.providers}
        capabilities: dict[str, ProcessLocalOneShotLiveProviderCapability] = {}
        for selection in request.command.selections:
            option = options[selection.option_id]
            if not isinstance(option, ModelSOModelPlayerOptionBinding):
                continue
            identity = identities[option.model_identity_id]
            provider = providers[identity.provider_binding_id]
            if provider.kind == "stub":
                continue
            if option.model_identity_id in capabilities:
                continue
            capabilities[option.model_identity_id] = ProcessLocalOneShotLiveProviderCapability(
                grant=ModelSOLiveProviderLaunchGrant(
                    creator_principal_id=context.creator_principal_id,
                    creator_session_id=context.creator_session_id,
                    launch_command_id=request.command.command_id,
                    launch_command_sha256=canonical_command_sha256(request.command),
                    overlay_sha256=canonical_overlay_sha256(canonical_overlay or overlay),
                    roster_sha256=roster.canonical_sha256(),
                    model_identity_id=option.model_identity_id,
                    provider_id=provider.provider_id,
                    max_completions=max_completions,
                )
            )
        if not capabilities:
            raise ValueError("live provider capability requested for a stub-only launch")
        if len(capabilities) == 1:
            return next(iter(capabilities.values()))
        return capabilities

    return build_capability


def _catalog_selection_overlay(
    *,
    overlay: ModelSOApplicationOverlay,
    catalog: ModelSOModelCatalog,
    source_overlays: Mapping[str, ModelSOApplicationOverlay],
    request: ModelSOBrowserStartMatchRequest,
) -> ModelSOApplicationOverlay:
    """Select only the card-programmer bindings for the admitted catalog seats."""

    options = {option.option_id: option for option in catalog.options}
    card_bindings = []
    for selection in request.command.selections:
        option = options.get(selection.option_id)
        if option is None or option.kind != "model":
            continue
        source_overlay = source_overlays.get(option.source_overlay_id)
        if source_overlay is None or source_overlay.contracts.card_catalog is None:
            continue
        source_programmers = source_overlay.contracts.card_catalog.programmers
        if source_programmers is None:
            continue
        binding = next(
            (programmer for programmer in source_programmers if programmer.side == selection.side),
            None,
        )
        if binding is not None:
            # A source overlay supplies the seat's card-programming defaults,
            # but the selected catalog option owns the exact pilot identity.
            # Rebind that programmer to the admitted option so a differentiated
            # same-provider role (for example Qwen35 sniper) cannot execute
            # the source roster's other pilot by accident.
            card_bindings.append(binding.model_copy(update={"pilot_spec_id": option.pilot_spec_id}))
    card_catalog = overlay.contracts.card_catalog
    if card_catalog is None:
        return overlay
    selected_card_catalog = card_catalog.model_copy(update={"programmers": tuple(card_bindings)})
    contracts = overlay.contracts.model_copy(update={"card_catalog": selected_card_catalog})
    return overlay.model_copy(update={"contracts": contracts})


def _configured_browser_server(
    *,
    overlay_path: Path,
    roster_path: Path | None = None,
    catalog_index_path: Path | None = None,
    session_path: Path,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int | None,
    origin: str,
    host: str,
    port: int,
    live_provider_capability: BrowserLiveProviderCapability | None = None,
    live_provider_capability_factory: BrowserLiveProviderCapabilityFactory | None = None,
    live_runtime_factory: Callable[
        [ModelSOApplicationOverlay, str | tuple[str, ...], tuple[str, ...]], RuntimeDependencies
    ]
    | None = None,
    application_factory: CliApplicationFactory | None = None,
    live_max_completions: int = 256,
) -> BrowserPlayServer:
    if application_factory is not None and (
        live_provider_capability is not None
        or live_provider_capability_factory is not None
        or live_runtime_factory is not None
    ):
        raise ValueError(
            "application_factory cannot be combined with explicit live composition ports"
        )
    if live_provider_capability is not None and live_provider_capability_factory is not None:
        raise ValueError("fixed and per-start live provider capabilities cannot be combined")
    factory = application_factory or CliApplicationFactory.packaged()
    if bool(getattr(factory, "live_enabled", False)):
        live_runtime_factory = factory.selected_runtime
    elif application_factory is not None:
        raise ValueError(
            "application_factory requires both injected secret and HTTP capabilities for live play"
        )
    # A live application factory mints the per-start capability after the
    # canonical overlay is loaded; count that deferred authority here so
    # malformed injection combinations still fail before filesystem reads.
    has_live_authority = (
        live_provider_capability is not None
        or live_provider_capability_factory is not None
        or bool(getattr(factory, "live_enabled", False))
    )
    if has_live_authority != (live_runtime_factory is not None):
        raise ValueError(
            "live provider authority and live_runtime_factory must be supplied together"
        )
    if (roster_path is None) == (catalog_index_path is None):
        raise ValueError("exactly one of roster_path or catalog_index_path is required")
    overlay = load_application_overlay(overlay_path)
    model_catalog = None
    catalog_pilot_registry = None
    catalog_source_overlays: Mapping[str, ModelSOApplicationOverlay] = {}
    if catalog_index_path is not None:
        model_catalog, catalog_source_overlays = load_model_catalog_runtime_sources(
            catalog_index_path
        )
        _, overlay = load_model_catalog_runtime_overlay(catalog_index_path, overlay)
        catalog_pilot_registry = load_model_catalog_pilot_registry(catalog_index_path)
        roster = model_catalog.to_roster_binding()
    else:
        assert roster_path is not None
        roster = _load_yaml_model(roster_path, ModelSOPlayerRosterBinding)
    if bool(getattr(factory, "live_enabled", False)):
        live_provider_capability_factory = _injected_live_provider_capability_factory(
            max_completions=live_max_completions,
            canonical_overlay=overlay,
        )
    has_live_authority = (
        live_provider_capability is not None or live_provider_capability_factory is not None
    )
    if has_live_authority != (live_runtime_factory is not None):
        raise ValueError(
            "live provider authority and live_runtime_factory must be supplied together"
        )
    session = _load_yaml_model(session_path, ModelSOAuthenticatedSession)
    red_loadout = load_loadout(red_loadout_path)
    blue_loadout = load_loadout(blue_loadout_path)
    loadouts = {red_loadout.id: red_loadout, blue_loadout.id: blue_loadout}
    if catalog_index_path is not None:
        for loadout_id, catalog_loadout in load_model_catalog_loadouts(catalog_index_path).items():
            existing = loadouts.get(loadout_id)
            if existing is not None and existing != catalog_loadout:
                raise ValueError(
                    f"catalog loadout conflicts with explicit launch loadout: {loadout_id!r}"
                )
            loadouts[loadout_id] = catalog_loadout

    runtime_factory: Callable[[ModelSOApplicationOverlay], RuntimeDependencies]
    selected_runtime_factory: (
        Callable[
            [ModelSOApplicationOverlay, str | tuple[str, ...], tuple[str, ...]], RuntimeDependencies
        ]
        | None
    ) = live_runtime_factory
    if catalog_pilot_registry is not None:

        def runtime_factory(runtime_overlay: ModelSOApplicationOverlay) -> RuntimeDependencies:
            return factory.runtime(runtime_overlay, pilot_registry=catalog_pilot_registry)

        if live_runtime_factory is not None:

            def selected_runtime_factory(
                runtime_overlay: ModelSOApplicationOverlay,
                provider_selection: str | tuple[str, ...],
                pilot_spec_ids: tuple[str, ...],
            ) -> RuntimeDependencies:
                return factory.selected_runtime(
                    runtime_overlay,
                    provider_selection,
                    pilot_spec_ids,
                    pilot_registry=catalog_pilot_registry,
                )
    else:
        runtime_factory = factory.runtime
    sessions = _ConfiguredSessionCapability(session)
    allowed_origins = _loopback_origin_aliases(origin)

    def authenticate(candidate_origin: str) -> tuple[str, str] | None:
        if candidate_origin not in allowed_origins:
            return None
        return session.principal_id, session.session_id

    def session_factory(
        request: ModelSOBrowserStartMatchRequest,
        transport: ModelSOBrowserRequestContext,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> BrowserPlaySession:
        options = {option.option_id: option for option in roster.options}
        claims = tuple(
            ModelSOHumanSeatAuthorityClaim(
                side=selection.side,
                principal_id=principal_id,
                session_id=session_id,
            )
            for selection in request.command.selections
            if options[selection.option_id].kind == "human"
        )
        context = ModelSOStartMatchAuthorityContext(
            creator_principal_id=principal_id,
            creator_session_id=session_id,
            human_seats=claims,
        )
        selected_overlay = overlay
        if model_catalog is not None:
            selected_overlay = _catalog_selection_overlay(
                overlay=overlay,
                catalog=model_catalog,
                source_overlays=catalog_source_overlays,
                request=request,
            )
        selected_live_capability: BrowserLiveProviderCapability | None = None
        if _selects_non_stub_provider(request, overlay=overlay, roster=roster):
            selected_live_capability = live_provider_capability
            if live_provider_capability_factory is not None:
                selected_live_capability = live_provider_capability_factory(
                    request,
                    context,
                    selected_overlay,
                    roster,
                )

        return launch_browser_play_session(
            overlay=selected_overlay,
            canonical_overlay=overlay,
            roster=roster,
            sessions=sessions,
            request=request,
            transport=transport,
            principal_id=principal_id,
            session_id=session_id,
            context=context,
            identity=MatchIdentity(
                match_id=request.match_id,
                correlation_id=request.command.command_id,
            ),
            loadouts=loadouts,
            runtime_factory=runtime_factory,
            pilot_registry=catalog_pilot_registry,
            live_provider_capability=selected_live_capability,
            live_runtime_factory=selected_runtime_factory,
            seed=seed,
            max_ticks=max_ticks,
            allowed_origins=allowed_origins,
        )

    return BrowserPlayServer(
        bootstrap=build_frontend_bootstrap(
            overlay,
            roster=roster,
            model_catalog=model_catalog,
        ),
        gateway=None,
        bus=None,
        authenticate=authenticate,
        host=host,
        port=port,
        session_factory=session_factory,
    )


def configured_live_browser_server(
    *,
    overlay_path: Path,
    roster_path: Path | None = None,
    catalog_index_path: Path | None = None,
    session_path: Path,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int | None,
    origin: str,
    host: str,
    port: int,
    secret_resolver: ProtocolSecretResolver,
    http_transport: ProtocolHttpTransport,
    sleeper: ProtocolSleeper | None = None,
    live_max_completions: int = 256,
) -> BrowserPlayServer:
    """Explicit live-play entrypoint for callers owning provider capabilities.

    ``play_command`` continues to use the packaged, stub-safe factory.  A
    process that has intentionally acquired provider capabilities calls this
    entrypoint and supplies them directly; no ambient discovery is performed.
    """

    return _configured_browser_server(
        overlay_path=overlay_path,
        roster_path=roster_path,
        catalog_index_path=catalog_index_path,
        session_path=session_path,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
        origin=origin,
        host=host,
        port=port,
        application_factory=CliApplicationFactory.live(
            secret_resolver=secret_resolver,
            http_transport=http_transport,
            sleeper=sleeper,
        ),
        live_max_completions=live_max_completions,
    )


async def _serve_browser_play(server: BrowserPlayServer, *, bootstrap_output: Path | None) -> None:
    await server.start()
    try:
        payload = server.bootstrap.model_dump_json(indent=2) + "\n"
        if bootstrap_output is not None:
            bootstrap_output.write_text(payload, encoding="utf-8")
        click.echo(f"bootstrap_url: {server.bootstrap_url}")
        click.echo(f"events_url: {server.event_url}")
        click.echo(f"commands_url: {server.command_url}")
        await asyncio.Event().wait()
    finally:
        await server.stop()


@click.command(name="play")
@click.option(
    "--overlay",
    "overlay_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--roster",
    "roster_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Explicit player roster; mutually exclusive with --catalog-index.",
)
@click.option(
    "--catalog-index",
    "catalog_index_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Explicit multi-provider catalog source index; mutually exclusive with --roster.",
)
@click.option(
    "--session",
    "session_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--loadout-red",
    "red_loadout_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--loadout-blue",
    "blue_loadout_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--seed", type=click.IntRange(min=0), required=True)
@click.option(
    "--max-ticks",
    type=click.IntRange(min=1),
    default=None,
    help="Optional debug/test cap. Omit for normal winner-only matches.",
)
@click.option("--origin", default="http://localhost:5173", show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=click.IntRange(min=0, max=65_535), default=0, show_default=True)
@click.option("--bootstrap-output", type=click.Path(dir_okay=False, path_type=Path), default=None)
def play_command(
    overlay_path: Path,
    roster_path: Path | None,
    catalog_index_path: Path | None,
    session_path: Path,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int | None,
    origin: str,
    host: str,
    port: int,
    bootstrap_output: Path | None,
) -> None:
    """Run one configured, process-local browser match server."""

    server = _configured_browser_server(
        overlay_path=overlay_path,
        roster_path=roster_path,
        catalog_index_path=catalog_index_path,
        session_path=session_path,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
        origin=origin,
        host=host,
        port=port,
    )
    try:
        asyncio.run(_serve_browser_play(server, bootstrap_output=bootstrap_output))
    except KeyboardInterrupt:
        click.echo("play interrupted", err=True)


@click.command(name="play-live")
@click.option(
    "--overlay",
    "overlay_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--roster",
    "roster_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Explicit player roster; mutually exclusive with --catalog-index.",
)
@click.option(
    "--catalog-index",
    "catalog_index_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Explicit multi-provider catalog source index; mutually exclusive with --roster.",
)
@click.option(
    "--session",
    "session_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--loadout-red",
    "red_loadout_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--loadout-blue",
    "blue_loadout_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--seed", type=click.IntRange(min=0), required=True)
@click.option(
    "--max-ticks",
    type=click.IntRange(min=1),
    default=None,
    help="Optional debug/test cap. Omit for the configured sudden-death horizon.",
)
@click.option("--origin", default="http://localhost:5173", show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=click.IntRange(min=0, max=65_535), default=0, show_default=True)
@click.option("--bootstrap-output", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option(
    "--glm-api-key",
    envvar="LLM_GLM_API_KEY",
    required=False,
    hide_input=True,
    help="Injected GLM credential; defaults to LLM_GLM_API_KEY.",
)
@click.option(
    "--openrouter-api-key",
    envvar="OPENROUTER_API_KEY",
    required=False,
    hide_input=True,
    help="Injected OpenRouter credential; defaults to OPENROUTER_API_KEY.",
)
@click.option(
    "--gemini-api-key",
    envvar="GEMINI_API_KEY",
    required=False,
    hide_input=True,
    help="Injected Gemini credential; defaults to GEMINI_API_KEY.",
)
def play_live_command(
    overlay_path: Path,
    roster_path: Path | None,
    catalog_index_path: Path | None,
    session_path: Path,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int | None,
    origin: str,
    host: str,
    port: int,
    bootstrap_output: Path | None,
    glm_api_key: str | None,
    openrouter_api_key: str | None,
    gemini_api_key: str | None,
) -> None:
    """Run a browser match with explicitly injected provider authority.

    Unlike ``so play``, this command is intentionally not stub-safe: it
    requires at least one credential for the overlay's configured live
    providers.  The browser roster selects which configured model/provider is
    used; this command only injects credentials for the overlay's opaque secret
    references.  The HTTP client is root-owned here and is never discovered by
    runtime composition.
    """

    if not any((glm_api_key, openrouter_api_key, gemini_api_key)):
        raise click.ClickException(
            "provide at least one live credential via --glm-api-key, "
            "--openrouter-api-key, or --gemini-api-key"
        )
    secret_resolver = _InjectedSecretResolver.from_cli(
        glm_api_key=glm_api_key,
        openrouter_api_key=openrouter_api_key,
        gemini_api_key=gemini_api_key,
    )

    # The explicit live overlay owns its filesystem destinations.  Create
    # those destinations at this process boundary so SQLite can open them;
    # composition still receives only the validated, resolved overlay.
    overlay = load_application_overlay(overlay_path)
    for directory in (
        overlay.event_ledger.path.parent,
        overlay.leaderboard.path.parent,
        overlay.learning_artifacts.evaluation_root,
        overlay.learning_artifacts.lineage_root,
        overlay.learning_artifacts.experiment_root,
        overlay.evaluation_storage.root,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    try:
        server = configured_live_browser_server(
            overlay_path=overlay_path,
            roster_path=roster_path,
            catalog_index_path=catalog_index_path,
            session_path=session_path,
            red_loadout_path=red_loadout_path,
            blue_loadout_path=blue_loadout_path,
            seed=seed,
            max_ticks=max_ticks,
            origin=origin,
            host=host,
            port=port,
            secret_resolver=secret_resolver,
            http_transport=_UrllibJsonTransport(),
        )
        try:
            asyncio.run(_serve_browser_play(server, bootstrap_output=bootstrap_output))
        except KeyboardInterrupt:
            click.echo("play-live interrupted", err=True)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


__all__ = [
    "BrowserPlayServer",
    "BrowserPlaySession",
    "configured_live_browser_server",
    "launch_browser_play_session",
    "play_command",
    "play_live_command",
]
