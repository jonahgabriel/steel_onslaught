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

import hashlib
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr, ValidationError

from steel_onslaught.contracts.application import ModelSOLlmImageAttachmentBinding
from steel_onslaught.contracts.mode import ModelSOModeSwitchIntentPayload
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMoveIntentPayload,
    ModelSOWeaponFireIntentPayload,
)
from steel_onslaught.immutable import FrozenJSONMapping, thaw_json_mapping
from steel_onslaught.llm.effect import LlmSemanticError, consume_llm_completion
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.render import render_observation_png
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmResponse,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
    ModelSOLlmImageAttachment,
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

type LlmPilotFailurePolicy = Literal["fallback", "raise"]

# Actions the LLM is allowed to return (a subset — emergency/module/disengage
# are not exposed to keep the prompt simple).
_LLM_ACTION_VOCAB: dict[str, SOPilotAction] = {
    "remain": SOPilotAction.REMAIN,
    "move": SOPilotAction.MOVE,
    "fire_weapon": SOPilotAction.FIRE_WEAPON,
    "switch_mode": SOPilotAction.SWITCH_MODE,
    "vent": SOPilotAction.VENT,
}

_TACTICAL_OBJECTIVES: dict[str, str] = {
    "berserker": "close quickly and force a point-blank exchange",
    "sniper": "hold maximum standoff, preserve heat headroom, and punish overextension",
    "opportunist": "probe from range, wait for heat or confidence mistakes, then counter-punch",
}

# The ONE sentence that differs between the V-TEXT and V-IMG arms of the
# 2026-07-24 vision-representation experiment (within-model isolation): a
# neutral pointer to the attached image, carrying no strategy or additional
# information beyond what the text prompt already states. Every other
# character of the user prompt is byte-identical between the two arms.
_IMAGE_ATTACHMENT_NOTE = (
    "An image of the current arena state is attached below; it depicts the "
    "same information described above (your position, cover cells, "
    "objectives, and the enemy distance ring)."
)


class _ModelSOLlmPilotResponse(BaseModel):
    """Closed semantic boundary for nondeterministic provider output."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    action: StrictStr = Field(min_length=1)
    action_params: FrozenJSONMapping
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rationale: StrictStr = Field(min_length=1)


def _serialize_observation(obs: ModelSOPilotObservation, *, persona_id: str) -> str:
    """Compact one-mech observation → prompt text (own state + noisy enemy)."""
    b = obs.boiler
    lines = [
        f"--- YOUR MECH (tick {obs.tick}) ---",
        f"role: {persona_id}",
        "tactical_objective: "
        f"{_TACTICAL_OBJECTIVES.get(persona_id, 'adapt to terrain, spacing, and heat')}",
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
    allowed_actions = sorted(
        action.value for action in available_actions(obs) if action in _LLM_ACTION_VOCAB.values()
    )
    ready_weapon_ids = [
        weapon.weapon_id
        for weapon in obs.weapons
        if weapon.cooldown_remaining_ticks == 0
        and obs.boiler.pressure_current >= weapon.pressure_cost
    ]
    lines.extend(
        (
            f"available_actions: [{', '.join(allowed_actions)}]",
            f"ready_weapon_ids: [{', '.join(ready_weapon_ids)}]",
            "action_rule: choose only an available action; fire_weapon also requires "
            "an enemy sensor reading within the selected weapon range; otherwise move, "
            "vent, or remain.",
        )
    )
    if obs.objectives and obs.victory_points is not None:
        # Objective-victory legibility (Phase 4).  Rendered ONLY on objective
        # arenas so every objective-free prompt stays byte-identical.
        vp = obs.victory_points
        lines.append(
            f"--- OBJECTIVES (hold a cell within 1, uncontested, to score; "
            f"first to {vp.vp_threshold} VP wins) ---"
        )
        lines.append(f"victory_points: you {vp.own_vp} vs enemy {vp.enemy_vp}")
        for objective in obs.objectives:
            lines.append(
                f"  - {objective.objective_id}: cell=({objective.cell.x},{objective.cell.y}) "
                f"vp_per_round={objective.vp_per_round} control={objective.control} "
                f"your_distance={objective.own_distance_chebyshev}"
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

    def __init__(
        self,
        *,
        client: ProtocolLlmClient,
        persona: Persona,
        failure_policy: LlmPilotFailurePolicy = "fallback",
        image_attachment: ModelSOLlmImageAttachmentBinding | None = None,
    ) -> None:
        if failure_policy not in ("fallback", "raise"):
            raise ValueError(f"unknown LLM pilot failure policy: {failure_policy!r}")
        self._client = client
        self._persona = persona
        self._failure_policy = failure_policy
        # Present only for the V-IMG arm's provider binding (2026-07-24
        # vision-representation experiment). ``None`` for every other pilot,
        # which keeps ``decide`` producing the exact same request it always
        # has.
        self._image_attachment_config = image_attachment
        # Remember only each mech's own observed HP trend.  This is pilot
        # context, not authoritative match state: the observation remains the
        # sole source of truth and the maps are intentionally not serialized
        # into events or projections.
        self._last_hp_percent_by_mech: dict[str, float] = {}
        self._hp_loss_streak_by_mech: dict[str, int] = {}

    @property
    def client(self) -> ProtocolLlmClient:
        """Return the injected client for composition-only adapter seams."""

        return self._client

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        """Consult the LLM and return a validated decision, or REMAIN on failure."""
        user_prompt = self._serialize_observation_with_memory(observation)
        image_attachment = self._render_image_attachment(observation)
        if image_attachment is not None:
            user_prompt = f"{user_prompt}\n\n{_IMAGE_ATTACHMENT_NOTE}"
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
                    image_attachment=image_attachment,
                ),
                consumer=lambda response: self._parse_response(response, observation),
            )
        except LlmCompletionBoundaryError:
            # Provider length/timeout boundaries are terminal live-match
            # failures. Never convert them into a deterministic REMAIN action.
            raise
        except Exception as exc:
            _LOG.warning("LLM call failed (%s)", type(exc).__name__)
            if self._failure_policy == "raise":
                raise
            return _fallback_decision(type(exc).__name__)

    def _render_image_attachment(
        self, observation: ModelSOPilotObservation
    ) -> ModelSOLlmImageAttachment | None:
        """Render + persist this tick's deterministic PNG, or ``None`` for V-TEXT.

        Persists under ``render_output_dir/<match_id>/tick_<NNNN>_<mech_id>.png``
        (state-root-relative, tick-keyed, no ULIDs/wall-clock in the path) so
        the sha256 recorded in the ``LLM_COMPLETION_REQUESTED`` ledger event is
        joinable to a durable evidence artifact.
        """
        config = self._image_attachment_config
        if config is None:
            return None
        png_bytes = render_observation_png(observation, arena_size=config.arena_size)
        sha256_hex = hashlib.sha256(png_bytes).hexdigest()
        match_dir = config.render_output_dir / observation.match_id
        match_dir.mkdir(parents=True, exist_ok=True)
        output_path = match_dir / f"tick_{observation.tick:04d}_{observation.mech_id}.png"
        output_path.write_bytes(png_bytes)
        return ModelSOLlmImageAttachment(png_bytes=png_bytes, sha256_hex=sha256_hex)

    def _serialize_observation_with_memory(self, observation: ModelSOPilotObservation) -> str:
        """Serialize the current observation with the pilot's remembered HP trend."""
        base = _serialize_observation(observation, persona_id=self._persona.persona_id)
        previous_hp = self._last_hp_percent_by_mech.get(observation.mech_id)
        if previous_hp is None:
            hp_delta = 0.0
            loss_streak = 0
            previous_text = "unknown"
        else:
            hp_delta = observation.hp_percent - previous_hp
            previous_text = f"{previous_hp:.1f}%"
            previous_streak = self._hp_loss_streak_by_mech.get(observation.mech_id, 0)
            loss_streak = previous_streak + 1 if hp_delta < -0.01 else 0

        self._last_hp_percent_by_mech[observation.mech_id] = observation.hp_percent
        self._hp_loss_streak_by_mech[observation.mech_id] = loss_streak

        memory = [
            "--- COMBAT MEMORY (your own remembered state) ---",
            f"previous_hp_percent: {previous_text}",
            f"hp_delta_since_last_decision: {hp_delta:.1f}",
            f"consecutive_hp_loss_ticks: {loss_streak}",
            "attrition_guidance: if you are taking repeated damage and not clearly",
            "winning the exchange, prefer defensive movement, cover, venting, or",
            "range control over standing still to trade shots. Enemy HP is not",
            "authoritative unless a sensor reports it; do not assume a favorable",
            "trade just because your weapon is ready.",
        ]
        return base + "\n" + "\n".join(memory)

    def _parse_response(
        self, response: LlmResponse, observation: ModelSOPilotObservation
    ) -> ModelSOPilotDecision:
        """Parse the LLM's JSON text → validated decision, or REMAIN fallback."""
        try:
            parsed = _ModelSOLlmPilotResponse.model_validate_json(response.text)
        except (ValidationError, ValueError, TypeError):
            raise LlmSemanticError("malformed_json") from None

        action_str = parsed.action.strip().lower()
        action = _LLM_ACTION_VOCAB.get(action_str)
        if action is None:
            raise LlmSemanticError("unknown_action")

        # Validate against availability (e.g. can't fire a weapon on cooldown).
        allowed = available_actions(observation)
        if action not in allowed:
            raise LlmSemanticError("action_unavailable")

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
            raise LlmSemanticError("invalid_action_parameters") from None

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


__all__ = ["LLMPilot", "LlmPilotFailurePolicy"]
