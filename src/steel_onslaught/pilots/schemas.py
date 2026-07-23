"""Pilot observation + decision schemas — Task 14.

The pilot tick reducer (Task 21) builds a ``ModelSOPilotObservation`` per
living mech per tick, calls ``PilotProtocol.decide``, and emits the returned
``ModelSOPilotDecision`` as the ``PILOT_DECISION_MADE`` payload.

Invariants enforced here:
- ``confidence`` is clamped to [0, 1] (not rejected — heuristics may emit raw
  scores outside the band and rely on the clamp).
- ``considered_actions`` must include the chosen action.
- A decision must reference an action that is available given the current
  observation (``validate_decision_against_observation``); e.g. SWITCH_MODE
  requires ``mode_lock_expired`` and FIRE_WEAPON requires a ready weapon the
  boiler can afford. Finer-grained validation (which mode, which target) is
  owned by the downstream intent reducers.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.player_selection import DecisionSource
from steel_onslaught.immutable import FrozenJSONMapping

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SOPilotAction(StrEnum):
    """Action a pilot may choose for a tick."""

    REMAIN = "remain"
    MOVE = "move"
    FIRE_WEAPON = "fire_weapon"
    ACTIVATE_MODULE = "activate_module"
    VENT = "vent"
    SWITCH_MODE = "switch_mode"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"
    DISENGAGE = "disengage"
    DEPLOY_UTILITY = "deploy_utility"


class SOPilotReasonCode(StrEnum):
    """Why the pilot chose its action (telemetry + decision inspector)."""

    TARGET_IN_RANGE = "target_in_range"
    MODE_ADVANTAGE = "mode_advantage"
    HEAT_CRITICAL = "heat_critical"
    CLOSING_DISTANCE = "closing_distance"
    MAINTAIN_RANGE = "maintain_range"
    LOW_HP_RETREAT = "low_hp_retreat"
    LOW_CONFIDENCE_HOLD = "low_confidence_hold"
    PRESSURE_RECOVERY = "pressure_recovery"
    PREDICTED_INTERCEPT = "predicted_intercept"
    EVADE_SENSOR_LOCK = "evade_sensor_lock"
    NO_VIABLE_ACTION = "no_viable_action"
    HUMAN_INPUT = "human_input"
    # LLM-pilot-specific: a decision made by the LLM, or a REMAIN fallback when
    # the LLM call failed / returned an invalid action.
    LLM_DECISION = "llm_decision"
    LLM_FALLBACK = "llm_fallback"


# ---------------------------------------------------------------------------
# Observation sub-models
# ---------------------------------------------------------------------------


class ModelSOPosition(BaseModel):
    """Integer grid position (Chebyshev-distance arena, Task 19)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: StrictInt
    y: StrictInt


class SOCompassDirection(StrEnum):
    """Eight deterministic king-move directions exposed as terrain awareness."""

    N = "n"
    NE = "ne"
    E = "e"
    SE = "se"
    S = "s"
    SW = "sw"
    W = "w"
    NW = "nw"


# One closed move-intent vocabulary shared by LLM, human-command, and event
# contracts.  A direction must be executable by the deterministic runner.
type SOMoveDirection = Literal[
    "toward_enemy",
    "defensive",
    "flank_left",
    "flank_right",
    "toward_cover",
    "hold_position",
]


class ModelSOPilotWeaponView(BaseModel):
    """Per-weapon readiness view exposed to the pilot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    weapon_id: str
    damage: int = Field(ge=0)
    range: int = Field(ge=0)
    pressure_cost: int = Field(ge=0)
    heat_generated: int = Field(ge=0)
    cooldown_remaining_ticks: int = Field(ge=0, description="0 means ready to fire")


class ModelSOSensorReading(BaseModel):
    """One sensor observation of an enemy mech (SENSOR_OBSERVATION payload view)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enemy_mech_id: str
    tick: int = Field(ge=0, description="Tick at which the observation was made")
    distance_estimate: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    heat_estimate: float | None = Field(
        default=None, description="Present iff a thermal sensor resolved target heat"
    )
    mode_estimate: ModeId | None = Field(
        default=None, description="Present iff an acoustic sensor resolved target mode"
    )


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


class ModelSOObjectiveView(BaseModel):
    """One objective cell as the pilot sees it this tick (Phase 4).

    ``control`` is viewer-relative (``own``/``enemy``/``contested``/
    ``unclaimed``) and computed by the SAME rule the scoring fold uses
    (``match.objectives``), so what the pilot is told about control can never
    diverge from what actually scores.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_id: str = Field(pattern=r"^objective\.[a-z][a-z0-9_]*$")
    cell: ModelSOPosition
    vp_per_round: int = Field(ge=1)
    control: Literal["own", "enemy", "contested", "unclaimed"]
    own_distance_chebyshev: int = Field(ge=0)


class ModelSOVictoryPointsView(BaseModel):
    """Match-level VP scoreboard as the pilot sees it this tick (Phase 4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    own_vp: int = Field(ge=0)
    enemy_vp: int = Field(ge=0)
    vp_threshold: int = Field(gt=0)


class ModelSOPilotObservation(BaseModel):
    """The full view passed to a pilot for one tick.

    This is everything the pilot is allowed to know: its own state plus
    noisy sensor readings of the enemy. Pilots never see ground truth.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.pilot_observation"] = "steel_onslaught.pilot_observation"

    match_id: str
    mech_id: str
    player_id: str
    tick: int = Field(ge=0)
    match_elapsed_ticks: int = Field(ge=0)

    # Own state.
    boiler: ModelSOBoilerState
    weapons: list[ModelSOPilotWeaponView]
    current_mode: ModeId = Field(description="Closed current combat mode")
    mode_lock_expired: bool
    position: ModelSOPosition
    hp_percent: float = Field(ge=0.0, le=100.0)
    under_sensor_lock: bool
    has_line_of_sight_to_enemy: bool = False
    blocked_directions: tuple[SOCompassDirection, ...] = ()

    # Enemy state as observed (noisy, possibly stale; newest last).
    enemy_observations: list[ModelSOSensorReading]

    # Objective-victory view (Phase 4).  Empty/None on objective-free arenas,
    # which keeps every pre-Phase-4 observation (and its serialized prompt)
    # byte-identical.  Set together — validated below.
    objectives: tuple[ModelSOObjectiveView, ...] = ()
    victory_points: ModelSOVictoryPointsView | None = None

    @model_validator(mode="after")
    def _objective_view_is_paired(self) -> ModelSOPilotObservation:
        if bool(self.objectives) != (self.victory_points is not None):
            raise ValueError(
                "objectives and victory_points must be set together "
                "(a scoreboard without cells, or cells without a finish line, "
                "is a half-configured objective view)"
            )
        return self


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class ModelSOConsideredAction(BaseModel):
    """One scored candidate from the pilot's decision process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: SOPilotAction
    score: StrictFloat


class ModelSOPilotDecision(BaseModel):
    """The pilot's chosen action for a tick, with full decision telemetry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.pilot_decision"] = "steel_onslaught.pilot_decision"

    action: SOPilotAction
    action_params: FrozenJSONMapping = Field(
        default_factory=dict,
        validate_default=True,
        description="Kwargs for the chosen action, per action type",
    )
    reason_code: SOPilotReasonCode
    confidence: StrictFloat
    considered_actions: Annotated[
        Sequence[ModelSOConsideredAction],
        AfterValidator(tuple),
        PlainSerializer(list, return_type=list[ModelSOConsideredAction]),
    ]
    rationale: str | None = Field(
        default=None,
        description="Freeform natural-language reasoning (LLM pilots); None for heuristics.",
    )
    decision_source: DecisionSource | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Exact human-command or model-completion provenance when available.",
    )

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        """Clamp (not reject): heuristic scores outside [0, 1] saturate."""
        return min(1.0, max(0.0, v))

    @model_validator(mode="after")
    def _chosen_action_in_considered(self) -> ModelSOPilotDecision:
        if self.action not in {candidate.action for candidate in self.considered_actions}:
            raise ValueError(
                f"considered_actions must include the chosen action {self.action!r}; "
                f"got {[candidate.action for candidate in self.considered_actions]!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Availability invariant
# ---------------------------------------------------------------------------

_ALWAYS_AVAILABLE: frozenset[SOPilotAction] = frozenset(
    {
        SOPilotAction.REMAIN,
        SOPilotAction.MOVE,
        SOPilotAction.VENT,
        SOPilotAction.ACTIVATE_MODULE,
        SOPilotAction.EMERGENCY_SHUTDOWN,
        SOPilotAction.DISENGAGE,
    }
)


def available_actions(observation: ModelSOPilotObservation) -> frozenset[SOPilotAction]:
    """Actions the schema layer can prove available for this observation.

    - SWITCH_MODE requires the mode lock to have expired.
    - FIRE_WEAPON requires at least one weapon off cooldown whose pressure
      cost the boiler can currently afford.
    - Everything else is always schema-available; downstream intent reducers
      own the finer-grained checks (target validity, module state, etc.).
    """
    actions = set(_ALWAYS_AVAILABLE)
    if observation.mode_lock_expired:
        actions.add(SOPilotAction.SWITCH_MODE)
    if any(
        weapon.cooldown_remaining_ticks == 0
        and observation.boiler.pressure_current >= weapon.pressure_cost
        for weapon in observation.weapons
    ):
        actions.add(SOPilotAction.FIRE_WEAPON)
    return frozenset(actions)


def validate_decision_against_observation(
    observation: ModelSOPilotObservation, decision: ModelSOPilotDecision
) -> None:
    """Raise ``ValueError`` if the decision's action is not available.

    Called by the pilot tick reducer (Task 21) before translating a decision
    into intent events.
    """
    actions = available_actions(observation)
    if decision.action not in actions:
        raise ValueError(
            f"action {decision.action.value!r} is not available for mech "
            f"{observation.mech_id!r} at tick {observation.tick}; "
            f"available: {sorted(action.value for action in actions)}"
        )


# ---------------------------------------------------------------------------
# Pilot protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PilotProtocol(Protocol):
    """A pilot archetype: deterministic mapping observation -> decision."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision: ...
