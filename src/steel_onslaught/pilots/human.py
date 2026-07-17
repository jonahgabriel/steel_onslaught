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
from steel_onslaught.contracts.player_selection import Side
from steel_onslaught.immutable import FrozenJSONMapping
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    SOPilotAction,
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
    """Consume an authenticated pre-submitted action into a local closed result.

    ``consume`` never waits and never falls back.  Missing, stale, or unauthorized
    input propagates the inbox's fail-closed exception.  Runtime composition is
    intentionally outside this Phase 52 class.  This class deliberately has no
    ``decide`` method until the shared decision payload gains explicit human
    provenance in a later phase.
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
