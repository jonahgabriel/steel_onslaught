"""Hermetic proof for selected-only live-provider composition."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from steel_onslaught.cli import play as play_cli
from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    SessionId,
    canonical_overlay_sha256,
)
from steel_onslaught.commands.browser_gateway import (
    ModelSOBrowserRequestContext,
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
    ModelSOSecretRef,
)
from steel_onslaught.contracts.commands import (
    ModelSOPlayerActionCommand,
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
    canonical_command_sha256,
)
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
)
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.immutable import thaw_json_mapping
from steel_onslaught.llm.client_http import ProviderRegistryError
from steel_onslaught.llm.schemas import (
    LlmTransportError,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
)
from steel_onslaught.match.composition import (
    assemble_selected_match_live,
    build_selected_runtime_dependencies,
    load_loadout,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.replay.engine import ReplayEngine

_ROOT = Path(__file__).resolve().parents[2]
_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_FAILURE_MATCH_ID = "match.01JABCDE0123456789ABCDEFGY"
_RED_PATH = _ROOT / "contracts_data/loadouts/example_aggressive_light.yaml"
_BLUE_PATH = _ROOT / "contracts_data/loadouts/example_llm_berserker_light.yaml"


class _Transport:
    def __init__(
        self,
        outcome: ModelSOOpenAIChatResponse | Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, dict[str, str], ModelSOOpenAIChatRequest, float]] = []

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        self.calls.append((url, headers, request, timeout_seconds))
        if self.outcome is None:
            raise AssertionError("composition must not call the provider")
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _Resolver:
    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret
        self.references: list[ModelSOSecretRef] = []

    def resolve(self, reference: ModelSOSecretRef) -> str:
        self.references.append(reference)
        if self.secret is None:
            raise AssertionError("composition must not resolve secrets")
        return self.secret


class _Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        raise AssertionError(f"composition must not retry or sleep: {seconds}")


class _Sessions:
    def __init__(self) -> None:
        self._session = ModelSOAuthenticatedSession(
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            human_identity_id="human_identity.local_operator",
            permissions=("match:create", "seat:red"),
        )

    def resolve(
        self,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOAuthenticatedSession | None:
        if (principal_id, session_id) == (
            self._session.principal_id,
            self._session.session_id,
        ):
            return self._session
        return None


def _overlay(tmp_path: Path) -> ModelSOApplicationOverlay:
    personas = tmp_path / "personas"
    pilots = tmp_path / "pilots"
    personas.mkdir()
    pilots.mkdir()
    (personas / "configured.yaml").write_text(
        "persona_id: configured\n"
        "display_name: Configured\n"
        "temperature: 0.0\n"
        "doctrine: Choose one legal action.\n",
        encoding="utf-8",
    )
    (pilots / "selected.yaml").write_text(
        'schema_version: "0.1.0"\n'
        "kind: steel_onslaught.pilot\n"
        "id: pilot.live.selected\n"
        "display_name: Selected\n"
        "archetype: llm\n"
        "lineage:\n  parent: pilot.template.llm\n"
        "parameters:\n  persona: configured\n  provider: selected\n",
        encoding="utf-8",
    )
    (pilots / "unselected.yaml").write_text(
        'schema_version: "0.1.0"\n'
        "kind: steel_onslaught.pilot\n"
        "id: pilot.live.unselected\n"
        "display_name: Unselected\n"
        "archetype: llm\n"
        "lineage:\n  parent: pilot.template.llm\n"
        "parameters:\n  persona: unavailable\n  provider: unselected\n",
        encoding="utf-8",
    )
    return ModelSOApplicationOverlay.model_validate(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": tmp_path / "events.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": False,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": tmp_path / "leaderboard.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": False,
                "transaction_mode": "autocommit",
                "storage_schema": "leaderboard_v1",
            },
            "learning_artifacts": {
                "kind": "filesystem_yaml",
                "evaluation_root": tmp_path / "evaluations",
                "lineage_root": tmp_path / "lineage",
                "experiment_root": tmp_path / "experiments",
            },
            "evaluation_storage": {
                "kind": "sqlite",
                "root": tmp_path / "evaluation_storage",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
                "leaderboard_schema": "leaderboard_v1",
            },
            "contracts": {
                "catalog_dir": _ROOT / "contracts_data",
                "pilot_registry_dir": pilots,
                "arena_id": "open_field",
            },
            "llm": {
                "providers": [
                    {
                        "kind": "openai_compatible",
                        "provider_id": "selected",
                        "endpoint_url": "https://selected.invalid/v1/chat/completions",
                        "model": "selected-model",
                        "secret_ref": {
                            "kind": "opaque",
                            "ref": "secret://llm/selected",
                        },
                        "timeout_seconds": 1.0,
                        "max_tokens": 16,
                        "retry": {
                            "max_attempts": 1,
                            "initial_backoff_seconds": 0.0,
                            "backoff_multiplier": 1.0,
                        },
                    },
                    {
                        "kind": "openai_compatible",
                        "provider_id": "unselected",
                        "endpoint_url": "https://unselected.invalid/v1/chat/completions",
                        "model": "unselected-model",
                        "secret_ref": {
                            "kind": "opaque",
                            "ref": "secret://llm/unselected",
                        },
                        "timeout_seconds": 1.0,
                        "max_tokens": 16,
                        "retry": {
                            "max_attempts": 3,
                            "initial_backoff_seconds": 1.0,
                            "backoff_multiplier": 2.0,
                        },
                    },
                ],
                "model_identities": [
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.model_identity",
                        "model_identity_id": "model_identity.selected",
                        "display_name": "Selected live fixture",
                        "provider_binding_id": "selected",
                    }
                ],
                "personas_dir": personas,
                "secret_resolver": {"kind": "injected"},
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
            "frontend_transport": {
                "kind": "websocket",
                "contract": "steel_onslaught.frontend_transport.v1",
                "websocket_url": "ws://127.0.0.1:8765/events",
                "event_schema": "canonical_event_v1",
                "milliseconds_per_tick": 500,
            },
        }
    )


@pytest.mark.integration
def test_selected_runtime_builds_only_explicit_provider_and_pilot(tmp_path: Path) -> None:
    transport = _Transport()
    resolver = _Resolver()

    dependencies = build_selected_runtime_dependencies(
        _overlay(tmp_path),
        selected_provider_id="selected",
        selected_pilot_spec_ids=("pilot.live.selected",),
        secret_resolver=resolver,
        http_transport=transport,
        sleeper=_Sleeper(),
    )
    try:
        selected = dependencies.pilot_registry.get("pilot.live.selected")
        unselected = dependencies.pilot_registry.get("pilot.live.unselected")
        assert selected is not None
        assert unselected is not None
        dependencies.pilot_factory.from_spec(selected)
        with pytest.raises(ProviderRegistryError, match="unknown_provider"):
            dependencies.pilot_factory.from_spec(unselected)
        assert transport.calls == []
        assert resolver.references == []
    finally:
        dependencies.close()


@pytest.mark.integration
def test_selected_runtime_closes_root_owned_http_client_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _ClosableHttpClient:
        def __init__(self) -> None:
            self.close_count = 0
            self.request_count = 0

        def post(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            self.request_count += 1
            raise AssertionError("selected dependency construction must not issue a request")

        def close(self) -> None:
            self.close_count += 1

    raw = _ClosableHttpClient()

    def fake_http_client(*args: object, **kwargs: object) -> _ClosableHttpClient:
        assert args == ()
        assert kwargs == {"trust_env": False}
        return raw

    monkeypatch.setattr(httpx, "Client", fake_http_client)
    dependencies = build_selected_runtime_dependencies(
        _overlay(tmp_path),
        selected_provider_id="selected",
        selected_pilot_spec_ids=("pilot.live.selected",),
        secret_resolver=_Resolver("fixture-secret"),
    )

    dependencies.close()
    dependencies.close()

    assert raw.request_count == 0
    assert raw.close_count == 1


def _roster(red_pilot_id: str) -> ModelSOPlayerRosterBinding:
    human = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser human",
        human_identity_id="human_identity.local_operator",
        pilot_spec_id=red_pilot_id,
        input_source="browser_command",
    )
    model = ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id="player_option.selected_live",
        display_name="Selected live fixture",
        model_identity_id="model_identity.selected",
        pilot_spec_id="pilot.live.selected",
        persona_id="configured",
        input_source="llm_completion",
    )
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.live_loopback",
        options=(human, model),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.example.aggressive_light",
                allowed_option_ids=(human.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.example.llm_berserker_light",
                allowed_option_ids=(model.option_id,),
            ),
        ),
    )


def _response() -> ModelSOOpenAIChatResponse:
    return ModelSOOpenAIChatResponse.model_validate(
        {
            "id": "raw-provider-id-must-not-be-emitted",
            "choices": (
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "action": "remain",
                                "action_params": {},
                                "confidence": 1.0,
                                "rationale": "fixture accepted",
                            }
                        ),
                    },
                    "finish_reason": "stop",
                },
            ),
            "usage": {"prompt_tokens": 3, "completion_tokens": 5},
            "model": "served-live-model",
        }
    )


@pytest.mark.integration
def test_browser_live_start_mints_one_exact_capability_and_replay_does_not_remint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    overlay = _overlay(tmp_path)
    red = load_loadout(_RED_PATH)
    roster = _roster(red.pilot_id)
    command = ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=UUID("abababab-abab-4bab-8bab-abababababab"),
        expected_overlay_sha256=canonical_overlay_sha256(overlay),
        expected_roster_sha256=roster.canonical_sha256(),
        selections=(
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.selected_live"),
        ),
    )
    request = ModelSOBrowserStartMatchRequest(match_id=_MATCH_ID, command=command)
    session = ModelSOAuthenticatedSession(
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        human_identity_id="human_identity.local_operator",
        permissions=("match:create", "seat:red"),
    )
    launch_calls: list[dict[str, object]] = []

    class Bus:
        def subscribe(self, _handler: object, **_kwargs: object) -> int:
            return 1

        def unsubscribe(self, _token: int) -> None:
            return None

    class Gateway:
        def start_match(
            self, exact_request: ModelSOBrowserStartMatchRequest, **_kwargs: object
        ) -> ModelSOBrowserStartAccepted:
            return ModelSOBrowserStartAccepted(
                command_id=exact_request.command.command_id,
                command_sha256=canonical_command_sha256(exact_request.command),
                match_id=exact_request.match_id,
                overlay_sha256=canonical_overlay_sha256(overlay),
                roster_sha256=roster.canonical_sha256(),
            )

    def launch(**kwargs: object) -> object:
        launch_calls.append(kwargs)
        selected_runtime_factory = kwargs["live_runtime_factory"]
        assert callable(selected_runtime_factory)
        selected_dependencies = selected_runtime_factory(
            overlay,
            "selected",
            ("pilot.live.selected",),
        )
        selected_dependencies.close()
        stack = SimpleNamespace(
            bus=Bus(),
            launch_provenance=SimpleNamespace(seat_assignments=()),
        )
        return SimpleNamespace(
            gateway=Gateway(),
            stack=stack,
            launch_provenance=stack.launch_provenance,
            match_id=_MATCH_ID,
            run=lambda: None,
            close=lambda: None,
        )

    monkeypatch.setattr(play_cli, "load_application_overlay", lambda _path: overlay)
    monkeypatch.setattr(
        play_cli,
        "_load_yaml_model",
        lambda _path, model: roster if model is ModelSOPlayerRosterBinding else session,
    )
    monkeypatch.setattr(
        play_cli,
        "load_loadout",
        lambda path: SimpleNamespace(
            id=(
                "loadout.example.aggressive_light"
                if path == _RED_PATH
                else "loadout.example.llm_berserker_light"
            )
        ),
    )

    monkeypatch.setattr(play_cli, "build_frontend_bootstrap", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(play_cli, "launch_browser_play_session", launch)

    server = play_cli.configured_live_browser_server(
        overlay_path=tmp_path / "overlay.yaml",
        roster_path=tmp_path / "roster.yaml",
        session_path=tmp_path / "session.yaml",
        red_loadout_path=_RED_PATH,
        blue_loadout_path=_BLUE_PATH,
        seed=7,
        max_ticks=2,
        origin="http://localhost:5173",
        host="127.0.0.1",
        port=0,
        secret_resolver=_Resolver("unused-test-secret"),
        http_transport=_Transport(),
        live_max_completions=8,
    )

    async def admit_twice() -> tuple[str, str]:
        transport = ModelSOBrowserRequestContext(
            origin="http://localhost:5173", host="127.0.0.1:8765"
        )
        first = await server._admit_start(
            request,
            transport=transport,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
        )
        replay = await server._admit_start(
            request,
            transport=transport,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
        )
        await server.stop()
        return first, replay

    first, replay = asyncio.run(admit_twice())

    assert first == replay
    assert len(launch_calls) == 1
    capability = launch_calls[0]["live_provider_capability"]
    assert isinstance(capability, ProcessLocalOneShotLiveProviderCapability)
    grant = capability._grant
    assert grant.model_identity_id == "model_identity.selected"
    assert grant.provider_id == "selected"
    assert grant.max_completions == 8
    assert callable(launch_calls[0]["live_runtime_factory"])


@pytest.mark.integration
def test_authenticated_human_vs_one_shot_live_provider_is_replayable_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def poison_http_client(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("injected live runtime must not construct an HTTP client")

    monkeypatch.setattr(httpx, "Client", poison_http_client)
    overlay = _overlay(tmp_path)
    red = load_loadout(_RED_PATH)
    blue = load_loadout(_BLUE_PATH).model_copy(update={"pilot_id": "pilot.live.selected"})
    roster = _roster(red.pilot_id)
    command = ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=UUID("33333333-3333-4333-8333-333333333333"),
        expected_overlay_sha256=canonical_overlay_sha256(overlay),
        expected_roster_sha256=roster.canonical_sha256(),
        selections=(
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.selected_live"),
        ),
    )
    context = ModelSOStartMatchAuthorityContext(
        creator_principal_id="principal.local_operator",
        creator_session_id="session.local_operator",
        human_seats=(
            ModelSOHumanSeatAuthorityClaim(
                side="red",
                principal_id="principal.local_operator",
                session_id="session.local_operator",
            ),
        ),
    )
    grant = ModelSOLiveProviderLaunchGrant(
        creator_principal_id=context.creator_principal_id,
        creator_session_id=context.creator_session_id,
        launch_command_id=command.command_id,
        launch_command_sha256=canonical_command_sha256(command),
        overlay_sha256=canonical_overlay_sha256(overlay),
        roster_sha256=roster.canonical_sha256(),
        model_identity_id="model_identity.selected",
        provider_id="selected",
    )
    capability = ProcessLocalOneShotLiveProviderCapability(grant=grant)
    selected_reference = ModelSOSecretRef(kind="opaque", ref="secret://llm/selected")
    transport = _Transport(_response())
    resolver = _Resolver("resolved-credential-must-not-be-emitted")
    sleeper = _Sleeper()
    live_factory = CliApplicationFactory.live(
        secret_resolver=resolver,
        http_transport=transport,
        sleeper=sleeper,
    )

    def forbidden_default_runtime(candidate: ModelSOApplicationOverlay) -> object:
        del candidate
        raise AssertionError("live launch must not construct the default runtime")

    def live_runtime_factory(
        candidate: ModelSOApplicationOverlay,
        provider_id: str,
        pilot_spec_ids: tuple[str, ...],
    ) -> object:
        return live_factory.selected_runtime(candidate, provider_id, pilot_spec_ids)

    stack = assemble_selected_match_live(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(),
        command=command,
        context=context,
        identity=MatchIdentity(
            match_id=_MATCH_ID,
            correlation_id=UUID("11111111-1111-4111-8111-111111111111"),
        ),
        loadouts={red.id: red, blue.id: blue},
        runtime_factory=forbidden_default_runtime,  # type: ignore[arg-type]
        live_provider_capability=capability,
        live_runtime_factory=live_runtime_factory,  # type: ignore[arg-type]
        seed=7,
        max_ticks=2,
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(stack.runner.run)
            prompt = stack.human_inbox.wait_for_prompt(
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
                match_id=_MATCH_ID,
                after_tick=0,
            )
            stack.human_inbox.submit_action(
                ModelSOPlayerActionCommand(
                    schema_version="1",
                    kind="steel_onslaught.player_action",
                    command_id=UUID(int=prompt.expected_tick),
                    match_id=prompt.match_id,
                    turn_id=prompt.turn_id,
                    expected_tick=prompt.expected_tick,
                    observation_sha256=prompt.observation_sha256,
                    action=prompt.available_actions[0],
                ),
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
            )
            live_final = result.result(timeout=10)

        events = list(stack.ledger.read_all(_MATCH_ID))
        requested = [
            event for event in events if event.event_type is SOEventType.LLM_COMPLETION_REQUESTED
        ]
        resolved = [
            event for event in events if event.event_type is SOEventType.LLM_COMPLETION_RESOLVED
        ]
        failed = [
            event for event in events if event.event_type is SOEventType.LLM_COMPLETION_FAILED
        ]
        assert len(requested) == len(resolved) == 1
        assert failed == []
        assert set(thaw_json_mapping(requested[0].payload)) == {
            "provider_id",
            "persona_id",
            "system_prompt_length",
            "user_prompt_length",
        }
        assert set(thaw_json_mapping(resolved[0].payload)) == {
            "provider_id",
            "model",
            "finish_reason",
            "prompt_tokens",
            "completion_tokens",
            "response_length",
            "cost_usd",
        }
        decisions = [
            thaw_json_mapping(event.payload)
            for event in events
            if event.event_type is SOEventType.PILOT_DECISION_MADE
        ]
        blue_decisions = [
            decision
            for event, decision in zip(
                (event for event in events if event.event_type is SOEventType.PILOT_DECISION_MADE),
                decisions,
                strict=True,
            )
            if event.subject.player_id == "player.blue"
        ]
        assert len(blue_decisions) == 1
        assert blue_decisions[0]["reason_code"] == "llm_decision"
        assert all(decision["reason_code"] != "llm_fallback" for decision in decisions)
        assert any(
            decision.get("decision_source", {}).get("kind") == "human" for decision in decisions
        )

        started = next(event for event in events if event.event_type is SOEventType.MATCH_STARTED)
        assert thaw_json_mapping(started.payload)["launch_provenance"] == (
            stack.launch_provenance.model_dump(mode="json")
        )
        replay_final = ReplayEngine(
            stack.ledger,
            _MATCH_ID,
            catalog=stack.catalog,
            event_factory=stack.event_factory,
        ).reconstruct_at_tick(live_final.tick)
        assert replay_final == live_final
        assert live_final.status.value == "ended"

        assert capability.consumption_count == 1
        assert resolver.references == [selected_reference]
        assert sleeper.calls == []
        assert len(transport.calls) == 1
        url, headers, _, _ = transport.calls[0]
        assert url == "https://selected.invalid/v1/chat/completions"
        assert headers["Authorization"] == "Bearer resolved-credential-must-not-be-emitted"
        serialized_events = json.dumps(
            [event.model_dump(mode="json") for event in events],
            sort_keys=True,
        )
        for forbidden in (
            "Choose one legal action.",
            "resolved-credential-must-not-be-emitted",
            "Authorization",
            "Bearer ",
            "raw-provider-id-must-not-be-emitted",
            "unselected.invalid",
            "secret://llm/unselected",
        ):
            assert forbidden not in serialized_events
    finally:
        stack.close()


@pytest.mark.integration
def test_authenticated_live_provider_failure_is_terminal_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def poison_http_client(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("injected live runtime must not construct an HTTP client")

    monkeypatch.setattr(httpx, "Client", poison_http_client)
    overlay = _overlay(tmp_path)
    red = load_loadout(_RED_PATH)
    blue = load_loadout(_BLUE_PATH).model_copy(update={"pilot_id": "pilot.live.selected"})
    roster = _roster(red.pilot_id)
    command = ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=UUID("44444444-4444-4444-8444-444444444444"),
        expected_overlay_sha256=canonical_overlay_sha256(overlay),
        expected_roster_sha256=roster.canonical_sha256(),
        selections=(
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.selected_live"),
        ),
    )
    context = ModelSOStartMatchAuthorityContext(
        creator_principal_id="principal.local_operator",
        creator_session_id="session.local_operator",
        human_seats=(
            ModelSOHumanSeatAuthorityClaim(
                side="red",
                principal_id="principal.local_operator",
                session_id="session.local_operator",
            ),
        ),
    )
    capability = ProcessLocalOneShotLiveProviderCapability(
        grant=ModelSOLiveProviderLaunchGrant(
            creator_principal_id=context.creator_principal_id,
            creator_session_id=context.creator_session_id,
            launch_command_id=command.command_id,
            launch_command_sha256=canonical_command_sha256(command),
            overlay_sha256=canonical_overlay_sha256(overlay),
            roster_sha256=roster.canonical_sha256(),
            model_identity_id="model_identity.selected",
            provider_id="selected",
        )
    )
    selected_reference = ModelSOSecretRef(kind="opaque", ref="secret://llm/selected")
    transport_failure = "LLM provider returned HTTP 400"
    transport = _Transport(LlmTransportError(transport_failure, retryable=False))
    resolver = _Resolver("resolved-failure-credential-must-not-be-emitted")
    sleeper = _Sleeper()

    def forbidden_default_runtime(candidate: ModelSOApplicationOverlay) -> object:
        del candidate
        raise AssertionError("live launch must not construct the default runtime")

    def live_runtime_factory(
        candidate: ModelSOApplicationOverlay,
        provider_id: str,
        pilot_spec_ids: tuple[str, ...],
    ) -> object:
        return build_selected_runtime_dependencies(
            candidate,
            selected_provider_id=provider_id,
            selected_pilot_spec_ids=pilot_spec_ids,
            secret_resolver=resolver,
            http_transport=transport,
            sleeper=sleeper,
        )

    stack = assemble_selected_match_live(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(),
        command=command,
        context=context,
        identity=MatchIdentity(
            match_id=_FAILURE_MATCH_ID,
            correlation_id=UUID("22222222-2222-4222-8222-222222222222"),
        ),
        loadouts={red.id: red, blue.id: blue},
        runtime_factory=forbidden_default_runtime,  # type: ignore[arg-type]
        live_provider_capability=capability,
        live_runtime_factory=live_runtime_factory,  # type: ignore[arg-type]
        seed=7,
        max_ticks=2,
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(stack.runner.run)
            prompt = stack.human_inbox.wait_for_prompt(
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
                match_id=_FAILURE_MATCH_ID,
                after_tick=0,
            )
            stack.human_inbox.submit_action(
                ModelSOPlayerActionCommand(
                    schema_version="1",
                    kind="steel_onslaught.player_action",
                    command_id=UUID(int=prompt.expected_tick),
                    match_id=prompt.match_id,
                    turn_id=prompt.turn_id,
                    expected_tick=prompt.expected_tick,
                    observation_sha256=prompt.observation_sha256,
                    action=prompt.available_actions[0],
                ),
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
            )
            with pytest.raises(LlmTransportError, match="HTTP 400"):
                result.result(timeout=10)

        events = list(stack.ledger.read_all(_FAILURE_MATCH_ID))
        requested = [
            event for event in events if event.event_type is SOEventType.LLM_COMPLETION_REQUESTED
        ]
        resolved = [
            event for event in events if event.event_type is SOEventType.LLM_COMPLETION_RESOLVED
        ]
        failed = [
            event for event in events if event.event_type is SOEventType.LLM_COMPLETION_FAILED
        ]
        assert len(requested) == len(failed) == 1
        assert resolved == []
        assert thaw_json_mapping(failed[0].payload)["reason_code"] == "provider_error"

        decisions = [
            event for event in events if event.event_type is SOEventType.PILOT_DECISION_MADE
        ]
        assert [event for event in decisions if event.subject.player_id == "player.blue"] == []
        assert all(
            thaw_json_mapping(event.payload)["reason_code"] != "llm_fallback" for event in decisions
        )

        partial_live = stack.runner.fold.state
        replayed = ReplayEngine(
            stack.ledger,
            _FAILURE_MATCH_ID,
            catalog=stack.catalog,
            event_factory=stack.event_factory,
        ).reconstruct_at_tick(partial_live.tick)
        assert replayed == partial_live

        assert capability.consumption_count == 1
        assert stack.human_inbox.action_admission_count == 1
        assert resolver.references == [selected_reference]
        assert sleeper.calls == []
        assert len(transport.calls) == 1
        serialized_events = json.dumps(
            [event.model_dump(mode="json") for event in events],
            sort_keys=True,
        )
        for forbidden in (
            "Choose one legal action.",
            "resolved-failure-credential-must-not-be-emitted",
            "Authorization",
            "Bearer ",
            transport_failure,
            "llm_fallback",
            "unselected.invalid",
            "secret://llm/unselected",
        ):
            assert forbidden not in serialized_events
    finally:
        stack.close()
        with pytest.raises(HumanDecisionCancelledError, match="shut down"):
            stack.human_inbox.wait_for_prompt(
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
                match_id=_FAILURE_MATCH_ID,
                after_tick=0,
            )
