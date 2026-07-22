"""Round-4 close-in carbine — sustainability verified against the REAL boiler.

Hostile-review fix #1: the naive close-in carbine is pressure/heat-throttled, so
the sniper's sustainable close-range output collapses (~15/tick) while the
brawler is unthrottled (~30-39/tick) -> ~2.3:1 brawler auto-win. The fix is a
carbine that is genuinely SUSTAINABLE against the Bessemer-90's real regen/vent
caps AND never trips the c11 overpressure lockout, so the sniper keeps a real
close-range floor (a CONTEST, not a walkover).

These tests pin the shipped carbine values and prove, through the ACTUAL boiler
and weapon contracts and the SAME per-tick arithmetic the runtime uses
(WEAPON_FIRED spends pressure_cost / adds heat_generated; MATCH_TICK regens /
vents), that:

  - firing the carbine every available weapon register never drains pressure and
    never accumulates heat round-over-round (per-tick pressure/heat budget, not
    free-fire DPS);
  - the carbine is admissible from EVERY heat state the c11 handler can reach, so
    it is never self-locked — unlike the mortar, which is rate-taxed (the
    intended asymmetry);
  - the carbine is exempt from the round-4 range-band falloff (range < the band's
    min_weapon_range), while the mortar/harpoon are subject to it;
  - a landed carbine hit is weak-but-real against the 60-HP brawler.

If a future retune breaks sustainability or the lockout asymmetry, the balance
target fails here rather than silently over-correcting in a live battery.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.reducers.damage import compute_armor_reduction

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parent.parent.parent / "contracts_data"
_WEAPONS = _ROOT / "weapons"
_BOILERS = _ROOT / "boilers"
_CHASSIS = _ROOT / "chassis"

# The sniper's shipped split-deck seat parameters (see
# tactical_split_range_band_evasion_qwen.yaml): 5 registers per paced round, of
# which up to 3 are weapon registers. Paced cadence resolves one register per
# tick, so a round spans 5 MATCH_TICKs.
_ROUND_TICKS = 5
_WEAPON_REGISTERS_PER_ROUND = 3

# The shipped range-band binding (tactical_split_range_band_evasion_qwen.yaml).
_MIN_WEAPON_RANGE = 20


def _carbine_fires_per_round(cooldown_ticks: int) -> int:
    """Sustained worst-case carbine fires in one paced round.

    Two independent caps apply: the sniper may spend at most
    ``_WEAPON_REGISTERS_PER_ROUND`` weapon registers on the carbine, and
    ``cooldown_ticks`` forces a >= ``cooldown_ticks``-MATCH_TICK gap between
    fires, admitting at most ``_ROUND_TICKS // cooldown_ticks`` sustained fires
    per ``_ROUND_TICKS``-tick round. The effective sustained rate is the smaller
    of the two. At cooldown 1 the register quota binds (3/round); at the shipped
    cooldown 3 the cooldown binds (~1/round). This is the c11 throttle: the same
    formula reproduces the pre-throttle worst case, so the drop is proven by the
    cooldown value alone.
    """
    cooldown_admitted = _ROUND_TICKS // cooldown_ticks
    return min(_WEAPON_REGISTERS_PER_ROUND, cooldown_admitted)


def _weapon(filename: str) -> ModelSOWeaponSpec:
    return ModelSOWeaponSpec.model_validate(yaml.safe_load((_WEAPONS / filename).read_text()))


def _bessemer() -> ModelSOBoilerSpec:
    return ModelSOBoilerSpec.model_validate(
        yaml.safe_load((_BOILERS / "industrial_bessemer_90.yaml").read_text())
    )


def test_shipped_carbine_values() -> None:
    """Pin the exact balance values so a silent retune fails the suite."""
    carbine = _weapon("defense_carbine.yaml")
    assert carbine.range == 14  # < min_weapon_range 20 => exempt from the falloff
    assert carbine.damage == 20
    assert carbine.pressure_cost == 5
    assert carbine.heat_generated == 3
    # c11 throttle: cooldown 1 -> 3 gates sustained point-blank fire to ~1/round
    # so the carbine stops backfilling the mortar's stripped damage.
    assert carbine.cooldown_ticks == 3


def test_carbine_cooldown_throttle_cuts_sustained_output() -> None:
    """The c11 fix is the cooldown alone: at the shipped cooldown 3 the carbine's
    sustained fires/round drop well below the pre-throttle cooldown-1 rate that
    fully backfilled the mortar's range-band-stripped point-blank damage."""
    carbine = _weapon("defense_carbine.yaml")
    throttled = _carbine_fires_per_round(carbine.cooldown_ticks)
    pre_throttle = _carbine_fires_per_round(1)
    assert pre_throttle == 3  # register-quota-bound at cooldown 1
    assert throttled == 1  # cooldown-bound at cooldown 3 (5 // 3)
    # ~66% cut in sustained point-blank cadence (3 -> 1), the balance target.
    assert throttled < pre_throttle
    assert throttled <= pre_throttle // 3 + (1 if pre_throttle % 3 else 0)


def test_carbine_pressure_is_sustainable() -> None:
    """Firing the carbine on every ADMISSIBLE weapon register never drains
    pressure: the per-round spend is strictly below the per-round regen (net
    positive). cooldown 3 only deepens the margin the cooldown-1 carbine had."""
    carbine = _weapon("defense_carbine.yaml")
    boiler = _bessemer()

    fires = _carbine_fires_per_round(carbine.cooldown_ticks)  # 1 at cooldown 3
    spend_per_round = fires * carbine.pressure_cost  # 1 * 5 = 5
    regen_per_round = _ROUND_TICKS * boiler.regen_per_tick  # 5 * 5 = 25
    assert spend_per_round < regen_per_round, (spend_per_round, regen_per_round)
    # Net per round is comfortably positive (pressure climbs back toward the cap).
    assert regen_per_round - spend_per_round >= 5


def test_carbine_heat_is_sustainable() -> None:
    """Firing the carbine on every admissible weapon register never accumulates
    heat: the per-round heat added is strictly below the per-round venting (net
    cooling). cooldown 3 only deepens the cooling margin."""
    carbine = _weapon("defense_carbine.yaml")
    boiler = _bessemer()

    fires = _carbine_fires_per_round(carbine.cooldown_ticks)  # 1 at cooldown 3
    added_per_round = fires * carbine.heat_generated  # 1 * 3 = 3
    vented_per_round = _ROUND_TICKS * boiler.vent_rate  # 5 * 4 = 20
    assert added_per_round < vented_per_round, (added_per_round, vented_per_round)


def test_carbine_never_trips_the_c11_overpressure_lockout() -> None:
    """The carbine is admissible from EVERY heat the c11 handler can reach.

    The overpressure_cooldown handler holds every plan's heat at or below the
    ceiling (``heat_capacity``), and each register-tick vents ``vent_rate`` before
    a shot's heat is added. So the hottest a carbine shot ever sees is
    ``heat_capacity``; after venting and adding its heat it must stay strictly
    below the ceiling, or it would be the thing that trips the lockout.
    """
    carbine = _weapon("defense_carbine.yaml")
    boiler = _bessemer()
    ceiling = boiler.heat_capacity  # 28

    heat_after_vent = max(ceiling - boiler.vent_rate, 0)  # 24
    assert heat_after_vent + carbine.heat_generated < ceiling, "carbine can self-lock"

    # Asymmetry (the whole point): the mortar DOES cross the ceiling from a hot
    # pool, so it is the rate-taxed weapon while the carbine is the sustainable
    # fallback. (harpoon likewise.)
    mortar = _weapon("artillery_mortar.yaml")
    assert heat_after_vent + mortar.heat_generated >= ceiling, "mortar should be rate-taxed"


def test_carbine_is_exempt_from_the_falloff_but_long_guns_are_not() -> None:
    """The falloff is a long-weapon rule: the carbine (range 14) is exempt; the
    mortar (50) and harpoon (30) are subject."""
    assert _weapon("defense_carbine.yaml").range < _MIN_WEAPON_RANGE
    assert _weapon("artillery_mortar.yaml").range >= _MIN_WEAPON_RANGE
    assert _weapon("harpoon_gun.yaml").range >= _MIN_WEAPON_RANGE


def test_carbine_hit_is_weak_but_real_against_the_brawler() -> None:
    """A landed carbine hit does real double-digit damage to the 60-HP scout
    brawler (not a free melee for the brawler) but is never a one-shot and stays
    below the brawler's own per-hit output (a contest, not a sniper walkover)."""
    carbine = _weapon("defense_carbine.yaml")
    scout = ModelSOChassisSpec.model_validate(
        yaml.safe_load((_CHASSIS / "light_scout_mk1.yaml").read_text())
    )
    cls = scout.chassis_class  # light
    armor_max = scout.constraints.base_armor  # 6

    def net(armor_value: int) -> int:
        effectiveness = carbine.target_class_effectiveness[cls]
        damage_raw = int(carbine.damage * effectiveness)
        reduction = compute_armor_reduction(
            damage_raw=damage_raw,
            armor_value=armor_value,
            weapon_damage_type=carbine.damage_type,
        )
        return damage_raw - reduction.absorbed

    # damage_raw = int(20 * 1.0) = 20; fresh net 20-6 = 14, stripped net 20.
    assert net(armor_max) == 14
    assert net(0) == 20
    # Real (double-digit) but never a one-shot on 60 HP.
    assert net(armor_max) >= 10
    assert net(0) < scout.constraints.base_hp // 2  # 20 < 30

    # Below the brawler's own close-range output (shrapnel nets ~23-39 vs the
    # sniper): the carbine is a counterplay floor, not a superior trade.
    shrapnel = _weapon("shrapnel_thrower.yaml")
    sniper = ModelSOChassisSpec.model_validate(
        yaml.safe_load((_CHASSIS / "heavy_ironclad_mk1.yaml").read_text())
    )
    shrapnel_stripped = int(
        shrapnel.damage * shrapnel.target_class_effectiveness[sniper.chassis_class]
    )  # 39
    assert net(0) < shrapnel_stripped
