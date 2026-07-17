"""Enforcement census for current canonical Slice-1 event payloads."""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from steel_onslaught.contracts.mode import ModelSOModeTransitionCompletedPayload
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.events.payloads import (
    CURRENT_CONSUMED_PAYLOAD_MODELS,
    ModelSOCurrentLiveMechSnapshot,
    ModelSOMatchStartedPayload,
    ModelSOPilotDecisionPayload,
)
from steel_onslaught.match.state import ModelSOMechRuntimeState
from tests.fixtures.event_samples import build_sample_envelopes

EXPECTED_CURRENT_CONSUMED_EVENT_TYPES = frozenset(
    {
        SOEventType.MATCH_STARTED,
        SOEventType.MATCH_TICK,
        SOEventType.MECH_SPAWNED,
        SOEventType.SENSOR_OBSERVATION,
        SOEventType.PILOT_DECISION_MADE,
        SOEventType.LLM_COMPLETION_REQUESTED,
        SOEventType.LLM_COMPLETION_RESOLVED,
        SOEventType.LLM_COMPLETION_FAILED,
        SOEventType.MOVE_INTENT,
        SOEventType.WEAPON_FIRE_INTENT,
        SOEventType.MODE_SWITCH_INTENT,
        SOEventType.VENT_INTENT,
        SOEventType.MOVEMENT_RESOLVED,
        SOEventType.BOILER_UPDATED,
        SOEventType.HEAT_REDLINE_ENTERED,
        SOEventType.HEAT_REDLINE_EXITED,
        SOEventType.BOILER_OVERLOADED,
        SOEventType.BOILER_RUPTURED,
        SOEventType.MODE_TRANSITION_STARTED,
        SOEventType.WEAPON_FIRED,
        SOEventType.HIT_RESOLVED,
        SOEventType.ARMOR_ABSORBED,
        SOEventType.DAMAGE_APPLIED,
        SOEventType.PILOT_KILLED,
        SOEventType.MECH_DESTROYED,
        SOEventType.VICTORY_DECLARED,
        SOEventType.MATCH_ENDED,
        SOEventType.MATCH_SCORED,
    }
)


def _validate(event_type: SOEventType, payload: object) -> BaseModel:
    authority = CURRENT_CONSUMED_PAYLOAD_MODELS[event_type]
    validated = authority.model_validate(payload)
    assert isinstance(validated, BaseModel)
    return validated


def _assert_deeply_frozen(value: object) -> None:
    if isinstance(value, BaseModel):
        assert value.model_config.get("extra") == "forbid"
        assert value.model_config.get("frozen") is True
        field_name = next(iter(type(value).model_fields), None)
        if field_name is not None:
            with pytest.raises(ValidationError):
                setattr(value, field_name, getattr(value, field_name))
        for name in type(value).model_fields:
            _assert_deeply_frozen(getattr(value, name))
        return
    if isinstance(value, Mapping):
        with pytest.raises(TypeError):
            value["__mutation_probe__"] = None  # type: ignore[index]
        for nested in value.values():
            _assert_deeply_frozen(nested)
        return
    if isinstance(value, tuple):
        for nested in value:
            _assert_deeply_frozen(nested)
        return
    assert not isinstance(value, list | dict), f"mutable nested payload value: {value!r}"


@pytest.mark.unit
def test_current_consumed_payload_registry_has_exact_independent_census() -> None:
    assert len(EXPECTED_CURRENT_CONSUMED_EVENT_TYPES) == 28
    assert set(CURRENT_CONSUMED_PAYLOAD_MODELS) == EXPECTED_CURRENT_CONSUMED_EVENT_TYPES
    assert set(SOEventType) - EXPECTED_CURRENT_CONSUMED_EVENT_TYPES == {
        SOEventType.MODE_TRANSITION_COMPLETED,
        SOEventType.PILOT_INJURED,
    }

    # MODE_TRANSITION_COMPLETED is a current emitted, closed payload, but no
    # current consumer reads it. PILOT_INJURED is future-only and remains the
    # sole open payload, so neither belongs in the consumed-authority registry.
    assert ModelSOModeTransitionCompletedPayload.model_config["extra"] == "forbid"
    assert ModelSOModeTransitionCompletedPayload.model_config["frozen"] is True
    assert SOEventType.MODE_TRANSITION_COMPLETED not in CURRENT_CONSUMED_PAYLOAD_MODELS
    assert SOEventType.PILOT_INJURED not in CURRENT_CONSUMED_PAYLOAD_MODELS


@pytest.mark.unit
@pytest.mark.parametrize("event_type", tuple(EXPECTED_CURRENT_CONSUMED_EVENT_TYPES))
def test_current_payload_authorities_accept_frozen_in_memory_bus_payloads(
    event_type: SOEventType,
) -> None:
    sample = build_sample_envelopes()[event_type]

    validated = _validate(event_type, sample.payload)

    assert isinstance(validated, BaseModel)


@pytest.mark.unit
@pytest.mark.parametrize("event_type", tuple(CURRENT_CONSUMED_PAYLOAD_MODELS))
def test_current_payload_authorities_are_closed_and_deeply_frozen(
    event_type: SOEventType,
) -> None:
    sample = build_sample_envelopes()[event_type]
    raw = sample.model_dump(mode="json")["payload"]
    validated = _validate(event_type, raw)
    _assert_deeply_frozen(validated)

    with pytest.raises(ValidationError):
        _validate(event_type, {**raw, "unexpected_payload_field": True})


@pytest.mark.unit
@pytest.mark.parametrize("event_type", tuple(CURRENT_CONSUMED_PAYLOAD_MODELS))
def test_current_payload_validation_preserves_canonical_json_keys(
    event_type: SOEventType,
) -> None:
    sample = build_sample_envelopes()[event_type]
    raw = sample.model_dump(mode="json")["payload"]
    expected = dict(raw)
    if event_type is SOEventType.WEAPON_FIRE_INTENT:
        expected.setdefault("target_mech_id", None)

    validated = _validate(event_type, raw)

    assert validated.model_dump(mode="json") == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_type", "mutate"),
    [
        (
            SOEventType.MATCH_STARTED,
            lambda payload: payload["mechs"][0].__setitem__("unexpected", True),
        ),
        (
            SOEventType.MODE_TRANSITION_STARTED,
            lambda payload: payload["costs"].__setitem__("unexpected", True),
        ),
        (
            SOEventType.HIT_RESOLVED,
            lambda payload: payload["result"].__setitem__("unexpected", True),
        ),
        (
            SOEventType.PILOT_DECISION_MADE,
            lambda payload: payload["considered_actions"][0].__setitem__("unexpected", True),
        ),
        (
            SOEventType.MATCH_SCORED,
            lambda payload: next(iter(payload["scores"].values())).__setitem__("unexpected", True),
        ),
    ],
)
def test_nested_payload_models_reject_extra_fields(
    event_type: SOEventType,
    mutate: Any,
) -> None:
    sample = build_sample_envelopes()[event_type]
    raw = sample.model_dump(mode="json")["payload"]
    mutate(raw)
    with pytest.raises(ValidationError):
        _validate(event_type, raw)


@pytest.mark.unit
def test_runtime_default_cooldowns_remain_frozen_but_live_snapshot_requires_field() -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    raw = sample.model_dump(mode="json")["payload"]
    del raw["mechs"][0]["weapon_cooldowns"]

    with pytest.raises(ValidationError, match="weapon_cooldowns"):
        _validate(SOEventType.MATCH_STARTED, raw)

    runtime_data = raw["mechs"][0]
    runtime_data["sensor_ids"] = tuple(runtime_data["sensor_ids"])
    runtime_data["gizmo_ids"] = tuple(runtime_data["gizmo_ids"])
    mech = ModelSOMechRuntimeState.model_validate(runtime_data)
    with pytest.raises(TypeError):
        mech.weapon_cooldowns["weapon.forged"] = 1  # type: ignore[index]


@pytest.mark.unit
def test_current_live_python_mech_fields_exactly_match_typescript() -> None:
    typescript = (Path(__file__).resolve().parents[2] / "frontend/src/types.ts").read_text(
        encoding="utf-8"
    )
    match = re.search(r"const MECH_FIELDS = \[(.*?)\] as const;", typescript, re.DOTALL)
    assert match is not None
    typescript_fields = frozenset(re.findall(r'"([a-z_]+)"', match.group(1)))

    assert frozenset(ModelSOCurrentLiveMechSnapshot.model_fields) == typescript_fields


@pytest.mark.unit
@pytest.mark.parametrize(
    "field_name",
    sorted(ModelSOCurrentLiveMechSnapshot.model_fields),
)
def test_current_match_started_rejects_each_missing_mech_field(field_name: str) -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    raw = sample.model_dump(mode="json")["payload"]
    del raw["mechs"][0][field_name]

    with pytest.raises(ValidationError, match=field_name):
        _validate(SOEventType.MATCH_STARTED, raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "field_name",
    [
        "schema_version",
        "kind",
        "arena_id",
        "size",
        "spawn_a",
        "spawn_b",
        "obstacles",
    ],
)
def test_current_match_started_rejects_each_missing_arena_field(field_name: str) -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    raw = sample.model_dump(mode="json")["payload"]
    del raw["arena"][field_name]

    with pytest.raises(ValidationError, match=field_name):
        _validate(SOEventType.MATCH_STARTED, raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("roster-count", "exactly two mechs"),
        ("out-of-bounds", "outside arena"),
        ("obstacle", "occupies an arena obstacle"),
        ("swapped-spawns", "canonical roster order"),
    ],
)
def test_current_match_started_cross_validates_roster_positions_against_arena(
    case: str,
    error: str,
) -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    raw = sample.model_dump(mode="json")["payload"]
    if case == "roster-count":
        raw["mechs"] = raw["mechs"][:1]
    elif case == "out-of-bounds":
        raw["mechs"][0]["position"] = {"x": raw["arena"]["size"], "y": 5}
    elif case == "obstacle":
        raw["arena"]["obstacles"] = [{"x": 6, "y": 5}]
        raw["mechs"][0]["position"] = {"x": 6, "y": 5}
    elif case == "swapped-spawns":
        first = raw["mechs"][0]["position"]
        second = raw["mechs"][1]["position"]
        raw["mechs"][0]["position"] = second
        raw["mechs"][1]["position"] = first
    else:  # pragma: no cover - closed parametrization
        raise AssertionError(case)

    with pytest.raises(ValidationError, match=error):
        _validate(SOEventType.MATCH_STARTED, raw)


@pytest.mark.unit
def test_internal_runtime_defaults_do_not_become_current_live_wire_defaults() -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    legacy_state_data = sample.model_dump(mode="python")["payload"]["mechs"][0]
    del legacy_state_data["side"]
    legacy_state_data["sensor_ids"] = tuple(legacy_state_data["sensor_ids"])
    legacy_state_data["gizmo_ids"] = tuple(legacy_state_data["gizmo_ids"])
    legacy_state = ModelSOMechRuntimeState.model_validate(legacy_state_data)
    assert legacy_state.side == "neutral"
    assert "side" not in legacy_state.model_fields_set
    with pytest.raises(ValidationError, match="missing required current-live fields"):
        ModelSOMatchStartedPayload.model_validate(
            {
                "seed": 12345,
                "max_ticks": 200,
                "mechs": (legacy_state,),
                "arena": sample.model_dump(mode="python")["payload"]["arena"],
            }
        )


@pytest.mark.unit
def test_current_match_started_preserves_explicit_red_blue_sides() -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    validated = _validate(SOEventType.MATCH_STARTED, sample.model_dump(mode="json")["payload"])

    assert isinstance(validated, ModelSOMatchStartedPayload)
    assert [mech.side for mech in validated.mechs] == ["red", "blue"]
    expected_fields = frozenset(ModelSOCurrentLiveMechSnapshot.model_fields)
    assert all(mech.model_fields_set == expected_fields for mech in validated.mechs)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_type", "mutate"),
    [
        (SOEventType.MECH_SPAWNED, lambda payload: payload.__setitem__("facing", True)),
        (
            SOEventType.MOVEMENT_RESOLVED,
            lambda payload: payload.__setitem__("ticks_consumed", "1"),
        ),
        (
            SOEventType.MOVEMENT_RESOLVED,
            lambda payload: payload.__setitem__("pressure_consumed", True),
        ),
        (
            SOEventType.SENSOR_OBSERVATION,
            lambda payload: payload.__setitem__("confidence", "0.5"),
        ),
        (
            SOEventType.WEAPON_FIRED,
            lambda payload: payload.__setitem__("hit_probability", "0.5"),
        ),
        (
            SOEventType.MATCH_SCORED,
            lambda payload: next(iter(payload["scores"].values())).__setitem__("damage_dealt", "0"),
        ),
        (
            SOEventType.MATCH_SCORED,
            lambda payload: payload.__setitem__("is_draw", 0),
        ),
    ],
)
def test_numeric_payload_fields_reject_string_and_boolean_coercion(
    event_type: SOEventType,
    mutate: Any,
) -> None:
    sample = build_sample_envelopes()[event_type]
    raw = sample.model_dump(mode="json")["payload"]
    mutate(raw)

    with pytest.raises(ValidationError):
        _validate(event_type, raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.__setitem__("loser_player_id", payload["winner_player_id"]),
        lambda payload: payload["scores"].pop(payload["loser_player_id"]),
        lambda payload: payload.__setitem__("winner_score", payload["winner_score"] + 1),
        lambda payload: payload.__setitem__("is_draw", True),
        lambda payload: payload.__setitem__("winner", None),
        lambda payload: payload["winner"].__setitem__("player_id", payload["loser_player_id"]),
        lambda payload: payload["scores"][payload["winner_player_id"]].__setitem__("victory", 0),
    ],
)
def test_match_scored_rejects_contradictory_truth(mutate: Any) -> None:
    sample = build_sample_envelopes()[SOEventType.MATCH_SCORED]
    raw = sample.model_dump(mode="json")["payload"]
    mutate(raw)

    with pytest.raises(ValidationError):
        _validate(SOEventType.MATCH_SCORED, raw)


@pytest.mark.unit
def test_pilot_decision_event_validation_preserves_exact_emitted_keys() -> None:
    sample = build_sample_envelopes()[SOEventType.PILOT_DECISION_MADE]
    raw = sample.model_dump(mode="json")["payload"]

    validated = ModelSOPilotDecisionPayload.model_validate(raw)

    assert validated.model_dump(mode="json") == raw


@pytest.mark.unit
@pytest.mark.parametrize("unexpected", ["schema_version", "kind"])
def test_pilot_decision_event_rejects_domain_only_keys(unexpected: str) -> None:
    sample = build_sample_envelopes()[SOEventType.PILOT_DECISION_MADE]
    raw = sample.model_dump(mode="json")["payload"]
    raw[unexpected] = "forged"

    with pytest.raises(ValidationError):
        ModelSOPilotDecisionPayload.model_validate(raw)


@pytest.mark.unit
def test_pilot_decision_event_requires_action_params() -> None:
    sample = build_sample_envelopes()[SOEventType.PILOT_DECISION_MADE]
    raw = sample.model_dump(mode="json")["payload"]
    del raw["action_params"]

    with pytest.raises(ValidationError):
        ModelSOPilotDecisionPayload.model_validate(raw)


@pytest.mark.unit
def test_payload_consumers_do_not_read_unvalidated_payload_dicts() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "steel_onslaught"
    files = [
        *sorted((root / "reducers").glob("*.py")),
        root / "match" / "fold.py",
        root / "match" / "runner.py",
        root / "match" / "composition.py",
        root / "projections" / "cli" / "renderer.py",
    ]
    offenders: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text())
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr != "payload":
                continue
            parent = parents[node]
            if not isinstance(parent, ast.Call) or node not in parent.args:
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
                continue
            function = parent.func
            if not isinstance(function, ast.Attribute) or function.attr not in {
                "model_validate",
                "validate_python",
            }:
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")

    assert offenders == []
