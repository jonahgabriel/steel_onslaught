"""Canonical match runtime state — Task 18.

``ModelSOMechRuntimeState`` is deliberately COMPREHENSIVE: the downstream
reducer tasks (19-26: movement, sensors, pilot tick, boiler, mode, weapons,
damage, failure cascade) run in parallel and are forbidden from editing this
file, so every field they read or replace must already exist here.

All models are frozen — reducers evolve state by constructing replacement
instances (full construction re-runs validators; prefer it over
``model_copy(update=...)`` when an invariant could be affected).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.immutable import FrozenMapping
from steel_onslaught.pilots.schemas import ModelSOPosition

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SOMatchStatus(StrEnum):
    """Lifecycle status of a match."""

    PENDING = "pending"
    RUNNING = "running"
    ENDED = "ended"


class SOMatchEndReason(StrEnum):
    """Why a match ended (recorded on the final state and MATCH_ENDED payload)."""

    LAST_MECH_STANDING = "last_mech_standing"
    PILOT_KILLED = "pilot_killed"
    DRAW_MAX_TICKS = "draw_max_ticks"
    ABORTED = "aborted"


# ---------------------------------------------------------------------------
# Mech runtime state
# ---------------------------------------------------------------------------


class ModelSOMechRuntimeState(BaseModel):
    """Runtime state of one fielded mech, owned by the reducer chain.

    Field consumers (Tasks 19-26):
      - movement (19): ``position``, ``facing``, ``base_speed``, ``speed``
      - sensors (20): ``sensor_ids``, ``jamming_intensity``,
        ``sensor_dropout_ticks_remaining``, ``under_sensor_lock``
      - pilot tick (21): ``alive``, ``pilot_alive``, ``hp``/``hp_max``,
        ``current_mode``, ``mode_lock_until``, ``weapon_cooldowns``
      - boiler (22): ``boiler``
      - mode (23): ``current_mode``, ``mode_lock_until``,
        ``transition_ticks_remaining``, ``transition_to_mode``,
        ``mode_switch_disabled_until``
      - weapons (24): ``weapon_cooldowns``, ``evasion``,
        ``accuracy_penalty_next_fire``, ``chassis_class``
      - damage (25): ``armor_value``, ``hp``, ``chassis_class``
      - failure cascade (26): ``redline_consecutive_ticks``, ``overloaded``,
        ``overloaded_consecutive_ticks``, ``gizmo_ids``, ``pilot_alive``
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.mech_runtime_state"] = "steel_onslaught.mech_runtime_state"

    # Identity — static after spawn, copied from the loadout/contract layer.
    mech_id: str
    player_id: str
    side: Literal["red", "blue", "neutral"] = "neutral"
    loadout_id: str
    pilot_id: str
    chassis_id: str
    chassis_class: Literal["light", "medium", "heavy"]
    sensor_ids: tuple[str, ...] = ()
    gizmo_ids: tuple[str, ...] = ()
    base_speed: int = Field(gt=0, description="Chassis base speed in cells/tick (pre-mode)")

    # Spatial.
    position: ModelSOPosition
    facing: int = Field(ge=0, lt=360, description="Facing in degrees, 0 <= deg < 360")
    speed: int = Field(ge=0, description="Current effective speed (base_speed + mode modifier)")

    # Health.
    hp: int = Field(ge=0)
    hp_max: int = Field(gt=0)
    armor_value: int = Field(
        ge=0, description="Current armor (degrades per hit, regenerates per tick)"
    )
    armor_max: int = Field(
        ge=0, description="Armor capacity ceiling; armor_value regenerates toward this"
    )
    alive: bool = True
    pilot_alive: bool = True

    # Mode + transition bookkeeping.
    current_mode: ModeId = Field(description="Closed current combat mode")
    mode_lock_until: int = Field(
        default=0, ge=0, description="Tick at which the post-switch mode lock expires"
    )
    transition_ticks_remaining: int = Field(
        default=0, ge=0, description="Ticks left in an in-flight mode transition (0 = none)"
    )
    transition_to_mode: ModeId | None = Field(
        default=None, description="Target mode of an in-flight transition (None = none)"
    )
    sensor_dropout_ticks_remaining: int = Field(
        default=0, ge=0, description="Ticks sensors stay dark after a transition starts"
    )
    mode_switch_disabled_until: int = Field(
        default=0, ge=0, description="Tick until which mode switching is disabled (overload)"
    )

    # Combat.
    weapon_cooldowns: FrozenMapping[int] = Field(
        default_factory=dict,
        validate_default=True,
        description="weapon_id -> cooldown ticks remaining (0 = ready)",
    )
    evasion: float = Field(default=0.0, ge=0.0, le=1.0)
    accuracy_penalty_next_fire: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Multiplicative accuracy penalty (overload)"
    )
    jamming_intensity: float = Field(default=0.0, ge=0.0, le=1.0)
    under_sensor_lock: bool = False

    # Boiler + failure cascade.
    boiler: ModelSOBoilerState
    redline_consecutive_ticks: int = Field(default=0, ge=0)
    overloaded: bool = False
    overloaded_consecutive_ticks: int = Field(default=0, ge=0)

    @field_validator("current_mode", "transition_to_mode", mode="before")
    @classmethod
    def _parse_mode_ids(cls, value: object) -> object:
        if value is None or isinstance(value, ModeId):
            return value
        if isinstance(value, str):
            return ModeId(value)
        return value

    @property
    def hp_percent(self) -> float:
        """Current hit points as a percentage of maximum (0..100)."""
        return 100.0 * self.hp / self.hp_max

    @model_validator(mode="after")
    def _hp_within_max(self) -> ModelSOMechRuntimeState:
        if self.hp > self.hp_max:
            raise ValueError(f"hp ({self.hp}) must not exceed hp_max ({self.hp_max})")
        return self

    @model_validator(mode="after")
    def _cooldowns_non_negative(self) -> ModelSOMechRuntimeState:
        negative = {wid: cd for wid, cd in self.weapon_cooldowns.items() if cd < 0}
        if negative:
            raise ValueError(f"weapon cooldowns must be >= 0; got {negative}")
        return self

    @model_validator(mode="after")
    def _transition_fields_paired(self) -> ModelSOMechRuntimeState:
        in_flight = self.transition_ticks_remaining > 0
        has_target = self.transition_to_mode is not None
        if in_flight != has_target:
            raise ValueError(
                "transition_ticks_remaining and transition_to_mode must be set together: "
                f"got ticks={self.transition_ticks_remaining}, "
                f"target={self.transition_to_mode!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Match state
# ---------------------------------------------------------------------------


class ModelSOMatchState(BaseModel):
    """Canonical state of one match, folded from the event ledger.

    ``winner_id`` is the winning *player* id (``None`` on draws).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.match_state"] = "steel_onslaught.match_state"

    match_id: str
    tick: int = Field(default=0, ge=0)
    status: SOMatchStatus = SOMatchStatus.PENDING
    seed: int = Field(ge=0, description="Per-match RNG seed recorded by MATCH_STARTED")
    max_ticks: int = Field(gt=0, description="Hard upper bound on match length in ticks")
    mech_states: dict[str, ModelSOMechRuntimeState] = Field(default_factory=dict)
    winner_id: str | None = Field(default=None, description="Winning player_id; None on draws")
    end_reason: SOMatchEndReason | None = None

    def player_ids(self) -> frozenset[str]:
        """Every player fielding a mech in this match (dead or alive)."""
        return frozenset(mech.player_id for mech in self.mech_states.values())

    def surviving_player_ids(self) -> frozenset[str]:
        """Players with at least one mech that is alive and whose pilot lives."""
        return frozenset(mech.player_id for mech in self.living_mechs())

    def living_mechs(self) -> tuple[ModelSOMechRuntimeState, ...]:
        """Mechs still in the fight (alive hull AND living pilot), insertion order."""
        return tuple(mech for mech in self.mech_states.values() if mech.alive and mech.pilot_alive)

    @model_validator(mode="after")
    def _tick_within_bound(self) -> ModelSOMatchState:
        if self.tick > self.max_ticks:
            raise ValueError(
                f"tick ({self.tick}) must not exceed max_ticks ({self.max_ticks}): "
                "the match is guaranteed to terminate at the bound"
            )
        return self

    @model_validator(mode="after")
    def _terminal_fields_match_status(self) -> ModelSOMatchState:
        if self.status is SOMatchStatus.ENDED:
            if self.end_reason is None:
                raise ValueError("an ended match must record an end_reason")
        else:
            if self.winner_id is not None or self.end_reason is not None:
                raise ValueError(
                    f"winner_id/end_reason are only valid on an ended match; "
                    f"status={self.status.value!r}, winner_id={self.winner_id!r}, "
                    f"end_reason={self.end_reason!r}"
                )
        return self

    @model_validator(mode="after")
    def _mech_keys_match_mech_ids(self) -> ModelSOMatchState:
        mismatched = {
            key: mech.mech_id for key, mech in self.mech_states.items() if key != mech.mech_id
        }
        if mismatched:
            raise ValueError(f"mech_states keys must equal mech_id values; got {mismatched}")
        return self
