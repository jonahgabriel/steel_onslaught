"""Deep-immutability and canonical-JSON parity for shipped contract models."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, TypeAdapter, ValidationError

from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import ModelSOGizmoSpec
from steel_onslaught.contracts.mode import ModelSOModeSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.immutable import FrozenJSONMapping

_ROOT = Path(__file__).parents[2] / "contracts_data"


def _load(model: type[BaseModel], relative_path: str) -> tuple[BaseModel, dict[str, object]]:
    raw = yaml.safe_load((_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return model.model_validate(raw), raw


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "relative_path"),
    [
        (ModelSOBoilerSpec, "boilers/compact_v1.yaml"),
        (ModelSOChassisSpec, "chassis/light_scout_mk1.yaml"),
        (ModelSOWeaponSpec, "weapons/machine_gun.yaml"),
        (ModelSOModeSpec, "modes/recon.yaml"),
        (ModelSOGizmoSpec, "gizmos/emergency_condenser.yaml"),
    ],
)
def test_immutable_contract_collections_preserve_json_shape(
    model: type[BaseModel],
    relative_path: str,
) -> None:
    contract, raw = _load(model, relative_path)

    assert contract.model_dump(mode="json") == raw
    assert model.model_validate_json(contract.model_dump_json()) == contract


@pytest.mark.unit
def test_boiler_and_chassis_compatibility_collections_cannot_append() -> None:
    boiler, _ = _load(ModelSOBoilerSpec, "boilers/compact_v1.yaml")
    chassis, _ = _load(ModelSOChassisSpec, "chassis/light_scout_mk1.yaml")
    assert isinstance(boiler, ModelSOBoilerSpec)
    assert isinstance(chassis, ModelSOChassisSpec)

    with pytest.raises(AttributeError):
        boiler.compatibility.compatible_chassis_classes.append("heavy")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        chassis.compatibility.weapon_classes.append("siege")  # type: ignore[attr-defined]


@pytest.mark.unit
def test_weapon_nested_collections_cannot_append() -> None:
    weapon, _ = _load(ModelSOWeaponSpec, "weapons/machine_gun.yaml")
    assert isinstance(weapon, ModelSOWeaponSpec)

    with pytest.raises(AttributeError):
        weapon.accuracy_curve.append(weapon.accuracy_curve[0])  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        weapon.compatibility.compatible_chassis_classes.append("heavy")  # type: ignore[attr-defined]


@pytest.mark.unit
def test_mode_collections_and_nested_mapping_cannot_mutate() -> None:
    mode, _ = _load(ModelSOModeSpec, "modes/recon.yaml")
    assert isinstance(mode, ModelSOModeSpec)
    assert isinstance(mode.passive_modifiers, Mapping)
    assert not isinstance(mode.passive_modifiers, dict)

    with pytest.raises(AttributeError):
        mode.active_systems.append("weapon")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        mode.default_priorities.append("fire")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        mode.passive_modifiers["speed_multiplier"] = 99  # type: ignore[index]


@pytest.mark.unit
def test_gizmo_collections_and_deep_mapping_cannot_mutate() -> None:
    gizmo, _ = _load(ModelSOGizmoSpec, "gizmos/emergency_condenser.yaml")
    assert isinstance(gizmo, ModelSOGizmoSpec)
    on_redline = gizmo.effects["on_redline"]
    compatible = gizmo.constraints["compatible_chassis"]
    assert isinstance(on_redline, Mapping)
    assert isinstance(compatible, tuple)

    with pytest.raises(TypeError):
        on_redline["vent_bonus"] = 999  # type: ignore[index]
    with pytest.raises(AttributeError):
        compatible.append("light")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        gizmo.forbidden_stacking.append("gizmo.test.other")  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_frozen_json_mapping_rejects_non_finite_numbers(value: float) -> None:
    adapter: TypeAdapter[Mapping[str, Any]] = TypeAdapter(FrozenJSONMapping)

    with pytest.raises(ValidationError, match="finite"):
        adapter.validate_python({"nested": [0.25, {"value": value}]})


@pytest.mark.unit
def test_frozen_json_mapping_preserves_finite_float_json_parity() -> None:
    adapter: TypeAdapter[Mapping[str, Any]] = TypeAdapter(FrozenJSONMapping)
    raw = {"nested": [0.25, {"value": -12.5}]}

    frozen = adapter.validate_python(raw)

    assert adapter.dump_python(frozen, mode="json") == raw
