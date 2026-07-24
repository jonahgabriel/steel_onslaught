"""Offline evidence tests for the LLM tuner boundary."""

from __future__ import annotations

from uuid import UUID

import pytest

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.learning.protocols import ModelSONumericBound
from steel_onslaught.llm.context_arms import ContextArm
from steel_onslaught.llm.effect import LedgerLlmCompletionObserver, ObservedLlmClient
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
)
from steel_onslaught.llm.tuner import tune_with_usage
from tests.runtime import runtime_dependencies

_RAW_OUTPUT = "raw-tuner-output-sentinel {"
_RAW_PROMPT = "raw-tuner-prompt-sentinel"
_SYSTEM_PROMPT = "You are an expert game-balance tuner. Propose parameter improvements."
_CORRELATION = UUID("33333333-3333-3333-3333-333333333333")


class _MalformedTunerClient:
    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        return LlmResponse(
            text=_RAW_OUTPUT,
            usage=LlmUsage(prompt_tokens=17, completion_tokens=5, cost_usd=0.025),
            model="served-tuner-model",
            finish_reason="length",
        )


@pytest.mark.unit
def test_malformed_observed_tuner_response_is_sanitized_consumer_failure() -> None:
    emitted: list[ModelSOEventEnvelope] = []
    runtime = runtime_dependencies()
    observer = LedgerLlmCompletionObserver(
        correlation_id=UUID(int=1),
        event_factory=runtime.event_factory,
        emit=emitted.append,
    )
    client = ObservedLlmClient(
        base=_MalformedTunerClient(),
        provider_id="provider.tuner.fixture",
        observer=observer,
    )

    candidates, generator_id, usage = tune_with_usage(
        client=client,
        provider_id="provider.tuner.fixture",
        arm=ContextArm.LLM_OFF,
        archetype=_RAW_PROMPT,
        parent_params={"aggression": 0.5},
        bounds={"aggression": ModelSONumericBound(minimum=0.0, maximum=1.0, step=0.1)},
        n_proposals=1,
        evidence_context=ModelSOLlmEvidenceContext(
            match_id="match.tuner.evidence",
            mech_id="mech.red.01",
            player_id="player.red",
            tick=6,
            correlation_id=_CORRELATION,
        ),
    )

    assert candidates == []
    assert generator_id == "llm.served-tuner-model@llm_off"
    assert usage == LlmUsage(prompt_tokens=17, completion_tokens=5, cost_usd=0.025)
    assert [event.event_type for event in emitted] == [
        SOEventType.LLM_COMPLETION_REQUESTED,
        SOEventType.LLM_COMPLETION_FAILED,
    ]
    requested, failed = emitted
    assert failed.correlation_id == requested.correlation_id == _CORRELATION
    assert failed.causation_id == requested.envelope.message_id
    assert failed.payload == {
        "provider_id": "provider.tuner.fixture",
        "reason_code": "consumer_error",
        "semantic_failure_code": None,
        "model": "served-tuner-model",
        "finish_reason": "length",
        "prompt_tokens": 17,
        "completion_tokens": 5,
        "cost_usd": 0.025,
        # response_length is populated whenever a response exists, even for a
        # non-semantic consumer_error; semantic_failure_detail stays absent
        # (exclude_if) because this failure never carries one.
        "response_length": len(_RAW_OUTPUT),
    }

    serialized_evidence = "\n".join(event.model_dump_json() for event in emitted)
    for unsafe_text in (
        _RAW_OUTPUT,
        "unparseable tuner JSON",
        _RAW_PROMPT,
        _SYSTEM_PROMPT,
    ):
        assert unsafe_text not in serialized_evidence
