"""Tests for the LLM pilot (stub-driven, no network)."""

from __future__ import annotations

import json

import pytest

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.pilot import LLMPilot
from steel_onslaught.llm.schemas import LlmResponse, LlmUsage, ModelSOLlmCompletionRequest
from steel_onslaught.llm.stub import StubLlmClient
from steel_onslaught.pilots.schemas import (
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
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _weapon(
    *, weapon_id: str = "weapon.light.machine_gun", cooldown: int = 0
) -> ModelSOPilotWeaponView:
    return ModelSOPilotWeaponView(
        weapon_id=weapon_id,
        damage=8,
        range=12,
        pressure_cost=4,
        heat_generated=3,
        cooldown_remaining_ticks=cooldown,
    )


def _observation(
    *,
    weapons: list[ModelSOPilotWeaponView] | None = None,
    enemy_confidence: float | None = 0.9,
    heat: int = 10,
    has_line_of_sight_to_enemy: bool = False,
    blocked_directions: tuple[SOCompassDirection, ...] = (),
) -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id="m",
        mech_id="mech.a",
        player_id="player.a",
        tick=1,
        match_elapsed_ticks=1,
        boiler=_boiler(heat=heat),
        weapons=weapons if weapons is not None else [_weapon()],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=10, y=10),
        hp_percent=80.0,
        under_sensor_lock=False,
        has_line_of_sight_to_enemy=has_line_of_sight_to_enemy,
        blocked_directions=blocked_directions,
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id="mech.b", tick=1, distance_estimate=8.0, confidence=enemy_confidence
            )
        ]
        if enemy_confidence is not None
        else [],
    )


# ---------------------------------------------------------------------------
# Stub-driven decisions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_berserker_fires_when_weapon_ready() -> None:
    """The berserker stub fires when a weapon is off cooldown."""
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("berserker"))
    decision = pilot.decide(_observation())
    assert decision.action is SOPilotAction.FIRE_WEAPON
    assert decision.reason_code is SOPilotReasonCode.LLM_DECISION
    assert decision.rationale is not None


@pytest.mark.unit
def test_sniper_fires_on_high_confidence() -> None:
    """The sniper stub fires when sensor confidence is high."""
    pilot = LLMPilot(client=StubLlmClient(model="stub"), persona=_persona("sniper"))
    decision = pilot.decide(_observation(enemy_confidence=0.9))
    assert decision.action is SOPilotAction.FIRE_WEAPON


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

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.request = request
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
