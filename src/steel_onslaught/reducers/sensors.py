"""Sensor observation reducer — Task 20.

Per-tick logic
--------------
For each living mech that has active sensor modules (``sensor_ids`` non-empty)
and whose ``sensor_dropout_ticks_remaining`` is 0:

  1. Compute the true Chebyshev distance to each opponent mech.
  2. For each sensor the mech carries:
       a. Skip if target is out of sensor range.
       b. Add deterministic noise to produce ``distance_estimate``:
             noise = MatchRng.gauss(seed, tick, sensor_id, mean=0, stddev=1-precision)
             distance_estimate = max(0, true_distance + noise)
       c. Compute confidence:
             confidence = clamp(precision * (1 - jamming_intensity), 0, 1)
       d. Sensor-type extras:
             thermal  -> include heat_estimate iff target heat_current >= 30
             acoustic -> include mode_estimate iff target speed >= 2
       e. Emit ``SENSOR_OBSERVATION`` via the injected ``emit`` callback.

Determinism guarantee
---------------------
``MatchRng.for_event(tick, sensor_id, "sensor_noise")`` derives a per-context
``random.Random`` from the BLAKE2b of ``(match_seed, tick, sensor_id, "sensor_noise")``.
Replaying the same ledger always reconstructs the identical observation stream.

Design notes
------------
- The reducer is stateless between ticks: no observation history is kept here.
  The pilot tick reducer (Task 21) reads the bus emission directly.
- ``sensor_specs`` is a dict indexed by sensor id; unknown sensor ids are
  silently skipped (forward-compat with contract evolution).
- ``emit`` is an injected callback so the reducer does not couple to a specific
  bus implementation; callers pass ``bus.publish`` directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition

_PRODUCER_NODE = "node.reducer.sensors"

# Sensor-id suffixes that trigger type-specific extras.
_THERMAL_SUFFIX = "thermal"
_ACOUSTIC_SUFFIX = "acoustic"

# Heat threshold above which a thermal sensor reports heat_estimate.
_THERMAL_HEAT_THRESHOLD = 30

# Speed threshold at or above which an acoustic sensor reports mode_estimate.
_ACOUSTIC_SPEED_THRESHOLD = 2


def _chebyshev(a: ModelSOPosition, b: ModelSOPosition) -> int:
    return max(abs(b.x - a.x), abs(b.y - a.y))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class ReducerSensors:
    """Folds MATCH_TICK events into SENSOR_OBSERVATION emissions.

    Non-MATCH_TICK events are passed through without side-effects so the
    replay engine can feed the full ledger through every reducer.

    Parameters
    ----------
    match_id:
        Identifier of the match this reducer belongs to.
    correlation_id:
        ONEX workflow correlation id shared across all events of this match.
    state:
        Current (immutable) match state.  Updated by ``apply`` on MATCH_TICK.
    sensor_specs:
        Mapping from ``sensor_id`` to its ``ModelSOSensorSpec`` contract.
        Unknown ids are skipped; callers load specs at match startup.
    emit:
        Callback invoked for every emitted event.  Pass ``bus.publish`` in
        production and a list-append in tests.
    """

    def __init__(
        self,
        match_id: str,
        state: ModelSOMatchState,
        sensor_specs: dict[str, ModelSOSensorSpec],
        emit: Callable[[ModelSOEventEnvelope], None],
        *,
        correlation_id: UUID,
        event_factory: EventFactory,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._events = event_factory
        self._state = state
        self._sensor_specs = sensor_specs
        self._emit = emit

    @property
    def state(self) -> ModelSOMatchState:
        return self._state

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """EventHandler-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> ModelSOMatchState:
        """Process one event; emit observations on MATCH_TICK.

        Non-MATCH_TICK events are ignored (returns current state unchanged).
        """
        if event.match_id != self._match_id:
            # Silently ignore cross-match events (replay may interleave).
            return self._state

        if event.event_type == SOEventType.MATCH_TICK:
            self._process_tick(event.tick)

        return self._state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_tick(self, tick: int) -> None:
        state = self._state
        rng = MatchRng(match_seed=state.seed)
        all_mechs = list(state.mech_states.values())

        for observer in all_mechs:
            if not observer.alive or not observer.pilot_alive:
                continue
            if observer.sensor_dropout_ticks_remaining > 0:
                continue
            if not observer.sensor_ids:
                continue

            opponents = [m for m in all_mechs if m.mech_id != observer.mech_id]

            for sensor_id in observer.sensor_ids:
                spec = self._sensor_specs.get(sensor_id)
                if spec is None:
                    continue

                for target in opponents:
                    self._maybe_emit_observation(
                        observer=observer,
                        target=target,
                        sensor_id=sensor_id,
                        spec=spec,
                        tick=tick,
                        rng=rng,
                    )

    def _maybe_emit_observation(
        self,
        observer: ModelSOMechRuntimeState,
        target: ModelSOMechRuntimeState,
        sensor_id: str,
        spec: ModelSOSensorSpec,
        tick: int,
        rng: MatchRng,
    ) -> None:
        true_distance = _chebyshev(observer.position, target.position)
        if true_distance > spec.range:
            return  # out of range — no observation

        # Deterministic noise: stddev = 1 - precision
        stddev = 1.0 - spec.precision
        r = rng.for_event(tick=tick, mech_id=sensor_id, kind="sensor_noise")
        noise = r.gauss(0.0, stddev) if stddev > 0.0 else 0.0
        distance_estimate = max(0.0, float(true_distance) + noise)

        # Confidence = precision * (1 - jamming_intensity), clamped to [0, 1]
        confidence = _clamp(spec.precision * (1.0 - observer.jamming_intensity), 0.0, 1.0)

        payload: dict[str, Any] = {
            "enemy_mech_id": target.mech_id,
            "distance_estimate": distance_estimate,
            "confidence": confidence,
        }

        # Sensor-type extras.
        sensor_id_lower = sensor_id.lower()
        if _THERMAL_SUFFIX in sensor_id_lower:
            if target.boiler.heat_current >= _THERMAL_HEAT_THRESHOLD:
                payload["heat_estimate"] = float(target.boiler.heat_current)
        if _ACOUSTIC_SUFFIX in sensor_id_lower:
            if target.speed >= _ACOUSTIC_SPEED_THRESHOLD:
                payload["mode_estimate"] = target.current_mode

        self._emit(
            self._events.make(
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,  # bus re-stamps if wired through InProcessEventBus
                event_type=SOEventType.SENSOR_OBSERVATION,
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(
                    mech_id=observer.mech_id,
                    player_id=observer.player_id,
                ),
                payload=payload,
                correlation_id=self._correlation_id,
            )
        )
