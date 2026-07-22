"""Balance round 2 — brawler damage buff, verified against the REAL model.

Round 1 (28 live-Qwen matches, c11 handler) measured the brawler landing ~3-5
hits/match but each netting ~1 damage vs the sniper's 160 HP — a 100% sniper
walkover. The gate was the DAMAGE MODEL, not legibility: the brawler engages,
its hits just do not matter. This round buffs the two brawler weapons 5.5x
(machine_gun 8->44, shrapnel_thrower 12->66) so a brawler that closes and lands
its observed hits can threaten a meaningful fraction of the sniper's HP and
sometimes win — without one-shotting it.

These tests pin the shipped damage values AND prove, through the actual
``compute_armor_reduction`` reducer and the actual chassis/weapon contracts,
that a landed brawler hit does the intended armor-adjusted damage. If a future
edit reverts the buff or the armor model changes, the balance target breaks
here rather than silently regressing in a live battery.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec, WeaponDamageType
from steel_onslaught.reducers.damage import compute_armor_reduction

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parent.parent.parent / "contracts_data"
_WEAPONS = _ROOT / "weapons"
_CHASSIS = _ROOT / "chassis"


def _weapon(filename: str) -> ModelSOWeaponSpec:
    return ModelSOWeaponSpec.model_validate(yaml.safe_load((_WEAPONS / filename).read_text()))


def _sniper_chassis() -> ModelSOChassisSpec:
    # The Heavy Ironclad Mk1 is the sniper the brawler must kill: 160 HP behind
    # a 16-point armor pool that regenerates 1/tick.
    return ModelSOChassisSpec.model_validate(
        yaml.safe_load((_CHASSIS / "heavy_ironclad_mk1.yaml").read_text())
    )


def _net_hit(weapon: ModelSOWeaponSpec, *, armor_value: int, chassis_class: str) -> int:
    """Armor-adjusted net damage for one landed hit, via the real reducer.

    Mirrors ``MatchRunner`` exactly: damage_raw = int(damage * effectiveness),
    then the degrading-armor reducer, then the heat-vulnerability step (a no-op
    for STANDARD damage, which both brawler weapons are).
    """
    effectiveness = weapon.target_class_effectiveness[chassis_class]  # type: ignore[index]
    damage_raw = int(weapon.damage * effectiveness)
    reduction = compute_armor_reduction(
        damage_raw=damage_raw,
        armor_value=armor_value,
        weapon_damage_type=weapon.damage_type,
    )
    return damage_raw - reduction.absorbed


def test_shipped_brawler_damage_values_are_the_buffed_5_5x() -> None:
    """Pin the exact balance values so a silent revert fails the suite."""
    assert _weapon("machine_gun.yaml").damage == 44  # was 8 (5.5x)
    assert _weapon("shrapnel_thrower.yaml").damage == 66  # was 12 (5.5x)
    # Both remain STANDARD damage so the buff is a pure damage change: the
    # heavy-chassis heat-vulnerability multiplier never applies to them.
    assert _weapon("machine_gun.yaml").damage_type is WeaponDamageType.STANDARD
    assert _weapon("shrapnel_thrower.yaml").damage_type is WeaponDamageType.STANDARD


def test_machine_gun_hit_does_intended_armor_adjusted_damage() -> None:
    mg = _weapon("machine_gun.yaml")
    sniper = _sniper_chassis()
    cls = sniper.chassis_class
    armor_max = sniper.constraints.base_armor  # 16

    # damage_raw = int(44 * 0.7) = 30.
    assert int(mg.damage * mg.target_class_effectiveness[cls]) == 30
    # Fresh armor (16, STANDARD cap 0.75): absorbed = min(16, ceil(30*.75)=23) = 16
    # -> net 14 (was ~1 before the buff).
    assert _net_hit(mg, armor_value=armor_max, chassis_class=cls) == 14
    # Once the small armor pool is stripped, a hit lands near-full: net 30.
    assert _net_hit(mg, armor_value=0, chassis_class=cls) == 30
    # Steady state (armor regenerated to ~2 between shots): net 28.
    assert _net_hit(mg, armor_value=2, chassis_class=cls) == 28


def test_shrapnel_hit_does_intended_armor_adjusted_damage() -> None:
    st = _weapon("shrapnel_thrower.yaml")
    sniper = _sniper_chassis()
    cls = sniper.chassis_class
    armor_max = sniper.constraints.base_armor  # 16

    # damage_raw = int(66 * 0.6) = 39; shrapnel hits harder per shot than the MG.
    assert int(st.damage * st.target_class_effectiveness[cls]) == 39
    assert _net_hit(st, armor_value=armor_max, chassis_class=cls) == 23  # fresh
    assert _net_hit(st, armor_value=0, chassis_class=cls) == 39  # stripped
    assert _net_hit(st, armor_value=3, chassis_class=cls) == 36  # steady


def _hits_to_kill(weapon: ModelSOWeaponSpec, sniper: ModelSOChassisSpec) -> int:
    """Best-case single-weapon kill count: every shot lands, armor degrades to
    the reducer's ``armor_after`` (as the fold does) and only THEN regenerates by
    regen*(cooldown+1) between shots (bounded at the pool max)."""
    armor_max = sniper.constraints.base_armor
    regen = sniper.constraints.base_armor_regen
    effectiveness = weapon.target_class_effectiveness[sniper.chassis_class]
    damage_raw = int(weapon.damage * effectiveness)
    armor = armor_max
    hp = sniper.constraints.base_hp
    hits = 0
    while hp > 0 and hits < 100:
        reduction = compute_armor_reduction(
            damage_raw=damage_raw,
            armor_value=armor,
            weapon_damage_type=weapon.damage_type,
        )
        hp -= damage_raw - reduction.absorbed
        hits += 1
        # Fold order: armor first degrades to armor_after, then regenerates.
        armor = min(armor_max, reduction.armor_after + regen * (weapon.cooldown_ticks + 1))
    return hits


def test_buff_reaches_the_4_to_6_hit_kill_band_without_one_shotting() -> None:
    """The design target: ~4-6 clean armor-adjusted hits kill the sniper, and no
    single hit is anywhere near lethal (survive-and-land skill test, not a
    one-shot). Machine-gun-only is deliberately slower (safe chip damage);
    shrapnel-only is the close-range finisher."""
    sniper = _sniper_chassis()
    mg = _weapon("machine_gun.yaml")
    st = _weapon("shrapnel_thrower.yaml")

    mg_hits = _hits_to_kill(mg, sniper)
    st_hits = _hits_to_kill(st, sniper)
    # Shrapnel (the finisher) sits in the 4-6 target band; the machine gun is
    # intentionally a touch slower so closing to shrapnel range is rewarded.
    assert 4 <= st_hits <= 6, st_hits
    assert 6 <= mg_hits <= 7, mg_hits
    assert st_hits <= mg_hits  # shrapnel is the harder-hitting weapon

    # Not a one-shot: even against fully-stripped armor a single hit is a small
    # fraction of the sniper's 160 HP.
    max_single = max(
        _net_hit(mg, armor_value=0, chassis_class=sniper.chassis_class),
        _net_hit(st, armor_value=0, chassis_class=sniper.chassis_class),
    )
    assert max_single < sniper.constraints.base_hp // 3  # 39 < 53


def test_buff_is_a_material_improvement_over_the_pre_buff_walkover() -> None:
    """Sanity floor vs round 1: pre-buff a landed hit netted ~1 damage; every
    landed brawler hit must now net well into double digits even against fresh
    armor, so the brawler's observed 3-5 hits amount to a real threat."""
    sniper = _sniper_chassis()
    cls = sniper.chassis_class
    armor_max = sniper.constraints.base_armor
    for filename, fresh_floor in (("machine_gun.yaml", 12), ("shrapnel_thrower.yaml", 20)):
        weapon = _weapon(filename)
        assert _net_hit(weapon, armor_value=armor_max, chassis_class=cls) >= fresh_floor
