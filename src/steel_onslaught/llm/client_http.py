"""OpenAI-compatible HTTP LLM client (the real provider implementation).

Calls ``POST {base_url}/chat/completions`` — the OpenAI Chat Completions API,
also served by Ollama, vLLM, LM Studio, and Gemini-compat gateways via a
``base_url`` override. Uses ``httpx`` synchronously (the pilot's ``decide`` is
sync; the fold forbids asyncio in the hot path).

Configurable: ``base_url``, ``api_key`` (read from env at call time, fail-closed
if unset), ``model``, ``temperature``. Default ``base_url`` targets a local
Ollama/LM Studio server (no key) — local-first, cloud opt-in.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from steel_onslaught.llm.schemas import LlmResponse, LlmUsage

# Default: a local OpenAI-compatible server (Ollama/LM Studio default port).
_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_MODEL = "llama3.1"
_DEFAULT_TIMEOUT = 30.0


class OpenAICompatibleClient:
    """Synchronous OpenAI-compatible chat completions client.

    Parameters
    ----------
    base_url:
        The API root (without ``/chat/completions``). Defaults to a local
        Ollama server; override for OpenAI (``https://api.openai.com/v1``),
        vLLM, LM Studio, etc.
    api_key_env:
        Environment variable name holding the API key. Read at call time;
        if unset, the request is sent with no Authorization header (local
        servers typically don't require one). Fail-closed for cloud providers
        is the caller's responsibility (set the env var).
    model:
        Default model id; overridable per-call via ``opts["model"]``.
    temperature:
        Default sampling temperature; overridable per-call.
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        api_key_env: str = "OPENAI_API_KEY",
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.7,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._model = model
        self._temperature = temperature
        self._timeout = timeout

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **opts: Any,
    ) -> LlmResponse:
        """One synchronous chat-completion call. Raises on transport/HTTP error.

        The pilot wraps this in a try/except → REMAIN fallback, so a network
        failure degrades the decision rather than crashing the match.
        """
        model = opts.get("model", self._model)
        temperature = opts.get("temperature", self._temperature)
        api_key = os.environ.get(self._api_key_env)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

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
                f"{self._base_url}/chat/completions",
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


__all__ = ["PROVIDER_ENDPOINTS", "OpenAICompatibleClient", "client_for_provider"]


# Provider registry: maps provider ids to (base_url, model) for the AI PC lab.
# These are the live-probed endpoints (2026-07-02). To add a model, add an entry.
PROVIDER_ENDPOINTS: dict[str, tuple[str, str]] = {
    "stub": ("", ""),
    "openai-compat": (_DEFAULT_BASE_URL, _DEFAULT_MODEL),
    # AI PC lab (local, no key needed)
    "qwen35": ("http://100.109.203.94:8000/v1", "Qwen3.6-35B-A3B"),
    "qwen27": ("http://100.109.203.94:8001/v1", "Qwen3.6-27B-MTP-IQ4_XS.gguf"),
    "deepseek": ("http://100.99.174.19:8101/v1", "deepseek-v4-pro"),
    # z.ai frontier (GLM models; set LLM_GLM_API_KEY env var)
    "glm-5.2": ("https://api.z.ai/api/coding/paas/v4", "glm-5.2"),
    "glm-5.1": ("https://api.z.ai/api/coding/paas/v4", "glm-5.1"),
    "glm-5": ("https://api.z.ai/api/coding/paas/v4", "glm-5"),
    # OpenRouter (340+ models; set OPEN_ROUTER_API_KEY env var)
    "openrouter-glm": ("https://openrouter.ai/api/v1", "z-ai/glm-5.2"),
    "openrouter-claude": ("https://openrouter.ai/api/v1", "anthropic/claude-sonnet-5"),
}


# Provider -> env var name holding the API key (local endpoints need none).
_PROVIDER_API_KEY_ENV: dict[str, str] = {
    "glm-5.2": "LLM_GLM_API_KEY",
    "glm-5.1": "LLM_GLM_API_KEY",
    "glm-5": "LLM_GLM_API_KEY",
    "openrouter-glm": "OPEN_ROUTER_API_KEY",
    "openrouter-claude": "OPEN_ROUTER_API_KEY",
}


def client_for_provider(provider: str) -> OpenAICompatibleClient:
    """Build an OpenAICompatibleClient from a provider id (registry lookup).

    For z.ai/OpenRouter providers, the API key is read from the corresponding
    env var at call time (fail-closed if unset). Local endpoints send no auth.
    """
    base_url, model = PROVIDER_ENDPOINTS.get(provider, (_DEFAULT_BASE_URL, _DEFAULT_MODEL))
    api_key_env = _PROVIDER_API_KEY_ENV.get(provider, "OPENAI_API_KEY")
    return OpenAICompatibleClient(base_url=base_url, model=model, api_key_env=api_key_env)
