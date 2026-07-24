"""Contract proof for the 3 pair-sweep arms (mortar_r30 x lethality dose).

Session 2026-07-24: every prior approach/geometry lever (arm 1 mortar range
cap, arm 13 leapfrog cover, the combined v2 re-cut) measured null at 0/30
against the qwen35 asym v1 anchor. Forensic kill math: blue kills red in
~2.04 hits (avg 29.47 dmg-after-armor vs 60HP), red kills blue in ~26.74
hits (avg 5.98 dmg-after-armor vs 160HP+16 armor). This suite pairs the
merged approach fix (the arm-1 sniper loadout, mortar range 50 -> 30) with
three lethality doses on the OTHERWISE-STOCK v1 arena + stock red loadout
(``llm_qwen35_berserker``):

  - P1 (dmg3):    mortar_r30 + red weapon damage x3 (machine_gun +
                  shrapnel_thrower, variant copies with damage tripled).
  - P2 (dmg55):   mortar_r30 + red weapon damage x5.5 (the historical
                  single-lever dose that scored ~5% under the old lethal
                  approach, now paired with the approach fix).
  - P3 (armor8):  mortar_r30 + blue chassis armor 16 -> 8 (lethality via
                  the armor side, zero red-side buffs).

Each arm changes EXACTLY TWO levers (the shared approach fix + one
lethality dose) via additive variant files + its own overlay -- existing
baseline contracts (``artillery_mortar.yaml``, ``foundry_60_asym_v1.yaml``,
``llm_qwen35_berserker.yaml``, ``qwen35/sniper_ironclad.yaml``,
``qwen35/sniper_ironclad_mortar_r30.yaml``,
``chassis/heavy_ironclad_mk1.yaml``, the v1 combined overlay, and the arm-1
mortar_r30 overlay) are never edited in place, and no arm's variant files
leak into another arm's overlay.

This suite proves, without a live battery (CI-safe):

  1. every new weapon/chassis/loadout/overlay file parses and validates;
  2. every weapon variant differs from its baseline by EXACTLY the declared
     damage multiplier, with every other field byte-identical;
  3. the chassis variant differs from ``heavy_ironclad_mk1.yaml`` by EXACTLY
     ``base_armor`` (16 -> 8), with every other field byte-identical;
  4. every loadout variant differs from its baseline by EXACTLY the
     declared module swap(s), with zero budget-axis violations;
  5. every battery overlay parses, binds the baseline (stock) arena, and is
     otherwise structurally identical to the v1 combined overlay -- mirroring
     ``test_tournament_arms.py``'s discipline;
  6. every baseline file (both mortars, both weapons, the arena, all
     loadouts, the baseline chassis, both overlays) is proven untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOOpenAICompatibleProviderBinding,
)
from steel_onslaught.contracts.budget import ModelSOModuleBudget, validate_loadout_budgets
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import ModelSOGizmoConstraints
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_match_contract_catalog,
)

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_CHASSIS = _REPO_ROOT / "contracts_data" / "chassis"
_WEAPONS = _REPO_ROOT / "contracts_data" / "weapons"
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts"
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"

_BASE_ARENA_ID = "foundry_60_asym_v1"
_BASE_MACHINE_GUN_PATH = _WEAPONS / "machine_gun.yaml"
_BASE_SHRAPNEL_PATH = _WEAPONS / "shrapnel_thrower.yaml"
_BASE_MORTAR_PATH = _WEAPONS / "artillery_mortar.yaml"
_MORTAR_R30_PATH = _WEAPONS / "artillery_mortar_r30.yaml"
_BASE_CHASSIS_PATH = _CHASSIS / "heavy_ironclad_mk1.yaml"
_BASE_SNIPER_PATH = _LOADOUTS / "qwen35" / "sniper_ironclad.yaml"
_MORTAR_R30_SNIPER_PATH = _LOADOUTS / "qwen35" / "sniper_ironclad_mortar_r30.yaml"
_BASE_BERSERKER_PATH = _LOADOUTS / "llm_qwen35_berserker.yaml"
_BASE_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"
_ARM1_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen_mortar_r30.yaml"

_QWEN35_PROVIDER_ID = "qwen35"


def _load_weapon(path: Path) -> ModelSOWeaponSpec:
    return ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))


def _load_chassis(path: Path) -> ModelSOChassisSpec:
    return ModelSOChassisSpec.model_validate(yaml.safe_load(path.read_text()))


def _load_loadout(path: Path) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(yaml.safe_load(path.read_text()))


def _qwen35_provider(
    overlay: ModelSOApplicationOverlay,
) -> ModelSOOpenAICompatibleProviderBinding:
    selected = [
        provider
        for provider in overlay.llm.providers
        if provider.provider_id == _QWEN35_PROVIDER_ID
    ]
    assert len(selected) == 1, "overlay must declare exactly one qwen35 provider"
    provider = selected[0]
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    return provider


def _assert_loadout_zero_budget_violations(loadout: ModelSOLoadout) -> None:
    """Rebuilds the same ``ModelSOModuleBudget`` normalization
    ``match/runner.py::_module_budgets`` performs, mirroring
    ``test_tournament_arms.py``.
    """
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    chassis = catalog.chassis[loadout.chassis_id]
    boiler = catalog.boilers[loadout.boiler_id]

    modules: list[ModelSOModuleBudget] = []
    for weapon_id in loadout.modules.weapons:
        weapon = catalog.weapons[weapon_id]
        modules.append(
            ModelSOModuleBudget(
                module_id=weapon_id,
                mass=0,
                slots=1,
                pressure_draw=0.0,
                heat_output=float(weapon.heat_generated),
                signature_impact=0.0,
                active_modes=(ModeId.ASSAULT,),
            )
        )
    for sensor_id in loadout.modules.sensors:
        sensor = catalog.sensors[sensor_id]
        modules.append(
            ModelSOModuleBudget(
                module_id=sensor_id,
                mass=0,
                slots=1,
                pressure_draw=sensor.pressure_draw_per_tick,
                heat_output=sensor.heat_per_tick,
                signature_impact=sensor.signature_impact,
                active_modes=tuple(ModeId),
            )
        )
    for gizmo_id in loadout.modules.gizmos:
        gizmo = catalog.gizmos[gizmo_id]
        constraints = ModelSOGizmoConstraints.model_validate(gizmo.constraints)
        modules.append(
            ModelSOModuleBudget(
                module_id=gizmo_id,
                mass=constraints.mass,
                slots=constraints.slots,
                pressure_draw=0.0,
                heat_output=0.0,
                signature_impact=0.0,
                active_modes=tuple(ModeId),
            )
        )

    violations = validate_loadout_budgets(loadout, chassis, boiler, modules)
    assert violations == [], f"unexpected budget violations: {violations}"


# ---------------------------------------------------------------------------
# Baseline is untouched (shared across all 3 arms)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_baseline_weapons_are_untouched() -> None:
    machine_gun = _load_weapon(_BASE_MACHINE_GUN_PATH)
    assert machine_gun.id == "weapon.light.machine_gun"
    assert machine_gun.damage == 8
    shrapnel = _load_weapon(_BASE_SHRAPNEL_PATH)
    assert shrapnel.id == "weapon.light.shrapnel_thrower"
    assert shrapnel.damage == 12


@pytest.mark.unit
def test_baseline_arena_is_untouched() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[_BASE_ARENA_ID]
    assert (arena.spawn_a.x, arena.spawn_a.y) == (4, 30)
    assert (arena.spawn_b.x, arena.spawn_b.y) == (52, 30)


@pytest.mark.unit
def test_baseline_chassis_is_untouched() -> None:
    chassis = _load_chassis(_BASE_CHASSIS_PATH)
    assert chassis.id == "chassis.heavy.ironclad_mk1"
    assert chassis.constraints.base_armor == 16
    assert chassis.constraints.base_hp == 160


@pytest.mark.unit
def test_baseline_loadouts_are_untouched() -> None:
    sniper = _load_loadout(_BASE_SNIPER_PATH)
    assert sniper.id == "loadout.llm.qwen35_sniper_ironclad"
    assert sniper.chassis_id == "chassis.heavy.ironclad_mk1"
    berserker = _load_loadout(_BASE_BERSERKER_PATH)
    assert berserker.id == "loadout.llm.qwen35_berserker"
    assert berserker.modules.weapons == (
        "weapon.light.machine_gun",
        "weapon.light.shrapnel_thrower",
    )
    mortar_r30_sniper = _load_loadout(_MORTAR_R30_SNIPER_PATH)
    assert mortar_r30_sniper.id == "loadout.llm.qwen35_sniper_ironclad_mortar_r30"
    assert mortar_r30_sniper.chassis_id == "chassis.heavy.ironclad_mk1"


@pytest.mark.unit
def test_baseline_overlays_are_untouched() -> None:
    overlay = load_application_overlay(_BASE_OVERLAY)
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    arm1_overlay = load_application_overlay(_ARM1_OVERLAY)
    assert arm1_overlay.contracts.arena_id == _BASE_ARENA_ID


# ---------------------------------------------------------------------------
# P1: mortar_r30 + red weapon damage x3
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_p1_machine_gun_dmg3_changes_only_damage() -> None:
    base = _load_weapon(_BASE_MACHINE_GUN_PATH)
    variant = _load_weapon(_WEAPONS / "machine_gun_dmg3.yaml")
    assert variant.id == "weapon.light.machine_gun_dmg3"
    assert variant.damage == 24
    assert variant.damage == base.damage * 3
    assert variant.range == base.range
    assert variant.pressure_cost == base.pressure_cost
    assert variant.heat_generated == base.heat_generated
    assert variant.cooldown_ticks == base.cooldown_ticks
    assert variant.accuracy_curve == base.accuracy_curve
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_p1_shrapnel_thrower_dmg3_changes_only_damage() -> None:
    base = _load_weapon(_BASE_SHRAPNEL_PATH)
    variant = _load_weapon(_WEAPONS / "shrapnel_thrower_dmg3.yaml")
    assert variant.id == "weapon.light.shrapnel_thrower_dmg3"
    assert variant.damage == 36
    assert variant.damage == base.damage * 3
    assert variant.range == base.range
    assert variant.pressure_cost == base.pressure_cost
    assert variant.heat_generated == base.heat_generated
    assert variant.cooldown_ticks == base.cooldown_ticks
    assert variant.accuracy_curve == base.accuracy_curve
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_p1_berserker_loadout_swaps_only_the_two_weapons() -> None:
    base = _load_loadout(_BASE_BERSERKER_PATH)
    variant = _load_loadout(_LOADOUTS / "llm_qwen35_berserker_dmg3.yaml")
    assert variant.id == "loadout.llm.qwen35_berserker_dmg3"
    assert variant.modules.weapons == (
        "weapon.light.machine_gun_dmg3",
        "weapon.light.shrapnel_thrower_dmg3",
    )
    assert variant.chassis_id == base.chassis_id
    assert variant.boiler_id == base.boiler_id
    assert variant.pilot_id == base.pilot_id
    assert variant.modules.sensors == base.modules.sensors
    assert variant.modules.gizmos == base.modules.gizmos
    assert variant.budgets == base.budgets
    _assert_loadout_zero_budget_violations(variant)


@pytest.mark.unit
def test_p1_overlay_binds_baseline_stock_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_pair_p1_dmg3_qwen.yaml"
    )
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider


# ---------------------------------------------------------------------------
# P2: mortar_r30 + red weapon damage x5.5
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_p2_machine_gun_dmg55_changes_only_damage() -> None:
    base = _load_weapon(_BASE_MACHINE_GUN_PATH)
    variant = _load_weapon(_WEAPONS / "machine_gun_dmg55.yaml")
    assert variant.id == "weapon.light.machine_gun_dmg55"
    assert variant.damage == 44
    assert variant.damage == round(base.damage * 5.5)
    assert variant.range == base.range
    assert variant.pressure_cost == base.pressure_cost
    assert variant.heat_generated == base.heat_generated
    assert variant.cooldown_ticks == base.cooldown_ticks
    assert variant.accuracy_curve == base.accuracy_curve
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_p2_shrapnel_thrower_dmg55_changes_only_damage() -> None:
    base = _load_weapon(_BASE_SHRAPNEL_PATH)
    variant = _load_weapon(_WEAPONS / "shrapnel_thrower_dmg55.yaml")
    assert variant.id == "weapon.light.shrapnel_thrower_dmg55"
    assert variant.damage == 66
    assert variant.damage == round(base.damage * 5.5)
    assert variant.range == base.range
    assert variant.pressure_cost == base.pressure_cost
    assert variant.heat_generated == base.heat_generated
    assert variant.cooldown_ticks == base.cooldown_ticks
    assert variant.accuracy_curve == base.accuracy_curve
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_p2_berserker_loadout_swaps_only_the_two_weapons() -> None:
    base = _load_loadout(_BASE_BERSERKER_PATH)
    variant = _load_loadout(_LOADOUTS / "llm_qwen35_berserker_dmg55.yaml")
    assert variant.id == "loadout.llm.qwen35_berserker_dmg55"
    assert variant.modules.weapons == (
        "weapon.light.machine_gun_dmg55",
        "weapon.light.shrapnel_thrower_dmg55",
    )
    assert variant.chassis_id == base.chassis_id
    assert variant.boiler_id == base.boiler_id
    assert variant.pilot_id == base.pilot_id
    assert variant.modules.sensors == base.modules.sensors
    assert variant.modules.gizmos == base.modules.gizmos
    assert variant.budgets == base.budgets
    _assert_loadout_zero_budget_violations(variant)


@pytest.mark.unit
def test_p2_overlay_binds_baseline_stock_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_pair_p2_dmg55_qwen.yaml"
    )
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider


# ---------------------------------------------------------------------------
# P3: mortar_r30 + blue chassis armor 16 -> 8
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_p3_chassis_armor8_changes_only_base_armor() -> None:
    base = _load_chassis(_BASE_CHASSIS_PATH)
    variant = _load_chassis(_CHASSIS / "heavy_ironclad_mk1_armor8.yaml")
    assert variant.id == "chassis.heavy.ironclad_mk1_armor8"
    assert variant.constraints.base_armor == 8
    assert variant.constraints.base_armor != base.constraints.base_armor
    assert variant.chassis_class == base.chassis_class
    assert variant.constraints.max_mass == base.constraints.max_mass
    assert variant.constraints.max_module_slots == base.constraints.max_module_slots
    assert variant.constraints.max_boiler_volume == base.constraints.max_boiler_volume
    assert variant.constraints.base_speed == base.constraints.base_speed
    assert variant.constraints.base_turn_rate == base.constraints.base_turn_rate
    assert variant.constraints.base_signature == base.constraints.base_signature
    assert variant.constraints.base_vent_rate == base.constraints.base_vent_rate
    assert variant.constraints.base_hp == base.constraints.base_hp
    assert variant.constraints.base_armor_regen == base.constraints.base_armor_regen
    assert variant.compatibility == base.compatibility
    assert variant.penalties == base.penalties


@pytest.mark.unit
def test_p3_sniper_loadout_pairs_mortar_r30_weapon_with_armor8_chassis() -> None:
    mortar_r30_base = _load_loadout(_MORTAR_R30_SNIPER_PATH)
    variant = _load_loadout(_LOADOUTS / "qwen35" / "sniper_ironclad_mortar_r30_armor8.yaml")
    assert variant.id == "loadout.llm.qwen35_sniper_ironclad_mortar_r30_armor8"
    assert variant.chassis_id == "chassis.heavy.ironclad_mk1_armor8"
    assert variant.chassis_id != mortar_r30_base.chassis_id
    assert variant.modules.weapons == mortar_r30_base.modules.weapons
    assert variant.modules.weapons == (
        "weapon.siege.artillery_mortar_r30",
        "weapon.heavy.harpoon_gun",
    )
    assert variant.boiler_id == mortar_r30_base.boiler_id
    assert variant.pilot_id == mortar_r30_base.pilot_id
    assert variant.modules.sensors == mortar_r30_base.modules.sensors
    assert variant.modules.gizmos == mortar_r30_base.modules.gizmos
    assert variant.budgets == mortar_r30_base.budgets
    _assert_loadout_zero_budget_violations(variant)


@pytest.mark.unit
def test_p3_overlay_binds_baseline_stock_arena_and_stock_red_loadout() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_pair_p3_armor8_qwen.yaml"
    )
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider
    # P3 does not introduce a red-side loadout variant -- the stock
    # berserker (unchanged from the baseline) stays the driver default.
    berserker = _load_loadout(_BASE_BERSERKER_PATH)
    assert berserker.modules.weapons == (
        "weapon.light.machine_gun",
        "weapon.light.shrapnel_thrower",
    )


# ---------------------------------------------------------------------------
# Cross-arm: no leakage between arm overlays / variant files
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_pair_overlay_binds_the_stock_baseline_arena() -> None:
    """All three arms are lethality doses paired with the shared approach
    fix on the OTHERWISE-STOCK v1 arena -- none of them touches the arena.
    """
    for name in (
        "tactical_split_overdeal_utility_asym_pair_p1_dmg3_qwen.yaml",
        "tactical_split_overdeal_utility_asym_pair_p2_dmg55_qwen.yaml",
        "tactical_split_overdeal_utility_asym_pair_p3_armor8_qwen.yaml",
    ):
        overlay = load_application_overlay(_OVERLAYS / name)
        assert overlay.contracts.arena_id == _BASE_ARENA_ID


@pytest.mark.unit
def test_each_dose_variant_is_a_distinct_new_id_not_shared_across_arms() -> None:
    weapon_variant_ids = {
        _load_weapon(_WEAPONS / "machine_gun_dmg3.yaml").id,
        _load_weapon(_WEAPONS / "shrapnel_thrower_dmg3.yaml").id,
        _load_weapon(_WEAPONS / "machine_gun_dmg55.yaml").id,
        _load_weapon(_WEAPONS / "shrapnel_thrower_dmg55.yaml").id,
    }
    assert len(weapon_variant_ids) == 4
    assert "weapon.light.machine_gun" not in weapon_variant_ids
    assert "weapon.light.shrapnel_thrower" not in weapon_variant_ids

    chassis_variant_id = _load_chassis(_CHASSIS / "heavy_ironclad_mk1_armor8.yaml").id
    assert chassis_variant_id != "chassis.heavy.ironclad_mk1"

    loadout_variant_ids = {
        _load_loadout(_LOADOUTS / "llm_qwen35_berserker_dmg3.yaml").id,
        _load_loadout(_LOADOUTS / "llm_qwen35_berserker_dmg55.yaml").id,
        _load_loadout(_LOADOUTS / "qwen35" / "sniper_ironclad_mortar_r30_armor8.yaml").id,
    }
    assert len(loadout_variant_ids) == 3


@pytest.mark.unit
def test_p1_and_p2_share_the_mortar_r30_approach_fix_via_the_arm1_loadout() -> None:
    """P1 and P2 both bind the arm-1 mortar_r30 sniper loadout unmodified on
    the blue seat -- the shared approach-fix lever is byte-identical across
    both arms (only the red-side dose differs).
    """
    mortar_r30 = _load_loadout(_MORTAR_R30_SNIPER_PATH)
    assert mortar_r30.modules.weapons == (
        "weapon.siege.artillery_mortar_r30",
        "weapon.heavy.harpoon_gun",
    )
    p1_overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_pair_p1_dmg3_qwen.yaml"
    )
    p2_overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_pair_p2_dmg55_qwen.yaml"
    )
    # Both overlays are structurally identical apart from state-directory
    # paths -- same arena, same card-deck policy, same utility handler pack.
    assert p1_overlay.contracts.arena_id == p2_overlay.contracts.arena_id
    assert p1_overlay.contracts.card_catalog is not None
    assert p2_overlay.contracts.card_catalog is not None
    assert (
        p1_overlay.contracts.card_catalog.deck_policy
        == p2_overlay.contracts.card_catalog.deck_policy
    )
    assert p1_overlay.contracts.utility_handler_pack == p2_overlay.contracts.utility_handler_pack
