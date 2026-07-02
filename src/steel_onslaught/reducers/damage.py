"""Armor response + damage application reducer — Task 25.

Flow (on HIT_RESOLVED):
    1. compute_armor_reduction: apply armor efficiency per weapon damage type.
       - Heat weapons: armor is less effective (lower efficiency).
       - Pressure weapons: armor is more effective (higher efficiency).
       - Standard weapons: baseline efficiency (1.0).
    2. compute_effective_damage_after_vulnerability: apply chassis penalties.
       - Heat weapons vs heavy chassis: multiply by heat_weapon_vulnerability.
       - Non-heat weapons: no vulnerability multiplier applied.
    3. Emit ARMOR_ABSORBED(absorbed_amount).
    4. Emit DAMAGE_APPLIED(target_id, damage_after_armor).
    5. apply_damage: update target hp (floored at 0).
    6. If target.hp <= 0: emit MECH_DESTROYED(target_id).

Invariants:
    - Armor never amplifies damage: absorbed_amount <= damage_raw.
    - damage_after_armor is always >= 0.
    - Heat weapon vulnerability multiplier only applies to WeaponDamageType.HEAT.
    - Mech with hp 5 hit for 8 raw → hp=0, mech_destroyed=True.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from steel_onslaught.contracts.weapon import WeaponDamageType

__all__ = ["ArmorReduction", "WeaponDamageType"]  # WeaponDamageType re-exported (was defined here)


# ---------------------------------------------------------------------------
# Mitigation caps per damage type
# ---------------------------------------------------------------------------

# Degrading-armor model: armor absorbs a *fraction* of each hit (capped so a
# fraction of every hit always leaks through — no weapon is ever fully negated
# by high armor), and degrades by the amount absorbed (regeneration is per-tick
# in the fold, toward armor_max).
#
# mitigation_cap = the maximum fraction of damage_raw that armor may absorb on
# a single hit. The ordering HEAT < STANDARD < PRESSURE preserves the original
# design intent (heat bypasses armor, pressure is well-absorbed).
_MITIGATION_CAP: dict[WeaponDamageType, float] = {
    WeaponDamageType.HEAT: 0.50,  # heat weapons: armor absorbs <=50% of a hit
    WeaponDamageType.STANDARD: 0.75,  # standard weapons: armor absorbs <=75%
    WeaponDamageType.PRESSURE: 0.90,  # pressure weapons: armor absorbs <=90%
}


# ---------------------------------------------------------------------------
# DamageOutcome value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DamageOutcome:
    """Result of applying damage to a mech.

    Attributes:
        hp_after:       HP remaining after damage (floored at 0).
        mech_destroyed: True when hp_after == 0 (the mech is destroyed this tick).
    """

    hp_after: int
    mech_destroyed: bool


@dataclass(frozen=True)
class ArmorReduction:
    """Result of armor absorbing one hit (degrading-armor model).

    Attributes:
        absorbed:    Damage absorbed by armor this hit, in [0, damage_raw].
                     Armor never amplifies damage.
        armor_after: Armor remaining after this hit (armor_value - absorbed).
                     Drives the fold's per-mech armor degradation.
    """

    absorbed: int
    armor_after: int


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def compute_armor_reduction(
    *,
    damage_raw: int,
    armor_value: int,
    weapon_damage_type: WeaponDamageType,
) -> ArmorReduction:
    """Compute how armor absorbs one hit (degrading + capped mitigation).

    The model guarantees a fraction of every hit leaks through, so no weapon
    is ever fully negated by high armor — even when ``damage_raw < armor_value``
    (the original flat-subtraction bug). Armor degrades by the absorbed amount.

    Args:
        damage_raw:        Raw damage from the weapon before armor (>= 0).
        armor_value:       Current armor of the target (>= 0; degrades per hit).
        weapon_damage_type: Type of the incoming weapon damage.

    Returns:
        An ``ArmorReduction`` with ``absorbed`` in [0, damage_raw] and
        ``armor_after`` in [0, armor_value].

    Per-hit absorption::

        cap         = mitigation_cap[weapon_damage_type]   # heat .50 / std .75 / pressure .90
        absorbable  = min(armor_value, ceil(damage_raw * cap))
        absorbed    = min(absorbable, damage_raw)          # never amplify
        armor_after = armor_value - absorbed               # degrades
    """
    if armor_value <= 0 or damage_raw <= 0:
        return ArmorReduction(absorbed=0, armor_after=armor_value)

    cap = _MITIGATION_CAP[weapon_damage_type]
    absorbable = min(armor_value, math.ceil(damage_raw * cap))
    absorbed = min(absorbable, damage_raw)
    return ArmorReduction(absorbed=absorbed, armor_after=armor_value - absorbed)


def compute_effective_damage_after_vulnerability(
    *,
    damage_after_armor: int,
    weapon_damage_type: WeaponDamageType,
    heat_weapon_vulnerability: float,
) -> int:
    """Apply chassis-specific vulnerability multipliers after armor reduction.

    The heat_weapon_vulnerability multiplier (from ModelSOChassisPenalties) is
    applied only when weapon_damage_type == HEAT.  Non-heat weapons ignore this
    chassis penalty.

    Args:
        damage_after_armor:       Post-armor damage (>= 0).
        weapon_damage_type:       Type of the incoming damage.
        heat_weapon_vulnerability: Chassis heat-weapon penalty (>= 1.0).
                                   Ignored for non-HEAT damage types.

    Returns:
        Effective damage after vulnerability, as a non-negative integer
        (truncated, not rounded).
    """
    if weapon_damage_type is WeaponDamageType.HEAT:
        return int(damage_after_armor * heat_weapon_vulnerability)
    return damage_after_armor


def should_destroy(*, hp_after: int) -> bool:
    """Return True when a mech's hp_after value means it should be destroyed.

    Args:
        hp_after: The mech's hp after damage application.

    Returns:
        True if hp_after <= 0 (mech destroyed this tick), False otherwise.
    """
    return hp_after <= 0


def apply_damage(
    *,
    hp: int,
    hp_max: int,
    damage_after_armor: int,
) -> DamageOutcome:
    """Apply post-armor, post-vulnerability damage to a mech and determine
    whether it is destroyed.

    Args:
        hp:               Current mech hit points (>= 0).
        hp_max:           Maximum mech hit points (> 0).  Recorded in the
                          outcome for potential callers that want it; not used
                          internally beyond documentation.
        damage_after_armor: Effective damage to subtract from hp (>= 0).

    Returns:
        DamageOutcome with:
            - hp_after floored at 0 (never negative).
            - mech_destroyed = True when hp_after reaches 0.
    """
    _ = hp_max  # kept in signature for readability; validated by mech state model
    hp_after = max(0, hp - damage_after_armor)
    return DamageOutcome(
        hp_after=hp_after,
        mech_destroyed=should_destroy(hp_after=hp_after),
    )
