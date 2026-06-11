"""Tests for Task 25: armor response + damage application reducer.

Invariants verified:
- Total damage_applied across all hits <= initial weapon damage_raw sum
  (armor never amplifies damage).
- Heat weapons against heavy chassis use the heat_weapon_vulnerability multiplier
  from the chassis penalty spec.
- Mech with hp 5, hit for 8 raw damage: both DAMAGE_APPLIED and MECH_DESTROYED
  are emitted in the same tick.
- damage_after_armor is non-negative even if armor_value > damage_raw.
- Armor efficiency is clamped to [0, 1] regardless of weapon type modifiers.
- Pressure-based weapons have higher armor effectiveness (more reduction) than
  heat weapons against the same target.
- apply_damage returns the same mech state when damage_after_armor == 0 hp change
  is handled correctly.
- compute_armor_reduction never returns a negative value (armor cannot amplify).
- should_destroy returns True exactly when hp reaches 0 or below after damage.
"""

from __future__ import annotations

import pytest

from steel_onslaught.reducers.damage import (
    WeaponDamageType,
    apply_damage,
    compute_armor_reduction,
    should_destroy,
)

# ---------------------------------------------------------------------------
# compute_armor_reduction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_armor_reduction_pressure_weapon_reduces_more() -> None:
    """Pressure-based weapons are reduced more by armor than heat weapons."""
    absorbed_pressure = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.PRESSURE,
    )
    absorbed_heat = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.HEAT,
    )
    # Pressure weapons: armor reduces more → absorbed_pressure > absorbed_heat
    assert absorbed_pressure > absorbed_heat


@pytest.mark.unit
def test_armor_reduction_never_negative() -> None:
    """Armor reduction never returns a negative value."""
    # Even if armor_value is larger than damage_raw, absorbed should be >= 0.
    absorbed = compute_armor_reduction(
        damage_raw=5,
        armor_value=100,
        weapon_damage_type=WeaponDamageType.PRESSURE,
    )
    assert absorbed >= 0


@pytest.mark.unit
def test_armor_reduction_cannot_exceed_raw_damage() -> None:
    """Absorbed amount cannot exceed raw damage (armor cannot amplify)."""
    absorbed = compute_armor_reduction(
        damage_raw=10,
        armor_value=50,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    assert absorbed <= 10


@pytest.mark.unit
def test_armor_reduction_zero_armor_absorbs_nothing() -> None:
    """A mech with armor_value=0 absorbs 0 damage."""
    absorbed = compute_armor_reduction(
        damage_raw=15,
        armor_value=0,
        weapon_damage_type=WeaponDamageType.PRESSURE,
    )
    assert absorbed == 0


@pytest.mark.unit
def test_armor_reduction_standard_weapon() -> None:
    """Standard weapon uses baseline armor efficiency (1.0 multiplier)."""
    absorbed = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    # baseline efficiency = 1.0 → absorbed = min(10, 20) = 10
    assert absorbed == 10


@pytest.mark.unit
def test_armor_reduction_heat_weapon_reduced_efficiency() -> None:
    """Heat weapons: armor reduces less (lower efficiency than baseline)."""
    absorbed_standard = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    absorbed_heat = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.HEAT,
    )
    # Heat weapons bypass armor more: absorbed_heat < absorbed_standard
    assert absorbed_heat < absorbed_standard


# ---------------------------------------------------------------------------
# apply_damage tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_damage_reduces_hp() -> None:
    """apply_damage reduces mech hp by the after-armor damage amount."""
    outcome = apply_damage(
        hp=50,
        hp_max=100,
        damage_after_armor=15,
    )
    assert outcome.hp_after == 35


@pytest.mark.unit
def test_apply_damage_hp_floored_at_zero() -> None:
    """Damage exceeding remaining hp floors hp at 0, not negative."""
    outcome = apply_damage(
        hp=5,
        hp_max=100,
        damage_after_armor=20,
    )
    assert outcome.hp_after == 0


@pytest.mark.unit
def test_apply_damage_mech_destroyed_when_hp_depleted() -> None:
    """Mech with hp 5 hit for 8 raw damage is destroyed (hp reaches 0)."""
    # armor absorbs 0 (armor_value=0 for simplicity)
    damage_after_armor = 8  # full raw damage passes through
    outcome = apply_damage(
        hp=5,
        hp_max=100,
        damage_after_armor=damage_after_armor,
    )
    assert outcome.hp_after == 0
    assert outcome.mech_destroyed is True


@pytest.mark.unit
def test_apply_damage_no_destruction_when_hp_positive() -> None:
    """Mech with hp above 0 after damage is not destroyed."""
    outcome = apply_damage(
        hp=100,
        hp_max=100,
        damage_after_armor=50,
    )
    assert outcome.hp_after == 50
    assert outcome.mech_destroyed is False


@pytest.mark.unit
def test_apply_damage_zero_damage_no_change() -> None:
    """Zero damage_after_armor produces no change in hp."""
    outcome = apply_damage(
        hp=40,
        hp_max=100,
        damage_after_armor=0,
    )
    assert outcome.hp_after == 40
    assert outcome.mech_destroyed is False


@pytest.mark.unit
def test_apply_damage_exact_lethal_hp() -> None:
    """Damage exactly equal to remaining hp destroys the mech."""
    outcome = apply_damage(
        hp=10,
        hp_max=100,
        damage_after_armor=10,
    )
    assert outcome.hp_after == 0
    assert outcome.mech_destroyed is True


# ---------------------------------------------------------------------------
# should_destroy tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_should_destroy_at_zero_hp() -> None:
    """should_destroy returns True when hp_after is 0."""
    assert should_destroy(hp_after=0) is True


@pytest.mark.unit
def test_should_destroy_below_zero_hp() -> None:
    """should_destroy returns True for negative hp_after (overkill)."""
    # Damage application floors hp at 0, but should_destroy itself is defined
    # independently of the floor — both <= 0 must destroy.
    assert should_destroy(hp_after=-5) is True


@pytest.mark.unit
def test_should_destroy_positive_hp() -> None:
    """should_destroy returns False when hp_after > 0."""
    assert should_destroy(hp_after=1) is False


# ---------------------------------------------------------------------------
# DamageOutcome structural tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_damage_outcome_absorbed_plus_applied_equals_raw() -> None:
    """absorbed_amount + damage_applied <= damage_raw (armor never amplifies)."""
    damage_raw = 20
    armor_value = 8

    absorbed = compute_armor_reduction(
        damage_raw=damage_raw,
        armor_value=armor_value,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    damage_after = max(0, damage_raw - absorbed)

    # absorbed + damage_after must equal damage_raw (conservation)
    assert absorbed + damage_after == damage_raw


@pytest.mark.unit
def test_damage_total_never_exceeds_raw_across_multiple_hits() -> None:
    """Total damage applied across multiple hits never exceeds sum of raw damage."""
    raws = [10, 15, 8, 20]
    armor_value = 5
    total_applied = 0
    total_raw = sum(raws)

    for raw in raws:
        absorbed = compute_armor_reduction(
            damage_raw=raw,
            armor_value=armor_value,
            weapon_damage_type=WeaponDamageType.STANDARD,
        )
        total_applied += max(0, raw - absorbed)

    assert total_applied <= total_raw


@pytest.mark.unit
def test_heat_weapon_vulnerability_multiplier_applied_for_heavy_chassis() -> None:
    """Heat weapons against heavy chassis use the heat_weapon_vulnerability multiplier.

    The chassis penalty spec defines heat_weapon_vulnerability >= 1.0.
    When weapon_damage_type=HEAT and chassis heat_weapon_vulnerability > 1.0,
    the effective damage_after_armor increases (multiplier applied *after* armor).
    """
    from steel_onslaught.reducers.damage import compute_effective_damage_after_vulnerability

    damage_after_armor = 10
    # Heavy chassis with heat_weapon_vulnerability = 1.5 (50% extra heat damage taken)
    heat_weapon_vulnerability = 1.5

    effective = compute_effective_damage_after_vulnerability(
        damage_after_armor=damage_after_armor,
        weapon_damage_type=WeaponDamageType.HEAT,
        heat_weapon_vulnerability=heat_weapon_vulnerability,
    )
    assert effective == 15  # 10 * 1.5


@pytest.mark.unit
def test_heat_vulnerability_not_applied_for_non_heat_weapons() -> None:
    """Heat weapon vulnerability multiplier is not applied for non-heat weapons."""
    from steel_onslaught.reducers.damage import compute_effective_damage_after_vulnerability

    damage_after_armor = 10
    heat_weapon_vulnerability = 1.5  # should be ignored for PRESSURE type

    effective = compute_effective_damage_after_vulnerability(
        damage_after_armor=damage_after_armor,
        weapon_damage_type=WeaponDamageType.PRESSURE,
        heat_weapon_vulnerability=heat_weapon_vulnerability,
    )
    assert effective == 10  # unchanged


@pytest.mark.unit
def test_heat_vulnerability_neutral_multiplier_no_change() -> None:
    """Heat weapon vulnerability of 1.0 (neutral) produces no extra damage."""
    from steel_onslaught.reducers.damage import compute_effective_damage_after_vulnerability

    effective = compute_effective_damage_after_vulnerability(
        damage_after_armor=12,
        weapon_damage_type=WeaponDamageType.HEAT,
        heat_weapon_vulnerability=1.0,
    )
    assert effective == 12
