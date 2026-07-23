"""Match lifecycle reducer — Task 18.

Folds MATCH_STARTED / MATCH_TICK / VICTORY_DECLARED / MATCH_ENDED into
``ModelSOMatchState``. An explicit ``max_ticks`` remains a deterministic
test/CI backstop; ``None`` leaves terminal convergence to arena pressure.

Emission vs replay
------------------
When constructed with a bus, the reducer emits the terminal events the plan
assigns to it (VICTORY_DECLARED on a single survivor at the bound; otherwise
MATCH_ENDED for a draw). The terminal state transition is
applied inline *before* emission, so a bus-less reducer (the replay path,
Task 27) reaches the identical final state from the same event sequence —
the emitted events are then idempotent re-statements when they come back
around via the bus or the ledger.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMatchEndedPayload,
    ModelSOMatchStartedPayload,
    ModelSOVictoryDeclaredPayload,
)
from steel_onslaught.match.state import (
    ModelSOMatchState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.reducers.errors import ReducerError

_PRODUCER_NODE = "node.reducer.lifecycle"

# Match-scoped events have no single mech/player subject.
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# Placeholder values for the pre-start (PENDING) state; MATCH_STARTED records
# the real seed and max_ticks from its payload.
_PENDING_SEED = 0


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class ReducerMatchLifecycle:
    """Per-match lifecycle reducer. Construct one per ``match_id``."""

    def __init__(
        self,
        match_id: str,
        correlation_id: UUID,
        *,
        event_factory: EventFactory,
        bus: EventBus | None = None,
    ) -> None:
        self._correlation_id = correlation_id
        self._events = event_factory
        self._bus = bus
        self._state = ModelSOMatchState(
            match_id=match_id,
            seed=_PENDING_SEED,
            max_ticks=None,
        )

    @property
    def state(self) -> ModelSOMatchState:
        return self._state

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """``EventHandler``-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> ModelSOMatchState:
        """Fold one event into match state; returns the (new) current state.

        Non-lifecycle events are ignored so the replay engine can feed the
        full ledger through every reducer.
        """
        if event.match_id != self._state.match_id:
            raise ReducerError(
                f"match_id_mismatch: reducer owns {self._state.match_id!r}, "
                f"event carries {event.match_id!r}"
            )
        match event.event_type:
            case SOEventType.MATCH_STARTED:
                self._apply_match_started(event)
            case SOEventType.MATCH_TICK:
                self._apply_match_tick(event)
            case SOEventType.VICTORY_DECLARED:
                self._apply_victory_declared(event)
            case SOEventType.MATCH_ENDED:
                self._apply_match_ended(event)
            case _:
                pass  # not a lifecycle event
        return self._state

    # -- event application ---------------------------------------------------

    def _apply_match_started(self, event: ModelSOEventEnvelope) -> None:
        if self._state.status is not SOMatchStatus.PENDING:
            raise ReducerError(
                f"match_already_started: match {self._state.match_id!r} is "
                f"{self._state.status.value}"
            )
        payload = ModelSOMatchStartedPayload.model_validate(event.payload)
        self._state = ModelSOMatchState(
            match_id=self._state.match_id,
            tick=0,
            status=SOMatchStatus.RUNNING,
            seed=payload.seed,
            max_ticks=payload.max_ticks,
            mech_states={mech.mech_id: mech for mech in payload.mechs},
        )

    def _apply_match_tick(self, event: ModelSOEventEnvelope) -> None:
        ModelSOEmptyPayload.model_validate(event.payload)
        state = self._state
        if state.status is not SOMatchStatus.RUNNING:
            raise ReducerError(
                f"match_not_running: MATCH_TICK on a {state.status.value} match is rejected"
            )
        expected = state.tick + 1
        if event.tick != expected:
            raise ReducerError(
                f"tick_skip: expected tick {expected}, got {event.tick} — "
                "tick increments are exactly +1"
            )

        if state.max_ticks is None or expected < state.max_ticks:
            self._state = state.model_copy(update={"tick": expected})
            return

        # Bound reached: terminate. Single surviving player -> victory;
        # otherwise a draw with no winner.  A clock ending is an ANOMALY, not
        # a gameplay outcome (Phase 4): the victory keeps its historical
        # ``last_mech_standing`` reason for fold/replay compatibility, but is
        # classified ``tick_cap_failsafe`` so terminal scorecards can tell a
        # real elimination from a match the clock had to end.
        survivors = state.surviving_player_ids()
        if len(survivors) == 1:
            winner = next(iter(survivors))
            self._end(
                tick=expected,
                winner_id=winner,
                end_reason=SOMatchEndReason.LAST_MECH_STANDING,
            )
            self._emit(
                SOEventType.VICTORY_DECLARED,
                {
                    "winner_player_id": winner,
                    "reason": SOMatchEndReason.LAST_MECH_STANDING.value,
                    "victory_kind": "tick_cap_failsafe",
                },
            )
            return

        self._end(tick=expected, winner_id=None, end_reason=SOMatchEndReason.DRAW_MAX_TICKS)
        self._emit(
            SOEventType.MATCH_ENDED,
            {"reason": SOMatchEndReason.DRAW_MAX_TICKS.value, "winner_id": None},
        )

    def _apply_victory_declared(self, event: ModelSOEventEnvelope) -> None:
        payload = ModelSOVictoryDeclaredPayload.model_validate(event.payload)
        state = self._state
        if state.status is SOMatchStatus.PENDING:
            raise ReducerError("match_not_started: VICTORY_DECLARED before MATCH_STARTED")
        if state.status is SOMatchStatus.ENDED:
            self._require_consistent_terminal(
                winner_id=payload.winner_player_id, end_reason=payload.reason
            )
            return  # idempotent re-statement
        self._end(
            tick=state.tick,
            winner_id=payload.winner_player_id,
            end_reason=payload.reason,
        )

    def _apply_match_ended(self, event: ModelSOEventEnvelope) -> None:
        payload = ModelSOMatchEndedPayload.model_validate(event.payload)
        state = self._state
        if state.status is SOMatchStatus.PENDING:
            raise ReducerError("match_not_started: MATCH_ENDED before MATCH_STARTED")
        if state.status is SOMatchStatus.ENDED:
            self._require_consistent_terminal(
                winner_id=payload.winner_id, end_reason=payload.reason
            )
            return  # idempotent re-statement for replay
        # No preceding VICTORY_DECLARED: this is a draw/abort declaration.
        self._end(tick=state.tick, winner_id=payload.winner_id, end_reason=payload.reason)

    # -- helpers ---------------------------------------------------------------

    def _end(self, tick: int, winner_id: str | None, end_reason: SOMatchEndReason) -> None:
        state = self._state
        self._state = ModelSOMatchState(
            match_id=state.match_id,
            tick=tick,
            status=SOMatchStatus.ENDED,
            seed=state.seed,
            max_ticks=state.max_ticks,
            mech_states=state.mech_states,
            winner_id=winner_id,
            end_reason=end_reason,
        )

    def _require_consistent_terminal(
        self, winner_id: str | None, end_reason: SOMatchEndReason
    ) -> None:
        state = self._state
        if state.winner_id != winner_id or state.end_reason != end_reason:
            raise ReducerError(
                "conflicting_terminal_state: match already ended with "
                f"winner={state.winner_id!r}, reason={state.end_reason!r}; "
                f"re-statement carries winner={winner_id!r}, reason={end_reason!r}"
            )

    def _emit(self, event_type: SOEventType, payload: dict[str, Any]) -> None:
        """Publish a reducer-produced event; no-op without a bus (replay path)."""
        if self._bus is None:
            return
        self._bus.publish(
            self._events.make(
                match_id=self._state.match_id,
                correlation_id=self._correlation_id,
                tick=self._state.tick,  # bus re-stamps tick + sequence_in_tick
                sequence_in_tick=0,
                event_type=event_type,
                producer_node=_PRODUCER_NODE,
                subject=_MATCH_SUBJECT,
                payload=payload,
            )
        )
