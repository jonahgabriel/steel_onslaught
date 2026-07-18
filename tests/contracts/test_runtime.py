"""Strict, transport-free runtime lifecycle contract tests."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.runtime import (
    ModelSORuntimeCommand,
    ModelSORuntimeStatusPayload,
    SORuntimeAction,
    SORuntimeMode,
    SORuntimeStatus,
)

_COMMAND_ID = UUID("11111111-1111-4111-8111-111111111111")
_OWNER_ID = "runtime_owner.browser"


def _command(action: str, *, mode: str | None = None, revision: int = 0) -> dict[str, object]:
    raw: dict[str, object] = {
        "schema_version": "1",
        "kind": "steel_onslaught.runtime_command",
        "command_id": _COMMAND_ID,
        "expected_revision": revision,
        "owner_id": _OWNER_ID,
        "action": SORuntimeAction(action),
    }
    if mode is not None:
        raw["mode"] = SORuntimeMode(mode)
    return raw


@pytest.mark.unit
@pytest.mark.parametrize("mode", [SORuntimeMode.ONE_GAME, SORuntimeMode.CONTINUOUS])
def test_start_command_is_strict_and_typed(mode: SORuntimeMode) -> None:
    command = ModelSORuntimeCommand.model_validate(_command("start", mode=mode.value))

    assert command.action is SORuntimeAction.START
    assert command.mode is mode
    assert command.command_id == _COMMAND_ID
    assert command.expected_revision == 0
    assert command.owner_id == _OWNER_ID
    assert ModelSORuntimeCommand.model_validate_json(command.model_dump_json()) == command


@pytest.mark.unit
def test_command_json_accepts_wire_strings_at_the_json_boundary() -> None:
    raw = _command("pause")
    parsed = ModelSORuntimeCommand.model_validate_json(json.dumps(raw, default=str))
    assert parsed.action is SORuntimeAction.PAUSE


@pytest.mark.unit
@pytest.mark.parametrize("action", ["pause", "resume", "stop"])
def test_non_start_commands_forbid_mode(action: str) -> None:
    command = ModelSORuntimeCommand.model_validate(_command(action))
    assert command.action.value == action
    with pytest.raises(ValidationError, match="mode_only_valid_for_start"):
        ModelSORuntimeCommand.model_validate(_command(action, mode="one_game"))


@pytest.mark.unit
def test_start_requires_mode_and_commands_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="start_requires_mode"):
        ModelSORuntimeCommand.model_validate(_command("start"))
    with pytest.raises(ValidationError, match="extra"):
        ModelSORuntimeCommand.model_validate({**_command("pause"), "unexpected": True})


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        {**_command("pause"), "expected_revision": True},
        {**_command("pause"), "expected_revision": -1},
        {**_command("pause"), "owner_id": ""},
    ],
)
def test_command_revision_and_owner_are_strict(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ModelSORuntimeCommand.model_validate(raw)


@pytest.mark.unit
def test_command_wire_uuid_owner_and_revision_bounds_match_ts_policy() -> None:
    bad_uuid = _command("pause")
    bad_uuid["command_id"] = UUID("00000000-0000-0000-8000-000000000000")
    with pytest.raises(ValidationError, match="RFC4122"):
        ModelSORuntimeCommand.model_validate(bad_uuid)

    too_long_owner = _command("pause")
    too_long_owner["owner_id"] = "o" * 129
    with pytest.raises(ValidationError):
        ModelSORuntimeCommand.model_validate(too_long_owner)

    too_large_revision = _command("pause", revision=2**53)
    with pytest.raises(ValidationError):
        ModelSORuntimeCommand.model_validate(too_large_revision)


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_uuid",
    [
        "11111111111141118111111111111111",
        "{11111111-1111-4111-8111-111111111111}",
    ],
)
def test_command_rejects_noncanonical_uuid_spellings(bad_uuid: str) -> None:
    raw = _command("pause")
    raw["command_id"] = bad_uuid
    with pytest.raises(ValidationError, match="canonical RFC4122"):
        ModelSORuntimeCommand.model_validate(raw)


def _status(
    status: str,
    *,
    mode: str | None,
    revision: int = 0,
    last_command_id: UUID | None = None,
) -> ModelSORuntimeStatusPayload:
    return ModelSORuntimeStatusPayload(
        status=SORuntimeStatus(status),
        mode=None if mode is None else SORuntimeMode(mode),
        revision=revision,
        owner_id=_OWNER_ID,
        match_index=0,
        last_command_id=last_command_id,
    )


@pytest.mark.unit
def test_status_payload_round_trips_and_enforces_lifecycle_shape() -> None:
    ready = _status("ready", mode=None)
    running = _status("running", mode="one_game", revision=1, last_command_id=_COMMAND_ID)

    assert ready.status is SORuntimeStatus.READY
    assert running.mode is SORuntimeMode.ONE_GAME
    assert ModelSORuntimeStatusPayload.model_validate_json(running.model_dump_json()) == running
    with pytest.raises(ValidationError, match="extra"):
        ModelSORuntimeStatusPayload.model_validate(
            {**running.model_dump(mode="python"), "unexpected": True}
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "status, mode, last_command_id",
    [
        ("ready", "one_game", None),
        ("running", None, _COMMAND_ID),
        ("paused", None, _COMMAND_ID),
        ("ended", None, _COMMAND_ID),
        ("ready", None, _COMMAND_ID),
    ],
)
def test_status_payload_rejects_inconsistent_mode_or_command(
    status: str,
    mode: str | None,
    last_command_id: UUID | None,
) -> None:
    with pytest.raises(ValidationError):
        _status(status, mode=mode, last_command_id=last_command_id)


@pytest.mark.unit
def test_status_payload_revision_and_index_are_nonnegative_strict_ints() -> None:
    valid = _status("running", mode="continuous", revision=3, last_command_id=_COMMAND_ID)
    raw = valid.model_dump(mode="python")
    with pytest.raises(ValidationError):
        ModelSORuntimeStatusPayload.model_validate({**raw, "revision": True})
    with pytest.raises(ValidationError):
        ModelSORuntimeStatusPayload.model_validate({**raw, "match_index": -1})
    with pytest.raises(ValidationError):
        ModelSORuntimeStatusPayload.model_validate({**raw, "revision": 2**53})
    with pytest.raises(ValidationError, match="RFC4122"):
        ModelSORuntimeStatusPayload.model_validate(
            {**raw, "last_command_id": UUID("00000000-0000-0000-8000-000000000000")}
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_uuid",
    [
        "11111111111141118111111111111111",
        "{11111111-1111-4111-8111-111111111111}",
    ],
)
def test_status_rejects_noncanonical_last_command_uuid_spellings(bad_uuid: str) -> None:
    raw = _status("running", mode="one_game", last_command_id=_COMMAND_ID).model_dump(mode="python")
    raw["last_command_id"] = bad_uuid
    with pytest.raises(ValidationError, match="canonical RFC4122"):
        ModelSORuntimeStatusPayload.model_validate(raw)
