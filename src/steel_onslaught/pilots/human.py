"""Unwired human-input consumer backed by a process-local decision inbox.

This module intentionally does not implement ``PilotProtocol`` yet.  The
shared pilot-decision reason/payload surface has no human-input provenance in
Phase 52; adapting this local result into an event-ready decision belongs to a
later payload-parity phase.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.commands.authority import PrincipalId, SessionId
from steel_onslaught.commands.inbox import ProcessLocalHumanDecisionInbox
from steel_onslaught.contracts.commands import (
    ModelSODisengagePlayerAction,
    ModelSOFireWeaponPlayerAction,
    ModelSOMovePlayerAction,
    ModelSOPlayerActionCommand,
    ModelSORemainPlayerAction,
    ModelSOSwitchModePlayerAction,
    ModelSOVentPlayerAction,
    PlayerAction,
)
from steel_onslaught.contracts.player_selection import ModelSOHumanDecisionSource, Side
from steel_onslaught.immutable import FrozenJSONMapping
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
    available_actions,
)


def _translate_action(action: PlayerAction) -> tuple[SOPilotAction, dict[str, object]]:
    if isinstance(action, ModelSORemainPlayerAction):
        return SOPilotAction.REMAIN, {}
    if isinstance(action, ModelSOMovePlayerAction):
        return SOPilotAction.MOVE, action.model_dump(exclude={"kind"}, exclude_none=True)
    if isinstance(action, ModelSOFireWeaponPlayerAction):
        return SOPilotAction.FIRE_WEAPON, action.model_dump(exclude={"kind"}, exclude_none=True)
    if isinstance(action, ModelSOVentPlayerAction):
        return SOPilotAction.VENT, {}
    if isinstance(action, ModelSOSwitchModePlayerAction):
        return SOPilotAction.SWITCH_MODE, action.model_dump(exclude={"kind"}, exclude_none=True)
    if isinstance(action, ModelSODisengagePlayerAction):
        return SOPilotAction.DISENGAGE, action.model_dump(exclude={"kind"}, exclude_none=True)
    raise TypeError(f"unsupported closed human action: {type(action).__name__}")


class ModelSOHumanInputSelection(BaseModel):
    """Closed local provenance for one authenticated human input selection."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.human_input_selection"] = "steel_onslaught.human_input_selection"
    source: Literal["human_input"] = "human_input"
    command: ModelSOPlayerActionCommand
    action: SOPilotAction
    action_params: FrozenJSONMapping = Field(validate_default=True)


class HumanPilot:
    """Consume an authenticated action into a local result or event-ready decision.

    ``consume`` never waits and never falls back.  Missing, stale, or unauthorized
    input propagates the inbox's fail-closed exception.  ``decide`` waits only on
    the inbox condition for the exact published observation; accepted action or
    explicit shutdown are its only exits.  Neither path polls or synthesizes a
    fallback.
    """

    def __init__(
        self,
        *,
        inbox: ProcessLocalHumanDecisionInbox,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> None:
        self._inbox = inbox
        self._principal_id = principal_id
        self._session_id = session_id
        self._side = side

    def consume(self, observation: ModelSOPilotObservation) -> ModelSOHumanInputSelection:
        command = self._inbox.consume_for_observation(
            observation,
            principal_id=self._principal_id,
            session_id=self._session_id,
            side=self._side,
        )
        return self._selection(command, observation)

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        """Wait for one exact admitted command and return its typed provenance."""

        command = self._inbox.wait_for_observation(
            observation,
            principal_id=self._principal_id,
            session_id=self._session_id,
            side=self._side,
        )
        selection = self._selection(command, observation)
        return ModelSOPilotDecision(
            action=selection.action,
            action_params=selection.action_params,
            reason_code=SOPilotReasonCode.HUMAN_INPUT,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=selection.action, score=1.0),),
            decision_source=ModelSOHumanDecisionSource(
                kind="human",
                input_source="browser_command",
                command_id=command.command_id,
                turn_id=command.turn_id,
                observation_sha256=command.observation_sha256,
            ),
        )

    @staticmethod
    def _selection(
        command: ModelSOPlayerActionCommand,
        observation: ModelSOPilotObservation,
    ) -> ModelSOHumanInputSelection:
        action, action_params = _translate_action(command.action)
        if action not in available_actions(observation):
            raise ValueError(
                f"human action {action.value!r} is unavailable for observation tick "
                f"{observation.tick}"
            )
        return ModelSOHumanInputSelection(
            command=command,
            action=action,
            action_params=action_params,
        )


__all__ = ["HumanPilot", "ModelSOHumanInputSelection"]
