"""LLM completion seam — the replaceable provider boundary.

A single Protocol (``ProtocolLlmClient``) with one sync method. The LLM pilot
and tuner depend on this Protocol, never on a specific SDK, so the provider is
swappable: an OpenAI-compatible HTTP client, a future omnimarket-imported
handler, or a deterministic stub for offline development.

Why sync: ``PilotProtocol.decide`` is synchronous (called inside the tick loop),
and the fold's purity contract forbids asyncio in the hot path. The OpenAI
chat-completions endpoint is a plain HTTP request; ``httpx.Client`` (already a
dependency) handles it synchronously.

The seam is deliberately minimal — request text + opts in, response text + usage
out — so it carries no provider-specific assumptions. Personas (game contracts)
and endpoint resolution (provider config) live elsewhere; this is just the call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class LlmUsage:
    """Token/cost accounting for one completion (carried in decision evidence)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class LlmResponse:
    """A completed LLM call's text + usage. Failures raise (the pilot catches)."""

    text: str
    usage: LlmUsage = field(default_factory=LlmUsage)
    model: str = ""
    finish_reason: str = ""


@runtime_checkable
class ProtocolLlmClient(Protocol):
    """The replaceable LLM provider seam.

    Implementations:
    - ``OpenAICompatibleClient`` (llm/client_http.py) — real provider via httpx.
    - ``StubLlmClient`` (llm/stub.py) — deterministic table-driven responses.

    Future: an omnimarket-imported ``HandlerLlmDelegationCall`` adapter behind
    this same Protocol (once the sibling version alignment is resolved).
    """

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **opts: Any,
    ) -> LlmResponse: ...


__all__ = ["LlmResponse", "LlmUsage", "ProtocolLlmClient"]
