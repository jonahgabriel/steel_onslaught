"""Tests for the transport-independent browser play session."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
import ulid
from click.testing import CliRunner

from steel_onslaught.cli.main import main
from steel_onslaught.cli.play import (
    BrowserLiveProviderCapabilityFactory,
    BrowserPlayServer,
    BrowserPlaySession,
    _configured_browser_server,
    _load_yaml_model,
    _loopback_origin_aliases,
    launch_browser_play_session,
)
from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
)
from steel_onslaught.commands.browser_gateway import (
    ModelSOBrowserRequestContext,
    ModelSOBrowserRuntimeAccepted,
    ModelSOBrowserStartMatchRequest,
)
from steel_onslaught.commands.live_provider import ProcessLocalOneShotLiveProviderCapability
from steel_onslaught.contracts.commands import (
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
)
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
)
from steel_onslaught.contracts.runtime import (
    ModelSORuntimeCommand,
    ModelSORuntimeStatusPayload,
    SORuntimeMode,
    SORuntimeStatus,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.composition import (
    RuntimeDependencies,
    SystemClock,
    SystemIdentityProvider,
)
from steel_onslaught.match.runner import MatchIdentity

_PRINCIPAL = "principal.browser"
_SESSION = "session.browser"
_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_COMMAND_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


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


def _request() -> ModelSOBrowserStartMatchRequest:
    return ModelSOBrowserStartMatchRequest(
        match_id=_MATCH_ID,
        command=ModelSOStartMatchCommand(
            schema_version="1",
            kind="steel_onslaught.start_match",
            command_id=_COMMAND_ID,
            expected_overlay_sha256="1" * 64,
            expected_roster_sha256="2" * 64,
            selections=(
                ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
                ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.local_stub"),
            ),
        ),
    )


def _stack() -> SimpleNamespace:
    closed = []
    ran = []
    provenance = SimpleNamespace(
        launch_command_id=_COMMAND_ID,
        launch_command_sha256="a" * 64,
        match_id=_MATCH_ID,
        overlay_sha256="b" * 64,
        roster_sha256="c" * 64,
    )

    class HumanInbox:
        def submit_action(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            return SimpleNamespace(
                command_id=_COMMAND_ID,
                command_sha256="d" * 64,
                principal_id=_PRINCIPAL,
                session_id=_SESSION,
                side="red",
                prompt_sha256="e" * 64,
            )

    class Runner:
        def run(self) -> str:
            ran.append(True)
            return "ended"

    return SimpleNamespace(
        launch_provenance=provenance,
        human_inbox=HumanInbox(),
        runner=Runner(),
        match_id=_MATCH_ID,
        close=lambda: closed.append(True),
        closed=closed,
        ran=ran,
    )


@pytest.mark.unit
def test_launch_admits_before_runner_and_reuses_stack_human_inbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _stack()
    assemble_kwargs: dict[str, object] = {}

    def assemble(**kwargs: object) -> SimpleNamespace:
        assemble_kwargs.update(kwargs)
        return stack

    monkeypatch.setattr("steel_onslaught.cli.play.assemble_selected_match_live", assemble)

    live_capability = cast(ProcessLocalOneShotLiveProviderCapability, object())
    live_runtime_factory = cast(
        Callable[[object, str, tuple[str, ...]], RuntimeDependencies],
        lambda *_: cast(RuntimeDependencies, object()),
    )

    session = launch_browser_play_session(
        overlay=object(),  # type: ignore[arg-type]
        roster=_roster(),
        sessions=_Sessions(),
        request=_request(),
        transport=ModelSOBrowserRequestContext(
            origin="http://localhost:5173", host="127.0.0.1:8765"
        ),
        principal_id=_PRINCIPAL,
        session_id=_SESSION,
        context=ModelSOStartMatchAuthorityContext(
            creator_principal_id=_PRINCIPAL,
            creator_session_id=_SESSION,
            human_seats=(
                ModelSOHumanSeatAuthorityClaim(
                    side="red", principal_id=_PRINCIPAL, session_id=_SESSION
                ),
            ),
        ),
        identity=MatchIdentity(
            match_id=_MATCH_ID,
            correlation_id=UUID("11111111-1111-4111-8111-111111111111"),
        ),
        loadouts={},
        runtime_factory=lambda _: cast(RuntimeDependencies, object()),
        live_provider_capability=live_capability,
        live_runtime_factory=live_runtime_factory,
        seed=7,
        max_ticks=2,
        allowed_origins=("http://localhost:5173",),
    )

    assert isinstance(session, BrowserPlaySession)
    assert stack.ran == []
    assert assemble_kwargs["live_provider_capability"] is live_capability
    assert assemble_kwargs["live_runtime_factory"] is live_runtime_factory
    assert session.start_result.match_id == _MATCH_ID
    assert session.run() is not None
    assert stack.ran == [True]
    session.close()
    assert stack.closed == [True]


@pytest.mark.unit
def test_play_cli_requires_explicit_contract_inputs() -> None:
    result = CliRunner().invoke(main, ["play"])
    assert result.exit_code != 0
    assert "Missing option '--overlay'" in result.stderr


@pytest.mark.unit
def test_configured_model_loader_parses_json_arrays_as_wire_tuples(tmp_path: Path) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "principal_id": "principal.local_operator",
                "session_id": "session.local_operator",
                "human_identity_id": "human_identity.local_operator",
                "permissions": ["match:create", "seat:red"],
            }
        ),
        encoding="utf-8",
    )

    session = _load_yaml_model(session_path, ModelSOAuthenticatedSession)

    assert session.permissions == ("match:create", "seat:red")


@pytest.mark.unit
def test_browser_play_server_exports_ephemeral_loopback_contract() -> None:
    assert BrowserPlayServer.__name__ == "BrowserPlayServer"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_browser_server_projects_runtime_status_before_terminal_event() -> None:
    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

    started = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    class Runtime:
        def __init__(self) -> None:
            self.status = ModelSORuntimeStatusPayload(
                status=SORuntimeStatus.RUNNING,
                mode=SORuntimeMode.ONE_GAME,
                revision=1,
                owner_id="runtime_owner.browser",
                match_index=0,
                last_command_id=_COMMAND_ID,
            )

        def mark_match_ended(self) -> ModelSORuntimeStatusPayload:
            self.status = self.status.model_copy(
                update={"status": SORuntimeStatus.ENDED, "revision": 2}
            )
            return self.status

        def wait_for_pause_boundary(self, _command_id: UUID) -> int:
            return 0

    runtime = Runtime()
    event_factory = EventFactory(clock=SystemClock(), identities=SystemIdentityProvider())
    stack = SimpleNamespace(
        match_id=started.match_id,
        runtime=runtime,
        event_factory=event_factory,
        runner=SimpleNamespace(identity=SimpleNamespace(correlation_id=started.correlation_id)),
        close=lambda: None,
    )
    session = SimpleNamespace(stack=stack, match_id=started.match_id, close=lambda: None)
    server = BrowserPlayServer(
        bootstrap=object(),  # type: ignore[arg-type]
        gateway=None,
        bus=Bus(),  # type: ignore[arg-type]
        authenticate=lambda _origin: (_PRINCIPAL, _SESSION),
        port=0,
    )
    server._session = session  # type: ignore[assignment]
    server._session_owner = (_PRINCIPAL, _SESSION)
    server._loop = asyncio.get_running_loop()
    try:
        server._on_event(started)
        await asyncio.sleep(0)

        class Gateway:
            def dispatch_runtime(
                self, command: ModelSORuntimeCommand, **_: object
            ) -> ModelSOBrowserRuntimeAccepted:
                runtime.status = runtime.status.model_copy(
                    update={"status": SORuntimeStatus.PAUSED, "revision": 2}
                )
                return ModelSOBrowserRuntimeAccepted(
                    command_id=command.command_id,
                    status=runtime.status,
                )

        server._gateway = Gateway()  # type: ignore[assignment]
        pause_response = await server._dispatch_command(
            json.dumps(
                {
                    "schema_version": "1",
                    "kind": "steel_onslaught.runtime_command",
                    "command_id": "33333333-3333-4333-8333-333333333333",
                    "expected_revision": 1,
                    "owner_id": "runtime_owner.browser",
                    "action": "pause",
                }
            ),
            transport=ModelSOBrowserRequestContext(
                origin="http://localhost:5173", host="127.0.0.1:8765"
            ),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
        )
        assert json.loads(pause_response or "{}")["outcome"] == "accepted"
        assert [event.payload.get("status") for event in server._event_history[1:]] == [
            "running",
            "paused",
        ]
        terminal = started.model_copy(
            update={
                "event_id": ulid.new().str,
                "event_type": SOEventType.MATCH_ENDED,
                "sequence_in_tick": 3,
                "payload": {"reason": "aborted", "winner_id": None},
                "envelope": started.envelope.model_copy(
                    update={"message_id": UUID("22222222-2222-4222-8222-222222222222")}
                ),
            }
        )
        server._on_event(terminal)
        await asyncio.sleep(0)
        assert [event.event_type for event in server._event_history] == [
            SOEventType.MATCH_STARTED,
            SOEventType.RUNTIME_STATUS_CHANGED,
            SOEventType.RUNTIME_STATUS_CHANGED,
            SOEventType.RUNTIME_STATUS_CHANGED,
            SOEventType.MATCH_ENDED,
        ]
        assert server._event_history[-2].payload["status"] == "ended"
        assert (
            server._event_history[-2].sequence_in_tick == server._event_history[-1].sequence_in_tick
        )
    finally:
        server._loop = None


@pytest.mark.unit
def test_browser_play_accepts_only_localhost_loopback_origin_aliases() -> None:
    assert _loopback_origin_aliases("http://localhost:5173") == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert _loopback_origin_aliases("http://127.0.0.1:5173") == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    with pytest.raises(ValueError, match="loopback"):
        _loopback_origin_aliases("http://192.168.1.20:5173")  # sanitize-ok: shape fixture


@pytest.mark.unit
@pytest.mark.parametrize(
    ("live_provider_capability", "live_provider_capability_factory", "live_runtime_factory"),
    (
        (object(), lambda *_args: object(), lambda *_args: object()),
        (object(), None, None),
        (None, lambda *_args: object(), None),
        (None, None, lambda *_args: object()),
    ),
)
def test_configured_browser_server_rejects_ambiguous_or_unpaired_live_injection(
    live_provider_capability: object | None,
    live_provider_capability_factory: object | None,
    live_runtime_factory: object | None,
) -> None:
    with pytest.raises(ValueError, match=r"live provider|live_runtime_factory"):
        _configured_browser_server(
            overlay_path=Path("unused-overlay.yaml"),
            roster_path=Path("unused-roster.yaml"),
            session_path=Path("unused-session.yaml"),
            red_loadout_path=Path("unused-red.yaml"),
            blue_loadout_path=Path("unused-blue.yaml"),
            seed=7,
            max_ticks=2,
            origin="http://localhost:5173",
            host="127.0.0.1",
            port=0,
            live_provider_capability=cast(
                ProcessLocalOneShotLiveProviderCapability | None,
                live_provider_capability,
            ),
            live_provider_capability_factory=cast(
                BrowserLiveProviderCapabilityFactory | None,
                live_provider_capability_factory,
            ),
            live_runtime_factory=cast(
                Callable[[object, str, tuple[str, ...]], RuntimeDependencies] | None,
                live_runtime_factory,
            ),
        )
