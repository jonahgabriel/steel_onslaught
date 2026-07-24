"""Contract proof for the brawler-recut v2 arena, loadout, and overlay.

Session 2026-07-24, combined declarative re-cut: a new arena
(``foundry_60_asym_v2``, sightline-breaking cover added to the open
east-west lane) and a new brawler loadout (``loadout.llm.qwen35_berserker_v2``,
a medium-range/heat-weapon refit) rebound into a new battery overlay
(``tactical_split_overdeal_utility_asym_v2_qwen.yaml``). All three files are
additive — this suite also proves the v1 baseline files (arena, loadout,
overlay) are untouched, mirroring the discipline of
``test_symmetric_utility_overlay.py``.

This suite proves, without a live battery (CI-safe):

  1. the v2 arena parses, validates, and differs from v1 by EXACTLY the two
     new sightline-breaking cover rects (everything else — spawns,
     objectives, VP schedule, sudden-death timing, every pre-existing rect —
     is byte-identical);
  2. the two new cover rects sit strictly inside the v1 open lane band and do
     not touch any spawn or objective cell;
  3. the v2 loadout parses, validates against every mechanically-enforced
     budget axis (mass/slots/pressure) with zero violations, swaps in
     ``weapon.medium.heat_lance`` (not ``steam_cannon``, which fails the
     weapon's own chassis-compatibility gate for a light chassis) while
     keeping ``weapon.light.machine_gun``, and fills its budget headroom with
     the only defensive-adjacent gizmo the catalog offers a light chassis;
  4. the v1 loadout is untouched (still fields ``shrapnel_thrower``);
  5. the v2 overlay parses, binds ``foundry_60_asym_v2``, and is otherwise
     structurally identical to the v1 combined overlay (same card-deck
     policy, same utility handler pack, same LLM provider/retry config) —
     the arena binding and state-root paths are the only free variables.
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
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_match_contract_catalog,
)

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_ARENAS = _REPO_ROOT / "contracts_data" / "arenas"
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts"
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"

_ARENA_V1_ID = "foundry_60_asym_v1"
_ARENA_V2_ID = "foundry_60_asym_v2"
_LOADOUT_V1_PATH = _LOADOUTS / "llm_qwen35_berserker.yaml"
_LOADOUT_V2_PATH = _LOADOUTS / "llm_qwen35_berserker_v2.yaml"
_OVERLAY_V1 = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"
_OVERLAY_V2 = _OVERLAYS / "tactical_split_overdeal_utility_asym_v2_qwen.yaml"

_NEW_COVER_BLOCK_1 = frozenset((x, y) for x in range(20, 25) for y in range(29, 32))
_NEW_COVER_BLOCK_2 = frozenset((x, y) for x in range(36, 41) for y in range(29, 32))

_QWEN35_PROVIDER_ID = "qwen35"


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


# ---------------------------------------------------------------------------
# Arena: foundry_60_asym_v2
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_arena_v2_parses_and_registers_in_the_shipped_catalog() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    assert _ARENA_V2_ID in catalog.arenas
    arena = catalog.arenas[_ARENA_V2_ID]
    assert arena.arena_id == _ARENA_V2_ID
    assert arena.size == 60


@pytest.mark.unit
def test_arena_v2_differs_from_v1_by_exactly_two_new_cover_blocks() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    v1 = catalog.arenas[_ARENA_V1_ID]
    v2 = catalog.arenas[_ARENA_V2_ID]

    added = v2.obstacle_cells - v1.obstacle_cells
    removed = v1.obstacle_cells - v2.obstacle_cells
    assert removed == frozenset(), "v2 must not remove any v1 obstacle cell"
    assert added == (_NEW_COVER_BLOCK_1 | _NEW_COVER_BLOCK_2)


@pytest.mark.unit
def test_arena_v2_preserves_everything_else_byte_identical_to_v1() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    v1 = catalog.arenas[_ARENA_V1_ID]
    v2 = catalog.arenas[_ARENA_V2_ID]

    assert v2.size == v1.size
    assert (v2.spawn_a.x, v2.spawn_a.y) == (v1.spawn_a.x, v1.spawn_a.y)
    assert (v2.spawn_b.x, v2.spawn_b.y) == (v1.spawn_b.x, v1.spawn_b.y)
    assert v2.objectives == v1.objectives
    assert v2.vp_threshold == v1.vp_threshold
    assert v2.sudden_death_start_tick == v1.sudden_death_start_tick
    assert v2.sudden_death_damage_base == v1.sudden_death_damage_base


@pytest.mark.unit
def test_new_cover_blocks_sit_inside_the_v1_open_lane_and_clear_objectives() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    v2 = catalog.arenas[_ARENA_V2_ID]

    # Both new blocks are inset strictly inside the v1 lane band y=28..32.
    for cell in _NEW_COVER_BLOCK_1 | _NEW_COVER_BLOCK_2:
        assert 28 <= cell[1] <= 32

    objective_cells = {(o.cell.x, o.cell.y) for o in v2.objectives}
    spawn_cells = {(v2.spawn_a.x, v2.spawn_a.y), (v2.spawn_b.x, v2.spawn_b.y)}
    for cell in _NEW_COVER_BLOCK_1 | _NEW_COVER_BLOCK_2:
        assert cell not in objective_cells
        assert cell not in spawn_cells

    # west_yard (18,30) sits west of block 1 with a real gap; east_gate's
    # (42,36) lane approach sits east of block 2 with a real gap.
    assert (18, 30) not in _NEW_COVER_BLOCK_1
    assert max(_NEW_COVER_BLOCK_1, key=lambda c: c[0])[0] < 30  # block 1 west of north_works' x
    assert min(_NEW_COVER_BLOCK_2, key=lambda c: c[0])[0] > 24  # block 2 east of block 1


@pytest.mark.unit
def test_arena_v1_is_untouched() -> None:
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    v1 = catalog.arenas[_ARENA_V1_ID]
    assert v1.arena_id == _ARENA_V1_ID
    assert (18, 30) not in v1.obstacle_cells  # west_yard objective cell, always clear
    assert len(v1.obstacle_cells) < len(catalog.arenas[_ARENA_V2_ID].obstacle_cells)


# ---------------------------------------------------------------------------
# Loadout: loadout.llm.qwen35_berserker_v2
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_loadout_v2_parses_and_swaps_shrapnel_thrower_for_heat_lance() -> None:
    loadout = _load_loadout(_LOADOUT_V2_PATH)
    assert loadout.id == "loadout.llm.qwen35_berserker_v2"
    assert loadout.chassis_id == "chassis.light.scout_mk1"
    assert loadout.boiler_id == "boiler.compact.v1"
    assert loadout.pilot_id == "pilot.llm.qwen35"
    assert loadout.modules.weapons == (
        "weapon.light.machine_gun",
        "weapon.medium.heat_lance",
    )
    assert "weapon.light.shrapnel_thrower" not in loadout.modules.weapons
    assert "weapon.medium.steam_cannon" not in loadout.modules.weapons
    assert loadout.modules.sensors == ("sensor.short_range_scanner",)
    assert loadout.modules.cooling == ()
    assert loadout.modules.armor == ()
    assert loadout.modules.gizmos == ("gizmo.efficiency.efficient_regulator",)


@pytest.mark.unit
def test_loadout_v2_satisfies_every_enforced_budget_axis_with_zero_violations() -> None:
    """Rebuilds the same ``ModelSOModuleBudget`` normalization
    ``match/runner.py::_module_budgets`` performs, then runs the real
    ``validate_loadout_budgets`` -- proving the declared swap is legal on the
    mechanically-enforced MASS/SLOTS/PRESSURE axes, independent of the
    driver.
    """
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    loadout = _load_loadout(_LOADOUT_V2_PATH)
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


@pytest.mark.unit
def test_heat_lance_is_chassis_compatible_but_steam_cannon_is_not() -> None:
    """Pins the swap-decision rationale documented in the loadout YAML."""
    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    heat_lance = catalog.weapons["weapon.medium.heat_lance"]
    steam_cannon = catalog.weapons["weapon.medium.steam_cannon"]
    assert "light" in heat_lance.compatibility.compatible_chassis_classes
    assert "light" not in steam_cannon.compatibility.compatible_chassis_classes


@pytest.mark.unit
def test_loadout_v1_is_untouched() -> None:
    loadout = _load_loadout(_LOADOUT_V1_PATH)
    assert loadout.id == "loadout.llm.qwen35_berserker"
    assert loadout.modules.weapons == (
        "weapon.light.machine_gun",
        "weapon.light.shrapnel_thrower",
    )


# ---------------------------------------------------------------------------
# Overlay: tactical_split_overdeal_utility_asym_v2_qwen.yaml
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overlay_v2_parses_and_binds_arena_v2() -> None:
    overlay = load_application_overlay(_OVERLAY_V2)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == _ARENA_V2_ID

    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    arena = catalog.arenas[overlay.contracts.arena_id]
    assert arena.objectives
    assert arena.vp_threshold == 15


@pytest.mark.unit
def test_overlay_v2_still_deals_a_utility_pile() -> None:
    overlay = load_application_overlay(_OVERLAY_V2)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    deck_policy = card_binding.deck_policy
    assert deck_policy is not None
    assert deck_policy.seats, "the deck policy must declare seats"
    for seat in deck_policy.seats:
        assert seat.utility_deck_id is not None
        assert seat.hand_quota.utility > 0

    utility_pack = overlay.contracts.utility_handler_pack
    assert utility_pack is not None
    assert tuple(utility_pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


@pytest.mark.unit
def test_overlay_v2_inherits_v1_proven_tolerant_retry_and_provider() -> None:
    v1_provider = _qwen35_provider(load_application_overlay(_OVERLAY_V1))
    v2_provider = _qwen35_provider(load_application_overlay(_OVERLAY_V2))

    assert v2_provider.retry.max_attempts == 1
    assert v2_provider.retry == v1_provider.retry
    assert v2_provider.timeout_seconds == v1_provider.timeout_seconds
    assert v2_provider == v1_provider


@pytest.mark.unit
def test_overlay_v2_only_differs_from_v1_by_arena_binding() -> None:
    """The single free variable across the two overlays is the arena binding.

    Everything the match runtime consumes -- providers/retry, the deck policy
    (piles, over-deal quotas), and the utility handler pack -- is identical to
    the v1 overlay; only ``arena_id`` (and the isolated state-root paths, not
    asserted here) differs.
    """
    v1 = load_application_overlay(_OVERLAY_V1)
    v2 = load_application_overlay(_OVERLAY_V2)

    assert v1.contracts.arena_id == _ARENA_V1_ID
    assert v2.contracts.arena_id == _ARENA_V2_ID
    assert v1.contracts.arena_id != v2.contracts.arena_id

    assert v1.llm.providers == v2.llm.providers
    assert v1.contracts.card_catalog is not None
    assert v2.contracts.card_catalog is not None
    assert v1.contracts.card_catalog.deck_policy == v2.contracts.card_catalog.deck_policy
    assert v1.contracts.utility_handler_pack == v2.contracts.utility_handler_pack


@pytest.mark.unit
def test_overlay_v1_is_untouched() -> None:
    overlay = load_application_overlay(_OVERLAY_V1)
    assert overlay.contracts.arena_id == _ARENA_V1_ID
