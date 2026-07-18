"""Focused admission and provenance tests for the process-local match coordinator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypedDict, cast
from uuid import UUID

import pytest

from steel_onslaught.commands.authority import (
    CommandContractStaleError,
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    SelectionAuthorityError,
    SessionAuthenticationError,
    SessionId,
    canonical_overlay_sha256,
)
from steel_onslaught.commands.coordinator import (
    MatchLaunchConflictError,
    NonStubModelProviderError,
    ProcessLocalMatchLaunchCoordinator,
)
from steel_onslaught.commands.live_provider import (
    LiveProviderGrantBindingError,
    LiveProviderGrantConsumedError,
    ModelSOLiveProviderLaunchGrant,
    ProcessLocalOneShotLiveProviderCapability,
)
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOLlmRetryBinding,
    ModelSOOpenAICompatibleProviderBinding,
)
from steel_onslaught.contracts.commands import (
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

_MATCH_ID = "match.01JABCDE0123456789ABCDEFGX"
_COMMAND_ID = UUID("11111111-1111-4111-8111-111111111111")


class _LiveProviderGrantBindings(TypedDict):
    creator_principal_id: str
    creator_session_id: str
    launch_command_id: UUID
    launch_command_sha256: str
    overlay_sha256: str
    roster_sha256: str
    model_identity_id: str
    provider_id: str


class _Sessions:
    def __init__(self, *sessions: ModelSOAuthenticatedSession) -> None:
        self._sessions = {
            (session.principal_id, session.session_id): session for session in sessions
        }

    def resolve(
        self,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOAuthenticatedSession | None:
        return self._sessions.get((principal_id, session_id))


def _operator() -> ModelSOAuthenticatedSession:
    return ModelSOAuthenticatedSession(
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        human_identity_id="human_identity.local_operator",
        permissions=("match:create", "seat:red"),
    )


def _overlay(tmp_path: Path) -> ModelSOApplicationOverlay:
    return ModelSOApplicationOverlay.model_validate(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": tmp_path / "events.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": tmp_path / "leaderboard.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
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
                "catalog_dir": tmp_path / "catalog",
                "pilot_registry_dir": tmp_path / "pilots",
                "arena_id": "open_field",
            },
            "llm": {
                "providers": [{"kind": "stub", "provider_id": "stub", "model": "fixture"}],
                "model_identities": [
                    {
                        "schema_version": "1",
                        "kind": "steel_onslaught.model_identity",
                        "model_identity_id": "model_identity.local_qwen",
                        "display_name": "Local Qwen",
                        "provider_binding_id": "stub",
                    }
                ],
                "personas_dir": tmp_path / "personas",
                "secret_resolver": {"kind": "none"},
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


def _roster() -> ModelSOPlayerRosterBinding:
    human = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser pilot",
        human_identity_id="human_identity.local_operator",
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
        roster_id="roster.local_play",
        options=(human, model),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.playable.red_light",
                allowed_option_ids=(human.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.playable.blue_light",
                allowed_option_ids=(model.option_id,),
            ),
        ),
    )


def _command(
    overlay: ModelSOApplicationOverlay,
    roster: ModelSOPlayerRosterBinding,
) -> ModelSOStartMatchCommand:
    return ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=_COMMAND_ID,
        expected_overlay_sha256=canonical_overlay_sha256(overlay),
        expected_roster_sha256=roster.canonical_sha256(),
        selections=(
            ModelSOStartMatchSeatSelection(
                side="red",
                option_id="player_option.browser_human",
            ),
            ModelSOStartMatchSeatSelection(
                side="blue",
                option_id="player_option.local_qwen",
            ),
        ),
    )


def _context() -> ModelSOStartMatchAuthorityContext:
    return ModelSOStartMatchAuthorityContext(
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


def _coordinator(
    overlay: ModelSOApplicationOverlay,
    *,
    sessions: _Sessions | None = None,
) -> ProcessLocalMatchLaunchCoordinator:
    return ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=_roster(),
        sessions=sessions or _Sessions(_operator()),
    )


def _live_overlay(tmp_path: Path) -> ModelSOApplicationOverlay:
    base = _overlay(tmp_path)
    identity = base.llm.model_identities[0]
    return base.model_copy(
        update={
            "llm": base.llm.model_copy(
                update={
                    "providers": (
                        ModelSOOpenAICompatibleProviderBinding(
                            kind="openai_compatible",
                            provider_id="remote",
                            endpoint_url="https://example.invalid/v1",
                            model="remote-model",
                            secret_ref=None,
                            timeout_seconds=1.0,
                            max_tokens=16,
                            retry=ModelSOLlmRetryBinding(
                                max_attempts=1,
                                initial_backoff_seconds=0.0,
                                backoff_multiplier=1.0,
                            ),
                        ),
                    ),
                    "model_identities": (
                        identity.model_copy(update={"provider_binding_id": "remote"}),
                    ),
                }
            )
        }
    )


@pytest.mark.unit
def test_authenticated_start_returns_canonical_secret_free_launch_provenance(
    tmp_path: Path,
) -> None:
    overlay = _overlay(tmp_path)
    roster = _roster()
    command = _command(overlay, roster)
    coordinator = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(_operator()),
    )

    provenance = coordinator.admit_start_match(
        command,
        context=_context(),
        match_id=_MATCH_ID,
    )

    assert provenance.match_id == _MATCH_ID
    assert provenance.launch_command_id == command.command_id
    assert provenance.overlay_sha256 == command.expected_overlay_sha256
    assert provenance.roster_id == roster.roster_id
    assert provenance.roster_sha256 == command.expected_roster_sha256
    assert [assignment.side for assignment in provenance.seat_assignments] == ["red", "blue"]
    red, blue = provenance.seat_assignments
    assert red.kind == "human"
    assert red.player_id == "player.red"
    assert red.loadout_id == "loadout.playable.red_light"
    assert blue.kind == "model"
    assert blue.player_id == "player.blue"
    assert blue.loadout_id == "loadout.playable.blue_light"

    option = next(option for option in roster.options if option.option_id == blue.option_id)
    canonical = json.dumps(
        option.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    assert blue.option_sha256 == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    serialized = provenance.model_dump_json()
    assert "provider_binding_id" not in serialized
    assert "endpoint_url" not in serialized
    assert "secret_ref" not in serialized


@pytest.mark.unit
def test_coordinator_delegates_authentication_digest_and_seat_validation(
    tmp_path: Path,
) -> None:
    overlay = _overlay(tmp_path)
    roster = _roster()
    command = _command(overlay, roster)

    missing_session = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(),
    )
    with pytest.raises(SessionAuthenticationError):
        missing_session.admit_start_match(command, context=_context(), match_id=_MATCH_ID)

    coordinator = _coordinator(overlay)
    stale = command.model_copy(update={"expected_roster_sha256": "f" * 64})
    with pytest.raises(CommandContractStaleError, match="roster"):
        coordinator.admit_start_match(stale, context=_context(), match_id=_MATCH_ID)

    disallowed = command.model_copy(
        update={
            "selections": (
                ModelSOStartMatchSeatSelection(
                    side="red",
                    option_id="player_option.local_qwen",
                ),
                command.selections[1],
            )
        }
    )
    with pytest.raises(SelectionAuthorityError, match="not allowed"):
        coordinator.admit_start_match(disallowed, context=_context(), match_id=_MATCH_ID)


@pytest.mark.unit
def test_non_stub_selected_model_fails_before_launch_admission(tmp_path: Path) -> None:
    overlay = _live_overlay(tmp_path)
    roster = _roster()
    coordinator = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(_operator()),
    )

    with pytest.raises(NonStubModelProviderError, match="stub"):
        coordinator.admit_start_match(
            _command(overlay, roster),
            context=_context(),
            match_id=_MATCH_ID,
        )

    assert coordinator.launch_admission_count == 0


@pytest.mark.unit
def test_live_provider_grant_exact_binding_is_authenticated_and_consumed_once(
    tmp_path: Path,
) -> None:
    overlay = _live_overlay(tmp_path)
    roster = _roster()
    command = _command(overlay, roster)
    bindings: _LiveProviderGrantBindings = {
        "creator_principal_id": "principal.local_operator",
        "creator_session_id": "session.local_operator",
        "launch_command_id": command.command_id,
        "launch_command_sha256": canonical_command_sha256(command),
        "overlay_sha256": command.expected_overlay_sha256,
        "roster_sha256": command.expected_roster_sha256,
        "model_identity_id": "model_identity.local_qwen",
        "provider_id": "remote",
    }
    grant = ModelSOLiveProviderLaunchGrant(
        schema_version="1",
        kind="steel_onslaught.live_provider_launch_grant",
        **bindings,
    )
    mismatches = {
        "creator_principal_id": "principal.someone_else",
        "creator_session_id": "session.someone_else",
        "launch_command_id": UUID("22222222-2222-4222-8222-222222222222"),
        "launch_command_sha256": "a" * 64,
        "overlay_sha256": "b" * 64,
        "roster_sha256": "c" * 64,
        "model_identity_id": "model_identity.someone_else",
        "provider_id": "someone_else",
    }
    for field, mismatch in mismatches.items():
        capability = ProcessLocalOneShotLiveProviderCapability(grant=grant)
        with pytest.raises(LiveProviderGrantBindingError, match=field):
            capability.consume(**cast(_LiveProviderGrantBindings, bindings | {field: mismatch}))
        assert capability.consumption_count == 0

    unauthenticated = ProcessLocalOneShotLiveProviderCapability(grant=grant)
    coordinator = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(),
        live_provider_capability=unauthenticated,
    )
    with pytest.raises(SessionAuthenticationError):
        coordinator.admit_start_match(command, context=_context(), match_id=_MATCH_ID)
    assert unauthenticated.consumption_count == 0

    capability = ProcessLocalOneShotLiveProviderCapability(grant=grant)
    coordinator = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(_operator()),
        live_provider_capability=capability,
    )
    provenance = coordinator.admit_start_match(
        command,
        context=_context(),
        match_id=_MATCH_ID,
    )
    assert provenance.launch_command_id == command.command_id
    assert capability.consumption_count == 1
    with pytest.raises(LiveProviderGrantConsumedError, match="consumed"):
        capability.consume(**bindings)


@pytest.mark.unit
def test_same_live_model_identity_can_fill_both_llm_seats(tmp_path: Path) -> None:
    overlay = _live_overlay(tmp_path)
    base = _roster()
    model = next(
        option for option in base.options if isinstance(option, ModelSOModelPlayerOptionBinding)
    )
    roster = base.model_copy(
        update={
            "seats": (
                base.seats[0].model_copy(update={"allowed_option_ids": (model.option_id,)}),
                base.seats[1].model_copy(update={"allowed_option_ids": (model.option_id,)}),
            )
        }
    )
    command = _command(overlay, roster).model_copy(
        update={
            "selections": (
                ModelSOStartMatchSeatSelection(side="red", option_id=model.option_id),
                ModelSOStartMatchSeatSelection(side="blue", option_id=model.option_id),
            )
        }
    )
    session = ModelSOAuthenticatedSession(
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        human_identity_id=None,
        permissions=("match:create",),
    )
    grant = ModelSOLiveProviderLaunchGrant(
        creator_principal_id=session.principal_id,
        creator_session_id=session.session_id,
        launch_command_id=command.command_id,
        launch_command_sha256=canonical_command_sha256(command),
        overlay_sha256=command.expected_overlay_sha256,
        roster_sha256=command.expected_roster_sha256,
        model_identity_id=model.model_identity_id,
        provider_id="remote",
        max_completions=64,
    )
    capability = ProcessLocalOneShotLiveProviderCapability(grant=grant)
    coordinator = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(session),
        live_provider_capability=capability,
    )

    provenance = coordinator.admit_start_match(
        command,
        context=ModelSOStartMatchAuthorityContext(
            creator_principal_id=session.principal_id,
            creator_session_id=session.session_id,
        ),
        match_id=_MATCH_ID,
    )

    assert [assignment.kind for assignment in provenance.seat_assignments] == ["model", "model"]
    assert capability.consumption_count == 1


@pytest.mark.unit
def test_command_cannot_be_rebound_to_another_match_id(tmp_path: Path) -> None:
    overlay = _overlay(tmp_path)
    roster = _roster()
    coordinator = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(_operator()),
    )
    command = _command(overlay, roster)
    first = coordinator.admit_start_match(command, context=_context(), match_id=_MATCH_ID)

    assert (
        coordinator.admit_start_match(
            command,
            context=_context(),
            match_id=_MATCH_ID,
        )
        is first
    )
    with pytest.raises(MatchLaunchConflictError, match=str(UUID(int=command.command_id.int))):
        coordinator.admit_start_match(
            command,
            context=_context(),
            match_id="match.01JABCDE0123456789ABCDEFGY",
        )
