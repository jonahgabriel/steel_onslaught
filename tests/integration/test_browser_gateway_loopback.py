"""End-to-end process-local browser gateway proof without network/provider I/O."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
import ulid

from steel_onslaught.cli.play import BrowserPlayServer, BrowserPlaySession
from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    ModelSOStartMatchAuthorityContext,
)
from steel_onslaught.commands.browser_gateway import (
    BrowserCommandGateway,
    ModelSOBrowserActionAccepted,
    ModelSOBrowserActionRequest,
    ModelSOBrowserRequestContext,
    ModelSOBrowserStartAccepted,
    ModelSOBrowserStartMatchRequest,
)
from steel_onslaught.commands.inbox import HumanDecisionCancelledError, ModelSOHumanActionAdmission
from steel_onslaught.contracts.application import (
    ModelSOFrontendBootstrap,
    ModelSOFrontendTransportBinding,
)
from steel_onslaught.contracts.commands import (
    ModelSOHumanTurnPrompt,
    ModelSOPlayerActionCommand,
    ModelSORemainPlayerAction,
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
    canonical_command_sha256,
)
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOMatchLaunchProvenance,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

_PRINCIPAL = "principal.browser"
_SESSION = "session.browser"
_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_START_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_ACTION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


def _bootstrap() -> ModelSOFrontendBootstrap:
    return ModelSOFrontendBootstrap(
        schema_version="1",
        kind="steel_onslaught.frontend_bootstrap",
        overlay_sha256="a" * 64,
        frontend_transport=ModelSOFrontendTransportBinding(
            kind="websocket",
            contract="steel_onslaught.frontend_transport.v1",
            websocket_url="ws://127.0.0.1:1/events",
            event_schema="canonical_event_v1",
            milliseconds_per_tick=1,
        ),
    )


class _Sessions:
    def resolve(self, *, principal_id: str, session_id: str) -> ModelSOAuthenticatedSession | None:
        if (principal_id, session_id) != (_PRINCIPAL, _SESSION):
            return None
        return ModelSOAuthenticatedSession(
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
            human_identity_id="human_identity.browser",
            permissions=("match:create", "seat:red"),
        )


def _roster() -> ModelSOPlayerRosterBinding:
    human = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser human",
        human_identity_id="human_identity.browser",
        pilot_spec_id="pilot.human.browser",
        input_source="browser_command",
    )
    model = ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id="player_option.local_stub",
        display_name="Local stub",
        model_identity_id="model_identity.local_stub",
        pilot_spec_id="pilot.llm.qwen35",
        persona_id="berserker",
        input_source="llm_completion",
    )
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.browser",
        options=(human, model),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.browser.red",
                allowed_option_ids=(human.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.browser.blue",
                allowed_option_ids=(model.option_id,),
            ),
        ),
    )


def _start_request() -> ModelSOBrowserStartMatchRequest:
    command = ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=_START_ID,
        expected_overlay_sha256="1" * 64,
        expected_roster_sha256="2" * 64,
        selections=(
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.local_stub"),
        ),
    )
    return ModelSOBrowserStartMatchRequest(match_id=_MATCH_ID, command=command)


def _action_request() -> ModelSOBrowserActionRequest:
    command = ModelSOPlayerActionCommand(
        schema_version="1",
        kind="steel_onslaught.player_action",
        command_id=_ACTION_ID,
        match_id=_MATCH_ID,
        turn_id="turn.red.000001",
        expected_tick=1,
        observation_sha256="f" * 64,
        action=ModelSORemainPlayerAction(kind="remain"),
    )
    return ModelSOBrowserActionRequest(side="red", command=command)


@pytest.mark.unit
def test_browser_server_rejects_pre_admitted_session_startup() -> None:
    """A pre-admitted session would let refresh launch without Start Match."""
    with pytest.raises(ValueError, match="sole launch authority"):
        BrowserPlayServer(
            bootstrap=_bootstrap(),
            gateway=None,
            bus=None,
            authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
            session=cast(BrowserPlaySession, object()),
        )


@pytest.mark.integration
def test_local_stub_gateway_session_has_one_start_action_replay_and_close() -> None:
    sessions = _Sessions()
    roster = _roster()
    request = _start_request()
    trace = ["MATCH_STARTED", "MATCH_TICK", "PILOT_DECISION_MADE", "MATCH_ENDED"]
    closed: list[bool] = []
    run_count = 0

    provenance = SimpleNamespace(
        launch_command_id=request.command.command_id,
        launch_command_sha256=canonical_command_sha256(request.command),
        match_id=_MATCH_ID,
        overlay_sha256="b" * 64,
        roster_sha256="c" * 64,
    )

    class Start:
        def admit_start_match(
            self,
            command: ModelSOStartMatchCommand,
            *,
            context: ModelSOStartMatchAuthorityContext,
            match_id: str,
        ) -> ModelSOMatchLaunchProvenance:
            del context, match_id
            assert command == request.command
            return cast(ModelSOMatchLaunchProvenance, provenance)

    class Human:
        calls = 0

        def submit_action(
            self, command: ModelSOPlayerActionCommand, **_: object
        ) -> ModelSOHumanActionAdmission:
            self.calls += 1
            return ModelSOHumanActionAdmission(
                command_id=command.command_id,
                command_sha256=canonical_command_sha256(command),
                principal_id=_PRINCIPAL,
                session_id=_SESSION,
                side="red",
                prompt_sha256="e" * 64,
            )

    human = Human()
    gateway = BrowserCommandGateway(
        sessions=sessions,
        roster=roster,
        start_coordinator=Start(),
        human_coordinator=human,
        allowed_origins=("http://localhost:5173",),
    )

    class Runner:
        def run(self) -> tuple[str, ...]:
            nonlocal run_count
            run_count += 1
            return tuple(trace)

    stack = SimpleNamespace(
        match_id=_MATCH_ID,
        launch_provenance=provenance,
        human_inbox=human,
        runner=Runner(),
        close=lambda: closed.append(True),
    )
    session = BrowserPlaySession(
        stack=stack,  # type: ignore[arg-type]
        gateway=gateway,
        start_result=gateway.start_match(
            request,
            transport=ModelSOBrowserRequestContext(
                origin="http://localhost:5173", host="127.0.0.1:8765"
            ),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
        ),
    )

    accepted = session.submit_action(
        _action_request(),
        transport=ModelSOBrowserRequestContext(
            origin="http://localhost:5173", host="127.0.0.1:8765"
        ),
        principal_id=_PRINCIPAL,
        session_id=_SESSION,
    )
    assert accepted.outcome == "accepted"
    assert human.calls == 1
    live_trace = cast(object, session.run())
    replay_trace = tuple(trace)
    assert live_trace == replay_trace
    assert run_count == 1
    session.close()
    session.close()
    assert closed == [True]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ephemeral_server_authenticates_commands_and_rejects_event_writes() -> None:
    import asyncio
    import json

    import websockets

    class Gateway:
        def start_match(self, request: object, **_: object) -> object:
            del request
            return SimpleNamespace(model_dump_json=lambda: json.dumps({"outcome": "accepted"}))

        def submit_action(self, request: object, **_: object) -> object:
            del request
            return SimpleNamespace(model_dump_json=lambda: json.dumps({"outcome": "accepted"}))

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=Gateway(),  # type: ignore[arg-type]
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda origin: (
            ("principal.browser", "session.browser") if origin == "http://localhost:5173" else None
        ),
        port=0,
    )
    await server.start()
    try:
        assert server.bootstrap.command_gateway is not None
        assert server.bootstrap.frontend_transport.websocket_url.endswith("/events")
        assert server.bootstrap.command_gateway.websocket_url.endswith("/commands")
        async with websockets.connect(server.event_url) as events:
            await events.send("client must not publish events")
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(events.recv(), timeout=2)

        async with websockets.connect(
            server.command_url,
            additional_headers={"Origin": "http://localhost:5173"},
        ) as commands:
            await commands.send(
                json.dumps(
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.browser_start_intent",
                        "request_id": str(_START_ID),
                        "intent": {
                            "expected_overlay_sha256": "1" * 64,
                            "roster_id": "roster.browser",
                            "expected_roster_sha256": "2" * 64,
                            "selections": [
                                {"side": "red", "option_id": "player_option.browser_human"},
                                {"side": "blue", "option_id": "player_option.local_stub"},
                            ],
                        },
                    }
                )
            )
            start_response = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert start_response["outcome"] == "accepted"
            await commands.send(
                json.dumps(
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.browser_player_action",
                        "request_id": str(_ACTION_ID),
                        "action": {
                            "match_id": _MATCH_ID,
                            "side": "red",
                            "turn_id": "turn.red.000001",
                            "expected_tick": 1,
                            "observation_sha256": "f" * 64,
                            "action": {"kind": "remain"},
                        },
                    }
                )
            )
            action_response = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert action_response["outcome"] == "accepted"
            await commands.send(
                json.dumps(
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.browser_cancel",
                        "request_id": "request.cancel.01",
                    }
                )
            )
            response = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert response["outcome"] == "cancelled"

        with pytest.raises((websockets.ConnectionClosed, websockets.InvalidStatus)):
            async with websockets.connect(
                server.command_url,
                additional_headers={"Origin": "https://evil.example"},
            ):
                pass
    finally:
        await server.stop()
    assert server.closed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_socket_replays_match_started_when_opened_after_emission() -> None:
    """A late browser event handshake must not start at tick one.

    The command socket can admit a match before the event socket finishes its
    handshake. The server therefore replays its process-local canonical event
    prefix to the newly connected receive-only stream.
    """
    import asyncio
    import json

    import websockets

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    event = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))
    await server.start()
    try:
        # Emulate the runner emitting MATCH_STARTED before the browser's
        # receive socket completes its handshake.
        server._on_event(event)
        await asyncio.sleep(0)
        async with websockets.connect(server.event_url) as events:
            replayed = json.loads(await asyncio.wait_for(events.recv(), timeout=2))
            assert replayed["event_type"] == "match_started"
            assert replayed["tick"] == 0
            assert replayed["sequence_in_tick"] == 0
    finally:
        await server.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_after_terminal_retirement_does_not_replay_old_match() -> None:
    """Server readiness is empty; refresh must not look like a new launch."""
    import asyncio

    import websockets

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))
    terminal = started.model_copy(
        update={
            "event_id": ulid.new().str,
            "event_type": SOEventType.MATCH_ENDED,
            "tick": 1,
            "sequence_in_tick": 0,
            "payload": {"reason": "aborted", "winner_id": None},
            "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
        }
    )
    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    await server.start()
    server._session = SimpleNamespace(
        match_id=started.match_id,
        stack=SimpleNamespace(runtime=None),
        close=lambda: None,
    )  # type: ignore[assignment]
    server._loop = asyncio.get_running_loop()
    try:
        server._on_event(started)
        server._on_event(terminal)
        await asyncio.sleep(0)
        assert [event.event_type for event in server._event_history] == [
            SOEventType.MATCH_STARTED,
            SOEventType.MATCH_ENDED,
        ]

        await server._retire_completed_session()
        assert server._event_history == []
        async with websockets.connect(server.event_url) as events:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(events.recv(), timeout=0.05)
    finally:
        await server.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_late_event_socket_gets_one_shot_prefix_after_admitted_fast_match() -> None:
    """A start-before-events race remains recoverable without making refresh a launch."""
    import asyncio
    import json

    import websockets

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    class Gateway:
        def start_match(self, request: ModelSOBrowserStartMatchRequest, **_: object) -> object:
            return ModelSOBrowserStartAccepted(
                command_id=request.command.command_id,
                command_sha256="d" * 64,
                match_id=request.match_id,
                overlay_sha256="a" * 64,
                roster_sha256="b" * 64,
            )

    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(
        fixture.read_text(encoding="utf-8")
    ).model_copy(update={"match_id": _MATCH_ID})
    terminal = started.model_copy(
        update={
            "event_id": ulid.new().str,
            "event_type": SOEventType.MATCH_ENDED,
            "tick": 1,
            "sequence_in_tick": 0,
            "payload": {"reason": "aborted", "winner_id": None},
            "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
        }
    )
    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=Gateway(),  # type: ignore[arg-type]
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    await server.start()
    server._loop = asyncio.get_running_loop()
    request = _start_request()
    try:
        # No /events client is connected when the browser's Start Match intent
        # is admitted, which is the race exercised by the live UI.
        accepted = await server._admit_start(
            request,
            transport=ModelSOBrowserRequestContext(
                origin="http://localhost:5173", host="127.0.0.1:1"
            ),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
        )
        assert json.loads(accepted)["outcome"] == "accepted"
        server._session = SimpleNamespace(
            match_id=started.match_id,
            stack=SimpleNamespace(runtime=None),
            close=lambda: None,
        )  # type: ignore[assignment]
        server._on_event(started)
        server._on_event(terminal)
        await asyncio.sleep(0)
        await server._retire_completed_session()
        assert server._late_replay_pending is True
        assert [event.event_type for event in server._event_history] == [
            SOEventType.MATCH_STARTED,
            SOEventType.MATCH_ENDED,
        ]

        async with websockets.connect(server.event_url) as events:
            replayed = [
                json.loads(await asyncio.wait_for(events.recv(), timeout=2)) for _ in range(2)
            ]
            assert [frame["event_type"] for frame in replayed] == [
                "match_started",
                "match_ended",
            ]
            assert server._late_replay_pending is False
            assert server._event_history == []

        async with websockets.connect(server.event_url) as refreshed:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(refreshed.recv(), timeout=0.05)
    finally:
        await server.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_late_event_socket_does_not_consume_retained_prefix() -> None:
    """A failed first replay leaves MATCH_STARTED available for reconnect."""
    import asyncio
    import json

    class FakeConnection:
        def __init__(self, *, fail_send: bool) -> None:
            self.fail_send = fail_send
            self.frames: list[str] = []

        async def send(self, frame: str) -> None:
            if self.fail_send:
                raise OSError("socket closed before replay delivery")
            self.frames.append(frame)

        async def close(self, **_: object) -> None:
            return None

        def __aiter__(self) -> FakeConnection:
            return self

        async def __anext__(self) -> str:
            await asyncio.Future()
            raise StopAsyncIteration

    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(
        fixture.read_text(encoding="utf-8")
    ).model_copy(update={"match_id": _MATCH_ID})
    terminal = started.model_copy(
        update={
            "event_id": ulid.new().str,
            "event_type": SOEventType.MATCH_ENDED,
            "tick": 1,
            "sequence_in_tick": 0,
            "payload": {"reason": "aborted", "winner_id": None},
            "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
        }
    )
    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=None,
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    server._loop = asyncio.get_running_loop()
    server._late_replay_match_id = _MATCH_ID
    server._late_replay_pending = True
    server._event_history = [started, terminal]
    server._event_history_ids = {started.event_id, terminal.event_id}
    try:
        failed = FakeConnection(fail_send=True)
        await server._handle_event_client(failed)  # type: ignore[arg-type]
        assert server._late_replay_pending is True
        assert [event.event_type for event in server._event_history] == [
            SOEventType.MATCH_STARTED,
            SOEventType.MATCH_ENDED,
        ]

        recovered = FakeConnection(fail_send=False)
        task = asyncio.create_task(server._handle_event_client(recovered))  # type: ignore[arg-type]
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [json.loads(frame)["event_type"] for frame in recovered.frames] == [
            "match_started",
            "match_ended",
        ]
        assert server._late_replay_pending is False
        assert server._event_history == []
    finally:
        server._loop = None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_socket_serializes_same_tick_frames_in_canonical_order() -> None:
    """Rapid cross-thread callbacks must not invert same-tick wire frames."""
    import asyncio
    import json

    import websockets

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))
    same_tick = [
        started.model_copy(
            update={
                "event_id": ulid.new().str,
                "tick": 1,
                "sequence_in_tick": sequence,
                "event_type": SOEventType.MATCH_TICK,
                "payload": {},
                "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
            }
        )
        for sequence in range(3)
    ]
    await server.start()
    try:
        async with websockets.connect(server.event_url) as events:
            # Deliver the same-tick callbacks in the observed race order while
            # a client is live. Tick 2 closes the deterministic tick-1 drain.
            server._on_event(started)
            for event in (same_tick[2], same_tick[1], same_tick[0]):
                server._on_event(event)
            server._on_event(
                started.model_copy(
                    update={
                        "event_id": ulid.new().str,
                        "tick": 2,
                        "sequence_in_tick": 0,
                        "event_type": SOEventType.MATCH_TICK,
                        "payload": {},
                        "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
                    }
                )
            )
            await asyncio.sleep(0)
            frames = [
                json.loads(await asyncio.wait_for(events.recv(), timeout=2)) for _ in range(4)
            ]
            assert [(frame["tick"], frame["sequence_in_tick"]) for frame in frames] == [
                (0, 0),
                (1, 0),
                (1, 1),
                (1, 2),
            ]
    finally:
        await server.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_socket_quarantines_late_tick_without_leaking_or_reordering() -> None:
    """A late callback cannot append a frame behind an already-published tick."""
    import asyncio
    import json

    import websockets

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))

    def tick_event(
        tick: int, sequence: int, *, event_id: str | None = None
    ) -> ModelSOEventEnvelope:
        return started.model_copy(
            update={
                "event_id": event_id or ulid.new().str,
                "tick": tick,
                "sequence_in_tick": sequence,
                "event_type": SOEventType.MATCH_TICK,
                "payload": {},
                "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
            }
        )

    tick_one = tick_event(1, 0)
    tick_two = tick_event(2, 0)
    tick_three = tick_event(3, 0)
    late_tick_one = tick_event(1, 1)
    await server.start()
    try:
        async with websockets.connect(server.event_url) as events:
            server._on_event(started)
            server._on_event(tick_one)
            server._on_event(tick_two)
            server._on_event(tick_three)
            await asyncio.sleep(0.01)
            # Tick two flushes tick one, while tick three remains buffered;
            # therefore the already-published history ends at tick two.

            # The callback is a duplicate delivery of a tick already drained.
            server._on_event(late_tick_one)
            server._on_event(late_tick_one)
            await asyncio.sleep(0.01)

            frames = [
                json.loads(await asyncio.wait_for(events.recv(), timeout=2)) for _ in range(3)
            ]
            assert [(frame["tick"], frame["sequence_in_tick"]) for frame in frames] == [
                (0, 0),
                (1, 0),
                (2, 0),
            ]
            assert all(frame["event_id"] != late_tick_one.event_id for frame in frames)
            assert [(event.tick, event.sequence_in_tick) for event in server._event_history] == [
                (0, 0),
                (1, 0),
                (2, 0),
            ]
            assert late_tick_one.event_id in server._quarantined_event_ids
    finally:
        await server.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_socket_preserves_same_tick_order_and_duplicate_suppression() -> None:
    """Out-of-arrival-order callbacks still drain once in sequence order."""
    import asyncio
    import json

    import websockets

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))

    def tick_event(
        tick: int, sequence: int, *, event_id: str | None = None
    ) -> ModelSOEventEnvelope:
        return started.model_copy(
            update={
                "event_id": event_id or ulid.new().str,
                "tick": tick,
                "sequence_in_tick": sequence,
                "event_type": SOEventType.MATCH_TICK,
                "payload": {},
                "envelope": started.envelope.model_copy(update={"message_id": uuid4()}),
            }
        )

    same_tick = [tick_event(1, sequence) for sequence in range(3)]
    await server.start()
    try:
        async with websockets.connect(server.event_url) as events:
            server._on_event(started)
            for event in (same_tick[2], same_tick[0], same_tick[1]):
                server._on_event(event)
            server._on_event(tick_event(1, 1, event_id=same_tick[1].event_id))
            server._on_event(tick_event(1, 0, event_id=same_tick[0].event_id))
            server._on_event(tick_event(2, 0))
            await asyncio.sleep(0.01)

            # Duplicate callbacks after the tick drained are suppressed by
            # the history id set just as pending duplicates are.
            server._on_event(tick_event(1, 1, event_id=same_tick[1].event_id))
            await asyncio.sleep(0.01)

            frames = [
                json.loads(await asyncio.wait_for(events.recv(), timeout=2)) for _ in range(4)
            ]
            assert [(frame["tick"], frame["sequence_in_tick"]) for frame in frames] == [
                (0, 0),
                (1, 0),
                (1, 1),
                (1, 2),
            ]
            assert len(server._event_history) == 4
            assert len({event.event_id for event in server._event_history}) == 4
    finally:
        await server.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_start_replay_runs_match_and_forwards_authoritative_prompt() -> None:
    import asyncio
    import json

    import websockets

    prompt_ready = threading.Event()
    cancelled = threading.Event()
    run_started = threading.Event()
    factory_calls = 0
    start_calls = 0
    lifecycle_order: list[str] = []

    prompt = ModelSOHumanTurnPrompt(
        schema_version="1",
        kind="steel_onslaught.human_turn",
        match_id=_MATCH_ID,
        turn_id="turn.red.000001",
        side="red",
        expected_tick=1,
        observation_sha256="f" * 64,
        available_actions=(ModelSORemainPlayerAction(kind="remain"),),
    )

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    class HumanInbox:
        def wait_for_prompt(self, **kwargs: object) -> ModelSOHumanTurnPrompt:
            after_tick = kwargs["after_tick"]
            if after_tick == -1:
                assert prompt_ready.wait(2)
                return prompt
            assert cancelled.wait()
            raise HumanDecisionCancelledError("test cancellation")

        def submit_action(self, **_: object) -> object:
            return SimpleNamespace()

    class Runner:
        def run(self) -> None:
            lifecycle_order.append("run")
            run_started.set()
            cancelled.wait(2)

    class Gateway:
        def start_match(self, request: ModelSOBrowserStartMatchRequest, **_: object) -> object:
            nonlocal start_calls
            start_calls += 1
            lifecycle_order.append("start")
            return ModelSOBrowserStartAccepted(
                command_id=request.command.command_id,
                command_sha256="d" * 64,
                match_id=request.match_id,
                overlay_sha256="a" * 64,
                roster_sha256="b" * 64,
            )

        def submit_action(self, request: ModelSOBrowserActionRequest, **_: object) -> object:
            return ModelSOBrowserActionAccepted(
                command_id=request.command.command_id,
                command_sha256="e" * 64,
                match_id=request.command.match_id,
                turn_id=request.command.turn_id,
                expected_tick=request.command.expected_tick,
                side=request.side,
                prompt_sha256="c" * 64,
            )

    stack = SimpleNamespace(
        match_id=_MATCH_ID,
        launch_provenance=SimpleNamespace(
            seat_assignments=(SimpleNamespace(kind="human", side="red"),)
        ),
        human_inbox=HumanInbox(),
        runner=Runner(),
        bus=Bus(),
        close=lambda: cancelled.set(),
    )

    def session_factory(
        request: ModelSOBrowserStartMatchRequest,
        _transport: ModelSOBrowserRequestContext,
        _principal_id: str,
        _session_id: str,
    ) -> BrowserPlaySession:
        nonlocal factory_calls
        factory_calls += 1
        return BrowserPlaySession(
            stack=stack,  # type: ignore[arg-type]
            gateway=Gateway(),  # type: ignore[arg-type]
            start_result=SimpleNamespace(match_id=request.match_id),  # type: ignore[arg-type]
        )

    server = BrowserPlayServer(
        bootstrap=_bootstrap(),
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda origin: (
            (_PRINCIPAL, _SESSION) if origin == "http://localhost:5173" else None
        ),
        session_factory=session_factory,
    )
    await server.start()
    try:
        async with websockets.connect(
            server.command_url,
            additional_headers={"Origin": "http://localhost:5173"},
        ) as commands:
            start_frame = {
                "schema_version": "1",
                "kind": "steel_onslaught.browser_start_intent",
                "request_id": str(_START_ID),
                "intent": {
                    "expected_overlay_sha256": "a" * 64,
                    "roster_id": "roster.browser",
                    "expected_roster_sha256": "b" * 64,
                    "selections": [
                        {"side": "red", "option_id": "player_option.browser_human"},
                        {"side": "blue", "option_id": "player_option.local_stub"},
                    ],
                },
            }
            await commands.send(json.dumps(start_frame))
            accepted = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert accepted["outcome"] == "accepted"
            prompt_ready.set()
            received_prompt = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert received_prompt["kind"] == "steel_onslaught.human_turn"
            await commands.send(
                json.dumps(
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.browser_player_action",
                        "request_id": str(_ACTION_ID),
                        "action": {
                            "match_id": _MATCH_ID,
                            "side": "red",
                            "turn_id": received_prompt["turn_id"],
                            "expected_tick": received_prompt["expected_tick"],
                            "observation_sha256": received_prompt["observation_sha256"],
                            "action": {"kind": "remain"},
                        },
                    }
                )
            )
            action_result = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert action_result["outcome"] == "accepted"
            async with websockets.connect(
                server.command_url,
                additional_headers={"Origin": "http://localhost:5173"},
            ) as reconnected:
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(reconnected.recv(), timeout=0.1)
            await commands.send(json.dumps(start_frame))
            replay = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert replay == accepted
            conflicting = json.loads(json.dumps(start_frame))
            conflicting["intent"]["expected_overlay_sha256"] = "c" * 64
            await commands.send(json.dumps(conflicting))
            failure = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert failure["outcome"] == "failed"
            await commands.send(
                json.dumps(
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.browser_cancel",
                        "request_id": "cancel.request.01",
                    }
                )
            )
            cancelled_result = json.loads(await asyncio.wait_for(commands.recv(), timeout=2))
            assert cancelled_result["outcome"] == "cancelled"
    finally:
        cancelled.set()
        await server.stop()
    assert factory_calls == 1
    assert start_calls == 1
    assert lifecycle_order[:2] == ["start", "run"]
    assert run_started.is_set()
    assert server.closed
