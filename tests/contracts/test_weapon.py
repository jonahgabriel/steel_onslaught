"""Tests for ModelSOWeaponSpec — Task 9."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.weapon import (
    ModelSOAccuracyPoint,
    ModelSOTargetClassEffectiveness,
    ModelSOWeaponCompatibility,
    ModelSOWeaponSpec,
    WeaponDamageType,
)

CONTRACTS_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "weapons"

WEAPON_FILES = [
    "machine_gun.yaml",
    "steam_cannon.yaml",
    "artillery_mortar.yaml",
    "heat_lance.yaml",
    "shrapnel_thrower.yaml",
    "harpoon_gun.yaml",
]


def _valid_weapon_data() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.weapon",
        "id": "weapon.light.test",
        "display_name": "Test Weapon",
        "weapon_class": "light",
        "range": 10,
        "damage": 5,
        "pressure_cost": 5,
        "heat_generated": 3,
        "cooldown_ticks": 1,
        "accuracy_curve": [{"range": 5, "hit_probability": 0.8}],
        "target_class_effectiveness": {"light": 1.0, "medium": 1.0, "heavy": 1.0},
        "damage_type": "standard",
        "compatibility": {"compatible_chassis_classes": ["light"]},
    }


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
                "target_class_effectiveness": {
                    "light": 1.0,
                    "medium": 1.0,
                    "heavy": 1.0,
                },
                "damage_type": "standard",
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
                "target_class_effectiveness": {
                    "light": 1.0,
                    "medium": 1.0,
                    "heavy": 1.0,
                },
                "damage_type": "standard",
                "compatibility": {"compatible_chassis_classes": ["light"]},
            }
        )


@pytest.mark.unit
def test_target_class_effectiveness_values_are_positive() -> None:
    path = CONTRACTS_DATA / "steam_cannon.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    for val in (
        spec.target_class_effectiveness.light,
        spec.target_class_effectiveness.medium,
        spec.target_class_effectiveness.heavy,
    ):
        assert val > 0.0


@pytest.mark.unit
@pytest.mark.parametrize("chassis_class", ["light", "medium", "heavy"])
def test_target_class_effectiveness_requires_every_class(chassis_class: str) -> None:
    data = _valid_weapon_data()
    effectiveness = data["target_class_effectiveness"]
    assert isinstance(effectiveness, dict)
    del effectiveness[chassis_class]

    with pytest.raises(ValidationError, match=chassis_class):
        ModelSOWeaponSpec.model_validate(data)


@pytest.mark.unit
def test_target_class_effectiveness_rejects_unknown_class() -> None:
    data = _valid_weapon_data()
    effectiveness = data["target_class_effectiveness"]
    assert isinstance(effectiveness, dict)
    effectiveness["siege"] = 1.0

    with pytest.raises(ValidationError, match="siege"):
        ModelSOWeaponSpec.model_validate(data)


@pytest.mark.unit
@pytest.mark.parametrize("chassis_class", ["light", "medium", "heavy"])
@pytest.mark.parametrize("multiplier", [0.0, -0.1])
def test_target_class_effectiveness_rejects_non_positive_values(
    chassis_class: str,
    multiplier: float,
) -> None:
    data = _valid_weapon_data()
    effectiveness = data["target_class_effectiveness"]
    assert isinstance(effectiveness, dict)
    effectiveness[chassis_class] = multiplier

    with pytest.raises(ValidationError, match=chassis_class):
        ModelSOWeaponSpec.model_validate(data)


@pytest.mark.unit
def test_target_class_effectiveness_is_frozen() -> None:
    effectiveness = ModelSOTargetClassEffectiveness(light=1.0, medium=1.0, heavy=1.0)

    with pytest.raises(ValidationError, match="frozen"):
        effectiveness.light = 2.0


@pytest.mark.unit
def test_target_class_effectiveness_runtime_absence_fails_closed() -> None:
    corrupted = ModelSOTargetClassEffectiveness.model_construct(light=1.0, medium=1.0)

    with pytest.raises(KeyError, match="heavy"):
        _ = corrupted["heavy"]


@pytest.mark.unit
def test_heat_lance_damage_type_is_heat() -> None:
    """The only heat weapon in the catalog names its damage type explicitly."""
    path = CONTRACTS_DATA / "heat_lance.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    assert spec.damage_type is WeaponDamageType.HEAT


@pytest.mark.unit
@pytest.mark.parametrize(
    "filename",
    ["machine_gun", "steam_cannon", "artillery_mortar", "shrapnel_thrower", "harpoon_gun"],
)
def test_non_heat_weapons_are_standard(filename: str) -> None:
    path = CONTRACTS_DATA / f"{filename}.yaml"
    spec = ModelSOWeaponSpec.model_validate(yaml.safe_load(path.read_text()))
    assert spec.damage_type is WeaponDamageType.STANDARD


@pytest.mark.unit
@pytest.mark.parametrize("field", ["schema_version", "kind", "damage_type"])
def test_contract_identity_and_damage_type_are_required(field: str) -> None:
    data = _valid_weapon_data()
    del data[field]
    with pytest.raises(ValidationError, match=field):
        ModelSOWeaponSpec.model_validate(data)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "data"),
    [
        (ModelSOAccuracyPoint, {"range": 5, "hit_probability": 0.8, "extra": True}),
        (
            ModelSOWeaponCompatibility,
            {"compatible_chassis_classes": ["light"], "extra": True},
        ),
    ],
)
def test_nested_weapon_models_reject_extra_fields(
    model: type[ModelSOAccuracyPoint] | type[ModelSOWeaponCompatibility],
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="extra"):
        model.model_validate(data)


@pytest.mark.unit
def test_nested_weapon_models_are_frozen() -> None:
    point = ModelSOAccuracyPoint(range=5, hit_probability=0.8)
    compatibility = ModelSOWeaponCompatibility(compatible_chassis_classes=["light"])

    with pytest.raises(ValidationError, match="frozen"):
        point.range = 6
    with pytest.raises(ValidationError, match="frozen"):
        compatibility.compatible_chassis_classes = ["heavy"]


@pytest.mark.unit
def test_damage_type_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        ModelSOWeaponSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.weapon",
                "id": "weapon.light.bad",
                "display_name": "Bad",
                "weapon_class": "light",
                "range": 10,
                "damage": 5,
                "pressure_cost": 5,
                "heat_generated": 3,
                "cooldown_ticks": 1,
                "accuracy_curve": [{"range": 5, "hit_probability": 0.8}],
                "target_class_effectiveness": {
                    "light": 1.0,
                    "medium": 1.0,
                    "heavy": 1.0,
                },
                "damage_type": "plasma",  # not a WeaponDamageType member
                "compatibility": {"compatible_chassis_classes": ["light"]},
            }
        )
