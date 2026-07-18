"""Closed command-channel wire contracts for a future live application root."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.player_selection import (
    MatchId,
    MechId,
    PlayerOptionId,
    Sha256Digest,
    Side,
    TurnId,
)
from steel_onslaught.pilots.schemas import SOMoveDirection


class _ClosedStrictCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ModelSOStartMatchSeatSelection(_ClosedStrictCommand):
    side: Side
    option_id: PlayerOptionId


class ModelSOStartMatchCommand(_ClosedStrictCommand):
    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.start_match"]
    command_id: UUID
    expected_overlay_sha256: Sha256Digest
    expected_roster_sha256: Sha256Digest
    selections: tuple[ModelSOStartMatchSeatSelection, ModelSOStartMatchSeatSelection]

    @model_validator(mode="after")
    def _selections_are_exact(self) -> Self:
        sides = [selection.side for selection in self.selections]
        if set(sides) != {"red", "blue"} or len(sides) != len(set(sides)):
            raise ValueError("selections must contain exactly one red and one blue seat")
        return self


class ModelSORemainPlayerAction(_ClosedStrictCommand):
    kind: Literal["remain"]


class ModelSOMovePlayerAction(_ClosedStrictCommand):
    kind: Literal["move"]
    direction: SOMoveDirection
    speed: Literal["full"] | None = None


class ModelSOFireWeaponPlayerAction(_ClosedStrictCommand):
    kind: Literal["fire_weapon"]
    weapon_id: StrictStr = Field(min_length=1, pattern=r"^weapon\.")
    target_mech_id: MechId | None = None


class ModelSOVentPlayerAction(_ClosedStrictCommand):
    kind: Literal["vent"]


class ModelSOSwitchModePlayerAction(_ClosedStrictCommand):
    kind: Literal["switch_mode"]
    target_mode: ModeId


class ModelSODisengagePlayerAction(_ClosedStrictCommand):
    kind: Literal["disengage"]
    direction: Literal["defensive"]
    speed: Literal["full"] | None = None


PlayerAction = Annotated[
    ModelSORemainPlayerAction
    | ModelSOMovePlayerAction
    | ModelSOFireWeaponPlayerAction
    | ModelSOVentPlayerAction
    | ModelSOSwitchModePlayerAction
    | ModelSODisengagePlayerAction,
    Field(discriminator="kind"),
]


class ModelSOHumanTurnPrompt(_ClosedStrictCommand):
    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.human_turn"]
    match_id: MatchId
    turn_id: TurnId
    side: Side
    expected_tick: StrictInt = Field(ge=0)
    observation_sha256: Sha256Digest
    available_actions: tuple[PlayerAction, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _available_actions_are_unique(self) -> Self:
        canonical = [action.model_dump_json() for action in self.available_actions]
        if len(canonical) != len(set(canonical)):
            raise ValueError("available_actions must contain unique action choices")
        return self


class ModelSOPlayerActionCommand(_ClosedStrictCommand):
    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.player_action"]
    command_id: UUID
    match_id: MatchId
    turn_id: TurnId
    expected_tick: StrictInt = Field(ge=0)
    observation_sha256: Sha256Digest
    action: PlayerAction


CommandContract = ModelSOStartMatchCommand | ModelSOPlayerActionCommand
COMMAND_HASH_AUTHORITY_V1: Literal["process_lifetime_canonical_hash_only"] = (
    "process_lifetime_canonical_hash_only"
)
COMMAND_HASH_V1_HELD_CAPABILITIES = (
    "live_auth_or_ingress",
    "durable_idempotency_receipts_or_journal",
    "restart_or_crash_recovery",
)


def canonical_command_sha256(command: CommandContract) -> Sha256Digest:
    """Hash a validated command for process-lifetime equality only.

    This digest is not live authentication or ingress authorization, is not a
    durable idempotency receipt or journal, and makes no restart/crash recovery
    claim. Those capabilities remain held for a later runtime phase.
    """

    canonical = json.dumps(
        command.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "COMMAND_HASH_AUTHORITY_V1",
    "COMMAND_HASH_V1_HELD_CAPABILITIES",
    "CommandContract",
    "ModelSODisengagePlayerAction",
    "ModelSOFireWeaponPlayerAction",
    "ModelSOHumanTurnPrompt",
    "ModelSOMovePlayerAction",
    "ModelSOPlayerActionCommand",
    "ModelSORemainPlayerAction",
    "ModelSOStartMatchCommand",
    "ModelSOStartMatchSeatSelection",
    "ModelSOSwitchModePlayerAction",
    "ModelSOVentPlayerAction",
    "PlayerAction",
    "canonical_command_sha256",
]
