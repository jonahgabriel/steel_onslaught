"""Tests for the transport-independent browser play session."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
import ulid
from click.testing import CliRunner

from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.cli.main import main
from steel_onslaught.cli.play import (
    BrowserLiveProviderCapabilityFactory,
    BrowserPlayServer,
    BrowserPlaySession,
    _catalog_selection_overlay,
    _configured_browser_server,
    _InjectedSecretResolver,
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
from steel_onslaught.contracts.application import ModelSOSecretRef
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
    SORuntimeAction,
    SORuntimeMode,
    SORuntimeStatus,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.composition import (
    RuntimeDependencies,
    SystemClock,
    SystemIdentityProvider,
    load_application_overlay,
    load_model_catalog,
    load_model_catalog_loadouts,
    load_model_catalog_pilot_registry,
    load_model_catalog_runtime_overlay,
    load_model_catalog_runtime_sources,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.runtime import ConditionProgressGate, MatchRuntime

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
        Callable[[Any, str | tuple[str, ...], tuple[str, ...]], RuntimeDependencies],
        lambda *_: cast(RuntimeDependencies, object()),
    )

    session = launch_browser_play_session(
        overlay=cast(Any, object()),
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
def test_live_secret_resolver_maps_explicit_provider_credentials() -> None:
    resolver = _InjectedSecretResolver.from_cli(
        glm_api_key="glm-secret",
        openrouter_api_key="openrouter-secret",
        gemini_api_key="gemini-secret",
    )

    assert resolver.resolve(ModelSOSecretRef(kind="opaque", ref="secret://llm/glm")) == (
        "glm-secret"
    )
    assert resolver.resolve(ModelSOSecretRef(kind="opaque", ref="secret://llm/openrouter")) == (
        "openrouter-secret"
    )
    assert resolver.resolve(ModelSOSecretRef(kind="opaque", ref="secret://llm/gemini")) == (
        "gemini-secret"
    )


@pytest.mark.unit
def test_live_secret_resolver_rejects_unknown_provider_reference() -> None:
    resolver = _InjectedSecretResolver.from_cli(
        glm_api_key=None,
        openrouter_api_key="openrouter-secret",
        gemini_api_key=None,
    )

    with pytest.raises(ValueError, match="no live secret mapping"):
        resolver.resolve(ModelSOSecretRef(kind="opaque", ref="secret://llm/unknown"))


@pytest.mark.unit
def test_play_live_help_exposes_supported_provider_credentials() -> None:
    result = CliRunner().invoke(main, ["play-live", "--help"])

    assert result.exit_code == 0
    assert "--glm-api-key" in result.output
    assert "--openrouter-api-key" in result.output
    assert "--gemini-api-key" in result.output


@pytest.mark.unit
def test_packaged_cli_factory_is_fail_closed_for_live_selection() -> None:
    factory = CliApplicationFactory.packaged()
    assert factory.live_enabled is False
    with pytest.raises(ValueError, match="injected secret and HTTP"):
        factory.selected_runtime(cast(Any, object()), "provider.live", ("pilot.live",))


@pytest.mark.unit
def test_live_cli_factory_passes_exact_selected_provider_and_pilots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def build_selected(_overlay: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(
        "steel_onslaught.cli.application.build_selected_runtime_dependencies",
        build_selected,
    )
    resolver = cast(Any, object())
    transport = cast(Any, object())
    factory = CliApplicationFactory.live(secret_resolver=resolver, http_transport=transport)
    overlay = SimpleNamespace(llm=SimpleNamespace(secret_resolver=SimpleNamespace(kind="injected")))
    result = factory.selected_runtime(
        cast(Any, overlay),
        ("provider.red", "provider.blue"),
        ("pilot.red", "pilot.blue"),
    )
    assert result is not None
    assert calls == [
        {
            "selected_provider_ids": ("provider.red", "provider.blue"),
            "selected_pilot_spec_ids": ("pilot.red", "pilot.blue"),
            "secret_resolver": resolver,
            "http_transport": transport,
            "sleeper": None,
        }
    ]


@pytest.mark.unit
def test_live_cli_factory_omits_resolver_for_keyless_selected_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keyless live providers must not receive the injected secret capability."""

    calls: list[dict[str, object]] = []

    def build_selected(_overlay: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(
        "steel_onslaught.cli.application.build_selected_runtime_dependencies",
        build_selected,
    )
    resolver = cast(Any, object())
    transport = cast(Any, object())
    factory = CliApplicationFactory.live(secret_resolver=resolver, http_transport=transport)
    overlay = SimpleNamespace(llm=SimpleNamespace(secret_resolver=SimpleNamespace(kind="none")))

    result = factory.selected_runtime(
        cast(Any, overlay),
        "qwen35",
        ("pilot.llm.qwen35",),
    )

    assert result is not None
    assert calls == [
        {
            "selected_provider_id": "qwen35",
            "selected_pilot_spec_ids": ("pilot.llm.qwen35",),
            "secret_resolver": None,
            "http_transport": transport,
            "sleeper": None,
        }
    ]


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
async def test_catalog_index_is_the_browser_bootstrap_roster_authority() -> None:
    root = Path(__file__).parents[2]
    server = _configured_browser_server(
        overlay_path=root / "contracts_data/overlays/live_glm_cards.yaml",
        catalog_index_path=root / "contracts_data/model_catalogs/configured_v1.yaml",
        session_path=root / "contracts_data/sessions/local_operator.yaml",
        red_loadout_path=root / "contracts_data/loadouts/live_glm_sniper_ironclad.yaml",
        blue_loadout_path=root / "contracts_data/loadouts/live_glm_opportunist_hunter.yaml",
        seed=7,
        max_ticks=2,
        origin="http://localhost:5173",
        host="127.0.0.1",
        port=0,
    )

    await server.start()
    try:
        bootstrap = server.bootstrap
        assert bootstrap.model_catalog is not None
        assert bootstrap.player_roster is not None
        assert bootstrap.model_catalog.default_option_ids == (
            "player_option.glm_sniper",
            "player_option.glm_opportunist",
        )
        assert bootstrap.model_catalog.mirror_match_mode is False
        model_options = {
            option.option_id: (option.provider_binding_id, option.provider_model)
            for option in bootstrap.model_catalog.options
            if option.kind == "model"
        }
        assert {
            "qwen35",
            "qwen27",
            "glm-5.2",
            "openrouter",
            "gemini",
        } <= set(provider for provider, _model in model_options.values())
        assert any(option.kind == "human" for option in bootstrap.model_catalog.options)
        assert {option.option_id for option in bootstrap.player_roster.options} == {
            option.option_id for option in bootstrap.model_catalog.options
        }
        loaded_catalog = load_model_catalog(
            root / "contracts_data/model_catalogs/configured_v1.yaml"
        )
        catalog_roster = loaded_catalog.to_roster_binding()
        red_loadouts = {
            binding.option_id: binding.loadout_id
            for binding in catalog_roster.seats[0].option_loadouts
        }
        blue_loadouts = {
            binding.option_id: binding.loadout_id
            for binding in catalog_roster.seats[1].option_loadouts
        }
        assert red_loadouts["player_option.qwen35_model"] == "loadout.llm.qwen35_berserker"
        assert blue_loadouts["player_option.qwen27_model"] == "loadout.llm.qwen27_sniper"
        pairing = loaded_catalog.pairing_provenance(
            red_option_id="player_option.qwen35_model",
            blue_option_id="player_option.qwen27_model",
        )
        assert pairing.red_loadout_id == "loadout.llm.qwen35_berserker"
        assert pairing.blue_loadout_id == "loadout.llm.qwen27_sniper"
        assert set(
            load_model_catalog_loadouts(root / "contracts_data/model_catalogs/configured_v1.yaml")
        ) >= {
            "loadout.llm.qwen35_berserker",
            "loadout.llm.qwen27_sniper",
            "loadout.tactical.openrouter_sniper_ironclad",
            "loadout.tactical.gemini_opportunist_hunter",
        }
        catalog_pilots = load_model_catalog_pilot_registry(
            root / "contracts_data/model_catalogs/configured_v1.yaml"
        )
        assert catalog_pilots.get("pilot.openrouter.sniper") is not None
        assert catalog_pilots.get("pilot.gemini.opportunist") is not None
    finally:
        await server.stop()


@pytest.mark.unit
def test_catalog_runtime_overlay_selects_source_card_programmers_per_seat() -> None:
    root = Path(__file__).parents[2]
    catalog_path = root / "contracts_data/model_catalogs/configured_v1.yaml"
    base_overlay = load_application_overlay(root / "contracts_data/overlays/live_glm_cards.yaml")
    catalog, source_overlays = load_model_catalog_runtime_sources(catalog_path)
    _, merged_overlay = load_model_catalog_runtime_overlay(catalog_path, base_overlay)
    request = ModelSOBrowserStartMatchRequest(
        match_id=_MATCH_ID,
        command=ModelSOStartMatchCommand(
            schema_version="1",
            kind="steel_onslaught.start_match",
            command_id=_COMMAND_ID,
            expected_overlay_sha256="1" * 64,
            expected_roster_sha256="2" * 64,
            selections=(
                ModelSOStartMatchSeatSelection(side="red", option_id="player_option.qwen35_model"),
                ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.qwen27_model"),
            ),
        ),
    )

    selected_overlay = _catalog_selection_overlay(
        overlay=merged_overlay,
        catalog=catalog,
        source_overlays=source_overlays,
        request=request,
    )
    assert selected_overlay.contracts.card_catalog is not None
    assert {
        binding.pilot_spec_id for binding in selected_overlay.contracts.card_catalog.programmers
    } == {"pilot.llm.qwen35", "pilot.llm.qwen27"}

    differentiated_request = request.model_copy(
        update={
            "command": request.command.model_copy(
                update={
                    "selections": (
                        ModelSOStartMatchSeatSelection(
                            side="red", option_id="player_option.qwen35_sniper"
                        ),
                        ModelSOStartMatchSeatSelection(
                            side="blue", option_id="player_option.qwen27_opportunist"
                        ),
                    )
                }
            )
        }
    )
    differentiated_overlay = _catalog_selection_overlay(
        overlay=merged_overlay,
        catalog=catalog,
        source_overlays=source_overlays,
        request=differentiated_request,
    )
    assert differentiated_overlay.contracts.card_catalog is not None
    assert {
        binding.pilot_spec_id
        for binding in differentiated_overlay.contracts.card_catalog.programmers
    } == {"pilot.llm.qwen35_sniper", "pilot.llm.qwen27_opportunist"}


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
@pytest.mark.asyncio
async def test_browser_server_projects_failed_runtime_status_when_the_worker_raises() -> None:
    """A crashed worker must reach the client, not just stop the stream.

    ``MatchRuntime.run`` commits the terminal ``FAILED`` status when its worker
    raises, but that projection is worthless unless a client can observe it.
    Without the projection the browser sees the event stream simply stop with
    its runtime status frozen on ``running`` — indistinguishable from a slow
    match.  The server therefore projects the committed FAILED status into the
    browser event stream (the same surface every other runtime status uses)
    before the failed session is torn down.
    """
    fixture = Path(__file__).parents[2] / "frontend/src/__tests__/fixtures/match_started.json"
    started = ModelSOEventEnvelope.model_validate_json(fixture.read_text(encoding="utf-8"))

    class Bus:
        def subscribe(self, handler: object, **_: object) -> int:
            del handler
            return 1

        def unsubscribe(self, token: int) -> None:
            del token

    def _explode() -> object:
        raise RuntimeError("worker exploded mid-match")

    runtime = MatchRuntime(
        match_id=started.match_id,
        owner_id="runtime_owner.browser",
        run_match=_explode,
        progress_gate=ConditionProgressGate(),
        terminal_evidence=lambda _match_id: False,
    )
    runtime.dispatch(
        ModelSORuntimeCommand(
            schema_version="1",
            kind="steel_onslaught.runtime_command",
            command_id=_COMMAND_ID,
            expected_revision=0,
            owner_id="runtime_owner.browser",
            action=SORuntimeAction.START,
            mode=SORuntimeMode.ONE_GAME,
        )
    )
    assert runtime.status.status is SORuntimeStatus.RUNNING

    event_factory = EventFactory(clock=SystemClock(), identities=SystemIdentityProvider())
    stack = SimpleNamespace(
        match_id=started.match_id,
        runtime=runtime,
        event_factory=event_factory,
        runner=SimpleNamespace(
            identity=SimpleNamespace(correlation_id=started.correlation_id),
            fold=SimpleNamespace(state=SimpleNamespace(tick=0)),
        ),
        close=lambda: None,
    )
    session = SimpleNamespace(
        stack=stack,
        match_id=started.match_id,
        run=runtime.run,
        close=lambda: None,
    )
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
    # Stand in for a connected /events subscriber: this is the surface a real
    # browser reads, and it survives the post-failure session retirement.
    delivered: asyncio.Queue[str | None] = asyncio.Queue()
    server._event_queues[cast(Any, "events-client")] = delivered
    try:
        server._on_event(started)
        await asyncio.sleep(0)

        server._start_run_task()
        run_task = server._run_task
        assert run_task is not None
        with pytest.raises(RuntimeError, match="worker exploded"):
            await run_task
        # Let the done-callback (and the retirement it schedules) settle.
        for _ in range(4):
            await asyncio.sleep(0)

        committed = runtime.status
        assert committed.status is SORuntimeStatus.FAILED
        frames = []
        while not delivered.empty():
            frame = delivered.get_nowait()
            if frame is not None:
                frames.append(json.loads(frame))
        statuses = [
            frame["payload"]["status"]
            for frame in frames
            if frame["event_type"] == "runtime_status_changed"
        ]
        assert statuses == ["running", "failed"]
        failed_frame = next(
            frame
            for frame in frames
            if frame["event_type"] == "runtime_status_changed"
            and frame["payload"]["status"] == "failed"
        )
        # The projection carries the committed revision, so the frontend's
        # strictly-monotonic runtime-status check accepts it.
        assert failed_frame["payload"]["revision"] == committed.revision
        assert failed_frame["match_id"] == started.match_id
    finally:
        server._loop = None
        server._event_queues.clear()


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
                Callable[[Any, str | tuple[str, ...], tuple[str, ...]], RuntimeDependencies] | None,
                live_runtime_factory,
            ),
        )
