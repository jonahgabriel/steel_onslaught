"""Tests for the LLM pilot (stub-driven, no network)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.llm.effect import LlmSemanticError
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.pilot import LLMPilot
from steel_onslaught.llm.schemas import LlmResponse, LlmUsage, ModelSOLlmCompletionRequest
from steel_onslaught.llm.stub import StubLlmClient
from steel_onslaught.pilots.schemas import (
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
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
        heat_capacity=100,
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
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        return LlmResponse(
            text=self._response_text,
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
def test_raise_policy_surfaces_closed_semantic_failure_code(
    response_text: str,
    weapon_cooldown: int,
    expected_code: str,
) -> None:
    pilot = LLMPilot(
        client=_SemanticResponseClient(response_text),
        persona=_persona("semantic-errors"),
        failure_policy="raise",
    )

    with pytest.raises(LlmSemanticError) as raised:
        pilot.decide(_observation(weapons=[_weapon(cooldown=weapon_cooldown)]))

    assert raised.value.code == expected_code


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
