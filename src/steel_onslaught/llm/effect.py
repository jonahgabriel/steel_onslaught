"""Typed LLM completion observation over canonical event evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from types import TracebackType
from typing import Self
from uuid import UUID

from pydantic import TypeAdapter

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import (
    ModelSOLlmCompletionFailedPayload,
    ModelSOLlmCompletionRequestedPayload,
    ModelSOLlmCompletionResolvedPayload,
)
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmCompletionFailureReason,
    LlmResponse,
    LlmSemanticFailureCode,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
    ProtocolLlmAttemptClient,
    ProtocolLlmClient,
    ProtocolLlmCompletionObserver,
)

_PRODUCER_NODE = "node.llm.completion_effect"
_SEMANTIC_FAILURE_CODE_ADAPTER: TypeAdapter[LlmSemanticFailureCode] = TypeAdapter(
    LlmSemanticFailureCode
)
_SAFE_FINISH_REASON_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_finish_reason(response: LlmResponse | None) -> str | None:
    if response is None:
        return None
    finish_reason = response.finish_reason
    if len(finish_reason) > 64 or _SAFE_FINISH_REASON_PATTERN.fullmatch(finish_reason) is None:
        return None
    return finish_reason


class LlmSemanticError(ValueError):
    """A provider response failed the consumer's strict semantic contract."""

    def __init__(self, code: str) -> None:
        self.code = _SEMANTIC_FAILURE_CODE_ADAPTER.validate_python(code, strict=True)
        super().__init__(self.code)


class _ObservedLlmAttempt:
    """One opaque request token with exactly one terminal transition."""

    def __init__(
        self,
        *,
        base: ProtocolLlmClient,
        provider_id: str,
        request: ModelSOLlmCompletionRequest,
        observer: ProtocolLlmCompletionObserver,
    ) -> None:
        self._base = base
        self._provider_id = provider_id
        self._request = request
        self._observer = observer
        self._requested: ModelSOEventEnvelope | None = None
        self._response: LlmResponse | None = None
        self._terminal = False

    def __enter__(self) -> Self:
        if self._requested is not None:
            raise RuntimeError("LLM attempt token cannot be entered twice")
        self._requested = self._observer.requested(self._provider_id, self._request)
        try:
            self._response = self._base.complete(self._request)
        except LlmCompletionBoundaryError as exc:
            self._response = exc.response
            self.fail(exc.reason_code)
            raise
        except BaseException:
            self.fail("provider_error")
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if not self._terminal:
            self.fail("consumer_error" if exc_type is not None else "abandoned")

    @property
    def response(self) -> LlmResponse:
        if self._response is None:
            raise RuntimeError("LLM attempt response is unavailable before entry")
        return self._response

    def resolve(self) -> None:
        requested = self._require_pending()
        response = self.response
        self._terminal = True
        self._observer.resolved(
            self._provider_id,
            self._request,
            response,
            requested,
        )

    def fail(
        self,
        reason_code: LlmCompletionFailureReason,
        *,
        semantic_failure_code: LlmSemanticFailureCode | None = None,
    ) -> None:
        requested = self._require_pending()
        self._terminal = True
        self._observer.failed(
            self._provider_id,
            self._request,
            reason_code,
            self._response,
            requested,
            semantic_failure_code=semantic_failure_code,
        )

    def _require_pending(self) -> ModelSOEventEnvelope:
        if self._requested is None:
            raise RuntimeError("LLM attempt token was not entered")
        if self._terminal:
            raise RuntimeError("LLM attempt token already has a terminal outcome")
        return self._requested


class ObservedLlmClient:
    """Provider decorator requiring consumer acceptance before resolution."""

    def __init__(
        self,
        *,
        base: ProtocolLlmClient,
        provider_id: str,
        observer: ProtocolLlmCompletionObserver,
    ) -> None:
        self._base = base
        self._provider_id = provider_id
        self._observer = observer

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        raise RuntimeError("observed LLM clients require consume_llm_completion")

    @property
    def observes_attempts(self) -> bool:
        return True

    def begin_attempt(self, request: ModelSOLlmCompletionRequest) -> _ObservedLlmAttempt:
        if request.evidence_context is None:
            raise ValueError("observed LLM completion requires evidence_context")
        return _ObservedLlmAttempt(
            base=self._base,
            provider_id=self._provider_id,
            request=request,
            observer=self._observer,
        )


def consume_llm_completion[T](
    *,
    client: ProtocolLlmClient,
    request: ModelSOLlmCompletionRequest,
    consumer: Callable[[LlmResponse], T],
    allow_length_finish_reason: bool = False,
) -> T:
    """Finalize observed evidence only after strict consumer acceptance.

    Live match consumers leave ``allow_length_finish_reason`` false so a
    provider-truncated completion is terminal. Offline learning/tuning may
    opt into parsing the response as an ordinary consumer error while still
    retaining the requested/failed evidence pair.
    """
    if not isinstance(client, ProtocolLlmAttemptClient) or not client.observes_attempts:
        response = client.complete(request)
        if response.finish_reason == "length" and not allow_length_finish_reason:
            raise LlmCompletionBoundaryError("length", response=response)
        return consumer(response)
    with client.begin_attempt(request) as attempt:
        if attempt.response.finish_reason == "length" and not allow_length_finish_reason:
            attempt.fail("length")
            raise LlmCompletionBoundaryError("length", response=attempt.response)
        try:
            result = consumer(attempt.response)
        except LlmSemanticError as exc:
            attempt.fail("invalid_response", semantic_failure_code=exc.code)
            raise
        except Exception:
            attempt.fail("consumer_error")
            raise
        attempt.resolve()
        return result


class LedgerLlmCompletionObserver:
    """Publishes evidence only through the injected canonical EventFactory."""

    def __init__(
        self,
        *,
        correlation_id: UUID,
        event_factory: EventFactory,
        emit: Callable[[ModelSOEventEnvelope], None],
    ) -> None:
        self._correlation_id = correlation_id
        self._events = event_factory
        self._emit = emit

    @staticmethod
    def _context(request: ModelSOLlmCompletionRequest) -> ModelSOLlmEvidenceContext:
        context = request.evidence_context
        if context is None:
            raise ValueError("LLM evidence request is missing evidence_context")
        return context

    def requested(
        self, provider_id: str, request: ModelSOLlmCompletionRequest
    ) -> ModelSOEventEnvelope:
        context = self._context(request)
        payload = ModelSOLlmCompletionRequestedPayload(
            provider_id=provider_id,
            persona_id=request.persona,
            system_prompt_length=len(request.system_prompt),
            user_prompt_length=len(request.user_prompt),
        )
        event = self._events.make(
            match_id=context.match_id,
            tick=context.tick,
            sequence_in_tick=0,
            event_type=SOEventType.LLM_COMPLETION_REQUESTED,
            producer_node=_PRODUCER_NODE,
            subject=ModelSOEventSubject(
                mech_id=context.mech_id,
                player_id=context.player_id,
            ),
            payload=payload.model_dump(mode="json"),
            correlation_id=context.correlation_id or self._correlation_id,
        )
        self._emit(event)
        return event

    def resolved(
        self,
        provider_id: str,
        request: ModelSOLlmCompletionRequest,
        response: LlmResponse,
        requested: ModelSOEventEnvelope,
    ) -> None:
        context = self._context(request)
        payload = ModelSOLlmCompletionResolvedPayload(
            provider_id=provider_id,
            model=response.model,
            finish_reason=response.finish_reason,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            response_length=len(response.text),
            cost_usd=response.usage.cost_usd,
        )
        self._emit(
            self._events.caused_by(
                requested,
                match_id=context.match_id,
                tick=context.tick,
                sequence_in_tick=0,
                event_type=SOEventType.LLM_COMPLETION_RESOLVED,
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(
                    mech_id=context.mech_id,
                    player_id=context.player_id,
                ),
                payload=payload.model_dump(mode="json"),
            )
        )

    def failed(
        self,
        provider_id: str,
        request: ModelSOLlmCompletionRequest,
        reason_code: LlmCompletionFailureReason,
        response: LlmResponse | None,
        requested: ModelSOEventEnvelope,
        *,
        semantic_failure_code: LlmSemanticFailureCode | None = None,
    ) -> None:
        context = self._context(request)
        payload = ModelSOLlmCompletionFailedPayload(
            provider_id=provider_id,
            reason_code=reason_code,
            semantic_failure_code=semantic_failure_code,
            model=response.model if response is not None else None,
            finish_reason=_safe_finish_reason(response),
            prompt_tokens=response.usage.prompt_tokens if response is not None else None,
            completion_tokens=(response.usage.completion_tokens if response is not None else None),
            cost_usd=response.usage.cost_usd if response is not None else None,
        )
        self._emit(
            self._events.caused_by(
                requested,
                match_id=context.match_id,
                tick=context.tick,
                sequence_in_tick=0,
                event_type=SOEventType.LLM_COMPLETION_FAILED,
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(
                    mech_id=context.mech_id,
                    player_id=context.player_id,
                ),
                payload=payload.model_dump(mode="json"),
            )
        )


__all__ = [
    "LedgerLlmCompletionObserver",
    "LlmSemanticError",
    "ObservedLlmClient",
    "consume_llm_completion",
]
