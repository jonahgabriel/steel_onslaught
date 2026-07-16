"""Mode transition reducer — Task 23.

Intent / event separation
--------------------------
The pilot emits ``MODE_SWITCH_INTENT`` (a request).  The mode reducer validates
the intent and either:

  - accepts it → emits ``MODE_TRANSITION_STARTED`` (canonical state-change event)
  - rejects it → drops the intent silently (no canonical event emitted)

``MODE_TRANSITION_STARTED`` is emitted ONLY here.  All other modules must NOT
reference that event type for emission purposes (enforced by the static scan in
``tests/reducers/test_mode.py``).

Per-tick countdown
------------------
On every ``MATCH_TICK`` event the reducer checks each mech in mid-transition.
When ``transition_ticks_remaining`` reaches 0, it emits
``MODE_TRANSITION_COMPLETED`` and finalises mech state.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.mode import ModelSOModeTransition
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState

_PRODUCER_NODE = "node.reducer.mode"


# ---------------------------------------------------------------------------
# Module-level helpers (Task 34) — shared by ReducerModeTransition (legacy
# in-place reducer), the live intent resolver in match/runner.py, and the
# canonical state fold in match/fold.py.  MODE_TRANSITION_STARTED envelopes
# are built ONLY here (enforced by the static scan in tests/reducers/test_mode.py).
# ---------------------------------------------------------------------------


def validate_mode_switch(
    mech: ModelSOMechRuntimeState,
    transition: ModelSOModeTransition,
    from_mode: str,
    current_tick: int,
) -> bool:
    """Return True iff every mode-switch validation check passes."""
    # from_mode must match the mech's actual current mode.
    if mech.current_mode != from_mode:
        return False

    # Mode lock must have expired.
    if current_tick < mech.mode_lock_until:
        return False

    # Mode switching must not be disabled (e.g. due to overload).
    if current_tick < mech.mode_switch_disabled_until:
        return False

    # Sufficient pressure.
    if mech.boiler.pressure_current < transition.costs.pressure:
        return False

    # Heat guard (strict inequality: heat must be < limit, not ==).
    heat_limit = transition.restrictions.cannot_switch_if_heat_above
    if heat_limit is not None and mech.boiler.heat_current >= heat_limit:
        return False

    # Boiler disabled guard.
    if transition.restrictions.cannot_switch_if_boiler_disabled and mech.boiler.status_disabled:
        return False

    return True


def build_mode_transition_started_event(
    *,
    event_factory: EventFactory,
    match_id: str,
    correlation_id: UUID,
    causation_id: UUID | None = None,
    tick: int,
    mech: ModelSOMechRuntimeState,
    transition: ModelSOModeTransition,
) -> ModelSOEventEnvelope:
    """Build the canonical MODE_TRANSITION_STARTED envelope for *mech*.

    *causation_id* (when set) links this event to the MODE_SWITCH_INTENT that
    triggered it — the ONEX causation chain.
    """
    return event_factory.make(
        match_id=match_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        tick=tick,
        sequence_in_tick=0,  # bus re-stamps
        event_type=SOEventType.MODE_TRANSITION_STARTED,
        producer_node=_PRODUCER_NODE,
        subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
        payload={
            "from_mode": transition.from_mode,
            "to_mode": transition.to_mode,
            "costs": {
                "pressure": transition.costs.pressure,
                "heat": transition.costs.heat,
                "transition_ticks": transition.costs.transition_ticks,
            },
            "sensor_dropout_ticks": transition.vulnerability.sensor_dropout_ticks,
            "evasion_penalty": transition.vulnerability.evasion_penalty_during_transition,
        },
    )


def build_mode_transition_completed_event(
    *,
    event_factory: EventFactory,
    match_id: str,
    correlation_id: UUID,
    tick: int,
    mech_id: str,
    player_id: str,
    from_mode: str,
    new_mode: str,
    mode_lock_until: int,
) -> ModelSOEventEnvelope:
    """Build the canonical MODE_TRANSITION_COMPLETED envelope."""
    return event_factory.make(
        match_id=match_id,
        correlation_id=correlation_id,
        tick=tick,
        sequence_in_tick=0,  # bus re-stamps
        event_type=SOEventType.MODE_TRANSITION_COMPLETED,
        producer_node=_PRODUCER_NODE,
        subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
        payload={
            "from_mode": from_mode,
            "new_mode": new_mode,
            "mode_lock_until": mode_lock_until,
        },
    )


class ReducerModeTransition:
    """Per-match mode-transition reducer.

    Parameters
    ----------
    match_id:
        Owning match identifier.
    correlation_id:
        ONEX workflow correlation id shared across all events of this match.
    transitions:
        Mapping ``(from_mode, to_mode) -> ModelSOModeTransition`` for all
        valid directed mode pairs in this match's rule set.
    bus:
        Optional event bus.  When ``None`` (replay path) the reducer still
        updates internal mech states but does not emit events.
    """

    def __init__(
        self,
        match_id: str,
        transitions: dict[tuple[str, str], ModelSOModeTransition],
        *,
        correlation_id: UUID,
        event_factory: EventFactory,
        bus: EventBus | None = None,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._events = event_factory
        self._transitions = transitions
        self._bus = bus
        # Mutable per-mech state cache, keyed by mech_id.  Seeded via
        # ``update_state`` before ``apply`` is called.
        self._mech_states: dict[str, ModelSOMechRuntimeState] = {}
        # Current match tick, updated on MATCH_TICK.
        self._current_tick: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_state(self, state: ModelSOMatchState) -> None:
        """Sync the reducer's mech-state cache from a ``ModelSOMatchState``.

        The tick counter is always updated.  Mech state follows two rules:

        * **New mechs** (ids not yet tracked internally) are seeded from
          ``state.mech_states`` — this covers match-start bootstrap and
          late-spawned mechs.
        * **Known mechs** are *not* overwritten: the mode reducer owns their
          transition bookkeeping fields.  Overwriting would reset in-flight
          ``transition_ticks_remaining`` to 0, causing stuck-transition bugs.

        The replay engine feeds events sequentially; ``update_state`` is called
        once at match-start.  The match runner calls it once before the first
        tick; subsequent ticks drive via ``apply(MATCH_TICK)``.
        """
        self._current_tick = state.tick
        for mech_id, mech in state.mech_states.items():
            if mech_id not in self._mech_states:
                self._mech_states[mech_id] = mech

    def get_mech_state(self, mech_id: str) -> ModelSOMechRuntimeState:
        """Return the current (possibly updated) mech state for *mech_id*."""
        return self._mech_states[mech_id]

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """``EventHandler``-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> None:
        """Fold one event into reducer state.

        Non-mode events (other than ``MATCH_TICK`` for the countdown) are
        ignored so the replay engine can feed the full ledger.
        """
        if event.match_id != self._match_id:
            return  # wrong match — ignore silently

        match event.event_type:
            case SOEventType.MODE_SWITCH_INTENT:
                self._handle_intent(event)
            case SOEventType.MATCH_TICK:
                self._current_tick = event.tick
                self._tick_transitions()
            case _:
                pass

    # ------------------------------------------------------------------
    # Intent handling
    # ------------------------------------------------------------------

    def _handle_intent(self, event: ModelSOEventEnvelope) -> None:
        mech_id = event.subject.mech_id
        mech = self._mech_states.get(mech_id)
        if mech is None:
            return  # unknown mech — ignore

        if not mech.alive or not mech.pilot_alive:
            return  # dead mechs cannot switch modes

        from_mode: str = event.payload.get("from_mode", "")
        to_mode: str = event.payload.get("to_mode", "")

        # Validate — all failures are silent drops (the pilot_decision_made
        # event already records the attempted mode switch with a reason code).
        transition = self._transitions.get((from_mode, to_mode))
        if transition is None:
            return  # unknown transition pair

        if not self._validate(mech, transition, from_mode):
            return  # one or more checks failed — drop silently

        # Accept: deduct costs, set transition state, emit STARTED.
        new_boiler = mech.boiler.model_copy(
            update={
                "pressure_current": mech.boiler.pressure_current - transition.costs.pressure,
                "heat_current": mech.boiler.heat_current + transition.costs.heat,
            }
        )
        new_mech = mech.model_copy(
            update={
                "boiler": new_boiler,
                "transition_ticks_remaining": transition.costs.transition_ticks,
                "transition_to_mode": to_mode,
                "sensor_dropout_ticks_remaining": transition.vulnerability.sensor_dropout_ticks,
                # Apply evasion penalty for the duration of the transition.
                "evasion": transition.vulnerability.evasion_penalty_during_transition,
            }
        )
        self._mech_states[mech_id] = new_mech

        self._emit(
            SOEventType.MODE_TRANSITION_STARTED,
            mech_id=mech_id,
            player_id=mech.player_id,
            payload={
                "from_mode": from_mode,
                "to_mode": to_mode,
                "costs": {
                    "pressure": transition.costs.pressure,
                    "heat": transition.costs.heat,
                    "transition_ticks": transition.costs.transition_ticks,
                },
                "sensor_dropout_ticks": transition.vulnerability.sensor_dropout_ticks,
                "evasion_penalty": transition.vulnerability.evasion_penalty_during_transition,
            },
        )

    def _validate(
        self,
        mech: ModelSOMechRuntimeState,
        transition: ModelSOModeTransition,
        from_mode: str,
    ) -> bool:
        """Return True iff all validation checks pass for the given intent."""
        return validate_mode_switch(mech, transition, from_mode, self._current_tick)

    # ------------------------------------------------------------------
    # Per-tick countdown
    # ------------------------------------------------------------------

    def _tick_transitions(self) -> None:
        """Decrement in-flight transition counters; complete those that reach 0."""
        for mech_id, mech in list(self._mech_states.items()):
            if mech.transition_ticks_remaining <= 0:
                continue  # not in transition

            new_ticks = mech.transition_ticks_remaining - 1
            if new_ticks > 0:
                # Still in transition — just decrement.
                self._mech_states[mech_id] = mech.model_copy(
                    update={"transition_ticks_remaining": new_ticks}
                )
                continue

            # Transition complete.
            to_mode = mech.transition_to_mode
            if to_mode is None:
                # Should never happen (paired fields invariant on ModelSOMechRuntimeState),
                # but guard defensively.
                self._mech_states[mech_id] = mech.model_copy(
                    update={"transition_ticks_remaining": 0}
                )
                continue

            # Look up the minimum_lock_ticks_after_switch for this transition.
            # We need to find the transition that was in flight.  We search by
            # (current_mode_at_start, to_mode).  Since current_mode hasn't been
            # updated yet, we check all transitions that end at to_mode — the
            # lock value is attached to the destination transition rule.
            lock_ticks = self._lock_ticks_for_completion(mech.current_mode, to_mode)

            completed_mech = mech.model_copy(
                update={
                    "current_mode": to_mode,
                    "transition_ticks_remaining": 0,
                    "transition_to_mode": None,
                    "mode_lock_until": self._current_tick + lock_ticks,
                    # Remove the evasion penalty imposed at transition start.
                    "evasion": 0.0,
                }
            )
            self._mech_states[mech_id] = completed_mech

            self._emit(
                SOEventType.MODE_TRANSITION_COMPLETED,
                mech_id=mech_id,
                player_id=mech.player_id,
                payload={
                    "from_mode": mech.current_mode,
                    "new_mode": to_mode,
                    "mode_lock_until": self._current_tick + lock_ticks,
                },
            )

    def _lock_ticks_for_completion(self, from_mode: str, to_mode: str) -> int:
        """Return ``minimum_lock_ticks_after_switch`` for the completed transition."""
        transition = self._transitions.get((from_mode, to_mode))
        if transition is None:
            return 0
        return transition.restrictions.minimum_lock_ticks_after_switch

    # ------------------------------------------------------------------
    # Emission helper
    # ------------------------------------------------------------------

    def _emit(
        self,
        event_type: SOEventType,
        *,
        mech_id: str,
        player_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            self._events.make(
                match_id=self._match_id,
                correlation_id=self._correlation_id,
                tick=self._current_tick,
                sequence_in_tick=0,  # bus re-stamps
                event_type=event_type,
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
                payload=payload,
            )
        )
