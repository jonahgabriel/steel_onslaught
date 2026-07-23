"""Focused tests for the typed after-match learning effect."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from steel_onslaught.contracts.live_learning import (
    ModelSOLiveLearningOutcome,
    ModelSOLiveMatchPolicySnapshot,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import CURRENT_CONSUMED_PAYLOAD_MODELS
from steel_onslaught.learning.after_match import AfterMatchLearningHandler
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.live import (
    LearningSeamViolationError,
    LiveLearningPromotionPort,
)
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


# ---------------------------------------------------------------------------
# Containment boundary (L-GATE-2 live-fire findings F1/F2)
# ---------------------------------------------------------------------------


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 22, tzinfo=UTC)


class _FixedIdentities:
    def new_match_id(self) -> str:
        return "match.fixed"

    def new_correlation_id(self) -> UUID:
        return UUID("00000000-0000-0000-0000-000000000010")

    def new_event_id(self) -> str:
        return "01HZY3E9ZTAV5J6BQF8KM2WXBB"

    def new_message_id(self) -> UUID:
        return UUID("00000000-0000-0000-0000-000000000011")


class _RaisingPromotion:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def begin_match(self, match_id: str) -> ModelSOLiveMatchPolicySnapshot:
        raise NotImplementedError("terminal-only double")

    def handle_after_match(
        self, evidence: ModelSOAfterMatchLearningEvidence
    ) -> ModelSOLiveLearningOutcome:
        self.calls += 1
        raise self.error


def _promotion_handler(
    promotion: _RaisingPromotion,
) -> tuple[AfterMatchLearningHandler, _Artifacts, list[ModelSOEventEnvelope]]:
    events = _complete_stream()
    ledger, artifacts, recording = _ports(events)
    emitted: list[ModelSOEventEnvelope] = []
    handler = AfterMatchLearningHandler(
        ledger=ledger,
        artifacts=artifacts,
        promotion=cast(LiveLearningPromotionPort, promotion),
        emit=emitted.append,
        event_factory=EventFactory(clock=_FixedClock(), identities=_FixedIdentities()),
    )
    return handler, recording, emitted


@pytest.mark.unit
def test_evaluation_runtime_failure_is_contained_and_recorded() -> None:
    """An evaluation-runtime failure out of the promotion port must NOT
    propagate into the bus: the evidence write (ordered BEFORE the gate)
    survives, the failure becomes a typed contained outcome, the terminal is
    processed (no battery re-run on duplicate delivery), and nothing emits."""

    samples = build_sample_envelopes()
    promotion = _RaisingPromotion(RuntimeError("evaluator exploded mid-battery"))
    handler, recording, emitted = _promotion_handler(promotion)

    handler.handle(samples[SOEventType.MATCH_SCORED])  # must not raise

    assert len(recording.evidence) == 1
    assert emitted == []
    assert len(handler.contained_failures) == 1
    failure = handler.contained_failures[0]
    assert failure.match_id == samples[SOEventType.MATCH_SCORED].match_id
    assert failure.stage == "promotion_evaluation"
    assert failure.error_type == "RuntimeError"
    assert "evaluator exploded mid-battery" in failure.message

    # The contained terminal is a processed terminal: duplicate delivery must
    # not re-run the (expensive, already-failed) evaluation.
    handler.handle(samples[SOEventType.MATCH_SCORED])
    assert promotion.calls == 1
    assert len(handler.contained_failures) == 1


@pytest.mark.unit
def test_seam_violation_still_raises_through_the_containment_boundary() -> None:
    """The loud half of the split: a seam violation (e.g. an un-admitted
    terminal) means the WIRING is wrong — containment must not swallow it."""

    samples = build_sample_envelopes()
    promotion = _RaisingPromotion(
        LearningSeamViolationError("match 'match.x' must be admitted before terminal evidence")
    )
    handler, recording, _ = _promotion_handler(promotion)

    with pytest.raises(LearningSeamViolationError, match="must be admitted"):
        handler.handle(samples[SOEventType.MATCH_SCORED])

    assert handler.contained_failures == ()
    # Evidence is still written first — it must survive promotion failure.
    assert len(recording.evidence) == 1
