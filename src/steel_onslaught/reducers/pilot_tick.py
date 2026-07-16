"""Pilot orchestrator invocation reducer — Task 21.

Per-tick logic
--------------
On ``MATCH_TICK``, for each living mech (alive AND pilot_alive):

1. Build ``ModelSOPilotObservation`` from the current match state and any
   recent ``SENSOR_OBSERVATION`` events for this mech.
2. Call ``pilot.decide(observation)`` synchronously.
3. Emit ``PILOT_DECISION_MADE`` with the full decision payload
   (action, action_params, reason_code, confidence, considered_actions).
4. Translate the decision into the appropriate intent event:
     MOVE            -> MOVE_INTENT
     FIRE_WEAPON     -> WEAPON_FIRE_INTENT
     SWITCH_MODE     -> MODE_SWITCH_INTENT
     VENT            -> VENT_INTENT
     anything else   -> no intent event (REMAIN, DISENGAGE, etc.)

Design notes
------------
- ``PILOT_DECISION_MADE`` is always emitted *before* the corresponding intent
  event (the ordering guarantee for downstream reducers).
- Pilot side effects are isolated: the reducer does not update match state;
  only ``emit`` calls are side-effecting.
- ``sensor_events`` is the list of ``SENSOR_OBSERVATION`` envelopes collected
  this tick (passed in by the match runner / test harness).  Only events whose
  subject ``mech_id`` matches the observing mech are included in that mech's
  observation.
- The ``pilots`` mapping keys are mech_ids.  A living mech with no entry in
  ``pilots`` is skipped (defensive; the match runner must populate it).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import (
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOSensorReading,
    PilotProtocol,
    SOPilotAction,
)

_PRODUCER_NODE = "node.reducer.pilot_tick"


def _build_observation(
    mech: ModelSOMechRuntimeState,
    state: ModelSOMatchState,
    sensor_events: list[ModelSOEventEnvelope],
    weapon_specs: dict[str, ModelSOWeaponSpec],
) -> ModelSOPilotObservation:
    """Build the observation passed to a pilot for one tick."""
    # Weapon views — empty if no weapon_cooldowns recorded on the mech.
    # The cooldowns dict maps weapon_id -> remaining ticks.
    # We expose the weapons the mech *has cooldown entries for*; the pilot
    # only needs to know about weapons the match runner has registered.
    # Stats come from the weapon contract index (Task 34); a weapon with no
    # spec entry falls back to zeros (the Task 21 scope behavior).
    weapon_views: list[ModelSOPilotWeaponView] = []
    for weapon_id, cooldown in mech.weapon_cooldowns.items():
        spec = weapon_specs.get(weapon_id)
        weapon_views.append(
            ModelSOPilotWeaponView(
                weapon_id=weapon_id,
                damage=spec.damage if spec is not None else 0,
                range=spec.range if spec is not None else 0,
                pressure_cost=spec.pressure_cost if spec is not None else 0,
                heat_generated=spec.heat_generated if spec is not None else 0,
                cooldown_remaining_ticks=cooldown,
            )
        )

    # Sensor readings — filter to events whose subject is this mech.
    enemy_readings: list[ModelSOSensorReading] = []
    for evt in sensor_events:
        if evt.event_type != SOEventType.SENSOR_OBSERVATION:
            continue
        if evt.subject.mech_id != mech.mech_id:
            continue
        payload = evt.payload
        enemy_readings.append(
            ModelSOSensorReading(
                enemy_mech_id=payload["enemy_mech_id"],
                tick=evt.tick,
                distance_estimate=float(payload["distance_estimate"]),
                confidence=float(payload["confidence"]),
                heat_estimate=payload.get("heat_estimate"),
                mode_estimate=payload.get("mode_estimate"),
            )
        )
    # Newest last (events are already in ledger order; sensor_events passed in
    # tick order so no additional sort needed).

    return ModelSOPilotObservation(
        match_id=state.match_id,
        mech_id=mech.mech_id,
        tick=state.tick,
        match_elapsed_ticks=state.tick,
        boiler=mech.boiler,
        weapons=weapon_views,
        current_mode=mech.current_mode,
        mode_lock_expired=state.tick >= mech.mode_lock_until,
        position=mech.position,
        hp_percent=mech.hp_percent,
        under_sensor_lock=mech.under_sensor_lock,
        enemy_observations=enemy_readings,
    )


def _decision_payload(decision: ModelSOPilotDecision) -> dict[str, Any]:
    return {
        "action": decision.action.value,
        "action_params": decision.action_params,
        "reason_code": decision.reason_code.value,
        "confidence": decision.confidence,
        "considered_actions": [
            {"action": c.action.value, "score": c.score} for c in decision.considered_actions
        ],
    }


def _intent_for(decision: ModelSOPilotDecision) -> tuple[SOEventType, dict[str, Any]] | None:
    """Return (intent_event_type, payload) or None if no intent is needed."""
    match decision.action:
        case SOPilotAction.MOVE | SOPilotAction.DISENGAGE:
            # DISENGAGE is a directional move (away); treated as a MOVE_INTENT.
            return SOEventType.MOVE_INTENT, dict(decision.action_params)
        case SOPilotAction.FIRE_WEAPON:
            return SOEventType.WEAPON_FIRE_INTENT, dict(decision.action_params)
        case SOPilotAction.SWITCH_MODE:
            return SOEventType.MODE_SWITCH_INTENT, dict(decision.action_params)
        case SOPilotAction.VENT:
            return SOEventType.VENT_INTENT, dict(decision.action_params)
        case _:
            # REMAIN, ACTIVATE_MODULE, EMERGENCY_SHUTDOWN: no intent event.
            return None


class ReducerPilotTick:
    """Orchestrates pilot invocation for all living mechs on MATCH_TICK.

    Parameters
    ----------
    match_id:
        Identifier of the match this reducer belongs to.
    correlation_id:
        ONEX workflow correlation id shared across all events of this match.
    state:
        Current (immutable) match state.  The pilot tick reducer does NOT
        mutate match state; it only emits events.
    pilots:
        Mapping from ``mech_id`` to a ``PilotProtocol`` implementation.
        A living mech not present in this mapping is skipped.
    sensor_events:
        ``SENSOR_OBSERVATION`` events emitted *this tick* by the sensor
        reducer.  Passed to ``_build_observation`` to populate enemy readings.
    emit:
        Callback invoked for every emitted event.  Pass ``bus.publish`` in
        production and a list-append in tests.
    """

    def __init__(
        self,
        match_id: str,
        state: ModelSOMatchState,
        pilots: dict[str, PilotProtocol],
        sensor_events: list[ModelSOEventEnvelope],
        emit: Callable[[ModelSOEventEnvelope], None],
        weapon_specs: dict[str, ModelSOWeaponSpec] | None = None,
        *,
        correlation_id: UUID,
        event_factory: EventFactory,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._events = event_factory
        self._state = state
        self._pilots = pilots
        self._sensor_events = sensor_events
        self._emit = emit
        self._weapon_specs = weapon_specs if weapon_specs is not None else {}

    @property
    def state(self) -> ModelSOMatchState:
        return self._state

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """EventHandler-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> ModelSOMatchState:
        """Process one event; invoke pilots on MATCH_TICK.

        Non-MATCH_TICK events are ignored (returns current state unchanged).
        """
        if event.match_id != self._match_id:
            return self._state
        if event.event_type != SOEventType.MATCH_TICK:
            return self._state

        self._process_tick()
        return self._state

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_tick(self) -> None:
        state = self._state
        for mech in state.living_mechs():
            pilot = self._pilots.get(mech.mech_id)
            if pilot is None:
                continue
            self._invoke_pilot(pilot, mech, state)

    def _invoke_pilot(
        self,
        pilot: PilotProtocol,
        mech: ModelSOMechRuntimeState,
        state: ModelSOMatchState,
    ) -> None:
        observation = _build_observation(mech, state, self._sensor_events, self._weapon_specs)
        decision = pilot.decide(observation)

        subject = ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id)

        # 1. Emit PILOT_DECISION_MADE first (invariant: before any intent).
        self._emit(
            self._events.make(
                match_id=self._match_id,
                correlation_id=self._correlation_id,
                tick=state.tick,
                sequence_in_tick=0,
                event_type=SOEventType.PILOT_DECISION_MADE,
                producer_node=_PRODUCER_NODE,
                subject=subject,
                payload=_decision_payload(decision),
            )
        )

        # 2. Translate decision to intent event (if applicable).
        intent = _intent_for(decision)
        if intent is not None:
            intent_type, intent_payload = intent
            self._emit(
                self._events.make(
                    match_id=self._match_id,
                    correlation_id=self._correlation_id,
                    tick=state.tick,
                    sequence_in_tick=0,
                    event_type=intent_type,
                    producer_node=_PRODUCER_NODE,
                    subject=subject,
                    payload=intent_payload,
                )
            )
