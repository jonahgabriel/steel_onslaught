"""Golden fixture generator — run BEFORE refactoring any archetype.

Usage:
    uv run --no-sync python -m tests.pilots.golden.generate aggressive
    uv run --no-sync python -m tests.pilots.golden.generate defensive
    uv run --no-sync python -m tests.pilots.golden.generate predictive

Instantiates the CURRENT (hardcoded) archetype pilot, runs it over the shared
observation battery, and writes:
    tests/pilots/golden/{archetype}_golden.json

The JSON structure is compact — the battery is ~2.7 M observations which makes
storing full decision dicts impractical (>1 GB).  Instead the fixture stores
per-decision SHA-256 hashes and a single root hash that covers all of them:

    {
        "metadata": {
            "archetype": "<name>",
            "battery_size": <int>,
            "generated_from": "hardcoded <archetype> pilot, pre-refactor"
        },
        "decision_hashes": ["<hex32>", ...],   // one per observation, in order
        "root_hash": "<hex64>"                  // sha256 of all hashes concatenated
    }

The root_hash is the primary oracle.  decision_hashes lets a failing test
binary-search for the first divergent observation without re-running the
generator.

The per-decision hash is sha256(json.dumps(decision.model_dump(), sort_keys=True,
separators=(',',':'))).hexdigest().
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from steel_onslaught.pilots.schemas import ModelSOPilotDecision, PilotProtocol

_GOLDEN_DIR = Path(__file__).parent


def _decision_hash(decision: ModelSOPilotDecision) -> str:
    """Return a 64-hex sha256 digest of the canonical JSON for this decision."""
    canonical = json.dumps(decision.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _root_hash(hashes: list[str]) -> str:
    """Concatenate all per-decision hashes and sha256 the result."""
    return hashlib.sha256("".join(hashes).encode()).hexdigest()


def _generate(archetype: str) -> None:
    from tests.pilots.golden.observation_battery import observation_battery

    battery = observation_battery()

    pilot: PilotProtocol
    if archetype == "aggressive":
        from steel_onslaught.contracts.pilot import ModelSOPilotSpec
        from steel_onslaught.pilots.aggressive import AggressivePilot

        _tmpl = (
            Path(__file__).parent.parent.parent.parent
            / "contracts_data"
            / "pilots"
            / "template_aggressive.yaml"
        )
        _spec = ModelSOPilotSpec.model_validate(yaml.safe_load(_tmpl.read_text()))
        pilot = AggressivePilot(spec=_spec)
    elif archetype == "defensive":
        from steel_onslaught.pilots.defensive import DefensivePilot

        pilot = DefensivePilot()
    elif archetype == "predictive":
        from steel_onslaught.pilots.predictive import PredictivePilot

        pilot = PredictivePilot()
    else:
        raise ValueError(f"Unknown archetype: {archetype!r}")

    hashes = [_decision_hash(pilot.decide(obs)) for obs in battery]

    root = _root_hash(hashes)

    # Store only the root hash + metadata — the per-decision hash list is too
    # large to commit (~60 MB for 900 K observations).  The root hash is the
    # single oracle; the test re-derives it from the refactored pilot and
    # asserts equality.  If the root hash fails, re-run the generator against
    # the OLD hardcoded pilot to reproduce per-decision hashes for debugging.
    output = {
        "metadata": {
            "archetype": archetype,
            "battery_size": len(battery),
            "generated_from": f"hardcoded {archetype.capitalize()}Pilot, pre-refactor",
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
