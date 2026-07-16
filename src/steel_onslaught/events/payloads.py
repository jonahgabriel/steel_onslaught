"""Closed payload authorities for current Slice-1 consumed events."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_serializer,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.mode import (
    ModeId,
    ModelSOModeSwitchIntentPayload,
    ModelSOModeTransitionStartedPayload,
)
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.immutable import FrozenJSONMapping, thaw_json_mapping
from steel_onslaught.match.state import ModelSOMechRuntimeState, SOMatchEndReason
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPosition,
    SOPilotAction,
    SOPilotReasonCode,
)


class _ClosedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSOEmptyPayload(_ClosedPayload):
    """Canonical empty payload used by MATCH_TICK."""


class ModelSOMatchStartedPayload(_ClosedPayload):
    seed: StrictInt = Field(ge=0)
    max_ticks: StrictInt = Field(gt=0)
    mechs: tuple[ModelSOMechRuntimeState, ...] = Field(min_length=1)

    @field_validator("mechs", mode="before")
    @classmethod
    def _normalize_frozen_envelope_mechs(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        normalized: list[object] = []
        for mech in value:
            if not isinstance(mech, Mapping):
                normalized.append(mech)
                continue
            mutable = thaw_json_mapping(mech)
            for tuple_field in ("sensor_ids", "gizmo_ids"):
                if isinstance(mutable.get(tuple_field), list):
                    mutable[tuple_field] = tuple(mutable[tuple_field])
            normalized.append(mutable)
        return normalized

    @model_validator(mode="after")
    def _mech_ids_unique(self) -> ModelSOMatchStartedPayload:
        ids = [mech.mech_id for mech in self.mechs]
        duplicates = sorted({mech_id for mech_id in ids if ids.count(mech_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate mech_ids in match_started payload: {duplicates}")
        return self


class ModelSOMechSpawnedPayload(_ClosedPayload):
    position: ModelSOPosition
    facing: StrictInt = Field(ge=0)


class ModelSOMovementResolvedPayload(_ClosedPayload):
    from_pos: ModelSOPosition = Field(alias="from")
    to_pos: ModelSOPosition = Field(alias="to")
    ticks_consumed: StrictInt = Field(gt=0)
    pressure_consumed: StrictInt = Field(ge=0)

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class ModelSOWeaponFiredPayload(_ClosedPayload):
    weapon_id: str
    target_id: str
    hit_probability: StrictFloat = Field(ge=0.0, le=1.0)
    pressure_cost: StrictInt = Field(ge=0)
    heat_generated: StrictInt = Field(ge=0)


class ModelSOHitResult(_ClosedPayload):
    hit: StrictBool
    damage_after_armor: StrictInt = Field(ge=0)


class ModelSOHitResolvedPayload(_ClosedPayload):
    attacker_id: str
    defender_id: str
    result: ModelSOHitResult


class ModelSOArmorAbsorbedPayload(_ClosedPayload):
    target_id: str
    absorbed_amount: StrictInt = Field(ge=0)
    armor_after: StrictInt = Field(ge=0)


class ModelSODamageAppliedPayload(_ClosedPayload):
    target_id: str
    damage: StrictInt = Field(ge=0)
    cause: str
    hp_after: StrictInt = Field(ge=0)
    source_mech_id: str | None = None
    radius_cells: StrictInt | None = Field(default=None, ge=0)


class ModelSOBoilerUpdatedPayload(_ClosedPayload):
    pressure_before: StrictInt = Field(ge=0)
    pressure_after: StrictInt = Field(ge=0)
    heat_before: StrictInt = Field(ge=0)
    heat_after: StrictInt = Field(ge=0)


class ModelSOHeatRedlinePayload(_ClosedPayload):
    heat: StrictInt = Field(ge=0)
    redline_threshold: StrictInt = Field(gt=0)


class ModelSOBoilerOverloadedPayload(_ClosedPayload):
    heat: StrictInt = Field(ge=0)
    redline_threshold: StrictInt = Field(gt=0)
    redline_consecutive_ticks: StrictInt = Field(gt=0)
    accuracy_penalty_next_fire: StrictFloat = Field(ge=0.0, le=1.0)
    mode_switch_disabled_until: StrictInt = Field(ge=0)


class ModelSOBoilerRupturedPayload(_ClosedPayload):
    cause: str
    heat: StrictInt = Field(ge=0)
    rupture_threshold: StrictInt = Field(gt=0)
    direct_damage: StrictInt = Field(ge=0)
    area_damage: StrictInt = Field(ge=0)
    area_radius_cells: StrictInt = Field(ge=0)


class ModelSOSensorObservationPayload(_ClosedPayload):
    enemy_mech_id: str
    distance_estimate: StrictFloat = Field(ge=0.0)
    confidence: StrictFloat = Field(ge=0.0, le=1.0)
    heat_estimate: StrictFloat | None = Field(default=None, ge=0.0)
    mode_estimate: ModeId | None = None


class ModelSOPilotDecisionPayload(_ClosedPayload):
    action: SOPilotAction
    action_params: FrozenJSONMapping
    reason_code: SOPilotReasonCode
    confidence: StrictFloat
    considered_actions: tuple[ModelSOConsideredAction, ...]
    rationale: str | None

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return min(1.0, max(0.0, value))

    @model_validator(mode="after")
    def _chosen_action_is_considered(self) -> ModelSOPilotDecisionPayload:
        if self.action not in {candidate.action for candidate in self.considered_actions}:
            raise ValueError("considered_actions must include the chosen action")
        return self


class ModelSOLlmCompletionRequestedPayload(_ClosedPayload):
    provider_id: str
    persona_id: str
    system_prompt_length: StrictInt = Field(ge=0)
    user_prompt_length: StrictInt = Field(ge=0)


class ModelSOLlmCompletionResolvedPayload(_ClosedPayload):
    provider_id: str
    model: str
    finish_reason: str
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    response_length: StrictInt = Field(ge=0)


class ModelSOLlmCompletionFailedPayload(_ClosedPayload):
    provider_id: str
    reason_code: Literal[
        "provider_error",
        "invalid_response",
        "consumer_error",
        "abandoned",
    ]
    model: str | None
    prompt_tokens: StrictInt | None = Field(ge=0)
    completion_tokens: StrictInt | None = Field(ge=0)
    cost_usd: StrictFloat | None = Field(ge=0.0, allow_inf_nan=False)


class ModelSOMoveIntentPayload(_ClosedPayload):
    direction: Literal["toward_enemy", "defensive"]
    speed: Literal["full"] | None = None


class ModelSOWeaponFireIntentPayload(_ClosedPayload):
    weapon_id: str
    target_mech_id: str | None = None


class ModelSOPilotKilledPayload(_ClosedPayload):
    mech_id: str
    survival_probability: StrictFloat = Field(ge=0.0, le=1.0)
    roll: StrictFloat = Field(ge=0.0, lt=1.0)
    safety_gizmos_equipped: StrictInt = Field(ge=0)


class ModelSOMechDestroyedPayload(_ClosedPayload):
    cause: str
    source_mech_id: str | None = None


class ModelSOVictoryDeclaredPayload(_ClosedPayload):
    winner_player_id: str
    reason: SOMatchEndReason


class ModelSOMatchEndedPayload(_ClosedPayload):
    reason: SOMatchEndReason
    winner_id: str | None = None


class ModelSOPlayerScore(_ClosedPayload):
    victory: StrictInt = Field(ge=0, le=1)
    damage_dealt: StrictInt = Field(ge=0)
    damage_efficiency: StrictFloat = Field(ge=0.0)
    pressure_efficiency: StrictFloat = Field(ge=0.0, le=1.0)
    overload_penalty: StrictInt = Field(ge=0)
    replay_validity: StrictInt = Field(ge=0, le=1)
    final_score: StrictInt = Field(ge=0)


class ModelSOScoredWinner(_ClosedPayload):
    player_id: str
    mech_id: str


class ModelSOMatchScoredPayload(_ClosedPayload):
    kind: Literal["steel_onslaught.match_scored"] = "steel_onslaught.match_scored"
    match_id: str
    winner: ModelSOScoredWinner | None
    scores: Mapping[str, ModelSOPlayerScore]
    winner_player_id: str
    winner_loadout_id: str
    winner_score: StrictInt = Field(ge=0)
    loser_player_id: str
    loser_score: StrictInt = Field(ge=0)
    duration_ticks: StrictInt = Field(gt=0)
    scored_at: str
    is_draw: StrictBool

    @model_validator(mode="after")
    def _score_truth_is_consistent(self) -> ModelSOMatchScoredPayload:
        if self.winner_player_id == self.loser_player_id:
            raise ValueError("winner_player_id and loser_player_id must be distinct")
        expected_players = {self.winner_player_id, self.loser_player_id}
        if set(self.scores) != expected_players or len(self.scores) != 2:
            raise ValueError("scores must contain exactly winner_player_id and loser_player_id")
        winner_score = self.scores[self.winner_player_id]
        loser_score = self.scores[self.loser_player_id]
        if self.winner_score != winner_score.final_score:
            raise ValueError("winner_score must equal the winner's nested final_score")
        if self.loser_score != loser_score.final_score:
            raise ValueError("loser_score must equal the loser's nested final_score")
        if self.is_draw:
            if self.winner is not None:
                raise ValueError("draw scores require winner=null")
            if any(score.victory != 0 for score in self.scores.values()):
                raise ValueError("draw scores require zero victory points for every player")
        else:
            if self.winner is None:
                raise ValueError("decisive scores require a winner block")
            if self.winner.player_id != self.winner_player_id:
                raise ValueError("winner block player_id must equal winner_player_id")
            if winner_score.victory != 1 or loser_score.victory != 0:
                raise ValueError("decisive scores require winner victory=1 and loser victory=0")
        return self

    @field_validator("scores", mode="after")
    @classmethod
    def _freeze_scores(
        cls, scores: Mapping[str, ModelSOPlayerScore]
    ) -> Mapping[str, ModelSOPlayerScore]:
        return MappingProxyType(dict(scores))

    @field_serializer("scores")
    def _serialize_scores(
        self, scores: Mapping[str, ModelSOPlayerScore]
    ) -> dict[str, dict[str, object]]:
        return {player_id: score.model_dump(mode="json") for player_id, score in scores.items()}


CURRENT_CONSUMED_PAYLOAD_MODELS: Mapping[SOEventType, type[BaseModel]] = MappingProxyType(
    {
        SOEventType.MATCH_STARTED: ModelSOMatchStartedPayload,
        SOEventType.MATCH_TICK: ModelSOEmptyPayload,
        SOEventType.MOVE_INTENT: ModelSOMoveIntentPayload,
        SOEventType.WEAPON_FIRE_INTENT: ModelSOWeaponFireIntentPayload,
        SOEventType.MODE_SWITCH_INTENT: ModelSOModeSwitchIntentPayload,
        SOEventType.VENT_INTENT: ModelSOEmptyPayload,
        SOEventType.MECH_SPAWNED: ModelSOMechSpawnedPayload,
        SOEventType.MOVEMENT_RESOLVED: ModelSOMovementResolvedPayload,
        SOEventType.SENSOR_OBSERVATION: ModelSOSensorObservationPayload,
        SOEventType.PILOT_DECISION_MADE: ModelSOPilotDecisionPayload,
        SOEventType.LLM_COMPLETION_REQUESTED: ModelSOLlmCompletionRequestedPayload,
        SOEventType.LLM_COMPLETION_RESOLVED: ModelSOLlmCompletionResolvedPayload,
        SOEventType.LLM_COMPLETION_FAILED: ModelSOLlmCompletionFailedPayload,
        SOEventType.BOILER_UPDATED: ModelSOBoilerUpdatedPayload,
        SOEventType.HEAT_REDLINE_ENTERED: ModelSOHeatRedlinePayload,
        SOEventType.HEAT_REDLINE_EXITED: ModelSOHeatRedlinePayload,
        SOEventType.BOILER_OVERLOADED: ModelSOBoilerOverloadedPayload,
        SOEventType.BOILER_RUPTURED: ModelSOBoilerRupturedPayload,
        SOEventType.MODE_TRANSITION_STARTED: ModelSOModeTransitionStartedPayload,
        SOEventType.WEAPON_FIRED: ModelSOWeaponFiredPayload,
        SOEventType.HIT_RESOLVED: ModelSOHitResolvedPayload,
        SOEventType.ARMOR_ABSORBED: ModelSOArmorAbsorbedPayload,
        SOEventType.DAMAGE_APPLIED: ModelSODamageAppliedPayload,
        SOEventType.PILOT_KILLED: ModelSOPilotKilledPayload,
        SOEventType.MECH_DESTROYED: ModelSOMechDestroyedPayload,
        SOEventType.VICTORY_DECLARED: ModelSOVictoryDeclaredPayload,
        SOEventType.MATCH_ENDED: ModelSOMatchEndedPayload,
        SOEventType.MATCH_SCORED: ModelSOMatchScoredPayload,
    }
)


__all__ = [
    "CURRENT_CONSUMED_PAYLOAD_MODELS",
    "ModelSOArmorAbsorbedPayload",
    "ModelSOBoilerOverloadedPayload",
    "ModelSOBoilerRupturedPayload",
    "ModelSOBoilerUpdatedPayload",
    "ModelSODamageAppliedPayload",
    "ModelSOEmptyPayload",
    "ModelSOHeatRedlinePayload",
    "ModelSOHitResolvedPayload",
    "ModelSOHitResult",
    "ModelSOLlmCompletionRequestedPayload",
    "ModelSOLlmCompletionResolvedPayload",
    "ModelSOMatchEndedPayload",
    "ModelSOMatchScoredPayload",
    "ModelSOMatchStartedPayload",
    "ModelSOMechDestroyedPayload",
    "ModelSOMechSpawnedPayload",
    "ModelSOModeTransitionStartedPayload",
    "ModelSOMoveIntentPayload",
    "ModelSOMovementResolvedPayload",
    "ModelSOPilotDecisionPayload",
    "ModelSOPilotKilledPayload",
    "ModelSOPlayerScore",
    "ModelSOScoredWinner",
    "ModelSOSensorObservationPayload",
    "ModelSOVictoryDeclaredPayload",
    "ModelSOWeaponFireIntentPayload",
    "ModelSOWeaponFiredPayload",
]
