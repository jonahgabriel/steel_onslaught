"""Injected OpenAI-compatible client and transport adapters.

Provider configuration is owned by the validated application overlay. This
module performs no environment, package-path, registry, or constructor lookup.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from types import MappingProxyType

import httpx

from steel_onslaught.contracts.application import (
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOSecretRef,
)
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmTransportError,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOOpenAIChatMessage,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    ModelSOOpenAIResponseFormat,
    ProtocolHttpTransport,
    ProtocolLlmClient,
    ProtocolSecretResolver,
    ProtocolSleeper,
    SecretResolutionError,
)


class ProviderRegistryError(ValueError):
    """A requested provider is absent from the immutable injected registry."""


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
            raise LlmTransportError("LLM request timed out", retryable=True) from None
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise LlmTransportError(
                f"LLM provider returned HTTP {status_code}",
                retryable=status_code in {408, 429} or status_code >= 500,
            ) from None
        except httpx.RequestError:
            raise LlmTransportError("LLM transport request failed", retryable=True) from None
        try:
            return ModelSOOpenAIChatResponse.model_validate(response.json())
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

    def complete(
        self,
        request: ModelSOLlmCompletionRequest,
    ) -> LlmResponse:
        provider_request = ModelSOOpenAIChatRequest(
            model=self._config.model,
            messages=(
                ModelSOOpenAIChatMessage(role="system", content=request.system_prompt),
                ModelSOOpenAIChatMessage(role="user", content=request.user_prompt),
            ),
            temperature=request.temperature,
            max_tokens=self._config.max_tokens,
            response_format=(
                ModelSOOpenAIResponseFormat(type="json_object") if request.json_mode else None
            ),
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
    "HttpxJsonTransport",
    "NoSecretResolver",
    "OpenAICompatibleClient",
    "ProviderRegistryError",
    "StaticLlmClientFactory",
    "SystemSleeper",
]
