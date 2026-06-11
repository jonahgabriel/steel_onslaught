"""Aggressive pilot heuristic — Task 15.

Deterministic decision tree implementing an aggressive combat archetype.
No randomness, no LLM — pure Python conditionals that produce the same
decision for the same observation every time.

Decision priority (from the plan §Task 15):
1. If heat >= rupture_threshold - 5 → VENT (near-rupture guard, highest priority).
2. If enemy in weapon range AND any weapon ready AND pressure >= weapon_cost
   AND heat < rupture_threshold - 5 → FIRE highest-damage weapon at enemy
   (lowest weapon_id alphabetically on damage tie).
3. Else if not in assault mode AND mode_lock_expired AND pressure >= 12
   AND heat <= 80 → SWITCH_MODE assault.
4. Else if heat >= 90 (just below redline) → VENT.
5. Else → MOVE toward enemy at full speed.

The plan also states "tolerates redline up to heat == rupture_threshold - 5":
this means fire is allowed even at redline, as long as heat < rupture_threshold - 5.
"""

from __future__ import annotations

from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    SOPilotAction,
    SOPilotReasonCode,
)

# Thresholds used by the heuristic.
_MODE_SWITCH_PRESSURE_MINIMUM: int = 12
_MODE_SWITCH_HEAT_MAXIMUM: int = 80
_VENT_HEAT_THRESHOLD: int = 90  # Rule 4: vent if heat >= this
# Rule 5 / Rule 2: tolerates redline up to rupture_threshold - 5; above that, vent.
_RUPTURE_GUARD_OFFSET: int = 5


def _best_weapon(
    observation: ModelSOPilotObservation,
    enemy_distance: float,
) -> ModelSOPilotWeaponView | None:
    """Return the highest-damage ready weapon that can reach the enemy.

    Tiebreaker: lowest weapon_id alphabetically (deterministic, no RNG).
    Returns None if no eligible weapon exists.
    """
    candidates = [
        w
        for w in observation.weapons
        if (
            w.cooldown_remaining_ticks == 0
            and observation.boiler.pressure_current >= w.pressure_cost
            and w.range >= enemy_distance
        )
    ]
    if not candidates:
        return None
    # Sort: primary descending damage, secondary ascending weapon_id.
    candidates.sort(key=lambda w: (-w.damage, w.weapon_id))
    return candidates[0]


def _enemy_distance(observation: ModelSOPilotObservation) -> float:
    """Return the most-recent enemy distance estimate, or infinity if none."""
    if not observation.enemy_observations:
        return float("inf")
    # Observations are newest-last per the schema docstring.
    return observation.enemy_observations[-1].distance_estimate


class AggressivePilot:
    """Aggressive combat archetype — deterministic, heuristic-only.

    Priority:
    1. Near-rupture guard: VENT when heat >= rupture_threshold - 5.
    2. Fire the highest-damage weapon when enemy is in range and resources allow.
    3. Switch to assault mode if not already there and conditions are met.
    4. Vent if heat >= 90 (just-below-redline proactive cooling).
    5. Move toward enemy.
    """

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        boiler = observation.boiler
        heat = boiler.heat_current
        rupture = boiler.heat_rupture_threshold
        distance = _enemy_distance(observation)

        # ---------------------------------------------------------------
        # Rule 1 (highest priority): near-rupture guard.
        # heat >= rupture_threshold - 5 → VENT immediately.
        # ---------------------------------------------------------------
        near_rupture_guard = heat >= (rupture - _RUPTURE_GUARD_OFFSET)
        if near_rupture_guard:
            return ModelSOPilotDecision(
                action=SOPilotAction.VENT,
                action_params={},
                reason_code=SOPilotReasonCode.HEAT_CRITICAL,
                confidence=1.0,
                considered_actions=[
                    ModelSOConsideredAction(action=SOPilotAction.VENT, score=1.0),
                    ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=0.0),
                ],
            )

        # ---------------------------------------------------------------
        # Rule 2: switch to assault mode if not there and conditions met.
        # Prioritised above firing so the pilot enters its optimal combat mode
        # before expending resources. This matches the plan invariant: "Given
        # mode=recon + assault available + enemy in range: switches to assault
        # before firing."
        # Conditions: not in assault mode, mode_lock_expired, pressure >= 12,
        #             heat <= 80.
        # ---------------------------------------------------------------
        not_in_assault = observation.current_mode != "assault"
        mode_conditions_met = (
            not_in_assault
            and observation.mode_lock_expired
            and boiler.pressure_current >= _MODE_SWITCH_PRESSURE_MINIMUM
            and heat <= _MODE_SWITCH_HEAT_MAXIMUM
        )
        if mode_conditions_met:
            return ModelSOPilotDecision(
                action=SOPilotAction.SWITCH_MODE,
                action_params={"target_mode": "assault"},
                reason_code=SOPilotReasonCode.MODE_ADVANTAGE,
                confidence=0.8,
                considered_actions=[
                    ModelSOConsideredAction(action=SOPilotAction.SWITCH_MODE, score=0.8),
                    ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.3),
                ],
            )

        # ---------------------------------------------------------------
        # Rule 3: fire the best weapon if enemy in range and resources allow.
        # Permitted even while at redline, provided heat < rupture_threshold - 5
        # (already checked in Rule 1 above).
        # ---------------------------------------------------------------
        best_weapon = _best_weapon(observation, distance)
        if best_weapon is not None:
            return ModelSOPilotDecision(
                action=SOPilotAction.FIRE_WEAPON,
                action_params={"weapon_id": best_weapon.weapon_id},
                reason_code=SOPilotReasonCode.TARGET_IN_RANGE,
                confidence=0.9,
                considered_actions=[
                    ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=0.9),
                    ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.2),
                ],
            )

        # ---------------------------------------------------------------
        # Rule 4: proactive vent at heat >= 90 (just below default redline of 80
        # is not actually "just below redline" for all configs — the rule uses
        # the fixed threshold 90 from the plan, not observation.boiler.heat_redline).
        # ---------------------------------------------------------------
        if heat >= _VENT_HEAT_THRESHOLD:
            return ModelSOPilotDecision(
                action=SOPilotAction.VENT,
                action_params={},
                reason_code=SOPilotReasonCode.HEAT_CRITICAL,
                confidence=0.85,
                considered_actions=[
                    ModelSOConsideredAction(action=SOPilotAction.VENT, score=0.85),
                    ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.2),
                ],
            )

        # ---------------------------------------------------------------
        # Rule 5 (fallback): move toward the enemy at full speed.
        # ---------------------------------------------------------------
        return ModelSOPilotDecision(
            action=SOPilotAction.MOVE,
            action_params={"direction": "toward_enemy", "speed": "full"},
            reason_code=SOPilotReasonCode.CLOSING_DISTANCE,
            confidence=0.7,
            considered_actions=[
                ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.7),
                ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.1),
            ],
        )
