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

from steel_onslaught.contracts.arena import (
    ModelSOCurrentLiveArenaSnapshot,
    arena_contract_hash,
)
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeProvenance
from steel_onslaught.contracts.live_learning import ModelSOSeatPolicyProvenance
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
from steel_onslaught.pilots.persona_prompts import ModelSOMatchPromptProvenance
from steel_onslaught.pilots.programming import ModelSOCardRulePackProvenance
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPosition,
    SOMoveDirection,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.reducers.defense_handlers import ModelSODefenseHandlerPackProvenance

WeaponFireRejectionReason = Literal[
    "insufficient_pressure",
    "weapon_on_cooldown",
    "target_out_of_range",
    "target_not_alive",
    "target_not_found",
]

SOVictoryKind = Literal["elimination", "vp_threshold", "tick_cap_failsafe"]
"""HOW a victory terminal happened (Phase 4).

``reason`` alone is ambiguous: ``last_mech_standing`` is emitted both by a
real elimination and by the explicit tick-cap bound with a lone survivor.
``victory_kind`` disambiguates so the evidence projector (and O-GATE) can
classify terminals — a clock ending is an anomaly to report, never a normal
outcome.  Optional on the wire because pre-Phase-4 ledgers do not carry it;
every NEW emission sets it.
"""


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
    card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    # The effective, possibly operator-edited persona prompts this match flew
    # with.  Recorded for the same reason as persona_id and model identity:
    # without it a replay of an edited prompt silently diverges.
    prompt_provenance: ModelSOMatchPromptProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    # Per-seat policy provenance (L-GATE-2): which live-learning policy each
    # learning seat flew with.  Binds a match's decisions to the exact policy
    # generation that shaped them; the adaptation battery and the promotion
    # audit chain (POLICY_PROMOTED -> lineage -> replay) both anchor here.
    policy_provenance: tuple[ModelSOSeatPolicyProvenance, ...] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    # Canonical digest of the embedded arena/objective contract (Phase 4
    # finish-line seam).  Self-verifying: when present it MUST equal the hash
    # recomputed from ``arena`` — a mismatch is a provenance forgery, not a
    # tolerable drift.  Optional only because pre-Phase-4 ledgers lack it;
    # the runner stamps it on every new match.
    arena_contract_hash: StrictStr | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        exclude_if=lambda value: value is None,
    )
    # Content-addressed identity of the active defense-resolution (armor)
    # handler pack (defense seam refactor). Optional only because ledgers
    # recorded before this seam existed lack it; the runner stamps it on
    # every new match unconditionally — unlike the opt-in packs above, this
    # seam is never off, so a new match is never missing this field.
    defense_handler_pack_provenance: ModelSODefenseHandlerPackProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def _arena_contract_hash_matches_arena(self) -> ModelSOMatchStartedPayload:
        if self.arena_contract_hash is not None:
            expected = arena_contract_hash(self.arena)
            if self.arena_contract_hash != expected:
                raise ValueError(
                    "arena_contract_hash does not match the embedded arena snapshot "
                    f"(claimed {self.arena_contract_hash!r}, computed {expected!r})"
                )
        return self

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

    @field_validator("card_rule_pack_provenance", mode="before")
    @classmethod
    def _normalize_card_rule_pack_provenance(cls, value: object) -> object:
        if isinstance(value, Mapping):
            normalized = thaw_json_mapping(value)
            handlers = normalized.get("handlers")
            if isinstance(handlers, list):
                normalized["handlers"] = tuple(handlers)
            return normalized
        return value

    @field_validator("defense_handler_pack_provenance", mode="before")
    @classmethod
    def _normalize_defense_handler_pack_provenance(cls, value: object) -> object:
        if isinstance(value, Mapping):
            normalized = thaw_json_mapping(value)
            handlers = normalized.get("handlers")
            if isinstance(handlers, list):
                normalized["handlers"] = tuple(handlers)
            return normalized
        return value

    @field_validator("prompt_provenance", mode="before")
    @classmethod
    def _normalize_prompt_provenance(cls, value: object) -> object:
        if isinstance(value, Mapping):
            normalized = thaw_json_mapping(value)
            prompts = normalized.get("prompts")
            if isinstance(prompts, list):
                normalized["prompts"] = tuple(prompts)
            return normalized
        return value

    @field_validator("policy_provenance", mode="before")
    @classmethod
    def _normalize_frozen_policy_provenance(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(
                thaw_json_mapping(entry) if isinstance(entry, Mapping) else entry for entry in value
            )
        return value

    @field_validator("policy_provenance", mode="after")
    @classmethod
    def _policy_provenance_seats_are_distinct(
        cls, value: tuple[ModelSOSeatPolicyProvenance, ...] | None
    ) -> tuple[ModelSOSeatPolicyProvenance, ...] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("policy_provenance must not be an empty tuple; omit it instead")
        player_ids = [entry.player_id for entry in value]
        duplicates = sorted({pid for pid in player_ids if player_ids.count(pid) > 1})
        if duplicates:
            raise ValueError(f"duplicate policy_provenance player_ids: {duplicates}")
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
    # Present only on the V-IMG arm of the vision-representation experiment
    # (2026-07-24). ``None`` for every text-only completion, so pre-existing
    # ledger evidence stays additive/backward-compatible. The sha256 is the
    # durable, joinable evidence trail: event -> sha256 -> PNG persisted
    # under the state root (see ``LLMPilot.decide``).
    image_sha256: StrictStr | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        exclude_if=lambda value: value is None,
    )
    image_byte_length: StrictInt | None = Field(
        default=None,
        ge=0,
        exclude_if=lambda value: value is None,
    )


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
        "length",
        "timeout",
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
    # Forensic fields (2026-07-24).  The R2 spatial battery aborted 6/30
    # matches; three were ``finish_reason=length`` truncations (diagnosable
    # from the token counts already above) but the other three exhausted the
    # plan-attempt budget on ``malformed_json`` and were NOT diagnosable at
    # all from the ledger — the failure event recorded the code but discarded
    # both the validator's rejection message and any measure of the offending
    # response.  Without those, "why did the repair prompt fail three times in
    # a row" is unanswerable after the fact and the arm cannot be root-caused
    # without re-running it.
    #
    # ``semantic_failure_detail`` carries the SAME bounded string already fed
    # to the repair prompt (``programming._error_detail``): it originates from
    # our own closed response model or the canonical plan validator, never
    # from raw provider text, so persisting it introduces no provider-text
    # leakage that the repair prompt did not already contain.
    #
    # Both default to ``None`` so every event persisted before these fields
    # existed stays valid on replay, and absence is never read as evidence.
    # ``exclude_if`` matches the established pattern for optional forensic
    # fields on this same event family (see ``image_sha256``/
    # ``image_byte_length`` on ``ModelSOLlmCompletionRequestedPayload`` above):
    # a ``None`` value is omitted from the serialized payload entirely rather
    # than persisted as an explicit null, so events emitted before these
    # fields existed round-trip byte-identically.
    semantic_failure_detail: StrictStr | None = Field(
        default=None,
        max_length=512,
        exclude_if=lambda value: value is None,
    )
    response_length: StrictInt | None = Field(
        default=None,
        ge=0,
        exclude_if=lambda value: value is None,
    )

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
        if self.semantic_failure_detail is not None and self.semantic_failure_code is None:
            raise ValueError("semantic_failure_detail is forbidden without a semantic_failure_code")
        return self


class ModelSOMoveIntentPayload(_ClosedPayload):
    direction: SOMoveDirection
    speed: Literal["full"] | None = None


class ModelSOWeaponFireIntentPayload(_ClosedPayload):
    weapon_id: str
    target_mech_id: str | None = None


class ModelSOWeaponFireRejectedPayload(_ClosedPayload):
    """A typed, non-state-changing record of a rejected fire intent.

    The runner keeps validation in :func:`validate_weapon_fire_intent`; this
    payload makes that validation outcome observable without teaching the
    canonical fold about live-only rejection handling.
    """

    weapon_id: StrictStr
    target_id: StrictStr | None = None
    reason: WeaponFireRejectionReason


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
    victory_kind: SOVictoryKind | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def _victory_kind_consistent_with_reason(self) -> ModelSOVictoryDeclaredPayload:
        """``vp_threshold`` is one fact stated twice — the statements must agree."""

        reason_is_vp = self.reason is SOMatchEndReason.VP_THRESHOLD
        kind_is_vp = self.victory_kind == "vp_threshold"
        if self.victory_kind is not None and reason_is_vp != kind_is_vp:
            raise ValueError(
                f"victory_kind {self.victory_kind!r} conflicts with reason {self.reason.value!r}"
            )
        if reason_is_vp and self.victory_kind is None:
            raise ValueError("a vp_threshold victory must carry victory_kind='vp_threshold'")
        return self


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


class ModelSOObjectiveScoredPayload(_ClosedPayload):
    """One controlled-round VP award for one objective (Phase 4).

    Emitted by the canonical fold during MATCH_TICK when exactly one player
    holds the objective (sole living mech presence within the control radius).
    VP state folds from MATCH_TICK itself — this event is the durable,
    projection-facing record of the award, a fold no-op on replay (the
    BOILER_UPDATED discipline).  ``round_index`` is the scoring round, which
    is the MATCH_TICK tick: one control evaluation per tick, matching the
    atomic card cadence where one tick hosts one full card round.
    """

    kind: Literal["steel_onslaught.objective_scored"] = "steel_onslaught.objective_scored"
    objective_id: StrictStr = Field(pattern=r"^objective\.[a-z][a-z0-9_]*$")
    controlling_player_id: StrictStr = Field(min_length=1)
    vp_awarded: StrictInt = Field(ge=1)
    cumulative_vp: Mapping[str, StrictInt]
    round_index: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def _award_truth_is_consistent(self) -> ModelSOObjectiveScoredPayload:
        if self.controlling_player_id not in self.cumulative_vp:
            raise ValueError("cumulative_vp must include the controlling player")
        negative = {player: vp for player, vp in self.cumulative_vp.items() if vp < 0}
        if negative:
            raise ValueError(f"cumulative_vp must be >= 0; got {negative}")
        if self.cumulative_vp[self.controlling_player_id] < self.vp_awarded:
            raise ValueError("the controlling player's cumulative_vp must include this award")
        return self

    @field_validator("cumulative_vp", mode="after")
    @classmethod
    def _freeze_cumulative_vp(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        return MappingProxyType(dict(value))

    @field_serializer("cumulative_vp")
    def _serialize_cumulative_vp(self, value: Mapping[str, int]) -> dict[str, int]:
        return {player: vp for player, vp in sorted(value.items())}


class ModelSOPolicyPromotedPayload(_ClosedPayload):
    """Durable promotion fact appended to the promoting match's stream.

    Deliberately hash-carrying, not parameter-carrying: raw parameters live in
    the promoted lineage record; this event carries the digests that make the
    chain verifiable.  Audit path: ``source_lineage_digest`` resolves the
    lineage record (parameters + evidence); ``evidence_scored_event_id``
    resolves the MATCH_SCORED event whose evidence was evaluated; replaying
    the promoting match reproduces the decision inputs.  Cross-match ordering
    authority is ``generation`` + the ``parent_spec_hash`` chain, never wall
    clock.
    """

    kind: Literal["steel_onslaught.policy_promoted"] = "steel_onslaught.policy_promoted"
    match_id: StrictStr = Field(min_length=1)
    policy_id: StrictStr = Field(min_length=1)
    archetype: StrictStr = Field(min_length=1)
    generation: StrictInt = Field(ge=1)
    spec_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    parent_spec_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    source_lineage_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_scored_event_id: StrictStr = Field(min_length=26, max_length=26)

    @model_validator(mode="after")
    def _chain_is_well_formed(self) -> ModelSOPolicyPromotedPayload:
        if self.spec_hash == self.parent_spec_hash:
            raise ValueError("a promotion must change the policy: spec_hash == parent_spec_hash")
        return self


SOUtilityKind = Literal["smoke", "chaff", "flares"]
"""Which counterplay effect a utility card deploys (Phase 2, design §3.2)."""


class ModelSOUtilityDeployIntentPayload(_ClosedPayload):
    """A resolved utility card's typed deploy intent (Phase 2, Stage A).

    Value-only: it carries WHAT to deploy (kind, area, duration) and which card
    authored it, but not WHERE — the origin is the deploying mech's live cell,
    stamped by the runner when it resolves this intent into ``UTILITY_DEPLOYED``.
    """

    card_id: StrictStr = Field(min_length=1)
    utility_kind: SOUtilityKind
    radius: StrictInt = Field(ge=0)
    duration_ticks: StrictInt = Field(ge=1)


class ModelSOUtilityDeployedPayload(_ClosedPayload):
    """One deployed battlefield-effect record (Phase 2, design §6 line 234).

    Emitted by the runner when a utility card resolves; folded into
    ``active_utility_effects`` with per-tick expiry.  ``origin`` is the
    deploying mech's cell; ``radius`` its area; ``duration_ticks`` how long the
    effect persists.  A fold-affecting, projection-facing record — the first
    card whose resolution changes the battlefield.
    """

    kind: Literal["steel_onslaught.utility_deployed"] = "steel_onslaught.utility_deployed"
    card_id: StrictStr = Field(min_length=1)
    utility_kind: SOUtilityKind
    origin: ModelSOPosition
    radius: StrictInt = Field(ge=0)
    duration_ticks: StrictInt = Field(ge=1)


CURRENT_CONSUMED_PAYLOAD_MODELS: Mapping[SOEventType, type[BaseModel]] = MappingProxyType(
    {
        SOEventType.MATCH_STARTED: ModelSOMatchStartedPayload,
        SOEventType.RUNTIME_STATUS_CHANGED: ModelSORuntimeStatusChangedPayload,
        SOEventType.MATCH_TICK: ModelSOEmptyPayload,
        SOEventType.MOVE_INTENT: ModelSOMoveIntentPayload,
        SOEventType.WEAPON_FIRE_INTENT: ModelSOWeaponFireIntentPayload,
        SOEventType.MODE_SWITCH_INTENT: ModelSOModeSwitchIntentPayload,
        SOEventType.VENT_INTENT: ModelSOEmptyPayload,
        SOEventType.UTILITY_DEPLOY_INTENT: ModelSOUtilityDeployIntentPayload,
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
        SOEventType.WEAPON_FIRE_REJECTED: ModelSOWeaponFireRejectedPayload,
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
        SOEventType.POLICY_PROMOTED: ModelSOPolicyPromotedPayload,
        SOEventType.OBJECTIVE_SCORED: ModelSOObjectiveScoredPayload,
        SOEventType.UTILITY_DEPLOYED: ModelSOUtilityDeployedPayload,
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
    "ModelSOObjectiveScoredPayload",
    "ModelSOPilotDecisionPayload",
    "ModelSOPilotKilledPayload",
    "ModelSOPlanCommittedPayload",
    "ModelSOPlayerScore",
    "ModelSOPolicyPromotedPayload",
    "ModelSORegisterResolvedPayload",
    "ModelSORuntimeStatusChangedPayload",
    "ModelSOScoredWinner",
    "ModelSOSensorObservationPayload",
    "ModelSOUtilityDeployIntentPayload",
    "ModelSOUtilityDeployedPayload",
    "ModelSOVictoryDeclaredPayload",
    "ModelSOWeaponFireIntentPayload",
    "ModelSOWeaponFireRejectedPayload",
    "ModelSOWeaponFiredPayload",
    "SOUtilityKind",
    "SOVictoryKind",
    "WeaponFireRejectionReason",
]
