"""Focused concurrency, authentication, and freshness tests for the human inbox."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from uuid import UUID

import pytest

from steel_onslaught.commands.authority import (
    CommandConflictError,
    CommandOwnershipError,
    ModelSOAuthenticatedSession,
    PermissionDeniedError,
    PrincipalId,
    SessionAuthenticationError,
    SessionId,
)
from steel_onslaught.commands.inbox import (
    ActionNotAvailableError,
    HumanDecisionNotReadyError,
    HumanTurnDecisionConflictError,
    ModelSOHumanActionAdmission,
    ProcessLocalHumanDecisionInbox,
    StaleHumanTurnError,
    canonical_observation_sha256,
)
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.commands import (
    ModelSOHumanTurnPrompt,
    ModelSOMovePlayerAction,
    ModelSOPlayerActionCommand,
    ModelSORemainPlayerAction,
    ModelSOVentPlayerAction,
)
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.match.composition import SystemIdentityProvider
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

_MATCH_ID = "match.01J00000000000000000000000"
_COMMAND_ID = UUID("22222222-2222-4222-8222-222222222222")


class _Sessions:
    def __init__(self, *sessions: ModelSOAuthenticatedSession) -> None:
        if not sessions:
            sessions = (_session(),)
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


def _session(
    *,
    principal_id: str = "principal.local_operator",
    session_id: str = "session.local_operator",
) -> ModelSOAuthenticatedSession:
    return ModelSOAuthenticatedSession.model_validate(
        {
            "principal_id": principal_id,
            "session_id": session_id,
            "human_identity_id": "human_identity.local_operator",
            "permissions": ("seat:red",),
        }
    )


def _observation(*, tick: int = 3, match_id: str = _MATCH_ID) -> ModelSOPilotObservation:
    boiler = ModelSOBoilerState(
        match_id=match_id,
        mech_id="mech.red.01",
        tick=tick,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=3,
        heat_current=20,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )
    return ModelSOPilotObservation(
        match_id=match_id,
        mech_id="mech.red.01",
        player_id="player.red",
        tick=tick,
        match_elapsed_ticks=tick,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.gatling_array",
                damage=12,
                range=6,
                pressure_cost=8,
                heat_generated=10,
                cooldown_remaining_ticks=0,
            )
        ],
        current_mode=ModeId.RECON,
        mode_lock_expired=True,
        position=ModelSOPosition(x=3, y=7),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=[],
    )


def _prompt(
    observation: ModelSOPilotObservation,
    *,
    actions: tuple[object, ...] | None = None,
    turn_id: str = "turn.local.003",
) -> ModelSOHumanTurnPrompt:
    return ModelSOHumanTurnPrompt.model_validate(
        {
            "schema_version": "1",
            "kind": "steel_onslaught.human_turn",
            "match_id": observation.match_id,
            "turn_id": turn_id,
            "side": "red",
            "expected_tick": observation.tick,
            "observation_sha256": canonical_observation_sha256(observation),
            "available_actions": actions
            or (
                ModelSORemainPlayerAction(kind="remain"),
                ModelSOMovePlayerAction(kind="move", direction="toward_enemy", speed="full"),
            ),
        }
    )


def _command(
    prompt: ModelSOHumanTurnPrompt,
    *,
    command_id: UUID = _COMMAND_ID,
    action: object | None = None,
) -> ModelSOPlayerActionCommand:
    return ModelSOPlayerActionCommand.model_validate(
        {
            "schema_version": "1",
            "kind": "steel_onslaught.player_action",
            "command_id": command_id,
            "match_id": prompt.match_id,
            "turn_id": prompt.turn_id,
            "expected_tick": prompt.expected_tick,
            "observation_sha256": prompt.observation_sha256,
            "action": action or ModelSORemainPlayerAction(kind="remain"),
        }
    )


def _publish(
    inbox: ProcessLocalHumanDecisionInbox,
    prompt: ModelSOHumanTurnPrompt,
    *,
    principal_id: str = "principal.local_operator",
    session_id: str = "session.local_operator",
) -> None:
    inbox.publish_prompt(
        prompt,
        principal_id=principal_id,
        session_id=session_id,
    )


@pytest.mark.unit
def test_same_prompt_publication_is_thread_safe_and_idempotent() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    prompt = _prompt(_observation())
    publish = partial(
        inbox.publish_prompt,
        prompt,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
    )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _index: publish(), range(64)))

    assert all(result is results[0] for result in results)


@pytest.mark.unit
def test_same_action_is_one_thread_safe_admission_and_replayable_consumption() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    observation = _observation()
    prompt = _prompt(observation)
    command = _command(prompt)
    _publish(inbox, prompt)
    submit = partial(
        inbox.submit_action,
        command,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        side="red",
    )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _index: submit(), range(64)))

    assert inbox.action_admission_count == 1
    assert all(result is results[0] for result in results)
    assert (
        inbox.consume_for_observation(
            observation,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )
        is command
    )


@pytest.mark.unit
def test_changed_hash_and_second_command_for_same_turn_conflict() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    prompt = _prompt(_observation())
    command = _command(prompt)
    _publish(inbox, prompt)
    inbox.submit_action(
        command,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        side="red",
    )

    changed = _command(
        prompt,
        action=ModelSOMovePlayerAction(kind="move", direction="toward_enemy", speed="full"),
    )
    with pytest.raises(CommandConflictError, match="different canonical content"):
        inbox.submit_action(
            changed,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )


@pytest.mark.unit
def test_conflicting_concurrent_commands_have_one_atomic_winner() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    prompt = _prompt(_observation())
    _publish(inbox, prompt)
    commands = (
        _command(prompt, command_id=UUID("55555555-5555-4555-8555-555555555555")),
        _command(prompt, command_id=UUID("66666666-6666-4666-8666-666666666666")),
    )

    def submit(
        command: ModelSOPlayerActionCommand,
    ) -> ModelSOHumanActionAdmission | HumanTurnDecisionConflictError:
        try:
            return inbox.submit_action(
                command,
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
            )
        except HumanTurnDecisionConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, commands))

    assert sum(isinstance(result, ModelSOHumanActionAdmission) for result in results) == 1
    assert sum(isinstance(result, HumanTurnDecisionConflictError) for result in results) == 1
    assert inbox.action_admission_count == 1


@pytest.mark.unit
def test_same_command_uuid_is_rejected_for_another_authenticated_owner() -> None:
    primary = _session()
    other = _session(principal_id="principal.other", session_id="session.other")
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions(primary, other))
    prompt = _prompt(_observation())
    command = _command(prompt)
    _publish(inbox, prompt)
    _publish(
        inbox,
        prompt,
        principal_id=other.principal_id,
        session_id=other.session_id,
    )
    inbox.submit_action(
        command,
        principal_id=primary.principal_id,
        session_id=primary.session_id,
        side="red",
    )

    with pytest.raises(CommandOwnershipError, match="another authority context"):
        inbox.submit_action(
            command,
            principal_id=other.principal_id,
            session_id=other.session_id,
            side="red",
        )

    second = _command(
        prompt,
        command_id=UUID("33333333-3333-4333-8333-333333333333"),
    )
    with pytest.raises(HumanTurnDecisionConflictError, match="already decided"):
        inbox.submit_action(
            second,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )


@pytest.mark.unit
def test_wrong_principal_and_seat_fail_closed() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    prompt = _prompt(_observation())
    command = _command(prompt)
    _publish(inbox, prompt)

    with pytest.raises(SessionAuthenticationError):
        inbox.submit_action(
            command,
            principal_id="principal.impostor",
            session_id="session.local_operator",
            side="red",
        )
    with pytest.raises(PermissionDeniedError, match="seat:blue"):
        inbox.submit_action(
            command,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="blue",
        )


@pytest.mark.unit
def test_stale_turn_tick_observation_and_unavailable_action_reject() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    observation = _observation()
    prompt = _prompt(observation, actions=(ModelSORemainPlayerAction(kind="remain"),))
    _publish(inbox, prompt)

    for update in (
        {"turn_id": "turn.local.stale"},
        {"expected_tick": prompt.expected_tick + 1},
        {"observation_sha256": "a" * 64},
    ):
        stale = _command(prompt).model_copy(update=update)
        with pytest.raises(StaleHumanTurnError):
            inbox.submit_action(
                stale,
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
            )

    unavailable = _command(prompt, action=ModelSOVentPlayerAction(kind="vent"))
    with pytest.raises(ActionNotAvailableError):
        inbox.submit_action(
            unavailable,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )


@pytest.mark.unit
def test_prompt_freshness_and_missing_decision_never_fallback() -> None:
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    observation = _observation()
    prompt = _prompt(observation)
    _publish(inbox, prompt)

    with pytest.raises(HumanDecisionNotReadyError):
        inbox.consume_for_observation(
            observation,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )


@pytest.mark.unit
def test_system_identity_provider_match_and_strict_turn_id_flow_through_inbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FixedUlid:
        str = _MATCH_ID.removeprefix("match.")

    monkeypatch.setattr("steel_onslaught.match.composition.ulid.new", _FixedUlid)
    match_id = SystemIdentityProvider().new_match_id()
    observation = _observation(match_id=match_id)
    prompt = _prompt(observation, turn_id="turn.system.003")
    command = _command(prompt)
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    _publish(inbox, prompt)
    inbox.submit_action(
        command,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        side="red",
    )

    consumed = inbox.consume_for_observation(
        observation,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        side="red",
    )

    assert match_id == _MATCH_ID
    assert consumed.match_id == match_id
    assert consumed.turn_id == "turn.system.003"

    changed_same_tick = prompt.model_copy(update={"turn_id": "turn.local.changed"})
    with pytest.raises(StaleHumanTurnError, match="advance expected_tick"):
        _publish(inbox, changed_same_tick)

    with pytest.raises(StaleHumanTurnError, match="tick/hash"):
        inbox.consume_for_observation(
            _observation(tick=4),
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )
