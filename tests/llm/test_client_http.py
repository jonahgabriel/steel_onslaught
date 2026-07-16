"""Hermetic tests for the injected OpenAI-compatible provider boundary."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from steel_onslaught.contracts.application import (
    ModelSOLlmRetryBinding,
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOSecretRef,
)
from steel_onslaught.llm.client_http import (
    HttpxJsonTransport,
    OpenAICompatibleClient,
    ProviderRegistryError,
    StaticLlmClientFactory,
)
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmTransportError,
    ModelSOLlmCompletionRequest,
    ModelSOOpenAIChatMessage,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    SecretResolutionError,
)
from steel_onslaught.llm.stub import StubLlmClient


def _config(
    *,
    endpoint_url: str = "https://provider.test/custom/chat/completions/",
    secret_ref: ModelSOSecretRef | None = None,
    max_tokens: int | None = None,
    max_attempts: int = 3,
) -> ModelSOOpenAICompatibleProviderBinding:
    return ModelSOOpenAICompatibleProviderBinding(
        kind="openai_compatible",
        provider_id="primary",
        endpoint_url=endpoint_url,
        model="explicit-model",
        secret_ref=secret_ref,
        timeout_seconds=17.0,
        max_tokens=max_tokens,
        retry=ModelSOLlmRetryBinding(
            max_attempts=max_attempts,
            initial_backoff_seconds=0.25,
            backoff_multiplier=2.0,
        ),
    )


def _request(*, json_mode: bool = True) -> ModelSOLlmCompletionRequest:
    return ModelSOLlmCompletionRequest(
        system_prompt="system",
        user_prompt="user",
        persona="persona",
        temperature=0.4,
        json_mode=json_mode,
        evidence_context=None,
    )


def _response() -> ModelSOOpenAIChatResponse:
    return ModelSOOpenAIChatResponse.model_validate(
        {
            "id": "provider-metadata-is-accepted",
            "choices": (
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                },
            ),
            "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            "model": "served-model",
        }
    )


def _provider_request() -> ModelSOOpenAIChatRequest:
    return ModelSOOpenAIChatRequest(
        model="model",
        messages=(
            ModelSOOpenAIChatMessage(role="system", content="system"),
            ModelSOOpenAIChatMessage(role="user", content="user"),
        ),
        temperature=0.1,
        max_tokens=None,
        response_format=None,
    )


class _Resolver:
    def __init__(self, value: str = "resolved-secret") -> None:
        self.value = value
        self.references: list[ModelSOSecretRef] = []

    def resolve(self, reference: ModelSOSecretRef) -> str:
        self.references.append(reference)
        return self.value


class _Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


class _Transport:
    def __init__(self, outcomes: list[ModelSOOpenAIChatResponse | Exception] | None = None) -> None:
        self.outcomes = list(outcomes or [_response()])
        self.calls: list[tuple[str, dict[str, str], ModelSOOpenAIChatRequest, float]] = []

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        self.calls.append((url, headers, request, timeout_seconds))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(
    *,
    config: ModelSOOpenAICompatibleProviderBinding | None = None,
    transport: _Transport | None = None,
    resolver: _Resolver | None = None,
    sleeper: _Sleeper | None = None,
) -> tuple[OpenAICompatibleClient, _Transport, _Resolver, _Sleeper]:
    resolved_transport = transport or _Transport()
    resolved_resolver = resolver or _Resolver()
    resolved_sleeper = sleeper or _Sleeper()
    return (
        OpenAICompatibleClient(
            config=config or _config(),
            transport=resolved_transport,
            secret_resolver=resolved_resolver,
            sleeper=resolved_sleeper,
        ),
        resolved_transport,
        resolved_resolver,
        resolved_sleeper,
    )


@pytest.mark.unit
def test_posts_complete_url_and_explicit_request_fields_verbatim() -> None:
    client, transport, _, _ = _client()
    response = client.complete(_request())

    url, headers, request, timeout = transport.calls[0]
    assert url == "https://provider.test/custom/chat/completions/"
    assert headers == {"Content-Type": "application/json"}
    assert timeout == 17.0
    assert request.model == "explicit-model"
    assert [message.content for message in request.messages] == ["system", "user"]
    assert request.temperature == 0.4
    assert request.response_format is not None
    assert response == LlmResponse.model_validate(
        {
            "text": "ok",
            "usage": {"prompt_tokens": 3, "completion_tokens": 5, "cost_usd": None},
            "model": "served-model",
            "finish_reason": "stop",
        }
    )


@pytest.mark.unit
@pytest.mark.parametrize(("configured", "present"), [(None, False), (128, True)])
def test_max_tokens_is_sent_only_when_explicitly_non_null(
    configured: int | None, present: bool
) -> None:
    client, transport, _, _ = _client(config=_config(max_tokens=configured))
    client.complete(_request())
    payload = transport.calls[0][2].model_dump(mode="json", exclude_none=True)
    assert ("max_tokens" in payload) is present
    if present:
        assert payload["max_tokens"] == 128


@pytest.mark.unit
def test_secret_reference_is_resolved_and_only_value_reaches_auth_header() -> None:
    reference = ModelSOSecretRef(kind="opaque", ref="secret://llm/primary")
    client, transport, resolver, _ = _client(config=_config(secret_ref=reference))
    client.complete(_request())
    assert resolver.references == [reference]
    assert transport.calls[0][1]["Authorization"] == "Bearer resolved-secret"


@pytest.mark.unit
def test_secret_resolver_failure_is_sanitized_and_never_reaches_transport() -> None:
    leaked = "secret://llm/primary sk-do-not-leak"

    class _FailingResolver:
        def resolve(self, reference: ModelSOSecretRef) -> str:
            raise RuntimeError(leaked)

    transport = _Transport()
    client = OpenAICompatibleClient(
        config=_config(secret_ref=ModelSOSecretRef(kind="opaque", ref="secret://llm/primary")),
        transport=transport,
        secret_resolver=_FailingResolver(),
        sleeper=_Sleeper(),
    )
    with pytest.raises(SecretResolutionError) as raised:
        client.complete(_request())
    assert str(raised.value) == "secret resolution failed"
    assert raised.value.__cause__ is None
    assert leaked not in repr(raised.value)
    assert transport.calls == []


@pytest.mark.unit
def test_retryable_failures_use_exact_bounded_backoff_schedule() -> None:
    transport = _Transport(
        [
            LlmTransportError("first", retryable=True),
            LlmTransportError("second", retryable=True),
            _response(),
        ]
    )
    sleeper = _Sleeper()
    client, _, _, _ = _client(transport=transport, sleeper=sleeper)
    assert client.complete(_request()).text == "ok"
    assert len(transport.calls) == 3
    assert sleeper.calls == [0.25, 0.5]


@pytest.mark.unit
def test_non_retryable_failure_stops_without_sleeping() -> None:
    transport = _Transport([LlmTransportError("invalid", retryable=False)])
    sleeper = _Sleeper()
    client, _, _, _ = _client(transport=transport, sleeper=sleeper)
    with pytest.raises(LlmTransportError, match="invalid"):
        client.complete(_request())
    assert len(transport.calls) == 1
    assert sleeper.calls == []


@pytest.mark.unit
def test_factory_selects_only_explicitly_registered_provider() -> None:
    factory = StaticLlmClientFactory({"stub": StubLlmClient(model="configured-stub")})
    assert isinstance(factory.client_for("stub"), StubLlmClient)
    with pytest.raises(ProviderRegistryError, match="unknown_provider"):
        factory.client_for("missing")


def _http_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (408, True), (429, True), (503, True)]
)
def test_http_statuses_are_sanitized_and_classified(status: int, retryable: bool) -> None:
    with _http_client(lambda request: httpx.Response(status, request=request)) as raw:
        transport = HttpxJsonTransport(raw)
        with pytest.raises(LlmTransportError) as raised:
            transport.post_json(
                url="https://provider.test/chat",
                headers={},
                request=_provider_request(),
                timeout_seconds=1.0,
            )
    assert str(raised.value) == f"LLM provider returned HTTP {status}"
    assert raised.value.retryable is retryable


@pytest.mark.unit
def test_http_transport_accepts_metadata_but_rejects_missing_consumed_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "max_tokens" not in body
        return httpx.Response(200, request=request, json={"choices": [], "model": "m"})

    with _http_client(handler) as raw:
        transport = HttpxJsonTransport(raw)
        with pytest.raises(LlmTransportError, match="invalid response contract") as raised:
            transport.post_json(
                url="https://provider.test/chat",
                headers={},
                request=_provider_request(),
                timeout_seconds=1.0,
            )
    assert raised.value.retryable is False


@pytest.mark.unit
def test_http_timeout_is_sanitized_and_retryable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("credential-like provider detail", request=request)

    with _http_client(timeout) as raw:
        with pytest.raises(LlmTransportError) as raised:
            HttpxJsonTransport(raw).post_json(
                url="https://provider.test/chat",
                headers={},
                request=_provider_request(),
                timeout_seconds=1.0,
            )
    assert str(raised.value) == "LLM request timed out"
    assert raised.value.retryable is True
    assert raised.value.__cause__ is None
