"""Tests for ModelSOSensorSpec — Task 10."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.sensor import ModelSOSensorSpec

SPECS_DIR = Path(__file__).parent.parent.parent / "contracts_data" / "sensors"


def _load(filename: str) -> ModelSOSensorSpec:
    raw = yaml.safe_load((SPECS_DIR / filename).read_text())
    return ModelSOSensorSpec.model_validate(raw)


# ---------------------------------------------------------------------------
# YAML fixture loading
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_long_range_radar_loads() -> None:
    spec = _load("long_range_radar.yaml")
    assert spec.id == "sensor.long_range_radar"
    assert spec.range == 40
    assert spec.precision == pytest.approx(0.6)
    assert spec.latency_ticks == 1


@pytest.mark.unit
def test_short_range_scanner_loads() -> None:
    spec = _load("short_range_scanner.yaml")
    assert spec.id == "sensor.short_range_scanner"
    assert spec.range == 15
    assert spec.precision == pytest.approx(0.9)
    assert spec.latency_ticks == 0


@pytest.mark.unit
def test_thermal_detector_loads() -> None:
    spec = _load("thermal_detector.yaml")
    assert spec.id == "sensor.thermal_detector"
    # Thermal detects high-heat targets — precision and range are set per design
    assert spec.precision > 0.0
    assert spec.range > 0


@pytest.mark.unit
def test_acoustic_detector_loads() -> None:
    spec = _load("acoustic_detector.yaml")
    assert spec.id == "sensor.acoustic_detector"
    # Acoustic detects fast-moving / high-vent targets
    assert spec.precision > 0.0
    assert spec.range > 0


# ---------------------------------------------------------------------------
# Field invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_four_specs_have_required_fields() -> None:
    files = [
        "long_range_radar.yaml",
        "short_range_scanner.yaml",
        "thermal_detector.yaml",
        "acoustic_detector.yaml",
    ]
    for f in files:
        spec = _load(f)
        assert spec.id.startswith("sensor.")
        assert spec.display_name
        assert spec.range > 0
        assert 0.0 < spec.precision <= 1.0
        assert spec.latency_ticks >= 0
        assert spec.pressure_draw_per_tick >= 0
        assert spec.heat_per_tick >= 0
        assert 0.0 <= spec.jamming_vulnerability_score <= 1.0


@pytest.mark.unit
def test_jamming_vulnerability_rejects_above_one() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorSpec(
            id="sensor.bad",
            display_name="Bad",
            range=10,
            precision=0.5,
            latency_ticks=0,
            pressure_draw_per_tick=1,
            heat_per_tick=0,
            signature_impact=0,
            jamming_vulnerability_score=1.5,
        )


@pytest.mark.unit
def test_jamming_vulnerability_rejects_below_zero() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorSpec(
            id="sensor.bad",
            display_name="Bad",
            range=10,
            precision=0.5,
            latency_ticks=0,
            pressure_draw_per_tick=1,
            heat_per_tick=0,
            signature_impact=0,
            jamming_vulnerability_score=-0.1,
        )


@pytest.mark.unit
def test_precision_rejects_above_one() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorSpec(
            id="sensor.bad",
            display_name="Bad",
            range=10,
            precision=1.1,
            latency_ticks=0,
            pressure_draw_per_tick=1,
            heat_per_tick=0,
            signature_impact=0,
            jamming_vulnerability_score=0.5,
        )


@pytest.mark.unit
def test_precision_rejects_zero_or_below() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorSpec(
            id="sensor.bad",
            display_name="Bad",
            range=10,
            precision=0.0,
            latency_ticks=0,
            pressure_draw_per_tick=1,
            heat_per_tick=0,
            signature_impact=0,
            jamming_vulnerability_score=0.5,
        )


@pytest.mark.unit
def test_range_rejects_non_positive() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorSpec(
            id="sensor.bad",
            display_name="Bad",
            range=0,
            precision=0.5,
            latency_ticks=0,
            pressure_draw_per_tick=1,
            heat_per_tick=0,
            signature_impact=0,
            jamming_vulnerability_score=0.5,
        )


@pytest.mark.unit
def test_latency_ticks_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        ModelSOSensorSpec(
            id="sensor.bad",
            display_name="Bad",
            range=10,
            precision=0.5,
            latency_ticks=-1,
            pressure_draw_per_tick=1,
            heat_per_tick=0,
            signature_impact=0,
            jamming_vulnerability_score=0.5,
        )


@pytest.mark.unit
def test_round_trip_json() -> None:
    spec = _load("long_range_radar.yaml")
    blob = spec.model_dump_json()
    parsed = ModelSOSensorSpec.model_validate_json(blob)
    assert parsed == spec


@pytest.mark.unit
def test_model_is_frozen() -> None:
    spec = _load("short_range_scanner.yaml")
    with pytest.raises(ValidationError):
        spec.range = 999
