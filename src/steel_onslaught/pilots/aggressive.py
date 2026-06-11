"""Aggressive pilot heuristic — Task 15 (spec-driven refactor: Task 2).

Deterministic decision tree implementing an aggressive combat archetype.
No randomness, no LLM — pure Python conditionals that produce the same
decision for the same observation every time.

Decision priority (from the plan §Task 15):
1. If heat >= rupture_threshold - vent_at_heat_margin → VENT (near-rupture guard).
2. If not in assault mode AND mode_lock_expired AND pressure >= mode_switch_pressure_floor
   AND heat <= mode_switch_heat_ceiling → SWITCH_MODE assault.
3. If enemy in weapon range AND any weapon ready AND pressure >= weapon_cost → FIRE weapon
   selected by weapon_preference policy (lowest weapon_id tiebreak).
4. Else if heat >= idle_vent_heat_threshold → VENT.
5. Else → MOVE toward enemy at full speed.

All decision thresholds come from the injected ``ModelSOPilotSpec``; no
module-level integer literals survive as decision constants.
"""

from __future__ import annotations

from steel_onslaught.contracts.pilot import (
    ModelSOAggressivePilotParams,
    ModelSOPilotSpec,
    SOWeaponPreference,
)
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    SOPilotAction,
    SOPilotReasonCode,
)


def _best_weapon(
    observation: ModelSOPilotObservation,
    enemy_distance: float,
    preference: SOWeaponPreference,
) -> ModelSOPilotWeaponView | None:
    """Return the preferred ready weapon that can reach the enemy.

    Weapon selection policy (per addendum §5.1):
    - ``HIGHEST_DAMAGE``: sort primary descending damage, secondary ascending weapon_id.
    - ``LOWEST_HEAT``: sort primary ascending heat_generated, secondary ascending weapon_id.

    The lowest-weapon_id tiebreak is fixed under both policies.
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
    if preference is SOWeaponPreference.HIGHEST_DAMAGE:
        candidates.sort(key=lambda w: (-w.damage, w.weapon_id))
    else:  # LOWEST_HEAT
        candidates.sort(key=lambda w: (w.heat_generated, w.weapon_id))
    return candidates[0]


def _enemy_distance(observation: ModelSOPilotObservation) -> float:
    """Return the most-recent enemy distance estimate, or infinity if none."""
    if not observation.enemy_observations:
        return float("inf")
    # Observations are newest-last per the schema docstring.
    return observation.enemy_observations[-1].distance_estimate


class AggressivePilot:
    """Aggressive combat archetype — spec-driven, deterministic, heuristic-only.

    All decision thresholds are read from the injected ``ModelSOPilotSpec``.
    The decision tree structure (rule order, scoring, action_params shape) is
    fixed in code; only the constants are tunable.

    Priority:
    1. Near-rupture guard: VENT when heat >= rupture_threshold - vent_at_heat_margin.
    2. Switch to assault mode when not there and conditions are met.
    3. Fire the preferred weapon when enemy is in range and resources allow.
    4. Vent if heat >= idle_vent_heat_threshold.
    5. Move toward enemy.
    """

    def __init__(self, spec: ModelSOPilotSpec) -> None:
        if spec.archetype != "aggressive":
            raise ValueError(
                f"AggressivePilot requires archetype='aggressive'; "
                f"got archetype={spec.archetype!r} (spec id: {spec.id!r})"
            )
        assert isinstance(spec.parameters, ModelSOAggressivePilotParams)
        self._params: ModelSOAggressivePilotParams = spec.parameters

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        params = self._params
        boiler = observation.boiler
        heat = boiler.heat_current
        rupture = boiler.heat_rupture_threshold
        distance = _enemy_distance(observation)

        # ---------------------------------------------------------------
        # Rule 1 (highest priority): near-rupture guard.
        # heat >= rupture_threshold - vent_at_heat_margin → VENT immediately.
        # Strict >= semantics (addendum §5.1).
        # ---------------------------------------------------------------
        near_rupture_guard = heat >= (rupture - params.vent_at_heat_margin)
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
        # before expending resources.
        # Conditions: not in assault mode, mode_lock_expired,
        #             pressure >= mode_switch_pressure_floor,
        #             heat <= mode_switch_heat_ceiling.
        # ---------------------------------------------------------------
        not_in_assault = observation.current_mode != "assault"
        mode_conditions_met = (
            not_in_assault
            and observation.mode_lock_expired
            and boiler.pressure_current >= params.mode_switch_pressure_floor
            and heat <= params.mode_switch_heat_ceiling
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
        # Permitted even while at redline, provided heat < rupture_threshold -
        # vent_at_heat_margin (already checked in Rule 1 above).
        # ---------------------------------------------------------------
        best_weapon = _best_weapon(observation, distance, params.weapon_preference)
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
        # Rule 4: proactive vent at heat >= idle_vent_heat_threshold.
        # ---------------------------------------------------------------
        if heat >= params.idle_vent_heat_threshold:
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
