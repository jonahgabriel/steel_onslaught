"""Tests for ModelSOLoadout — Task 13 (design §15.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.loadout import (
    ModelSOLoadout,
    ModelSOLoadoutBudgets,
    ModelSOLoadoutModules,
)

_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "loadouts"


def _load(fname: str) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(yaml.safe_load((_DATA / fname).read_text()))


def _budgets() -> ModelSOLoadoutBudgets:
    return ModelSOLoadoutBudgets(
        points_used=10,
        points_max=100,
        mass_used=20,
        mass_max=60,
        slots_used=2,
        slots_max=4,
        expected_heat_peak=5,
        expected_signature=34,
    )


# ---------------------------------------------------------------------------
# Example YAML loadouts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_example_aggressive_light_loads() -> None:
    loadout = _load("example_aggressive_light.yaml")
    assert loadout.id == "loadout.example.aggressive_light"
    assert loadout.kind == "steel_onslaught.loadout"
    assert loadout.schema_version == "0.1.0"
    assert loadout.chassis_id == "chassis.light.scout_mk1"
    assert loadout.boiler_id == "boiler.compact.v1"
    assert loadout.pilot_id.startswith("pilot.")
    assert loadout.modules.weapons  # at least one weapon
    assert loadout.budgets.slots_used <= loadout.budgets.slots_max


@pytest.mark.unit
def test_example_predictive_heavy_loads() -> None:
    """The heavy example mirrors design §15.3 with real contracts_data module ids."""
    loadout = _load("example_predictive_heavy.yaml")
    assert loadout.id == "loadout.example.predictive_heavy"
    assert loadout.chassis_id == "chassis.heavy.ironclad_mk1"
    assert loadout.boiler_id == "boiler.industrial.bessemer_90"
    assert "weapon.siege.artillery_mortar" in loadout.modules.weapons
    assert "sensor.long_range_radar" in loadout.modules.sensors
    assert "gizmo.cooling.emergency_condenser" in loadout.modules.gizmos
    assert loadout.budgets.mass_used <= loadout.budgets.mass_max
    assert loadout.budgets.points_used <= loadout.budgets.points_max


@pytest.mark.unit
def test_all_module_ids_concatenates_every_category() -> None:
    modules = ModelSOLoadoutModules(
        weapons=("weapon.light.machine_gun",),
        sensors=("sensor.short_range_scanner",),
        cooling=("cooling.auxiliary_vent",),
        armor=("armor.reinforced_plating",),
        gizmos=("gizmo.control.targeting_assist",),
    )
    assert modules.all_module_ids() == (
        "weapon.light.machine_gun",
        "sensor.short_range_scanner",
        "cooling.auxiliary_vent",
        "armor.reinforced_plating",
        "gizmo.control.targeting_assist",
    )


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_duplicate_module_id_across_categories_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        ModelSOLoadoutModules(
            weapons=("weapon.light.machine_gun",),
            sensors=("weapon.light.machine_gun",),  # duplicate across categories
        )


@pytest.mark.unit
def test_duplicate_module_id_within_category_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        ModelSOLoadoutModules(weapons=("weapon.light.machine_gun", "weapon.light.machine_gun"))


@pytest.mark.unit
def test_bad_loadout_id_rejected() -> None:
    with pytest.raises(ValidationError, match="loadout"):
        ModelSOLoadout(
            id="not_a_loadout.example",
            chassis_id="chassis.light.scout_mk1",
            boiler_id="boiler.compact.v1",
            pilot_id="pilot.example.aggressive_v1",
            modules=ModelSOLoadoutModules(weapons=("weapon.light.machine_gun",)),
            budgets=_budgets(),
        )


@pytest.mark.unit
def test_chassis_id_namespace_enforced() -> None:
    with pytest.raises(ValidationError):
        ModelSOLoadout(
            id="loadout.example.bad_chassis",
            chassis_id="boiler.compact.v1",  # wrong namespace
            boiler_id="boiler.compact.v1",
            pilot_id="pilot.example.aggressive_v1",
            modules=ModelSOLoadoutModules(weapons=("weapon.light.machine_gun",)),
            budgets=_budgets(),
        )


@pytest.mark.unit
def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ModelSOLoadout.model_validate(
            {
                "id": "loadout.example.extra",
                "chassis_id": "chassis.light.scout_mk1",
                "boiler_id": "boiler.compact.v1",
                "pilot_id": "pilot.example.aggressive_v1",
                "modules": {"weapons": ["weapon.light.machine_gun"]},
                "budgets": _budgets().model_dump(),
                "surprise": True,  # extra field — must be rejected
            }
        )


@pytest.mark.unit
def test_loadout_is_frozen() -> None:
    loadout = _load("example_aggressive_light.yaml")
    with pytest.raises(ValidationError):
        loadout.id = "loadout.example.mutated"


@pytest.mark.unit
def test_loadout_module_collections_are_immutable_and_detached() -> None:
    source = ["weapon.light.machine_gun"]
    modules = ModelSOLoadoutModules.model_validate({"weapons": source})
    source.append("weapon.light.shrapnel_thrower")

    assert modules.weapons == ("weapon.light.machine_gun",)
    with pytest.raises(AttributeError):
        modules.weapons.append("weapon.light.shrapnel_thrower")  # type: ignore[attr-defined]


@pytest.mark.unit
def test_loadout_tuple_collections_preserve_json_array_shape() -> None:
    raw = yaml.safe_load((_DATA / "example_aggressive_light.yaml").read_text())
    loadout = ModelSOLoadout.model_validate(raw)

    assert loadout.model_dump(mode="json") == {**raw, "pilot_spec_path": None}
    assert ModelSOLoadout.model_validate_json(loadout.model_dump_json()) == loadout


@pytest.mark.unit
def test_negative_budget_values_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelSOLoadoutBudgets(
            points_used=-1,
            points_max=100,
            mass_used=20,
            mass_max=60,
            slots_used=2,
            slots_max=4,
            expected_heat_peak=5,
            expected_signature=34,
        )
