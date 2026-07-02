"""Predictive pilot heuristic — Task 17 (spec-driven, tunable-pilots Task 4).

Anticipates enemy state via 1-tick lookahead using linear extrapolation of the
last (up to) 3 sensor observations.

Decision tree:
1. Estimate enemy distance next tick via linear extrapolation.
2. If enemy will enter weapon range next tick AND a mode-switch is needed AND
   mode_lock_expired -> SWITCH_MODE this tick.
3. Else if enemy in current optimal range AND lock_confidence >= lock_confidence_floor AND
   predicted_hit_probability >= predicted_hit_floor -> FIRE_WEAPON.
4. Else if heat >= redline_threshold - preemptive_vent_headroom -> VENT preemptively.
5. Else if pressure < regen_pressure_floor AND no immediate threat -> MOVE (defensive regen).
6. Fallback -> REMAIN.

Design invariants:
- Linear extrapolation is deterministic: no smoothing, no randomness.
  The 3-observation window is structural (NOT tunable) per addendum section 5.3.
- The pilot never chooses SWITCH_MODE when mode_lock_expired is False.
- Firing requires BOTH confidence and predicted hit probability thresholds.
- All decision thresholds are read from ``spec.parameters``; no module-level
  integer or float literals are used as decision constants.
"""

from __future__ import annotations

from steel_onslaught.contracts.pilot import ModelSOPilotSpec, ModelSOPredictivePilotParams
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOSensorReading,
    SOPilotAction,
    SOPilotReasonCode,
)

# The mode that grants weapon access; any other mode is considered to need a
# switch before weapons become fully available to the predictive pilot.
_WEAPON_MODE: str = "assault"


# ---------------------------------------------------------------------------
# Linear extrapolation helper
# ---------------------------------------------------------------------------


def _extrapolate_next_distance(observations: list[ModelSOSensorReading]) -> float | None:
    """Estimate enemy distance at next tick via linear extrapolation.

    Uses the last 3 observations (by tick order, newest last).
    Returns None if there are no observations.

    With 1 observation: returns the last known distance unchanged.
    With 2 observations: first-order difference.
    With 3 observations: mean of the last two first-order differences.

    The result is always deterministic (no smoothing or randomness).
    The 3-observation window is structural and NOT tunable per addendum section 5.3.
    """
    if not observations:
        return None

    # Take the up-to-3 most recent observations ordered by tick ascending.
    recent = sorted(observations, key=lambda o: (o.tick, o.enemy_mech_id))[-3:]

    if len(recent) == 1:
        return recent[0].distance_estimate

    # Compute the average delta per tick across consecutive pairs.
    deltas: list[float] = []
    for i in range(1, len(recent)):
        tick_diff = recent[i].tick - recent[i - 1].tick
        if tick_diff <= 0:
            # Same tick — treat as zero velocity contribution.
            deltas.append(0.0)
        else:
            deltas.append(
                (recent[i].distance_estimate - recent[i - 1].distance_estimate) / tick_diff
            )

    avg_delta = sum(deltas) / len(deltas)
    return max(0.0, recent[-1].distance_estimate + avg_delta)


def _predicted_hit_probability(distance: float, weapon_range: int) -> float:
    """Simple linear hit probability: 1.0 at range 0, 0.0 at range >= weapon_range.

    This is an approximation of the accuracy_curve concept from the weapon
    contract (Task 9). The pilot uses this to decide whether to fire; the
    actual hit resolution uses the full accuracy_curve in Task 24.
    """
    if weapon_range <= 0:
        return 1.0 if distance <= 0 else 0.0
    return max(0.0, 1.0 - distance / weapon_range)


def _best_confidence(observations: list[ModelSOSensorReading]) -> float:
    """Return the highest confidence value among all observations, or 0 if none."""
    if not observations:
        return 0.0
    return max(o.confidence for o in observations)


def _latest_distance(observations: list[ModelSOSensorReading]) -> float | None:
    """Return the distance estimate from the most recent observation, or None."""
    if not observations:
        return None
    return max(observations, key=lambda o: o.tick).distance_estimate


# ---------------------------------------------------------------------------
# Pilot
# ---------------------------------------------------------------------------


class PredictivePilot:
    """Predictive archetype — 1-tick lookahead, spec-driven decision tree.

    Constructed with a ``ModelSOPilotSpec`` whose archetype must be
    ``"predictive"``.  The ``spec.parameters`` (a
    ``ModelSOPredictivePilotParams``) supplies every decision threshold;
    no thresholds are hardcoded.  The 3-observation lookahead window is
    structural and not configurable via the spec.
    """

    def __init__(self, spec: ModelSOPilotSpec) -> None:
        if spec.archetype != "predictive":
            raise ValueError(
                f"PredictivePilot requires archetype='predictive', "
                f"got archetype={spec.archetype!r} (spec id={spec.id!r})"
            )
        if not isinstance(spec.parameters, ModelSOPredictivePilotParams):
            raise ValueError(
                f"spec.parameters must be ModelSOPredictivePilotParams, "
                f"got {type(spec.parameters).__name__!r}"
            )
        self._spec = spec
        self._params: ModelSOPredictivePilotParams = spec.parameters

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        """Produce a deterministic decision for the given observation."""
        params = self._params
        boiler = observation.boiler
        weapons = observation.weapons
        enemy_obs = list(observation.enemy_observations)

        # ----------------------------------------------------------------
        # Pre-compute shared values
        # ----------------------------------------------------------------
        current_distance = _latest_distance(enemy_obs)
        predicted_distance = _extrapolate_next_distance(enemy_obs)
        lock_confidence = _best_confidence(enemy_obs)

        # Best ready weapon (on cooldown=0, highest damage, sufficient pressure).
        ready_weapons = [
            w
            for w in weapons
            if w.cooldown_remaining_ticks == 0 and boiler.pressure_current >= w.pressure_cost
        ]
        best_weapon = max(ready_weapons, key=lambda w: w.damage) if ready_weapons else None

        in_weapon_range = (
            best_weapon is not None
            and current_distance is not None
            and current_distance <= best_weapon.range
        )
        will_enter_range_next_tick = (
            best_weapon is not None
            and predicted_distance is not None
            and predicted_distance <= best_weapon.range
        )
        mode_switch_needed = observation.current_mode != _WEAPON_MODE

        # Predicted hit probability uses best weapon range and current distance.
        hit_prob = (
            _predicted_hit_probability(current_distance, best_weapon.range)
            if (best_weapon is not None and current_distance is not None)
            else 0.0
        )

        immediate_threat = current_distance is not None and (
            best_weapon is not None and current_distance <= best_weapon.range
        )

        # ----------------------------------------------------------------
        # Decision tree (rules 1..5 per plan)
        # ----------------------------------------------------------------
        considered: list[ModelSOConsideredAction] = []

        # Rule 2: anticipated entry into range -> pre-emptive mode switch
        if will_enter_range_next_tick and mode_switch_needed and observation.mode_lock_expired:
            considered.append(ModelSOConsideredAction(action=SOPilotAction.SWITCH_MODE, score=0.9))
            considered.append(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.1))
            return ModelSOPilotDecision(
                action=SOPilotAction.SWITCH_MODE,
                action_params={"target_mode": _WEAPON_MODE},
                reason_code=SOPilotReasonCode.PREDICTED_INTERCEPT,
                confidence=lock_confidence,
                considered_actions=considered,
            )

        # Rule 3: fire if in optimal range with sufficient confidence + hit probability
        # Thresholds from spec: lock_confidence_floor, predicted_hit_floor
        if (
            in_weapon_range
            and lock_confidence >= params.lock_confidence_floor
            and hit_prob >= params.predicted_hit_floor
            and best_weapon is not None
        ):
            considered.append(ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=0.85))
            considered.append(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.1))
            return ModelSOPilotDecision(
                action=SOPilotAction.FIRE_WEAPON,
                action_params={"weapon_id": best_weapon.weapon_id},
                reason_code=SOPilotReasonCode.TARGET_IN_RANGE,
                confidence=lock_confidence,
                considered_actions=considered,
            )

        # Rule 4: preemptive vent when near redline.
        # Threshold from spec: preemptive_vent_headroom
        if boiler.heat_current >= boiler.heat_redline_threshold - params.preemptive_vent_headroom:
            considered.append(ModelSOConsideredAction(action=SOPilotAction.VENT, score=0.8))
            considered.append(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.05))
            return ModelSOPilotDecision(
                action=SOPilotAction.VENT,
                action_params={},
                reason_code=SOPilotReasonCode.HEAT_CRITICAL,
                confidence=1.0,
                considered_actions=considered,
            )

        # Rule 5: low pressure, no immediate threat -> move to defensive regen position.
        # Threshold from spec: regen_pressure_floor
        if boiler.pressure_current < params.regen_pressure_floor and not immediate_threat:
            considered.append(ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.7))
            considered.append(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.2))
            return ModelSOPilotDecision(
                action=SOPilotAction.MOVE,
                action_params={"direction": "defensive"},
                reason_code=SOPilotReasonCode.PRESSURE_RECOVERY,
                confidence=0.9,
                considered_actions=considered,
            )

        # Fallback: if the enemy is known but out of weapon range (or confidence
        # is too low to fire), close distance rather than remain — otherwise two
        # predictive pilots stare at each other forever and the match draws.
        # Only remain when there is genuinely no enemy information.
        if current_distance is not None and not in_weapon_range:
            considered.append(ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.4))
            considered.append(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.1))
            return ModelSOPilotDecision(
                action=SOPilotAction.MOVE,
                action_params={"direction": "toward_enemy"},
                reason_code=SOPilotReasonCode.CLOSING_DISTANCE,
                confidence=0.4,
                considered_actions=considered,
            )

        # Fallback: remain (no actionable enemy information)
        considered.append(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.3))
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            action_params={},
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=0.3,
            considered_actions=considered,
        )
