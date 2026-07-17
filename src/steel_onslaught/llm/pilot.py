"""The LLM pilot — a pilot archetype that consults an LLM for each decision.

Implements ``PilotProtocol.decide(observation) -> ModelSOPilotDecision`` by:
  1. Serializing the observation to a compact prompt.
  2. Calling the LLM (via the replaceable ``ProtocolLlmClient`` seam).
  3. Parsing + validating the LLM's JSON response against the action vocabulary.
  4. Returning a decision (with the LLM's ``rationale``), OR degrading to REMAIN
     on any failure (timeout, malformed JSON, invalid action) — never crashing
     the match.

Nondeterministic by design (the LLM samples), but replay-validity holds: the
fold ignores ``PILOT_DECISION_MADE`` events (they're telemetry), and the
recorded ledger's resolved events replay identically regardless of how the
decision was produced.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr, ValidationError

from steel_onslaught.contracts.mode import ModelSOModeSwitchIntentPayload
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMoveIntentPayload,
    ModelSOWeaponFireIntentPayload,
)
from steel_onslaught.immutable import FrozenJSONMapping, thaw_json_mapping
from steel_onslaught.llm.effect import LlmSemanticError, consume_llm_completion
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.schemas import (
    LlmResponse,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
    ProtocolLlmClient,
)
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
    available_actions,
)

_LOG = logging.getLogger(__name__)

# Actions the LLM is allowed to return (a subset — emergency/module/disengage
# are not exposed to keep the prompt simple).
_LLM_ACTION_VOCAB: dict[str, SOPilotAction] = {
    "remain": SOPilotAction.REMAIN,
    "move": SOPilotAction.MOVE,
    "fire_weapon": SOPilotAction.FIRE_WEAPON,
    "switch_mode": SOPilotAction.SWITCH_MODE,
    "vent": SOPilotAction.VENT,
}


class _ModelSOLlmPilotResponse(BaseModel):
    """Closed semantic boundary for nondeterministic provider output."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    action: StrictStr = Field(min_length=1)
    action_params: FrozenJSONMapping
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rationale: StrictStr = Field(min_length=1)


def _serialize_observation(obs: ModelSOPilotObservation) -> str:
    """Compact one-mech observation → prompt text (own state + noisy enemy)."""
    b = obs.boiler
    lines = [
        f"--- YOUR MECH (tick {obs.tick}) ---",
        f"hp: {obs.hp_percent:.0f}%  mode: {obs.current_mode}"
        f"  mode_lock_expired: {obs.mode_lock_expired}",
        f"position: ({obs.position.x},{obs.position.y})"
        f"  under_sensor_lock: {obs.under_sensor_lock}",
        f"terrain: line_of_sight_to_enemy: {obs.has_line_of_sight_to_enemy}"
        f"  blocked_directions: [{', '.join(d.value for d in obs.blocked_directions)}]",
        f"boiler: pressure {b.pressure_current}/{b.pressure_maximum}"
        f"  heat {b.heat_current}/{b.heat_rupture_threshold}"
        f"  redline: {b.status_redline}",
        "weapons:",
    ]
    for w in obs.weapons:
        lines.append(
            f"  - {w.weapon_id}: damage={w.damage} range={w.range} "
            f"pressure_cost={w.pressure_cost} heat_generated={w.heat_generated} "
            f"cooldown_remaining_ticks: {w.cooldown_remaining_ticks}"
        )
    if obs.enemy_observations:
        lines.append("--- ENEMY (noisy sensor readings, newest last) ---")
        for r in obs.enemy_observations[-3:]:  # last 3 readings
            lines.append(
                f"  tick {r.tick}: distance_estimate={r.distance_estimate:.1f} "
                f"confidence={r.confidence:.2f}"
                + (f" heat_estimate={r.heat_estimate}" if r.heat_estimate is not None else "")
            )
    else:
        lines.append("--- ENEMY: no sensor readings (enemy not detected) ---")
    return "\n".join(lines)


def _fallback_decision(reason: str) -> ModelSOPilotDecision:
    """A REMAIN decision used when the LLM call fails or returns invalid output."""
    return ModelSOPilotDecision(
        action=SOPilotAction.REMAIN,
        action_params={},
        reason_code=SOPilotReasonCode.LLM_FALLBACK,
        confidence=0.0,
        considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.0)],
        rationale=f"LLM fallback: {reason}",
    )


class LLMPilot:
    """A pilot archetype that consults an LLM for each decision.

    Satisfies ``PilotProtocol`` structurally (single sync ``decide`` method).
    The LLM call is wrapped so any failure degrades to REMAIN rather than
    crashing the match.

    Parameters
    ----------
    client:
        The LLM provider seam (``StubLlmClient`` for tests, ``OpenAICompatibleClient``
        for real play, or a future omnimarket-imported handler adapter).
    persona:
        The persona contract (system prompt + opts) shaping the playstyle.
    """

    def __init__(self, *, client: ProtocolLlmClient, persona: Persona) -> None:
        self._client = client
        self._persona = persona

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        """Consult the LLM and return a validated decision, or REMAIN on failure."""
        user_prompt = _serialize_observation(observation)
        try:
            return consume_llm_completion(
                client=self._client,
                request=ModelSOLlmCompletionRequest(
                    system_prompt=self._persona.system_prompt,
                    user_prompt=user_prompt,
                    persona=self._persona.persona_id,
                    temperature=self._persona.temperature,
                    json_mode=True,
                    evidence_context=ModelSOLlmEvidenceContext(
                        match_id=observation.match_id,
                        mech_id=observation.mech_id,
                        player_id=observation.player_id,
                        tick=observation.tick,
                        correlation_id=None,
                    ),
                ),
                consumer=lambda response: self._parse_response(response, observation),
            )
        except Exception as exc:
            _LOG.warning("LLM call failed (%s)", type(exc).__name__)
            return _fallback_decision(type(exc).__name__)

    def _parse_response(
        self, response: LlmResponse, observation: ModelSOPilotObservation
    ) -> ModelSOPilotDecision:
        """Parse the LLM's JSON text → validated decision, or REMAIN fallback."""
        try:
            parsed = _ModelSOLlmPilotResponse.model_validate_json(response.text)
        except (ValidationError, ValueError, TypeError):
            raise LlmSemanticError("malformed semantic JSON") from None

        action_str = parsed.action.strip().lower()
        action = _LLM_ACTION_VOCAB.get(action_str)
        if action is None:
            raise LlmSemanticError("unknown action")

        # Validate against availability (e.g. can't fire a weapon on cooldown).
        allowed = available_actions(observation)
        if action not in allowed:
            raise LlmSemanticError("action unavailable")

        action_params = thaw_json_mapping(parsed.action_params)
        try:
            match action:
                case SOPilotAction.MOVE:
                    ModelSOMoveIntentPayload.model_validate(action_params)
                case SOPilotAction.FIRE_WEAPON:
                    fire = ModelSOWeaponFireIntentPayload.model_validate(action_params)
                    if fire.weapon_id not in {weapon.weapon_id for weapon in observation.weapons}:
                        raise ValueError("unknown weapon")
                case SOPilotAction.SWITCH_MODE:
                    ModelSOModeSwitchIntentPayload.model_validate(action_params)
                case SOPilotAction.VENT | SOPilotAction.REMAIN:
                    ModelSOEmptyPayload.model_validate(action_params)
        except (ValidationError, ValueError, TypeError):
            raise LlmSemanticError("invalid action parameters") from None

        confidence = parsed.confidence
        rationale = parsed.rationale

        return ModelSOPilotDecision(
            action=action,
            action_params=action_params,
            reason_code=SOPilotReasonCode.LLM_DECISION,
            confidence=confidence,
            considered_actions=[ModelSOConsideredAction(action=action, score=confidence)],
            rationale=rationale,
        )


__all__ = ["LLMPilot"]
