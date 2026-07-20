"""Focused tests for the typed after-match learning effect."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import CURRENT_CONSUMED_PAYLOAD_MODELS
from steel_onslaught.learning.after_match import AfterMatchLearningHandler
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.ledger.protocol import EventLedger
from tests.fixtures.event_samples import build_sample_envelopes


class _Ledger:
    def __init__(self, events: list[ModelSOEventEnvelope]) -> None:
        self._events = events
        self.read_match_ids: list[str] = []

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        self.read_match_ids.append(match_id)
        return iter(event for event in self._events if event.match_id == match_id)


class _Artifacts:
    def __init__(self) -> None:
        self.evidence: list[ModelSOAfterMatchLearningEvidence] = []

    def write_after_match_evidence(
        self,
        evidence: ModelSOAfterMatchLearningEvidence,
    ) -> Path:
        self.evidence.append(evidence)
        return Path("evaluations/matches") / f"{evidence.match_id}.yaml"


def _ports(
    events: list[ModelSOEventEnvelope],
) -> tuple[EventLedger, LearningArtifactStore, _Artifacts]:
    ledger = _Ledger(events)
    artifacts = _Artifacts()
    return cast(EventLedger, ledger), cast(LearningArtifactStore, artifacts), artifacts


def _complete_stream() -> list[ModelSOEventEnvelope]:
    samples = build_sample_envelopes()
    return [samples[event_type] for event_type in CURRENT_CONSUMED_PAYLOAD_MODELS]


@pytest.mark.unit
def test_after_match_handler_projects_only_scored_events_and_is_idempotent() -> None:
    samples = build_sample_envelopes()
    events = _complete_stream()
    ledger, artifacts, recording = _ports(events)
    recording_ledger = cast(_Ledger, ledger)
    handler = AfterMatchLearningHandler(ledger=ledger, artifacts=artifacts)

    handler.handle(samples[SOEventType.MATCH_TICK])
    handler.handle(samples[SOEventType.MATCH_SCORED])
    handler.handle(samples[SOEventType.MATCH_SCORED])

    assert len(recording.evidence) == 1
    evidence = recording.evidence[0]
    assert isinstance(evidence, ModelSOAfterMatchLearningEvidence)
    assert evidence.match_id == samples[SOEventType.MATCH_SCORED].match_id
    assert evidence.event_counts[SOEventType.MATCH_SCORED.value] == 1
    assert recording_ledger.read_match_ids == [samples[SOEventType.MATCH_SCORED].match_id]


@pytest.mark.unit
def test_after_match_handler_retries_when_artifact_write_fails() -> None:
    samples = build_sample_envelopes()
    events = _complete_stream()
    ledger = _Ledger(events)

    class FlakyArtifacts(_Artifacts):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        def write_after_match_evidence(
            self,
            evidence: ModelSOAfterMatchLearningEvidence,
        ) -> Path:
            if self.fail:
                self.fail = False
                raise OSError("temporary artifact failure")
            return super().write_after_match_evidence(evidence)

    artifacts = FlakyArtifacts()
    handler = AfterMatchLearningHandler(
        ledger=cast(EventLedger, ledger),
        artifacts=cast(LearningArtifactStore, artifacts),
    )

    with pytest.raises(OSError, match="temporary artifact failure"):
        handler.handle(samples[SOEventType.MATCH_SCORED])
    handler.handle(samples[SOEventType.MATCH_SCORED])

    assert len(artifacts.evidence) == 1
