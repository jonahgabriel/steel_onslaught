"""Failure cascade reducer — Task 26.

Cascade ladder (deterministic order, per living mech per ``MATCH_TICK``):

1. Heat >= redline_threshold — ``HEAT_REDLINE_ENTERED`` is owned by the boiler
   reducer (Task 22); this reducer only *counts* consecutive redline ticks.
2. Sustained redline (``OVERLOAD_REDLINE_TICKS`` = 3+ consecutive ticks)
   -> emit ``BOILER_OVERLOADED``.  Effects: ``accuracy_penalty_next_fire`` set
   to 0.2 (-20% accuracy on the next firing, applied by the weapon reducer)
   and mode switching disabled for 3 ticks (enforced by the mode reducer via
   ``mode_switch_disabled_until``).
3. Heat >= rupture_threshold OR sustained overload (``RUPTURE_OVERLOAD_TICKS``
   = 5+ overloaded ticks) -> emit ``BOILER_RUPTURED``.  Effects: the rupturing
   mech takes ``RUPTURE_DIRECT_DAMAGE`` (30) hp, and every other living mech
   within ``RUPTURE_AREA_RADIUS_CELLS`` (3, Chebyshev) takes
   ``RUPTURE_AREA_DAMAGE``.  Rupture is terminal (design §10.4): the rupturing
   mech is always destroyed, which is what guarantees the plan invariant that
   a rupture at tick N yields ``VICTORY_DECLARED`` at tick N when no other
   mechs remain.
4. On rupture: pilot rupture-survival roll with probability
   ``0.5 + 0.2 * <emergency safety gizmos equipped>`` (clamped to 1.0), rolled
   via ``MatchRng.for_event(tick, mech_id, "rupture_survival")``.  On fail:
   emit ``PILOT_KILLED``.
5. ``MECH_DESTROYED`` (from rupture or from cumulative damage): the mech's
   ``alive`` flag drops, removing it from ``surviving_player_ids`` /
   ``living_mechs`` so subsequent ticks skip its pilot decision.  Externally
   produced ``MECH_DESTROYED`` / ``PILOT_KILLED`` events are folded
   idempotently so the reducer's own loop-back emissions are no-ops.
6. If exactly one player has surviving mechs after a change: emit
   ``VICTORY_DECLARED(winner_player_id, reason="last_mech_standing")``.  If the
   same pass leaves ZERO survivors (a rupture always destroys its own mech and
   its area damage can finish the last opponent in the same pass): emit
   ``MATCH_ENDED(reason="draw_mutual_destruction")``.  Emitting nothing on the
   zero-survivor transition used to leave the match RUNNING with an empty
   arena.

Exit rule (documented decision — the plan specifies entry thresholds only):
dropping below the redline threshold resets the whole ladder — the redline
counter zeroes and overload clears.  Area damage bypasses armor (rupture is an
internal explosion, not a weapon hit).

Replay determinism: all bookkeeping (redline/overload counters, flags) lives
on ``ModelSOMechRuntimeState``; all randomness goes through ``MatchRng`` seeded
from ``state.seed``.  State changes are applied inline before emission, so a
bus-less replay (``emit`` = no-op) reaches the identical final state from the
same event sequence.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any
from uuid import UUID

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMechDestroyedPayload,
    ModelSOPilotKilledPayload,
)
from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import ModelSOPosition

_PRODUCER_NODE = "node.reducer.failure"

# Match-scoped terminals (VICTORY_DECLARED, MATCH_ENDED) carry the wildcard
# subject, mirroring the lifecycle reducer's convention.
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# ---------------------------------------------------------------------------
# Cascade constants (plan Task 26)
# ---------------------------------------------------------------------------

OVERLOAD_REDLINE_TICKS = 3
"""Consecutive redline ticks required to trip BOILER_OVERLOADED."""

OVERLOAD_ACCURACY_PENALTY = 0.2
"""Multiplicative accuracy penalty applied to the next weapon firing."""

OVERLOAD_MODE_SWITCH_DISABLED_TICKS = 3
"""Ticks mode switching stays disabled after overload."""

RUPTURE_OVERLOAD_TICKS = 5
"""Consecutive overloaded ticks required to trip BOILER_RUPTURED."""

RUPTURE_DIRECT_DAMAGE = 30
"""Hp damage the rupturing mech takes from its own boiler."""

RUPTURE_AREA_DAMAGE = 15
"""Hp damage dealt to every other mech within the blast radius (the plan
fixes the radius but not the magnitude; half the direct damage is the chosen
value)."""

RUPTURE_AREA_RADIUS_CELLS = 3
"""Chebyshev blast radius of a boiler rupture, in grid cells."""

RUPTURE_SURVIVAL_BASE = 0.5
"""Base pilot rupture-survival probability."""

RUPTURE_SURVIVAL_PER_SAFETY_GIZMO = 0.2
"""Survival probability bonus per equipped emergency safety gizmo."""


# ---------------------------------------------------------------------------
# Cause enums
# ---------------------------------------------------------------------------


class SORuptureCause(StrEnum):
    """Why a boiler ruptured (BOILER_RUPTURED payload ``cause``)."""

    HEAT_THRESHOLD = "heat_threshold"
    SUSTAINED_OVERLOAD = "sustained_overload"


class SODestructionCause(StrEnum):
    """Why a mech was destroyed by this reducer (MECH_DESTROYED ``cause``)."""

    BOILER_RUPTURE = "boiler_rupture"
    RUPTURE_AREA_DAMAGE = "rupture_area_damage"


# ---------------------------------------------------------------------------
# Public type alias
# ---------------------------------------------------------------------------

EmitFn = Callable[[ModelSOEventEnvelope], None]


def _chebyshev(a: ModelSOPosition, b: ModelSOPosition) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class ReducerFailureCascade:
    """Per-match failure cascade reducer.

    Args:
        match_id:         Owning match identifier; events for other matches
                          are silently ignored.
        correlation_id:   ONEX workflow correlation id shared across all events
                          of this match.
        emit:             Callable receiving produced events (e.g.
                          bus.publish).  Pass a no-op for replay.
        safety_gizmo_ids: Gizmo ids that count as *emergency safety* gizmos
                          for the rupture-survival roll (resolved by the match
                          runner from gizmo specs with ``category=safety``).
    """

    def __init__(
        self,
        match_id: str,
        correlation_id: UUID,
        *,
        emit: EmitFn,
        event_factory: EventFactory,
        safety_gizmo_ids: frozenset[str],
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._emit = emit
        self._events = event_factory
        self._safety_gizmo_ids = safety_gizmo_ids

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def apply(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
    ) -> ModelSOMatchState:
        """Fold one event into match state; return the updated state.

        Handles ``MATCH_TICK`` (cascade evaluation) and folds externally
        produced ``MECH_DESTROYED`` / ``PILOT_KILLED`` idempotently.  All
        other events — and events for other matches — are ignored.
        """
        if event.match_id != self._match_id:
            return state

        match event.event_type:
            case SOEventType.MATCH_TICK:
                ModelSOEmptyPayload.model_validate(event.payload)
                return self._apply_tick(event, state)
            case SOEventType.MECH_DESTROYED:
                ModelSOMechDestroyedPayload.model_validate(event.payload)
                return self._fold_flag(event, state, field="alive")
            case SOEventType.PILOT_KILLED:
                ModelSOPilotKilledPayload.model_validate(event.payload)
                return self._fold_flag(event, state, field="pilot_alive")
            case _:
                return state

    # ------------------------------------------------------------------
    # MATCH_TICK cascade
    # ------------------------------------------------------------------

    def _apply_tick(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
    ) -> ModelSOMatchState:
        if state.status is not SOMatchStatus.RUNNING:
            return state

        survivors_before = state.surviving_player_ids()
        working = dict(state.mech_states)

        # Snapshot of ids — deterministic insertion order from MATCH_STARTED.
        for mech_id in list(working):
            if not working[mech_id].alive:
                continue  # destroyed mechs (incl. earlier in this tick) skip
            self._cascade_mech(event, state.seed, working, mech_id)

        new_state = state.evolve(update={"mech_states": working})
        self._maybe_declare_terminal(event, survivors_before, new_state)
        return new_state

    def _cascade_mech(
        self,
        event: ModelSOEventEnvelope,
        seed: int,
        working: dict[str, ModelSOMechRuntimeState],
        mech_id: str,
    ) -> None:
        """Run the ladder for one living mech: counters -> overload -> rupture."""
        mech = working[mech_id]
        boiler = mech.boiler

        if boiler.heat_current < boiler.heat_redline_threshold:
            # Below redline: the whole ladder resets (documented exit rule).
            if (
                mech.redline_consecutive_ticks
                or mech.overloaded
                or mech.overloaded_consecutive_ticks
            ):
                working[mech_id] = mech.evolve(
                    update={
                        "redline_consecutive_ticks": 0,
                        "overloaded": False,
                        "overloaded_consecutive_ticks": 0,
                    }
                )
            return  # heat < redline < rupture: no rupture possible this tick

        # --- Step 1: redline counting (event emission owned by Task 22). ---
        redline_ticks = mech.redline_consecutive_ticks + 1
        updates: dict[str, Any] = {"redline_consecutive_ticks": redline_ticks}

        # --- Step 2: overload. ---
        if mech.overloaded:
            updates["overloaded_consecutive_ticks"] = mech.overloaded_consecutive_ticks + 1
        elif redline_ticks >= OVERLOAD_REDLINE_TICKS:
            disabled_until = event.tick + OVERLOAD_MODE_SWITCH_DISABLED_TICKS
            updates.update(
                {
                    "overloaded": True,
                    "overloaded_consecutive_ticks": 1,
                    "accuracy_penalty_next_fire": OVERLOAD_ACCURACY_PENALTY,
                    "mode_switch_disabled_until": disabled_until,
                }
            )
            self._emit_event(
                event.tick,
                SOEventType.BOILER_OVERLOADED,
                subject=ModelSOEventSubject(mech_id=mech_id, player_id=mech.player_id),
                payload={
                    "heat": boiler.heat_current,
                    "redline_threshold": boiler.heat_redline_threshold,
                    "redline_consecutive_ticks": redline_ticks,
                    "accuracy_penalty_next_fire": OVERLOAD_ACCURACY_PENALTY,
                    "mode_switch_disabled_until": disabled_until,
                },
            )

        mech = mech.evolve(update=updates)
        working[mech_id] = mech

        # --- Step 3: rupture. ---
        heat_rupture = boiler.heat_current >= boiler.heat_rupture_threshold
        overload_rupture = mech.overloaded_consecutive_ticks >= RUPTURE_OVERLOAD_TICKS
        if not (heat_rupture or overload_rupture):
            return

        cause = SORuptureCause.HEAT_THRESHOLD if heat_rupture else SORuptureCause.SUSTAINED_OVERLOAD
        self._rupture(event, seed, working, mech_id, cause)

    # ------------------------------------------------------------------
    # Rupture resolution
    # ------------------------------------------------------------------

    def _rupture(
        self,
        event: ModelSOEventEnvelope,
        seed: int,
        working: dict[str, ModelSOMechRuntimeState],
        mech_id: str,
        cause: SORuptureCause,
    ) -> None:
        mech = working[mech_id]
        subject = ModelSOEventSubject(mech_id=mech_id, player_id=mech.player_id)

        self._emit_event(
            event.tick,
            SOEventType.BOILER_RUPTURED,
            subject=subject,
            payload={
                "cause": cause.value,
                "heat": mech.boiler.heat_current,
                "rupture_threshold": mech.boiler.heat_rupture_threshold,
                "direct_damage": RUPTURE_DIRECT_DAMAGE,
                "area_damage": RUPTURE_AREA_DAMAGE,
                "area_radius_cells": RUPTURE_AREA_RADIUS_CELLS,
            },
        )

        # Step 3 effects: direct hp damage to the rupturing mech.
        hp_after = max(0, mech.hp - RUPTURE_DIRECT_DAMAGE)
        self._emit_event(
            event.tick,
            SOEventType.DAMAGE_APPLIED,
            subject=subject,
            payload={
                "target_id": mech_id,
                "damage": RUPTURE_DIRECT_DAMAGE,
                "cause": SODestructionCause.BOILER_RUPTURE.value,
                "hp_after": hp_after,
            },
        )

        # Step 4: pilot rupture-survival roll (deterministic via MatchRng).
        safety_count = sum(1 for gid in mech.gizmo_ids if gid in self._safety_gizmo_ids)
        probability = min(
            1.0, RUPTURE_SURVIVAL_BASE + RUPTURE_SURVIVAL_PER_SAFETY_GIZMO * safety_count
        )
        roll = (
            MatchRng(match_seed=seed)
            .for_event(tick=event.tick, mech_id=mech_id, kind="rupture_survival")
            .random()
        )
        pilot_alive = mech.pilot_alive
        if roll >= probability:
            pilot_alive = False
            self._emit_event(
                event.tick,
                SOEventType.PILOT_KILLED,
                subject=subject,
                payload={
                    "mech_id": mech_id,
                    "survival_probability": probability,
                    "roll": roll,
                    "safety_gizmos_equipped": safety_count,
                },
            )

        # Step 5: rupture is terminal — destroy the mech unconditionally.
        ruptured_boiler = mech.boiler.evolve(
            update={
                "tick": event.tick,
                "status_ruptured": True,
                "status_disabled": True,
            }
        )
        working[mech_id] = mech.evolve(
            update={
                "hp": hp_after,
                "alive": False,
                "pilot_alive": pilot_alive,
                "boiler": ruptured_boiler,
            }
        )
        self._emit_event(
            event.tick,
            SOEventType.MECH_DESTROYED,
            subject=subject,
            payload={"cause": SODestructionCause.BOILER_RUPTURE.value},
        )

        # Area damage to every other living mech within the blast radius.
        # Bypasses armor: a rupture is an internal explosion, not a weapon hit.
        for other_id, other in list(working.items()):
            if other_id == mech_id or not other.alive:
                continue
            if _chebyshev(mech.position, other.position) > RUPTURE_AREA_RADIUS_CELLS:
                continue

            other_subject = ModelSOEventSubject(mech_id=other_id, player_id=other.player_id)
            other_hp = max(0, other.hp - RUPTURE_AREA_DAMAGE)
            destroyed = other_hp <= 0
            self._emit_event(
                event.tick,
                SOEventType.DAMAGE_APPLIED,
                subject=other_subject,
                payload={
                    "target_id": other_id,
                    "damage": RUPTURE_AREA_DAMAGE,
                    "cause": SODestructionCause.RUPTURE_AREA_DAMAGE.value,
                    "source_mech_id": mech_id,
                    "radius_cells": RUPTURE_AREA_RADIUS_CELLS,
                    "hp_after": other_hp,
                },
            )
            working[other_id] = other.evolve(update={"hp": other_hp, "alive": not destroyed})
            if destroyed:
                self._emit_event(
                    event.tick,
                    SOEventType.MECH_DESTROYED,
                    subject=other_subject,
                    payload={
                        "cause": SODestructionCause.RUPTURE_AREA_DAMAGE.value,
                        "source_mech_id": mech_id,
                    },
                )

    # ------------------------------------------------------------------
    # Folding externally produced death events (idempotent)
    # ------------------------------------------------------------------

    def _fold_flag(
        self,
        event: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        *,
        field: str,
    ) -> ModelSOMatchState:
        """Drop ``alive`` / ``pilot_alive`` for the subject mech, idempotently.

        Covers MECH_DESTROYED from the damage reducer (Task 25, cumulative
        damage) and loop-backs of this reducer's own emissions.  The victory
        check runs only on an actual transition, so re-folds never duplicate
        VICTORY_DECLARED.
        """
        mech = state.mech_states.get(event.subject.mech_id)
        if mech is None or getattr(mech, field) is False:
            return state  # unknown mech or already folded — no-op

        survivors_before = state.surviving_player_ids()
        new_mech = mech.evolve(update={field: False})
        new_state = state.evolve(
            update={"mech_states": {**state.mech_states, mech.mech_id: new_mech}}
        )
        self._maybe_declare_terminal(event, survivors_before, new_state)
        return new_state

    # ------------------------------------------------------------------
    # Terminal declaration (victory OR mutual-destruction draw)
    # ------------------------------------------------------------------

    def _maybe_declare_terminal(
        self,
        event: ModelSOEventEnvelope,
        survivors_before: frozenset[str],
        new_state: ModelSOMatchState,
    ) -> None:
        """Emit the terminal event for whichever survivor transition occurred.

        Two transitions are terminal:
          - ``>1 -> ==1``: ``VICTORY_DECLARED`` for the last player standing;
          - ``>=1 -> ==0``: ``MATCH_ENDED(draw_mutual_destruction)``.  A rupture
            takes its own mech unconditionally AND deals area damage, so a
            single cascade pass can go 2 -> 0.  Emitting nothing there left the
            match RUNNING with no survivors, and the runner then published
            empty ticks forever.

        The already-RUNNING guard, not the predecessor count, is what keeps
        re-folds and already-decided states from duplicating a declaration —
        a per-event fold walks ``2 -> 1 -> 0`` and would otherwise skip the
        draw entirely.

        Defense-in-depth: ``MatchStateFold._on_flag_drop`` (in ``match/fold.py``)
        declares the same terminals on the same transitions.  This
        cascade-level declaration fires when the kill arrives via the rupture
        chain; the fold-level one is the backstop for kills arriving as direct
        MECH_DESTROYED events.  The paired redundancy is intentional — see
        ``tests/match/test_fold_victory_backstop.py``.
        """
        if new_state.status is not SOMatchStatus.RUNNING:
            return  # a terminal is already recorded; never re-declare one
        survivors_after = new_state.surviving_player_ids()
        if not survivors_before:
            return
        if not survivors_after:
            self._emit_event(
                event.tick,
                SOEventType.MATCH_ENDED,
                subject=_MATCH_SUBJECT,
                payload={
                    "reason": SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION.value,
                    "winner_id": None,
                },
            )
            return
        if len(survivors_before) > 1 and len(survivors_after) == 1:
            winner = next(iter(survivors_after))
            self._emit_event(
                event.tick,
                SOEventType.VICTORY_DECLARED,
                subject=_MATCH_SUBJECT,
                payload={
                    "winner_player_id": winner,
                    "reason": SOMatchEndReason.LAST_MECH_STANDING.value,
                    "victory_kind": "elimination",
                },
            )

    # ------------------------------------------------------------------
    # Envelope factory
    # ------------------------------------------------------------------

    def _emit_event(
        self,
        tick: int,
        event_type: SOEventType,
        *,
        subject: ModelSOEventSubject,
        payload: dict[str, Any],
    ) -> None:
        self._emit(
            self._events.make(
                match_id=self._match_id,
                correlation_id=self._correlation_id,
                tick=tick,
                sequence_in_tick=0,  # bus reassigns on publish
                event_type=event_type,
                producer_node=_PRODUCER_NODE,
                subject=subject,
                payload=payload,
            )
        )
