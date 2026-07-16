"""OpenAI-compatible HTTP LLM client (the real provider implementation).

Posts to the **complete** chat-completions endpoint URL **verbatim** — the URL
declared for the provider is sent byte-for-byte, with no base-url ``rstrip`` and
no ``/chat/completions`` append. Model, key-env, and timeout for every provider,
plus public/localhost endpoints, are declared in the contract file
``providers.yaml`` (loaded once, validated by the frozen
:class:`ProviderEndpoint` model). Private endpoints come from a gitignored,
typed local overlay — never hardcoded in Python source or committed registry
data.

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
# Gitignored local overlay supplying endpoint_url values for providers that
# declare none in the committed registry (private LAN/Tailscale/lab servers).
# Committed sibling ``providers.local.yaml.example`` documents the format.
_LOCAL_OVERLAY_YAML = Path(__file__).parent / "providers.local.yaml"
_LOCAL_OVERLAY_EXAMPLE = Path(__file__).parent / "providers.local.yaml.example"


class ProviderRegistryError(ValueError):
    """``providers.yaml`` is malformed, or names a duplicate/unknown provider."""


class ProviderOverlayMissingError(ProviderRegistryError):
    """A requested provider has no committed or locally overlaid endpoint."""


class ProviderEndpoint(BaseModel):
    """One provider entry from ``providers.yaml`` (frozen contract row).

    ``endpoint_url`` is the COMPLETE chat-completions URL, posted verbatim, or
    ``None`` when a private endpoint must come from the gitignored local overlay.
    ``api_key_env`` is the name of the env var holding the key, or ``None`` for
    keyless-by-declaration (local) providers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str
    endpoint_url: str | None = None
    model: str
    api_key_env: str | None = None
    timeout_s: float = _DEFAULT_TIMEOUT


def _load_local_overlay() -> dict[str, str]:
    """Read and validate the gitignored local endpoint overlay.

    An absent file yields an empty map so public providers remain usable. A
    private provider with no overlay entry fails closed only when requested.
    """
    if not _LOCAL_OVERLAY_YAML.exists():
        return {}
    raw: Any = yaml.safe_load(_LOCAL_OVERLAY_YAML.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("endpoints"), dict):
        raise ProviderRegistryError(
            f"local overlay must map 'endpoints' -> dict ({_LOCAL_OVERLAY_YAML})"
        )
    endpoints: dict[str, str] = {}
    for provider_id, endpoint_url in raw["endpoints"].items():
        if not isinstance(provider_id, str) or not isinstance(endpoint_url, str):
            raise ProviderRegistryError(
                "local overlay 'endpoints' must map str provider_id -> str url "
                f"({_LOCAL_OVERLAY_YAML})"
            )
        endpoints[provider_id] = endpoint_url
    return endpoints


@lru_cache(maxsize=1)
def load_providers() -> dict[str, ProviderEndpoint]:
    """Load and validate the committed registry plus optional local overlay."""
    raw: Any = yaml.safe_load(_PROVIDERS_YAML.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        raise ProviderRegistryError(
            f"providers.yaml must map 'providers' -> list ({_PROVIDERS_YAML})"
        )
    overlay = _load_local_overlay()
    registry: dict[str, ProviderEndpoint] = {}
    for item in raw["providers"]:
        entry = ProviderEndpoint.model_validate(item)
        if entry.provider_id in registry:
            raise ProviderRegistryError(
                f"duplicate_provider_id: {entry.provider_id!r} declared more than "
                f"once in {_PROVIDERS_YAML}"
            )
        overlay_url = overlay.get(entry.provider_id)
        if overlay_url is not None:
            if entry.endpoint_url is not None:
                raise ProviderRegistryError(
                    f"overlay_conflict: {entry.provider_id!r} declares a committed "
                    f"endpoint_url in {_PROVIDERS_YAML}; the local overlay must not "
                    f"override it ({_LOCAL_OVERLAY_YAML})"
                )
            entry = entry.model_copy(update={"endpoint_url": overlay_url})
        registry[entry.provider_id] = entry
    unknown = set(overlay) - set(registry)
    if unknown:
        raise ProviderRegistryError(
            f"overlay_unknown_provider: {sorted(unknown)} in {_LOCAL_OVERLAY_YAML} "
            f"match no provider declared in {_PROVIDERS_YAML}"
        )
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
    if entry.endpoint_url is None:
        raise ProviderOverlayMissingError(
            f"missing_local_endpoint: provider {provider!r} declares no committed "
            f"endpoint_url and no local overlay supplies one. Copy "
            f"{_LOCAL_OVERLAY_EXAMPLE.name} to {_LOCAL_OVERLAY_YAML} and set its "
            "endpoint URL (private LAN/Tailscale/lab address); refusing to "
            "fall back to a default."
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
    "ProviderOverlayMissingError",
    "ProviderRegistryError",
    "client_for_provider",
    "load_providers",
]
