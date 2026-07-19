"""Rule-pack provenance survives start/evidence and gates replay drift."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.application import ModelSOBalanceRulePackBinding
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import CURRENT_CONSUMED_PAYLOAD_MODELS
from steel_onslaught.learning.post_match import project_match_learning_evidence
from steel_onslaught.pilots.programming import (
    ModelSOCardRuleHandlerMetadata,
    ModelSOCardRulePackProvenance,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.fixtures.event_samples import build_sample_envelopes
from tests.runtime import runtime_dependencies


def _provenance(*, digest: str = "a" * 64) -> ModelSOCardRulePackProvenance:
    metadata = ModelSOCardRuleHandlerMetadata(
        handler_id="prefer_attack_cards",
        version="v1.0.0",
        implementation_sha256="b" * 64,
    )
    return ModelSOCardRulePackProvenance(
        pack_id="rules.card_programming_v1",
        handlers=(metadata,),
        content_sha256=digest,
    )


@pytest.mark.unit
def test_overlay_rule_pack_binding_is_closed_and_ordered() -> None:
    binding = ModelSOBalanceRulePackBinding(
        kind="card_programming_rules",
        pack_id="rules.card_programming_v1",
        handler_ids=("prefer_attack_cards",),
    )
    assert binding.handler_ids == ("prefer_attack_cards",)
    with pytest.raises(ValidationError, match="handler_ids must be unique"):
        ModelSOBalanceRulePackBinding(
            kind="card_programming_rules",
            pack_id="rules.card_programming_v1",
            handler_ids=("prefer_attack_cards", "prefer_attack_cards"),
        )


class _MemoryLedger:
    def __init__(self, events: list[ModelSOEventEnvelope]) -> None:
        self.events = events

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return (event for event in self.events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return (
            event for event in self.events if event.match_id == match_id and event.tick > after_tick
        )


@pytest.mark.unit
def test_rule_pack_is_retained_in_start_and_learning_evidence() -> None:
    samples = build_sample_envelopes()
    provenance = _provenance()
    started = samples[SOEventType.MATCH_STARTED].model_copy(
        update={
            "payload": {
                **samples[SOEventType.MATCH_STARTED].payload,
                "card_rule_pack_provenance": provenance.model_dump(mode="json"),
            }
        }
    )
    started_payload = started.payload
    assert started_payload["card_rule_pack_provenance"] == provenance.model_dump(mode="json")

    stream = [
        started if event_type is SOEventType.MATCH_STARTED else samples[event_type]
        for event_type in CURRENT_CONSUMED_PAYLOAD_MODELS
    ]
    evidence = project_match_learning_evidence(stream)
    assert evidence.card_rule_pack_provenance == provenance


@pytest.mark.unit
def test_replay_rejects_rule_pack_drift() -> None:
    started = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    provenance = _provenance()
    started = started.model_copy(
        update={
            "payload": {
                **started.payload,
                "card_rule_pack_provenance": provenance.model_dump(mode="json"),
            }
        }
    )
    runtime = runtime_dependencies()
    replay = ReplayEngine(
        _MemoryLedger([started]),
        started.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        card_rule_pack_provenance=_provenance(digest="c" * 64),
    )
    with pytest.raises(ValueError, match="card rule-pack provenance"):
        replay.reconstruct_at_tick(0)
