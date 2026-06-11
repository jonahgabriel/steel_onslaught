"""Tests for the predictive pilot heuristic — Task 17.

Invariants (from the plan):
- Given last-3 enemy positions show approach: switches mode before enemy arrives.
- Given lock_confidence 0.5: holds fire (waits).
- Given lock_confidence 0.7 + predicted_hit 0.6: fires.
- Linear extrapolation is deterministic (no smoothing, no random).
- Given heat >= redline_threshold - 5: vents preemptively.
- Given pressure < 30 AND no immediate threat: moves to defensive position to regen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import (
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    SOPilotAction,
)

_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / "contracts_data" / "pilots" / "template_predictive.yaml"
)


def _template_spec() -> ModelSOPilotSpec:
    return ModelSOPilotSpec.model_validate(yaml.safe_load(_TEMPLATE_PATH.read_text()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _boiler(
    pressure: int = 60,
    heat: int = 20,
    redline: int = 80,
    rupture: int = 100,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id="m",
        mech_id="mech.red.01",
        tick=0,
        pressure_current=pressure,
        pressure_maximum=100,
        regeneration_per_tick=5,
        heat_current=heat,
        heat_redline_threshold=redline,
        heat_rupture_threshold=rupture,
        heat_vent_rate=10,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _weapon(
    weapon_id: str = "weapon.steam_cannon",
    damage: int = 25,
    range_: int = 12,
    pressure_cost: int = 15,
    heat_generated: int = 10,
    cooldown: int = 0,
) -> ModelSOPilotWeaponView:
    return ModelSOPilotWeaponView(
        weapon_id=weapon_id,
        damage=damage,
        range=range_,
        pressure_cost=pressure_cost,
        heat_generated=heat_generated,
        cooldown_remaining_ticks=cooldown,
    )


def _sensor_reading(
    enemy_id: str = "mech.blue.01",
    tick: int = 0,
    distance: float = 10.0,
    confidence: float = 0.7,
) -> ModelSOSensorReading:
    return ModelSOSensorReading(
        enemy_mech_id=enemy_id,
        tick=tick,
        distance_estimate=distance,
        confidence=confidence,
    )


def _observation(
    *,
    position: ModelSOPosition | None = None,
    enemy_observations: list[ModelSOSensorReading] | None = None,
    current_mode: str = "assault",
    mode_lock_expired: bool = True,
    boiler: ModelSOBoilerState | None = None,
    weapons: list[ModelSOPilotWeaponView] | None = None,
    hp_percent: float = 100.0,
    under_sensor_lock: bool = False,
    tick: int = 3,
) -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id="m",
        mech_id="mech.red.01",
        tick=tick,
        match_elapsed_ticks=tick,
        boiler=boiler if boiler is not None else _boiler(),
        weapons=weapons if weapons is not None else [_weapon()],
        current_mode=current_mode,
        mode_lock_expired=mode_lock_expired,
        position=position or ModelSOPosition(x=0, y=0),
        hp_percent=hp_percent,
        under_sensor_lock=under_sensor_lock,
        enemy_observations=enemy_observations if enemy_observations is not None else [],
    )


# ---------------------------------------------------------------------------
# Invariant tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_implements_pilot_protocol() -> None:
    """PredictivePilot satisfies PilotProtocol (duck-typing, not ABC)."""
    from steel_onslaught.pilots.schemas import PilotProtocol

    pilot = PredictivePilot(spec=_template_spec())
    assert isinstance(pilot, PilotProtocol)


@pytest.mark.unit
def test_decide_returns_pilot_decision() -> None:
    """decide() always returns a valid ModelSOPilotDecision."""
    pilot = PredictivePilot(spec=_template_spec())
    obs = _observation()
    decision = pilot.decide(obs)
    assert isinstance(decision, ModelSOPilotDecision)
    assert decision.action in SOPilotAction.__members__.values()
    # considered_actions must include the chosen action (schema invariant)
    assert any(c.action == decision.action for c in decision.considered_actions)


@pytest.mark.unit
def test_approaching_enemy_triggers_mode_switch() -> None:
    """Given last-3 enemy positions show approach: switches mode before enemy arrives.

    Enemy positions: distances 25, 20, 15 (approaching).
    At distance 15 the enemy is outside weapon range (range=12).
    Extrapolated next-tick distance ≈ 10 — inside range.
    Mode-switch needed (currently in recon, assault gives weapon access).
    Mode lock expired → pilot chooses SWITCH_MODE.
    """
    observations = [
        _sensor_reading(tick=0, distance=25.0, confidence=0.7),
        _sensor_reading(tick=1, distance=20.0, confidence=0.7),
        _sensor_reading(tick=2, distance=15.0, confidence=0.7),
    ]
    # Weapon range is 12; current distance 15 → enemy out of range.
    # Extrapolated distance next tick ≈ 10 → in range.
    obs = _observation(
        enemy_observations=observations,
        current_mode="recon",  # mode-switch needed to unlock weapons
        mode_lock_expired=True,
        tick=3,
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.SWITCH_MODE


@pytest.mark.unit
def test_low_confidence_holds_fire() -> None:
    """Given lock_confidence 0.5: holds fire (waits)."""
    observations = [_sensor_reading(tick=2, distance=8.0, confidence=0.5)]
    # Enemy inside weapon range, weapon ready, pressure fine.
    # BUT confidence=0.5 < 0.65 threshold → must NOT fire.
    obs = _observation(
        enemy_observations=observations,
        current_mode="assault",
        tick=3,
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action != SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_high_confidence_and_high_predicted_hit_fires() -> None:
    """Given lock_confidence 0.7 + predicted_hit >= 0.6: fires.

    Enemy at distance 3, weapon range 12:
      - hit_probability = 1 - 3/12 = 0.75 >= 0.55 threshold
      - confidence 0.7 >= 0.65 threshold
    Both thresholds satisfied → FIRE_WEAPON.
    """
    observations = [_sensor_reading(tick=2, distance=3.0, confidence=0.7)]
    obs = _observation(
        enemy_observations=observations,
        current_mode="assault",
        tick=3,
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_preemptive_vent_when_heat_near_redline() -> None:
    """Given heat >= redline_threshold - 5: vent preemptively.

    Redline=80, heat=76 → 80-76=4 ≤ 5 → vent.
    Even with enemy in range and confidence OK.
    """
    observations = [_sensor_reading(tick=2, distance=8.0, confidence=0.7)]
    obs = _observation(
        enemy_observations=observations,
        current_mode="assault",
        tick=3,
        boiler=_boiler(pressure=60, heat=76, redline=80, rupture=100),
        weapons=[_weapon(range_=12)],
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.VENT


@pytest.mark.unit
def test_low_pressure_no_threat_moves_to_regen() -> None:
    """Given pressure < 30 AND no immediate threat: MOVE to defensive position to regen."""
    # No enemy observations = no immediate threat.
    obs = _observation(
        enemy_observations=[],
        current_mode="assault",
        tick=3,
        boiler=_boiler(pressure=25, heat=20),  # pressure=25 < 30
        weapons=[_weapon(range_=12, cooldown=3)],  # weapon on cooldown anyway
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.MOVE


@pytest.mark.unit
def test_linear_extrapolation_is_deterministic() -> None:
    """Linear extrapolation produces the same result on repeated calls."""
    observations = [
        _sensor_reading(tick=0, distance=30.0, confidence=0.7),
        _sensor_reading(tick=1, distance=25.0, confidence=0.7),
        _sensor_reading(tick=2, distance=20.0, confidence=0.7),
    ]
    obs = _observation(
        enemy_observations=observations,
        current_mode="recon",
        mode_lock_expired=True,
        tick=3,
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision_a = pilot.decide(obs)
    decision_b = pilot.decide(obs)
    assert decision_a.action == decision_b.action
    assert decision_a.reason_code == decision_b.reason_code


@pytest.mark.unit
def test_no_enemy_observations_does_not_fire() -> None:
    """Without any sensor readings the pilot cannot fire."""
    obs = _observation(
        enemy_observations=[],
        current_mode="assault",
        tick=3,
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action != SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_mode_switch_requires_mode_lock_expired() -> None:
    """If mode lock has NOT expired, the pilot must not choose SWITCH_MODE.

    Even if the approaching enemy heuristic would normally trigger a mode switch.
    """
    observations = [
        _sensor_reading(tick=0, distance=25.0, confidence=0.7),
        _sensor_reading(tick=1, distance=20.0, confidence=0.7),
        _sensor_reading(tick=2, distance=15.0, confidence=0.7),
    ]
    obs = _observation(
        enemy_observations=observations,
        current_mode="recon",
        mode_lock_expired=False,  # lock NOT expired — must not switch
        tick=3,
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    assert decision.action != SOPilotAction.SWITCH_MODE


@pytest.mark.unit
def test_already_in_correct_mode_no_unnecessary_switch() -> None:
    """If already in assault mode, no mode-switch triggered for approaching enemy."""
    observations = [
        _sensor_reading(tick=0, distance=25.0, confidence=0.7),
        _sensor_reading(tick=1, distance=20.0, confidence=0.7),
        _sensor_reading(tick=2, distance=15.0, confidence=0.7),
    ]
    obs = _observation(
        enemy_observations=observations,
        current_mode="assault",  # already in assault
        mode_lock_expired=True,
        tick=3,
        weapons=[_weapon(range_=12, cooldown=0, pressure_cost=15)],
        boiler=_boiler(pressure=60, heat=20),
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    # Should not switch — already in the right mode.
    assert decision.action != SOPilotAction.SWITCH_MODE


@pytest.mark.unit
def test_extrapolation_with_only_one_observation() -> None:
    """With only one observation, linear extrapolation falls back to last known distance."""
    observations = [_sensor_reading(tick=2, distance=8.0, confidence=0.7)]
    obs = _observation(
        enemy_observations=observations,
        current_mode="assault",
        tick=3,
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    pilot = PredictivePilot(spec=_template_spec())
    decision = pilot.decide(obs)
    # Should still produce a valid decision (not crash).
    assert isinstance(decision, ModelSOPilotDecision)
