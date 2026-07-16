"""Tests for the per-tick initiative ordering mechanic."""

from __future__ import annotations

import pytest

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.match.initiative import initiative_score, order_by_initiative
from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.state import ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition


def _boiler(
    *,
    pressure: int = 30,
    pressure_max: int = 60,
    heat: int = 0,
    redline: int = 80,
    rupture: int = 100,
    status_redline: bool = False,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id="m",
        mech_id="mech.x",
        tick=1,
        pressure_current=pressure,
        pressure_maximum=pressure_max,
        regeneration_per_tick=5,
        heat_current=heat,
        heat_redline_threshold=redline,
        heat_rupture_threshold=rupture,
        heat_vent_rate=5,
        status_redline=status_redline or heat >= redline,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _mech(
    mech_id: str = "mech.a.01",
    *,
    chassis_class: str = "medium",
    pressure: int = 30,
    pressure_max: int = 60,
    heat: int = 0,
    redline: int = 80,
    status_redline: bool = False,
    overloaded: bool = False,
) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id="player.a",
        loadout_id="loadout.x",
        pilot_id="pilot.x",
        chassis_id=f"chassis.{chassis_class}.x",
        chassis_class=chassis_class,  # type: ignore[arg-type]
        base_speed=4,
        position=ModelSOPosition(x=0, y=0),
        facing=0,
        speed=4,
        hp=100,
        hp_max=100,
        armor_value=10,
        armor_max=10,
        current_mode="recon",
        weapon_cooldowns={},
        boiler=_boiler(
            pressure=pressure,
            pressure_max=pressure_max,
            heat=heat,
            redline=redline,
            status_redline=status_redline,
        ),
        overloaded=overloaded,
    )


# ---------------------------------------------------------------------------
# Base initiative: chassis class agility
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lighter_chassis_acts_first() -> None:
    """Light > medium > heavy in base initiative."""
    assert initiative_score(_mech(chassis_class="light")) > initiative_score(
        _mech(chassis_class="medium")
    )
    assert initiative_score(_mech(chassis_class="medium")) > initiative_score(
        _mech(chassis_class="heavy")
    )


# ---------------------------------------------------------------------------
# Boiler modifiers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_high_pressure_grants_bonus() -> None:
    """A boiler at >= 80% pressure acts earlier (responsive reserves)."""
    low = initiative_score(_mech(pressure=20, pressure_max=60))
    high = initiative_score(_mech(pressure=55, pressure_max=60))  # 55/60 = 91%
    assert high > low


@pytest.mark.unit
def test_redline_heat_inflicts_penalty() -> None:
    """A redline-hot boiler fights sluggishly (lower initiative)."""
    cool = initiative_score(_mech(heat=10, status_redline=False))
    hot = initiative_score(_mech(heat=85, redline=80))  # status_redline auto-set
    assert hot < cool


@pytest.mark.unit
def test_overload_inflicts_large_penalty() -> None:
    """An overloaded boiler severely slows the mech."""
    normal = initiative_score(_mech(overloaded=False))
    overloaded = initiative_score(_mech(overloaded=True))
    assert overloaded < normal
    assert normal - overloaded >= 15  # the overload penalty magnitude


# ---------------------------------------------------------------------------
# Ordering + tiebreak determinism
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_order_by_initiative_highest_first() -> None:
    """order_by_initiative returns mechs highest-initiative-first."""
    rng = MatchRng(match_seed=1)
    heavy = _mech("mech.h", chassis_class="heavy")
    light = _mech("mech.l", chassis_class="light")
    ordered = order_by_initiative([heavy, light], rng=rng, tick=1)
    assert ordered[0].mech_id == "mech.l"  # light acts first
    assert ordered[1].mech_id == "mech.h"


@pytest.mark.unit
def test_tiebreak_is_deterministic_for_identical_state() -> None:
    """Two identical-initiative mechs break ties deterministically (same seed/tick)."""
    rng = MatchRng(match_seed=42)
    a = _mech("mech.a.01", chassis_class="medium")
    b = _mech("mech.b.01", chassis_class="medium")
    run1 = order_by_initiative([a, b], rng=rng, tick=5)
    run2 = order_by_initiative([a, b], rng=rng, tick=5)
    assert [m.mech_id for m in run1] == [m.mech_id for m in run2]


@pytest.mark.unit
def test_tiebreak_varies_across_ticks() -> None:
    """The tiebreak sub-seed changes per tick, so equal mechs don't get a fixed order.

    This is the property that removes the first-actor bias: over a match,
    neither side has a systematic advantage from equal-initiative ties.
    """
    rng = MatchRng(match_seed=99)
    a = _mech("mech.a.01", chassis_class="medium")
    b = _mech("mech.b.01", chassis_class="medium")
    orderings = {
        tuple(m.mech_id for m in order_by_initiative([a, b], rng=rng, tick=t)) for t in range(1, 21)
    }
    # Across 20 ticks the tiebreak should produce both orderings at least once.
    assert len(orderings) == 2


@pytest.mark.unit
def test_overloaded_mech_acts_after_healthy_mech() -> None:
    """A medium mech with an overloaded boiler acts after a healthy heavy."""
    rng = MatchRng(match_seed=1)
    healthy_heavy = _mech("mech.hh", chassis_class="heavy")
    overloaded_medium = _mech("mech.om", chassis_class="medium", overloaded=True)
    ordered = order_by_initiative([overloaded_medium, healthy_heavy], rng=rng, tick=1)
    # base: heavy=10, medium=20; overload penalty 15 -> medium scores 5 < heavy 10.
    assert ordered[0].mech_id == "mech.hh"
