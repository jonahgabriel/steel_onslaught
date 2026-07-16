"""Canonical match-state fold — ONEX pure reducer (Task 34 / ONEX restructure).

``MatchStateFold`` is the SINGLE deterministic function from the canonical
event stream to ``ModelSOMatchState``.  The live match runner (Task 28/34)
and the replay engine (Task 27) both fold events through this class, which is
what makes ``replay.reconstruct_at_tick(final) == live_state`` hold by
construction (R9 / Architectural Decision #6).

ONEX reducer shape
------------------
This follows the OmniNode ``delta(state, event) -> (new_state, intents[])``
pure-reducer pattern. ``delta(event)`` is the pure state derivation — it
collects produced events (boiler updates, mode completions, victory
declarations) into an intents list and RETURNS them, never publishing.
``handle(event)`` is the effect-boundary adapter that publishes those intents
post-commit on the live bus (the only site of bus I/O). On the replay path
(``bus=None``) the intents are discarded (the same events arrive from the
ledger as idempotent re-statements).

Design rules
------------
1. State changes are derived ONLY from canonical resolved events
   (``MATCH_STARTED``, ``MATCH_TICK``, ``MOVEMENT_RESOLVED``,
   ``WEAPON_FIRED``, ``MODE_TRANSITION_STARTED``, ``DAMAGE_APPLIED``,
   ``MECH_DESTROYED``, ``PILOT_KILLED``, terminal events).  Intent events are
   telemetry: the live resolver in ``match/runner.py`` validates them and
   publishes the resolved events; the fold never re-validates intents.
2. Commit-then-return: every event the fold itself produces is buffered, the
   state delta commits first, and the buffer is RETURNED from ``delta`` (live
   path only; on replay ``bus=None`` suppresses emission and the same events
   arrive from the ledger as idempotent re-statements).
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

from typing import Literal, TypeVar
from uuid import UUID

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import GizmoCategory, ModelSOGizmoSpec
from steel_onslaught.contracts.mode import ModelSOModeTransition
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec, UnknownWeaponError
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.reducers.boiler import ReducerBoiler
from steel_onslaught.reducers.failure import ReducerFailureCascade
from steel_onslaught.reducers.lifecycle import ModelSOMatchStartedPayload, ReducerMatchLifecycle
from steel_onslaught.reducers.mode import build_mode_transition_completed_event
from steel_onslaught.reducers.movement import ReducerMovement, mode_effective_speed

_PRODUCER_NODE = "node.match.fold"

# Match-scoped events carry the wildcard subject (lifecycle convention).
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

_ContractT = TypeVar("_ContractT")
_ContractKind = Literal["chassis", "weapon", "sensor", "gizmo", "transition"]


class MissingMatchContractError(ValueError):
    """A canonical match event references absent injected contract truth."""

    def __init__(
        self,
        contract_kind: _ContractKind,
        contract_id: str,
        *,
        owner_id: str,
    ) -> None:
        self.contract_kind = contract_kind
        self.contract_id = contract_id
        self.owner_id = owner_id
        super().__init__(
            f"missing_match_contract: {contract_kind} {contract_id!r} referenced by "
            f"{owner_id!r} is absent from the injected match catalog"
        )


class MatchContractCatalog:
    """Static contract indexes a match needs at runtime AND at replay time.

    The catalog is constructed by the application composition root and
    injected explicitly. Live execution and replay must receive the same
    validated contract snapshot.
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
        catalog:  Required injected static contract indexes. The fold does
                  not discover or load contracts from the filesystem.
    """

    def __init__(
        self,
        match_id: str,
        correlation_id: UUID,
        *,
        event_factory: EventFactory,
        catalog: MatchContractCatalog,
        bus: EventBus | None = None,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._events = event_factory
        self._bus = bus
        self._catalog = catalog
        self._lifecycle = ReducerMatchLifecycle(
            match_id, correlation_id, event_factory=event_factory, bus=bus
        )
        self._failure = ReducerFailureCascade(
            match_id,
            correlation_id,
            emit=self._emit,
            event_factory=event_factory,
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
        """``EventHandler``-shaped adapter for ``EventBus.subscribe``.

        Drives ``delta`` (pure) and publishes the returned intents on the live
        bus post-commit — the single effect-boundary site for bus I/O. On the
        replay path (``bus=None``) the intents are discarded (the same events
        arrive from the ledger and re-fold as no-ops).
        """
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> ModelSOMatchState:
        """Fold one canonical event; return the updated composite state.

        Delegates to ``delta`` (the pure state derivation) and, on the live
        path, publishes the intents ``delta`` returned. This is the ONEX
        pure-reducer-as-effect pattern: state derivation is pure and returns
        intents; the effect boundary (this method, live-only) executes them.
        """
        if event.match_id != self._match_id:
            return self.state
        produced = self.delta(event)
        # Commit happened inside delta; emissions go out only afterwards (live).
        if self._bus is not None:
            for intent in produced:
                self._bus.publish(intent)
        return self.state

    def delta(self, event: ModelSOEventEnvelope) -> list[ModelSOEventEnvelope]:
        """Pure fold: derive the state delta from one event, return produced intents.

        This is the ONEX ``delta(state, event) -> (new_state, intents[])`` shape.
        It is the SINGLE deterministic function from the canonical event stream
        to ``ModelSOMatchState`` — used identically by the live runner and the
        replay engine, which is what guarantees ``replay == live`` (R9).

        Side-effect-free: produced events (boiler updates, victory declarations,
        mode completions) are collected and RETURNED, never published here.
        The live ``apply`` publishes them post-commit; replay (``bus=None``)
        discards them (they arrive from the ledger as idempotent re-statements).

        Non-deterministic inputs (clock/UUID for the produced events) flow
        through the ``make_event`` factories' injected ``emitted_at``/ids, which
        are excluded from state-level replay validity (see
        docs/plans/2026-07-02-determinism-boundaries.md).
        """
        produced: list[ModelSOEventEnvelope] = []
        outer_sink = self._sink
        self._sink = produced
        try:
            if event.event_type is SOEventType.MATCH_STARTED:
                payload = ModelSOMatchStartedPayload.model_validate(event.payload)
                self._validate_match_started_contracts(payload)

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
        return produced

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

    def _require_contract(
        self,
        contracts: dict[str, _ContractT],
        contract_kind: Literal["chassis", "weapon", "sensor", "gizmo"],
        contract_id: str,
        *,
        owner_id: str,
    ) -> _ContractT:
        try:
            return contracts[contract_id]
        except KeyError as exc:
            raise MissingMatchContractError(
                contract_kind,
                contract_id,
                owner_id=owner_id,
            ) from exc

    def _require_transition(
        self,
        from_mode: str,
        to_mode: str,
        *,
        owner_id: str,
    ) -> ModelSOModeTransition:
        try:
            return self._catalog.transitions[(from_mode, to_mode)]
        except KeyError as exc:
            raise MissingMatchContractError(
                "transition",
                f"{from_mode}->{to_mode}",
                owner_id=owner_id,
            ) from exc

    def _validate_match_started_contracts(self, payload: ModelSOMatchStartedPayload) -> None:
        """Validate every static mech reference before lifecycle state mutates."""
        for mech in payload.mechs:
            self._require_contract(
                self._catalog.chassis,
                "chassis",
                mech.chassis_id,
                owner_id=mech.mech_id,
            )
            for weapon_id in mech.weapon_cooldowns:
                self._require_contract(
                    self._catalog.weapons,
                    "weapon",
                    weapon_id,
                    owner_id=mech.mech_id,
                )
            for sensor_id in mech.sensor_ids:
                self._require_contract(
                    self._catalog.sensors,
                    "sensor",
                    sensor_id,
                    owner_id=mech.mech_id,
                )
            for gizmo_id in mech.gizmo_ids:
                self._require_contract(
                    self._catalog.gizmos,
                    "gizmo",
                    gizmo_id,
                    owner_id=mech.mech_id,
                )

    def _on_match_started(self) -> None:
        self._mech_states = dict(self._lifecycle.state.mech_states)
        composite = self.state
        self._boilers = {
            mech_id: ReducerBoiler(
                mech_id,
                composite,
                emit=self._emit,
                correlation_id=self._correlation_id,
                event_factory=self._events,
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
            if spec is None:
                raise UnknownWeaponError(weapon_id, owner_id=mech_id)
            mech = mech.model_copy(
                update={
                    "weapon_cooldowns": {
                        **mech.weapon_cooldowns,
                        weapon_id: spec.cooldown_ticks,
                    },
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
                self._events.make(
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
            chassis = self._require_contract(
                self._catalog.chassis,
                "chassis",
                mech.chassis_id,
                owner_id=mech_id,
            )
            regen = chassis.constraints.base_armor_regen
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

            transition = self._require_transition(
                mech.current_mode,
                to_mode,
                owner_id=mech_id,
            )
            lock_ticks = transition.restrictions.minimum_lock_ticks_after_switch
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
                    event_factory=self._events,
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
