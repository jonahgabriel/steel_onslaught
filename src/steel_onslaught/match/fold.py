"""Canonical match-state fold — Task 34.

``MatchStateFold`` is the SINGLE deterministic function from the canonical
event stream to ``ModelSOMatchState``.  The live match runner (Task 28/34)
and the replay engine (Task 27) both fold events through this class, which is
what makes ``replay.reconstruct_at_tick(final) == live_state`` hold by
construction (R9 / Architectural Decision #6).

Design rules
------------
1. State changes are derived ONLY from canonical resolved events
   (``MATCH_STARTED``, ``MATCH_TICK``, ``MOVEMENT_RESOLVED``,
   ``WEAPON_FIRED``, ``MODE_TRANSITION_STARTED``, ``DAMAGE_APPLIED``,
   ``MECH_DESTROYED``, ``PILOT_KILLED``, terminal events).  Intent events are
   telemetry: the live resolver in ``match/runner.py`` validates them and
   publishes the resolved events; the fold never re-validates intents.
2. Commit-then-emit: every event the fold itself produces (boiler updates,
   mode-transition completions, the failure cascade, victory declarations) is
   buffered, the state delta is committed first, and the buffer is published
   afterwards (live path only; on replay ``bus=None`` suppresses emission and
   the same events arrive from the ledger as idempotent re-statements).
3. All stochastic inputs (rupture survival rolls) flow through ``MatchRng``
   sub-seeds, so the fold is a pure function of ``(seed, event stream)``.

Sub-reducers composed per ``MATCH_TICK`` (after the lifecycle fold, only
while the match is still RUNNING):
  a. boiler regen / vent per mech (Task 22),
  b. weapon-cooldown + sensor-dropout countdowns,
  c. mode-transition countdown -> completion (Task 23),
  d. failure cascade: redline -> overload -> rupture (Task 26).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import GizmoCategory, ModelSOGizmoSpec
from steel_onslaught.contracts.mode import ModelSOModeTransition
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    make_event,
)
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.reducers.boiler import ReducerBoiler
from steel_onslaught.reducers.failure import ReducerFailureCascade
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle
from steel_onslaught.reducers.mode import build_mode_transition_completed_event
from steel_onslaught.reducers.movement import ReducerMovement, mode_effective_speed

_PRODUCER_NODE = "node.match.fold"

# Match-scoped events carry the wildcard subject (lifecycle convention).
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# Resolve contracts_data/ relative to this file's package tree:
# src/steel_onslaught/match/fold.py -> project root is 4 levels up.
DEFAULT_CONTRACTS_DATA_DIR = Path(__file__).parent.parent.parent.parent / "contracts_data"


def _load_specs[ModelT: BaseModel](directory: Path, model: type[ModelT]) -> dict[str, ModelT]:
    """Load every ``*.yaml`` contract under *directory*, keyed by its ``id``."""
    index: dict[str, ModelT] = {}
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        index[str(raw["id"])] = model.model_validate(raw)
    return index


def _load_transitions(directory: Path) -> dict[tuple[str, str], ModelSOModeTransition]:
    """Load mode-transition contracts, keyed by the directed (from, to) pair."""
    index: dict[tuple[str, str], ModelSOModeTransition] = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = ModelSOModeTransition.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        index[(spec.from_mode, spec.to_mode)] = spec
    return index


class MatchContractCatalog:
    """Static contract indexes a match needs at runtime AND at replay time.

    The catalog is loaded from ``contracts_data/`` once per match (or per
    replay) — contracts are content-addressed static files, so live fold and
    replay fold see identical data.
    """

    def __init__(
        self,
        *,
        chassis: dict[str, ModelSOChassisSpec],
        boilers: dict[str, ModelSOBoilerSpec],
        sensors: dict[str, ModelSOSensorSpec],
        weapons: dict[str, ModelSOWeaponSpec],
        gizmos: dict[str, ModelSOGizmoSpec],
        transitions: dict[tuple[str, str], ModelSOModeTransition],
    ) -> None:
        self.chassis = chassis
        self.boilers = boilers
        self.sensors = sensors
        self.weapons = weapons
        self.gizmos = gizmos
        self.transitions = transitions
        self.safety_gizmo_ids: frozenset[str] = frozenset(
            gizmo_id for gizmo_id, spec in gizmos.items() if spec.category is GizmoCategory.SAFETY
        )

    @classmethod
    def load(cls, contracts_data_dir: Path | None = None) -> MatchContractCatalog:
        data_dir = (
            contracts_data_dir if contracts_data_dir is not None else DEFAULT_CONTRACTS_DATA_DIR
        )
        return cls(
            chassis=_load_specs(data_dir / "chassis", ModelSOChassisSpec),
            boilers=_load_specs(data_dir / "boilers", ModelSOBoilerSpec),
            sensors=_load_specs(data_dir / "sensors", ModelSOSensorSpec),
            weapons=_load_specs(data_dir / "weapons", ModelSOWeaponSpec),
            gizmos=_load_specs(data_dir / "gizmos", ModelSOGizmoSpec),
            transitions=_load_transitions(data_dir / "modes" / "transitions"),
        )


class MatchStateFold:
    """Fold canonical events into ``ModelSOMatchState`` (live AND replay path).

    Args:
        match_id: Owning match; events for other matches are ignored.
        correlation_id:
                  ONEX workflow correlation id shared across all events of
                  this match; threaded into every event the fold + its
                  sub-reducers produce.
        bus:      Live path: fold-produced events are published here after the
                  state delta commits.  Replay path: ``None`` (no emission —
                  the same events arrive from the ledger and fold as no-ops).
        catalog:  Static contract indexes; defaults to ``contracts_data/``
                  relative to the package tree.
    """

    def __init__(
        self,
        match_id: str,
        correlation_id: UUID | None = None,
        *,
        bus: EventBus | None = None,
        catalog: MatchContractCatalog | None = None,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id if correlation_id is not None else uuid4()
        self._bus = bus
        self._catalog = catalog if catalog is not None else MatchContractCatalog.load()
        self._lifecycle = ReducerMatchLifecycle(match_id, correlation_id, bus=bus)
        self._failure = ReducerFailureCascade(
            match_id,
            correlation_id,
            emit=self._emit,
            safety_gizmo_ids=self._catalog.safety_gizmo_ids,
        )
        self._boilers: dict[str, ReducerBoiler] = {}
        self._mech_states: dict[str, ModelSOMechRuntimeState] = {}
        # Active emission buffer; set per `apply` call (commit-then-emit).
        self._sink: list[ModelSOEventEnvelope] | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> ModelSOMatchState:
        """Composite canonical state: lifecycle authority + mech detail."""
        return self._lifecycle.state.model_copy(update={"mech_states": dict(self._mech_states)})

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """``EventHandler``-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> ModelSOMatchState:
        """Fold one canonical event; return the updated composite state."""
        if event.match_id != self._match_id:
            return self.state

        buffer: list[ModelSOEventEnvelope] = []
        outer_sink = self._sink
        self._sink = buffer
        try:
            # Lifecycle authority first: status / tick / winner / end_reason.
            # (It commits its state BEFORE any of its own terminal emissions.)
            self._lifecycle.apply(event)

            match event.event_type:
                case SOEventType.MATCH_STARTED:
                    self._on_match_started()
                case SOEventType.MATCH_TICK:
                    self._on_match_tick(event)
                case SOEventType.MOVEMENT_RESOLVED:
                    self._on_movement_resolved(event)
                case SOEventType.WEAPON_FIRED:
                    self._on_weapon_fired(event)
                case SOEventType.MODE_TRANSITION_STARTED:
                    self._on_mode_transition_started(event)
                case SOEventType.DAMAGE_APPLIED:
                    self._on_damage_applied(event)
                case SOEventType.ARMOR_ABSORBED:
                    self._on_armor_absorbed(event)
                case SOEventType.MECH_DESTROYED:
                    self._on_flag_drop(event, field="alive")
                case SOEventType.PILOT_KILLED:
                    self._on_flag_drop(event, field="pilot_alive")
                case _:
                    pass  # intents, observations, telemetry: no state delta
        finally:
            self._sink = outer_sink

        # Commit happened above; emissions go out only afterwards (live path).
        if self._bus is not None:
            for produced in buffer:
                self._bus.publish(produced)
        return self.state

    # ------------------------------------------------------------------
    # Emission sink (buffered; drained post-commit by `apply`)
    # ------------------------------------------------------------------

    def _emit(self, event: ModelSOEventEnvelope) -> None:
        if self._sink is None:
            raise RuntimeError("MatchStateFold emission outside of apply()")
        self._sink.append(event)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_match_started(self) -> None:
        self._mech_states = dict(self._lifecycle.state.mech_states)
        composite = self.state
        self._boilers = {
            mech_id: ReducerBoiler(
                mech_id, composite, emit=self._emit, correlation_id=self._correlation_id
            )
            for mech_id in self._mech_states
        }

    def _on_match_tick(self, event: ModelSOEventEnvelope) -> None:
        if self._lifecycle.state.status is not SOMatchStatus.RUNNING:
            return  # terminal tick: per-mech deltas are skipped (Task 28 semantics)

        working = self.state  # tick already advanced by the lifecycle fold
        for mech_id in list(working.mech_states):
            working = self._boilers[mech_id].apply(event, working)
        working = self._decrement_counters(working)
        working = self._regenerate_armor(working)
        working = self._advance_mode_transitions(event, working)
        working = self._failure.apply(event, working)
        self._mech_states = dict(working.mech_states)

    def _on_movement_resolved(self, event: ModelSOEventEnvelope) -> None:
        reducer = ReducerMovement(self._match_id, self.state)
        new_state = reducer.apply(event)
        self._mech_states = dict(new_state.mech_states)

    def _on_weapon_fired(self, event: ModelSOEventEnvelope) -> None:
        mech_id = event.subject.mech_id
        working = self.state
        boiler = self._boilers.get(mech_id)
        if boiler is not None:
            working = boiler.apply(event, working)
        mech = working.mech_states.get(mech_id)
        if mech is not None:
            weapon_id = str(event.payload["weapon_id"])
            spec = self._catalog.weapons.get(weapon_id)
            cooldown = spec.cooldown_ticks if spec is not None else 0
            mech = mech.model_copy(
                update={
                    "weapon_cooldowns": {**mech.weapon_cooldowns, weapon_id: cooldown},
                    # The overload penalty applies to the next firing only.
                    "accuracy_penalty_next_fire": 0.0,
                }
            )
            working = working.model_copy(
                update={"mech_states": {**working.mech_states, mech_id: mech}}
            )
        self._mech_states = dict(working.mech_states)

    def _on_mode_transition_started(self, event: ModelSOEventEnvelope) -> None:
        mech_id = event.subject.mech_id
        working = self.state
        boiler = self._boilers.get(mech_id)
        if boiler is not None:
            working = boiler.apply(event, working)  # deduct costs (Task 22 fold)
        mech = working.mech_states.get(mech_id)
        if mech is not None:
            costs = event.payload["costs"]
            mech = mech.model_copy(
                update={
                    "transition_ticks_remaining": int(costs["transition_ticks"]),
                    "transition_to_mode": str(event.payload["to_mode"]),
                    "sensor_dropout_ticks_remaining": int(event.payload["sensor_dropout_ticks"]),
                    "evasion": float(event.payload["evasion_penalty"]),
                }
            )
            working = working.model_copy(
                update={"mech_states": {**working.mech_states, mech_id: mech}}
            )
        self._mech_states = dict(working.mech_states)

    def _on_damage_applied(self, event: ModelSOEventEnvelope) -> None:
        mech = self._mech_states.get(event.subject.mech_id)
        if mech is None:
            return
        hp_after = int(event.payload["hp_after"])
        if mech.hp == hp_after:
            return  # idempotent re-statement (e.g. rupture loop-back)
        self._mech_states = {
            **self._mech_states,
            mech.mech_id: mech.model_copy(update={"hp": hp_after}),
        }

    def _on_armor_absorbed(self, event: ModelSOEventEnvelope) -> None:
        """Degrade armor_value to the post-hit value the runner computed.

        The runner computes the capped absorption and emits ``armor_after``;
        the fold applies it so canonical state tracks the degrading pool.
        Idempotent if the value is already current.
        """
        mech = self._mech_states.get(event.subject.mech_id)
        if mech is None:
            return
        armor_after = int(event.payload["armor_after"])
        if mech.armor_value == armor_after:
            return  # idempotent re-statement
        self._mech_states = {
            **self._mech_states,
            mech.mech_id: mech.model_copy(update={"armor_value": armor_after}),
        }

    def _on_flag_drop(
        self,
        event: ModelSOEventEnvelope,
        *,
        field: Literal["alive", "pilot_alive"],
    ) -> None:
        """Fold MECH_DESTROYED / PILOT_KILLED; declare victory on the 2->1 transition.

        Defense-in-depth: the failure cascade (``ReducerFailureCascade._maybe_declare_victory``
        in ``reducers/failure.py``) declares victory on the same transition.  This
        fold-level declaration is the backstop that fires even on a MECH_DESTROYED
        emitted outside the cascade (e.g. a direct weapon kill).  Both are guarded
        to the >1 -> ==1 transition so they don't duplicate.  The paired
        redundancy is intentional — see ``tests/match/test_fold_victory_backstop.py``.
        """
        mech = self._mech_states.get(event.subject.mech_id)
        if mech is None:
            return
        current = mech.alive if field == "alive" else mech.pilot_alive
        if current is False:
            return  # already folded (e.g. failure-cascade loop-back) — no-op

        survivors_before = self.state.surviving_player_ids()
        self._mech_states = {
            **self._mech_states,
            mech.mech_id: mech.model_copy(update={field: False}),
        }
        survivors_after = self.state.surviving_player_ids()

        if len(survivors_before) > 1 and len(survivors_after) == 1:
            winner = next(iter(survivors_after))
            self._emit(
                make_event(
                    match_id=self._match_id,
                    correlation_id=self._correlation_id,
                    tick=event.tick,
                    sequence_in_tick=0,  # bus re-stamps
                    event_type=SOEventType.VICTORY_DECLARED,
                    producer_node=_PRODUCER_NODE,
                    subject=_MATCH_SUBJECT,
                    payload={
                        "winner_player_id": winner,
                        "reason": SOMatchEndReason.LAST_MECH_STANDING.value,
                    },
                )
            )

    # ------------------------------------------------------------------
    # Per-tick sub-steps
    # ------------------------------------------------------------------

    def _decrement_counters(self, working: ModelSOMatchState) -> ModelSOMatchState:
        """Tick down weapon cooldowns and sensor-dropout windows."""
        new_states: dict[str, ModelSOMechRuntimeState] = {}
        for mech_id, mech in working.mech_states.items():
            new_cooldowns = {
                weapon_id: max(0, ticks - 1) for weapon_id, ticks in mech.weapon_cooldowns.items()
            }
            new_dropout = max(0, mech.sensor_dropout_ticks_remaining - 1)
            if (
                new_cooldowns != mech.weapon_cooldowns
                or new_dropout != mech.sensor_dropout_ticks_remaining
            ):
                mech = mech.model_copy(
                    update={
                        "weapon_cooldowns": new_cooldowns,
                        "sensor_dropout_ticks_remaining": new_dropout,
                    }
                )
            new_states[mech_id] = mech
        return working.model_copy(update={"mech_states": new_states})

    def _regenerate_armor(self, working: ModelSOMatchState) -> ModelSOMatchState:
        """Regenerate each mech's armor_value toward armor_max (degrading-armor model).

        The regen rate is chassis-driven (``base_armor_regen``). Armor that is
        already at max is untouched. A dead mech does not regenerate.
        """
        new_states: dict[str, ModelSOMechRuntimeState] = {}
        changed = False
        for mech_id, mech in working.mech_states.items():
            if not mech.alive or mech.armor_value >= mech.armor_max:
                new_states[mech_id] = mech
                continue
            chassis = self._catalog.chassis.get(mech.chassis_id)
            regen = chassis.constraints.base_armor_regen if chassis is not None else 0
            new_armor = min(mech.armor_max, mech.armor_value + regen)
            if new_armor == mech.armor_value:
                new_states[mech_id] = mech
                continue
            changed = True
            new_states[mech_id] = mech.model_copy(update={"armor_value": new_armor})
        return working.model_copy(update={"mech_states": new_states}) if changed else working

    def _advance_mode_transitions(
        self, event: ModelSOEventEnvelope, working: ModelSOMatchState
    ) -> ModelSOMatchState:
        """Count down in-flight mode transitions; complete those reaching 0.

        Completion is folded here (deterministically from MATCH_TICK + the
        static transitions index); MODE_TRANSITION_COMPLETED is emitted as
        telemetry post-commit and is NOT itself folded.
        """
        new_states: dict[str, ModelSOMechRuntimeState] = dict(working.mech_states)
        for mech_id, mech in working.mech_states.items():
            if mech.transition_ticks_remaining <= 0:
                continue
            remaining = mech.transition_ticks_remaining - 1
            if remaining > 0:
                new_states[mech_id] = mech.model_copy(
                    update={"transition_ticks_remaining": remaining}
                )
                continue

            to_mode = mech.transition_to_mode
            if to_mode is None:  # unreachable per the paired-fields invariant
                new_states[mech_id] = mech.model_copy(update={"transition_ticks_remaining": 0})
                continue

            transition = self._catalog.transitions.get((mech.current_mode, to_mode))
            lock_ticks = (
                transition.restrictions.minimum_lock_ticks_after_switch
                if transition is not None
                else 0
            )
            lock_until = event.tick + lock_ticks
            new_states[mech_id] = mech.model_copy(
                update={
                    "current_mode": to_mode,
                    "transition_ticks_remaining": 0,
                    "transition_to_mode": None,
                    "mode_lock_until": lock_until,
                    "evasion": 0.0,  # transition vulnerability window closes
                    "speed": mode_effective_speed(mech.base_speed, to_mode),
                }
            )
            self._emit(
                build_mode_transition_completed_event(
                    match_id=self._match_id,
                    correlation_id=self._correlation_id,
                    tick=event.tick,
                    mech_id=mech_id,
                    player_id=mech.player_id,
                    from_mode=mech.current_mode,
                    new_mode=to_mode,
                    mode_lock_until=lock_until,
                )
            )
        return working.model_copy(update={"mech_states": new_states})
