"""Tests for the event-sample fixture emitter — Task 31.

The emitter is the Python half of the type-parity contract: it writes one
canonical envelope JSON per ``SOEventType`` into
``frontend/src/__tests__/fixtures/``; the vitest ``types_parity.test.ts``
suite parses each fixture through the hand-written TS types.  Any payload
schema change must regenerate the fixtures (``uv run python -m
tests.fixtures.event_samples``) and update ``frontend/src/types.ts``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from tests.fixtures.event_samples import FIXTURES_DIR, build_sample_envelopes, emit_fixtures


@pytest.mark.unit
def test_one_sample_per_event_type() -> None:
    samples = build_sample_envelopes()
    assert sorted(samples.keys()) == sorted(SOEventType)


@pytest.mark.unit
def test_samples_are_valid_envelopes_with_matching_event_type() -> None:
    for event_type, envelope in build_sample_envelopes().items():
        assert isinstance(envelope, ModelSOEventEnvelope)
        assert envelope.event_type is event_type
        # Round-trip through JSON: the wire form the bridge broadcasts.
        restored = ModelSOEventEnvelope.model_validate_json(envelope.model_dump_json())
        assert restored == envelope


@pytest.mark.unit
def test_emit_writes_one_file_per_event_type(tmp_path: Path) -> None:
    written = emit_fixtures(tmp_path)
    assert sorted(p.name for p in written) == sorted(f"{t.value}.json" for t in SOEventType)
    for path in written:
        ModelSOEventEnvelope.model_validate_json(path.read_text())


@pytest.mark.unit
def test_emit_is_deterministic(tmp_path: Path) -> None:
    first = {p.name: p.read_text() for p in emit_fixtures(tmp_path / "a")}
    second = {p.name: p.read_text() for p in emit_fixtures(tmp_path / "b")}
    assert first == second


@pytest.mark.integration
def test_committed_fixtures_are_up_to_date(tmp_path: Path) -> None:
    """The committed frontend fixtures must match a fresh emission exactly.

    Failure mode this guards: a Python event payload changes but the fixtures
    (and therefore the TS types) are not regenerated — the TS parity test
    would then pass against stale data.
    """
    fresh = {p.name: p.read_text() for p in emit_fixtures(tmp_path)}
    committed_dir = FIXTURES_DIR
    assert committed_dir.is_dir(), (
        f"committed fixtures missing at {committed_dir}; "
        "run: uv run python -m tests.fixtures.event_samples"
    )
    committed = {p.name: p.read_text() for p in sorted(committed_dir.glob("*.json"))}
    assert committed == fresh, (
        "committed frontend fixtures are stale; "
        "regenerate with: uv run python -m tests.fixtures.event_samples"
    )
