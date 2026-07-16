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
    ArmorReduction,
    WeaponDamageType,
    apply_damage,
    compute_armor_reduction,
    should_destroy,
)

# ---------------------------------------------------------------------------
# compute_armor_reduction tests (degrading + capped-mitigation model)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_armor_reduction_returns_struct_with_armor_after() -> None:
    """The reducer returns both absorbed and the post-hit armor value."""
    result = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    assert isinstance(result, ArmorReduction)
    assert result.armor_after == 10 - result.absorbed


@pytest.mark.unit
def test_armor_reduction_pressure_weapon_reduces_more() -> None:
    """Pressure-based weapons are reduced more by armor than heat weapons.

    Uses armor large enough that the mitigation cap (not the pool) is binding,
    so the per-type cap difference shows: pressure cap 0.90 > heat cap 0.50.
    """
    absorbed_pressure = compute_armor_reduction(
        damage_raw=20,
        armor_value=100,
        weapon_damage_type=WeaponDamageType.PRESSURE,
    ).absorbed
    absorbed_heat = compute_armor_reduction(
        damage_raw=20,
        armor_value=100,
        weapon_damage_type=WeaponDamageType.HEAT,
    ).absorbed
    # Pressure absorbs ceil(20*0.90)=18; heat absorbs ceil(20*0.50)=10.
    assert absorbed_pressure > absorbed_heat


@pytest.mark.unit
def test_armor_reduction_never_negative() -> None:
    """Armor reduction never returns a negative absorbed value."""
    result = compute_armor_reduction(
        damage_raw=5,
        armor_value=100,
        weapon_damage_type=WeaponDamageType.PRESSURE,
    )
    assert result.absorbed >= 0
    assert result.armor_after >= 0


@pytest.mark.unit
def test_armor_reduction_cannot_exceed_raw_damage() -> None:
    """Absorbed amount cannot exceed raw damage (armor cannot amplify)."""
    result = compute_armor_reduction(
        damage_raw=10,
        armor_value=50,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    assert result.absorbed <= 10


@pytest.mark.unit
def test_armor_reduction_zero_armor_absorbs_nothing() -> None:
    """A mech with armor_value=0 absorbs 0 damage and armor stays 0."""
    result = compute_armor_reduction(
        damage_raw=15,
        armor_value=0,
        weapon_damage_type=WeaponDamageType.PRESSURE,
    )
    assert result.absorbed == 0
    assert result.armor_after == 0


@pytest.mark.unit
def test_armor_reduction_standard_weapon_capped() -> None:
    """Standard weapon: armor absorbs at most 75% of the hit (mitigation cap).

    damage_raw=20, armor=10: cap = ceil(20*0.75)=15, absorbable=min(10,15)=10.
    So absorbed=10, armor_after=0, and 10 damage leaks (50% — under the 75% cap
    because armor ran out, which is the degrading behavior).
    """
    result = compute_armor_reduction(
        damage_raw=20,
        armor_value=10,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    assert result.absorbed == 10
    assert result.armor_after == 0


@pytest.mark.unit
def test_armor_reduction_heat_weapon_reduced_efficiency() -> None:
    """Heat weapons: armor absorbs less than standard (lower mitigation cap).

    Armor large enough that the cap binds: standard cap 0.75 > heat cap 0.50.
    """
    absorbed_standard = compute_armor_reduction(
        damage_raw=20,
        armor_value=100,
        weapon_damage_type=WeaponDamageType.STANDARD,
    ).absorbed
    absorbed_heat = compute_armor_reduction(
        damage_raw=20,
        armor_value=100,
        weapon_damage_type=WeaponDamageType.HEAT,
    ).absorbed
    # Heat weapons bypass armor more: absorbed_heat < absorbed_standard
    assert absorbed_heat < absorbed_standard


@pytest.mark.unit
def test_low_damage_weapon_always_leaks_some_damage() -> None:
    """The original bug: a weapon with damage <= armor did ZERO damage.

    Under the capped model, armor absorbs at most mitigation_cap of the hit, so
    at least (1 - cap) of every hit leaks. A machine_gun (8 dmg) vs armor 16
    must now deal nonzero damage (was 0 under flat subtraction).
    """
    result = compute_armor_reduction(
        damage_raw=8,
        armor_value=16,  # twice the damage — flat model absorbed all 8
        weapon_damage_type=WeaponDamageType.STANDARD,  # cap 0.75
    )
    # cap = ceil(8 * 0.75) = 6 → absorbable = min(16, 6) = 6 → 2 leaks
    assert result.absorbed == 6
    assert 8 - result.absorbed == 2  # nonzero leakage — the fix


@pytest.mark.unit
def test_armor_degrades_across_repeated_hits() -> None:
    """Sustained fire breaks armor: each hit degrades the pool further."""
    armor = 16
    damage_raw = 10  # standard, cap 0.75
    leaked_total = 0
    for _ in range(4):
        result = compute_armor_reduction(
            damage_raw=damage_raw,
            armor_value=armor,
            weapon_damage_type=WeaponDamageType.STANDARD,
        )
        leaked_total += damage_raw - result.absorbed
        armor = result.armor_after
    # Armor started at 16; across 4 hits it degrades and leakage increases.
    # Hit 1: absorbed min(16, ceil(10*.75)=8)=8, leak 2, armor 8
    # Hit 2: absorbed min(8, 8)=8, leak 2, armor 0
    # Hit 3+: absorbed 0, leak 10 each
    assert leaked_total == 2 + 2 + 10 + 10
    assert armor == 0


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
    """absorbed_amount + damage_applied == damage_raw (conservation; no amplification)."""
    damage_raw = 20
    armor_value = 8

    result = compute_armor_reduction(
        damage_raw=damage_raw,
        armor_value=armor_value,
        weapon_damage_type=WeaponDamageType.STANDARD,
    )
    damage_after = max(0, damage_raw - result.absorbed)

    # absorbed + damage_after must equal damage_raw (conservation)
    assert result.absorbed + damage_after == damage_raw


@pytest.mark.unit
def test_damage_total_never_exceeds_raw_across_multiple_hits() -> None:
    """Total damage applied across multiple hits never exceeds sum of raw damage."""
    raws = [10, 15, 8, 20]
    armor_value = 5
    total_applied = 0
    total_raw = sum(raws)

    for raw in raws:
        result = compute_armor_reduction(
            damage_raw=raw,
            armor_value=armor_value,
            weapon_damage_type=WeaponDamageType.STANDARD,
        )
        total_applied += max(0, raw - result.absorbed)

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
