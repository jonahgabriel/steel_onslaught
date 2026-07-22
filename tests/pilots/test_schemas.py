"""Tests for pilot observation + decision schemas (Task 14).

Invariants under test (from the plan):
- Decision must reference an action available given current state
  (e.g. SWITCH_MODE requires mode_lock_expired).
- `confidence` is clamped to [0, 1].
- `considered_actions` includes the chosen action.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    PilotProtocol,
    SOPilotAction,
    SOPilotReasonCode,
    available_actions,
    validate_decision_against_observation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _boiler_state(*, pressure: int = 40, heat: int = 20) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id="match-001",
        mech_id="mech-red",
        tick=5,
        pressure_current=pressure,
        pressure_maximum=60,
        regeneration_per_tick=3,
        heat_current=heat,
        heat_redline_threshold=80,
        heat_capacity=100,
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
    *,
    weapon_id: str = "weapon.gatling_array",
    cooldown: int = 0,
    pressure_cost: int = 8,
) -> ModelSOPilotWeaponView:
    return ModelSOPilotWeaponView(
        weapon_id=weapon_id,
        damage=12,
        range=6,
        pressure_cost=pressure_cost,
        heat_generated=10,
        cooldown_remaining_ticks=cooldown,
    )


def _observation(
    *,
    boiler: ModelSOBoilerState | None = None,
    weapons: list[ModelSOPilotWeaponView] | None = None,
    mode_lock_expired: bool = True,
    enemy_observations: list[ModelSOSensorReading] | None = None,
) -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id="match-001",
        mech_id="mech-red",
        player_id="player-red",
        tick=5,
        match_elapsed_ticks=5,
        boiler=boiler if boiler is not None else _boiler_state(),
        weapons=weapons if weapons is not None else [_weapon()],
        current_mode=ModeId.RECON,
        mode_lock_expired=mode_lock_expired,
        position=ModelSOPosition(x=3, y=7),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=(enemy_observations if enemy_observations is not None else []),
    )


def _decision(
    *,
    action: SOPilotAction = SOPilotAction.REMAIN,
    confidence: float = 0.5,
    considered: list[ModelSOConsideredAction] | None = None,
) -> ModelSOPilotDecision:
    if considered is None:
        considered = [ModelSOConsideredAction(action=action, score=1.0)]
    return ModelSOPilotDecision(
        action=action,
        action_params={},
        reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
        confidence=confidence,
        considered_actions=considered,
    )


@pytest.mark.unit
def test_default_action_params_are_deeply_immutable() -> None:
    decision = ModelSOPilotDecision(
        action=SOPilotAction.REMAIN,
        reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
        confidence=0.5,
        considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0)],
    )

    with pytest.raises(TypeError):
        decision.action_params["forged"] = True  # type: ignore[index]


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pilot_action_enum_members() -> None:
    assert {a.name for a in SOPilotAction} == {
        "REMAIN",
        "MOVE",
        "FIRE_WEAPON",
        "ACTIVATE_MODULE",
        "VENT",
        "SWITCH_MODE",
        "EMERGENCY_SHUTDOWN",
        "DISENGAGE",
    }


@pytest.mark.unit
def test_pilot_action_values_are_lower_snake() -> None:
    for action in SOPilotAction:
        assert action.value == action.name.lower()


# ---------------------------------------------------------------------------
# Observation model
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_observation_constructs_with_sensor_readings() -> None:
    reading = ModelSOSensorReading(
        enemy_mech_id="mech-blue",
        tick=5,
        distance_estimate=4.2,
        confidence=0.8,
        heat_estimate=35.0,
        mode_estimate=ModeId.ASSAULT,
    )
    obs = _observation(enemy_observations=[reading])
    assert obs.enemy_observations[0].enemy_mech_id == "mech-blue"
    assert obs.tick == 5
    assert obs.match_elapsed_ticks == 5
    assert obs.boiler.pressure_current == 40
    assert obs.position.x == 3


@pytest.mark.unit
def test_observation_is_frozen() -> None:
    obs = _observation()
    with pytest.raises(ValidationError):
        obs.tick = 6


@pytest.mark.unit
def test_observation_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelSOPilotObservation.model_validate({**_observation().model_dump(), "surprise": True})


@pytest.mark.unit
def test_observation_rejects_unknown_current_mode() -> None:
    data = _observation().model_dump(mode="json")
    data["current_mode"] = "siege"

    with pytest.raises(ValidationError):
        ModelSOPilotObservation.model_validate(data)


@pytest.mark.unit
def test_sensor_reading_rejects_unknown_mode_estimate() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorReading(
            enemy_mech_id="mech-blue",
            tick=5,
            distance_estimate=4.2,
            confidence=0.8,
            mode_estimate="siege",  # type: ignore[arg-type]
        )


@pytest.mark.unit
def test_sensor_reading_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorReading(
            enemy_mech_id="mech-blue",
            tick=0,
            distance_estimate=1.0,
            confidence=1.5,
        )
    with pytest.raises(ValidationError):
        ModelSOSensorReading(
            enemy_mech_id="mech-blue",
            tick=0,
            distance_estimate=1.0,
            confidence=-0.1,
        )


@pytest.mark.unit
def test_sensor_reading_optional_estimates_default_none() -> None:
    reading = ModelSOSensorReading(
        enemy_mech_id="mech-blue",
        tick=0,
        distance_estimate=1.0,
        confidence=0.5,
    )
    assert reading.heat_estimate is None
    assert reading.mode_estimate is None


# ---------------------------------------------------------------------------
# Decision model: confidence clamped to [0, 1]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_confidence_above_one_clamps_to_one() -> None:
    assert _decision(confidence=1.5).confidence == 1.0


@pytest.mark.unit
def test_confidence_below_zero_clamps_to_zero() -> None:
    assert _decision(confidence=-0.2).confidence == 0.0


@pytest.mark.unit
def test_confidence_in_range_unchanged() -> None:
    assert _decision(confidence=0.42).confidence == 0.42


# ---------------------------------------------------------------------------
# Decision model: considered_actions includes the chosen action
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chosen_action_must_be_in_considered_actions() -> None:
    with pytest.raises(ValidationError, match="considered_actions"):
        _decision(
            action=SOPilotAction.FIRE_WEAPON,
            considered=[ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.3)],
        )


@pytest.mark.unit
def test_empty_considered_actions_rejected() -> None:
    with pytest.raises(ValidationError):
        _decision(action=SOPilotAction.REMAIN, considered=[])


@pytest.mark.unit
def test_chosen_action_present_passes() -> None:
    decision = _decision(
        action=SOPilotAction.FIRE_WEAPON,
        considered=[
            ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=0.9),
            ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.3),
        ],
    )
    assert decision.action is SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_decision_rejects_unknown_reason_code() -> None:
    with pytest.raises(ValidationError):
        ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            action_params={},
            reason_code="totally_made_up",  # type: ignore[arg-type]
            confidence=0.5,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0)],
        )


@pytest.mark.unit
def test_decision_round_trips_through_json_dump() -> None:
    decision = _decision(action=SOPilotAction.VENT, confidence=0.7)
    restored = ModelSOPilotDecision.model_validate(decision.model_dump(mode="json"))
    assert restored == decision


# ---------------------------------------------------------------------------
# Availability invariant
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_baseline_actions_always_available() -> None:
    obs = _observation(mode_lock_expired=False, weapons=[])
    avail = available_actions(obs)
    for action in (
        SOPilotAction.REMAIN,
        SOPilotAction.MOVE,
        SOPilotAction.VENT,
        SOPilotAction.EMERGENCY_SHUTDOWN,
        SOPilotAction.DISENGAGE,
        SOPilotAction.ACTIVATE_MODULE,
    ):
        assert action in avail


@pytest.mark.unit
def test_switch_mode_requires_mode_lock_expired() -> None:
    locked = _observation(mode_lock_expired=False)
    assert SOPilotAction.SWITCH_MODE not in available_actions(locked)

    unlocked = _observation(mode_lock_expired=True)
    assert SOPilotAction.SWITCH_MODE in available_actions(unlocked)


@pytest.mark.unit
def test_fire_weapon_requires_ready_weapon() -> None:
    on_cooldown = _observation(weapons=[_weapon(cooldown=3)])
    assert SOPilotAction.FIRE_WEAPON not in available_actions(on_cooldown)

    ready = _observation(weapons=[_weapon(cooldown=0)])
    assert SOPilotAction.FIRE_WEAPON in available_actions(ready)


@pytest.mark.unit
def test_fire_weapon_requires_pressure_for_cost() -> None:
    broke = _observation(
        boiler=_boiler_state(pressure=5),
        weapons=[_weapon(cooldown=0, pressure_cost=8)],
    )
    assert SOPilotAction.FIRE_WEAPON not in available_actions(broke)


@pytest.mark.unit
def test_validate_decision_rejects_unavailable_switch_mode() -> None:
    obs = _observation(mode_lock_expired=False)
    decision = _decision(action=SOPilotAction.SWITCH_MODE)
    with pytest.raises(ValueError, match="switch_mode"):
        validate_decision_against_observation(obs, decision)


@pytest.mark.unit
def test_validate_decision_accepts_available_action() -> None:
    obs = _observation(mode_lock_expired=True)
    decision = _decision(action=SOPilotAction.SWITCH_MODE)
    validate_decision_against_observation(obs, decision)


# ---------------------------------------------------------------------------
# PilotProtocol
# ---------------------------------------------------------------------------


class _StubPilot:
    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            action_params={},
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=0.0,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.0)],
        )


class _NotAPilot:
    pass


@pytest.mark.unit
def test_stub_pilot_satisfies_protocol() -> None:
    pilot: PilotProtocol = _StubPilot()
    decision = pilot.decide(_observation())
    assert decision.action is SOPilotAction.REMAIN
    assert isinstance(_StubPilot(), PilotProtocol)


@pytest.mark.unit
def test_non_pilot_fails_runtime_protocol_check() -> None:
    assert not isinstance(_NotAPilot(), PilotProtocol)
