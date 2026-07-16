"""Exact-one terminal evidence tests for the observed LLM boundary."""

from __future__ import annotations

from uuid import UUID

import pytest

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.llm.effect import (
    LedgerLlmCompletionObserver,
    LlmSemanticError,
    ObservedLlmClient,
    consume_llm_completion,
)
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
)
from tests.runtime import runtime_dependencies

_CORRELATION = UUID("22222222-2222-2222-2222-222222222222")


class _ResponseClient:
    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        return LlmResponse(
            text='{"accepted":true}',
            usage=LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=None),
            model="served-model",
            finish_reason="stop",
        )


class _FailingClient:
    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        raise RuntimeError("secret transport detail")


def _request() -> ModelSOLlmCompletionRequest:
    return ModelSOLlmCompletionRequest(
        system_prompt="system",
        user_prompt="user",
        persona="pilot.persona",
        temperature=0.2,
        json_mode=True,
        evidence_context=ModelSOLlmEvidenceContext(
            match_id="match.evidence",
            mech_id="mech.red.01",
            player_id="player.red",
            tick=4,
            correlation_id=_CORRELATION,
        ),
    )


def _observed(base: object) -> tuple[ObservedLlmClient, list[ModelSOEventEnvelope]]:
    emitted: list[ModelSOEventEnvelope] = []
    runtime = runtime_dependencies()
    observer = LedgerLlmCompletionObserver(
        correlation_id=UUID(int=1),
        event_factory=runtime.event_factory,
        emit=emitted.append,
    )
    return (
        ObservedLlmClient(base=base, provider_id="provider.fixture", observer=observer),  # type: ignore[arg-type]
        emitted,
    )


def _assert_chain(events: list[ModelSOEventEnvelope], terminal: SOEventType) -> None:
    assert [event.event_type for event in events] == [
        SOEventType.LLM_COMPLETION_REQUESTED,
        terminal,
    ]
    requested, outcome = events
    assert outcome.correlation_id == requested.correlation_id == _CORRELATION
    assert outcome.causation_id == requested.envelope.message_id
    assert outcome.subject == requested.subject
    assert outcome.subject.player_id == "player.red"


@pytest.mark.unit
def test_strict_acceptance_emits_requested_then_resolved() -> None:
    client, events = _observed(_ResponseClient())
    result = consume_llm_completion(client=client, request=_request(), consumer=lambda r: r.model)
    assert result == "served-model"
    _assert_chain(events, SOEventType.LLM_COMPLETION_RESOLVED)


@pytest.mark.unit
def test_semantic_rejection_emits_failed_with_usage_without_raw_content() -> None:
    client, events = _observed(_ResponseClient())

    def reject(response: LlmResponse) -> None:
        raise LlmSemanticError("raw response detail")

    with pytest.raises(LlmSemanticError):
        consume_llm_completion(client=client, request=_request(), consumer=reject)
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    payload = events[-1].payload
    assert payload["reason_code"] == "invalid_response"
    assert payload["model"] == "served-model"
    assert payload["prompt_tokens"] == 7
    assert "raw response detail" not in events[-1].model_dump_json()


@pytest.mark.unit
def test_provider_failure_emits_sanitized_failed_terminal() -> None:
    client, events = _observed(_FailingClient())
    with pytest.raises(RuntimeError, match="secret transport detail"):
        consume_llm_completion(client=client, request=_request(), consumer=lambda response: None)
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    assert events[-1].payload["reason_code"] == "provider_error"
    assert events[-1].payload["model"] is None
    assert "secret transport detail" not in events[-1].model_dump_json()


@pytest.mark.unit
def test_abandoned_attempt_emits_failed_and_rejects_double_finalization() -> None:
    client, events = _observed(_ResponseClient())
    with client.begin_attempt(_request()):
        pass
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    assert events[-1].payload["reason_code"] == "abandoned"

    second, _ = _observed(_ResponseClient())
    with second.begin_attempt(_request()) as attempt:
        attempt.resolve()
        with pytest.raises(RuntimeError, match="terminal outcome"):
            attempt.resolve()
