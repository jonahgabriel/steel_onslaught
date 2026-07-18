"""Closed payload authorities for current Slice-1 consumed events."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.arena import ModelSOCurrentLiveArenaSnapshot
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeProvenance
from steel_onslaught.contracts.mode import (
    ModeId,
    ModelSOModeSwitchIntentPayload,
    ModelSOModeTransitionStartedPayload,
)
from steel_onslaught.contracts.player_selection import (
    DecisionSource,
    ModelSOMatchLaunchProvenance,
)
from steel_onslaught.contracts.runtime import (
    ModelSORuntimeStatusPayload,
)
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
)
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.immutable import FrozenJSONMapping, FrozenMapping, thaw_json_mapping
from steel_onslaught.llm.schemas import LlmSemanticFailureCode
from steel_onslaught.match.state import ModelSOMechRuntimeState, SOMatchEndReason
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPosition,
    SOMoveDirection,
    SOPilotAction,
    SOPilotReasonCode,
)


class _ClosedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSOEmptyPayload(_ClosedPayload):
    """Canonical empty payload used by MATCH_TICK."""


class ModelSORuntimeStatusChangedPayload(ModelSORuntimeStatusPayload):
    """Event-payload alias for the strict runtime status projection."""


class ModelSOCurrentLiveMechSnapshot(ModelSOMechRuntimeState):
    """Strict live MATCH_STARTED snapshot; reducer defaults are not wire defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.mech_runtime_state"] = Field(...)
    side: Literal["red", "blue", "neutral"] = Field(...)
    sensor_ids: tuple[str, ...] = Field(...)
    gizmo_ids: tuple[str, ...] = Field(...)
    alive: bool = Field(...)
    pilot_alive: bool = Field(...)
    mode_lock_until: int = Field(ge=0)
    transition_ticks_remaining: int = Field(ge=0)
    transition_to_mode: ModeId | None = Field(...)
    sensor_dropout_ticks_remaining: int = Field(ge=0)
    mode_switch_disabled_until: int = Field(ge=0)
    weapon_cooldowns: FrozenMapping[int] = Field(...)
    evasion: float = Field(ge=0.0, le=1.0)
    accuracy_penalty_next_fire: float = Field(ge=0.0, le=1.0)
    jamming_intensity: float = Field(ge=0.0, le=1.0)
    under_sensor_lock: bool = Field(...)
    redline_consecutive_ticks: int = Field(ge=0)
    overloaded: bool = Field(...)
    overloaded_consecutive_ticks: int = Field(ge=0)


class ModelSOMatchStartedPayload(_ClosedPayload):
    seed: StrictInt = Field(ge=0)
    max_ticks: StrictInt | None = Field(..., gt=0)
    mechs: tuple[ModelSOCurrentLiveMechSnapshot, ...] = Field(min_length=1)
    arena: ModelSOCurrentLiveArenaSnapshot = Field(...)
    launch_provenance: ModelSOMatchLaunchProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    card_runtime_provenance: ModelSOCardRuntimeProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("launch_provenance", mode="before")
    @classmethod
    def _normalize_frozen_launch_provenance(cls, value: object) -> object:
        if isinstance(value, Mapping):
            normalized = thaw_json_mapping(value)
            command_id = normalized.get("launch_command_id")
            if isinstance(command_id, str):
                normalized["launch_command_id"] = UUID(command_id)
            assignments = normalized.get("seat_assignments")
            if isinstance(assignments, list):
                normalized["seat_assignments"] = tuple(assignments)
            return normalized
        return value

    @field_validator("card_runtime_provenance", mode="before")
    @classmethod
    def _normalize_frozen_card_runtime_provenance(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return thaw_json_mapping(value)
        return value

    @field_validator("mechs", mode="before")
    @classmethod
    def _normalize_frozen_envelope_mechs(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        normalized: list[object] = []
        required_fields = frozenset(ModelSOCurrentLiveMechSnapshot.model_fields)
        for index, mech in enumerate(value):
            if isinstance(mech, ModelSOCurrentLiveMechSnapshot):
                normalized.append(mech)
                continue
            if isinstance(mech, ModelSOMechRuntimeState):
                missing = sorted(required_fields - mech.model_fields_set)
                if missing:
                    raise ValueError(
                        f"mechs[{index}] is missing required current-live fields: {missing}"
                    )
                mech = mech.model_dump(mode="python")
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
    def _validate_current_roster_against_arena(self) -> ModelSOMatchStartedPayload:
        ids = [mech.mech_id for mech in self.mechs]
        duplicates = sorted({mech_id for mech_id in ids if ids.count(mech_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate mech_ids in match_started payload: {duplicates}")
        if len(self.mechs) != 2:
            raise ValueError(
                "current-live match_started requires exactly two mechs in canonical roster order"
            )
        expected_spawns = (self.arena.spawn_a, self.arena.spawn_b)
        obstacles = self.arena.obstacle_cells
        for index, (mech, expected_spawn) in enumerate(
            zip(self.mechs, expected_spawns, strict=True)
        ):
            position = mech.position
            cell = (position.x, position.y)
            if not (0 <= position.x < self.arena.size and 0 <= position.y < self.arena.size):
                raise ValueError(
                    f"mechs[{index}].position {cell} is outside arena {self.arena.arena_id!r}"
                )
            if cell in obstacles:
                raise ValueError(f"mechs[{index}].position {cell} occupies an arena obstacle")
            if position != expected_spawn:
                spawn_name = "spawn_a" if index == 0 else "spawn_b"
                raise ValueError(
                    f"mechs[{index}].position {cell} must equal arena.{spawn_name} "
                    "in canonical roster order"
                )
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
    decision_source: DecisionSource | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("decision_source", mode="before")
    @classmethod
    def _normalize_frozen_decision_source(cls, value: object) -> object:
        if isinstance(value, Mapping):
            normalized = thaw_json_mapping(value)
            command_id = normalized.get("command_id")
            if isinstance(command_id, str):
                normalized["command_id"] = UUID(command_id)
            return normalized
        return value

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
    cost_usd: StrictFloat | None = Field(ge=0.0, allow_inf_nan=False)


class ModelSOLlmCompletionFailedPayload(_ClosedPayload):
    provider_id: str
    reason_code: Literal[
        "provider_error",
        "invalid_response",
        "consumer_error",
        "abandoned",
    ]
    semantic_failure_code: LlmSemanticFailureCode | None
    model: str | None
    finish_reason: StrictStr | None = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    prompt_tokens: StrictInt | None = Field(ge=0)
    completion_tokens: StrictInt | None = Field(ge=0)
    cost_usd: StrictFloat | None = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _semantic_failure_matches_reason(self) -> ModelSOLlmCompletionFailedPayload:
        if self.reason_code == "invalid_response":
            if self.semantic_failure_code is None:
                raise ValueError(
                    "semantic_failure_code is required when reason_code is invalid_response"
                )
        elif self.semantic_failure_code is not None:
            raise ValueError(
                "semantic_failure_code is forbidden unless reason_code is invalid_response"
            )
        return self


class ModelSOMoveIntentPayload(_ClosedPayload):
    direction: SOMoveDirection
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
        SOEventType.RUNTIME_STATUS_CHANGED: ModelSORuntimeStatusChangedPayload,
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
        SOEventType.HAND_DEALT: ModelSOHandDealtPayload,
        SOEventType.PLAN_COMMITTED: ModelSOPlanCommittedPayload,
        SOEventType.REGISTER_RESOLVED: ModelSORegisterResolvedPayload,
        SOEventType.CARDS_DISCARDED: ModelSOCardsDiscardedPayload,
    }
)


__all__ = [
    "CURRENT_CONSUMED_PAYLOAD_MODELS",
    "ModelSOArmorAbsorbedPayload",
    "ModelSOBoilerOverloadedPayload",
    "ModelSOBoilerRupturedPayload",
    "ModelSOBoilerUpdatedPayload",
    "ModelSOCardsDiscardedPayload",
    "ModelSOCurrentLiveMechSnapshot",
    "ModelSODamageAppliedPayload",
    "ModelSOEmptyPayload",
    "ModelSOHandDealtPayload",
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
    "ModelSOPlanCommittedPayload",
    "ModelSOPlayerScore",
    "ModelSORegisterResolvedPayload",
    "ModelSORuntimeStatusChangedPayload",
    "ModelSOScoredWinner",
    "ModelSOSensorObservationPayload",
    "ModelSOVictoryDeclaredPayload",
    "ModelSOWeaponFireIntentPayload",
    "ModelSOWeaponFiredPayload",
]
