"""Closed contract tests for server-owned player selection authority."""

from __future__ import annotations

import hashlib
import inspect
import json

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOPlayerRosterProjection,
    ModelSOSeatLaunchPolicy,
)

_HASH = "a" * 64


def _human() -> ModelSOHumanPlayerOptionBinding:
    return ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser pilot",
        human_identity_id="human_identity.local_operator",
        pilot_spec_id="pilot.human.browser",
        input_source="browser_command",
    )


def _model() -> ModelSOModelPlayerOptionBinding:
    return ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id="player_option.local_qwen",
        display_name="Local Qwen",
        model_identity_id="model_identity.local_qwen",
        pilot_spec_id="pilot.llm.qwen35",
        persona_id="berserker",
        input_source="llm_completion",
    )


def _seat(side: str, option_id: str) -> ModelSOSeatLaunchPolicy:
    return ModelSOSeatLaunchPolicy.model_validate(
        {
            "side": side,
            "loadout_id": f"loadout.playable.{side}_light",
            "allowed_option_ids": (option_id,),
        }
    )


def _roster() -> ModelSOPlayerRosterBinding:
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.local_play",
        options=(_human(), _model()),
        seats=(
            _seat("red", "player_option.browser_human"),
            _seat("blue", "player_option.local_qwen"),
        ),
    )


@pytest.mark.unit
def test_roster_round_trips_as_closed_frozen_discriminated_contract() -> None:
    roster = _roster()
    assert ModelSOPlayerRosterBinding.model_validate_json(roster.model_dump_json()) == roster
    assert [option.kind for option in roster.options] == ["human", "model"]
    with pytest.raises(ValidationError):
        roster.roster_id = "roster.forged"
    with pytest.raises(ValidationError):
        ModelSOPlayerRosterBinding.model_validate(
            {**roster.model_dump(mode="python"), "unexpected": True}
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("options", "seats"),
    [
        ((_human(), _human()), None),
        (None, (_seat("red", "player_option.browser_human"),) * 2),
        (
            None,
            (
                _seat("red", "player_option.browser_human"),
                _seat("blue", "player_option.unknown"),
            ),
        ),
        (
            None,
            (
                _seat("red", "player_option.browser_human"),
                _seat("blue", "player_option.browser_human"),
            ),
        ),
    ],
)
def test_roster_rejects_duplicate_sides_ids_unknown_refs_and_unreachable_options(
    options: tuple[object, ...] | None,
    seats: tuple[ModelSOSeatLaunchPolicy, ...] | None,
) -> None:
    roster = _roster()
    with pytest.raises(ValidationError):
        ModelSOPlayerRosterBinding.model_validate(
            {
                **roster.model_dump(mode="python"),
                "options": options or roster.options,
                "seats": seats or roster.seats,
            }
        )


@pytest.mark.unit
def test_seat_policy_rejects_duplicate_allowed_options() -> None:
    with pytest.raises(ValidationError):
        ModelSOSeatLaunchPolicy(
            side="red",
            loadout_id="loadout.playable.red_light",
            allowed_option_ids=("player_option.browser_human",) * 2,
        )


@pytest.mark.unit
def test_public_projection_is_allowlisted_and_secret_free_recursively() -> None:
    projection = _roster().public_projection()
    assert [option.kind for option in projection.options] == ["human", "model"]
    serialized = projection.model_dump_json()
    for forbidden in (
        "provider_binding_id",
        "provider_id",
        "endpoint_url",
        "secret_ref",
        "headers",
        "pilot_spec_id",
        "persona_id",
        "loadout_id",
    ):
        assert forbidden not in serialized


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("display_name", "Tampered browser pilot"),
        ("human_identity_id", "human_identity.other_operator"),
    ],
)
def test_public_projection_derives_canonical_roster_hash_and_detects_tampering(
    field: str, value: str
) -> None:
    roster = _roster()
    canonical = json.dumps(
        roster.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    projection = roster.public_projection()
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert projection.roster_sha256 == expected == roster.canonical_sha256()
    assert not inspect.signature(roster.public_projection).parameters

    raw = roster.model_dump(mode="python")
    human = dict(raw["options"][0])
    human[field] = value
    raw["options"] = (human, raw["options"][1])
    tampered = ModelSOPlayerRosterBinding.model_validate(raw)
    assert tampered.public_projection().roster_sha256 != projection.roster_sha256


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (
            "options",
            None,
            "unique option_id",
        ),
        (
            "seats",
            (
                {
                    "side": "red",
                    "allowed_option_ids": ("player_option.browser_human",),
                },
            )
            * 2,
            "exactly one red and one blue",
        ),
        (
            "seats",
            (
                {
                    "side": "red",
                    "allowed_option_ids": ("player_option.browser_human",) * 2,
                },
                {
                    "side": "blue",
                    "allowed_option_ids": ("player_option.local_qwen",),
                },
            ),
            "allowed_option_ids must be unique",
        ),
        (
            "seats",
            (
                {
                    "side": "red",
                    "allowed_option_ids": ("player_option.browser_human",),
                },
                {
                    "side": "blue",
                    "allowed_option_ids": ("player_option.unknown",),
                },
            ),
            "unknown option ids",
        ),
    ],
)
def test_public_projection_independently_rejects_invalid_sides_options_and_refs(
    field: str, value: object | None, error: str
) -> None:
    projection = _roster().public_projection()
    raw = projection.model_dump(mode="python")
    if field == "options" and value is None:
        raw[field] = (raw[field][0], raw[field][0])
    else:
        raw[field] = value

    with pytest.raises(ValidationError, match=error):
        ModelSOPlayerRosterProjection.model_validate(raw)


@pytest.mark.unit
def test_human_cannot_be_encoded_as_a_model_sentinel() -> None:
    raw = _human().model_dump(mode="python")
    raw["kind"] = "model"
    with pytest.raises(ValidationError):
        ModelSOModelPlayerOptionBinding.model_validate(raw)
