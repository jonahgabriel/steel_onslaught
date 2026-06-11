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

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Weapon damage type enum
# ---------------------------------------------------------------------------


class WeaponDamageType(StrEnum):
    """Damage type classification used to determine armor effectiveness.

    - STANDARD: baseline armor efficiency (1.0 multiplier).
    - HEAT: armor is less effective (lower efficiency coefficient).
    - PRESSURE: armor is more effective (higher efficiency coefficient).
    """

    STANDARD = "standard"
    HEAT = "heat"
    PRESSURE = "pressure"


# ---------------------------------------------------------------------------
# Armor efficiency coefficients per damage type
# ---------------------------------------------------------------------------

# Armor efficiency is the fraction of armor_value that is subtracted from
# damage_raw. The effective absorbed amount is:
#   absorbed = min(damage_raw, armor_value * efficiency)
#
# STANDARD: full armor value applies.
# HEAT: armor is bypassed more → lower efficiency (armor is less effective).
# PRESSURE: armor is especially effective → higher efficiency.
_ARMOR_EFFICIENCY: dict[WeaponDamageType, float] = {
    WeaponDamageType.STANDARD: 1.0,
    WeaponDamageType.HEAT: 0.5,  # heat weapons bypass armor
    WeaponDamageType.PRESSURE: 1.5,  # pressure weapons are absorbed well
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


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def compute_armor_reduction(
    *,
    damage_raw: int,
    armor_value: int,
    weapon_damage_type: WeaponDamageType,
) -> int:
    """Compute how many hit points of damage the armor absorbs.

    Args:
        damage_raw:        Raw damage from the weapon before armor.
        armor_value:       Mech armor stat (0 = unarmoured).
        weapon_damage_type: Type of the incoming weapon damage.

    Returns:
        Absorbed damage in [0, damage_raw].  The result is always non-negative
        and never exceeds damage_raw (armor cannot amplify damage).

    The effective armor absorption is:
        absorbed = min(damage_raw, floor(armor_value * efficiency))

    where efficiency depends on weapon_damage_type:
        - STANDARD: 1.0  (full armor value)
        - HEAT:     0.5  (armor less effective against heat weapons)
        - PRESSURE: 1.5  (armor very effective against pressure weapons)
    """
    if armor_value <= 0:
        return 0

    efficiency = _ARMOR_EFFICIENCY[weapon_damage_type]
    # Clamp efficiency so armor_value * efficiency never exceeds damage_raw
    # (the floor call keeps the result an integer).
    absorbed_raw = armor_value * efficiency
    absorbed = int(absorbed_raw)  # floor

    # Armor can absorb at most damage_raw (no amplification).
    return min(absorbed, damage_raw)


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
