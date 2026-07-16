"""Closed typed contracts for the LLM provider boundary."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Literal, Protocol, Self, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

if TYPE_CHECKING:
    from steel_onslaught.contracts.application import ModelSOSecretRef
    from steel_onslaught.contracts.pilot import ModelSOPilotSpec
    from steel_onslaught.events.envelope import ModelSOEventEnvelope
    from steel_onslaught.pilots.schemas import PilotProtocol


class _ClosedStrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class LlmUsage(_ClosedStrictModel):
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat | None = Field(ge=0.0, allow_inf_nan=False)


class LlmResponse(_ClosedStrictModel):
    text: StrictStr
    usage: LlmUsage
    model: StrictStr = Field(min_length=1)
    finish_reason: StrictStr


class ModelSOLlmEvidenceContext(_ClosedStrictModel):
    match_id: StrictStr = Field(min_length=1)
    mech_id: StrictStr = Field(min_length=1)
    player_id: StrictStr = Field(min_length=1)
    tick: StrictInt = Field(ge=0)
    correlation_id: UUID | None


class ModelSOLlmCompletionRequest(_ClosedStrictModel):
    system_prompt: StrictStr = Field(min_length=1)
    user_prompt: StrictStr = Field(min_length=1)
    persona: StrictStr = Field(min_length=1)
    temperature: StrictFloat = Field(ge=0.0, le=2.0, allow_inf_nan=False)
    json_mode: StrictBool
    evidence_context: ModelSOLlmEvidenceContext | None


class ModelSOLlmPilotSelection(_ClosedStrictModel):
    provider_id: StrictStr = Field(min_length=1)
    persona_id: StrictStr = Field(min_length=1)
    opponent_trace: StrictStr | None


class ModelSOOpenAIChatMessage(_ClosedStrictModel):
    role: Literal["system", "user"]
    content: StrictStr


class ModelSOOpenAIResponseFormat(_ClosedStrictModel):
    type: Literal["json_object"]


class ModelSOOpenAIChatRequest(_ClosedStrictModel):
    model: StrictStr = Field(min_length=1)
    messages: tuple[ModelSOOpenAIChatMessage, ModelSOOpenAIChatMessage]
    temperature: StrictFloat = Field(ge=0.0, le=2.0, allow_inf_nan=False)
    max_tokens: StrictInt | None = Field(gt=0, le=32768)
    response_format: ModelSOOpenAIResponseFormat | None


class _StrictWireResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)


class ModelSOOpenAIResponseMessage(_StrictWireResponseModel):
    content: StrictStr


class ModelSOOpenAIResponseChoice(_StrictWireResponseModel):
    message: ModelSOOpenAIResponseMessage
    finish_reason: StrictStr


class ModelSOOpenAIResponseUsage(_StrictWireResponseModel):
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)


class ModelSOOpenAIChatResponse(BaseModel):
    """Strict required response surface; unrelated standard metadata is ignored."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    choices: tuple[ModelSOOpenAIResponseChoice, ...] = Field(min_length=1)
    usage: ModelSOOpenAIResponseUsage
    model: StrictStr = Field(min_length=1)


@runtime_checkable
class ProtocolLlmClient(Protocol):
    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse: ...


class SecretResolutionError(RuntimeError):
    """An opaque secret reference could not be resolved."""


class LlmTransportError(RuntimeError):
    """Sanitized transport failure carrying only retry classification."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@runtime_checkable
class ProtocolSecretResolver(Protocol):
    def resolve(self, reference: ModelSOSecretRef) -> str: ...


@runtime_checkable
class ProtocolHttpTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse: ...


@runtime_checkable
class ProtocolSleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


@runtime_checkable
class ProtocolResourceCloser(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class ProtocolLlmClientFactory(Protocol):
    def client_for(self, provider_id: str) -> ProtocolLlmClient: ...


type LlmCompletionFailureReason = Literal[
    "provider_error",
    "invalid_response",
    "consumer_error",
    "abandoned",
]


@runtime_checkable
class ProtocolLlmAttempt(Protocol):
    @property
    def response(self) -> LlmResponse: ...

    def resolve(self) -> None: ...

    def fail(self, reason_code: LlmCompletionFailureReason) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class ProtocolLlmAttemptClient(Protocol):
    @property
    def observes_attempts(self) -> bool: ...

    def begin_attempt(self, request: ModelSOLlmCompletionRequest) -> ProtocolLlmAttempt: ...


@runtime_checkable
class ProtocolLlmCompletionObserver(Protocol):
    def requested(
        self, provider_id: str, request: ModelSOLlmCompletionRequest
    ) -> ModelSOEventEnvelope: ...

    def resolved(
        self,
        provider_id: str,
        request: ModelSOLlmCompletionRequest,
        response: LlmResponse,
        requested: ModelSOEventEnvelope,
    ) -> None: ...

    def failed(
        self,
        provider_id: str,
        request: ModelSOLlmCompletionRequest,
        reason_code: LlmCompletionFailureReason,
        response: LlmResponse | None,
        requested: ModelSOEventEnvelope,
    ) -> None: ...


@runtime_checkable
class ProtocolPilotFactory(Protocol):
    def with_observer(self, observer: ProtocolLlmCompletionObserver) -> ProtocolPilotFactory: ...

    def from_spec(self, spec: ModelSOPilotSpec) -> PilotProtocol: ...

    def llm_pilot(self, selection: ModelSOLlmPilotSelection) -> PilotProtocol: ...


__all__ = [
    "LlmCompletionFailureReason",
    "LlmResponse",
    "LlmTransportError",
    "LlmUsage",
    "ModelSOLlmCompletionRequest",
    "ModelSOLlmEvidenceContext",
    "ModelSOLlmPilotSelection",
    "ModelSOOpenAIChatMessage",
    "ModelSOOpenAIChatRequest",
    "ModelSOOpenAIChatResponse",
    "ModelSOOpenAIResponseChoice",
    "ModelSOOpenAIResponseFormat",
    "ModelSOOpenAIResponseMessage",
    "ModelSOOpenAIResponseUsage",
    "ProtocolHttpTransport",
    "ProtocolLlmAttempt",
    "ProtocolLlmAttemptClient",
    "ProtocolLlmClient",
    "ProtocolLlmClientFactory",
    "ProtocolLlmCompletionObserver",
    "ProtocolPilotFactory",
    "ProtocolResourceCloser",
    "ProtocolSecretResolver",
    "ProtocolSleeper",
    "SecretResolutionError",
]
