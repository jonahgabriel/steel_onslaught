"""OpenAI-compatible HTTP LLM client (the real provider implementation).

Posts to the **complete** chat-completions endpoint URL **verbatim** — the URL
declared for the provider is sent byte-for-byte, with no base-url ``rstrip`` and
no ``/chat/completions`` append. Endpoint, model, key-env, and timeout for every
provider are declared in the contract file ``providers.yaml`` (loaded once,
validated by the frozen :class:`ProviderEndpoint` model) — never hardcoded in
Python source.

Auth is **fail-closed**: a provider that declares an ``api_key_env`` whose value
is unset (or empty) raises before any network call — it never silently sends an
unauthenticated request. A provider that declares ``api_key_env: null`` is
keyless *by declaration* (local servers such as Ollama/LM Studio/vLLM).

Uses ``httpx`` synchronously (the pilot's ``decide`` is sync; the fold forbids
asyncio in the hot path).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from steel_onslaught.llm.schemas import LlmResponse, LlmUsage

# Default direct-construction target: a local OpenAI-compatible server. This is
# a COMPLETE endpoint URL, posted verbatim.
_DEFAULT_ENDPOINT_URL = "http://localhost:11434/v1/chat/completions"
_DEFAULT_MODEL = "llama3.1"
_DEFAULT_TIMEOUT = 30.0

_PROVIDERS_YAML = Path(__file__).parent / "providers.yaml"


class ProviderRegistryError(ValueError):
    """``providers.yaml`` is malformed, or names a duplicate/unknown provider."""


class ProviderEndpoint(BaseModel):
    """One provider entry from ``providers.yaml`` (frozen contract row).

    ``endpoint_url`` is the COMPLETE chat-completions URL, posted verbatim.
    ``api_key_env`` is the name of the env var holding the key, or ``None`` for
    keyless-by-declaration (local) providers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str
    endpoint_url: str
    model: str
    api_key_env: str | None = None
    timeout_s: float = _DEFAULT_TIMEOUT


@lru_cache(maxsize=1)
def load_providers() -> dict[str, ProviderEndpoint]:
    """Load + validate ``providers.yaml`` once; return a ``provider_id`` map."""
    raw: Any = yaml.safe_load(_PROVIDERS_YAML.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        raise ProviderRegistryError(
            f"providers.yaml must map 'providers' -> list ({_PROVIDERS_YAML})"
        )
    registry: dict[str, ProviderEndpoint] = {}
    for item in raw["providers"]:
        entry = ProviderEndpoint.model_validate(item)
        if entry.provider_id in registry:
            raise ProviderRegistryError(
                f"duplicate_provider_id: {entry.provider_id!r} declared more than "
                f"once in {_PROVIDERS_YAML}"
            )
        registry[entry.provider_id] = entry
    return registry


class OpenAICompatibleClient:
    """Synchronous OpenAI-compatible chat completions client.

    Parameters
    ----------
    base_url:
        The **complete** chat-completions endpoint URL, posted verbatim (no
        append). Defaults to a local Ollama/LM Studio endpoint; override for any
        OpenAI-compatible server. (Named ``base_url`` for call-site stability.)
    api_key_env:
        Name of the env var holding the API key, or ``None`` for keyless
        (local) providers. When a name is given, the key is read at call time
        and the request **fails closed** — it raises if the var is unset/empty
        rather than sending an unauthenticated request.
    model:
        Default model id; overridable per-call via ``opts["model"]``.
    temperature:
        Default sampling temperature; overridable per-call.
    timeout:
        Per-request timeout (seconds).
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_ENDPOINT_URL,
        api_key_env: str | None = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.7,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        # Posted verbatim — no rstrip, no path append.
        self._endpoint_url = base_url
        self._api_key_env = api_key_env
        self._model = model
        self._temperature = temperature
        self._timeout = timeout

    def _resolve_auth_header(self) -> dict[str, str]:
        """Fail-closed key resolution → the Authorization header (or none).

        Keyless-by-declaration (``api_key_env is None``) → no header. A declared
        key that resolves to nothing raises **before** any network call.
        """
        if self._api_key_env is None:
            return {}
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise RuntimeError(
                f"missing_api_key: provider declares api_key_env "
                f"{self._api_key_env!r} but it is unset/empty; refusing to send "
                f"an unauthenticated request to {self._endpoint_url!r}"
            )
        return {"Authorization": f"Bearer {api_key}"}

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **opts: Any,
    ) -> LlmResponse:
        """One synchronous chat-completion call. Raises on transport/HTTP error.

        The pilot wraps this in a try/except → REMAIN fallback, so a network
        failure degrades the decision rather than crashing the match. A
        fail-closed missing-key raise surfaces the same way.
        """
        model = opts.get("model", self._model)
        temperature = opts.get("temperature", self._temperature)

        headers = {"Content-Type": "application/json"}
        headers.update(self._resolve_auth_header())

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        # Request JSON output if the caller asks for it (most compat servers
        # support response_format; older ones ignore it).
        if opts.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                self._endpoint_url,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        usage_raw = data.get("usage", {})
        usage = LlmUsage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            cost_usd=0.0,  # cost computation is provider-specific; left for the tuner sidecar
        )
        return LlmResponse(
            text=message["content"],
            usage=usage,
            model=data.get("model", model),
            finish_reason=choice.get("finish_reason", ""),
        )


def client_for_provider(provider: str) -> OpenAICompatibleClient:
    """Build an :class:`OpenAICompatibleClient` from a provider id.

    Resolves the endpoint/model/key-env/timeout from ``providers.yaml``. Fails
    fast (``ProviderRegistryError``) on an unknown provider — no silent
    fall-through to a local default. Cloud providers whose ``api_key_env`` is
    unset fail closed at call time (see :class:`OpenAICompatibleClient`).
    """
    registry = load_providers()
    entry = registry.get(provider)
    if entry is None:
        raise ProviderRegistryError(
            f"unknown_provider: {provider!r} is not declared in {_PROVIDERS_YAML} "
            f"(known: {sorted(registry)})"
        )
    return OpenAICompatibleClient(
        base_url=entry.endpoint_url,
        api_key_env=entry.api_key_env,
        model=entry.model,
        timeout=entry.timeout_s,
    )


__all__ = [
    "OpenAICompatibleClient",
    "ProviderEndpoint",
    "ProviderRegistryError",
    "client_for_provider",
    "load_providers",
]
