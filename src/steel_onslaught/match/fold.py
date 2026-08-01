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

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeVar
from uuid import UUID

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.arena import (
    ModelSOArenaSpec,
    ModelSOCurrentLiveArenaSnapshot,
)
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import GizmoCategory, ModelSOGizmoSpec
from steel_onslaught.contracts.incentive import ModelSOUtilityIncentive
from steel_onslaught.contracts.mode import (
    ModeId,
    ModelSOModeTransition,
    ModelSOModeTransitionStartedPayload,
)
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec, UnknownWeaponError
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import (
    ModelSOArmorAbsorbedPayload,
    ModelSODamageAppliedPayload,
    ModelSOMatchStartedPayload,
    ModelSOMechDestroyedPayload,
    ModelSOPilotKilledPayload,
    ModelSOUtilityDeployedPayload,
    ModelSOWeaponFiredPayload,
)
from steel_onslaught.immutable import freeze_mapping
from steel_onslaught.match.objectives import objective_controller
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.match.utility_effects import ModelSOUtilityEffect, expire_effects
from steel_onslaught.reducers.boiler import ReducerBoiler
from steel_onslaught.reducers.failure import ReducerFailureCascade
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle
from steel_onslaught.reducers.mode import build_mode_transition_completed_event
from steel_onslaught.reducers.movement import ReducerMovement, mode_effective_speed

_PRODUCER_NODE = "node.match.fold"

# Match-scoped events carry the wildcard subject (lifecycle convention).
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

_ContractT = TypeVar("_ContractT")
_ContractKind = Literal["arena", "chassis", "weapon", "sensor", "gizmo", "transition"]


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


class MatchContractStateMismatchError(ValueError):
    """MATCH_STARTED state disagrees with its injected contract projection."""

    def __init__(
        self,
        field: str,
        actual: object,
        expected: object,
        *,
        owner_id: str,
    ) -> None:
        self.field = field
        self.actual = actual
        self.expected = expected
        self.owner_id = owner_id
        super().__init__(
            "match_contract_state_mismatch: "
            f"{owner_id!r}.{field} is {actual!r}; injected contract truth requires {expected!r}"
        )


@dataclass(frozen=True, init=False)
class MatchContractCatalog:
    """Static contract indexes a match needs at runtime AND at replay time.

    The catalog is constructed by the application composition root and
    injected explicitly. Live execution and replay must receive the same
    validated contract snapshot.
    """

    arenas: Mapping[str, ModelSOArenaSpec]
    chassis: Mapping[str, ModelSOChassisSpec]
    boilers: Mapping[str, ModelSOBoilerSpec]
    sensors: Mapping[str, ModelSOSensorSpec]
    weapons: Mapping[str, ModelSOWeaponSpec]
    gizmos: Mapping[str, ModelSOGizmoSpec]
    transitions: Mapping[tuple[ModeId, ModeId], ModelSOModeTransition]
    safety_gizmo_ids: frozenset[str]

    def __init__(
        self,
        *,
        arenas: Mapping[str, ModelSOArenaSpec],
        chassis: Mapping[str, ModelSOChassisSpec],
        boilers: Mapping[str, ModelSOBoilerSpec],
        sensors: Mapping[str, ModelSOSensorSpec],
        weapons: Mapping[str, ModelSOWeaponSpec],
        gizmos: Mapping[str, ModelSOGizmoSpec],
        transitions: Mapping[tuple[ModeId, ModeId], ModelSOModeTransition],
    ) -> None:
        object.__setattr__(self, "arenas", MappingProxyType(dict(arenas)))
        object.__setattr__(self, "chassis", MappingProxyType(dict(chassis)))
        object.__setattr__(self, "boilers", MappingProxyType(dict(boilers)))
        object.__setattr__(self, "sensors", MappingProxyType(dict(sensors)))
        object.__setattr__(self, "weapons", MappingProxyType(dict(weapons)))
        object.__setattr__(self, "gizmos", MappingProxyType(dict(gizmos)))
        object.__setattr__(self, "transitions", MappingProxyType(dict(transitions)))
        safety_gizmo_ids = frozenset(
            gizmo_id
            for gizmo_id, spec in self.gizmos.items()
            if spec.category is GizmoCategory.SAFETY
        )
        object.__setattr__(self, "safety_gizmo_ids", safety_gizmo_ids)


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
        historical_arena_migration: ModelSOCurrentLiveArenaSnapshot | None = None,
        before_emit: Callable[[ModelSOEventEnvelope], None] | None = None,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._events = event_factory
        self._bus = bus
        self._catalog = catalog
        self._historical_arena_migration = historical_arena_migration
        self._before_emit = before_emit
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
        self._arena: ModelSOCurrentLiveArenaSnapshot | None = None
        # Per-player VP, folded deterministically from MATCH_TICK over the
        # arena's objectives (Phase 4) and — when a match records a
        # ``utility_incentive`` — from UTILITY_DEPLOYED bounties
        # (SO-UTIL-MECH).  Stays empty on objective-free arenas.
        self._vp_totals: dict[str, int] = {}
        # Deployed, still-active utility effects (Phase 2), folded from
        # UTILITY_DEPLOYED and pruned per MATCH_TICK by ``expiry_tick``.  Stays
        # empty on matches with no utility deployment (replay identity).
        self._active_utility_effects: list[ModelSOUtilityEffect] = []
        # Structural in-register utility incentive (SO-UTIL-MECH), read from
        # the MATCH_STARTED payload so the payout derives from the LEDGER and
        # replays identically.  ``None`` on every incentive-free match, which
        # makes every branch below inert and the VP derivation byte-identical
        # to the pre-incentive tree.
        self._utility_incentive: ModelSOUtilityIncentive | None = None
        # Set when a bounty was paid since the last threshold evaluation, so
        # the existing MATCH_TICK threshold check also settles a win reached
        # purely on bounty VP.  Stays False for the whole match when the
        # incentive is off.
        self._utility_bounty_unsettled = False
        # Active emission buffer; set per `apply` call (commit-then-emit).
        self._sink: list[ModelSOEventEnvelope] | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> ModelSOMatchState:
        """Composite canonical state: lifecycle authority + mech detail."""
        return self._lifecycle.state.evolve(
            update={
                "mech_states": dict(self._mech_states),
                "vp_totals": dict(self._vp_totals),
                "active_utility_effects": tuple(self._active_utility_effects),
            }
        )

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
                if self._before_emit is not None:
                    self._before_emit(intent)
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
                    self._on_match_started(payload)
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
                    ModelSOMechDestroyedPayload.model_validate(event.payload)
                    self._on_flag_drop(event, field="alive")
                case SOEventType.PILOT_KILLED:
                    ModelSOPilotKilledPayload.model_validate(event.payload)
                    self._on_flag_drop(event, field="pilot_alive")
                case SOEventType.UTILITY_DEPLOYED:
                    self._on_utility_deployed(event)
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
        contracts: Mapping[str, _ContractT],
        contract_kind: _ContractKind,
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
        from_mode: ModeId,
        to_mode: ModeId,
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
        if payload.arena.arena_id == "historical_open_field":
            expected_arena = self._historical_arena_migration
            if expected_arena is None:
                raise MissingMatchContractError(
                    "arena",
                    payload.arena.arena_id,
                    owner_id=payload.arena.arena_id,
                )
        else:
            arena = self._require_contract(
                self._catalog.arenas,
                "arena",
                payload.arena.arena_id,
                owner_id=payload.arena.arena_id,
            )
            expected_arena = arena.to_snapshot()
        if payload.arena != expected_arena:
            raise MatchContractStateMismatchError(
                "arena",
                payload.arena.model_dump(mode="json"),
                expected_arena.model_dump(mode="json"),
                owner_id=payload.arena.arena_id,
            )
        for mech in payload.mechs:
            chassis = self._require_contract(
                self._catalog.chassis,
                "chassis",
                mech.chassis_id,
                owner_id=mech.mech_id,
            )
            expected_base_speed = chassis.constraints.base_speed
            if mech.base_speed != expected_base_speed:
                raise MatchContractStateMismatchError(
                    "base_speed",
                    mech.base_speed,
                    expected_base_speed,
                    owner_id=mech.mech_id,
                )
            expected_speed = mode_effective_speed(expected_base_speed, mech.current_mode)
            if mech.speed != expected_speed:
                raise MatchContractStateMismatchError(
                    "speed",
                    mech.speed,
                    expected_speed,
                    owner_id=mech.mech_id,
                )
            if mech.transition_to_mode is not None:
                self._require_transition(
                    mech.current_mode,
                    mech.transition_to_mode,
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

    def _on_match_started(self, payload: ModelSOMatchStartedPayload) -> None:
        self._arena = payload.arena
        # Recorded, not configured: the bounty rate this match's VP totals are
        # derived from comes from the ledger, so replay cannot silently pay a
        # different rate than the live match did.  The payload validator has
        # already rejected an incentive on an arena that cannot settle VP.
        self._utility_incentive = payload.utility_incentive
        self._mech_states = dict(self._lifecycle.state.mech_states)
        # Objective arenas start every player at zero VP; objective-free
        # arenas keep the historical empty mapping (replay identity).
        if payload.arena.objectives:
            self._vp_totals = {
                player_id: 0 for player_id in sorted({mech.player_id for mech in payload.mechs})
            }
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
        # Prune expired utility effects before scoring — deterministic from the
        # folded tick, identical live and on replay (R9).
        self._active_utility_effects = list(
            expire_effects(tuple(self._active_utility_effects), event.tick)
        )
        self._score_objectives(event)

    def _on_utility_deployed(self, event: ModelSOEventEnvelope) -> None:
        """Fold a deployed utility card into the active-effects table (Phase 2).

        The effect's ``expiry_tick`` is deployment tick + ``duration_ticks``, so
        it bites from the deploying tick and is pruned in ``_on_match_tick`` once
        that tick is reached — the same derivation live and on replay.

        When the match recorded a ``utility_incentive`` on MATCH_STARTED, this
        is ALSO the payout site (SO-UTIL-MECH): the deploying player is
        credited ``vp_per_deploy`` victory points, in the same ``_vp_totals``
        objective control scores into and against the same ``vp_threshold``.
        The reward is therefore structural — it changes the win condition —
        rather than advisory.  Paid on resolution, never on programming, so a
        card the pilot programs but that never resolves (heat lock, death,
        match end) pays nothing.
        """

        payload = ModelSOUtilityDeployedPayload.model_validate(event.payload)
        incentive = self._utility_incentive
        if incentive is not None:
            player_id = event.subject.player_id
            self._vp_totals[player_id] = self._vp_totals.get(player_id, 0) + incentive.vp_per_deploy
            self._utility_bounty_unsettled = True
        self._active_utility_effects = [
            *self._active_utility_effects,
            ModelSOUtilityEffect(
                kind=payload.utility_kind,
                card_id=payload.card_id,
                origin_x=payload.origin.x,
                origin_y=payload.origin.y,
                radius=payload.radius,
                expiry_tick=event.tick + payload.duration_ticks,
                owner_mech_id=event.subject.mech_id,
                owner_player_id=event.subject.player_id,
            ),
        ]

    def _score_objectives(self, event: ModelSOEventEnvelope) -> None:
        """Fold one objective-control scoring round (Phase 4, per MATCH_TICK).

        Deterministic from folded positions: control is evaluated AFTER the
        per-tick sub-reducers, so a mech the failure cascade just killed never
        scores.  Runs only while both players still field a living mech — a
        terminal emitted earlier this tick (rupture kill, mutual destruction)
        is still in the sink un-folded, and scoring past it would race a
        second terminal into the lifecycle's consistency guard.

        Objective VP state mutates HERE (the MATCH_TICK derivation),
        identically live and on replay — the one other VP mutation site is
        the SO-UTIL-MECH bounty in ``_on_utility_deployed``, whose threshold
        settlement this method also performs; the emitted ``OBJECTIVE_SCORED`` events are durable
        telemetry that re-folds as a no-op, and the ``VICTORY_DECLARED``
        threshold intent folds through the lifecycle exactly like the
        elimination backstop's.  A threshold tie (both players reaching the
        line with equal totals in the same round) declares nothing and play
        continues until the totals diverge — deterministic, and never invents
        a winner from an ordering accident.
        """

        arena = self._arena
        if arena is None or not arena.objectives or arena.vp_threshold is None:
            return
        if arena.objective_scoring == "decoy":
            # SO-OBJ-DECOY: the objectives are declared and SHOWN to the pilot
            # (the observation/prompt path is untouched), but they never pay.
            # No VP accrues, no OBJECTIVE_SCORED is emitted, and no VP victory
            # can be declared -- so ``vp_totals`` stays at the zeroes
            # ``_on_match_started`` seeded and the pilot's scoreboard reads
            # 0-0 for the whole match.  Read from the RECORDED snapshot, so a
            # replay suppresses exactly what the live match suppressed.
            #
            # Returning before the bounty settlement below is safe rather than
            # silently lossy: a ``utility_incentive`` on a decoy arena is
            # rejected at composition AND at the MATCH_STARTED payload
            # boundary, so ``_utility_bounty_unsettled`` can never be True
            # here.
            return
        composite = self.state
        if len(composite.surviving_player_ids()) < 2:
            return

        scored_any = False
        for objective in sorted(arena.objectives, key=lambda item: item.objective_id):
            controller = objective_controller(objective.cell, composite)
            if controller is None:
                continue
            self._vp_totals[controller.player_id] = (
                self._vp_totals.get(controller.player_id, 0) + objective.vp_per_round
            )
            scored_any = True
            self._emit(
                self._events.make(
                    match_id=self._match_id,
                    correlation_id=self._correlation_id,
                    tick=event.tick,
                    sequence_in_tick=0,  # bus re-stamps
                    event_type=SOEventType.OBJECTIVE_SCORED,
                    producer_node=_PRODUCER_NODE,
                    subject=ModelSOEventSubject(
                        mech_id=controller.mech_id,
                        player_id=controller.player_id,
                    ),
                    payload={
                        "objective_id": objective.objective_id,
                        "controlling_player_id": controller.player_id,
                        "vp_awarded": objective.vp_per_round,
                        "cumulative_vp": {
                            player: vp for player, vp in sorted(self._vp_totals.items())
                        },
                        "round_index": event.tick,
                    },
                )
            )
        # A bounty paid since the last evaluation must be settled here too:
        # otherwise a player could cross ``vp_threshold`` on bounty VP alone
        # and the match would never declare, because the pre-incentive code
        # only evaluated the threshold on a round where an objective scored.
        # ``_utility_bounty_unsettled`` is permanently False when the
        # incentive is off, so the incentive-free path is unchanged.
        bounty_unsettled = self._utility_bounty_unsettled
        self._utility_bounty_unsettled = False
        if not scored_any and not bounty_unsettled:
            return

        threshold = arena.vp_threshold
        leaders = [player for player, vp in sorted(self._vp_totals.items()) if vp >= threshold]
        if not leaders:
            return
        best = max(self._vp_totals[player] for player in leaders)
        winners = [player for player in leaders if self._vp_totals[player] == best]
        if len(winners) != 1:
            return  # exact tie at the line: keep playing until totals diverge
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
                    "winner_player_id": winners[0],
                    "reason": SOMatchEndReason.VP_THRESHOLD.value,
                    "victory_kind": "vp_threshold",
                },
            )
        )

    def _on_movement_resolved(self, event: ModelSOEventEnvelope) -> None:
        if self._arena is None:
            raise RuntimeError("MATCH_STARTED arena must be validated before movement")
        reducer = ReducerMovement(
            self._match_id,
            self.state,
            arena=self._arena,
        )
        new_state = reducer.apply(event)
        self._mech_states = dict(new_state.mech_states)

    def _on_weapon_fired(self, event: ModelSOEventEnvelope) -> None:
        payload = ModelSOWeaponFiredPayload.model_validate(event.payload)
        mech_id = event.subject.mech_id
        working = self.state
        boiler = self._boilers.get(mech_id)
        if boiler is not None:
            working = boiler.apply(event, working)
        mech = working.mech_states.get(mech_id)
        if mech is not None:
            weapon_id = payload.weapon_id
            spec = self._catalog.weapons.get(weapon_id)
            if spec is None:
                raise UnknownWeaponError(weapon_id, owner_id=mech_id)
            mech = mech.evolve(
                update={
                    "weapon_cooldowns": freeze_mapping(
                        {
                            **mech.weapon_cooldowns,
                            weapon_id: spec.cooldown_ticks,
                        }
                    ),
                    # The overload penalty applies to the next firing only.
                    "accuracy_penalty_next_fire": 0.0,
                }
            )
            working = working.evolve(update={"mech_states": {**working.mech_states, mech_id: mech}})
        self._mech_states = dict(working.mech_states)

    def _on_mode_transition_started(self, event: ModelSOEventEnvelope) -> None:
        mech_id = event.subject.mech_id
        working = self.state
        payload = ModelSOModeTransitionStartedPayload.model_validate(event.payload)
        mech = working.mech_states.get(mech_id)
        if mech is None:
            return
        if payload.from_mode != mech.current_mode:
            raise MatchContractStateMismatchError(
                "current_mode",
                mech.current_mode,
                payload.from_mode,
                owner_id=mech_id,
            )
        transition = self._require_transition(
            payload.from_mode,
            payload.to_mode,
            owner_id=mech_id,
        )
        expected_payload = ModelSOModeTransitionStartedPayload(
            from_mode=transition.from_mode,
            to_mode=transition.to_mode,
            costs=transition.costs,
            sensor_dropout_ticks=transition.vulnerability.sensor_dropout_ticks,
            evasion_penalty=transition.vulnerability.evasion_penalty_during_transition,
        )
        if payload != expected_payload:
            raise MatchContractStateMismatchError(
                "mode_transition",
                payload.model_dump(mode="json"),
                expected_payload.model_dump(mode="json"),
                owner_id=mech_id,
            )
        boiler = self._boilers.get(mech_id)
        if boiler is not None:
            working = boiler.apply(event, working)  # deduct costs (Task 22 fold)
            mech = working.mech_states[mech_id]
        mech = mech.evolve(
            update={
                "transition_ticks_remaining": payload.costs.transition_ticks,
                "transition_to_mode": payload.to_mode,
                "sensor_dropout_ticks_remaining": payload.sensor_dropout_ticks,
                # ``payload.evasion_penalty`` is the transition VULNERABILITY and is
                # deliberately not written into ``evasion`` (a defensive bonus): it is
                # derived at hit resolution from the in-flight transition contract via
                # ``reducers.mode.transition_vulnerability`` (OMN-15592).
            }
        )
        working = working.evolve(update={"mech_states": {**working.mech_states, mech_id: mech}})
        self._mech_states = dict(working.mech_states)

    def _on_damage_applied(self, event: ModelSOEventEnvelope) -> None:
        payload = ModelSODamageAppliedPayload.model_validate(event.payload)
        mech = self._mech_states.get(event.subject.mech_id)
        if mech is None:
            return
        hp_after = payload.hp_after
        if mech.hp == hp_after:
            return  # idempotent re-statement (e.g. rupture loop-back)
        self._mech_states = {
            **self._mech_states,
            mech.mech_id: mech.evolve(update={"hp": hp_after}),
        }

    def _on_armor_absorbed(self, event: ModelSOEventEnvelope) -> None:
        """Degrade armor_value to the post-hit value the runner computed.

        The runner computes the capped absorption and emits ``armor_after``;
        the fold applies it so canonical state tracks the degrading pool.
        Idempotent if the value is already current.
        """
        payload = ModelSOArmorAbsorbedPayload.model_validate(event.payload)
        mech = self._mech_states.get(event.subject.mech_id)
        if mech is None:
            return
        armor_after = payload.armor_after
        if mech.armor_value == armor_after:
            return  # idempotent re-statement
        self._mech_states = {
            **self._mech_states,
            mech.mech_id: mech.evolve(update={"armor_value": armor_after}),
        }

    def _on_flag_drop(
        self,
        event: ModelSOEventEnvelope,
        *,
        field: Literal["alive", "pilot_alive"],
    ) -> None:
        """Fold MECH_DESTROYED / PILOT_KILLED and declare the resulting terminal.

        Two survivor transitions are terminal, not one:
          - ``>1 -> ==1``: ``VICTORY_DECLARED`` for the last player standing;
          - ``>=1 -> ==0``: ``MATCH_ENDED(draw_mutual_destruction)``.  Without
            the second branch a tick that kills every remaining mech left the
            match RUNNING with zero survivors, and the runner published empty
            ticks until an external guard aborted it.

        A simultaneous kill reaches the fold as two ORDERED ``MECH_DESTROYED``
        events, so the survivor count walks ``2 -> 1 -> 0`` rather than
        jumping straight to zero — which is why the draw branch keys on the
        resulting empty set, not on a ``>1`` predecessor.  For the same reason
        the ``==1`` branch would otherwise declare a false victory for a mech
        whose own destruction is still in flight; ``hp == 0`` is the
        un-forgeable marker of that in-flight destruction (every
        ``DAMAGE_APPLIED`` that zeroes hp is always followed by the matching
        ``MECH_DESTROYED``), so a lone "survivor" at zero hp defers the
        declaration to its own destruction event, which then takes the
        ``==0`` branch.

        Defense-in-depth: the failure cascade
        (``ReducerFailureCascade._maybe_declare_terminal`` in
        ``reducers/failure.py``) declares the same terminals on the same
        transitions.  This fold-level declaration is the backstop that fires
        even on a ``MECH_DESTROYED`` emitted outside the cascade (e.g. a direct
        weapon kill).  Both are guarded to the transition so they don't
        duplicate.  The paired redundancy is intentional — see
        ``tests/match/test_fold_victory_backstop.py``.
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
            mech.mech_id: mech.evolve(update={field: False}),
        }
        composite = self.state
        survivors_after = composite.surviving_player_ids()

        if self._lifecycle.state.status is not SOMatchStatus.RUNNING:
            return  # a terminal is already recorded; never re-declare one
        if not survivors_before:
            return
        if not survivors_after:
            self._emit(
                self._events.make(
                    match_id=self._match_id,
                    correlation_id=self._correlation_id,
                    tick=event.tick,
                    sequence_in_tick=0,  # bus re-stamps
                    event_type=SOEventType.MATCH_ENDED,
                    producer_node=_PRODUCER_NODE,
                    subject=_MATCH_SUBJECT,
                    payload={
                        "reason": SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION.value,
                        "winner_id": None,
                    },
                )
            )
            return
        if len(survivors_before) <= 1 or len(survivors_after) > 1:
            return
        if all(survivor.hp == 0 for survivor in composite.living_mechs()):
            # Its own MECH_DESTROYED is still in flight: this is a mutual kill,
            # not a victory. The pending event takes the ``==0`` branch above.
            return
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
                    "victory_kind": "elimination",
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
                mech = mech.evolve(
                    update={
                        "weapon_cooldowns": freeze_mapping(new_cooldowns),
                        "sensor_dropout_ticks_remaining": new_dropout,
                    }
                )
            new_states[mech_id] = mech
        return working.evolve(update={"mech_states": new_states})

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
            new_states[mech_id] = mech.evolve(update={"armor_value": new_armor})
        return working.evolve(update={"mech_states": new_states}) if changed else working

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
                new_states[mech_id] = mech.evolve(update={"transition_ticks_remaining": remaining})
                continue

            to_mode = mech.transition_to_mode
            if to_mode is None:  # unreachable per the paired-fields invariant
                new_states[mech_id] = mech.evolve(update={"transition_ticks_remaining": 0})
                continue

            transition = self._require_transition(
                mech.current_mode,
                to_mode,
                owner_id=mech_id,
            )
            chassis = self._require_contract(
                self._catalog.chassis,
                "chassis",
                mech.chassis_id,
                owner_id=mech_id,
            )
            lock_ticks = transition.restrictions.minimum_lock_ticks_after_switch
            lock_until = event.tick + lock_ticks
            new_states[mech_id] = mech.evolve(
                update={
                    "current_mode": to_mode,
                    "transition_ticks_remaining": 0,
                    "transition_to_mode": None,
                    "mode_lock_until": lock_until,
                    # Vulnerability window closes with ``transition_ticks_remaining``;
                    # ``evasion`` is pinned to its defensive baseline (OMN-15592).
                    "evasion": 0.0,
                    "speed": mode_effective_speed(chassis.constraints.base_speed, to_mode),
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
        return working.evolve(update={"mech_states": new_states})
