"""Tests for ModelSOChassisSpec — invariants per plan Task 7."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.chassis import ModelSOChassisSpec

_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "chassis"


def _load(fname: str) -> ModelSOChassisSpec:
    return ModelSOChassisSpec.model_validate(yaml.safe_load((_DATA / fname).read_text()))


@pytest.mark.unit
def test_light_scout_mk1_loads() -> None:
    spec = _load("light_scout_mk1.yaml")
    assert spec.chassis_class == "light"
    assert spec.constraints.base_signature < 50


@pytest.mark.unit
def test_medium_hunter_mk1_loads() -> None:
    spec = _load("medium_hunter_mk1.yaml")
    assert spec.chassis_class == "medium"


@pytest.mark.unit
def test_heavy_ironclad_mk1_loads() -> None:
    spec = _load("heavy_ironclad_mk1.yaml")
    assert spec.chassis_class == "heavy"
    assert spec.constraints.max_boiler_volume == 90
    assert spec.constraints.base_speed == 2


@pytest.mark.unit
def test_all_three_yaml_specs_load() -> None:
    for fname in ("light_scout_mk1.yaml", "medium_hunter_mk1.yaml", "heavy_ironclad_mk1.yaml"):
        spec = _load(fname)
        assert spec.kind == "steel_onslaught.chassis"
        assert spec.schema_version == "0.1.0"


@pytest.mark.unit
def test_rejects_invalid_chassis_class() -> None:
    with pytest.raises(ValidationError):
        ModelSOChassisSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.chassis",
                "id": "chassis.medium.test",
                "display_name": "Test",
                "chassis_class": "ultra",
                "constraints": {
                    "max_mass": 100,
                    "max_module_slots": 6,
                    "max_boiler_volume": 60,
                    "base_speed": 4,
                    "base_turn_rate": 3,
                    "base_signature": 50,
                    "base_vent_rate": 3,
                    "base_hp": 100,
                    "base_armor": 10,
                },
                "compatibility": {
                    "weapon_classes": ["light", "medium"],
                    "boiler_classes": ["industrial"],
                    "mobility_classes": ["tracked"],
                },
                "penalties": {
                    "mode_switch_latency_modifier": 1.0,
                    "sensor_lock_penalty": 1.0,
                    "heat_weapon_vulnerability": 1.0,
                },
            }
        )


@pytest.mark.unit
def test_rejects_negative_max_mass() -> None:
    with pytest.raises(ValidationError):
        ModelSOChassisSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.chassis",
                "id": "chassis.light.test",
                "display_name": "Test",
                "chassis_class": "light",
                "constraints": {
                    "max_mass": -1,
                    "max_module_slots": 4,
                    "max_boiler_volume": 40,
                    "base_speed": 6,
                    "base_turn_rate": 4,
                    "base_signature": 30,
                    "base_vent_rate": 2,
                    "base_hp": 60,
                    "base_armor": 6,
                },
                "compatibility": {
                    "weapon_classes": ["light"],
                    "boiler_classes": ["compact"],
                    "mobility_classes": ["wheeled"],
                },
                "penalties": {
                    "mode_switch_latency_modifier": 1.0,
                    "sensor_lock_penalty": 1.0,
                    "heat_weapon_vulnerability": 1.0,
                },
            }
        )


@pytest.mark.unit
def test_id_pattern_matches_spec() -> None:
    pattern = r"^chassis\.(light|medium|heavy)\.[a-z0-9_]+$"
    for fname in ("light_scout_mk1.yaml", "medium_hunter_mk1.yaml", "heavy_ironclad_mk1.yaml"):
        spec = _load(fname)
        assert re.match(pattern, spec.id), f"id={spec.id!r} does not match pattern"


@pytest.mark.unit
def test_penalties_are_at_least_1() -> None:
    for fname in ("light_scout_mk1.yaml", "medium_hunter_mk1.yaml", "heavy_ironclad_mk1.yaml"):
        spec = _load(fname)
        assert spec.penalties.mode_switch_latency_modifier >= 1.0
        assert spec.penalties.sensor_lock_penalty >= 1.0
        assert spec.penalties.heat_weapon_vulnerability >= 1.0


@pytest.mark.unit
def test_compatibility_lists_are_nonempty() -> None:
    for fname in ("light_scout_mk1.yaml", "medium_hunter_mk1.yaml", "heavy_ironclad_mk1.yaml"):
        spec = _load(fname)
        assert len(spec.compatibility.weapon_classes) > 0
        assert len(spec.compatibility.boiler_classes) > 0
        assert len(spec.compatibility.mobility_classes) > 0


@pytest.mark.unit
def test_base_hp_and_armor_increase_with_chassis_class() -> None:
    """Durability is now chassis-driven: light < medium < heavy on both axes."""
    light = _load("light_scout_mk1.yaml").constraints
    medium = _load("medium_hunter_mk1.yaml").constraints
    heavy = _load("heavy_ironclad_mk1.yaml").constraints
    assert light.base_hp < medium.base_hp < heavy.base_hp
    assert light.base_armor < medium.base_armor < heavy.base_armor


@pytest.mark.unit
def test_medium_matches_legacy_constants() -> None:
    """Medium chassis matches the pre-contract provisional hull/armor (100/10),
    so existing medium-vs-medium fixtures stay numerically stable."""
    medium = _load("medium_hunter_mk1.yaml").constraints
    assert medium.base_hp == 100
    assert medium.base_armor == 10


@pytest.mark.unit
def test_rejects_zero_base_hp() -> None:
    with pytest.raises(ValidationError):
        ModelSOChassisSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.chassis",
                "id": "chassis.light.test",
                "display_name": "Test",
                "chassis_class": "light",
                "constraints": {
                    "max_mass": 60,
                    "max_module_slots": 4,
                    "max_boiler_volume": 40,
                    "base_speed": 6,
                    "base_turn_rate": 4,
                    "base_signature": 30,
                    "base_vent_rate": 2,
                    "base_hp": 0,
                    "base_armor": 6,
                },
                "compatibility": {
                    "weapon_classes": ["light"],
                    "boiler_classes": ["compact"],
                    "mobility_classes": ["wheeled"],
                },
                "penalties": {
                    "mode_switch_latency_modifier": 1.0,
                    "sensor_lock_penalty": 1.0,
                    "heat_weapon_vulnerability": 1.0,
                },
            }
        )
