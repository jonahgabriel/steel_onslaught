"""Golden parity test — defensive pilot (Task 3).

Asserts that the spec-driven DefensivePilot constructed from
template_defensive.yaml produces the exact same decision for every
observation in the battery as the frozen hardcoded pilot did when
defensive_golden.json was generated.

The golden fixture is the reference implementation; no heuristic logic is
duplicated in this test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.schemas import ModelSOPilotDecision
from tests.pilots.golden.observation_battery import observation_battery

_REPO_ROOT = Path(__file__).parent.parent.parent
_GOLDEN_PATH = Path(__file__).parent / "golden" / "defensive_golden.json"
_TEMPLATE_PATH = _REPO_ROOT / "contracts_data" / "pilots" / "template_defensive.yaml"


def _load_spec(path: Path) -> ModelSOPilotSpec:
    return ModelSOPilotSpec.model_validate(yaml.safe_load(path.read_text()))


@pytest.mark.unit
def test_template_spec_matches_hardcoded_golden() -> None:
    """Template-spec pilot reproduces every frozen golden decision."""
    spec = _load_spec(_TEMPLATE_PATH)
    pilot = DefensivePilot(spec=spec)
    battery = observation_battery()
    golden_data = json.loads(_GOLDEN_PATH.read_text())
    golden_entries = golden_data["entries"]

    assert len(golden_entries) == len(battery), (
        f"Battery size {len(battery)} does not match golden entry count "
        f"{len(golden_entries)} — regenerate the fixture."
    )

    for entry in golden_entries:
        idx = entry["observation_index"]
        obs = battery[idx]
        expected = ModelSOPilotDecision.model_validate(entry["decision"])
        actual = pilot.decide(obs)
        assert actual == expected, (
            f"Decision mismatch at observation_index={idx}: "
            f"expected action={expected.action!r} reason={expected.reason_code!r}, "
            f"got action={actual.action!r} reason={actual.reason_code!r}"
        )


@pytest.mark.unit
def test_golden_fixture_constants_match_template() -> None:
    """The fire_confidence_floor in the golden fixture metadata equals the template YAML value.

    This test breaks if template_defensive.yaml is updated without regenerating
    the fixture (or vice versa).
    """
    golden_data = json.loads(_GOLDEN_PATH.read_text())
    fixture_confidence = golden_data["_meta"]["constants"]["HIGH_CONFIDENCE_THRESHOLD"]

    spec = _load_spec(_TEMPLATE_PATH)
    from steel_onslaught.contracts.pilot import ModelSODefensivePilotParams

    assert isinstance(spec.parameters, ModelSODefensivePilotParams)
    assert spec.parameters.fire_confidence_floor == fixture_confidence, (
        f"template fire_confidence_floor={spec.parameters.fire_confidence_floor} "
        f"!= fixture constant={fixture_confidence}; "
        "regenerate defensive_golden.json or fix template_defensive.yaml"
    )
