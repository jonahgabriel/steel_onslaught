from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SOEventType(StrEnum):
    # Lifecycle
    MATCH_STARTED = "match_started"
    MATCH_TICK = "match_tick"
    MECH_SPAWNED = "mech_spawned"
    # Observation
    SENSOR_OBSERVATION = "sensor_observation"
    # Pilot decision (informational, emitted before intents)
    PILOT_DECISION_MADE = "pilot_decision_made"
    # Intents — produced by the pilot tick reducer; consumed by downstream
    #           reducers which validate and either accept or reject.
    MOVE_INTENT = "move_intent"
    WEAPON_FIRE_INTENT = "weapon_fire_intent"
    MODE_SWITCH_INTENT = "mode_switch_intent"
    VENT_INTENT = "vent_intent"
    # Resolved state changes (canonical truth)
    MOVEMENT_RESOLVED = "movement_resolved"
    BOILER_UPDATED = "boiler_updated"
    HEAT_REDLINE_ENTERED = "heat_redline_entered"
    HEAT_REDLINE_EXITED = "heat_redline_exited"
    BOILER_OVERLOADED = "boiler_overloaded"
    BOILER_RUPTURED = "boiler_ruptured"
    MODE_TRANSITION_STARTED = "mode_transition_started"
    MODE_TRANSITION_COMPLETED = "mode_transition_completed"
    WEAPON_FIRED = "weapon_fired"
    HIT_RESOLVED = "hit_resolved"
    ARMOR_ABSORBED = "armor_absorbed"
    DAMAGE_APPLIED = "damage_applied"
    PILOT_INJURED = "pilot_injured"
    PILOT_KILLED = "pilot_killed"
    MECH_DESTROYED = "mech_destroyed"
    # Termination
    VICTORY_DECLARED = "victory_declared"
    MATCH_ENDED = "match_ended"
    MATCH_SCORED = "match_scored"


class ModelSOEventSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mech_id: str
    player_id: str


class ModelSOEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "0.1.0"
    event_id: str = Field(min_length=26, max_length=26)  # ULID; uniqueness only
    match_id: str
    tick: int = Field(ge=0)  # primary ordering authority
    sequence_in_tick: int = Field(ge=0)  # secondary ordering authority
    correlation_id: str | None = None
    causation_id: str | None = None
    producer_node: str
    subject: ModelSOEventSubject
    event_type: SOEventType
    payload: dict[str, Any]
    emitted_at: str  # metadata only, not for ordering
