"""Tests for ModelSOWeaponSpec — Task 9."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.weapon import ModelSOWeaponSpec

CONTRACTS_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "weapons"

WEAPON_FILES = [
    "machine_gun.yaml",
    "steam_cannon.yaml",
    "artillery_mortar.yaml",
    "heat_lance.yaml",
    "shrapnel_thrower.yaml",
    "harpoon_gun.yaml",
]


@pytest.mark.unit
@pytest.mark.parametrize("filename", WEAPON_FILES)
def test_all_weapon_specs_validate(filename: str) -> None:
    path = CONTRACTS_DATA / filename
    data = yaml.safe_load(path.read_text())
    spec = ModelSOWeaponSpec.model_validate(data)
    assert spec.id


@pytest.mark.unit
def test_machine_gun_invariants() -> None:
    path = CONTRACTS_DATA / "machine_gun.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    assert spec.weapon_class == "light"
    assert spec.range <= 15
    assert spec.cooldown_ticks == 1


@pytest.mark.unit
def test_artillery_mortar_invariants() -> None:
    path = CONTRACTS_DATA / "artillery_mortar.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    assert spec.weapon_class == "siege"
    assert spec.range >= 40


@pytest.mark.unit
def test_weapon_rejects_negative_damage() -> None:
    with pytest.raises(ValidationError):
        ModelSOWeaponSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.weapon",
                "id": "weapon.light.bad",
                "display_name": "Bad Weapon",
                "weapon_class": "light",
                "range": 10,
                "damage": -1,
                "pressure_cost": 5,
                "heat_generated": 3,
                "cooldown_ticks": 1,
                "accuracy_curve": [{"range": 5, "hit_probability": 0.8}],
                "target_class_effectiveness": {"light": 1.0},
                "compatibility": {"compatible_chassis_classes": ["light"]},
            }
        )


@pytest.mark.unit
def test_accuracy_curve_round_trips() -> None:
    path = CONTRACTS_DATA / "machine_gun.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    # accuracy_curve must be a non-empty list of range+hit_probability points
    assert len(spec.accuracy_curve) > 0
    for point in spec.accuracy_curve:
        assert 0.0 <= point.hit_probability <= 1.0
        assert point.range >= 0


@pytest.mark.unit
def test_weapon_rejects_invalid_weapon_class() -> None:
    with pytest.raises(ValidationError):
        ModelSOWeaponSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.weapon",
                "id": "weapon.ultra.bad",
                "display_name": "Ultra Weapon",
                "weapon_class": "ultra",
                "range": 10,
                "damage": 5,
                "pressure_cost": 5,
                "heat_generated": 3,
                "cooldown_ticks": 1,
                "accuracy_curve": [{"range": 5, "hit_probability": 0.8}],
                "target_class_effectiveness": {"light": 1.0},
                "compatibility": {"compatible_chassis_classes": ["light"]},
            }
        )


@pytest.mark.unit
def test_target_class_effectiveness_values_are_positive() -> None:
    path = CONTRACTS_DATA / "steam_cannon.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    for val in spec.target_class_effectiveness.values():
        assert val > 0.0
