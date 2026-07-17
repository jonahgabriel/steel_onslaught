"""HumanPilot translation tests with no runtime composition or fallback behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from uuid import UUID

import pytest
from pydantic import ValidationError

from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    PrincipalId,
    SessionId,
)
from steel_onslaught.commands.inbox import (
    HumanDecisionCancelledError,
    HumanDecisionNotReadyError,
    ProcessLocalHumanDecisionInbox,
    canonical_observation_sha256,
)
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.commands import (
    ModelSODisengagePlayerAction,
    ModelSOFireWeaponPlayerAction,
    ModelSOHumanTurnPrompt,
    ModelSOMovePlayerAction,
    ModelSOPlayerActionCommand,
    ModelSORemainPlayerAction,
    ModelSOSwitchModePlayerAction,
    ModelSOVentPlayerAction,
    PlayerAction,
)
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.pilots.human import HumanPilot, ModelSOHumanInputSelection
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    PilotProtocol,
    SOPilotAction,
    SOPilotReasonCode,
)

_MATCH_ID = "match.01J00000000000000000000000"


class _Sessions:
    def __init__(self) -> None:
        self._session = ModelSOAuthenticatedSession(
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            human_identity_id="human_identity.local_operator",
            permissions=("seat:red",),
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


def _observation() -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id=_MATCH_ID,
        mech_id="mech.red.01",
        player_id="player.red",
        tick=3,
        match_elapsed_ticks=3,
        boiler=ModelSOBoilerState(
            match_id=_MATCH_ID,
            mech_id="mech.red.01",
            tick=3,
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
        ),
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


def _pending(
    action: PlayerAction,
) -> tuple[
    HumanPilot,
    ModelSOPilotObservation,
    ProcessLocalHumanDecisionInbox,
    ModelSOPlayerActionCommand,
]:
    observation = _observation()
    prompt = ModelSOHumanTurnPrompt(
        schema_version="1",
        kind="steel_onslaught.human_turn",
        match_id=_MATCH_ID,
        turn_id="turn.local.003",
        side="red",
        expected_tick=observation.tick,
        observation_sha256=canonical_observation_sha256(observation),
        available_actions=(action,),
    )
    command = ModelSOPlayerActionCommand(
        schema_version="1",
        kind="steel_onslaught.player_action",
        command_id=UUID("44444444-4444-4444-8444-444444444444"),
        match_id=prompt.match_id,
        turn_id=prompt.turn_id,
        expected_tick=prompt.expected_tick,
        observation_sha256=prompt.observation_sha256,
        action=action,
    )
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    inbox.publish_prompt(
        prompt,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
    )
    return (
        HumanPilot(
            inbox=inbox,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        ),
        observation,
        inbox,
        command,
    )


def _prepare(action: PlayerAction) -> tuple[HumanPilot, ModelSOPilotObservation]:
    pilot, observation, inbox, command = _pending(action)
    inbox.submit_action(
        command,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        side="red",
    )
    return pilot, observation


@pytest.mark.unit
@pytest.mark.parametrize(
    ("action", "expected_action", "expected_params"),
    [
        (ModelSORemainPlayerAction(kind="remain"), SOPilotAction.REMAIN, {}),
        (
            ModelSOMovePlayerAction(kind="move", direction="toward_enemy", speed="full"),
            SOPilotAction.MOVE,
            {"direction": "toward_enemy", "speed": "full"},
        ),
        (
            ModelSOFireWeaponPlayerAction(
                kind="fire_weapon",
                weapon_id="weapon.gatling_array",
                target_mech_id="mech.blue.01",
            ),
            SOPilotAction.FIRE_WEAPON,
            {"weapon_id": "weapon.gatling_array", "target_mech_id": "mech.blue.01"},
        ),
        (ModelSOVentPlayerAction(kind="vent"), SOPilotAction.VENT, {}),
        (
            ModelSOSwitchModePlayerAction(kind="switch_mode", target_mode=ModeId.ASSAULT),
            SOPilotAction.SWITCH_MODE,
            {"target_mode": "assault"},
        ),
        (
            ModelSODisengagePlayerAction(kind="disengage", direction="defensive", speed="full"),
            SOPilotAction.DISENGAGE,
            {"direction": "defensive", "speed": "full"},
        ),
    ],
)
def test_human_pilot_returns_closed_local_input_provenance(
    action: PlayerAction,
    expected_action: SOPilotAction,
    expected_params: dict[str, object],
) -> None:
    pilot, observation = _prepare(action)

    result = pilot.consume(observation)

    assert isinstance(pilot, PilotProtocol)
    assert isinstance(result, ModelSOHumanInputSelection)
    assert result.source == "human_input"
    assert result.action is expected_action
    assert dict(result.action_params) == expected_params
    assert result.command.action == action


@pytest.mark.unit
def test_human_pilot_never_waits_or_falls_back_when_action_is_missing() -> None:
    observation = _observation()
    inbox = ProcessLocalHumanDecisionInbox(sessions=_Sessions())
    inbox.publish_prompt(
        ModelSOHumanTurnPrompt(
            schema_version="1",
            kind="steel_onslaught.human_turn",
            match_id=_MATCH_ID,
            turn_id="turn.local.003",
            side="red",
            expected_tick=observation.tick,
            observation_sha256=canonical_observation_sha256(observation),
            available_actions=(ModelSORemainPlayerAction(kind="remain"),),
        ),
        principal_id="principal.local_operator",
        session_id="session.local_operator",
    )
    pilot = HumanPilot(
        inbox=inbox,
        principal_id="principal.local_operator",
        session_id="session.local_operator",
        side="red",
    )

    with pytest.raises(HumanDecisionNotReadyError):
        pilot.consume(observation)


@pytest.mark.unit
def test_human_pilot_decide_waits_and_returns_exact_command_provenance() -> None:
    pilot, observation, inbox, command = _pending(ModelSORemainPlayerAction(kind="remain"))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(pilot.decide, observation)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.02)
        first = inbox.submit_action(
            command,
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            side="red",
        )
        assert (
            inbox.submit_action(
                command,
                principal_id="principal.local_operator",
                session_id="session.local_operator",
                side="red",
            )
            is first
        )
        decision = future.result(timeout=1.0)

    assert isinstance(pilot, PilotProtocol)
    assert decision.action is SOPilotAction.REMAIN
    assert decision.reason_code is SOPilotReasonCode.HUMAN_INPUT
    assert decision.decision_source is not None
    assert decision.decision_source.kind == "human"
    assert decision.decision_source.command_id == command.command_id
    assert decision.decision_source.turn_id == command.turn_id
    assert decision.decision_source.observation_sha256 == command.observation_sha256


@pytest.mark.unit
def test_human_pilot_decide_has_explicit_shutdown_cancellation() -> None:
    pilot, observation, inbox, _command = _pending(ModelSORemainPlayerAction(kind="remain"))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(pilot.decide, observation)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.02)
        inbox.shutdown()
        with pytest.raises(HumanDecisionCancelledError, match="shut down"):
            future.result(timeout=1.0)


@pytest.mark.unit
def test_human_input_provenance_is_closed_frozen_and_local_only() -> None:
    pilot, observation = _prepare(ModelSORemainPlayerAction(kind="remain"))
    result = pilot.consume(observation)

    with pytest.raises(ValidationError):
        result.source = "forged"  # type: ignore[assignment]
    with pytest.raises(TypeError):
        result.action_params["forged"] = True  # type: ignore[index]
    with pytest.raises(ValidationError):
        ModelSOHumanInputSelection.model_validate(
            {**result.model_dump(mode="python"), "unexpected": True}
        )
