"""Tests for the LLM pilot (stub-driven, no network)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from steel_onslaught.contracts.application import ModelSOLlmImageAttachmentBinding
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams, SODisplaySalience
from steel_onslaught.llm.effect import LlmSemanticError
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.pilot import _IMAGE_ATTACHMENT_NOTE, LLMPilot
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmSemanticExhaustedError,
    LlmUsage,
    ModelSOLlmCompletionRequest,
)
from steel_onslaught.llm.stub import StubLlmClient
from steel_onslaught.pilots.schemas import (
    ModelSOObjectiveView,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    ModelSOVictoryPointsView,
    SOCompassDirection,
    SOPilotAction,
    SOPilotReasonCode,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _persona(persona_id: str) -> Persona:
    return Persona(
        persona_id=persona_id,
        display_name=persona_id.title(),
        system_prompt="Return a valid pilot action as JSON.",
        temperature=0.7,
    )


def _boiler(*, pressure: int = 40, heat: int = 10) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id="m",
        mech_id="mech.a",
        tick=1,
        pressure_current=pressure,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=heat,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=heat >= 80,
        status_rupture_warning=heat >= 90,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _weapon(
    *,
    weapon_id: str = "weapon.light.machine_gun",
    cooldown: int = 0,
    weapon_range: int = 12,
    pressure_cost: int = 4,
) -> ModelSOPilotWeaponView:
    return ModelSOPilotWeaponView(
        weapon_id=weapon_id,
        damage=8,
        range=weapon_range,
        pressure_cost=pressure_cost,
        heat_generated=3,
        cooldown_remaining_ticks=cooldown,
    )


def _observation(
    *,
    weapons: list[ModelSOPilotWeaponView] | None = None,
    enemy_confidence: float | None = 0.9,
    enemy_distance: float = 8.0,
    enemy_heat: float | None = None,
    pressure: int = 40,
    heat: int = 10,
    hp_percent: float = 80.0,
    has_line_of_sight_to_enemy: bool = False,
    blocked_directions: tuple[SOCompassDirection, ...] = (),
    objectives: tuple[ModelSOObjectiveView, ...] = (),
    victory_points: ModelSOVictoryPointsView | None = None,
) -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id="m",
        mech_id="mech.a",
        player_id="player.a",
        tick=1,
        match_elapsed_ticks=1,
        boiler=_boiler(pressure=pressure, heat=heat),
        weapons=weapons if weapons is not None else [_weapon()],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=10, y=10),
        hp_percent=hp_percent,
        under_sensor_lock=False,
        has_line_of_sight_to_enemy=has_line_of_sight_to_enemy,
        blocked_directions=blocked_directions,
        objectives=objectives,
        victory_points=victory_points,
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id="mech.b",
                tick=1,
                distance_estimate=enemy_distance,
                confidence=enemy_confidence,
                heat_estimate=enemy_heat,
            )
        ]
        if enemy_confidence is not None
        else [],
    )


def _decide_sequence(
    persona_id: str, observations: list[dict[str, Any]]
) -> list[ModelSOPilotDecision]:
    """Run one persistent persona over sequential observations."""
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona(persona_id))
    return [pilot.decide(_observation(**kwargs)) for kwargs in observations]


# ---------------------------------------------------------------------------
# Stub-driven decisions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_berserker_fires_when_weapon_ready() -> None:
    """The berserker stub fires when a weapon is off cooldown."""
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))
    decision = pilot.decide(_observation())
    assert decision.action is SOPilotAction.FIRE_WEAPON
    assert decision.action_params == {"weapon_id": "weapon.light.machine_gun"}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION
    assert decision.rationale is not None


@pytest.mark.unit
def test_sniper_fires_on_high_confidence() -> None:
    """The sniper stub fires when sensor confidence is high."""
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("sniper"))
    decision = pilot.decide(_observation(enemy_confidence=0.9, has_line_of_sight_to_enemy=True))
    assert decision.action is SOPilotAction.FIRE_WEAPON
    assert decision.action_params == {"weapon_id": "weapon.light.machine_gun"}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_rationale_carried_in_decision() -> None:
    """The LLM's rationale text flows into the decision (→ ledger evidence)."""
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))
    decision = pilot.decide(_observation())
    assert decision.rationale is not None
    assert len(decision.rationale) > 0


class _RecordingClient:
    def __init__(self) -> None:
        self.request: ModelSOLlmCompletionRequest | None = None
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.request = request
        self.requests.append(request)
        return LlmResponse(
            text=json.dumps(
                {
                    "action": "remain",
                    "action_params": {},
                    "confidence": 0.9,
                    "rationale": "terrain blocks the route",
                }
            ),
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="recording",
            finish_reason="stop",
        )


@pytest.mark.unit
def test_terrain_awareness_reaches_llm_prompt_serialization() -> None:
    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("terrain-aware"))

    decision = pilot.decide(
        _observation(
            has_line_of_sight_to_enemy=False,
            blocked_directions=(SOCompassDirection.N, SOCompassDirection.E),
        )
    )

    assert decision.action is SOPilotAction.REMAIN
    assert client.request is not None
    assert "line_of_sight_to_enemy: False" in client.request.user_prompt
    assert "blocked_directions: [n, e]" in client.request.user_prompt


@pytest.mark.unit
def test_persona_role_and_tactical_objective_reach_llm_prompt() -> None:
    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("sniper"))

    pilot.decide(_observation())

    assert client.request is not None
    assert "role: sniper" in client.request.user_prompt
    assert "tactical_objective: hold maximum standoff" in client.request.user_prompt


@pytest.mark.unit
def test_prompt_lists_only_currently_available_actions() -> None:
    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("availability-aware"))
    pilot.decide(_observation(weapons=[_weapon(cooldown=2)]))

    assert client.request is not None
    available_line = next(
        line
        for line in client.request.user_prompt.splitlines()
        if line.startswith("available_actions:")
    )
    assert available_line == "available_actions: [move, remain, switch_mode, vent]"
    assert "choose only an available action" in client.request.user_prompt
    assert "ready_weapon_ids: []" in client.request.user_prompt
    assert "fire_weapon also requires an enemy sensor reading" in client.request.user_prompt


@pytest.mark.unit
def test_prompt_carries_stateful_own_hp_trade_memory() -> None:
    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("sniper"))

    pilot.decide(_observation(hp_percent=90.0))
    pilot.decide(_observation(hp_percent=80.0))
    pilot.decide(_observation(hp_percent=85.0))

    assert len(client.requests) == 3
    first, second, recovered = (request.user_prompt for request in client.requests)
    assert "previous_hp_percent: unknown" in first
    assert "hp_delta_since_last_decision: 0.0" in first
    assert "consecutive_hp_loss_ticks: 0" in first
    assert "previous_hp_percent: 90.0%" in second
    assert "hp_delta_since_last_decision: -10.0" in second
    assert "consecutive_hp_loss_ticks: 1" in second
    assert "previous_hp_percent: 80.0%" in recovered
    assert "hp_delta_since_last_decision: 5.0" in recovered
    assert "consecutive_hp_loss_ticks: 0" in recovered


def _capture_current_request(
    *, persona_id: str = "berserker", observation: ModelSOPilotObservation | None = None
) -> ModelSOLlmCompletionRequest:
    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona(persona_id))
    decision = pilot.decide(observation or _observation())
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION
    assert client.request is not None
    return client.request


@pytest.mark.unit
@pytest.mark.parametrize("persona_id", ["berserker", "sniper", "opportunist", "tuner"])
def test_stub_is_deterministic_for_same_strict_request(persona_id: str) -> None:
    request = _capture_current_request(persona_id=persona_id)
    client = StubLlmClient(model="stub-row03")

    first = client.complete(request)
    second = client.complete(request)

    assert first == second
    assert first.text == second.text
    assert json.loads(first.text) == json.loads(second.text)
    assert first.model == "stub-row03"
    assert first.finish_reason == "stop"
    assert first.usage.cost_usd == 0.0


def _only_line_index(lines: list[str], prefix: str) -> int:
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    assert len(matches) == 1, f"current serializer must emit one {prefix!r} line"
    return matches[0]


def _malform_captured_prompt(user_prompt: str, case: str) -> str:
    """Mutate one current serializer field without hand-building a prompt."""
    lines = user_prompt.splitlines()
    prefix_by_section = {
        "header": "--- YOUR MECH ",
        "hp": "hp: ",
        "position": "position: ",
        "terrain": "terrain: ",
        "boiler": "boiler: ",
        "weapons": "weapons:",
        "enemy_header": "--- ENEMY (",
        "no_enemy": "--- ENEMY:",
    }

    operation, section = case.split("-", 1)
    if operation in {"missing", "duplicate"} and section in prefix_by_section:
        index = _only_line_index(lines, prefix_by_section[section])
        if operation == "missing":
            lines.pop(index)
        else:
            lines.insert(index + 1, lines[index])
        return "\n".join(lines)

    if case == "invalid-hp-shape":
        index = _only_line_index(lines, "hp: ")
        lines[index] = lines[index].replace("mode_lock_expired: True", "mode_lock_expired: yes")
    elif case == "invalid-position-shape":
        index = _only_line_index(lines, "position: ")
        lines[index] = lines[index].replace("under_sensor_lock: False", "under_sensor_lock: no")
    elif case == "invalid-terrain-los":
        index = _only_line_index(lines, "terrain: ")
        lines[index] = lines[index].replace(
            "line_of_sight_to_enemy: False", "line_of_sight_to_enemy: unknown"
        )
    elif case == "invalid-terrain-direction":
        index = _only_line_index(lines, "terrain: ")
        before, _separator, _blocked = lines[index].partition("blocked_directions:")
        lines[index] = f"{before}blocked_directions: [up]"
    elif case == "invalid-boiler-shape":
        index = _only_line_index(lines, "boiler: ")
        lines[index] = lines[index].replace("redline: False", "redline: no")
    elif case == "invalid-weapon-id":
        index = _only_line_index(lines, "  - ")
        lines[index] = lines[index].replace(": damage=", " invalid: damage=", 1)
    elif case == "duplicate-weapon-id":
        index = _only_line_index(lines, "  - ")
        lines.insert(index + 1, lines[index])
    elif case == "missing-enemy-reading":
        lines.pop(_only_line_index(lines, "  tick "))
    elif case in {
        "invalid-enemy-distance",
        "invalid-enemy-confidence",
        "invalid-enemy-heat",
    }:
        index = _only_line_index(lines, "  tick ")
        field = case.removeprefix("invalid-enemy-")
        prompt_field = {
            "distance": "distance_estimate",
            "confidence": "confidence",
            "heat": "heat_estimate",
        }[field]
        before, value_and_tail = lines[index].split(f"{prompt_field}=", 1)
        _value, separator, tail = value_and_tail.partition(" ")
        lines[index] = f"{before}{prompt_field}=invalid{separator}{tail}"
    elif case == "invalid-no-enemy-marker":
        index = _only_line_index(lines, "--- ENEMY:")
        lines[index] = "--- ENEMY: unknown sensor state ---"
    else:
        raise AssertionError(f"unknown parser-negative case {case!r}")
    return "\n".join(lines)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case", "observation_kind", "error"),
    [
        pytest.param("missing-header", "detected", "valid mech header", id="missing-header"),
        pytest.param("duplicate-header", "detected", "valid mech header", id="duplicate-header"),
        pytest.param("missing-hp", "detected", "valid hp/mode line", id="missing-hp"),
        pytest.param("invalid-hp-shape", "detected", "valid hp/mode line", id="hp-shape"),
        pytest.param("duplicate-hp", "detected", "valid hp/mode line", id="duplicate-hp"),
        pytest.param("missing-position", "detected", "valid position line", id="missing-position"),
        pytest.param(
            "invalid-position-shape", "detected", "valid position line", id="position-shape"
        ),
        pytest.param(
            "duplicate-position", "detected", "valid position line", id="duplicate-position"
        ),
        pytest.param("missing-terrain", "detected", "valid terrain line", id="missing-terrain"),
        pytest.param("invalid-terrain-los", "detected", "valid terrain line", id="terrain-los"),
        pytest.param(
            "invalid-terrain-direction",
            "detected",
            "invalid blocked direction",
            id="terrain-direction",
        ),
        pytest.param("duplicate-terrain", "detected", "valid terrain line", id="duplicate-terrain"),
        pytest.param("missing-boiler", "detected", "valid boiler line", id="missing-boiler"),
        pytest.param("invalid-boiler-shape", "detected", "valid boiler line", id="boiler-shape"),
        pytest.param("duplicate-boiler", "detected", "valid boiler line", id="duplicate-boiler"),
        pytest.param(
            "missing-weapons", "detected", "one weapons section", id="missing-weapons-section"
        ),
        pytest.param(
            "duplicate-weapons",
            "detected",
            "one weapons section",
            id="duplicate-weapons-section",
        ),
        pytest.param("invalid-weapon-id", "detected", "malformed weapon line", id="weapon-id"),
        pytest.param(
            "duplicate-weapon-id", "detected", "duplicate weapon ids", id="duplicate-weapon-id"
        ),
        pytest.param(
            "missing-enemy_header", "detected", "valid enemy section", id="missing-enemy-header"
        ),
        pytest.param(
            "duplicate-enemy_header",
            "detected",
            "valid enemy section",
            id="duplicate-enemy-header",
        ),
        pytest.param(
            "missing-enemy-reading",
            "detected",
            "enemy section requires a sensor reading",
            id="missing-enemy-reading",
        ),
        pytest.param(
            "invalid-enemy-distance",
            "detected",
            "malformed enemy reading",
            id="enemy-distance",
        ),
        pytest.param(
            "invalid-enemy-confidence",
            "detected",
            "malformed enemy reading",
            id="enemy-confidence",
        ),
        pytest.param("invalid-enemy-heat", "heated", "malformed enemy reading", id="enemy-heat"),
        pytest.param(
            "invalid-no-enemy-marker", "no-enemy", "valid enemy section", id="no-enemy-marker"
        ),
        pytest.param(
            "duplicate-no_enemy",
            "no-enemy",
            "valid enemy section",
            id="duplicate-no-enemy-marker",
        ),
    ],
)
def test_stub_rejects_malformed_current_prompt(
    case: str, observation_kind: str, error: str
) -> None:
    observation = {
        "detected": _observation(),
        "heated": _observation(enemy_heat=50.0),
        "no-enemy": _observation(enemy_confidence=None),
    }[observation_kind]
    request = _capture_current_request(observation=observation)
    malformed = request.model_copy(
        update={"user_prompt": _malform_captured_prompt(request.user_prompt, case)}
    )

    with pytest.raises(ValueError, match=error):
        StubLlmClient(model="stub").complete(malformed)


@pytest.mark.unit
def test_stub_requires_combat_memory_context() -> None:
    request = _capture_current_request()
    malformed = request.model_copy(
        update={
            "user_prompt": request.user_prompt.replace(
                "--- COMBAT MEMORY (your own remembered state) ---",
                "--- COMBAT MEMORY (missing) ---",
                1,
            )
        }
    )

    with pytest.raises(ValueError, match="combat memory"):
        StubLlmClient(model="stub").complete(malformed)


@pytest.mark.unit
def test_stub_rejects_unknown_persona() -> None:
    request = _capture_current_request()
    unknown = request.model_copy(update={"persona": "unknown-persona"})

    with pytest.raises(KeyError, match="unknown-persona"):
        StubLlmClient(model="stub").complete(unknown)


@pytest.mark.unit
def test_berserker_closes_with_clean_los_until_point_blank() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))

    closing = pilot.decide(_observation(enemy_distance=8.0, has_line_of_sight_to_enemy=True))
    point_blank = pilot.decide(_observation(enemy_distance=3.0, has_line_of_sight_to_enemy=True))

    assert closing.action is SOPilotAction.MOVE
    assert closing.action_params == {"direction": "toward_enemy"}
    assert point_blank.action is SOPilotAction.FIRE_WEAPON
    assert point_blank.action_params == {"weapon_id": "weapon.light.machine_gun"}
    assert point_blank.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
@pytest.mark.parametrize(
    ("weapons", "pressure", "enemy_distance"),
    [
        ([_weapon(cooldown=2)], 40, 8.0),
        ([_weapon(pressure_cost=4)], 0, 8.0),
        ([_weapon(weapon_range=12)], 40, 13.0),
    ],
)
def test_berserker_never_fires_an_invalid_weapon(
    weapons: list[ModelSOPilotWeaponView], pressure: int, enemy_distance: float
) -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))

    decision = pilot.decide(
        _observation(
            weapons=weapons,
            pressure=pressure,
            enemy_distance=enemy_distance,
            has_line_of_sight_to_enemy=False,
        )
    )

    assert decision.action is SOPilotAction.MOVE
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_berserker_fires_first_ready_weapon_with_explicit_id() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))

    decision = pilot.decide(
        _observation(
            weapons=[
                _weapon(weapon_id="weapon.cooling", cooldown=2),
                _weapon(weapon_id="weapon.ready", cooldown=0),
            ]
        )
    )

    assert decision.action is SOPilotAction.FIRE_WEAPON
    assert decision.action_params == {"weapon_id": "weapon.ready"}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
@pytest.mark.parametrize(
    ("observation", "direction"),
    [
        (
            _observation(enemy_distance=13.0, has_line_of_sight_to_enemy=True),
            "toward_enemy",
        ),
        (
            _observation(enemy_distance=5.0, has_line_of_sight_to_enemy=True),
            "defensive",
        ),
        (
            _observation(enemy_distance=8.0, has_line_of_sight_to_enemy=False),
            "defensive",
        ),
    ],
)
def test_sniper_holds_standoff_and_requires_los(
    observation: ModelSOPilotObservation, direction: str
) -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("sniper"))

    decision = pilot.decide(observation)

    assert decision.action is SOPilotAction.MOVE
    assert decision.action_params == {"direction": direction}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_sniper_kites_after_repeated_hp_loss() -> None:
    """A persistent sniper breaks a losing trade before reaching critical HP."""
    decisions = _decide_sequence(
        "sniper",
        [
            {"hp_percent": 90.0, "has_line_of_sight_to_enemy": True},
            {"hp_percent": 80.0, "has_line_of_sight_to_enemy": True},
            {"hp_percent": 70.0, "has_line_of_sight_to_enemy": True},
        ],
    )

    assert decisions[0].action is SOPilotAction.FIRE_WEAPON
    assert decisions[1].action is SOPilotAction.FIRE_WEAPON
    assert decisions[2].action is SOPilotAction.MOVE
    assert decisions[2].action_params == {"direction": "defensive"}


@pytest.mark.unit
def test_opportunist_disengages_after_repeated_hp_loss() -> None:
    """An opportunist resets a bad trade before the low-HP emergency branch."""
    decisions = _decide_sequence(
        "opportunist",
        [
            {"hp_percent": 95.0, "has_line_of_sight_to_enemy": True},
            {"hp_percent": 82.0, "has_line_of_sight_to_enemy": True},
            {"hp_percent": 70.0, "has_line_of_sight_to_enemy": True},
        ],
    )

    assert decisions[0].action is SOPilotAction.FIRE_WEAPON
    assert decisions[1].action is SOPilotAction.FIRE_WEAPON
    assert decisions[2].action is SOPilotAction.MOVE
    assert decisions[2].action_params == {"direction": "defensive"}


@pytest.mark.unit
def test_sniper_vents_at_proactive_heat_threshold() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("sniper"))

    decision = pilot.decide(_observation(heat=60, has_line_of_sight_to_enemy=True))

    assert decision.action is SOPilotAction.VENT
    assert decision.action_params == {}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_opportunist_waits_without_contact_and_flanks_without_los() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("opportunist"))

    waiting = pilot.decide(_observation(enemy_confidence=None))
    flanking = pilot.decide(_observation(enemy_confidence=0.5, has_line_of_sight_to_enemy=False))

    assert waiting.action is SOPilotAction.REMAIN
    assert waiting.reason_code is SOPilotReasonCode.LLM_DECISION
    assert flanking.action is SOPilotAction.MOVE
    assert flanking.action_params == {"direction": "toward_enemy"}


@pytest.mark.unit
def test_opportunist_vents_when_low_hp_and_hot() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("opportunist"))

    decision = pilot.decide(_observation(hp_percent=29.0, heat=60))

    assert decision.action is SOPilotAction.VENT
    assert decision.action_params == {}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_opportunist_fires_explicit_weapon_when_enemy_overheats() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("opportunist"))

    decision = pilot.decide(_observation(enemy_heat=60.0, has_line_of_sight_to_enemy=True))

    assert decision.action is SOPilotAction.FIRE_WEAPON
    assert decision.action_params == {"weapon_id": "weapon.light.machine_gun"}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_opportunist_fires_explicit_weapon_on_clean_opening() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("opportunist"))

    decision = pilot.decide(
        _observation(
            enemy_confidence=0.9,
            enemy_heat=None,
            has_line_of_sight_to_enemy=True,
        )
    )

    assert decision.action is SOPilotAction.FIRE_WEAPON
    assert decision.action_params == {"weapon_id": "weapon.light.machine_gun"}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


@pytest.mark.unit
def test_opportunist_presses_overheating_enemy_without_clean_shot() -> None:
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("opportunist"))

    decision = pilot.decide(_observation(enemy_heat=60.0, has_line_of_sight_to_enemy=False))

    assert decision.action is SOPilotAction.MOVE
    assert decision.action_params == {"direction": "toward_enemy"}
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION


# ---------------------------------------------------------------------------
# Fallback on failures (the robustness contract)
# ---------------------------------------------------------------------------


class _GarbageClient:
    """Returns unparseable text to exercise the fallback path."""

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        return LlmResponse(
            text="this is not json {",
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="garbage",
            finish_reason="stop",
        )


class _CrashingClient:
    """Raises on every call to exercise the transport-failure fallback."""

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        raise ConnectionError("network down")


class _SemanticResponseClient:
    """Always answers with the same (semantically rejected) response text."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls = 0

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.calls += 1
        return LlmResponse(
            text=self._response_text,
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="semantic-fixture",
            finish_reason="stop",
        )


class _InvalidThenRemainClient:
    """Reject exactly the first action, then answer a valid REMAIN forever.

    Proves the happy-retry path (OMN-15239): a single semantic slip
    self-corrects on the same model, so ``decide`` returns a decision instead
    of raising and the match keeps playing.
    """

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.calls += 1
        if self.calls == 1:
            text = json.dumps(
                {
                    "action": "fire_weapon",
                    "action_params": {"weapon_id": "weapon.unknown"},
                    "confidence": 0.9,
                    "rationale": "invalid weapon",
                }
            )
        else:
            text = json.dumps(
                {
                    "action": "remain",
                    "action_params": {},
                    "confidence": 0.7,
                    "rationale": "recovered",
                }
            )
        return LlmResponse(
            text=text,
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="semantic-fixture",
            finish_reason="stop",
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("response_text", "weapon_cooldown", "expected_code"),
    [
        pytest.param("not json", 0, "malformed_json", id="malformed-json"),
        pytest.param(
            json.dumps(
                {
                    "action": "dance",
                    "action_params": {},
                    "confidence": 0.9,
                    "rationale": "dance",
                }
            ),
            0,
            "unknown_action",
            id="unknown-action",
        ),
        pytest.param(
            json.dumps(
                {
                    "action": "fire_weapon",
                    "action_params": {"weapon_id": "weapon.light.machine_gun"},
                    "confidence": 0.9,
                    "rationale": "fire",
                }
            ),
            2,
            "action_unavailable",
            id="action-unavailable",
        ),
        pytest.param(
            json.dumps(
                {
                    "action": "remain",
                    "action_params": {"unexpected": True},
                    "confidence": 0.9,
                    "rationale": "remain",
                }
            ),
            0,
            "invalid_action_parameters",
            id="invalid-action-parameters",
        ),
    ],
)
def test_raise_policy_exhausts_bounded_retry_and_surfaces_closed_semantic_failure_code(
    response_text: str,
    weapon_cooldown: int,
    expected_code: str,
) -> None:
    """OMN-15239: a persistent semantic failure under the ``raise`` policy is
    bounded-retried (mirroring card mode's ``LLMProgrammingPilot``) and only
    then raises the classified, catchable ``LlmSemanticExhaustedError`` --
    never the bare ``LlmSemanticError`` this test asserted pre-fix (a bare
    ``LlmSemanticError`` is not one of the two types the match runner's tick
    loop catches, so it used to escape and kill the whole match)."""
    client = _SemanticResponseClient(response_text)
    pilot = LLMPilot(
        client=client,
        persona=_persona("semantic-errors"),
        failure_policy="raise",
    )

    with pytest.raises(LlmSemanticExhaustedError) as raised:
        pilot.decide(_observation(weapons=[_weapon(cooldown=weapon_cooldown)]))

    assert not isinstance(raised.value, LlmSemanticError)
    assert raised.value.semantic_failure_code == expected_code
    # One initial attempt + the bounded reprompt budget -- every attempt is a
    # real provider call against the persistently failing fixture.
    assert client.calls == raised.value.attempts
    assert client.calls > 1


@pytest.mark.unit
def test_omn15239_semantic_exhaustion_raises_llm_semantic_exhausted_not_bare_semantic_error() -> (
    None
):
    """OMN-15239 repro/fix, direct form: a permanently invalid ``fire_weapon``
    action (well-formed JSON, unavailable weapon id -- exactly the live-battery
    ``invalid_action_parameters`` defect) must never escape ``decide()`` as a
    bare ``LlmSemanticError``. Pre-fix this raised immediately on the FIRST
    attempt (``client.calls == 1``) with no retry at all. Post-fix it is
    bounded-retried and raises ``LlmSemanticExhaustedError`` once exhausted."""

    class _AlwaysInvalidWeaponClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            self.calls += 1
            return LlmResponse(
                text=json.dumps(
                    {
                        "action": "fire_weapon",
                        "action_params": {"weapon_id": "weapon.unknown"},
                        "confidence": 0.9,
                        "rationale": "invalid weapon",
                    }
                ),
                usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
                model="fixture",
                finish_reason="stop",
            )

    client = _AlwaysInvalidWeaponClient()
    pilot = LLMPilot(client=client, persona=_persona("berserker"), failure_policy="raise")

    with pytest.raises(LlmSemanticExhaustedError) as raised:
        pilot.decide(_observation())

    assert not isinstance(raised.value, LlmSemanticError)
    assert raised.value.semantic_failure_code == "invalid_action_parameters"
    assert client.calls == raised.value.attempts
    assert client.calls > 1


@pytest.mark.unit
def test_omn15239_transient_semantic_failure_recovers_within_bounds() -> None:
    """OMN-15239: a single semantic slip self-corrects on the same model --
    ``decide`` returns a decision instead of raising, so the match keeps
    playing rather than aborting on a one-off provider mistake."""

    client = _InvalidThenRemainClient()
    pilot = LLMPilot(client=client, persona=_persona("berserker"), failure_policy="raise")

    decision = pilot.decide(_observation())

    assert decision.action is SOPilotAction.REMAIN
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION
    assert client.calls == 2


@pytest.mark.unit
def test_fallback_on_malformed_json() -> None:
    """Malformed LLM output degrades to REMAIN, not a crash."""
    pilot = LLMPilot(client=_GarbageClient(), persona=_persona("berserker"))
    decision = pilot.decide(_observation())
    assert decision.action is SOPilotAction.REMAIN
    assert decision.reason_code is SOPilotReasonCode.LLM_FALLBACK
    assert "LlmSemanticError" in (decision.rationale or "")


@pytest.mark.unit
def test_fallback_on_transport_error() -> None:
    """A network/transport failure degrades to REMAIN, not a crash."""
    pilot = LLMPilot(client=_CrashingClient(), persona=_persona("berserker"))
    decision = pilot.decide(_observation())
    assert decision.action is SOPilotAction.REMAIN
    assert decision.reason_code is SOPilotReasonCode.LLM_FALLBACK


@pytest.mark.unit
def test_fallback_on_unavailable_action() -> None:
    """An LLM returning a valid action that's unavailable this tick falls back."""

    class _FireOnCooldown:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text=json.dumps(
                    {
                        "action": "fire_weapon",
                        "action_params": {"weapon_id": "weapon.light.machine_gun"},
                        "confidence": 0.9,
                        "rationale": "fire",
                    }
                ),
                usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
                model="test",
                finish_reason="stop",
            )

    pilot = LLMPilot(client=_FireOnCooldown(), persona=_persona("berserker"))
    # Weapon on cooldown → FIRE_WEAPON not available
    obs = _observation(weapons=[_weapon(cooldown=2)])
    decision = pilot.decide(obs)
    assert decision.action is SOPilotAction.REMAIN
    assert decision.reason_code is SOPilotReasonCode.LLM_FALLBACK
    assert decision.reason_code is SOPilotReasonCode.LLM_FALLBACK


# ---------------------------------------------------------------------------
# Satisfies the protocol
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_llm_pilot_satisfies_pilot_protocol() -> None:
    """LLMPilot is structurally compatible with PilotProtocol."""
    from steel_onslaught.pilots.schemas import PilotProtocol

    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))
    assert isinstance(pilot, PilotProtocol)


@pytest.mark.unit
def test_objective_view_reaches_per_tick_llm_prompt() -> None:
    """Phase 4: pilots must SEE the objectives, or O-GATE measures blindness."""

    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("berserker"))
    pilot.decide(
        _observation(
            objectives=(
                ModelSOObjectiveView(
                    objective_id="objective.west_yard",
                    cell=ModelSOPosition(x=18, y=30),
                    vp_per_round=1,
                    control="unclaimed",
                    own_distance_chebyshev=14,
                ),
            ),
            victory_points=ModelSOVictoryPointsView(own_vp=2, enemy_vp=5, vp_threshold=15),
        )
    )

    assert client.request is not None
    prompt = client.request.user_prompt
    assert "--- OBJECTIVES" in prompt
    assert "first to 15 VP wins" in prompt
    assert "victory_points: you 2 vs enemy 5" in prompt
    assert (
        "objective.west_yard: cell=(18,30) vp_per_round=1 control=unclaimed your_distance=14"
    ) in prompt


@pytest.mark.unit
def test_objective_free_per_tick_prompt_is_unchanged() -> None:
    """No objectives -> no OBJECTIVES section: pre-Phase-4 prompts stay stable."""

    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("berserker"))
    pilot.decide(_observation())

    assert client.request is not None
    assert "OBJECTIVES" not in client.request.user_prompt
    assert "victory_points" not in client.request.user_prompt


# ---------------------------------------------------------------------------
# Display-salience arm #1 (OMN-15166): SODisplaySalience.DEFAULT/.PROMINENT
# ---------------------------------------------------------------------------

_SALIENCE_OBJECTIVES = (
    ModelSOObjectiveView(
        objective_id="objective.west_yard",
        cell=ModelSOPosition(x=18, y=30),
        vp_per_round=1,
        control="unclaimed",
        own_distance_chebyshev=14,
    ),
)
_SALIENCE_VP = ModelSOVictoryPointsView(own_vp=2, enemy_vp=5, vp_threshold=15)


def _salience_observation() -> ModelSOPilotObservation:
    return _observation(objectives=_SALIENCE_OBJECTIVES, victory_points=_SALIENCE_VP)


@pytest.mark.unit
def test_default_display_salience_is_byte_identical_to_pre_omn15166_rendering() -> None:
    """Golden-stability (the #210 standard): omitting ``display_salience`` --
    every pilot spec authored before OMN-15166 -- reproduces EXACTLY the
    OBJECTIVES block ``test_objective_view_reaches_per_tick_llm_prompt``
    (pre-existing, unmodified by this ticket) asserts against."""

    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("berserker"))
    pilot.decide(_salience_observation())

    assert client.request is not None
    prompt = client.request.user_prompt
    assert (
        "--- OBJECTIVES (hold a cell within 1, uncontested, to score; first to 15 VP wins) ---"
    ) in prompt
    assert "victory_points: you 2 vs enemy 5" in prompt
    assert (
        "  - objective.west_yard: cell=(18,30) vp_per_round=1 control=unclaimed your_distance=14"
    ) in prompt
    # The prominent-only markers must never appear on the default rendering.
    assert "!!!" not in prompt
    assert "REMINDER" not in prompt


@pytest.mark.unit
def test_explicit_default_matches_omitted_display_salience_construction() -> None:
    """``LLMPilot(..., display_salience=SODisplaySalience.DEFAULT)`` and
    omitting the kwarg entirely must produce the IDENTICAL wire request --
    proves the default is truly a no-op, not merely "renders the same
    objectives block" by coincidence."""

    omitted_client = _RecordingClient()
    LLMPilot(client=omitted_client, persona=_persona("berserker")).decide(_salience_observation())

    explicit_client = _RecordingClient()
    LLMPilot(
        client=explicit_client,
        persona=_persona("berserker"),
        display_salience=SODisplaySalience.DEFAULT,
    ).decide(_salience_observation())

    assert omitted_client.request is not None
    assert explicit_client.request is not None
    assert omitted_client.request.user_prompt == explicit_client.request.user_prompt


@pytest.mark.unit
def test_prominent_display_salience_renders_the_same_facts_with_emphasis() -> None:
    """PROMINENT changes formatting only -- same ids/coords/counts, no new
    information, no dropped information."""

    client = _RecordingClient()
    pilot = LLMPilot(
        client=client,
        persona=_persona("berserker"),
        display_salience=SODisplaySalience.PROMINENT,
    )
    pilot.decide(_salience_observation())

    assert client.request is not None
    prompt = client.request.user_prompt
    assert "!!! OBJECTIVES -- SCORING NOW" in prompt
    assert "FIRST TO 15 VP WINS" in prompt
    assert "VICTORY POINTS: YOU 2  --  ENEMY 5" in prompt
    assert (
        "  * objective.west_yard: cell=(18,30) vp_per_round=1 control=unclaimed your_distance=14"
    ) in prompt
    assert "REMINDER: capturing objectives is how this match is won." in prompt
    # The default header must never co-appear with the prominent one.
    assert "--- OBJECTIVES" not in prompt
    assert "victory_points: you 2 vs enemy 5" not in prompt


@pytest.mark.unit
def test_prominent_delta_from_default_is_confined_to_the_objectives_block() -> None:
    """Byte-level proof, same standard as #210/MASK
    (``tests/contracts/test_objmask_overlay.py::
    test_objmask_prompt_stream_delta_from_the_paying_corner_is_exactly_the_display_block``):
    strip the contiguous OBJECTIVES span out of both renderings and assert
    what remains is byte-identical -- nothing outside the block moves."""

    default_client = _RecordingClient()
    LLMPilot(client=default_client, persona=_persona("berserker")).decide(_salience_observation())
    prominent_client = _RecordingClient()
    LLMPilot(
        client=prominent_client,
        persona=_persona("berserker"),
        display_salience=SODisplaySalience.PROMINENT,
    ).decide(_salience_observation())

    assert default_client.request is not None
    assert prominent_client.request is not None
    default_lines = default_client.request.user_prompt.split("\n")
    prominent_lines = prominent_client.request.user_prompt.split("\n")

    default_start = next(
        i for i, line in enumerate(default_lines) if line.startswith("--- OBJECTIVES")
    )
    default_end = next(i for i, line in enumerate(default_lines) if line.startswith("--- ENEMY"))
    prominent_start = next(i for i, line in enumerate(prominent_lines) if line.startswith("=" * 60))
    prominent_end = next(
        i for i, line in enumerate(prominent_lines) if line.startswith("--- ENEMY")
    )

    default_stripped = default_lines[:default_start] + default_lines[default_end:]
    prominent_stripped = prominent_lines[:prominent_start] + prominent_lines[prominent_end:]
    assert default_stripped == prominent_stripped
    assert "\n".join(default_stripped) == "\n".join(prominent_stripped)


@pytest.mark.unit
def test_prominent_display_salience_is_a_noop_without_objectives() -> None:
    """Salience only ever modulates a block that is already being rendered --
    an objective-free observation stays byte-identical whichever value is
    set, exactly like DEFAULT's own no-op guard."""

    default_client = _RecordingClient()
    LLMPilot(client=default_client, persona=_persona("berserker")).decide(_observation())
    prominent_client = _RecordingClient()
    LLMPilot(
        client=prominent_client,
        persona=_persona("berserker"),
        display_salience=SODisplaySalience.PROMINENT,
    ).decide(_observation())

    assert default_client.request is not None
    assert prominent_client.request is not None
    assert default_client.request.user_prompt == prominent_client.request.user_prompt
    assert "OBJECTIVES" not in prominent_client.request.user_prompt


@pytest.mark.unit
def test_display_salience_threads_from_pilot_spec_through_the_pilot_factory() -> None:
    """Wiring proof: ``ModelSOLlmPilotParams.display_salience`` reaches the
    prompt via the REAL composition seam
    (``ApplicationPilotFactory.from_spec`` -> ``.llm_pilot``), not a
    hand-built ``LLMPilot`` -- the same seam ``composition.py``'s
    production root uses."""

    from steel_onslaught.contracts.pilot import ModelSOPilotLineage, ModelSOPilotSpec
    from steel_onslaught.llm.client_http import StaticLlmClientFactory
    from steel_onslaught.llm.personas import PersonaRegistry
    from steel_onslaught.match.composition import ApplicationPilotFactory

    client = _RecordingClient()
    factory = ApplicationPilotFactory(
        clients=StaticLlmClientFactory({"stub": client}),
        personas=PersonaRegistry({"berserker": _persona("berserker")}),
    )
    spec = ModelSOPilotSpec(
        id="pilot.llm.test_salience",
        display_name="Test salience pilot",
        archetype="llm",
        lineage=ModelSOPilotLineage(parent="pilot.template.llm"),
        parameters=ModelSOLlmPilotParams(
            persona="berserker",
            provider="stub",
            display_salience=SODisplaySalience.PROMINENT,
        ),
    )
    pilot = factory.from_spec(spec)
    pilot.decide(_salience_observation())

    assert client.request is not None
    prompt = client.request.user_prompt
    assert "!!! OBJECTIVES -- SCORING NOW" in prompt
    assert "--- OBJECTIVES" not in prompt


@pytest.mark.unit
def test_display_salience_omitted_pilot_spec_threads_default_through_the_pilot_factory() -> None:
    """The wiring counterpart of the golden-stability test above: a pilot
    spec that predates OMN-15166 (no ``display_salience`` key at all) still
    resolves through ``ApplicationPilotFactory`` to the byte-identical
    default rendering."""

    from steel_onslaught.contracts.pilot import ModelSOPilotLineage, ModelSOPilotSpec
    from steel_onslaught.llm.client_http import StaticLlmClientFactory
    from steel_onslaught.llm.personas import PersonaRegistry
    from steel_onslaught.match.composition import ApplicationPilotFactory

    client = _RecordingClient()
    factory = ApplicationPilotFactory(
        clients=StaticLlmClientFactory({"stub": client}),
        personas=PersonaRegistry({"berserker": _persona("berserker")}),
    )
    spec = ModelSOPilotSpec(
        id="pilot.llm.test_salience_default",
        display_name="Test salience default pilot",
        archetype="llm",
        lineage=ModelSOPilotLineage(parent="pilot.template.llm"),
        parameters=ModelSOLlmPilotParams(persona="berserker", provider="stub"),
    )
    pilot = factory.from_spec(spec)
    pilot.decide(_salience_observation())

    assert client.request is not None
    prompt = client.request.user_prompt
    assert (
        "--- OBJECTIVES (hold a cell within 1, uncontested, to score; first to 15 VP wins) ---"
    ) in prompt
    assert "!!!" not in prompt


# ---------------------------------------------------------------------------
# Vision-representation experiment (2026-07-24): V-TEXT/V-IMG arm toggle
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_image_attachment_config_leaves_request_unattached() -> None:
    """V-TEXT arm: default construction never attaches an image."""
    client = _RecordingClient()
    pilot = LLMPilot(client=client, persona=_persona("berserker"))
    pilot.decide(_observation())

    assert client.request is not None
    assert client.request.image_attachment is None
    assert _IMAGE_ATTACHMENT_NOTE not in client.request.user_prompt


@pytest.mark.unit
def test_image_attachment_config_attaches_rendered_png_and_persists_it(tmp_path: Path) -> None:
    """V-IMG arm: renders + persists the PNG and attaches sha256-matched bytes."""
    client = _RecordingClient()
    output_dir = tmp_path / "renders"
    pilot = LLMPilot(
        client=client,
        persona=_persona("berserker"),
        image_attachment=ModelSOLlmImageAttachmentBinding(
            enabled=True,
            arena_size=20,
            render_output_dir=output_dir,
        ),
    )
    pilot.decide(_observation())

    assert client.request is not None
    attachment = client.request.image_attachment
    assert attachment is not None
    assert attachment.sha256_hex == hashlib.sha256(attachment.png_bytes).hexdigest()
    assert _IMAGE_ATTACHMENT_NOTE in client.request.user_prompt

    persisted_path = output_dir / "m" / "tick_0001_mech.a.png"
    assert persisted_path.is_file()
    assert persisted_path.read_bytes() == attachment.png_bytes


@pytest.mark.unit
def test_image_attachment_prompt_delta_is_exactly_the_neutral_note(tmp_path: Path) -> None:
    """The ONLY user-prompt delta between V-TEXT and V-IMG is the neutral note."""
    text_client = _RecordingClient()
    image_client = _RecordingClient()
    text_pilot = LLMPilot(client=text_client, persona=_persona("berserker"))
    image_pilot = LLMPilot(
        client=image_client,
        persona=_persona("berserker"),
        image_attachment=ModelSOLlmImageAttachmentBinding(
            enabled=True,
            arena_size=20,
            render_output_dir=tmp_path / "renders",
        ),
    )
    observation = _observation()
    text_pilot.decide(observation)
    image_pilot.decide(observation)
    assert text_client.request is not None
    assert image_client.request is not None
    text_prompt = text_client.request.user_prompt
    image_prompt = image_client.request.user_prompt
    assert image_prompt == f"{text_prompt}\n\n{_IMAGE_ATTACHMENT_NOTE}"


# ---------------------------------------------------------------------------
# Blank-image control arm (2026-07-24): render_mode="blank" toggle
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_mode_defaults_to_arena_render_for_existing_configs(tmp_path: Path) -> None:
    """Every pre-existing V-IMG config omits render_mode and must behave unchanged."""
    binding = ModelSOLlmImageAttachmentBinding(
        enabled=True,
        arena_size=20,
        render_output_dir=tmp_path / "renders",
    )
    assert binding.render_mode == "arena_render"


@pytest.mark.unit
def test_blank_render_mode_attaches_content_free_image_of_matched_dimensions(
    tmp_path: Path,
) -> None:
    """render_mode='blank': attaches a same-size render distinct from the arena render."""
    real_client = _RecordingClient()
    blank_client = _RecordingClient()
    real_pilot = LLMPilot(
        client=real_client,
        persona=_persona("berserker"),
        image_attachment=ModelSOLlmImageAttachmentBinding(
            enabled=True,
            arena_size=20,
            render_output_dir=tmp_path / "renders_real",
        ),
    )
    blank_pilot = LLMPilot(
        client=blank_client,
        persona=_persona("berserker"),
        image_attachment=ModelSOLlmImageAttachmentBinding(
            enabled=True,
            arena_size=20,
            render_output_dir=tmp_path / "renders_blank",
            render_mode="blank",
        ),
    )
    observation = _observation()
    real_pilot.decide(observation)
    blank_pilot.decide(observation)

    assert real_client.request is not None
    assert blank_client.request is not None
    real_attachment = real_client.request.image_attachment
    blank_attachment = blank_client.request.image_attachment
    assert real_attachment is not None
    assert blank_attachment is not None
    assert blank_attachment.png_bytes != real_attachment.png_bytes
    assert blank_attachment.sha256_hex == hashlib.sha256(blank_attachment.png_bytes).hexdigest()
    # Same neutral note, same user-prompt delta as the real-render V-IMG arm --
    # only the attached bytes differ.
    assert _IMAGE_ATTACHMENT_NOTE in blank_client.request.user_prompt
