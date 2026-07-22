"""Tests for the aggressive pilot heuristic — Task 15 (updated for spec-driven: Task 2).

Invariants (from the plan):
1. Given enemy in range + ready weapon + pressure: returns FIRE_WEAPON with the
   highest-damage option.
2. Given heat 92 of rupture 100 and enemy in range: still fires (tolerates redline).
3. Given heat 96 of rupture 100: vents (close to rupture, within rupture_threshold - 5).
4. Given mode=recon + assault available + enemy in range: switches to assault before
   firing.
5. Given multiple weapons of same damage: deterministically picks the lowest-id
   alphabetically (no random tiebreaker).

All tests now construct AggressivePilot from the canonical template spec so the
spec-wiring is exercised alongside every behavioural invariant.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.pilot import (
    ModelSOPilotSpec,
)
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.schemas import (
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    SOPilotAction,
)

_TEMPLATE_YAML = (
    Path(__file__).parent.parent.parent / "contracts_data" / "pilots" / "template_aggressive.yaml"
)


def _load_template_spec() -> ModelSOPilotSpec:
    return ModelSOPilotSpec.model_validate(yaml.safe_load(_TEMPLATE_YAML.read_text()))


# Module-level spec for all existing tests (avoids repeating the load).
_TEMPLATE_SPEC: ModelSOPilotSpec = _load_template_spec()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUPTURE_THRESHOLD = 100
REDLINE_THRESHOLD = 80


def _boiler(
    pressure: int = 50,
    heat: int = 30,
    redline: int = REDLINE_THRESHOLD,
    rupture: int = RUPTURE_THRESHOLD,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        schema_version="0.1.0",
        kind="steel_onslaught.boiler_state",
        match_id="match.test",
        mech_id="mech.red.01",
        tick=1,
        pressure_current=pressure,
        pressure_maximum=100,
        regeneration_per_tick=3,
        heat_current=heat,
        heat_redline_threshold=redline,
        heat_capacity=rupture,
        heat_rupture_threshold=rupture,
        heat_vent_rate=5,
        status_redline=(heat >= redline),
        status_rupture_warning=(heat >= rupture - 10),
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=0.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _weapon(
    weapon_id: str,
    damage: int = 15,
    rng: int = 20,
    pressure_cost: int = 10,
    heat_generated: int = 5,
    cooldown: int = 0,
) -> ModelSOPilotWeaponView:
    return ModelSOPilotWeaponView(
        weapon_id=weapon_id,
        damage=damage,
        range=rng,
        pressure_cost=pressure_cost,
        heat_generated=heat_generated,
        cooldown_remaining_ticks=cooldown,
    )


def _observation(
    boiler: ModelSOBoilerState | None = None,
    weapons: list[ModelSOPilotWeaponView] | None = None,
    current_mode: str = "assault",
    mode_lock_expired: bool = True,
    enemy_distance: float = 10.0,
    enemy_confidence: float = 0.9,
    hp_percent: float = 100.0,
    under_sensor_lock: bool = False,
) -> ModelSOPilotObservation:
    return ModelSOPilotObservation(
        match_id="match.test",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=1,
        match_elapsed_ticks=5,
        boiler=boiler if boiler is not None else _boiler(),
        weapons=weapons if weapons is not None else [_weapon("weapon.machinegun")],
        current_mode=ModeId(current_mode),
        mode_lock_expired=mode_lock_expired,
        position=ModelSOPosition(x=0, y=0),
        hp_percent=hp_percent,
        under_sensor_lock=under_sensor_lock,
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id="mech.blue.01",
                tick=1,
                distance_estimate=enemy_distance,
                confidence=enemy_confidence,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fires_highest_damage_weapon_when_enemy_in_range() -> None:
    """Given enemy in range + ready weapon + sufficient pressure → FIRE_WEAPON."""
    weapons = [
        _weapon("weapon.cannon", damage=30, rng=20, pressure_cost=10),
        _weapon("weapon.machinegun", damage=10, rng=20, pressure_cost=5),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=15.0,  # within range (both have rng=20)
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.FIRE_WEAPON
    assert decision.action_params["weapon_id"] == "weapon.cannon"


@pytest.mark.unit
def test_still_fires_when_heat_at_redline_but_below_rupture_minus_5() -> None:
    """Given heat 92 of rupture 100 (within redline, above 90) — still fires.

    Tolerates redline up to heat == rupture_threshold - 5 (rule 5 from plan).
    heat=92, rupture=100, rupture-5=95 → 92 < 95 → fire is still allowed.
    """
    obs = _observation(
        boiler=_boiler(pressure=50, heat=92, redline=80, rupture=100),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_vents_when_heat_near_rupture_threshold() -> None:
    """Given heat 96 of rupture 100: VENT (close to rupture, >= rupture_threshold - 5)."""
    obs = _observation(
        boiler=_boiler(pressure=50, heat=96, redline=80, rupture=100),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.VENT


@pytest.mark.unit
def test_vents_when_heat_at_rupture_minus_5_boundary() -> None:
    """heat == rupture_threshold - 5 is the exact boundary — should VENT."""
    obs = _observation(
        boiler=_boiler(pressure=50, heat=95, redline=80, rupture=100),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.VENT


@pytest.mark.unit
def test_switches_to_assault_before_firing_when_in_recon_mode() -> None:
    """Given mode=recon + mode_lock_expired + pressure≥12 + heat≤80 → SWITCH_MODE assault."""
    obs = _observation(
        boiler=_boiler(pressure=50, heat=40, redline=80, rupture=100),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="recon",
        mode_lock_expired=True,
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.SWITCH_MODE
    assert decision.action_params.get("target_mode") == "assault"


@pytest.mark.unit
def test_does_not_switch_mode_when_lock_not_expired() -> None:
    """If mode_lock_expired=False, cannot switch mode — should fire instead."""
    obs = _observation(
        boiler=_boiler(pressure=50, heat=40),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="recon",
        mode_lock_expired=False,  # cannot switch
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    # Can't switch mode, enemy in range with ready weapon: fires
    assert decision.action == SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_does_not_switch_mode_when_pressure_too_low() -> None:
    """If pressure < 12, mode switch condition not satisfied — fire instead."""
    obs = _observation(
        boiler=_boiler(pressure=11, heat=40),  # just below the 12 threshold
        weapons=[_weapon("weapon.cannon", damage=30, rng=20, pressure_cost=5)],
        current_mode="recon",
        mode_lock_expired=True,
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    # pressure < 12 → can't switch mode; but weapon pressure_cost=5 ≤ 11 → fires
    assert decision.action == SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_picks_alphabetically_lowest_id_on_damage_tie() -> None:
    """Multiple weapons of same damage → deterministically picks lowest-id alphabetically."""
    weapons = [
        _weapon("weapon.zapper", damage=20, rng=20, pressure_cost=8),
        _weapon("weapon.cannon", damage=20, rng=20, pressure_cost=8),
        _weapon("weapon.blaster", damage=20, rng=20, pressure_cost=8),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.FIRE_WEAPON
    assert decision.action_params["weapon_id"] == "weapon.blaster"


@pytest.mark.unit
def test_moves_toward_enemy_when_no_weapon_in_range() -> None:
    """Enemy out of all weapon ranges → MOVE toward enemy."""
    weapons = [
        _weapon("weapon.cannon", damage=30, rng=10, pressure_cost=8),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=50.0,  # far out of range (rng=10)
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.MOVE


@pytest.mark.unit
def test_moves_when_no_weapons_ready() -> None:
    """All weapons on cooldown → MOVE (no fire possible)."""
    weapons = [
        _weapon("weapon.cannon", damage=30, rng=20, cooldown=3),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.MOVE


@pytest.mark.unit
def test_moves_when_pressure_insufficient_for_any_weapon() -> None:
    """Pressure too low for any weapon → MOVE."""
    weapons = [
        _weapon("weapon.cannon", damage=30, rng=20, pressure_cost=50),
    ]
    obs = _observation(
        boiler=_boiler(pressure=10, heat=30),  # can't afford weapon (cost=50)
        weapons=weapons,
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.MOVE


@pytest.mark.unit
def test_vents_when_heat_above_90_even_without_enemy() -> None:
    """Given heat >= 90 and no enemy in range: VENT (rule 3 from plan)."""
    weapons = [
        _weapon("weapon.cannon", damage=30, rng=10),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=91, redline=80, rupture=100),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=100.0,  # out of range
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action == SOPilotAction.VENT


@pytest.mark.unit
def test_decision_contains_chosen_action_in_considered() -> None:
    """The considered_actions list must include the chosen action (schema invariant)."""
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=[_weapon("weapon.cannon")],
        current_mode="assault",
        enemy_distance=10.0,
    )
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)

    assert decision.action in {ca.action for ca in decision.considered_actions}


@pytest.mark.unit
def test_is_protocol_compliant() -> None:
    """AggressivePilot must satisfy PilotProtocol (runtime_checkable)."""
    from steel_onslaught.pilots.schemas import PilotProtocol

    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    assert isinstance(pilot, PilotProtocol)


@pytest.mark.unit
def test_returns_model_so_pilot_decision_type() -> None:
    """The return type is strictly ModelSOPilotDecision."""
    obs = _observation()
    pilot = AggressivePilot(spec=_TEMPLATE_SPEC)
    decision = pilot.decide(obs)
    assert isinstance(decision, ModelSOPilotDecision)


# ---------------------------------------------------------------------------
# Task 2 spec-driven invariants
# ---------------------------------------------------------------------------


def _make_spec(
    vent_at_heat_margin: int = 5,
    idle_vent_heat_threshold: int = 90,
    mode_switch_pressure_floor: int = 12,
    mode_switch_heat_ceiling: int = 80,
    weapon_preference: str = "highest_damage",
) -> ModelSOPilotSpec:
    """Construct a custom aggressive spec for tuning tests."""
    from steel_onslaught.contracts.pilot import (
        ModelSOAggressivePilotParams,
        ModelSOPilotLineage,
        SOWeaponPreference,
    )

    return ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id="pilot.test.aggressive",
        display_name="Test Aggressive",
        archetype="aggressive",
        lineage=ModelSOPilotLineage(parent="pilot.template.aggressive"),
        parameters=ModelSOAggressivePilotParams(
            vent_at_heat_margin=vent_at_heat_margin,
            idle_vent_heat_threshold=idle_vent_heat_threshold,
            mode_switch_pressure_floor=mode_switch_pressure_floor,
            mode_switch_heat_ceiling=mode_switch_heat_ceiling,
            weapon_preference=SOWeaponPreference(weapon_preference),
        ),
    )


@pytest.mark.unit
def test_wrong_archetype_raises_at_construction() -> None:
    """AggressivePilot(spec=<defensive spec>) must raise ValueError at construction."""
    from steel_onslaught.contracts.pilot import (
        ModelSODefensivePilotParams,
        ModelSOPilotLineage,
    )

    defensive_spec = ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id="pilot.test.defensive",
        display_name="Test Defensive",
        archetype="defensive",
        lineage=ModelSOPilotLineage(parent=None),
        parameters=ModelSODefensivePilotParams(
            vent_headroom_below_redline=8,
            fire_confidence_floor=0.7,
            fire_heat_headroom=12,
            disengage_hp_pct=30,
        ),
    )
    with pytest.raises(ValueError, match="aggressive"):
        AggressivePilot(spec=defensive_spec)


@pytest.mark.unit
def test_tuned_vent_margin_2_fires_at_heat_96() -> None:
    """With vent_at_heat_margin=2, pilot fires at heat 96/rupture 100 (template would vent).

    Template: rupture - 5 = 95 → heat 96 >= 95 → VENT.
    Tuned:    rupture - 2 = 98 → heat 96 < 98  → allowed to fire.
    """
    spec = _make_spec(vent_at_heat_margin=2)
    pilot = AggressivePilot(spec=spec)
    obs = _observation(
        boiler=_boiler(pressure=50, heat=96, redline=80, rupture=100),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="assault",
        enemy_distance=10.0,
    )
    assert pilot.decide(obs).action == SOPilotAction.FIRE_WEAPON


@pytest.mark.unit
def test_tuned_vent_margin_2_vents_at_heat_99() -> None:
    """With vent_at_heat_margin=2, pilot vents at heat 99/rupture 100 (rupture - 2 = 98)."""
    spec = _make_spec(vent_at_heat_margin=2)
    pilot = AggressivePilot(spec=spec)
    obs = _observation(
        boiler=_boiler(pressure=50, heat=99, redline=80, rupture=100),
        weapons=[_weapon("weapon.cannon", damage=30, rng=20)],
        current_mode="assault",
        enemy_distance=10.0,
    )
    assert pilot.decide(obs).action == SOPilotAction.VENT


@pytest.mark.unit
def test_lowest_heat_preference_fires_cooler_weapon() -> None:
    """With weapon_preference=lowest_heat, pilot fires the cooler weapon."""
    spec = _make_spec(weapon_preference="lowest_heat")
    pilot = AggressivePilot(spec=spec)
    weapons = [
        _weapon("weapon.alpha", damage=20, rng=20, pressure_cost=8, heat_generated=10),
        _weapon("weapon.beta", damage=20, rng=20, pressure_cost=8, heat_generated=3),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=10.0,
    )
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.FIRE_WEAPON
    # weapon.beta has lower heat_generated (3 < 10)
    assert decision.action_params["weapon_id"] == "weapon.beta"


@pytest.mark.unit
def test_lowest_heat_preference_lowest_id_tiebreak() -> None:
    """With weapon_preference=lowest_heat and equal heat, picks lowest weapon_id."""
    spec = _make_spec(weapon_preference="lowest_heat")
    pilot = AggressivePilot(spec=spec)
    weapons = [
        _weapon("weapon.zapper", damage=20, rng=20, pressure_cost=8, heat_generated=5),
        _weapon("weapon.alpha", damage=20, rng=20, pressure_cost=8, heat_generated=5),
    ]
    obs = _observation(
        boiler=_boiler(pressure=50, heat=30),
        weapons=weapons,
        current_mode="assault",
        enemy_distance=10.0,
    )
    decision = pilot.decide(obs)
    assert decision.action == SOPilotAction.FIRE_WEAPON
    # Equal heat — tiebreak is lowest weapon_id alphabetically
    assert decision.action_params["weapon_id"] == "weapon.alpha"
