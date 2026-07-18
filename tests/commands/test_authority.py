"""Focused authentication, contract, and idempotency tests for command authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from uuid import UUID

import pytest

from steel_onslaught.commands.authority import (
    CommandConflictError,
    CommandContractStaleError,
    CommandOwnershipError,
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PermissionDeniedError,
    PrincipalId,
    ProcessLocalCommandAuthority,
    SelectionAuthorityError,
    SessionAuthenticationError,
    SessionId,
    canonical_overlay_sha256,
)
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
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

_COMMAND_ID = UUID("11111111-1111-4111-8111-111111111111")


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


def _operator(
    *,
    permissions: tuple[str, ...] = ("match:create", "seat:red"),
    human_identity_id: str = "human_identity.local_operator",
) -> ModelSOAuthenticatedSession:
    return ModelSOAuthenticatedSession.model_validate(
        {
            "principal_id": "principal.local_operator",
            "session_id": "session.local_operator",
            "human_identity_id": human_identity_id,
            "permissions": permissions,
        }
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
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.local_qwen"),
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


def _authority(
    tmp_path: Path,
    *,
    session: ModelSOAuthenticatedSession | None = None,
) -> tuple[
    ProcessLocalCommandAuthority,
    ModelSOApplicationOverlay,
    ModelSOPlayerRosterBinding,
]:
    overlay = _overlay(tmp_path)
    roster = _roster()
    authority = ProcessLocalCommandAuthority(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(session or _operator()),
    )
    return authority, overlay, roster


@pytest.mark.unit
def test_same_authenticated_command_is_one_thread_safe_process_admission(
    tmp_path: Path,
) -> None:
    authority, overlay, roster = _authority(tmp_path)
    admit = partial(authority.admit_start_match, _command(overlay, roster), context=_context())

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _index: admit(), range(64)))

    assert authority.admission_count == 1
    assert all(result is results[0] for result in results)
    assert results[0].authority_scope == "process_lifetime"
    assert results[0].principal_id == "principal.local_operator"


@pytest.mark.unit
def test_same_id_with_different_canonical_order_conflicts(tmp_path: Path) -> None:
    authority, overlay, roster = _authority(tmp_path)
    command = _command(overlay, roster)
    authority.admit_start_match(command, context=_context())
    changed = command.model_copy(update={"selections": tuple(reversed(command.selections))})

    with pytest.raises(CommandConflictError, match="different canonical content"):
        authority.admit_start_match(changed, context=_context())


@pytest.mark.unit
def test_mirrored_two_human_claim_order_is_semantically_idempotent(tmp_path: Path) -> None:
    overlay = _overlay(tmp_path)
    base_roster = _roster()
    human_id = "player_option.browser_human"
    model_id = "player_option.local_qwen"
    roster = base_roster.model_copy(
        update={
            "seats": (
                ModelSOSeatLaunchPolicy(
                    side="red",
                    loadout_id="loadout.playable.red_light",
                    allowed_option_ids=(human_id, model_id),
                ),
                ModelSOSeatLaunchPolicy(
                    side="blue",
                    loadout_id="loadout.playable.blue_light",
                    allowed_option_ids=(human_id, model_id),
                ),
            )
        }
    )
    operator = _operator(permissions=("match:create", "seat:red", "seat:blue"))
    authority = ProcessLocalCommandAuthority(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(operator),
    )
    command = _command(overlay, roster).model_copy(
        update={
            "selections": (
                ModelSOStartMatchSeatSelection(side="red", option_id=human_id),
                ModelSOStartMatchSeatSelection(side="blue", option_id=human_id),
            )
        }
    )
    red = ModelSOHumanSeatAuthorityClaim(
        side="red",
        principal_id=operator.principal_id,
        session_id=operator.session_id,
    )
    blue = ModelSOHumanSeatAuthorityClaim(
        side="blue",
        principal_id=operator.principal_id,
        session_id=operator.session_id,
    )
    forward = ModelSOStartMatchAuthorityContext(
        creator_principal_id=operator.principal_id,
        creator_session_id=operator.session_id,
        human_seats=(red, blue),
    )
    reversed_claims = forward.model_copy(
        update={"human_seats": (blue, red)},
    )

    first = authority.admit_start_match(command, context=forward)
    second = authority.admit_start_match(command, context=reversed_claims)

    assert forward.human_seats == (red, blue)
    assert reversed_claims.human_seats == (blue, red)
    assert second is first


@pytest.mark.unit
def test_same_command_with_different_authority_context_conflicts(tmp_path: Path) -> None:
    overlay = _overlay(tmp_path)
    roster = _roster()
    operator = _operator()
    delegate = ModelSOAuthenticatedSession(
        principal_id="principal.delegate",
        session_id="session.delegate",
        human_identity_id="human_identity.local_operator",
        permissions=("seat:red",),
    )
    authority = ProcessLocalCommandAuthority(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(operator, delegate),
    )
    command = _command(overlay, roster)
    authority.admit_start_match(command, context=_context())
    delegated = ModelSOStartMatchAuthorityContext(
        creator_principal_id=operator.principal_id,
        creator_session_id=operator.session_id,
        human_seats=(
            ModelSOHumanSeatAuthorityClaim(
                side="red",
                principal_id=delegate.principal_id,
                session_id=delegate.session_id,
            ),
        ),
    )

    with pytest.raises(CommandOwnershipError, match="another authority context"):
        authority.admit_start_match(command, context=delegated)


@pytest.mark.unit
def test_authentication_permission_and_human_identity_fail_closed(tmp_path: Path) -> None:
    overlay = _overlay(tmp_path)
    roster = _roster()
    command = _command(overlay, roster)

    missing = ProcessLocalCommandAuthority(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(),
    )
    with pytest.raises(SessionAuthenticationError):
        missing.admit_start_match(command, context=_context())

    no_create = ProcessLocalCommandAuthority(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(_operator(permissions=("seat:red",))),
    )
    with pytest.raises(PermissionDeniedError, match="match:create"):
        no_create.admit_start_match(command, context=_context())

    wrong_human = ProcessLocalCommandAuthority(
        overlay=overlay,
        roster=roster,
        sessions=_Sessions(_operator(human_identity_id="human_identity.someone_else")),
    )
    with pytest.raises(SelectionAuthorityError, match="does not own"):
        wrong_human.admit_start_match(command, context=_context())


@pytest.mark.unit
def test_expected_hash_and_roster_membership_fail_closed(tmp_path: Path) -> None:
    authority, overlay, roster = _authority(tmp_path)
    command = _command(overlay, roster)
    stale = command.model_copy(update={"expected_overlay_sha256": "f" * 64})
    with pytest.raises(CommandContractStaleError, match="overlay"):
        authority.admit_start_match(stale, context=_context())

    disallowed = command.model_copy(
        update={
            "selections": (
                ModelSOStartMatchSeatSelection(side="red", option_id="player_option.local_qwen"),
                command.selections[1],
            )
        }
    )
    with pytest.raises(SelectionAuthorityError, match="not allowed"):
        authority.admit_start_match(disallowed, context=_context())
