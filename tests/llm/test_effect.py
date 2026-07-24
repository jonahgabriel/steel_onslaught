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
    LlmCompletionBoundaryError,
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
    ModelSOLlmImageAttachment,
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
    assert events[-1].payload["cost_usd"] is None


@pytest.mark.unit
def test_requested_payload_omits_image_fields_for_text_only_arm() -> None:
    """V-TEXT arm: no image_attachment -> no image_sha256/image_byte_length keys."""
    client, events = _observed(_ResponseClient())
    consume_llm_completion(client=client, request=_request(), consumer=lambda r: r.model)
    requested_payload = events[0].payload
    assert "image_sha256" not in requested_payload
    assert "image_byte_length" not in requested_payload


@pytest.mark.unit
def test_requested_payload_carries_image_sha256_and_byte_length_for_image_arm() -> None:
    """V-IMG arm: the ledger event's sha256 always matches the attached bytes."""
    client, events = _observed(_ResponseClient())
    attachment = ModelSOLlmImageAttachment(png_bytes=b"\x89PNGDATAFAKE", sha256_hex="b" * 64)
    request = ModelSOLlmCompletionRequest(
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
        image_attachment=attachment,
    )
    consume_llm_completion(client=client, request=request, consumer=lambda r: r.model)
    requested_payload = events[0].payload
    assert requested_payload["image_sha256"] == "b" * 64
    assert requested_payload["image_byte_length"] == len(b"\x89PNGDATAFAKE")


@pytest.mark.unit
def test_successful_provider_cost_is_preserved_on_resolved_terminal() -> None:
    class _PricedClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text='{"accepted":true}',
                usage=LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=0.0125),
                model="priced-model",
                finish_reason="stop",
            )

    client, events = _observed(_PricedClient())
    consume_llm_completion(client=client, request=_request(), consumer=lambda response: None)

    _assert_chain(events, SOEventType.LLM_COMPLETION_RESOLVED)
    assert events[-1].payload["cost_usd"] == 0.0125


@pytest.mark.unit
def test_semantic_rejection_emits_failed_with_usage_without_raw_content() -> None:
    raw_response = "raw-semantic-response-sentinel"
    raw_prompt = "raw-semantic-prompt-sentinel"

    class _SemanticResponseClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text=raw_response,
                usage=LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=None),
                model="served-model",
                finish_reason="stop",
            )

    client, events = _observed(_SemanticResponseClient())
    request = _request().model_copy(update={"user_prompt": raw_prompt})

    def reject(response: LlmResponse) -> None:
        raise LlmSemanticError("malformed_json")

    with pytest.raises(LlmSemanticError):
        consume_llm_completion(client=client, request=request, consumer=reject)
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    payload = events[-1].payload
    assert payload["reason_code"] == "invalid_response"
    assert payload["semantic_failure_code"] == "malformed_json"
    assert payload["model"] == "served-model"
    assert payload["finish_reason"] == "stop"
    assert payload["prompt_tokens"] == 7
    assert payload["completion_tokens"] == 3
    serialized_evidence = "\n".join(event.model_dump_json() for event in events)
    assert raw_response not in serialized_evidence
    assert raw_prompt not in serialized_evidence


@pytest.mark.unit
def test_semantic_rejection_persists_detail_and_response_length_on_the_failed_terminal() -> None:
    """2026-07-24 R2 abort forensics: the rejection detail that already goes
    into the repair prompt is ALSO persisted on the ledger's failed terminal,
    end to end from ``LlmSemanticError.detail`` through ``consume_llm_completion``
    to ``LedgerLlmCompletionObserver.failed``, so a repeated malformed_json
    failure is root-causable without re-running the battery."""

    class _SemanticResponseClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text='{"not": "a valid plan"}',
                usage=LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=None),
                model="served-model",
                finish_reason="stop",
            )

    client, events = _observed(_SemanticResponseClient())

    def reject(response: LlmResponse) -> None:
        raise LlmSemanticError("malformed_json", detail="registers must be non-empty")

    with pytest.raises(LlmSemanticError):
        consume_llm_completion(client=client, request=_request(), consumer=reject)
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    payload = events[-1].payload
    assert payload["semantic_failure_detail"] == "registers must be non-empty"
    assert payload["response_length"] == len('{"not": "a valid plan"}')


@pytest.mark.unit
def test_semantic_rejection_without_detail_omits_the_detail_field() -> None:
    """No detail on the raised error -> no key at all on the ledger event
    (``exclude_if``), never a persisted null -- matches every other optional
    forensic field on this payload family."""
    client, events = _observed(_ResponseClient())

    def reject(response: LlmResponse) -> None:
        raise LlmSemanticError("malformed_json")

    with pytest.raises(LlmSemanticError):
        consume_llm_completion(client=client, request=_request(), consumer=reject)
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    assert "semantic_failure_detail" not in events[-1].payload


@pytest.mark.unit
@pytest.mark.parametrize(
    "unsafe_finish_reason",
    [
        pytest.param("unsafe finish reason sentinel", id="whitespace"),
        pytest.param("overlength-finish-reason-sentinel-" + "x" * 65, id="overlength"),
    ],
)
def test_semantic_rejection_drops_unsafe_finish_reason(
    unsafe_finish_reason: str,
) -> None:
    class _UnsafeFinishReasonClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text='{"accepted":false}',
                usage=LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=None),
                model="served-model",
                finish_reason=unsafe_finish_reason,
            )

    client, events = _observed(_UnsafeFinishReasonClient())
    original_error = LlmSemanticError("malformed_json")

    def reject(response: LlmResponse) -> None:
        raise original_error

    with pytest.raises(LlmSemanticError) as captured:
        consume_llm_completion(client=client, request=_request(), consumer=reject)

    assert captured.value is original_error
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    assert events[-1].payload["finish_reason"] is None
    assert SOEventType.LLM_COMPLETION_RESOLVED not in {event.event_type for event in events}
    serialized_evidence = "\n".join(event.model_dump_json() for event in events)
    assert unsafe_finish_reason not in serialized_evidence


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
def test_length_completion_emits_typed_failed_terminal() -> None:
    class _LengthResponseClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text='{"accepted":false}',
                usage=LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=None),
                model="served-model",
                finish_reason="length",
            )

    client, events = _observed(_LengthResponseClient())
    with pytest.raises(LlmCompletionBoundaryError) as captured:
        consume_llm_completion(client=client, request=_request(), consumer=lambda response: None)

    assert captured.value.reason_code == "length"
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    failed = events[-1]
    assert failed.payload["reason_code"] == "length"
    assert failed.payload["finish_reason"] == "length"
    assert SOEventType.LLM_COMPLETION_RESOLVED not in {event.event_type for event in events}


@pytest.mark.unit
def test_timeout_boundary_emits_typed_failed_terminal() -> None:
    class _TimeoutClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            raise LlmCompletionBoundaryError("timeout", retryable=True)

    client, events = _observed(_TimeoutClient())
    with pytest.raises(LlmCompletionBoundaryError) as captured:
        consume_llm_completion(client=client, request=_request(), consumer=lambda response: None)

    assert captured.value.reason_code == "timeout"
    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    failed = events[-1]
    assert failed.payload["reason_code"] == "timeout"
    assert failed.payload["model"] is None
    assert SOEventType.LLM_COMPLETION_RESOLVED not in {event.event_type for event in events}


@pytest.mark.unit
def test_generic_consumer_exception_emits_one_sanitized_failed_terminal() -> None:
    raw_system_prompt = "raw-system-prompt-secret"
    raw_user_prompt = "raw-user-prompt-secret"
    raw_response = "raw-provider-response-secret"

    class _RawResponseClient:
        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            return LlmResponse(
                text=raw_response,
                usage=LlmUsage(prompt_tokens=13, completion_tokens=5, cost_usd=None),
                model="consumer-fixture-model",
                finish_reason="stop",
            )

    client, events = _observed(_RawResponseClient())
    request = _request().model_copy(
        update={
            "system_prompt": raw_system_prompt,
            "user_prompt": raw_user_prompt,
        }
    )

    def explode_after_provider_response(response: LlmResponse) -> None:
        assert response.text == raw_response
        raise RuntimeError("consumer acceptance failed")

    with pytest.raises(RuntimeError, match="consumer acceptance failed") as captured:
        consume_llm_completion(
            client=client,
            request=request,
            consumer=explode_after_provider_response,
        )

    _assert_chain(events, SOEventType.LLM_COMPLETION_FAILED)
    requested, failed = events
    assert failed.payload["reason_code"] == "consumer_error"
    assert failed.payload["provider_id"] == requested.payload["provider_id"] == "provider.fixture"
    assert failed.payload["model"] == "consumer-fixture-model"
    assert failed.payload["prompt_tokens"] == 13
    assert failed.payload["completion_tokens"] == 5
    assert SOEventType.LLM_COMPLETION_RESOLVED not in {event.event_type for event in events}
    assert sum(event.event_type is SOEventType.LLM_COMPLETION_FAILED for event in events) == 1

    serialized_evidence = "\n".join(event.model_dump_json() for event in events)
    exception_text = repr(captured.value)
    for raw_text in (raw_system_prompt, raw_user_prompt, raw_response):
        assert raw_text not in serialized_evidence
        assert raw_text not in exception_text


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
