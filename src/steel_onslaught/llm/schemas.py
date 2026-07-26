"""Closed typed contracts for the LLM provider boundary."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, Self, runtime_checkable
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictBytes,
    StrictFloat,
    StrictInt,
    StrictStr,
)

from steel_onslaught.contracts.application import ModelSOThinkingBinding
from steel_onslaught.contracts.pilot import SODisplaySalience

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


class ModelSOLlmImageAttachment(_ClosedStrictModel):
    """One deterministic per-tick render, attached alongside the text prompt.

    ``sha256_hex`` is computed by the caller (the renderer's only consumer)
    over the exact ``png_bytes`` carried here, so the ledger evidence and the
    wire payload can never diverge -- both are derived from this one value.
    """

    png_bytes: StrictBytes
    sha256_hex: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class ModelSOLlmCompletionRequest(_ClosedStrictModel):
    system_prompt: StrictStr = Field(min_length=1)
    user_prompt: StrictStr = Field(min_length=1)
    persona: StrictStr = Field(min_length=1)
    temperature: StrictFloat = Field(ge=0.0, le=2.0, allow_inf_nan=False)
    json_mode: StrictBool
    evidence_context: ModelSOLlmEvidenceContext | None
    # Present only on the V-IMG arm of the vision-representation experiment
    # (2026-07-24). ``None`` for every other call site, which is what keeps
    # ``OpenAICompatibleClient.complete`` emitting a byte-identical string
    # ``content`` field for every pre-existing (text-only) arm.
    image_attachment: ModelSOLlmImageAttachment | None = None


class ModelSOLlmPilotSelection(_ClosedStrictModel):
    provider_id: StrictStr = Field(min_length=1)
    persona_id: StrictStr = Field(min_length=1)
    opponent_trace: StrictStr | None
    # Display-salience arm #1 (OMN-15166) -- threaded verbatim from
    # ``ModelSOLlmPilotParams.display_salience`` through
    # ``ApplicationPilotFactory.from_spec``/``.llm_pilot`` into
    # ``LLMPilot.__init__``. Defaulted here (not just on the pilot-spec
    # model) so every pre-existing direct construction of this selection
    # (tests, tuner code) keeps resolving "default" without modification.
    display_salience: SODisplaySalience = SODisplaySalience.DEFAULT


class ModelSOOpenAITextContentPart(_ClosedStrictModel):
    type: Literal["text"]
    text: StrictStr


class ModelSOOpenAIImageUrl(_ClosedStrictModel):
    url: StrictStr = Field(min_length=1)


class ModelSOOpenAIImageUrlContentPart(_ClosedStrictModel):
    type: Literal["image_url"]
    image_url: ModelSOOpenAIImageUrl


ModelSOOpenAIContentPart = Annotated[
    ModelSOOpenAITextContentPart | ModelSOOpenAIImageUrlContentPart,
    Field(discriminator="type"),
]


class ModelSOOpenAIChatMessage(_ClosedStrictModel):
    role: Literal["system", "user"]
    # A plain string for every text-only arm (byte-identical to the
    # pre-existing wire body); a multi-part content-part tuple only for the
    # V-IMG arm's user message, which carries the text part plus one
    # ``image_url`` part holding the deterministic per-tick render as a
    # base64 data URI.
    content: StrictStr | tuple[ModelSOOpenAIContentPart, ...]


class ModelSOOpenAIResponseFormat(_ClosedStrictModel):
    type: Literal["json_object"]


class ModelSOOpenAIChatRequest(_ClosedStrictModel):
    model: StrictStr = Field(min_length=1)
    messages: tuple[ModelSOOpenAIChatMessage, ModelSOOpenAIChatMessage]
    temperature: StrictFloat = Field(ge=0.0, le=2.0, allow_inf_nan=False)
    max_tokens: StrictInt | None = Field(gt=0, le=32768)
    response_format: ModelSOOpenAIResponseFormat | None
    # Optional provider ``thinking`` control (e.g. GLM/z.ai) serialized as a
    # top-level object only when set. ``None`` (every non-GLM arm) is excluded by
    # ``model_dump(exclude_none=True)``, so the wire body stays byte-identical.
    thinking: ModelSOThinkingBinding | None = None


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


class LlmCompletionBoundaryError(LlmTransportError):
    """A provider completion crossed a fail-closed live-play boundary.

    ``length`` means the provider exhausted its output budget before producing
    an accepted completion. ``timeout`` means the typed transport timeout
    elapsed. Both are intentionally distinct from generic provider errors so
    the match runner can terminate a live match with durable evidence instead
    of silently selecting a deterministic action.
    """

    def __init__(
        self,
        reason_code: Literal["length", "timeout"],
        *,
        response: LlmResponse | None = None,
        retryable: bool = False,
    ) -> None:
        self.reason_code = reason_code
        self.response = response
        message = (
            "LLM completion reached the configured output limit"
            if reason_code == "length"
            else "LLM request timed out"
        )
        super().__init__(message, retryable=retryable)


class LlmSemanticExhaustedError(LlmTransportError):
    """A live provider never produced a semantically admissible plan.

    Raised only after a *bounded* number of same-model reprompts each failed
    the strict plan contract (malformed JSON, unknown/unavailable card, or
    invalid action parameters).  It is deliberately distinct from
    ``LlmCompletionBoundaryError``: a boundary failure means the completion was
    truncated/timed out, while this means the provider *answered every time*
    but never with a plan the engine could accept.

    Both belong to the same live-play termination family (``LlmTransportError``)
    so the match runner can convert either into durable ``MATCH_ENDED``
    evidence.  A boundary maps to ``aborted``; a semantic exhaustion maps to the
    distinct ``provider_semantic_failure`` terminal so a self-correction loop
    that ran out of attempts is never confused with a truncated completion or a
    clean gameplay outcome.  The failing seat, provider, model, and semantic
    code travel with the exception so the terminal is diagnosable without a
    ledger join (the per-attempt ``llm_completion_failed`` events remain the
    primary durable record).
    """

    def __init__(
        self,
        *,
        seat: str,
        semantic_failure_code: LlmSemanticFailureCode,
        attempts: int,
        provider_id: str | None = None,
        model: str | None = None,
    ) -> None:
        self.seat = seat
        self.semantic_failure_code = semantic_failure_code
        self.attempts = attempts
        self.provider_id = provider_id
        self.model = model
        super().__init__(
            f"live provider produced no admissible plan for seat {seat!r} after "
            f"{attempts} attempt(s) (last failure: {semantic_failure_code})",
            retryable=False,
        )


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
    "length",
    "timeout",
]

type LlmSemanticFailureCode = Literal[
    "malformed_json",
    "unknown_action",
    "action_unavailable",
    "invalid_action_parameters",
]


@runtime_checkable
class ProtocolLlmAttempt(Protocol):
    @property
    def response(self) -> LlmResponse: ...

    def resolve(self) -> None: ...

    def fail(
        self,
        reason_code: LlmCompletionFailureReason,
        *,
        semantic_failure_code: LlmSemanticFailureCode | None = None,
        semantic_failure_detail: str | None = None,
    ) -> None: ...

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
        *,
        semantic_failure_code: LlmSemanticFailureCode | None = None,
        semantic_failure_detail: str | None = None,
    ) -> None: ...


@runtime_checkable
class ProtocolPilotFactory(Protocol):
    def with_observer(self, observer: ProtocolLlmCompletionObserver) -> ProtocolPilotFactory: ...

    def from_spec(self, spec: ModelSOPilotSpec) -> PilotProtocol: ...

    def llm_pilot(self, selection: ModelSOLlmPilotSelection) -> PilotProtocol: ...


__all__ = [
    "LlmCompletionBoundaryError",
    "LlmCompletionFailureReason",
    "LlmResponse",
    "LlmSemanticExhaustedError",
    "LlmSemanticFailureCode",
    "LlmTransportError",
    "LlmUsage",
    "ModelSOLlmCompletionRequest",
    "ModelSOLlmEvidenceContext",
    "ModelSOLlmImageAttachment",
    "ModelSOLlmPilotSelection",
    "ModelSOOpenAIChatMessage",
    "ModelSOOpenAIChatRequest",
    "ModelSOOpenAIChatResponse",
    "ModelSOOpenAIContentPart",
    "ModelSOOpenAIImageUrl",
    "ModelSOOpenAIImageUrlContentPart",
    "ModelSOOpenAIResponseChoice",
    "ModelSOOpenAIResponseFormat",
    "ModelSOOpenAIResponseMessage",
    "ModelSOOpenAIResponseUsage",
    "ModelSOOpenAITextContentPart",
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
