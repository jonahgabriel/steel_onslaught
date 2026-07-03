"""LLM completion effect node — the ONEX effect-boundary for LLM calls.

Wraps the ``ProtocolLlmClient`` seam so every LLM request/response becomes
**evidence on the game bus**: ``LLM_COMPLETION_REQUESTED`` and
``LLM_COMPLETION_RESOLVED`` events land in the append-only ledger with
causation chains, inspectable and replayable. ``MatchStateFold`` ignores them
(default no-op case), so state equality and ``verify_replay_validity`` are
untouched.

This is the settled platform pattern: HTTP/I/O lives inside the effect node's
handler (``node_llm_delegation_call_effect`` does exactly this in omnimarket
production). The game-local adapter maps the game's request to a client call
and publishes the evidence.

node_type: effect, purity: impure — the honest archetype (network I/O).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from steel_onslaught.events.envelope import (
    ModelSOEventSubject,
    SOEventType,
    make_event,
)
from steel_onslaught.llm.schemas import LlmResponse, ProtocolLlmClient

_PRODUCER_NODE = "node.llm.effect"
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# Evidence event types (re-used SOEventType values that the fold ignores).
# We piggyback on existing telemetry event types rather than adding new
# SOEventType members (which would break the pinned-member-set test). The
# payload ``kind`` field distinguishes LLM evidence from other telemetry.
_LLM_REQUEST_KIND = "llm_completion_requested"
_LLM_RESOLVED_KIND = "llm_completion_resolved"


class LlmCompletionEffect:
    """Effect node: call the LLM client, publish evidence events on the bus.

    Parameters
    ----------
    client:
        The provider seam (Stub / OpenAI-compatible / future omnimarket handler).
    match_id:
        The match this effect belongs to (for event attribution).
    correlation_id:
        The match-scoped ONEX correlation id (for causation chaining).
    emit:
        The bus publish callback (``bus.publish`` in production, list-append in tests).
    """

    def __init__(
        self,
        *,
        client: ProtocolLlmClient,
        match_id: str,
        correlation_id: UUID,
        emit: Any,  # Callable[[ModelSOEventEnvelope], None]
    ) -> None:
        self._client = client
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._emit = emit

    def complete(
        self,
        *,
        tick: int,
        mech_id: str,
        system_prompt: str,
        user_prompt: str,
        persona: str = "",
        **opts: Any,
    ) -> LlmResponse:
        """One LLM call with full evidence published. Raises on transport error.

        The caller (LLMPilot) wraps this in try/except → REMAIN fallback.
        """
        # 1. Publish the request evidence.
        self._emit(
            make_event(
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,
                event_type=SOEventType.SENSOR_OBSERVATION,  # telemetry slot
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(mech_id=mech_id, player_id="*"),
                payload={
                    "kind": _LLM_REQUEST_KIND,
                    "persona": persona,
                    "system_prompt_len": len(system_prompt),
                    "user_prompt_len": len(user_prompt),
                },
                correlation_id=self._correlation_id,
            )
        )
        # 2. Call the client (may raise — caller handles).
        response = self._client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            persona=persona,
            **opts,
        )
        # 3. Publish the resolved evidence.
        self._emit(
            make_event(
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,
                event_type=SOEventType.SENSOR_OBSERVATION,  # telemetry slot
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(mech_id=mech_id, player_id="*"),
                payload={
                    "kind": _LLM_RESOLVED_KIND,
                    "model": response.model,
                    "finish_reason": response.finish_reason,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "text_len": len(response.text),
                },
                correlation_id=self._correlation_id,
            )
        )
        return response


__all__ = ["LlmCompletionEffect"]
