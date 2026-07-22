"""Deterministic observation battery — shared by Tasks 2-4 golden tests.

Generates a deterministic list[ModelSOPilotObservation] that crosses every
rule boundary in all three pilot archetypes.  Generation is fully
order-independent: no set iteration, no dict-order reliance, no hash seeds.

Structure: for each boiler spec, a cartesian product over heat values and a
compact set of behavioral axes.  Axes are sized to keep the total in the low
thousands (fast to generate and replay).  Every decision boundary in the
three archetypes has at least two observations straddling it.

Boiler specs inline — no YAML dependency.
Do NOT mutate the returned list.
"""

from __future__ import annotations

from itertools import product
from typing import NamedTuple

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
)

# ---------------------------------------------------------------------------
# Boiler spec: (tag, redline, rupture, max_pressure)
# ---------------------------------------------------------------------------


class _BoilerSpec(NamedTuple):
    tag: str
    redline: int
    rupture: int
    max_pressure: int


_BOILER_SPECS: list[_BoilerSpec] = [
    _BoilerSpec("compact", 65, 80, 50),  # compact_v1
    _BoilerSpec("bessemer", 80, 100, 90),  # industrial_bessemer_90
    _BoilerSpec("volatile", 60, 85, 75),  # volatile_v1
]

# ---------------------------------------------------------------------------
# Per-boiler heat values: straddle every archetype boundary.
# ---------------------------------------------------------------------------


def _heat_values_for(spec: _BoilerSpec) -> list[int]:
    """Sorted heat values straddling all archetype decision boundaries.

    Two values per boundary (just below / at boundary) to cover both sides
    of each conditional.
    """
    r, u = spec.redline, spec.rupture
    candidates = {
        0,
        40,
        r - 13,
        r - 12,  # defensive fire-headroom (redline - 12)
        r - 9,
        r - 8,  # defensive vent (redline - 8)
        r - 6,
        r - 5,  # predictive preemptive-vent (redline - 5)
        79,
        80,  # aggressive mode-switch ceiling (fixed ≤80)
        89,
        90,  # aggressive idle-vent (fixed ≥90)
        u - 6,
        u - 5,  # aggressive rupture-guard (rupture - 5)
        u,  # at rupture
    }
    return sorted(v for v in candidates if 0 <= v <= u)


# ---------------------------------------------------------------------------
# Compact fixed axes
# ---------------------------------------------------------------------------

# Pressure: below mode-switch floor (12), at floor, well above.
_PRESSURE_VALUES: list[int] = [0, 12, 50]

# (mode, mode_lock_expired): covers mode-switch preconditions.
_MODES: list[tuple[str, bool]] = [
    ("recon", True),  # mode-switch available, not in assault
    ("assault", True),  # already in assault
    ("evasion", False),  # mode-lock held
]

# Enemy distance: in-range (8) and out-of-range (20); weapon range = 10.
_ENEMY_DISTANCES: list[float] = [8.0, 20.0]

# Lock confidence: below defensive threshold (0.7), at threshold, above.
_LOCK_CONFIDENCES: list[float] = [0.4, 0.7, 0.8]

# hp_percent: below disengage threshold (30) and above.
_HP_PERCENTS: list[float] = [25.0, 100.0]

# Sensor lock (affects defensive rule 2).
_UNDER_LOCK_VALUES: list[bool] = [False, True]

# Weapon sets: none-ready, one-ready, two-equal-damage, two-unequal-damage.
# Row: (weapon_id, damage, range, pressure_cost, heat_generated, cooldown).
_WeaponRow = tuple[str, int, int, int, int, int]
_WEAPON_SETS: list[tuple[_WeaponRow, ...]] = [
    (("weapon.alpha", 15, 10, 8, 10, 3),),  # none ready
    (("weapon.alpha", 15, 10, 8, 10, 0),),  # one ready
    (("weapon.alpha", 15, 10, 8, 10, 0), ("weapon.beta", 15, 10, 8, 6, 0)),  # equal dmg
    (("weapon.alpha", 20, 10, 8, 12, 0), ("weapon.beta", 12, 10, 8, 6, 0)),  # unequal dmg
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_boiler(spec: _BoilerSpec, heat: int, pressure: int) -> ModelSOBoilerState:
    p = min(pressure, spec.max_pressure)
    return ModelSOBoilerState(
        match_id="battery",
        mech_id="mech-x",
        tick=1,
        pressure_current=p,
        pressure_maximum=spec.max_pressure,
        regeneration_per_tick=5,
        heat_current=heat,
        heat_redline_threshold=spec.redline,
        heat_capacity=spec.rupture,
        heat_rupture_threshold=spec.rupture,
        heat_vent_rate=5,
        status_redline=heat >= spec.redline,
        status_rupture_warning=heat >= (spec.rupture - 10),
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _make_weapons(rows: tuple[_WeaponRow, ...]) -> list[ModelSOPilotWeaponView]:
    return [
        ModelSOPilotWeaponView(
            weapon_id=wid,
            damage=dmg,
            range=rng,
            pressure_cost=pc,
            heat_generated=hg,
            cooldown_remaining_ticks=cd,
        )
        for wid, dmg, rng, pc, hg, cd in rows
    ]


def _make_reading(distance: float, confidence: float) -> ModelSOSensorReading:
    return ModelSOSensorReading(
        enemy_mech_id="mech-enemy",
        tick=1,
        distance_estimate=distance,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Battery constructor
# ---------------------------------------------------------------------------


def observation_battery() -> list[ModelSOPilotObservation]:
    """Return the full deterministic observation battery.

    Outer loop: boiler specs in declaration order.
    Inner loop: cartesian product of all axis lists in declaration order.
    No set/dict/hash traversal.

    Target size: ~3 x (14 heat) x 3 x 3 x 4 x 2 x 3 x 2 x 2 ≈ 18 000.
    All decision boundaries in all three archetypes are straddled.
    """
    battery: list[ModelSOPilotObservation] = []

    for spec in _BOILER_SPECS:
        for (
            heat,
            pressure,
            (mode, mode_lock_expired),
            weapon_rows,
            enemy_distance,
            lock_confidence,
            hp_percent,
            under_sensor_lock,
        ) in product(
            _heat_values_for(spec),
            _PRESSURE_VALUES,
            _MODES,
            _WEAPON_SETS,
            _ENEMY_DISTANCES,
            _LOCK_CONFIDENCES,
            _HP_PERCENTS,
            _UNDER_LOCK_VALUES,
        ):
            battery.append(
                ModelSOPilotObservation(
                    match_id="battery",
                    mech_id="mech-x",
                    player_id="player-x",
                    tick=1,
                    match_elapsed_ticks=1,
                    boiler=_make_boiler(spec, heat, pressure),
                    weapons=_make_weapons(weapon_rows),
                    current_mode=ModeId(mode),
                    mode_lock_expired=mode_lock_expired,
                    position=ModelSOPosition(x=0, y=0),
                    hp_percent=hp_percent,
                    under_sensor_lock=under_sensor_lock,
                    enemy_observations=[_make_reading(enemy_distance, lock_confidence)],
                )
            )

    return battery
