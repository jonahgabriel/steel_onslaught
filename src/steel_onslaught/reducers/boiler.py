"""Boiler/heat/pressure reducer — Task 22.

Per-tick logic:
  - MATCH_TICK: pressure += regen_per_tick (capped at maximum),
                heat -= vent_rate (floored at 0).

On-event logic:
  - WEAPON_FIRED:            pressure -= payload.pressure_cost,
                              heat += payload.heat_generated.
  - MODE_TRANSITION_STARTED: pressure -= payload.costs.pressure,
                              heat += payload.costs.heat.

Emissions after each state change:
  - BOILER_UPDATED          (always, whenever pressure or heat changes)
  - HEAT_REDLINE_ENTERED    (when heat crosses redline_threshold upward)
  - HEAT_REDLINE_EXITED     (when heat crosses redline_threshold downward)

The boiler reducer does NOT raise ReducerError for insufficient pressure on
WEAPON_FIRED — that validation belongs to the weapon reducer (Task 24), which
rejects the firing intent before the event reaches this reducer.  The boiler
reducer therefore floors pressure at 0 rather than raising.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState

_PRODUCER_NODE = "node.reducer.boiler"

# ---------------------------------------------------------------------------
# Public type alias
# ---------------------------------------------------------------------------

EmitFn = Callable[[ModelSOEventEnvelope], None]


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class ReducerBoiler:
    """Per-mech boiler reducer.  Construct one instance per (match, mech).

    Args:
        mech_id:  The mech whose boiler this reducer manages.
        correlation_id:
                  ONEX workflow correlation id shared across all events of
                  this match.
        state:    Current match state (used to initialise internal bookkeeping).
        emit:     Callable that receives produced events (e.g. bus.publish).
                  Pass a no-op lambda for replay scenarios where re-emission
                  is not desired.
    """

    def __init__(
        self,
        mech_id: str,
        state: ModelSOMatchState,
        emit: EmitFn,
        *,
        correlation_id: UUID,
        event_factory: EventFactory,
    ) -> None:
        self._mech_id = mech_id
        self._correlation_id = correlation_id
        self._events = event_factory
        self._emit = emit
        # Capture the initial redline flag from the current boiler state so we
        # can detect upward/downward threshold crossings correctly.
        boiler = state.mech_states[mech_id].boiler
        self._was_redline: bool = boiler.status_redline

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def apply(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
    ) -> ModelSOMatchState:
        """Fold one event into match state; return updated state.

        Non-boiler events for this mech are silently ignored (they may belong
        to other reducers in the chain).  Events for *other* mechs are also
        silently ignored.
        """
        mech = state.mech_states.get(self._mech_id)
        if mech is None:
            return state  # mech not yet spawned or wrong match

        match event.event_type:
            case SOEventType.MATCH_TICK:
                return self._apply_tick(event, state, mech)
            case SOEventType.WEAPON_FIRED:
                if event.subject.mech_id == self._mech_id:
                    return self._apply_weapon_fired(event, state, mech)
            case SOEventType.MODE_TRANSITION_STARTED:
                if event.subject.mech_id == self._mech_id:
                    return self._apply_mode_transition_started(event, state, mech)

        return state  # unrelated event

    # ------------------------------------------------------------------
    # Event application helpers
    # ------------------------------------------------------------------

    def _apply_tick(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> ModelSOMatchState:
        """MATCH_TICK: regen pressure, vent heat."""
        boiler = mech.boiler

        new_pressure = min(
            boiler.pressure_current + boiler.regeneration_per_tick,
            boiler.pressure_maximum,
        )
        new_heat = max(boiler.heat_current - boiler.heat_vent_rate, 0)

        return self._commit(event, state, mech, boiler, new_pressure, new_heat)

    def _apply_weapon_fired(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> ModelSOMatchState:
        """WEAPON_FIRED: deduct pressure cost, add heat."""
        boiler = mech.boiler
        pressure_cost: int = int(event.payload.get("pressure_cost", 0))
        heat_generated: int = int(event.payload.get("heat_generated", 0))

        new_pressure = max(boiler.pressure_current - pressure_cost, 0)
        # heat is capped at rupture_threshold by the boiler state validator;
        # we floor here; the validator prevents us from exceeding rupture.
        new_heat = min(
            boiler.heat_current + heat_generated,
            boiler.heat_rupture_threshold,
        )

        return self._commit(event, state, mech, boiler, new_pressure, new_heat)

    def _apply_mode_transition_started(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> ModelSOMatchState:
        """MODE_TRANSITION_STARTED: deduct pressure and add heat from costs."""
        boiler = mech.boiler
        costs: dict[str, Any] = event.payload.get("costs", {})
        pressure_cost: int = int(costs.get("pressure", 0))
        heat_cost: int = int(costs.get("heat", 0))

        new_pressure = max(boiler.pressure_current - pressure_cost, 0)
        new_heat = min(
            boiler.heat_current + heat_cost,
            boiler.heat_rupture_threshold,
        )

        return self._commit(event, state, mech, boiler, new_pressure, new_heat)

    # ------------------------------------------------------------------
    # Core commit: build new state, emit events
    # ------------------------------------------------------------------

    def _commit(
        self,
        triggering_event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
        old_boiler: ModelSOBoilerState,
        new_pressure: int,
        new_heat: int,
    ) -> ModelSOMatchState:
        """Persist the new pressure/heat, emit derived events, return new state."""
        # Determine redline status after change.
        now_redline = new_heat >= old_boiler.heat_redline_threshold

        new_boiler = ModelSOBoilerState(
            match_id=old_boiler.match_id,
            mech_id=old_boiler.mech_id,
            tick=triggering_event.tick,
            pressure_current=new_pressure,
            pressure_maximum=old_boiler.pressure_maximum,
            regeneration_per_tick=old_boiler.regeneration_per_tick,
            heat_current=new_heat,
            heat_redline_threshold=old_boiler.heat_redline_threshold,
            heat_rupture_threshold=old_boiler.heat_rupture_threshold,
            heat_vent_rate=old_boiler.heat_vent_rate,
            status_redline=now_redline,
            status_rupture_warning=old_boiler.status_rupture_warning,
            status_disabled=old_boiler.status_disabled,
            status_ruptured=old_boiler.status_ruptured,
            modifier_heat_weapon_pressure=old_boiler.modifier_heat_weapon_pressure,
            modifier_venting_penalty=old_boiler.modifier_venting_penalty,
            modifier_mode_switch_heat_delta=old_boiler.modifier_mode_switch_heat_delta,
        )

        new_mech = mech.model_copy(update={"boiler": new_boiler})
        new_mech_states = {**state.mech_states, self._mech_id: new_mech}
        new_state = state.model_copy(update={"mech_states": new_mech_states})

        subject = ModelSOEventSubject(
            mech_id=self._mech_id,
            player_id=mech.player_id,
        )

        # Emit BOILER_UPDATED whenever pressure or heat changed.
        if new_pressure != old_boiler.pressure_current or new_heat != old_boiler.heat_current:
            self._emit(
                _make_env(
                    event_factory=self._events,
                    match_id=state.match_id,
                    correlation_id=self._correlation_id,
                    tick=triggering_event.tick,
                    event_type=SOEventType.BOILER_UPDATED,
                    subject=subject,
                    payload={
                        "pressure_before": old_boiler.pressure_current,
                        "pressure_after": new_pressure,
                        "heat_before": old_boiler.heat_current,
                        "heat_after": new_heat,
                    },
                )
            )

        # Emit HEAT_REDLINE_ENTERED / HEAT_REDLINE_EXITED on threshold crossings.
        was_redline = self._was_redline
        if not was_redline and now_redline:
            self._emit(
                _make_env(
                    event_factory=self._events,
                    match_id=state.match_id,
                    correlation_id=self._correlation_id,
                    tick=triggering_event.tick,
                    event_type=SOEventType.HEAT_REDLINE_ENTERED,
                    subject=subject,
                    payload={
                        "heat": new_heat,
                        "redline_threshold": old_boiler.heat_redline_threshold,
                    },
                )
            )
        elif was_redline and not now_redline:
            self._emit(
                _make_env(
                    event_factory=self._events,
                    match_id=state.match_id,
                    correlation_id=self._correlation_id,
                    tick=triggering_event.tick,
                    event_type=SOEventType.HEAT_REDLINE_EXITED,
                    subject=subject,
                    payload={
                        "heat": new_heat,
                        "redline_threshold": old_boiler.heat_redline_threshold,
                    },
                )
            )

        # Update cached redline flag.
        self._was_redline = now_redline

        return new_state


# ---------------------------------------------------------------------------
# Envelope factory
# ---------------------------------------------------------------------------


def _make_env(
    *,
    event_factory: EventFactory,
    match_id: str,
    correlation_id: UUID,
    tick: int,
    event_type: SOEventType,
    subject: ModelSOEventSubject,
    payload: dict[str, Any],
) -> ModelSOEventEnvelope:
    return event_factory.make(
        match_id=match_id,
        correlation_id=correlation_id,
        tick=tick,
        sequence_in_tick=0,  # bus reassigns on publish
        event_type=event_type,
        producer_node=_PRODUCER_NODE,
        subject=subject,
        payload=payload,
    )
