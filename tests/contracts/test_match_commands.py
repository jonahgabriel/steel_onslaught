"""Strict wire-shape tests for future match and human-action commands."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.commands import (
    COMMAND_HASH_AUTHORITY_V1,
    COMMAND_HASH_V1_HELD_CAPABILITIES,
    ModelSODisengagePlayerAction,
    ModelSOFireWeaponPlayerAction,
    ModelSOHumanTurnPrompt,
    ModelSOMovePlayerAction,
    ModelSOPlayerActionCommand,
    ModelSORemainPlayerAction,
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
    ModelSOSwitchModePlayerAction,
    ModelSOVentPlayerAction,
    canonical_command_sha256,
)
from steel_onslaught.contracts.mode import ModeId, ModelSOModeSwitchIntentPayload
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMoveIntentPayload,
    ModelSOWeaponFireIntentPayload,
)
from steel_onslaught.match.composition import SystemIdentityProvider
from steel_onslaught.pilots.schemas import SOPilotAction

_COMMAND_ID = UUID("11111111-1111-4111-8111-111111111111")
_HASH = "b" * 64
_MATCH_ID = "match.01J00000000000000000000000"


def _selection(side: str, option: str) -> ModelSOStartMatchSeatSelection:
    return ModelSOStartMatchSeatSelection.model_validate({"side": side, "option_id": option})


def _start() -> ModelSOStartMatchCommand:
    return ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=_COMMAND_ID,
        expected_overlay_sha256=_HASH,
        expected_roster_sha256=_HASH,
        selections=(
            _selection("red", "player_option.browser_human"),
            _selection("blue", "player_option.local_qwen"),
        ),
    )


@pytest.mark.unit
def test_start_command_round_trips_without_client_owned_match_authority() -> None:
    command = _start()
    assert ModelSOStartMatchCommand.model_validate_json(command.model_dump_json()) == command
    serialized = command.model_dump_json()
    for forbidden in (
        "match_id",
        "seed",
        "loadout_id",
        "provider_id",
        "endpoint_url",
        "persona_id",
        "authorization",
    ):
        assert forbidden not in serialized


@pytest.mark.unit
def test_start_command_sha_is_canonical_deterministic_and_tamper_evident() -> None:
    command = _start()
    canonical = json.dumps(
        command.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert canonical_command_sha256(command) == expected
    assert (
        canonical_command_sha256(
            ModelSOStartMatchCommand.model_validate_json(command.model_dump_json())
        )
        == expected
    )

    changed = command.model_copy(
        update={"command_id": UUID("22222222-2222-4222-8222-222222222222")}
    )
    assert canonical_command_sha256(changed) != expected


@pytest.mark.unit
def test_command_hash_v1_is_explicitly_process_lifetime_only() -> None:
    assert COMMAND_HASH_AUTHORITY_V1 == "process_lifetime_canonical_hash_only"
    assert COMMAND_HASH_V1_HELD_CAPABILITIES == (
        "live_auth_or_ingress",
        "durable_idempotency_receipts_or_journal",
        "restart_or_crash_recovery",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "selections",
    [
        (
            _selection("red", "player_option.browser_human"),
            _selection("red", "player_option.local_qwen"),
        ),
    ],
)
def test_start_command_requires_exact_red_and_blue_selections(
    selections: tuple[ModelSOStartMatchSeatSelection, ModelSOStartMatchSeatSelection],
) -> None:
    with pytest.raises(ValidationError):
        ModelSOStartMatchCommand(
            schema_version="1",
            kind="steel_onslaught.start_match",
            command_id=_COMMAND_ID,
            expected_overlay_sha256=_HASH,
            expected_roster_sha256=_HASH,
            selections=selections,
        )


@pytest.mark.unit
def test_start_command_allows_mirrored_option_selection() -> None:
    mirrored = ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=_COMMAND_ID,
        expected_overlay_sha256=_HASH,
        expected_roster_sha256=_HASH,
        selections=(
            _selection("red", "player_option.browser_human"),
            _selection("blue", "player_option.browser_human"),
        ),
    )

    assert mirrored.selections[0].option_id == mirrored.selections[1].option_id


@pytest.mark.unit
def test_start_command_rejects_unknown_fields_and_noncanonical_hashes() -> None:
    raw = _start().model_dump(mode="python")
    with pytest.raises(ValidationError):
        ModelSOStartMatchCommand.model_validate({**raw, "seed": 42})
    with pytest.raises(ValidationError):
        ModelSOStartMatchCommand.model_validate({**raw, "expected_roster_sha256": "B" * 64})


def _prompt(actions: tuple[object, ...], *, match_id: str = _MATCH_ID) -> ModelSOHumanTurnPrompt:
    return ModelSOHumanTurnPrompt.model_validate(
        {
            "schema_version": "1",
            "kind": "steel_onslaught.human_turn",
            "match_id": match_id,
            "turn_id": "turn.local.001",
            "side": "red",
            "expected_tick": 3,
            "observation_sha256": _HASH,
            "available_actions": actions,
        }
    )


@pytest.mark.unit
def test_system_identity_provider_match_id_validates_through_human_turn_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FixedUlid:
        str = _MATCH_ID.removeprefix("match.")

    monkeypatch.setattr("steel_onslaught.match.composition.ulid.new", _FixedUlid)

    generated = SystemIdentityProvider().new_match_id()
    prompt = _prompt((ModelSORemainPlayerAction(kind="remain"),), match_id=generated)

    assert generated == _MATCH_ID
    assert prompt.match_id == generated


@pytest.mark.unit
def test_prompt_and_action_command_carry_concrete_turn_bound_choices() -> None:
    actions = (
        ModelSORemainPlayerAction(kind="remain"),
        ModelSOMovePlayerAction(kind="move", direction="toward_enemy", speed="full"),
        ModelSOFireWeaponPlayerAction(kind="fire_weapon", weapon_id="weapon.light.machine_gun"),
    )
    prompt = _prompt(actions)
    command = ModelSOPlayerActionCommand(
        schema_version="1",
        kind="steel_onslaught.player_action",
        command_id=_COMMAND_ID,
        match_id=prompt.match_id,
        turn_id=prompt.turn_id,
        expected_tick=prompt.expected_tick,
        observation_sha256=prompt.observation_sha256,
        action=actions[2],
    )
    assert ModelSOHumanTurnPrompt.model_validate_json(prompt.model_dump_json()) == prompt
    assert ModelSOPlayerActionCommand.model_validate_json(command.model_dump_json()) == command
    assert prompt.match_id == command.match_id == _MATCH_ID
    with pytest.raises(ValidationError):
        ModelSOPlayerActionCommand.model_validate(
            {**command.model_dump(mode="python"), "expected_tick": -1}
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "match_id",
    [
        "match.01j00000000000000000000000",
        "match.01I00000000000000000000000",
        "match.81J00000000000000000000000",
        "match.01J0000000000000000000000",
        "match.local.001",
    ],
)
def test_human_turn_prompt_rejects_noncanonical_runtime_match_ids(match_id: str) -> None:
    raw = _prompt((ModelSORemainPlayerAction(kind="remain"),)).model_dump(mode="python")
    with pytest.raises(ValidationError, match="match_id"):
        ModelSOHumanTurnPrompt.model_validate({**raw, "match_id": match_id})


@pytest.mark.unit
def test_prompt_rejects_empty_duplicate_or_malformed_action_choices() -> None:
    remain = ModelSORemainPlayerAction(kind="remain")
    with pytest.raises(ValidationError):
        _prompt(())
    with pytest.raises(ValidationError):
        _prompt((remain, remain))
    with pytest.raises(ValidationError):
        _prompt(({"kind": "fire_weapon", "weapon_id": "module.weapon.x", "extra": 1},))


@pytest.mark.unit
def test_human_action_grammar_exactly_maps_to_current_executable_intent_payloads() -> None:
    move = ModelSOMovePlayerAction(kind="move", direction="toward_enemy", speed="full")
    disengage = ModelSODisengagePlayerAction(kind="disengage", direction="defensive")
    fire = ModelSOFireWeaponPlayerAction(
        kind="fire_weapon",
        weapon_id="weapon.light.machine_gun",
        target_mech_id="mech.blue.01",
    )
    switch = ModelSOSwitchModePlayerAction(kind="switch_mode", target_mode=ModeId.ASSAULT)
    vent = ModelSOVentPlayerAction(kind="vent")
    remain = ModelSORemainPlayerAction(kind="remain")

    ModelSOMoveIntentPayload.model_validate(
        move.model_dump(mode="python", exclude={"kind"}, exclude_none=True)
    )
    ModelSOMoveIntentPayload.model_validate(
        disengage.model_dump(mode="python", exclude={"kind"}, exclude_none=True)
    )
    ModelSOWeaponFireIntentPayload.model_validate(
        fire.model_dump(mode="python", exclude={"kind"}, exclude_none=True)
    )
    ModelSOModeSwitchIntentPayload.model_validate(
        switch.model_dump(mode="python", exclude={"kind"}, exclude_none=True)
    )
    ModelSOEmptyPayload.model_validate(vent.model_dump(mode="python", exclude={"kind"}))
    assert {action.kind for action in (remain, move, fire, switch, vent, disengage)} == {
        action.value
        for action in (
            SOPilotAction.REMAIN,
            SOPilotAction.MOVE,
            SOPilotAction.FIRE_WEAPON,
            SOPilotAction.SWITCH_MODE,
            SOPilotAction.VENT,
            SOPilotAction.DISENGAGE,
        )
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "action",
    [
        {"kind": "activate_module", "module_id": "module.test"},
        {"kind": "emergency_shutdown"},
        {"kind": "move", "direction": "away_from_enemy", "speed": "full"},
        {"kind": "move", "direction": "defensive", "speed": "half"},
        {"kind": "fire_weapon", "weapon_id": "module.weapon.machine_gun"},
    ],
)
def test_human_action_grammar_rejects_non_emitting_or_speculative_shapes(
    action: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        _prompt((action,))


@pytest.mark.unit
@pytest.mark.parametrize(
    "target_mech_id",
    [
        "mech.Blue.01",
        "mech.blue.1",
        "mech.blue.02",
        "mech.blue.extra.01",
        "player.blue",
    ],
)
def test_fire_action_rejects_malformed_current_runtime_mech_ids(target_mech_id: str) -> None:
    with pytest.raises(ValidationError, match="target_mech_id"):
        ModelSOFireWeaponPlayerAction(
            kind="fire_weapon",
            weapon_id="weapon.light.machine_gun",
            target_mech_id=target_mech_id,
        )
