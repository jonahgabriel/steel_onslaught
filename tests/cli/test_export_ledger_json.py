from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.export_ledger_json import export
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from tests.fixtures.event_samples import build_sample_envelopes


class _Catalog:
    def __init__(self, events: tuple[ModelSOEventEnvelope, ...]) -> None:
        self._events = events

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        yield from (event for event in self._events if event.match_id == match_id)

    def read_match_ids(self) -> Iterator[str]:
        yield from sorted({event.match_id for event in self._events})


@pytest.mark.unit
def test_export_uses_injected_catalog_and_preserves_canonical_wire_frames(tmp_path: Path) -> None:
    samples = build_sample_envelopes()
    events = (
        samples[SOEventType.MATCH_STARTED],
        samples[SOEventType.MATCH_TICK],
    )
    out = tmp_path / "nested" / "envelopes.json"
    out.parent.mkdir()
    out.write_text("stale", encoding="utf-8")

    count = export(_Catalog(events), events[0].match_id, out)

    assert count == 2
    assert out.read_text(encoding="utf-8") == (
        "[\n  " + ",\n  ".join(event.model_dump_json() for event in events) + "\n]\n"
    )
    assert list(out.parent.glob(f".{out.name}.*.tmp")) == []


@pytest.mark.unit
def test_export_fails_without_canonical_events(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no events found"):
        export(_Catalog(()), "match.missing", tmp_path / "missing.json")


@pytest.mark.unit
def test_export_script_has_no_direct_storage_adapter_or_ledger_path_authority() -> None:
    source = (Path(__file__).resolve().parents[2] / "scripts/export_ledger_json.py").read_text(
        encoding="utf-8"
    )
    assert "SQLiteLedger" not in source
    assert 'add_argument("--ledger"' not in source
    assert "ReplayEventCatalog" in source
