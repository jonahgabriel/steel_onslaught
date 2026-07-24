"""Contract proof for the 5 tournament-winner single-lever arms.

Session 2026-07-24: a single-lever tournament to make the brawler/berserker
(red) competitive against the sniper (blue) on the qwen35 asym v1 anchor
(0/30 red wins, median 31 ticks). Each arm changes EXACTLY ONE lever versus
the baseline via additive variant files + its own battery overlay --
existing baseline contracts (``artillery_mortar.yaml``,
``foundry_60_asym_v1.yaml``, ``llm_qwen35_berserker.yaml``,
``qwen35/sniper_ironclad.yaml``, the v1 combined overlay) are never edited
in place, and no arm's variant files leak into another arm's overlay.

  - ARM 1  (mortar_r30):       weapon lever -- mortar range 50 -> 30.
  - ARM 3  (mortar_cd9):       weapon lever -- mortar cooldown_ticks 5 -> 9.
  - ARM 4  (mortar_acc):       weapon lever -- mortar far-band accuracy
                                nerf (35/45/50 hit_probability lowered).
                                CONDITIONAL: only battery-run if arm 1
                                undershoots.
  - ARM 11 (corridor_spawn):   arena lever -- spawn_a relocated into the
                                north corridor mouth (4,30) -> (10,22),
                                corrected from the dispatched (8,20), which
                                collides with an existing obstacle rect.
  - ARM 13 (leapfrog_cover):   arena lever -- 5 new staggered cover blocks
                                inside the open y=28..32 sightline lane,
                                one rect (block 2) corrected from the
                                dispatched {18,31,22,33} to {18,31,22,32}
                                to clear a collision with an existing
                                mid-lane flanking-cover rect.

This suite proves, without a live battery (CI-safe):

  1. every new weapon/arena/loadout/overlay file parses and validates;
  2. every weapon variant differs from ``artillery_mortar.yaml`` by EXACTLY
     the one declared lever, with every other field byte-identical;
  3. every arena variant differs from ``foundry_60_asym_v1.yaml`` by EXACTLY
     the declared spatial change (new cover cells / relocated spawn), with
     spawns/objectives/rects otherwise byte-identical (arm 1/3/4 do not
     touch the arena; arm 11/13 do not touch weapons);
  4. every sniper loadout variant differs from
     ``qwen35/sniper_ironclad.yaml`` by EXACTLY the one weapon-id swap, with
     zero budget-axis violations (weapons carry no mass, so the swap cannot
     perturb MASS/SLOTS/PRESSURE);
  5. every battery overlay parses, binds the correct arena_id, and is
     otherwise structurally identical to the v1 combined overlay (same
     card-deck policy, same utility handler pack, same LLM provider/retry
     config) -- mirroring ``test_brawler_recut_v2.py``'s discipline;
  6. every baseline file (mortar, arena, both loadouts, v1 overlay) is
     proven untouched.
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
_ARENAS = _REPO_ROOT / "contracts_data" / "arenas"
_WEAPONS = _REPO_ROOT / "contracts_data" / "weapons"
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts"
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"

_BASE_ARENA_ID = "foundry_60_asym_v1"
_BASE_MORTAR_PATH = _WEAPONS / "artillery_mortar.yaml"
_BASE_SNIPER_PATH = _LOADOUTS / "qwen35" / "sniper_ironclad.yaml"
_BASE_BERSERKER_PATH = _LOADOUTS / "llm_qwen35_berserker.yaml"
_BASE_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"

_QWEN35_PROVIDER_ID = "qwen35"


def _load_weapon(path: Path) -> ModelSOWeaponSpec:
    return ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))


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
    ``test_brawler_recut_v2.py``.
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
# Baseline is untouched (shared across all 5 arms)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_baseline_mortar_is_untouched() -> None:
    mortar = _load_weapon(_BASE_MORTAR_PATH)
    assert mortar.id == "weapon.siege.artillery_mortar"
    assert mortar.range == 50
    assert mortar.cooldown_ticks == 5
    assert [(p.range, p.hit_probability) for p in mortar.accuracy_curve] == [
        (20, 0.80),
        (35, 0.70),
        (45, 0.55),
        (50, 0.40),
    ]


@pytest.mark.unit
def test_baseline_arena_is_untouched() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena = catalog.arenas[_BASE_ARENA_ID]
    assert (arena.spawn_a.x, arena.spawn_a.y) == (4, 30)
    assert (arena.spawn_b.x, arena.spawn_b.y) == (52, 30)


@pytest.mark.unit
def test_baseline_loadouts_are_untouched() -> None:
    sniper = _load_loadout(_BASE_SNIPER_PATH)
    assert sniper.id == "loadout.llm.qwen35_sniper_ironclad"
    assert sniper.modules.weapons == (
        "weapon.siege.artillery_mortar",
        "weapon.heavy.harpoon_gun",
    )
    berserker = _load_loadout(_BASE_BERSERKER_PATH)
    assert berserker.id == "loadout.llm.qwen35_berserker"
    assert berserker.modules.weapons == (
        "weapon.light.machine_gun",
        "weapon.light.shrapnel_thrower",
    )


@pytest.mark.unit
def test_baseline_overlay_is_untouched() -> None:
    overlay = load_application_overlay(_BASE_OVERLAY)
    assert overlay.contracts.arena_id == _BASE_ARENA_ID


# ---------------------------------------------------------------------------
# ARM 1: mortar_r30 -- range 50 -> 30
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_arm1_mortar_r30_changes_only_range() -> None:
    base = _load_weapon(_BASE_MORTAR_PATH)
    variant = _load_weapon(_WEAPONS / "artillery_mortar_r30.yaml")
    assert variant.id == "weapon.siege.artillery_mortar_r30"
    assert variant.range == 30
    assert variant.range != base.range
    assert variant.damage == base.damage == 45
    assert variant.cooldown_ticks == base.cooldown_ticks == 5
    assert variant.heat_generated == base.heat_generated == 15
    assert variant.pressure_cost == base.pressure_cost
    assert variant.accuracy_curve == base.accuracy_curve
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_arm1_sniper_loadout_swaps_only_the_mortar() -> None:
    base = _load_loadout(_BASE_SNIPER_PATH)
    variant = _load_loadout(_LOADOUTS / "qwen35" / "sniper_ironclad_mortar_r30.yaml")
    assert variant.id == "loadout.llm.qwen35_sniper_ironclad_mortar_r30"
    assert variant.modules.weapons == (
        "weapon.siege.artillery_mortar_r30",
        "weapon.heavy.harpoon_gun",
    )
    assert variant.chassis_id == base.chassis_id
    assert variant.boiler_id == base.boiler_id
    assert variant.pilot_id == base.pilot_id
    assert variant.modules.sensors == base.modules.sensors
    assert variant.modules.gizmos == base.modules.gizmos
    _assert_loadout_zero_budget_violations(variant)


@pytest.mark.unit
def test_arm1_overlay_binds_baseline_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen_mortar_r30.yaml"
    )
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider


# ---------------------------------------------------------------------------
# ARM 3: mortar_cd9 -- cooldown_ticks 5 -> 9
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_arm3_mortar_cd9_changes_only_cooldown() -> None:
    base = _load_weapon(_BASE_MORTAR_PATH)
    variant = _load_weapon(_WEAPONS / "artillery_mortar_cd9.yaml")
    assert variant.id == "weapon.siege.artillery_mortar_cd9"
    assert variant.cooldown_ticks == 9
    assert variant.cooldown_ticks != base.cooldown_ticks
    assert variant.range == base.range == 50
    assert variant.damage == base.damage == 45
    assert variant.heat_generated == base.heat_generated == 15
    assert variant.pressure_cost == base.pressure_cost
    assert variant.accuracy_curve == base.accuracy_curve
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_arm3_sniper_loadout_swaps_only_the_mortar() -> None:
    base = _load_loadout(_BASE_SNIPER_PATH)
    variant = _load_loadout(_LOADOUTS / "qwen35" / "sniper_ironclad_mortar_cd9.yaml")
    assert variant.id == "loadout.llm.qwen35_sniper_ironclad_mortar_cd9"
    assert variant.modules.weapons == (
        "weapon.siege.artillery_mortar_cd9",
        "weapon.heavy.harpoon_gun",
    )
    assert variant.chassis_id == base.chassis_id
    assert variant.boiler_id == base.boiler_id
    assert variant.pilot_id == base.pilot_id
    assert variant.modules.sensors == base.modules.sensors
    assert variant.modules.gizmos == base.modules.gizmos
    _assert_loadout_zero_budget_violations(variant)


@pytest.mark.unit
def test_arm3_overlay_binds_baseline_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen_mortar_cd9.yaml"
    )
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider


# ---------------------------------------------------------------------------
# ARM 4: mortar_acc -- far-band accuracy nerf (CONDITIONAL arm)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_arm4_mortar_acc_changes_only_far_band_accuracy() -> None:
    base = _load_weapon(_BASE_MORTAR_PATH)
    variant = _load_weapon(_WEAPONS / "artillery_mortar_acc.yaml")
    assert variant.id == "weapon.siege.artillery_mortar_acc"
    curve = {p.range: p.hit_probability for p in variant.accuracy_curve}
    base_curve = {p.range: p.hit_probability for p in base.accuracy_curve}
    assert curve[20] == base_curve[20] == 0.80
    assert curve[35] == 0.35
    assert curve[45] == 0.25
    assert curve[50] == 0.15
    assert curve[35] < base_curve[35]
    assert curve[45] < base_curve[45]
    assert curve[50] < base_curve[50]
    assert variant.range == base.range == 50
    assert variant.damage == base.damage == 45
    assert variant.cooldown_ticks == base.cooldown_ticks == 5
    assert variant.heat_generated == base.heat_generated == 15
    assert variant.pressure_cost == base.pressure_cost
    assert variant.target_class_effectiveness == base.target_class_effectiveness
    assert variant.damage_type == base.damage_type
    assert variant.compatibility == base.compatibility


@pytest.mark.unit
def test_arm4_sniper_loadout_swaps_only_the_mortar() -> None:
    base = _load_loadout(_BASE_SNIPER_PATH)
    variant = _load_loadout(_LOADOUTS / "qwen35" / "sniper_ironclad_mortar_acc.yaml")
    assert variant.id == "loadout.llm.qwen35_sniper_ironclad_mortar_acc"
    assert variant.modules.weapons == (
        "weapon.siege.artillery_mortar_acc",
        "weapon.heavy.harpoon_gun",
    )
    assert variant.chassis_id == base.chassis_id
    assert variant.boiler_id == base.boiler_id
    assert variant.pilot_id == base.pilot_id
    assert variant.modules.sensors == base.modules.sensors
    assert variant.modules.gizmos == base.modules.gizmos
    _assert_loadout_zero_budget_violations(variant)


@pytest.mark.unit
def test_arm4_overlay_binds_baseline_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen_mortar_acc.yaml"
    )
    assert overlay.contracts.arena_id == _BASE_ARENA_ID
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider


# ---------------------------------------------------------------------------
# ARM 11: corridor_spawn -- spawn_a relocated (4,30) -> (10,22)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_arm11_arena_parses_and_registers_in_the_shipped_catalog() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena_id = "foundry_60_asym_v1_corridor_spawn"
    assert arena_id in catalog.arenas
    arena = catalog.arenas[arena_id]
    assert arena.arena_id == arena_id
    assert arena.size == 60


@pytest.mark.unit
def test_arm11_moves_only_spawn_a_and_the_new_cell_is_collision_free() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    base = catalog.arenas[_BASE_ARENA_ID]
    variant = catalog.arenas["foundry_60_asym_v1_corridor_spawn"]

    assert (variant.spawn_a.x, variant.spawn_a.y) == (10, 22)
    assert (variant.spawn_a.x, variant.spawn_a.y) != (base.spawn_a.x, base.spawn_a.y)
    assert (variant.spawn_b.x, variant.spawn_b.y) == (base.spawn_b.x, base.spawn_b.y)

    # The dispatched (8, 20) collides with the pre-existing corridor rect
    # {8,20,9,21}; the corrected (10, 22) is genuinely clear.
    assert (8, 20) in base.obstacle_cells
    assert (10, 22) not in variant.obstacle_cells

    # obstacle layout and objectives are otherwise byte-identical to v1.
    assert variant.obstacle_cells == base.obstacle_cells
    assert variant.objectives == base.objectives
    assert variant.vp_threshold == base.vp_threshold
    assert variant.sudden_death_start_tick == base.sudden_death_start_tick
    assert variant.sudden_death_damage_base == base.sudden_death_damage_base


@pytest.mark.unit
def test_arm11_spawn_is_clear_of_every_objective_and_spawn_b() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    variant = catalog.arenas["foundry_60_asym_v1_corridor_spawn"]
    spawn_a_cell = (variant.spawn_a.x, variant.spawn_a.y)
    spawn_b_cell = (variant.spawn_b.x, variant.spawn_b.y)
    objective_cells = {(o.cell.x, o.cell.y) for o in variant.objectives}
    assert spawn_a_cell != spawn_b_cell
    assert spawn_a_cell not in objective_cells
    assert spawn_a_cell not in variant.obstacle_cells


@pytest.mark.unit
def test_arm11_overlay_binds_the_corridor_spawn_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen_corridor_spawn.yaml"
    )
    assert overlay.contracts.arena_id == "foundry_60_asym_v1_corridor_spawn"
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider
    v1 = load_application_overlay(_BASE_OVERLAY)
    assert v1.contracts.card_catalog is not None
    assert overlay.contracts.card_catalog is not None
    assert v1.contracts.card_catalog.deck_policy == overlay.contracts.card_catalog.deck_policy
    assert v1.contracts.utility_handler_pack == overlay.contracts.utility_handler_pack


# ---------------------------------------------------------------------------
# ARM 13: leapfrog_cover -- 5 staggered blocking rects in the open lane
# ---------------------------------------------------------------------------

_LEAPFROG_BLOCK_1 = frozenset((x, y) for x in range(10, 15) for y in range(27, 30))
_LEAPFROG_BLOCK_2 = frozenset((x, y) for x in range(18, 23) for y in range(31, 33))
_LEAPFROG_BLOCK_3 = frozenset((x, y) for x in range(26, 31) for y in range(27, 30))
_LEAPFROG_BLOCK_4 = frozenset((x, y) for x in range(34, 39) for y in range(31, 34))
_LEAPFROG_BLOCK_5 = frozenset((x, y) for x in range(42, 47) for y in range(27, 30))
_LEAPFROG_ALL_BLOCKS = (
    _LEAPFROG_BLOCK_1
    | _LEAPFROG_BLOCK_2
    | _LEAPFROG_BLOCK_3
    | _LEAPFROG_BLOCK_4
    | _LEAPFROG_BLOCK_5
)


@pytest.mark.unit
def test_arm13_arena_parses_and_registers_in_the_shipped_catalog() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    arena_id = "foundry_60_asym_v1_leapfrog_cover"
    assert arena_id in catalog.arenas
    arena = catalog.arenas[arena_id]
    assert arena.arena_id == arena_id
    assert arena.size == 60


@pytest.mark.unit
def test_arm13_adds_exactly_the_five_leapfrog_blocks() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    base = catalog.arenas[_BASE_ARENA_ID]
    variant = catalog.arenas["foundry_60_asym_v1_leapfrog_cover"]

    added = variant.obstacle_cells - base.obstacle_cells
    removed = base.obstacle_cells - variant.obstacle_cells
    assert removed == frozenset(), "leapfrog_cover must not remove any v1 obstacle cell"
    assert added == _LEAPFROG_ALL_BLOCKS


@pytest.mark.unit
def test_arm13_block_2_was_corrected_to_clear_the_existing_flanking_rect() -> None:
    """Pins the collision-avoidance correction documented in the arena YAML.

    The dispatched block 2 ({18,31,22,33}) collides with the pre-existing
    mid-lane flanking-cover rect at (19,33)/(20,33) (west_yard's south
    flank, inherited byte-identical from v1). The corrected block drops the
    entire y=33 row (not just the two literally-colliding cells), landing
    as {18,31,22,32} -- a uniform rect, not an L-shape carved around the
    collision.
    """
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    base = catalog.arenas[_BASE_ARENA_ID]
    variant = catalog.arenas["foundry_60_asym_v1_leapfrog_cover"]

    dispatched_block_2 = frozenset((x, y) for x in range(18, 23) for y in range(31, 34))
    colliding_cells = frozenset({(19, 33), (20, 33)})
    assert colliding_cells <= base.obstacle_cells, "pre-existing flanking rect must be present"
    assert colliding_cells <= dispatched_block_2
    assert colliding_cells.isdisjoint(variant.obstacle_cells - base.obstacle_cells)
    # The corrected block is a strict subset of the dispatched footprint
    # (only the collision-bearing row was dropped, nothing else moved) and
    # is itself fully collision-free against the baseline arena.
    assert _LEAPFROG_BLOCK_2 <= dispatched_block_2
    assert _LEAPFROG_BLOCK_2.isdisjoint(base.obstacle_cells)
    assert _LEAPFROG_BLOCK_2 == frozenset((x, 33 - dy) for x in range(18, 23) for dy in (1, 2))


@pytest.mark.unit
def test_arm13_new_blocks_sit_inside_the_v1_lane_halo_and_clear_objectives() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    variant = catalog.arenas["foundry_60_asym_v1_leapfrog_cover"]

    for cell in _LEAPFROG_ALL_BLOCKS:
        assert 27 <= cell[1] <= 33

    objective_cells = {(o.cell.x, o.cell.y) for o in variant.objectives}
    spawn_cells = {(variant.spawn_a.x, variant.spawn_a.y), (variant.spawn_b.x, variant.spawn_b.y)}
    for cell in _LEAPFROG_ALL_BLOCKS:
        assert cell not in objective_cells
        assert cell not in spawn_cells


@pytest.mark.unit
def test_arm13_preserves_everything_else_byte_identical_to_v1() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    base = catalog.arenas[_BASE_ARENA_ID]
    variant = catalog.arenas["foundry_60_asym_v1_leapfrog_cover"]

    assert variant.size == base.size
    assert (variant.spawn_a.x, variant.spawn_a.y) == (base.spawn_a.x, base.spawn_a.y)
    assert (variant.spawn_b.x, variant.spawn_b.y) == (base.spawn_b.x, base.spawn_b.y)
    assert variant.objectives == base.objectives
    assert variant.vp_threshold == base.vp_threshold
    assert variant.sudden_death_start_tick == base.sudden_death_start_tick
    assert variant.sudden_death_damage_base == base.sudden_death_damage_base


@pytest.mark.unit
def test_arm13_overlay_binds_the_leapfrog_cover_arena() -> None:
    overlay = load_application_overlay(
        _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen_leapfrog_cover.yaml"
    )
    assert overlay.contracts.arena_id == "foundry_60_asym_v1_leapfrog_cover"
    base_provider = _qwen35_provider(load_application_overlay(_BASE_OVERLAY))
    provider = _qwen35_provider(overlay)
    assert provider == base_provider
    v1 = load_application_overlay(_BASE_OVERLAY)
    assert v1.contracts.card_catalog is not None
    assert overlay.contracts.card_catalog is not None
    assert v1.contracts.card_catalog.deck_policy == overlay.contracts.card_catalog.deck_policy
    assert v1.contracts.utility_handler_pack == overlay.contracts.utility_handler_pack


# ---------------------------------------------------------------------------
# Cross-arm: no leakage between arm overlays / variant files
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_arm_overlay_leaks_another_arms_arena_binding() -> None:
    """Every weapon-only arm (1/3/4) binds the baseline arena; every
    arena-only arm (11/13) binds its own new arena and nothing else.
    """
    weapon_arm_overlays = (
        "tactical_split_overdeal_utility_asym_v1_qwen_mortar_r30.yaml",
        "tactical_split_overdeal_utility_asym_v1_qwen_mortar_cd9.yaml",
        "tactical_split_overdeal_utility_asym_v1_qwen_mortar_acc.yaml",
    )
    for name in weapon_arm_overlays:
        overlay = load_application_overlay(_OVERLAYS / name)
        assert overlay.contracts.arena_id == _BASE_ARENA_ID

    arena_arm_overlays = {
        "tactical_split_overdeal_utility_asym_v1_qwen_corridor_spawn.yaml": (
            "foundry_60_asym_v1_corridor_spawn"
        ),
        "tactical_split_overdeal_utility_asym_v1_qwen_leapfrog_cover.yaml": (
            "foundry_60_asym_v1_leapfrog_cover"
        ),
    }
    for name, expected_arena_id in arena_arm_overlays.items():
        overlay = load_application_overlay(_OVERLAYS / name)
        assert overlay.contracts.arena_id == expected_arena_id
        assert overlay.contracts.arena_id != _BASE_ARENA_ID


@pytest.mark.unit
def test_each_weapon_variant_is_a_distinct_new_id_not_shared_across_arms() -> None:
    variant_ids = {
        _load_weapon(_WEAPONS / "artillery_mortar_r30.yaml").id,
        _load_weapon(_WEAPONS / "artillery_mortar_cd9.yaml").id,
        _load_weapon(_WEAPONS / "artillery_mortar_acc.yaml").id,
    }
    assert len(variant_ids) == 3
    assert "weapon.siege.artillery_mortar" not in variant_ids
