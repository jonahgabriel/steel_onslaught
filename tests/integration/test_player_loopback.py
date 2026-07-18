"""Hermetic human-versus-stub proof for the Phase 54A process-local loop."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    SessionId,
    canonical_overlay_sha256,
)
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOStubLlmProviderBinding,
)
from steel_onslaught.contracts.commands import (
    ModelSOPlayerActionCommand,
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
)
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
)
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.immutable import thaw_json_mapping
from steel_onslaught.llm.client_http import NoSecretResolver
from steel_onslaught.match.composition import (
    assemble_selected_match_live,
    build_runtime_dependencies,
    load_loadout,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.projections.cli.renderer import CliTextRenderer
from steel_onslaught.replay.engine import ReplayEngine

_ROOT = Path(__file__).resolve().parents[2]
_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_RED_PATH = _ROOT / "contracts_data/loadouts/example_aggressive_light.yaml"
_BLUE_PATH = _ROOT / "contracts_data/loadouts/example_llm_berserker_light.yaml"


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
                "check_same_thread": False,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
                "leaderboard_schema": "leaderboard_v1",
            },
            "contracts": {
                "catalog_dir": _ROOT / "contracts_data",
                "pilot_registry_dir": _ROOT / "contracts_data/pilots",
                "arena_id": "open_field",
            },
            "llm": {
                "providers": [
                    {"kind": "stub", "provider_id": provider_id, "model": "fixture"}
                    for provider_id in ("stub", "qwen35", "qwen27", "deepseek", "glm-5.2")
                ],
                "model_identities": [
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.model_identity",
                        "model_identity_id": "model_identity.local_stub",
                        "display_name": "Local stub",
                        "provider_binding_id": "stub",
                    }
                ],
                "personas_dir": _ROOT / "contracts_data/pilots/personas",
                "secret_resolver": {"kind": "none"},
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
            "frontend_transport": {
                "kind": "websocket",
                "contract": "steel_onslaught.frontend_transport.v1",
                "websocket_url": "ws://127.0.0.1:8765/events",
                "event_schema": "canonical_event_v1",
                "milliseconds_per_tick": 1,
            },
        }
    )


def _roster(red_pilot: str, blue_pilot: str) -> ModelSOPlayerRosterBinding:
    human = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser human",
        human_identity_id="human_identity.local_operator",
        pilot_spec_id=red_pilot,
        input_source="browser_command",
    )
    model = ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id="player_option.local_stub",
        display_name="Local stub",
        model_identity_id="model_identity.local_stub",
        pilot_spec_id=blue_pilot,
        persona_id="berserker",
        input_source="llm_completion",
    )
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.loopback",
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


@pytest.mark.integration
def test_authenticated_human_vs_stub_loop_is_replayable_and_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def poison_http_client_construction(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("stub-only loop must not construct an HTTP client")

    def poison_http_transport_construction(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("stub-only loop must not construct an HTTP transport")

    def poison_secret_resolution(resolver: object, reference: object) -> str:
        del resolver, reference
        raise AssertionError("stub-only loop must not resolve secrets")

    monkeypatch.setattr(httpx, "Client", poison_http_client_construction)
    monkeypatch.setattr(
        "steel_onslaught.match.composition.HttpxJsonTransport",
        poison_http_transport_construction,
    )
    monkeypatch.setattr(NoSecretResolver, "resolve", poison_secret_resolution)

    overlay = _overlay(tmp_path)
    provider_registry = {provider.provider_id: provider for provider in overlay.llm.providers}
    assert set(provider_registry) == {"stub", "qwen35", "qwen27", "deepseek", "glm-5.2"}
    assert all(
        isinstance(provider, ModelSOStubLlmProviderBinding)
        for provider in provider_registry.values()
    )
    red = load_loadout(_RED_PATH)
    blue = load_loadout(_BLUE_PATH)
    roster = _roster(red.pilot_id, blue.pilot_id)
    command = ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=UUID("33333333-3333-4333-8333-333333333333"),
        expected_overlay_sha256=canonical_overlay_sha256(overlay),
        expected_roster_sha256=roster.canonical_sha256(),
        selections=(
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.local_stub"),
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

    def runtime_factory(candidate: ModelSOApplicationOverlay) -> Any:
        return build_runtime_dependencies(candidate)

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
        runtime_factory=runtime_factory,
        seed=7,
        max_ticks=4,
    )

    assert stack.launch_provenance.match_id == _MATCH_ID
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(stack.runner.run)
        for previous_tick in (0, 1, 2):
            prompt = stack.human_inbox.wait_for_prompt(
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
                match_id=_MATCH_ID,
                after_tick=previous_tick,
            )
            assert prompt.expected_tick == previous_tick + 1
            assert prompt.available_actions
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
    started = next(event for event in events if event.event_type is SOEventType.MATCH_STARTED)
    assert thaw_json_mapping(started.payload)["launch_provenance"] == (
        stack.launch_provenance.model_dump(mode="json")
    )
    human_decisions = [
        thaw_json_mapping(event.payload)
        for event in events
        if event.event_type is SOEventType.PILOT_DECISION_MADE
        and event.subject.player_id == "player.red"
    ]
    assert human_decisions
    assert all(decision["decision_source"]["kind"] == "human" for decision in human_decisions)

    replay_final = ReplayEngine(
        stack.ledger,
        _MATCH_ID,
        catalog=stack.catalog,
        event_factory=stack.event_factory,
    ).reconstruct_at_tick(live_final.tick)
    assert replay_final == live_final

    output = StringIO()
    renderer = CliTextRenderer(output, color=False)
    for event in events:
        renderer.handle(event)
    assert "match ended" in output.getvalue().lower()
    assert (tmp_path / "events.sqlite3").is_file()
    stack.human_inbox.shutdown()
    stack.close()
