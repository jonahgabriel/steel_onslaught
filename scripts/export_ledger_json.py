#!/usr/bin/env python
"""Export a recorded match's envelope stream to a committed JSON fixture.

This is the *source of truth* for the frontend golden-replay regression test
(`frontend/src/__tests__/golden_match.test.tsx`). It re-uses the exact read
path and wire serialization the live bridge uses — ``SQLiteLedger.read_all``
(canonical ``tick, sequence_in_tick, event_id`` order) piped through
``ModelSOEventEnvelope.model_dump_json`` (the byte-identity contract from
``cli/serve.py::WebSocketBridge.serialize``) — so the committed fixture is the
real wire stream, not a synthetic hand-built one.

Run (never `python` directly):

    uv run --no-sync python scripts/export_ledger_json.py \
        --ledger /tmp/so-demo/demo.sqlite3 \
        --match match.01KWJWTQAYXA3SXPXRR8NK0NMP \
        --out frontend/src/__tests__/fixtures/golden_match/envelopes.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger


def export(ledger_path: Path, match_id: str, out_path: Path) -> int:
    ledger = SQLiteLedger(ledger_path)
    # `model_dump_json()` is the exact wire form the bridge broadcasts; parsing
    # it back to a dict keeps the fixture a faithful array of wire envelopes
    # (field names/values verbatim) that the TS `parseEnvelope` re-reads.
    envelopes = [json.loads(env.model_dump_json()) for env in ledger.read_all(match_id)]
    if not envelopes:
        raise SystemExit(f"no events found for match {match_id!r} in {ledger_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(envelopes, indent=2, ensure_ascii=False) + "\n")
    return len(envelopes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--match", required=True, dest="match_id")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    count = export(args.ledger, args.match_id, args.out)
    print(f"wrote {count} envelopes -> {args.out}")


if __name__ == "__main__":
    main()
