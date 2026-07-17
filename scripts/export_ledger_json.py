#!/usr/bin/env python
"""Export a recorded match's envelope stream to a committed JSON fixture.

This is the *source of truth* for the frontend golden-replay regression test
(`frontend/src/__tests__/golden_match.test.tsx`). It re-uses the exact injected
catalog read path and wire serialization the live bridge uses — ``read_all``
(canonical ``tick, sequence_in_tick, event_id`` order) piped through
``ModelSOEventEnvelope.model_dump_json`` (the byte-identity contract from
``cli/serve.py::WebSocketBridge.serialize``) — so the committed fixture is the
real wire stream, not a synthetic hand-built one.

Run (never `python` directly):

    uv run --no-sync python scripts/export_ledger_json.py \
        --overlay /tmp/so-demo/application.json \
        --match match.01KWJWTQAYXA3SXPXRR8NK0NMP \
        --out frontend/src/__tests__/fixtures/golden_match/envelopes.json
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.ledger.protocol import ReplayEventCatalog
from steel_onslaught.match.composition import load_application_overlay


def export(catalog: ReplayEventCatalog, match_id: str, out_path: Path) -> int:
    """Atomically export canonical model-dump frames from an injected catalog."""
    frames = [envelope.model_dump_json() for envelope in catalog.read_all(match_id)]
    if not frames:
        raise SystemExit(f"no events found for match {match_id!r}")
    document = "[\n  " + ",\n  ".join(frames) + "\n]\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=out_path.parent,
        prefix=f".{out_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, out_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return len(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--match", required=True, dest="match_id")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    overlay = load_application_overlay(args.overlay)
    with CliApplicationFactory.packaged().runtime(overlay) as dependencies:
        count = export(dependencies.ledger, args.match_id, args.out)
    print(f"wrote {count} envelopes -> {args.out}")


if __name__ == "__main__":
    main()
