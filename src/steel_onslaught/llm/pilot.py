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

import json
import logging
from typing import Any

from steel_onslaught.llm.personas import Persona, get_persona
from steel_onslaught.llm.schemas import LlmResponse, ProtocolLlmClient
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


def _serialize_observation(obs: ModelSOPilotObservation) -> str:
    """Compact one-mech observation → prompt text (own state + noisy enemy)."""
    b = obs.boiler
    lines = [
        f"--- YOUR MECH (tick {obs.tick}) ---",
        f"hp: {obs.hp_percent:.0f}%  mode: {obs.current_mode}"
        f"  mode_lock_expired: {obs.mode_lock_expired}",
        f"position: ({obs.position.x},{obs.position.y})"
        f"  under_sensor_lock: {obs.under_sensor_lock}",
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

    @classmethod
    def from_persona_id(cls, *, client: ProtocolLlmClient, persona_id: str) -> LLMPilot:
        """Construct from a persona id (fail-fast on unknown persona)."""
        return cls(client=client, persona=get_persona(persona_id))

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        """Consult the LLM and return a validated decision, or REMAIN on failure."""
        user_prompt = _serialize_observation(observation)
        try:
            response = self._client.complete(
                system_prompt=self._persona.system_prompt,
                user_prompt=user_prompt,
                persona=self._persona.persona_id,
                temperature=self._persona.temperature,
                json_mode=True,
            )
        except Exception as exc:
            _LOG.warning("LLM call failed: %s", exc)
            return _fallback_decision(f"{type(exc).__name__}: {exc}")

        return self._parse_response(response, observation)

    def _parse_response(
        self, response: LlmResponse, observation: ModelSOPilotObservation
    ) -> ModelSOPilotDecision:
        """Parse the LLM's JSON text → validated decision, or REMAIN fallback."""
        try:
            parsed: dict[str, Any] = json.loads(response.text)
        except (json.JSONDecodeError, TypeError) as exc:
            return _fallback_decision(f"malformed JSON: {exc}")

        action_str = str(parsed.get("action", "")).strip().lower()
        action = _LLM_ACTION_VOCAB.get(action_str)
        if action is None:
            return _fallback_decision(f"unknown action {action_str!r}")

        # Validate against availability (e.g. can't fire a weapon on cooldown).
        allowed = available_actions(observation)
        if action not in allowed:
            return _fallback_decision(f"action {action_str!r} not available this tick")

        action_params = parsed.get("action_params", {})
        if not isinstance(action_params, dict):
            action_params = {}

        # If firing, ensure weapon_id is set — the LLM may omit it (intent: "fire
        # any ready weapon"). Pick a ready, affordable, in-range weapon. Without
        # this, the resolver gets weapon_id="" and drops the shot.
        if action is SOPilotAction.FIRE_WEAPON and "weapon_id" not in action_params:
            # Estimate enemy distance from the latest sensor reading.
            enemy_dist = (
                observation.enemy_observations[-1].distance_estimate
                if observation.enemy_observations
                else float("inf")
            )
            ready = [
                w
                for w in observation.weapons
                if w.cooldown_remaining_ticks == 0
                and observation.boiler.pressure_current >= w.pressure_cost
                and w.range >= enemy_dist
            ]
            if not ready:
                return _fallback_decision("no ready weapon in range")
            # Highest-damage ready weapon that can reach.
            chosen = max(ready, key=lambda w: w.damage)
            action_params["weapon_id"] = chosen.weapon_id

        # If moving, ensure direction is set (the resolver requires it).
        if action is SOPilotAction.MOVE and "direction" not in action_params:
            action_params["direction"] = "toward_enemy"

        confidence = float(parsed.get("confidence", 0.5))
        rationale = str(parsed.get("rationale", "")) or None

        return ModelSOPilotDecision(
            action=action,
            action_params=action_params,
            reason_code=SOPilotReasonCode.LLM_DECISION,
            confidence=confidence,
            considered_actions=[ModelSOConsideredAction(action=action, score=confidence)],
            rationale=rationale,
        )


__all__ = ["LLMPilot"]
