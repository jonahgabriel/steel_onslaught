"""Injected OpenAI-compatible client and transport adapters.

Provider configuration is owned by the validated application overlay. This
module performs no environment, package-path, registry, or constructor lookup.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Mapping, Sequence
from threading import Lock
from types import MappingProxyType

import httpx

from steel_onslaught.contracts.application import (
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOSecretRef,
    ModelSOStubLlmProviderBinding,
)
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmResponse,
    LlmTransportError,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOOpenAIChatMessage,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    ModelSOOpenAIContentPart,
    ModelSOOpenAIImageUrl,
    ModelSOOpenAIImageUrlContentPart,
    ModelSOOpenAIResponseFormat,
    ModelSOOpenAITextContentPart,
    ProtocolHttpTransport,
    ProtocolLlmClient,
    ProtocolSecretResolver,
    ProtocolSleeper,
    SecretResolutionError,
)


class ProviderRegistryError(ValueError):
    """A requested provider is absent from the immutable injected registry."""


class OneShotLlmClientConsumedError(RuntimeError):
    """The one permitted live-provider completion was already consumed."""


class BoundedLlmClientConsumedError(RuntimeError):
    """The bounded live-provider completion budget was exhausted."""


class OneShotLlmClient:
    """Thread-safe client wrapper that permits exactly one delegated completion."""

    def __init__(self, client: ProtocolLlmClient) -> None:
        self._client = client
        self._consumed = False
        self._lock = Lock()

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        """Consume before delegation so provider failures cannot restore the allowance."""

        with self._lock:
            if self._consumed:
                raise OneShotLlmClientConsumedError("live provider completion is already consumed")
            self._consumed = True
        return self._client.complete(request)


class BoundedLlmClient:
    """Thread-safe live client with a finite per-match completion budget.

    Launch authority is still admitted exactly once, but an LLM-vs-LLM match
    needs one provider completion per pilot turn.  This wrapper keeps that
    budget explicit and fail-closed without changing the legacy one-shot
    client used by callers that intentionally request a single completion.
    """

    def __init__(self, client: ProtocolLlmClient, *, max_completions: int = 64) -> None:
        if max_completions <= 0:
            raise ValueError("max_completions must be positive")
        self._client = client
        self._max_completions = max_completions
        self._consumed = 0
        self._lock = Lock()

    @property
    def consumption_count(self) -> int:
        with self._lock:
            return self._consumed

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        """Consume one turn before delegation so failures cannot restore budget."""

        with self._lock:
            if self._consumed >= self._max_completions:
                raise BoundedLlmClientConsumedError(
                    "live provider completion budget is already consumed"
                )
            self._consumed += 1
        return self._client.complete(request)


class NoSecretResolver:
    """Fail-closed resolver selected by overlays that permit only keyless providers."""

    def resolve(self, reference: ModelSOSecretRef) -> str:
        raise SecretResolutionError("secret resolution capability is disabled")


class SystemSleeper:
    """Production backoff adapter; tests inject a deterministic recorder."""

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class HttpxJsonTransport:
    """One long-lived root-owned httpx client exposed through a narrow JSON port."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        try:
            response = self._client.post(
                url,
                headers=headers,
                json=request.model_dump(mode="json", exclude_none=True),
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise LlmCompletionBoundaryError("timeout", retryable=True) from None
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise LlmTransportError(
                f"LLM provider returned HTTP {status_code}",
                retryable=status_code in {408, 429} or status_code >= 500,
            ) from None
        except httpx.RequestError:
            raise LlmTransportError("LLM transport request failed", retryable=True) from None
        try:
            return ModelSOOpenAIChatResponse.model_validate_json(response.content)
        except (ValueError, TypeError):
            raise LlmTransportError(
                "LLM provider returned an invalid response contract", retryable=False
            ) from None


class OpenAICompatibleClient:
    """Sync client over injected transport, secret resolver, sleeper, and strict config."""

    def __init__(
        self,
        *,
        config: ModelSOOpenAICompatibleProviderBinding,
        transport: ProtocolHttpTransport,
        secret_resolver: ProtocolSecretResolver,
        sleeper: ProtocolSleeper,
    ) -> None:
        self._config = config
        self._transport = transport
        self._secret_resolver = secret_resolver
        self._sleeper = sleeper

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._config.secret_ref is None:
            return headers
        try:
            secret = self._secret_resolver.resolve(self._config.secret_ref)
        except Exception:
            raise SecretResolutionError("secret resolution failed") from None
        if not secret:
            raise SecretResolutionError("secret resolution failed")
        headers["Authorization"] = f"Bearer {secret}"
        return headers

    @staticmethod
    def _user_content(
        request: ModelSOLlmCompletionRequest,
    ) -> str | tuple[ModelSOOpenAIContentPart, ...]:
        """A plain string for text-only arms; multi-part content for V-IMG.

        Byte-identity of the pre-existing text-only wire body is the
        contract: when ``image_attachment`` is ``None`` (every arm except
        V-IMG) this returns exactly ``request.user_prompt``, unchanged.
        """
        attachment = request.image_attachment
        if attachment is None:
            return request.user_prompt
        data_url = f"data:image/png;base64,{base64.b64encode(attachment.png_bytes).decode('ascii')}"
        return (
            ModelSOOpenAITextContentPart(type="text", text=request.user_prompt),
            ModelSOOpenAIImageUrlContentPart(
                type="image_url",
                image_url=ModelSOOpenAIImageUrl(url=data_url),
            ),
        )

    def complete(
        self,
        request: ModelSOLlmCompletionRequest,
    ) -> LlmResponse:
        provider_request = ModelSOOpenAIChatRequest(
            model=self._config.model,
            messages=(
                ModelSOOpenAIChatMessage(role="system", content=request.system_prompt),
                ModelSOOpenAIChatMessage(role="user", content=self._user_content(request)),
            ),
            temperature=request.temperature,
            max_tokens=self._config.max_tokens,
            response_format=(
                ModelSOOpenAIResponseFormat(type="json_object") if request.json_mode else None
            ),
            # Provider-specific ``thinking`` control (e.g. GLM/z.ai). ``None`` for
            # every other arm, so ``model_dump(exclude_none=True)`` keeps the wire
            # body byte-identical.
            thinking=self._config.thinking,
        )

        headers = self._headers()
        backoff = self._config.retry.initial_backoff_seconds
        response: ModelSOOpenAIChatResponse | None = None
        for attempt in range(1, self._config.retry.max_attempts + 1):
            try:
                response = self._transport.post_json(
                    url=self._config.endpoint_url,
                    headers=headers,
                    request=provider_request,
                    timeout_seconds=self._config.timeout_seconds,
                )
                break
            except TimeoutError:
                raise LlmCompletionBoundaryError("timeout", retryable=True) from None
            except LlmTransportError as exc:
                if not exc.retryable or attempt == self._config.retry.max_attempts:
                    raise
                self._sleeper.sleep(backoff)
                backoff *= self._config.retry.backoff_multiplier
        if response is None:  # pragma: no cover - loop is statically non-empty by contract
            raise RuntimeError("LLM retry policy executed no attempts")
        choice = response.choices[0]
        usage = LlmUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=None,
        )
        return LlmResponse(
            text=choice.message.content,
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason,
        )


class SelectedOnlyLlmClientBuilder:
    """Purely select and validate one explicitly named live provider binding."""

    def select(
        self,
        *,
        providers: Sequence[ModelSOStubLlmProviderBinding | ModelSOOpenAICompatibleProviderBinding],
        selected_provider_id: str,
    ) -> ModelSOOpenAICompatibleProviderBinding:
        """Return the exact selected HTTP binding without constructing effects.

        The binding's own ``retry`` policy decides attempt count. A provider
        pinned to ``max_attempts=1`` stays single-shot (the retry loop makes one
        attempt and re-raises), so historically single-shot arms are byte-
        identical. A provider that opts into ``max_attempts>1`` — e.g. an arm
        behind an endpoint with intermittent transport stalls — reuses the
        client's existing bounded-backoff retry of RETRYABLE transport failures
        (timeouts / transient request errors) instead of aborting the match on
        the first stall. The attempt count and backoff schedule are already
        contract-bounded by ``ModelSOLlmRetryBinding`` (max_attempts 1..5, total
        backoff ≤ 300s), so no additional ceiling is enforced here.
        """

        selected = tuple(
            provider for provider in providers if provider.provider_id == selected_provider_id
        )
        if len(selected) != 1:
            raise ProviderRegistryError("selected live provider must resolve exactly once")
        provider = selected[0]
        if not isinstance(provider, ModelSOOpenAICompatibleProviderBinding):
            raise ValueError("selected live provider must be openai_compatible")
        return provider

    def select_many(
        self,
        *,
        providers: Sequence[ModelSOStubLlmProviderBinding | ModelSOOpenAICompatibleProviderBinding],
        selected_provider_ids: Sequence[str],
    ) -> tuple[ModelSOOpenAICompatibleProviderBinding, ...]:
        """Return each explicitly selected live provider exactly once."""

        ids = tuple(selected_provider_ids)
        if not ids or len(ids) != len(set(ids)):
            raise ProviderRegistryError("selected live providers must be non-empty and unique")
        return tuple(
            self.select(providers=providers, selected_provider_id=provider_id)
            for provider_id in ids
        )


class StaticLlmClientFactory:
    """Immutable provider selection over clients constructed at the root."""

    def __init__(self, clients: Mapping[str, ProtocolLlmClient]) -> None:
        self._clients = MappingProxyType(dict(clients))

    def client_for(self, provider_id: str) -> ProtocolLlmClient:
        try:
            return self._clients[provider_id]
        except KeyError as exc:
            raise ProviderRegistryError(f"unknown_provider: {provider_id!r}") from exc


__all__ = [
    "BoundedLlmClient",
    "BoundedLlmClientConsumedError",
    "HttpxJsonTransport",
    "NoSecretResolver",
    "OneShotLlmClient",
    "OneShotLlmClientConsumedError",
    "OpenAICompatibleClient",
    "ProviderRegistryError",
    "SelectedOnlyLlmClientBuilder",
    "StaticLlmClientFactory",
    "SystemSleeper",
]
