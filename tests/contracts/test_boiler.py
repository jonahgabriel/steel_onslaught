"""Tests for boiler contract model — Task 8."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.boiler import (
    ModelSOBoilerCompatibility,
    ModelSOBoilerSpec,
    ModelSOBoilerState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONTRACTS_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "boilers"


def _load_spec(name: str) -> ModelSOBoilerSpec:
    raw = yaml.safe_load((_CONTRACTS_DATA / name).read_text())
    return ModelSOBoilerSpec.model_validate(raw)


def _compat(*classes: str) -> ModelSOBoilerCompatibility:
    return ModelSOBoilerCompatibility(compatible_chassis_classes=classes)


def _minimal_spec(**overrides: object) -> ModelSOBoilerSpec:
    """Build a valid ModelSOBoilerSpec with optional field overrides."""
    defaults: dict[str, object] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.boiler",
        "id": "boiler.test.minimal",
        "display_name": "Minimal Test Boiler",
        "pressure_capacity": 90,
        "regen_per_tick": 5,
        "heat_capacity": 100,
        "heat_multiplier": 1.0,
        "vent_rate": 4,
        "redline_threshold": 80,
        "rupture_threshold": 100,
        "instability_curve": "linear",
        "repairability": "none",
        "mass": 20,
        "compatibility": _compat("heavy"),
    }
    defaults.update(overrides)
    return ModelSOBoilerSpec.model_validate(defaults)


# ---------------------------------------------------------------------------
# YAML spec loading
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compact_v1_loads() -> None:
    spec = _load_spec("compact_v1.yaml")
    assert spec.id.startswith("boiler.")
    assert spec.kind == "steel_onslaught.boiler"


@pytest.mark.unit
def test_industrial_bessemer_90_loads() -> None:
    spec = _load_spec("industrial_bessemer_90.yaml")
    assert spec.id == "boiler.industrial.bessemer_90"
    assert spec.kind == "steel_onslaught.boiler"


@pytest.mark.unit
def test_volatile_v1_loads() -> None:
    spec = _load_spec("volatile_v1.yaml")
    assert spec.id.startswith("boiler.")
    assert spec.kind == "steel_onslaught.boiler"


# ---------------------------------------------------------------------------
# Design example values (§10.3 — design doc bessemer example)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bessemer_90_pressure_capacity() -> None:
    """bessemer_90 has max 90 pressure per design §10.3."""
    spec = _load_spec("industrial_bessemer_90.yaml")
    assert spec.pressure_capacity == 90


@pytest.mark.unit
def test_bessemer_90_vent_rate() -> None:
    """bessemer_90 has vent_rate 4 per design §10.3."""
    spec = _load_spec("industrial_bessemer_90.yaml")
    assert spec.vent_rate == 4


# ---------------------------------------------------------------------------
# Validation invariants — ModelSOBoilerSpec
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redline_equal_rupture_enforced() -> None:
    """redline_threshold must be strictly less than rupture_threshold (equal is invalid)."""
    with pytest.raises(ValueError):
        _minimal_spec(redline_threshold=100, rupture_threshold=100)


@pytest.mark.unit
def test_redline_greater_than_rupture_enforced() -> None:
    """redline_threshold must be strictly less than rupture_threshold."""
    with pytest.raises(ValueError):
        _minimal_spec(redline_threshold=110, rupture_threshold=100)


@pytest.mark.unit
def test_invalid_instability_curve_rejected() -> None:
    """instability_curve must be linear|quadratic|exponential."""
    with pytest.raises(ValueError):
        _minimal_spec(instability_curve="sinusoidal")


@pytest.mark.unit
def test_invalid_repairability_rejected() -> None:
    """repairability must be none|partial|full."""
    with pytest.raises(ValueError):
        _minimal_spec(repairability="unknown")


@pytest.mark.unit
def test_negative_mass_rejected() -> None:
    """mass must be positive (gt=0)."""
    with pytest.raises(ValueError):
        _minimal_spec(mass=-1)


@pytest.mark.unit
def test_zero_mass_rejected() -> None:
    """mass must be strictly positive."""
    with pytest.raises(ValueError):
        _minimal_spec(mass=0)


# ---------------------------------------------------------------------------
# Validation invariants — ModelSOBoilerState
# ---------------------------------------------------------------------------


def _make_state(**overrides: object) -> ModelSOBoilerState:
    """Build a valid ModelSOBoilerState with optional field overrides."""
    defaults: dict[str, object] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.boiler_state",
        "match_id": "match.test.001",
        "mech_id": "mech.red.01",
        "tick": 10,
        "pressure_current": 50,
        "pressure_maximum": 90,
        "regeneration_per_tick": 5,
        "heat_current": 72,
        "heat_redline_threshold": 80,
        "heat_rupture_threshold": 100,
        "heat_vent_rate": 4,
        "status_redline": False,
        "status_rupture_warning": False,
        "status_disabled": False,
        "status_ruptured": False,
        "modifier_heat_weapon_pressure": 1.0,
        "modifier_venting_penalty": 0.0,
        "modifier_mode_switch_heat_delta": 0,
    }
    defaults.update(overrides)
    return ModelSOBoilerState.model_validate(defaults)


@pytest.mark.unit
def test_boiler_state_current_heat_above_rupture_is_invalid() -> None:
    """Rupture is terminal — a state with current_heat > rupture_threshold is invalid."""
    with pytest.raises(ValueError):
        _make_state(heat_current=105, heat_rupture_threshold=100)


@pytest.mark.unit
def test_boiler_state_heat_at_rupture_is_valid() -> None:
    """heat_current == rupture_threshold is accepted (rupture event itself, not exceeded)."""
    state = _make_state(heat_current=100, heat_rupture_threshold=100)
    assert state.heat_current == 100


# ---------------------------------------------------------------------------
# BoilerState valid construction (§10.3 example values)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_boiler_state_valid_construction() -> None:
    """A valid boiler state matching §10.3 example values constructs correctly."""
    state = ModelSOBoilerState(
        schema_version="0.1.0",
        kind="steel_onslaught.boiler_state",
        match_id="match.2026-04-30.001",
        mech_id="mech.red.01",
        tick=142,
        pressure_current=64,
        pressure_maximum=90,
        regeneration_per_tick=5,
        heat_current=72,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=4,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.15,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=8,
    )
    assert state.pressure_current == 64
    assert state.heat_current == 72
    assert not state.status_redline
    assert not state.status_ruptured


@pytest.mark.unit
def test_boiler_state_round_trip_json() -> None:
    """ModelSOBoilerState round-trips through JSON."""
    state = ModelSOBoilerState(
        schema_version="0.1.0",
        kind="steel_onslaught.boiler_state",
        match_id="match.2026-04-30.001",
        mech_id="mech.red.01",
        tick=142,
        pressure_current=64,
        pressure_maximum=90,
        regeneration_per_tick=5,
        heat_current=72,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=4,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.15,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=8,
    )
    blob = state.model_dump_json()
    parsed = ModelSOBoilerState.model_validate_json(blob)
    assert parsed == state
