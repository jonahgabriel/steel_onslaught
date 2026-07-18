"""Transport-independent browser command gateway proof."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    ModelSOStartMatchAuthorityContext,
)
from steel_onslaught.commands.browser_gateway import (
    BrowserCommandGateway,
    BrowserGatewayCommandConflictError,
    BrowserGatewayOriginError,
    BrowserGatewayReceiveOnlyError,
    ModelSOBrowserActionRequest,
    ModelSOBrowserRequestContext,
    ModelSOBrowserStartMatchRequest,
)
from steel_onslaught.commands.inbox import ModelSOHumanActionAdmission
from steel_onslaught.contracts.commands import (
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

_PRINCIPAL = "principal.browser"
_SESSION = "session.browser"
_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_COMMAND_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_ACTION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


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


class _Start:
    def __init__(self) -> None:
        self.calls = 0

    def admit_start_match(
        self,
        command: ModelSOStartMatchCommand,
        *,
        context: ModelSOStartMatchAuthorityContext,
        match_id: str,
    ) -> ModelSOMatchLaunchProvenance:
        del context
        self.calls += 1
        return cast(
            ModelSOMatchLaunchProvenance,
            SimpleNamespace(
                launch_command_sha256=canonical_command_sha256(command),
                match_id=match_id,
                overlay_sha256="b" * 64,
                roster_sha256="c" * 64,
                launch_command_id=command.command_id,
            ),
        )


class _Human:
    def __init__(self) -> None:
        self.calls = 0

    def submit_action(
        self,
        command: ModelSOPlayerActionCommand,
        **kwargs: object,
    ) -> ModelSOHumanActionAdmission:
        del kwargs
        self.calls += 1
        return ModelSOHumanActionAdmission(
            command_id=command.command_id,
            command_sha256=canonical_command_sha256(command),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
            side="red",
            prompt_sha256="e" * 64,
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
        option_id="player_option.local_qwen",
        display_name="Local Qwen",
        model_identity_id="model_identity.local_qwen",
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


def _start_request(command_id: UUID = _COMMAND_ID) -> ModelSOBrowserStartMatchRequest:
    return ModelSOBrowserStartMatchRequest(
        match_id=_MATCH_ID,
        command=ModelSOStartMatchCommand(
            schema_version="1",
            kind="steel_onslaught.start_match",
            command_id=command_id,
            expected_overlay_sha256="1" * 64,
            expected_roster_sha256="2" * 64,
            selections=(
                ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
                ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.local_qwen"),
            ),
        ),
    )


def _action_request(command_id: UUID = _ACTION_ID) -> ModelSOBrowserActionRequest:
    return ModelSOBrowserActionRequest(
        side="red",
        command=ModelSOPlayerActionCommand(
            schema_version="1",
            kind="steel_onslaught.player_action",
            command_id=command_id,
            match_id=_MATCH_ID,
            turn_id="turn.red.000001",
            expected_tick=1,
            observation_sha256="f" * 64,
            action=ModelSORemainPlayerAction(kind="remain"),
        ),
    )


def _gateway() -> tuple[BrowserCommandGateway, _Start, _Human]:
    start, human = _Start(), _Human()
    return (
        BrowserCommandGateway(
            sessions=_Sessions(),
            roster=_roster(),
            start_coordinator=start,
            human_coordinator=human,
            allowed_origins=("http://localhost:5173",),
        ),
        start,
        human,
    )


def _transport() -> ModelSOBrowserRequestContext:
    return ModelSOBrowserRequestContext(origin="http://localhost:5173", host="127.0.0.1:8765")


@pytest.mark.unit
def test_start_is_authenticated_idempotent_and_secret_free_under_concurrency() -> None:
    gateway, start, _ = _gateway()
    request = _start_request()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: gateway.start_match(
                    request,
                    transport=_transport(),
                    principal_id=_PRINCIPAL,
                    session_id=_SESSION,
                ),
                range(8),
            )
        )

    assert start.calls == 1
    assert results == [results[0]] * 8
    assert results[0].model_dump_json() == results[0].model_dump_json()
    for forbidden in ("secret", "provider", "principal", "session", "human_identity"):
        assert forbidden not in results[0].model_dump_json().lower()


@pytest.mark.unit
def test_action_is_idempotent_and_reused_id_conflicts() -> None:
    gateway, _, human = _gateway()
    request = _action_request()
    accepted = gateway.submit_action(
        request,
        transport=_transport(),
        principal_id=_PRINCIPAL,
        session_id=_SESSION,
    )
    assert (
        gateway.submit_action(
            request,
            transport=_transport(),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
        )
        == accepted
    )
    assert human.calls == 1

    conflict = _action_request(UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbc"))
    conflict = conflict.model_copy(
        update={"command": conflict.command.model_copy(update={"expected_tick": 2})}
    )
    conflict = conflict.model_copy(
        update={"command": conflict.command.model_copy(update={"command_id": _ACTION_ID})}
    )
    with pytest.raises(BrowserGatewayCommandConflictError):
        gateway.submit_action(
            conflict,
            transport=_transport(),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
        )


@pytest.mark.unit
def test_loopback_origin_and_receive_only_guards_fail_closed() -> None:
    gateway, _, _ = _gateway()
    with pytest.raises(ValueError, match="loopback"):
        ModelSOBrowserRequestContext(origin="https://evil.example", host="127.0.0.1:8765")
    with pytest.raises(BrowserGatewayOriginError):
        gateway.start_match(
            _start_request(),
            transport=ModelSOBrowserRequestContext(
                origin="http://127.0.0.1:5173", host="127.0.0.1:8765"
            ),
            principal_id=_PRINCIPAL,
            session_id=_SESSION,
        )
    with pytest.raises(ValueError, match="loopback"):
        ModelSOBrowserRequestContext(origin="http://localhost:5173", host="10.0.0.1:8765")
    with pytest.raises(BrowserGatewayReceiveOnlyError):
        gateway.reject_inbound_event({"kind": "steel_onslaught.match_tick"})
