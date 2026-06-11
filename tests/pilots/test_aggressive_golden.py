"""Golden parity test for the aggressive pilot — Task 2.

The fixture ``tests/pilots/golden/aggressive_golden.json`` was generated from
the HARDCODED (pre-refactor) AggressivePilot by running:

    uv run --no-sync python -m tests.pilots.golden.generate aggressive

It stores a root hash covering every decision in the battery.  The refactored
spec-driven pilot must produce an identical root hash, proving decision-for-
decision parity across all 199 680 observations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.pilots.aggressive import AggressivePilot
from tests.pilots.golden.observation_battery import observation_battery

_GOLDEN_PATH = Path(__file__).parent / "golden" / "aggressive_golden.json"
_TEMPLATE_YAML = (
    Path(__file__).parent.parent.parent / "contracts_data" / "pilots" / "template_aggressive.yaml"
)


def _load_spec(path: Path) -> ModelSOPilotSpec:
    return ModelSOPilotSpec.model_validate(yaml.safe_load(path.read_text()))


def _decision_hash(decision_dump: dict) -> str:  # type: ignore[type-arg]
    canonical = json.dumps(decision_dump, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _root_hash(hashes: list[str]) -> str:
    return hashlib.sha256("".join(hashes).encode()).hexdigest()


@pytest.mark.unit
def test_template_spec_matches_hardcoded_golden() -> None:
    """The template-spec pilot must reproduce the frozen hardcoded decisions.

    Root hash of all decisions (in battery order) must exactly match the
    fixture generated from the pre-refactor hardcoded AggressivePilot.
    """
    golden = json.loads(_GOLDEN_PATH.read_text())
    spec = _load_spec(_TEMPLATE_YAML)
    pilot = AggressivePilot(spec=spec)
    battery = observation_battery()

    assert len(battery) == golden["metadata"]["battery_size"], (
        f"Battery size changed: got {len(battery)}, "
        f"fixture has {golden['metadata']['battery_size']}. "
        "Regenerate aggressive_golden.json if the battery was intentionally changed."
    )

    hashes = [_decision_hash(pilot.decide(obs).model_dump()) for obs in battery]
    actual_root = _root_hash(hashes)
    expected_root = golden["root_hash"]

    assert actual_root == expected_root, (
        f"AggressivePilot(spec=template) produced a different decision tree "
        f"than the pre-refactor hardcoded pilot.\n"
        f"Expected root hash: {expected_root}\n"
        f"Actual root hash:   {actual_root}\n"
        "Re-run `uv run python -m tests.pilots.golden.generate aggressive` "
        "against the OLD hardcoded pilot to locate the first divergent observation."
    )
