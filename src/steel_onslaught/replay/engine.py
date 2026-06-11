"""Replay engine — Task 27.

Reads events from a ``SQLiteLedger`` in canonical order
``(tick ASC, sequence_in_tick ASC, event_id ASC)`` and folds them through the
same reducer stack used during live play, producing a ``ModelSOMatchState``
that is ``==`` to the live final state.

Reducers used during live play (see ``match/runner.py``):
  - ``ReducerMatchLifecycle`` — authoritative status / winner / end_reason /
    initial mech_states.  Bus is passed as ``None`` so the replay path
    produces no side-effect emissions.
  - ``ReducerBoiler`` per mech — folds MATCH_TICK, WEAPON_FIRED, and
    MODE_TRANSITION_STARTED into each mech's boiler sub-state.

Other reducers (movement, sensors, mode, pilot_tick, weapons, damage, failure)
do not mutate persisted canonical state in the current runner; their emissions
are re-read from the ledger and folded only through the two reducers above,
matching the runner's fold exactly.

API
---
``ReplayEngine`` is stateful: it tracks a ``_cursor_tick`` that is advanced by
``step_forward`` / ``step_backward`` and reset by ``reconstruct_at_tick``.

Usage::

    replay = ReplayEngine(ledger, match_id="match.2026-04-30.001")
    final  = replay.reconstruct_at_tick(200)   # fold through all events
    state3 = replay.reconstruct_at_tick(3)      # fold only through tick 3
    t4     = replay.step_forward()              # advance one tick
    t3_    = replay.step_backward()             # retreat one tick
"""

from __future__ import annotations

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.reducers.boiler import ReducerBoiler
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle


def _noop_emit(_event: ModelSOEventEnvelope) -> None:
    """No-op emit callback for replay reducers — no side effects wanted."""


class ReplayEngine:
    """Reconstruct ``ModelSOMatchState`` at any tick from a ledger.

    Args:
        ledger:   Open ``SQLiteLedger`` holding the target match's events.
        match_id: The match identifier whose events are replayed.

    The engine caches the full ordered event list on first construction to
    avoid repeated ledger scans.  The ledger is expected to be complete
    (match has ended) before replay is meaningful, though partial replays
    for running matches are supported.
    """

    def __init__(self, ledger: SQLiteLedger, match_id: str) -> None:
        self._ledger = ledger
        self._match_id = match_id
        # Cache the full canonical event list once.
        self._events: list[ModelSOEventEnvelope] = list(ledger.read_all(match_id))
        # Current cursor position — updated by reconstruct_at_tick / step_*.
        self._cursor_tick: int = 0

    # ------------------------------------------------------------------
    # Public API (matches the plan's spec)
    # ------------------------------------------------------------------

    def reconstruct_at_tick(self, tick: int) -> ModelSOMatchState:
        """Fold all events up to and including *tick* through the reducer stack.

        Sets the internal cursor to *tick* (clamped to [0, all_ticks()[-1]]).
        Returns the reconstructed ``ModelSOMatchState``.

        Args:
            tick: Target tick number (0 = initial state after MATCH_STARTED).

        Returns:
            ``ModelSOMatchState`` after folding all events with tick <= *tick*.
        """
        all_t = self.all_ticks()
        if not all_t:
            raise ValueError(f"no events for match_id={self._match_id!r}")
        clamped = max(all_t[0], min(tick, all_t[-1]))
        self._cursor_tick = clamped
        return self._fold_up_to(clamped)

    def step_forward(self) -> ModelSOMatchState:
        """Advance one tick and return the reconstructed state.

        Clamps at the final tick — if already at the end, returns the current
        (final) state unchanged.
        """
        all_t = self.all_ticks()
        if not all_t:
            raise ValueError(f"no events for match_id={self._match_id!r}")
        final_tick = all_t[-1]
        next_tick = min(self._cursor_tick + 1, final_tick)
        self._cursor_tick = next_tick
        return self._fold_up_to(next_tick)

    def step_backward(self) -> ModelSOMatchState:
        """Retreat one tick and return the reconstructed state.

        Clamps at tick 0 — if already at the start, returns the tick-0 state.
        """
        prev_tick = max(self._cursor_tick - 1, 0)
        self._cursor_tick = prev_tick
        return self._fold_up_to(prev_tick)

    def all_ticks(self) -> list[int]:
        """Return a sorted list of all distinct tick numbers in the ledger.

        Tick 0 is always present (MATCH_STARTED is emitted at tick 0 by
        ``InProcessEventBus`` before the first ``MATCH_TICK``).
        """
        seen: dict[int, None] = {}  # ordered-set via dict insertion order
        for e in self._events:
            seen[e.tick] = None
        return list(seen)

    def events_at_tick(self, tick: int) -> list[ModelSOEventEnvelope]:
        """Return all events for *tick* in canonical order
        ``(sequence_in_tick ASC, event_id ASC)``.

        Returns an empty list if *tick* is not present in the ledger.
        """
        at_tick = [e for e in self._events if e.tick == tick]
        return sorted(at_tick, key=lambda e: (e.sequence_in_tick, e.event_id))

    # ------------------------------------------------------------------
    # Internal fold implementation
    # ------------------------------------------------------------------

    def _fold_up_to(self, target_tick: int) -> ModelSOMatchState:
        """Fold events with tick <= *target_tick* through the reducer stack.

        Mirrors the runner's composition exactly:
        1. ``ReducerMatchLifecycle`` (bus=None) handles MATCH_STARTED,
           MATCH_TICK, VICTORY_DECLARED, MATCH_ENDED, and owns the
           authoritative match status / winner / end_reason / mech_states seed.
        2. ``ReducerBoiler`` (per mech, no-op emit) handles MATCH_TICK,
           WEAPON_FIRED, and MODE_TRANSITION_STARTED, updating each mech's
           boiler sub-state in the running ``state`` variable.

        Runner behaviour preserved here:
        - After ``MATCH_STARTED``, the runner initialises ``state`` and boiler
          reducers from ``lifecycle.state``.
        - On each ``MATCH_TICK``, the runner folds the lifecycle reducer first;
          if the match is still RUNNING, it then applies the boiler reducers.
          If the tick terminates the match (lifecycle transitions to ENDED),
          the runner breaks *before* calling the boiler reducers — so the
          boiler reducers are NOT applied for the terminal tick.  This replay
          engine replicates that skip.

        Returns ``lifecycle.state.model_copy(update={"mech_states": state.mech_states})``,
        which is the exact expression used by ``MatchRunner.run()``.
        """
        from steel_onslaught.match.state import SOMatchStatus

        lifecycle = ReducerMatchLifecycle(self._match_id, bus=None)

        # State variable mirrors the runner's local ``state`` — starts as
        # uninitialized; filled once MATCH_STARTED is folded.
        state: ModelSOMatchState | None = None
        # Boiler reducers are keyed by mech_id; created after MATCH_STARTED
        # populates mech_states so we can read the initial boiler status.
        boiler_reducers: dict[str, ReducerBoiler] = {}

        for event in self._events:
            if event.tick > target_tick:
                break

            # 1. Fold through lifecycle reducer.
            lifecycle.apply(event)

            # 2. After MATCH_STARTED, bootstrap the runner-equivalent state
            #    and build per-mech boiler reducers from it.
            if event.event_type is SOEventType.MATCH_STARTED and state is None:
                state = lifecycle.state
                boiler_reducers = {
                    mech_id: ReducerBoiler(mech_id, state, emit=_noop_emit)
                    for mech_id in state.mech_states
                }
                continue  # MATCH_STARTED itself carries no boiler delta

            # 3. For MATCH_TICK events, the runner applies boiler reducers only
            #    when the match is still RUNNING after the lifecycle fold.
            #    On the terminal tick the lifecycle transitions to ENDED, and the
            #    runner breaks *before* the boiler loop — so we replicate that skip.
            if event.event_type is SOEventType.MATCH_TICK:
                if lifecycle.state.status is not SOMatchStatus.RUNNING:
                    break  # terminal tick reached; boiler NOT applied (matches runner)
                if state is not None:
                    state = state.model_copy(update={"tick": event.tick})
                    for reducer in boiler_reducers.values():
                        state = reducer.apply(event, state)
                continue

            # 4. Non-MATCH_TICK, non-MATCH_STARTED events (WEAPON_FIRED, etc.)
            #    are folded through the boiler reducers just like the runner does
            #    (runner publishes to bus; boiler reducers subscribed to bus).
            if state is not None:
                for reducer in boiler_reducers.values():
                    state = reducer.apply(event, state)

        # If we never saw MATCH_STARTED, return whatever the lifecycle has
        # (will be the PENDING initial state).
        if state is None:
            return lifecycle.state

        # Mirror exactly: lifecycle owns status/winner/end_reason;
        # state.mech_states has the boiler-updated mech detail.
        return lifecycle.state.model_copy(update={"mech_states": state.mech_states})
