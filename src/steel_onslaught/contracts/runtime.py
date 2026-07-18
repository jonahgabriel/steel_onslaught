"""Strict command and status contracts for the browser match runtime.

This module intentionally contains no runtime controller or transport code.  It
defines the wire shapes that a later Gate-1 composition root will validate and
route.  Runtime progression remains unchanged until that owner is wired.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal, Self
from uuid import RFC_4122, UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

RUNTIME_COMMAND_KIND: Literal["steel_onslaught.runtime_command"] = "steel_onslaught.runtime_command"
MAX_RUNTIME_INTEGER = 2**53 - 1
_WIRE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class SORuntimeAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"


class SORuntimeMode(StrEnum):
    ONE_GAME = "one_game"
    CONTINUOUS = "continuous"


class SORuntimeStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ENDED = "ended"


class _ClosedRuntimeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _validate_wire_uuid(value: object) -> object:
    """Require the same RFC4122 v1-v8/variant policy as the TS mirror."""

    if value is None:
        return None
    text = str(value) if isinstance(value, UUID) else value
    if not isinstance(text, str) or _WIRE_UUID_RE.fullmatch(text) is None:
        raise ValueError("must be a canonical RFC4122 UUID")
    parsed = UUID(text)
    if parsed.version not in range(1, 9) or parsed.variant is not RFC_4122:
        raise ValueError("must be an RFC4122 UUID with version 1-8")
    return parsed


class ModelSORuntimeCommand(_ClosedRuntimeModel):
    """One strict command for the future injected runtime controller.

    ``expected_revision`` is an optimistic-concurrency token owned by the
    runtime projection.  ``owner_id`` is opaque identity metadata; it is
    carried for admission and conflict checks, not resolved in this contract.
    A start command must choose exactly one mode.  Pause, resume, and stop
    never carry a mode, preventing clients from smuggling a second lifecycle
    transition.  Stop is a terminal request; its controller semantics are
    intentionally deferred to the runtime integration slice.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.runtime_command"]
    command_id: UUID
    expected_revision: StrictInt = Field(ge=0, le=MAX_RUNTIME_INTEGER)
    owner_id: StrictStr = Field(min_length=1, max_length=128)
    action: SORuntimeAction
    mode: SORuntimeMode | None = None

    _command_id_is_wire_uuid = field_validator("command_id", mode="before")(_validate_wire_uuid)

    @model_validator(mode="after")
    def _mode_matches_action(self) -> Self:
        if self.action is SORuntimeAction.START and self.mode is None:
            raise ValueError("start_requires_mode")
        if self.action is not SORuntimeAction.START and self.mode is not None:
            raise ValueError("mode_only_valid_for_start")
        return self


class ModelSORuntimeStatusPayload(_ClosedRuntimeModel):
    """Strict runtime projection carried by ``runtime_status_changed``."""

    status: SORuntimeStatus
    mode: SORuntimeMode | None
    revision: StrictInt = Field(ge=0, le=MAX_RUNTIME_INTEGER)
    owner_id: StrictStr = Field(min_length=1, max_length=128)
    match_index: StrictInt = Field(ge=0, le=MAX_RUNTIME_INTEGER)
    last_command_id: UUID | None

    _last_command_id_is_wire_uuid = field_validator("last_command_id", mode="before")(
        _validate_wire_uuid
    )

    @model_validator(mode="after")
    def _status_matches_mode(self) -> Self:
        if self.status is SORuntimeStatus.READY and self.mode is not None:
            raise ValueError("ready_status_requires_null_mode")
        if self.status is not SORuntimeStatus.READY and self.mode is None:
            raise ValueError("active_status_requires_mode")
        if self.status is SORuntimeStatus.READY and self.last_command_id is not None:
            raise ValueError("ready_status_requires_null_last_command_id")
        return self


__all__ = [
    "MAX_RUNTIME_INTEGER",
    "RUNTIME_COMMAND_KIND",
    "ModelSORuntimeCommand",
    "ModelSORuntimeStatusPayload",
    "SORuntimeAction",
    "SORuntimeMode",
    "SORuntimeStatus",
]
