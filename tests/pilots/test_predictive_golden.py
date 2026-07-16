"""Golden parity test for the predictive pilot refactor — Task 4.

Asserts that ``PredictivePilot(spec=template_spec)`` produces decisions
byte-for-byte identical to the pre-refactor hardcoded pilot on every
observation in the shared battery.

The golden fixture (``predictive_golden.json``) was generated from the
hardcoded pilot BEFORE the refactor; it is the oracle.

Additional invariants tested here (§Task 4):
- Tuned ``lock_confidence_floor: 0.45`` fires at confidence 0.5 where
  template holds.
- Tuned ``regen_pressure_floor: 0`` does not reposition on the pressure-29
  no-threat observation.
- ``PredictivePilot(spec=<aggressive spec>)`` raises at construction.
- ``ModelSOPredictivePilotParams`` has exactly the four fields listed in
  Task 1 (introspection: no extra fields).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.pilot import (
    ModelSOPilotSpec,
    ModelSOPredictivePilotParams,
)
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import (
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    SOPilotAction,
)
from tests.pilots.golden.observation_battery import observation_battery

_GOLDEN_PATH = Path(__file__).parent / "golden" / "predictive_golden.json"
_TEMPLATE_PREDICTIVE = (
    Path(__file__).parent.parent.parent / "contracts_data" / "pilots" / "template_predictive.yaml"
)
_TEMPLATE_AGGRESSIVE = (
    Path(__file__).parent.parent.parent / "contracts_data" / "pilots" / "template_aggressive.yaml"
)


def _load_spec(path: Path) -> ModelSOPilotSpec:
    return ModelSOPilotSpec.model_validate(yaml.safe_load(path.read_text()))


# ---------------------------------------------------------------------------
# Golden parity — main invariant
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_template_spec_matches_hardcoded_golden() -> None:
    """template spec pilot must reproduce every golden decision."""
    spec = _load_spec(_TEMPLATE_PREDICTIVE)
    pilot = PredictivePilot(spec=spec)
    battery = observation_battery()
    data = json.loads(_GOLDEN_PATH.read_text())
    golden = data["decisions"]
    assert len(golden) == len(battery), (
        f"Battery size mismatch: golden has {len(golden)}, battery has {len(battery)}"
    )
    for entry in golden:
        obs = battery[entry["observation_index"]]
        expected = ModelSOPilotDecision.model_validate(entry["decision"])
        got = pilot.decide(obs)
        assert got == expected, (
            f"Decision mismatch at observation_index={entry['observation_index']}: "
            f"expected {expected.action!r} ({expected.reason_code!r}), "
            f"got {got.action!r} ({got.reason_code!r})"
        )


# ---------------------------------------------------------------------------
# Pre-existing Task 17 invariants — spec-constructed pilot
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


def _sensor(
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
        player_id="player.red",
        tick=tick,
        match_elapsed_ticks=tick,
        boiler=boiler if boiler is not None else _boiler(),
        weapons=weapons if weapons is not None else [_weapon()],
        current_mode=ModeId(current_mode),
        mode_lock_expired=mode_lock_expired,
        position=ModelSOPosition(x=0, y=0),
        hp_percent=hp_percent,
        under_sensor_lock=under_sensor_lock,
        enemy_observations=enemy_observations if enemy_observations is not None else [],
    )


@pytest.mark.unit
def test_holds_fire_at_low_confidence_spec() -> None:
    """lock_confidence 0.5 < 0.65 → must NOT fire (Task 17 invariant, spec-constructed)."""
    spec = _load_spec(_TEMPLATE_PREDICTIVE)
    pilot = PredictivePilot(spec=spec)
    obs = _observation(
        enemy_observations=[_sensor(tick=2, distance=8.0, confidence=0.5)],
        current_mode="assault",
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    decision = pilot.decide(obs)
    assert decision.action != SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_fires_at_high_confidence_spec() -> None:
    """lock_confidence 0.7 + predicted_hit 0.75 → FIRE_WEAPON (Task 17 invariant, spec)."""
    spec = _load_spec(_TEMPLATE_PREDICTIVE)
    pilot = PredictivePilot(spec=spec)
    obs = _observation(
        enemy_observations=[_sensor(tick=2, distance=3.0, confidence=0.7)],
        current_mode="assault",
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_preemptive_vent_near_redline_spec() -> None:
    """heat >= redline - 5 -> VENT (Task 17 invariant, spec-constructed)."""
    spec = _load_spec(_TEMPLATE_PREDICTIVE)
    pilot = PredictivePilot(spec=spec)
    obs = _observation(
        enemy_observations=[_sensor(tick=2, distance=8.0, confidence=0.7)],
        current_mode="assault",
        boiler=_boiler(pressure=60, heat=76, redline=80, rupture=100),
        weapons=[_weapon(range_=12)],
    )
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.VENT


@pytest.mark.unit
def test_extrapolation_deterministic_spec() -> None:
    """Linear extrapolation produces the same result on repeated calls (spec pilot)."""
    spec = _load_spec(_TEMPLATE_PREDICTIVE)
    pilot = PredictivePilot(spec=spec)
    observations = [
        _sensor(tick=0, distance=30.0, confidence=0.7),
        _sensor(tick=1, distance=25.0, confidence=0.7),
        _sensor(tick=2, distance=20.0, confidence=0.7),
    ]
    obs = _observation(
        enemy_observations=observations,
        current_mode="recon",
        mode_lock_expired=True,
        tick=3,
    )
    a = pilot.decide(obs)
    b = pilot.decide(obs)
    assert a.action == b.action
    assert a.reason_code == b.reason_code


# ---------------------------------------------------------------------------
# Tunable spec behavior tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lower_lock_confidence_floor_fires_at_0_5() -> None:
    """With lock_confidence_floor: 0.45, confidence 0.5 >= 0.45 → FIRE_WEAPON.

    Template holds at confidence 0.5 (0.5 < 0.65).  With floor=0.45, the
    confidence 0.5 is now above the threshold — fires if hit probability also
    clears predicted_hit_floor (0.55).  distance=3, range=12: hit_prob=0.75.
    """
    tuned_spec = ModelSOPilotSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.pilot",
            "id": "pilot.test.predictive_low_confidence",
            "display_name": "Low-Confidence Test",
            "archetype": "predictive",
            "lineage": {"parent": "pilot.template.predictive"},
            "parameters": {
                "lock_confidence_floor": 0.45,
                "predicted_hit_floor": 0.55,
                "preemptive_vent_headroom": 5,
                "regen_pressure_floor": 30,
            },
        }
    )
    tuned_pilot = PredictivePilot(spec=tuned_spec)

    obs = _observation(
        enemy_observations=[_sensor(tick=2, distance=3.0, confidence=0.5)],
        current_mode="assault",
        boiler=_boiler(pressure=60, heat=20),
        weapons=[_weapon(range_=12)],
    )
    decision = tuned_pilot.decide(obs)
    assert decision.action == SOPilotAction.FIRE_WEAPON, (
        f"Expected FIRE_WEAPON with lock_confidence_floor=0.45 and confidence=0.5, "
        f"got {decision.action!r}"
    )


@pytest.mark.unit
def test_regen_pressure_floor_zero_disables_reposition() -> None:
    """With regen_pressure_floor: 0, the pressure-29 no-threat observation no longer
    repositions for regen (pressure_current=29 < 30 → MOVE under template;
    but pressure_current=29 >= 0 → does NOT trigger MOVE under regen_pressure_floor=0).
    """
    tuned_spec = ModelSOPilotSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.pilot",
            "id": "pilot.test.predictive_no_regen",
            "display_name": "No-Regen Test",
            "archetype": "predictive",
            "lineage": {"parent": "pilot.template.predictive"},
            "parameters": {
                "lock_confidence_floor": 0.65,
                "predicted_hit_floor": 0.55,
                "preemptive_vent_headroom": 5,
                "regen_pressure_floor": 0,
            },
        }
    )
    tuned_pilot = PredictivePilot(spec=tuned_spec)

    # pressure=29 < 30, no enemy → template would MOVE, tuned (floor=0) should NOT.
    obs = _observation(
        enemy_observations=[],  # no immediate threat
        current_mode="assault",
        boiler=_boiler(pressure=29, heat=20),
        weapons=[_weapon(range_=12, cooldown=3)],  # weapon on cooldown
    )
    decision = tuned_pilot.decide(obs)
    # With floor=0, pressure(29) >= floor(0) → the regen-MOVE rule does not trigger.
    assert decision.action != SOPilotAction.MOVE, (
        f"Expected no MOVE reposition with regen_pressure_floor=0, got {decision.action!r}"
    )


# ---------------------------------------------------------------------------
# Wrong archetype raises at construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggressive_spec_raises_at_construction() -> None:
    """PredictivePilot(spec=<aggressive spec>) must raise at construction."""
    aggressive_spec = _load_spec(_TEMPLATE_AGGRESSIVE)
    with pytest.raises(ValueError, match="archetype"):
        PredictivePilot(spec=aggressive_spec)


# ---------------------------------------------------------------------------
# Structural introspection: exactly 4 parameters, no extras
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_predictive_params_has_exactly_four_fields() -> None:
    """ModelSOPredictivePilotParams must have exactly the four listed fields."""
    expected_fields = {
        "lock_confidence_floor",
        "predicted_hit_floor",
        "preemptive_vent_headroom",
        "regen_pressure_floor",
    }
    actual_fields = set(ModelSOPredictivePilotParams.model_fields.keys())
    assert actual_fields == expected_fields, (
        f"Expected exactly {expected_fields}, got {actual_fields}"
    )
