"""Defensive pilot heuristic archetype — Task 16 / tunable-pilots Task 3.

Decision tree (highest priority first):

1. If heat >= redline_threshold - vent_headroom_below_redline → VENT.
2. Else if not in evasion mode AND under sensor lock AND mode_lock_expired
   AND pressure available → SWITCH_MODE evasion.
3. Else if enemy in range AND high-confidence target (confidence >= fire_confidence_floor)
   AND pressure available AND heat headroom >= fire_heat_headroom → FIRE.
4. Else if hp_percent < disengage_hp_pct → DISENGAGE (move away).
5. Else → MOVE to maintain optimal range.

All decisions are deterministic (no random tiebreakers).  Multiple weapons
ready in rule 3: deterministically pick the weapon whose effective range is
closest to the optimal stand-off (longest-range weapon available in range),
breaking ties alphabetically by weapon_id.

The four tunable constants (rule 1, 3 confidence, 3 headroom, rule 4) come
from a ``ModelSOPilotSpec`` with archetype ``defensive``.  Rule 2 has no
tunable constant and is structurally unchanged.
"""

from __future__ import annotations

from steel_onslaught.contracts.pilot import ModelSODefensivePilotParams, ModelSOPilotSpec
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOSensorReading,
    SOPilotAction,
    SOPilotReasonCode,
)


def _best_ready_weapon_in_range(
    obs: ModelSOPilotObservation,
    enemy_distance: float,
) -> ModelSOPilotWeaponView | None:
    """Return the ready weapon to fire, or None if none is valid.

    A weapon is valid when:
    - cooldown_remaining_ticks == 0 (ready)
    - obs.boiler.pressure_current >= weapon.pressure_cost (can afford)
    - weapon.range >= enemy_distance (enemy is in range)

    Deterministic selection: among valid weapons, return the one with the
    greatest range (to maximise stand-off advantage), breaking ties
    alphabetically by weapon_id (ascending).
    """
    candidates = [
        w
        for w in obs.weapons
        if (
            w.cooldown_remaining_ticks == 0
            and obs.boiler.pressure_current >= w.pressure_cost
            and w.range >= enemy_distance
        )
    ]
    if not candidates:
        return None
    # Deterministic: sort by range descending, then weapon_id ascending for ties.
    return sorted(candidates, key=lambda w: (-w.range, w.weapon_id))[0]


def _best_enemy_reading(obs: ModelSOPilotObservation) -> ModelSOSensorReading | None:
    """Return the most recent (highest-tick) enemy reading, or None."""
    if not obs.enemy_observations:
        return None
    return max(obs.enemy_observations, key=lambda r: r.tick)


class DefensivePilot:
    """Defensive pilot archetype.

    Prioritises survivability: manages heat aggressively, breaks sensor locks
    via evasion mode, fires only when conditions are favourable, and retreats
    when HP is critically low.

    Implements ``PilotProtocol`` — fully deterministic, no I/O.

    Parameters
    ----------
    spec:
        A ``ModelSOPilotSpec`` with ``archetype == "defensive"``.  Raises
        ``ValueError`` at construction if the archetype does not match.
    """

    def __init__(self, spec: ModelSOPilotSpec) -> None:
        if spec.archetype != "defensive":
            raise ValueError(
                f"DefensivePilot requires archetype='defensive', got {spec.archetype!r}"
            )
        assert isinstance(spec.parameters, ModelSODefensivePilotParams)
        self._params: ModelSODefensivePilotParams = spec.parameters

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        """Apply the defensive decision tree and return the chosen action."""
        params = self._params
        boiler = observation.boiler
        redline = boiler.heat_redline_threshold
        heat = boiler.heat_current

        considered: list[ModelSOConsideredAction] = []

        # ------------------------------------------------------------------
        # Rule 1: Heat emergency — vent when heat >= redline - vent_headroom_below_redline.
        # ------------------------------------------------------------------
        if heat >= redline - params.vent_headroom_below_redline:
            considered.extend(
                [
                    ModelSOConsideredAction(action=SOPilotAction.VENT, score=1.0),
                    ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.1),
                ]
            )
            return ModelSOPilotDecision(
                action=SOPilotAction.VENT,
                action_params={},
                reason_code=SOPilotReasonCode.HEAT_CRITICAL,
                confidence=1.0,
                considered_actions=considered,
            )

        # ------------------------------------------------------------------
        # Rule 2: Break sensor lock via evasion mode.
        # Requires: not already in evasion, mode lock expired,
        # under sensor lock, and enough pressure for the mode switch.
        # (No tunable constant — structurally unchanged from MVP.)
        # ------------------------------------------------------------------
        if (
            observation.current_mode != "evasion"
            and observation.under_sensor_lock
            and observation.mode_lock_expired
            and boiler.pressure_current > 0
        ):
            considered.extend(
                [
                    ModelSOConsideredAction(action=SOPilotAction.SWITCH_MODE, score=0.9),
                    ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.4),
                ]
            )
            return ModelSOPilotDecision(
                action=SOPilotAction.SWITCH_MODE,
                action_params={"target_mode": "evasion"},
                reason_code=SOPilotReasonCode.EVADE_SENSOR_LOCK,
                confidence=0.9,
                considered_actions=considered,
            )

        # ------------------------------------------------------------------
        # Rule 3: Fire — only when all defensive conditions are met.
        # Requires: enemy reading with confidence >= fire_confidence_floor
        # and enemy in range, a ready weapon the boiler can afford, and
        # heat headroom (redline - heat) >= fire_heat_headroom.
        # ------------------------------------------------------------------
        enemy = _best_enemy_reading(obs=observation)
        heat_headroom = redline - heat

        if enemy is not None and enemy.confidence >= params.fire_confidence_floor:
            weapon = _best_ready_weapon_in_range(observation, enemy.distance_estimate)
            if weapon is not None and heat_headroom >= params.fire_heat_headroom:
                considered.extend(
                    [
                        ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=0.8),
                        ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.3),
                    ]
                )
                return ModelSOPilotDecision(
                    action=SOPilotAction.FIRE_WEAPON,
                    action_params={
                        "weapon_id": weapon.weapon_id,
                        "target_mech_id": enemy.enemy_mech_id,
                    },
                    reason_code=SOPilotReasonCode.TARGET_IN_RANGE,
                    confidence=enemy.confidence,
                    considered_actions=considered,
                )

        # ------------------------------------------------------------------
        # Rule 4: Critically low HP — disengage (move away from enemy).
        # ------------------------------------------------------------------
        if observation.hp_percent < params.disengage_hp_pct:
            considered.extend(
                [
                    ModelSOConsideredAction(action=SOPilotAction.DISENGAGE, score=0.85),
                    ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.2),
                ]
            )
            return ModelSOPilotDecision(
                action=SOPilotAction.DISENGAGE,
                action_params={"direction": "defensive"},
                reason_code=SOPilotReasonCode.LOW_HP_RETREAT,
                confidence=0.85,
                considered_actions=considered,
            )

        # ------------------------------------------------------------------
        # Rule 5: Fallback — move to maintain optimal range (open distance).
        # ------------------------------------------------------------------
        considered.append(ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.5))
        return ModelSOPilotDecision(
            action=SOPilotAction.MOVE,
            action_params={"direction": "defensive"},
            reason_code=SOPilotReasonCode.MAINTAIN_RANGE,
            confidence=0.5,
            considered_actions=considered,
        )
