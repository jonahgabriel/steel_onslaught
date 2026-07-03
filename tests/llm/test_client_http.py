"""Tests for the OpenAI-compatible HTTP client + provider registry.

Covers the Rev-5 divergence remediations:
  D1 — fail-closed auth (declared key unset raises before any network call).
  D2 — provider endpoints live in ``providers.yaml``, not Python source.
  D4 — the client posts the COMPLETE endpoint URL verbatim (no base append).
  D5 — no paid-via-OpenRouter entries; GLM routes direct to z.ai.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from steel_onslaught.llm.client_http import (
    OpenAICompatibleClient,
    ProviderRegistryError,
    client_for_provider,
    load_providers,
)

# ---------------------------------------------------------------------------
# Fake httpx transport (records the POST url + headers; performs no network I/O)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5},
            "model": "served-model",
        }


class _FakeClient:
    last_url: str | None = None
    last_headers: dict[str, str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def post(
        self, url: str, *, headers: dict[str, str] | None = None, json: Any = None
    ) -> _FakeResponse:
        _FakeClient.last_url = url
        _FakeClient.last_headers = headers
        return _FakeResponse()


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    _FakeClient.last_url = None
    _FakeClient.last_headers = None
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    return _FakeClient


# ---------------------------------------------------------------------------
# D4 — verbatim complete URL (no rstrip, no /chat/completions append)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_posts_complete_url_verbatim(fake_httpx: type[_FakeClient]) -> None:
    url = "https://example.test/custom/v9/chat/completions"
    client = OpenAICompatibleClient(base_url=url, api_key_env=None)
    client.complete("sys", "usr")
    assert fake_httpx.last_url == url  # byte-for-byte, no append


@pytest.mark.unit
def test_trailing_slash_is_not_stripped(fake_httpx: type[_FakeClient]) -> None:
    """Proves the old ``rstrip('/') + '/chat/completions'`` seam is gone."""
    url = "http://host.local/v1/chat/completions/"
    client = OpenAICompatibleClient(base_url=url, api_key_env=None)
    client.complete("sys", "usr")
    assert fake_httpx.last_url == url


# ---------------------------------------------------------------------------
# D1 — fail-closed auth
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_declared_key_unset_raises_before_network(
    fake_httpx: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SO_TEST_KEY", raising=False)
    client = OpenAICompatibleClient(
        base_url="https://api.test/v1/chat/completions", api_key_env="SO_TEST_KEY"
    )
    with pytest.raises(RuntimeError, match="missing_api_key"):
        client.complete("sys", "usr")
    assert fake_httpx.last_url is None  # never reached the network


@pytest.mark.unit
def test_declared_empty_key_raises(
    fake_httpx: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SO_TEST_KEY", "")  # present-but-empty is still fail-closed
    client = OpenAICompatibleClient(
        base_url="https://api.test/v1/chat/completions", api_key_env="SO_TEST_KEY"
    )
    with pytest.raises(RuntimeError, match="missing_api_key"):
        client.complete("sys", "usr")
    assert fake_httpx.last_url is None


@pytest.mark.unit
def test_declared_key_present_sends_bearer(
    fake_httpx: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SO_TEST_KEY", "sk-secret")
    client = OpenAICompatibleClient(
        base_url="https://api.test/v1/chat/completions", api_key_env="SO_TEST_KEY"
    )
    client.complete("sys", "usr")
    assert fake_httpx.last_headers is not None
    assert fake_httpx.last_headers["Authorization"] == "Bearer sk-secret"


@pytest.mark.unit
def test_keyless_by_declaration_sends_no_auth(
    fake_httpx: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """api_key_env=None is keyless *by declaration*: no header, no raise."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAICompatibleClient(base_url="http://localhost:11434/v1/chat/completions")
    client.complete("sys", "usr")
    assert fake_httpx.last_headers is not None
    assert "Authorization" not in fake_httpx.last_headers


# ---------------------------------------------------------------------------
# D2 / D5 — providers.yaml registry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registry_loads_expected_providers() -> None:
    registry = load_providers()
    for pid in ("openai-compat", "qwen35", "qwen27", "deepseek", "glm-5.2", "glm-5.1", "glm-5"):
        assert pid in registry


@pytest.mark.unit
def test_no_paid_openrouter_entries() -> None:
    """D5: paid-via-OpenRouter entries dropped; no OpenRouter entries remain."""
    registry = load_providers()
    assert "openrouter-glm" not in registry
    assert "openrouter-claude" not in registry
    for entry in registry.values():
        assert "openrouter.ai" not in entry.endpoint_url


@pytest.mark.unit
def test_glm_routes_direct_zai_with_declared_key() -> None:
    entry = load_providers()["glm-5.2"]
    assert entry.endpoint_url == "https://api.z.ai/api/coding/paas/v4/chat/completions"
    assert entry.api_key_env == "LLM_GLM_API_KEY"


@pytest.mark.unit
def test_local_providers_are_keyless_and_complete_url() -> None:
    for pid in ("openai-compat", "qwen35", "qwen27", "deepseek"):
        entry = load_providers()[pid]
        assert entry.api_key_env is None
        assert entry.endpoint_url.endswith("/chat/completions")


# ---------------------------------------------------------------------------
# client_for_provider — public seam preserved
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_client_for_provider_returns_configured_client() -> None:
    client = client_for_provider("glm-5.2")
    assert isinstance(client, OpenAICompatibleClient)
    assert client._endpoint_url == "https://api.z.ai/api/coding/paas/v4/chat/completions"
    assert client._api_key_env == "LLM_GLM_API_KEY"
    assert client._model == "glm-5.2"


@pytest.mark.unit
def test_client_for_provider_unknown_fails_fast() -> None:
    with pytest.raises(ProviderRegistryError, match="unknown_provider"):
        client_for_provider("does-not-exist")


@pytest.mark.unit
def test_glm_client_from_registry_is_fail_closed(
    fake_httpx: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a registry GLM client refuses to send with no key set."""
    monkeypatch.delenv("LLM_GLM_API_KEY", raising=False)
    client = client_for_provider("glm-5.1")
    with pytest.raises(RuntimeError, match="missing_api_key"):
        client.complete("sys", "usr")
    assert fake_httpx.last_url is None
