"""Golden fixture generator (root-hash format) for the shared observation battery.

Usage:
    uv run --no-sync python -m tests.pilots.golden.generate aggressive
    uv run --no-sync python -m tests.pilots.golden.generate defensive
    uv run --no-sync python -m tests.pilots.golden.generate predictive

Instantiates the archetype pilot from its canonical template spec, runs it
over the shared observation battery (32 832 observations), and writes:
    tests/pilots/golden/{archetype}_golden.json

    {
        "metadata": {
            "archetype": "<name>",
            "battery_size": <int>,
            "generated_from": "..."
        },
        "root_hash": "<hex64>"   // sha256 of all per-decision hashes concatenated
    }

The per-decision hash is sha256(json.dumps(decision.model_dump(), sort_keys=True,
separators=(',',':'))).hexdigest().

PROVENANCE WARNING: the committed fixtures were generated from the PRE-REFACTOR
hardcoded pilots (commit 748d499) and are the parity oracle for the spec-driven
refactor.  Re-running this generator now uses the spec-driven pilots, so a
regenerated fixture proves nothing about hardcoded parity — only regenerate
when the battery itself changes deliberately, and say so in the commit.

Note: defensive_golden.json and predictive_golden.json were frozen by their
task implementers in a full-entry format ({"_meta": ..., "entries": [...]})
rather than this root-hash format; their golden tests consume that format
directly.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.pilots.schemas import ModelSOPilotDecision, PilotProtocol

_GOLDEN_DIR = Path(__file__).parent


def _decision_hash(decision: ModelSOPilotDecision) -> str:
    """Return a 64-hex sha256 digest of the canonical JSON for this decision."""
    canonical = json.dumps(decision.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _root_hash(hashes: list[str]) -> str:
    """Concatenate all per-decision hashes and sha256 the result."""
    return hashlib.sha256("".join(hashes).encode()).hexdigest()


def _template_spec(archetype: str) -> ModelSOPilotSpec:
    """Load the canonical template spec YAML for one archetype."""
    template = (
        Path(__file__).parent.parent.parent.parent
        / "contracts_data"
        / "pilots"
        / f"template_{archetype}.yaml"
    )
    return ModelSOPilotSpec.model_validate(yaml.safe_load(template.read_text()))


def _generate(archetype: str) -> None:
    from tests.pilots.golden.observation_battery import observation_battery

    battery = observation_battery()

    pilot: PilotProtocol
    if archetype == "aggressive":
        from steel_onslaught.pilots.aggressive import AggressivePilot

        pilot = AggressivePilot(spec=_template_spec("aggressive"))
    elif archetype == "defensive":
        from steel_onslaught.pilots.defensive import DefensivePilot

        pilot = DefensivePilot(spec=_template_spec("defensive"))
    elif archetype == "predictive":
        from steel_onslaught.pilots.predictive import PredictivePilot

        pilot = PredictivePilot(spec=_template_spec("predictive"))
    else:
        raise ValueError(f"Unknown archetype: {archetype!r}")

    hashes = [_decision_hash(pilot.decide(obs)) for obs in battery]

    root = _root_hash(hashes)

    # Store only the root hash + metadata.  The root hash is the single
    # oracle; the test re-derives it from the spec-driven pilot and asserts
    # equality.  To locate a divergent observation, instantiate the OLD
    # hardcoded pilot (git show 748d499:src/steel_onslaught/pilots/<a>.py)
    # and diff per-decision hashes.
    output = {
        "metadata": {
            "archetype": archetype,
            "battery_size": len(battery),
            "generated_from": f"spec-driven {archetype.capitalize()}Pilot, template spec",
        },
        "root_hash": root,
    }

    out_path = _GOLDEN_DIR / f"{archetype}_golden.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Processed {len(hashes)} decisions, root hash: {root}")
    print(f"Written to {out_path}")


_ARCHETYPES = ["aggressive", "defensive", "predictive"]


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in _ARCHETYPES:
        print(f"Usage: python -m tests.pilots.golden.generate <{'|'.join(_ARCHETYPES)}>")
        sys.exit(1)
    _generate(sys.argv[1])


if __name__ == "__main__":
    main()
