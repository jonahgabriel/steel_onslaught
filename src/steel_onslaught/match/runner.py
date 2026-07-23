"""Synchronous tick-loop match runner — Tasks 28 + 34.

Composes the full reducer stack into a deterministic synchronous match loop
driven over an ``EventBus``:

  - canonical state evolution lives in ``MatchStateFold`` (match/fold.py),
    subscribed to the bus — the same fold the replay engine uses, which is
    what guarantees ``replay == live`` (R9);
  - per tick the runner publishes ``MATCH_TICK`` (the fold applies boiler
    regen, countdowns, mode-transition completion, and the failure cascade),
    then emits deterministic ``SENSOR_OBSERVATION``s (Task 20), invokes the
    pilots (Task 21), and resolves the resulting intent events:
      MOVE_INTENT        -> MOVEMENT_RESOLVED            (Task 19 fold)
      WEAPON_FIRE_INTENT -> WEAPON_FIRED / HIT_RESOLVED /
                            ARMOR_ABSORBED / DAMAGE_APPLIED /
                            MECH_DESTROYED               (Tasks 24 + 25)
      MODE_SWITCH_INTENT -> MODE_TRANSITION_STARTED      (Task 23)
      VENT_INTENT        -> no-op (ambient venting only in MVP scope)

All stochastic behaviour flows through ``MatchRng`` sub-seeds, so the full
event stream is a pure function of ``(seed, loadouts, max_ticks, geometry)``.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import ValidationError

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.cards.dealer import ModelSODealerScope, ModelSODeckState
from steel_onslaught.cards.round import carry_forward_plans
from steel_onslaught.contracts.arena import ModelSOArenaSpec, arena_contract_hash
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.budget import ModelSOModuleBudget, validate_loadout_budgets
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.gizmo import ModelSOGizmoConstraints
from steel_onslaught.contracts.live_learning import ModelSOSeatPolicyProvenance
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.mode import ModeId, ModelSOModeSwitchIntentPayload
from steel_onslaught.contracts.player_selection import ModelSOMatchLaunchProvenance, Side
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec, UnknownWeaponError
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
)
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMatchEndedPayload,
    ModelSOMoveIntentPayload,
    ModelSOSensorObservationPayload,
    ModelSOVictoryDeclaredPayload,
    ModelSOWeaponFireIntentPayload,
    ModelSOWeaponFireRejectedPayload,
    WeaponFireRejectionReason,
)
from steel_onslaught.llm.schemas import LlmCompletionBoundaryError, LlmSemanticExhaustedError
from steel_onslaught.match.card_adapter import (
    CardRunnerAdapter,
    ModelSOCardRoundEmission,
    ModelSOCardRoundSeatSplitState,
    ModelSOCardSeatRequest,
)
from steel_onslaught.match.card_event_specs import (
    ModelSOCardRoundEventSpec,
    build_card_round_event_specs,
)
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.geometry import chebyshev_line, greedy_sidestep, line_of_sight_clear
from steel_onslaught.match.initiative import initiative_score, order_by_initiative
from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.runtime import (
    OpenProgressGate,
    ProgressGate,
    ProgressGateStoppedError,
)
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.persona_prompts import ModelSOMatchPromptProvenance
from steel_onslaught.pilots.programming import ModelSOCardRulePackProvenance
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol
from steel_onslaught.reducers.damage import (
    compute_armor_reduction,
    compute_effective_damage_after_vulnerability,
)
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.mode import (
    build_mode_transition_started_event,
    validate_mode_switch,
)
from steel_onslaught.reducers.movement import chebyshev, effective_speed, mode_effective_speed
from steel_onslaught.reducers.pilot_tick import ReducerPilotTick, build_pilot_observation
from steel_onslaught.reducers.sensors import ReducerSensors
from steel_onslaught.reducers.weapons import (
    interpolate_accuracy,
    resolve_hit_probability,
    roll_hit,
    validate_weapon_fire_intent,
)

_LOG = logging.getLogger(__name__)

_PRODUCER_NODE = "node.match.runner"

RUNAWAY_TICK_LIMIT = 1000
"""Runaway failsafe, NOT a tactical tick cap.

Matches are unbounded by design: arena convergence pressure, not a timer, is
what ends an uncapped match.  A match that reaches this tick has stopped
converging, which is a bug in the pressure/terminal path rather than a
gameplay outcome — so it terminates with its own ``ABORTED_RUNAWAY`` reason
that no draw or victory path can produce.  Never widen this into a draw, and
never lower it to bound tactics.

It is also NOT an upper bound on ``max_ticks``.  ``--max-ticks`` is
``IntRange(min=1)`` and ``ModelSOMatchStartedPayload.max_ticks`` is
``Field(..., gt=0)`` — both unbounded above — so a caller may legitimately ask
for more ticks than this guard.  Such a match is converging on its own explicit
cap and must reach it; see :func:`_effective_runaway_limit`.
"""


def _effective_runaway_limit(max_ticks: int | None) -> int:
    """Failsafe tick for this match, never below an explicit ``max_ticks``.

    An explicit cap is an intentional terminal, so the guard must never
    preempt it: a 2000-tick match aborted at tick 1000 would report an engine
    defect (``aborted_runaway`` means "a bug to diagnose") for a perfectly
    correct run, and silently truncate the match the caller asked for.

    The guard is raised rather than disabled.  A capped match that somehow
    walked PAST its own cap is exactly the non-converging failure this failsafe
    exists to catch, so the loop stays bounded for every input.
    """

    if max_ticks is None:
        return RUNAWAY_TICK_LIMIT
    return max(RUNAWAY_TICK_LIMIT, max_ticks)


# Match-scoped events have no single mech/player subject.
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

_FACING_A = 45
_FACING_B = 225

# Combat stats: hull/armor come from the chassis contract (base_hp /
# base_armor on ModelSOChassisConstraints), so chassis class drives durability.
_INITIAL_MODE = ModeId.RECON

# All mode names a module may be active in (budget normalization).
_ALL_MODES = tuple(ModeId)

_INTENT_EVENT_TYPES = [
    SOEventType.MOVE_INTENT,
    SOEventType.WEAPON_FIRE_INTENT,
    SOEventType.MODE_SWITCH_INTENT,
    SOEventType.VENT_INTENT,
]


def _clamp(value: int, magnitude: int) -> int:
    return max(-magnitude, min(magnitude, value))


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


@dataclass(frozen=True)
class MatchIdentity:
    """Public match/workflow identity shared by every composed participant."""

    match_id: str
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class _ActiveCardRound:
    """Latched card lifecycle values shared by paced register ticks.

    The adapter still computes a complete immutable round once.  The runner
    retains that value and its causal event specifications until the final
    register is published, so no subsequent tick can deal, program, or
    recalculate heat locks for the active round.
    """

    emission: ModelSOCardRoundEmission
    specs: tuple[ModelSOCardRoundEventSpec, ...]
    next_register_index: int
    last_lifecycle_message_id: UUID | None = None


class MatchRunner:
    """Synchronous tick-loop driver for one two-mech match."""

    def __init__(
        self,
        *,
        identity: MatchIdentity,
        seed: int,
        loadout_a: ModelSOLoadout,
        loadout_b: ModelSOLoadout,
        bus: EventBus,
        event_factory: EventFactory,
        catalog: MatchContractCatalog,
        arena: ModelSOArenaSpec,
        pilots: dict[str, PilotProtocol],
        max_ticks: int | None = None,
        side_a: str = "a",
        side_b: str = "b",
        facing_a: int = _FACING_A,
        facing_b: int = _FACING_B,
        launch_provenance: ModelSOMatchLaunchProvenance | None = None,
        card_runtime_snapshot: ModelSOCardRuntimeSnapshot | None = None,
        card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = None,
        prompt_provenance: ModelSOMatchPromptProvenance | None = None,
        policy_provenance: tuple[ModelSOSeatPolicyProvenance, ...] | None = None,
        card_adapter: CardRunnerAdapter | None = None,
        card_cadence: Literal["atomic", "paced"] = "atomic",
        progress_gate: ProgressGate | None = None,
    ) -> None:
        self._identity = identity
        self._match_id = identity.match_id
        self._correlation_id = identity.correlation_id
        self._events = event_factory
        self._seed = seed
        self._rng = MatchRng(match_seed=seed)
        self._loadout_a = loadout_a
        self._loadout_b = loadout_b
        self._bus = bus
        self._max_ticks = max_ticks
        self._runaway_tick_limit = _effective_runaway_limit(max_ticks)
        self._side_a = side_a
        self._side_b = side_b
        self._arena = arena.to_snapshot()
        self._spawn_a = self._arena.spawn_a
        self._spawn_b = self._arena.spawn_b
        self._facing_a = facing_a
        self._facing_b = facing_b
        self._arena_size = self._arena.size
        self._obstacles = self._arena.obstacle_cells
        self._sudden_death_start_tick = self._arena.sudden_death_start_tick
        self._sudden_death_damage_base = self._arena.sudden_death_damage_base
        if max_ticks is None and self._sudden_death_start_tick is None:
            raise ValueError(
                "uncapped matches require arena sudden-death convergence configuration"
            )
        self._catalog = catalog
        if card_adapter is not None and not isinstance(card_adapter, CardRunnerAdapter):
            raise TypeError("card_adapter must be CardRunnerAdapter when supplied")
        adapter_snapshot = (
            None
            if card_adapter is None or not card_adapter.registers_enabled
            else card_adapter.snapshot
        )
        if (
            card_runtime_snapshot is not None
            and adapter_snapshot is not None
            and card_runtime_snapshot is not adapter_snapshot
        ):
            raise ValueError(
                "card_runtime_snapshot and card_adapter must share the exact snapshot object"
            )
        self._card_runtime_snapshot = card_runtime_snapshot or adapter_snapshot
        if card_rule_pack_provenance is not None and not isinstance(
            card_rule_pack_provenance, ModelSOCardRulePackProvenance
        ):
            raise TypeError(
                "card_rule_pack_provenance must be ModelSOCardRulePackProvenance when supplied"
            )
        self._card_rule_pack_provenance = card_rule_pack_provenance
        if prompt_provenance is not None and not isinstance(
            prompt_provenance, ModelSOMatchPromptProvenance
        ):
            raise TypeError("prompt_provenance must be ModelSOMatchPromptProvenance when supplied")
        self._prompt_provenance = prompt_provenance
        if policy_provenance is not None and (
            not isinstance(policy_provenance, tuple)
            or not policy_provenance
            or not all(
                isinstance(entry, ModelSOSeatPolicyProvenance) for entry in policy_provenance
            )
        ):
            raise TypeError(
                "policy_provenance must be a non-empty tuple of "
                "ModelSOSeatPolicyProvenance when supplied"
            )
        self._policy_provenance = policy_provenance
        self._card_adapter = card_adapter
        if card_cadence not in {"atomic", "paced"}:
            raise ValueError("card_cadence must be 'atomic' or 'paced'")
        self._card_cadence = card_cadence
        self._card_round_index = 0
        self._card_deck_state: ModelSODeckState | None = None
        self._card_split_deck_states: tuple[ModelSOCardRoundSeatSplitState, ...] = ()
        self._card_previous_plans: dict[str, ModelSOPlanCommittedPayload] = {}
        self._card_active_round: _ActiveCardRound | None = None
        self._pilots = dict(pilots)
        self._launch_provenance = self._validate_launch_provenance(
            launch_provenance,
            identity=identity,
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            side_a=side_a,
            side_b=side_b,
        )
        # The gate is consulted only between complete tick transactions.  A
        # no-op default preserves deterministic offline callers while the
        # lifecycle composition root can inject a pause/resume gate.
        self._progress_gate = progress_gate or OpenProgressGate()

        # Canonical state fold — the same fold the replay engine uses.
        # Subscribed at construction time so callers can order later
        # subscribers (scoring, leaderboard) AFTER the fold.
        self.fold = MatchStateFold(
            self._match_id,
            self._correlation_id,
            event_factory=event_factory,
            bus=bus,
            catalog=self._catalog,
            before_emit=self._before_fold_emit,
        )
        bus.subscribe(self.fold.handle)

        # Per-tick buffers + MATCH_ENDED bookkeeping.
        self._sensor_buffer: list[ModelSOEventEnvelope] = []
        bus.subscribe(self._sensor_buffer.append, event_types=[SOEventType.SENSOR_OBSERVATION])
        self._intent_buffer: list[ModelSOEventEnvelope] = []
        bus.subscribe(self._intent_buffer.append, event_types=_INTENT_EVENT_TYPES)
        self._match_ended_events: list[ModelSOEventEnvelope] = []
        bus.subscribe(self._match_ended_events.append, event_types=[SOEventType.MATCH_ENDED])

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def identity(self) -> MatchIdentity:
        return self._identity

    def run(self) -> ModelSOMatchState:
        """Drive the match to termination; return the final match state."""
        mech_a = self._build_mech(
            self._loadout_a,
            mech_id=f"mech.{self._side_a}.01",
            player_id=f"player.{self._side_a}",
            side="red",
            position=self._spawn_a,
            facing=self._facing_a,
        )
        mech_b = self._build_mech(
            self._loadout_b,
            mech_id=f"mech.{self._side_b}.01",
            player_id=f"player.{self._side_b}",
            side="blue",
            position=self._spawn_b,
            facing=self._facing_b,
        )
        mechs = (mech_a, mech_b)
        required_pilot_ids = {mech_a.mech_id, mech_b.mech_id}
        missing_pilots = required_pilot_ids - set(self._pilots)
        if missing_pilots:
            raise ValueError(f"missing injected pilots for seats: {sorted(missing_pilots)}")

        started_payload: dict[str, Any] = {
            "seed": self._seed,
            "max_ticks": self._max_ticks,
            "mechs": [mech.model_dump(mode="json") for mech in mechs],
            "arena": self._arena.model_dump(mode="json"),
            # Phase 4 finish-line seam: every new ledger names the exact
            # arena/objective contract it flew on (self-verifying digest).
            "arena_contract_hash": arena_contract_hash(self._arena),
        }
        if self._launch_provenance is not None:
            started_payload["launch_provenance"] = self._launch_provenance.model_dump(mode="json")
        card_provenance = (
            self._card_runtime_snapshot.provenance
            if self._card_runtime_snapshot is not None
            else None
        )
        if card_provenance is not None:
            started_payload["card_runtime_provenance"] = card_provenance.model_dump(mode="json")
        if self._card_rule_pack_provenance is not None:
            started_payload["card_rule_pack_provenance"] = (
                self._card_rule_pack_provenance.model_dump(mode="json")
            )
        if self._prompt_provenance is not None:
            started_payload["prompt_provenance"] = self._prompt_provenance.model_dump(mode="json")
        if self._policy_provenance is not None:
            started_payload["policy_provenance"] = [
                entry.model_dump(mode="json") for entry in self._policy_provenance
            ]
        self._bus.publish(
            self._make_match_event(
                SOEventType.MATCH_STARTED,
                tick=0,
                payload=started_payload,
            )
        )

        while self.fold.state.status is SOMatchStatus.RUNNING:
            next_tick = self.fold.state.tick + 1
            if next_tick > self._runaway_tick_limit:
                self._terminate_for_runaway(tick=self.fold.state.tick)
                break
            try:
                self._progress_gate.checkpoint(match_id=self._match_id, next_tick=next_tick)
            except ProgressGateStoppedError:
                # A lifecycle STOP closes the gate between complete ticks.
                # Convert that boundary signal into canonical terminal
                # evidence so the ledger can durably precede runtime ENDED.
                if self.fold.state.status is SOMatchStatus.RUNNING:
                    self._bus.publish(
                        self._make_match_event(
                            SOEventType.MATCH_ENDED,
                            tick=self.fold.state.tick,
                            payload={
                                "reason": SOMatchEndReason.ABORTED.value,
                                "winner_id": None,
                            },
                        )
                    )
                if self._card_cadence == "paced":
                    self._cancel_active_card_round(
                        tick=self.fold.state.tick,
                        reason="aborted",
                    )
                break
            self._sensor_buffer.clear()
            self._intent_buffer.clear()

            tick_event = self._make_match_event(SOEventType.MATCH_TICK, tick=next_tick, payload={})
            # ``MATCH_TICK`` folds lifecycle termination synchronously and
            # publishes its nested ``MATCH_ENDED`` before control returns to
            # this runner.  Close an in-flight paced card round first so the
            # scoring subscriber sees a complete replay lifecycle when a
            # max-tick draw interrupts the round.
            if (
                self._card_cadence == "paced"
                and self._card_active_round is not None
                and self._max_ticks is not None
                and next_tick >= self._max_ticks
            ):
                self._cancel_active_card_round(
                    tick=next_tick,
                    reason="max_ticks",
                    emit_match_ended=False,
                )
            self._bus.publish(tick_event)
            if self.fold.state.status is not SOMatchStatus.RUNNING:
                if self._card_cadence == "paced":
                    self._cancel_active_card_round(tick=next_tick, reason="max_ticks")
                else:
                    self._card_active_round = None
                break  # terminal tick (max_ticks bound or failure-cascade kill)

            ReducerSensors(
                self._match_id,
                self.fold.state,
                self._catalog.sensors,
                emit=self._bus.publish,
                correlation_id=self._correlation_id,
                event_factory=self._events,
            ).apply(tick_event)

            try:
                if self._card_adapter is not None and self._card_adapter.registers_enabled:
                    self._run_card_round(next_tick, tick_event)
                else:
                    ReducerPilotTick(
                        self._match_id,
                        self.fold.state,
                        self._pilots,
                        sensor_events=list(self._sensor_buffer),
                        emit=self._bus.publish,
                        weapon_specs=self._catalog.weapons,
                        correlation_id=self._correlation_id,
                        event_factory=self._events,
                        obstacles=self._obstacles,
                        arena_size=self._arena_size,
                        objectives=self._arena.objectives,
                        vp_threshold=self._arena.vp_threshold,
                    ).apply(tick_event)
            except LlmCompletionBoundaryError:
                # A live provider that exhausts its output budget or typed
                # timeout boundary must end the match at this tick. The
                # completion effect has already emitted its sanitized failed
                # terminal; this lifecycle event makes the match itself
                # durably terminal and prevents a pre-hand-dealt freeze.
                self._terminate_for_llm_boundary(tick=next_tick)
                break
            except LlmSemanticExhaustedError as exc:
                # A bound seat answered every reprompt but never with an
                # admissible plan. The completion effect already recorded one
                # sanitized llm_completion_failed per attempt; this makes the
                # match durably terminal with a DISTINCT provider_semantic_failure
                # reason instead of freezing with no terminal (the live stall).
                self._terminate_for_llm_semantic(tick=next_tick, detail=exc)
                break

            # Resolve intents in initiative order. Initiative is a real combat
            # mechanic (match/initiative.py): lighter chassis and well-managed
            # boilers act first; overloaded/redline boilers act late. This
            # replaces a fixed insertion order, which gave a systematic
            # first-actor disadvantage in same-tick kill exchanges and broke
            # the side-swap symmetry the learning loop relies on. Ties break
            # by a seeded RNG sub-seed so equal-initiative mechs don't get a
            # fixed ordering across the match.
            if self._card_adapter is None or not self._card_adapter.registers_enabled:
                ordered_mechs = order_by_initiative(
                    list(self.fold.state.living_mechs()), rng=self._rng, tick=next_tick
                )
                initiative_order = {mech.mech_id: i for i, mech in enumerate(ordered_mechs)}
                intents = sorted(
                    self._intent_buffer, key=lambda e: initiative_order.get(e.subject.mech_id, 0)
                )
                for intent in intents:
                    if self.fold.state.status is not SOMatchStatus.RUNNING:
                        break  # an earlier resolution ended the match
                    self._resolve_intent(intent)
            if self.fold.state.status is SOMatchStatus.RUNNING:
                self._apply_sudden_death(next_tick)
            elif self._card_cadence == "paced":
                self._cancel_active_card_round(tick=next_tick, reason="decisive_death")

        # Decisive endings terminate via VICTORY_DECLARED; the plan requires a
        # final MATCH_ENDED re-statement as well (the lifecycle reducer emits
        # it itself only on the max_ticks draw path).
        final = self.fold.state
        if not self._match_ended_events and final.end_reason is not None:
            self._bus.publish(
                self._make_match_event(
                    SOEventType.MATCH_ENDED,
                    tick=final.tick,
                    payload={"reason": final.end_reason.value, "winner_id": final.winner_id},
                )
            )
        return self.fold.state

    def _terminate_for_runaway(self, *, tick: int) -> None:
        """Record the runaway failsafe terminal with its own diagnosable reason."""

        if self.fold.state.status is not SOMatchStatus.RUNNING:
            return
        if self._card_cadence == "paced":
            self._cancel_active_card_round(tick=tick, reason="runaway")
        self._bus.publish(
            self._make_match_event(
                SOEventType.MATCH_ENDED,
                tick=tick,
                payload={
                    "reason": SOMatchEndReason.ABORTED_RUNAWAY.value,
                    "winner_id": None,
                },
            )
        )

    def _terminate_for_llm_boundary(self, *, tick: int) -> None:
        """Record an aborted terminal when a live provider cannot complete."""

        if self.fold.state.status is not SOMatchStatus.RUNNING:
            return
        if self._card_cadence == "paced":
            self._cancel_active_card_round(tick=tick, reason="llm_boundary")
        self._bus.publish(
            self._make_match_event(
                SOEventType.MATCH_ENDED,
                tick=tick,
                payload={
                    "reason": SOMatchEndReason.ABORTED.value,
                    "winner_id": None,
                },
            )
        )

    def _terminate_for_llm_semantic(self, *, tick: int, detail: LlmSemanticExhaustedError) -> None:
        """Record the distinct terminal for a bounded semantic-retry exhaustion.

        This is the fix for the live-provider stall: a plan the engine rejects
        as a SEMANTIC failure (e.g. ``invalid_action_parameters``) used to
        propagate past the boundary-only handler and freeze the match with no
        terminal. The seat/provider/semantic-code detail is durable in the
        per-attempt ``llm_completion_failed`` events at this tick; the terminal
        names its own distinct reason so it is never confused with a
        length/timeout ``aborted`` or a clean gameplay outcome.
        """

        _LOG.warning(
            "match %s ended provider_semantic_failure at tick %d "
            "(seat=%s, provider=%s, code=%s, attempts=%d)",
            self._match_id,
            tick,
            detail.seat,
            detail.provider_id,
            detail.semantic_failure_code,
            detail.attempts,
        )
        if self.fold.state.status is not SOMatchStatus.RUNNING:
            return
        if self._card_cadence == "paced":
            self._cancel_active_card_round(tick=tick, reason="provider_semantic_failure")
        self._bus.publish(
            self._make_match_event(
                SOEventType.MATCH_ENDED,
                tick=tick,
                payload={
                    "reason": SOMatchEndReason.PROVIDER_SEMANTIC_FAILURE.value,
                    "winner_id": None,
                },
            )
        )

    def _run_card_round(self, tick: int, tick_event: ModelSOEventEnvelope) -> None:
        """Publish one explicit card round and resolve its typed intents.

        The adapter owns pure dealing/programming.  This method is the narrow
        effect boundary: it allocates UUIDs through ``EventFactory``,
        publishes the validated specs, and only commits ephemeral deck/plan
        state after the complete round has been emitted.
        """

        adapter = self._card_adapter
        if adapter is None or not adapter.registers_enabled:
            return
        if self._card_cadence == "paced":
            self._run_paced_card_round(tick, tick_event)
            return
        living = tuple(sorted(self.fold.state.living_mechs(), key=lambda mech: mech.mech_id))
        seats: list[ModelSOCardSeatRequest] = []
        subject_by_seat: dict[str, ModelSOEventSubject] = {}
        for mech in living:
            seat = self._seat_for_mech(mech.mech_id)
            previous = self._card_previous_plans.get(seat)
            lock_depth = 0
            if previous is not None:
                lock_depth = int(mech.boiler.status_redline) + int(mech.overloaded)
            observation = build_pilot_observation(
                mech,
                self.fold.state,
                list(self._sensor_buffer),
                self._catalog.weapons,
                obstacles=self._obstacles,
                arena_size=self._arena_size,
                objectives=self._arena.objectives,
                vp_threshold=self._arena.vp_threshold,
            )
            seats.append(
                ModelSOCardSeatRequest(
                    seat=seat,
                    side=cast(Side, mech.side),
                    dealer_scope=ModelSODealerScope(
                        match_id=self._match_id,
                        match_seed=self._seed,
                        tick=tick,
                        seat=seat,
                    ),
                    pilot_observation=observation,
                    initiative=initiative_score(mech),
                    lock_depth=lock_depth,
                    previous_plan=previous,
                    weapon_ids=tuple(mech.weapon_cooldowns),
                )
            )
            subject_by_seat[seat] = ModelSOEventSubject(
                mech_id=mech.mech_id,
                player_id=mech.player_id,
            )

        emission = adapter.produce(
            seats=tuple(seats),
            round_index=self._card_round_index,
            tick=tick,
            causation_id=str(tick_event.envelope.message_id),
            starting_deck_state=(
                None if adapter.split_deck_adapter is not None else self._card_deck_state
            ),
            starting_split_deck_states=self._card_split_deck_states,
        )
        if emission.suppressed_reason is not None:
            return
        message_ids = tuple(
            self._events.identities.new_message_id()
            for _ in range(
                len(emission.values)
                + sum(action.event_type is not None for action in emission.actions)
            )
        )
        specs = build_card_round_event_specs(
            emission,
            root_causation_id=tick_event.envelope.message_id,
            seat_subjects=subject_by_seat,
            message_ids=message_ids,
        )
        for spec in specs:
            event = self._events.make_with_message_id(
                message_id=spec.message_id,
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,
                event_type=spec.event_type,
                producer_node=_PRODUCER_NODE,
                subject=spec.subject,
                payload=spec.model_dump(mode="json")["payload"],
                correlation_id=self._correlation_id,
                causation_id=spec.causation_id,
            )
            self._bus.publish(event)
            if spec.stage == "INTENT" and self.fold.state.status is SOMatchStatus.RUNNING:
                self._resolve_intent(event)

        if emission.sequence is None or (
            emission.deck_state is None and not emission.split_deck_states
        ):
            raise RuntimeError("enabled card emission must carry sequence and deck state")
        self._card_deck_state = emission.deck_state
        self._card_split_deck_states = emission.split_deck_states
        self._card_previous_plans = carry_forward_plans(emission.sequence)
        self._card_round_index += 1

    def _run_paced_card_round(self, tick: int, tick_event: ModelSOEventEnvelope) -> None:
        """Advance one latched card round by exactly one register.

        The first paced tick deals and commits plans, then resolves register
        zero.  Later ticks reuse the exact same causal specifications and only
        resolve their latched register.  The deck, previous-plan map, and
        round index are committed after the final register; a terminal match
        cancels the active round without committing a partial deck state.
        """

        adapter = self._card_adapter
        if adapter is None or not adapter.registers_enabled:
            return
        active = self._card_active_round
        first_tick = active is None
        if first_tick:
            living = tuple(sorted(self.fold.state.living_mechs(), key=lambda mech: mech.mech_id))
            seats: list[ModelSOCardSeatRequest] = []
            subject_by_seat: dict[str, ModelSOEventSubject] = {}
            for mech in living:
                seat = self._seat_for_mech(mech.mech_id)
                previous = self._card_previous_plans.get(seat)
                lock_depth = 0
                if previous is not None:
                    lock_depth = int(mech.boiler.status_redline) + int(mech.overloaded)
                observation = build_pilot_observation(
                    mech,
                    self.fold.state,
                    list(self._sensor_buffer),
                    self._catalog.weapons,
                    obstacles=self._obstacles,
                    arena_size=self._arena_size,
                    objectives=self._arena.objectives,
                    vp_threshold=self._arena.vp_threshold,
                )
                seats.append(
                    ModelSOCardSeatRequest(
                        seat=seat,
                        side=cast(Side, mech.side),
                        dealer_scope=ModelSODealerScope(
                            match_id=self._match_id,
                            match_seed=self._seed,
                            tick=tick,
                            seat=seat,
                        ),
                        pilot_observation=observation,
                        initiative=initiative_score(mech),
                        lock_depth=lock_depth,
                        previous_plan=previous,
                        weapon_ids=tuple(mech.weapon_cooldowns),
                    )
                )
                subject_by_seat[seat] = ModelSOEventSubject(
                    mech_id=mech.mech_id,
                    player_id=mech.player_id,
                )

            emission = adapter.produce(
                seats=tuple(seats),
                round_index=self._card_round_index,
                tick=tick,
                causation_id=str(tick_event.envelope.message_id),
                starting_deck_state=(
                    None if adapter.split_deck_adapter is not None else self._card_deck_state
                ),
                starting_split_deck_states=self._card_split_deck_states,
            )
            if emission.suppressed_reason is not None:
                return
            message_ids = tuple(
                self._events.identities.new_message_id()
                for _ in range(
                    len(emission.values)
                    + sum(action.event_type is not None for action in emission.actions)
                )
            )
            specs = build_card_round_event_specs(
                emission,
                root_causation_id=tick_event.envelope.message_id,
                seat_subjects=subject_by_seat,
                message_ids=message_ids,
            )
            active = _ActiveCardRound(emission=emission, specs=specs, next_register_index=0)
            self._card_active_round = active

        assert active is not None
        sequence = active.emission.sequence
        if sequence is None or (
            active.emission.deck_state is None and not active.emission.split_deck_states
        ):
            raise RuntimeError("enabled paced card emission must carry sequence and deck state")
        if active.emission.split_policy is not None:
            register_count = max(seat.register_count for seat in active.emission.split_policy.seats)
        elif self._card_runtime_snapshot is not None:
            register_count = self._card_runtime_snapshot.selected_deck.register_count
        else:
            register_count = 0
        if register_count <= 0:
            raise RuntimeError("enabled paced card emission requires a positive register count")
        register_index = active.next_register_index
        final_register = register_index == register_count - 1

        def include(spec: ModelSOCardRoundEventSpec) -> bool:
            if spec.stage in {"HAND_DEALT", "PLAN_COMMITTED"}:
                return first_tick
            if spec.stage == "CARDS_DISCARDED":
                return final_register
            if spec.stage == "REGISTER_RESOLVED":
                register_payload = ModelSORegisterResolvedPayload.model_validate(spec.payload)
                return register_payload.register_index == register_index
            if spec.stage == "INTENT":
                return spec.register_index == register_index
            return False

        selected_specs = tuple(spec for spec in active.specs if include(spec))
        if not any(spec.stage == "REGISTER_RESOLVED" for spec in selected_specs):
            raise RuntimeError(f"paced card emission has no register {register_index} rows")
        # Publish every lifecycle row for the current register before any
        # intent can kill a seat.  This retains the dead seat's canonical
        # REGISTER_RESOLVED row while its later intent is voided by
        # ``_resolve_intent``.  Discards remain last, after intents.
        specs = (
            tuple(spec for spec in selected_specs if spec.stage in {"HAND_DEALT", "PLAN_COMMITTED"})
            + tuple(spec for spec in selected_specs if spec.stage == "REGISTER_RESOLVED")
            + tuple(spec for spec in selected_specs if spec.stage == "INTENT")
            + tuple(spec for spec in selected_specs if spec.stage == "CARDS_DISCARDED")
        )
        for spec in specs:
            event = self._events.make_with_message_id(
                message_id=spec.message_id,
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,
                event_type=spec.event_type,
                producer_node=_PRODUCER_NODE,
                subject=spec.subject,
                payload=spec.model_dump(mode="json")["payload"],
                correlation_id=self._correlation_id,
                causation_id=spec.causation_id,
            )
            self._bus.publish(event)
            if spec.stage != "INTENT":
                active = _ActiveCardRound(
                    emission=active.emission,
                    specs=active.specs,
                    next_register_index=active.next_register_index,
                    last_lifecycle_message_id=spec.message_id,
                )
                self._card_active_round = active
            if spec.stage == "INTENT" and self.fold.state.status is SOMatchStatus.RUNNING:
                self._resolve_intent(event)
            if self.fold.state.status is not SOMatchStatus.RUNNING:
                # A decisive hit closes the active round at the exact event
                # boundary.  No partial deck/plan commit is allowed.
                self._cancel_active_card_round(tick=tick, reason="decisive_death")
                return

        if final_register:
            self._card_deck_state = active.emission.deck_state
            self._card_split_deck_states = active.emission.split_deck_states
            self._card_previous_plans = carry_forward_plans(sequence)
            self._card_round_index += 1
            self._card_active_round = None
        else:
            self._card_active_round = _ActiveCardRound(
                emission=active.emission,
                specs=active.specs,
                next_register_index=register_index + 1,
                last_lifecycle_message_id=active.last_lifecycle_message_id,
            )

    def _before_fold_emit(self, event: ModelSOEventEnvelope) -> None:
        """Close a paced card round before a fold-produced terminal event.

        Fold-produced victory declarations are published synchronously.  A
        terminal scoring subscriber can therefore observe the declaration
        before the runner's post-resolution cleanup unless the active card
        round is closed at this effect boundary first.

        The cancellation reason follows the terminal that caused it: a
        mutual-destruction ``MATCH_ENDED`` closed the round because mechs
        DIED, so labelling it ``max_ticks`` would put a false cause in the
        canonical discard row.
        """

        if (
            event.event_type in {SOEventType.VICTORY_DECLARED, SOEventType.MATCH_ENDED}
            and self._card_cadence == "paced"
            and self._card_active_round is not None
        ):
            if event.event_type is SOEventType.VICTORY_DECLARED:
                # A VP-threshold victory closed the round because a side hit
                # the objective finish line, not because a mech died — the
                # canonical discard row must name the true cause.
                victory_reason = ModelSOVictoryDeclaredPayload.model_validate(event.payload).reason
                reason = (
                    "vp_threshold"
                    if victory_reason is SOMatchEndReason.VP_THRESHOLD
                    else "decisive_death"
                )
            else:
                death_driven = (
                    ModelSOMatchEndedPayload.model_validate(event.payload).reason
                    is SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION
                )
                reason = "decisive_death" if death_driven else "max_ticks"
            self._cancel_active_card_round(
                tick=event.tick,
                reason=reason,
                emit_match_ended=False,
            )

    def _cancel_active_card_round(
        self,
        *,
        tick: int,
        reason: str,
        emit_match_ended: bool = True,
    ) -> None:
        """Close a paced round without committing its partial deck state.

        ``CARDS_DISCARDED`` is the existing terminal card vocabulary.  A
        ``cancelled:<reason>`` reason makes the closure explicit while
        preserving the closed payload contract; replay can therefore accept
        a complete terminal lifecycle batch without mistaking it for a deck
        commit.
        """

        active = self._card_active_round
        if active is None:
            return
        if (
            emit_match_ended
            and self.fold.state.status is SOMatchStatus.ENDED
            and not self._match_ended_events
        ):
            self._bus.publish(
                self._make_match_event(
                    SOEventType.MATCH_ENDED,
                    tick=self.fold.state.tick,
                    payload={
                        "reason": self.fold.state.end_reason.value
                        if self.fold.state.end_reason is not None
                        else SOMatchEndReason.ABORTED.value,
                        "winner_id": self.fold.state.winner_id,
                    },
                )
            )
        discard_specs = tuple(spec for spec in active.specs if spec.stage == "CARDS_DISCARDED")
        parent_message_id = active.last_lifecycle_message_id
        for spec in discard_specs:
            payload = ModelSOCardsDiscardedPayload.model_validate(spec.payload).model_copy(
                update={"reason": f"cancelled:{reason}"}
            )
            causation_id = parent_message_id or spec.parent.root_causation_id
            event = self._events.make_with_message_id(
                message_id=spec.message_id,
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,
                event_type=spec.event_type,
                producer_node=_PRODUCER_NODE,
                subject=spec.subject,
                payload=payload.model_dump(mode="json"),
                correlation_id=self._correlation_id,
                causation_id=causation_id,
            )
            self._bus.publish(event)
            parent_message_id = spec.message_id
        self._card_active_round = None

    def _seat_for_mech(self, mech_id: str) -> str:
        """Return the canonical card seat for a runner-owned mech id."""

        expected = {
            f"mech.{self._side_a}.01": self._side_a,
            f"mech.{self._side_b}.01": self._side_b,
        }
        try:
            return expected[mech_id]
        except KeyError as exc:
            raise ValueError(f"card runtime has no canonical seat for mech {mech_id!r}") from exc

    def _apply_sudden_death(self, tick: int) -> None:
        """Apply deterministic arena pressure to an uncapped match.

        This is game-design convergence, not a hidden lifecycle timer. Every
        attrition fact is emitted through the canonical damage/destruction path
        and is therefore folded and replayed exactly like weapon damage.

        The pulse is SIMULTANEOUS: every living mech is damaged from the same
        pre-pulse snapshot, and only then is destruction resolved.  Damaging
        and destroying one mech at a time (and breaking on the first kill) gave
        the win to whichever mech sorted last by ``mech_id`` — the
        alphabetically-first mech died before its opponent absorbed the same
        lethal pressure, so a symmetric uncapped match always ended
        ``winner=player.b`` at full HP.  When the pulse is lethal for every
        remaining mech the fold sees the ``>1 -> ==0`` survivor transition and
        records ``draw_mutual_destruction``; the ``hp == 0`` deferral in
        ``MatchStateFold._on_flag_drop`` is what stops the first destruction
        event from declaring a false victory in between.

        Why the destruction loop needs no post-terminal guard TODAY, and the
        exact precondition that would change that:

        The loop publishes ``MECH_DESTROYED`` only for the mechs the pulse
        zeroed, and the fold's terminals key on surviving *player* ids.  A
        match is duel-only — the runner builds exactly ``mech_a`` and
        ``mech_b``, one per player — so the zeroed set is either one mech (the
        survivor's own destruction never publishes, and the terminal lands on
        the single destruction) or both (survivors walk ``2 -> 1 -> 0``, the
        ``hp == 0`` deferral suppresses the intermediate victory, and the
        terminal lands on the last destruction).  Either way the terminal
        coincides with the FINAL publish of the pulse, so nothing is emitted
        after ``MATCH_ENDED``.

        That invariant is a consequence of one-mech-per-player, NOT of the
        loop.  Give a player two mechs and it breaks: with ``a`` fielding
        ``A1``/``A2`` and ``b`` fielding ``B1``, a pulse that zeroes ``A1`` and
        ``B1`` (leaving ``A2`` healthy) declares victory for ``a`` on ``B1``'s
        destruction whenever initiative orders ``B1`` first — and ``A1``'s
        destruction would then publish after the terminal, which the browser
        transport rejects outright.  A ``break`` here is deliberately NOT the
        answer: the fold applies ``alive=False`` before its terminal guard, so
        dropping the publish would leave ``A1`` recorded alive at zero hp.
        Whoever adds multi-mech seats must fix the ORDER (terminal-triggering
        destruction last), not silence the tail.  ``tests/match/
        test_terminal_correctness.py`` pins the duel invariant so the duel case
        cannot regress unnoticed in the meantime.
        """
        start = self._sudden_death_start_tick
        if start is None or tick < start or self._max_ticks is not None:
            return
        damage = self._sudden_death_damage_base * (tick - start + 1)
        # Initiative (seeded, never a raw mech_id sort) orders the residual
        # per-mech event sequence; it cannot change who dies, because every
        # hp_after is computed from the same pre-pulse snapshot.
        pulse = tuple(
            (mech, max(0, mech.hp - damage))
            for mech in order_by_initiative(
                list(self.fold.state.living_mechs()), rng=self._rng, tick=tick
            )
        )
        for mech, hp_after in pulse:
            self._bus.publish(
                self._make_subject_event(
                    SOEventType.DAMAGE_APPLIED,
                    tick=tick,
                    mech=mech,
                    payload={
                        "target_id": mech.mech_id,
                        "damage": mech.hp - hp_after,
                        "cause": "sudden_death",
                        "hp_after": hp_after,
                        "source_mech_id": None,
                    },
                )
            )
        for mech, hp_after in pulse:
            if hp_after != 0:
                continue
            self._bus.publish(
                self._make_subject_event(
                    SOEventType.MECH_DESTROYED,
                    tick=tick,
                    mech=mech,
                    payload={"cause": "sudden_death", "source_mech_id": None},
                )
            )

    @staticmethod
    def _validate_launch_provenance(
        provenance: ModelSOMatchLaunchProvenance | None,
        *,
        identity: MatchIdentity,
        loadout_a: ModelSOLoadout,
        loadout_b: ModelSOLoadout,
        side_a: str,
        side_b: str,
    ) -> ModelSOMatchLaunchProvenance | None:
        if provenance is None:
            return None
        if not isinstance(provenance, ModelSOMatchLaunchProvenance):
            raise TypeError("launch_provenance must be ModelSOMatchLaunchProvenance")
        if provenance.match_id != identity.match_id:
            raise ValueError("launch provenance match_id must equal runner identity match_id")

        assignments = {assignment.side: assignment for assignment in provenance.seat_assignments}
        expected: dict[Side, tuple[str, str, str]] = {
            "red": (f"player.{side_a}", loadout_a.id, loadout_a.pilot_id),
            "blue": (f"player.{side_b}", loadout_b.id, loadout_b.pilot_id),
        }
        for side, (player_id, loadout_id, pilot_spec_id) in expected.items():
            assignment = assignments[side]  # Model validation guarantees exact red/blue sides.
            actual = (assignment.player_id, assignment.loadout_id, assignment.pilot_spec_id)
            wanted = (player_id, loadout_id, pilot_spec_id)
            if actual != wanted:
                raise ValueError(
                    f"launch provenance {side} assignment must match runner "
                    "player/loadout/pilot bindings"
                )
        return provenance

    # ------------------------------------------------------------------
    # Intent resolution (live-only; canonical truth is the emitted events)
    # ------------------------------------------------------------------

    def _resolve_intent(self, intent: ModelSOEventEnvelope) -> None:
        state = self.fold.state
        mech = state.mech_states.get(intent.subject.mech_id)
        if mech is None or not mech.alive or not mech.pilot_alive:
            return  # the mech died earlier this tick — its intent is void
        match intent.event_type:
            case SOEventType.MOVE_INTENT:
                self._resolve_move(intent, state, mech)
            case SOEventType.WEAPON_FIRE_INTENT:
                self._resolve_weapon_fire(intent, state, mech)
            case SOEventType.MODE_SWITCH_INTENT:
                self._resolve_mode_switch(intent, state, mech)
            case SOEventType.VENT_INTENT:
                ModelSOEmptyPayload.model_validate(intent.payload)
            case _:
                pass

    def _living_opponent(
        self, state: ModelSOMatchState, mech: ModelSOMechRuntimeState
    ) -> ModelSOMechRuntimeState | None:
        for other in state.living_mechs():
            if other.player_id != mech.player_id:
                return other
        return None

    def _resolve_move(
        self,
        intent: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> None:
        payload = ModelSOMoveIntentPayload.model_validate(intent.payload)
        direction = payload.direction
        if direction == "hold_position":
            return
        enemy = self._living_opponent(state, mech)
        if enemy is None:
            return

        budget = min(effective_speed(mech), mech.boiler.pressure_current)
        if budget <= 0:
            return

        from_pos = mech.position
        if direction == "toward_enemy":
            distance = chebyshev(from_pos, enemy.position)
            step = min(budget, max(0, distance - 1))  # never enter the enemy's cell
            dx = _clamp(enemy.position.x - from_pos.x, step)
            dy = _clamp(enemy.position.y - from_pos.y, step)
        elif direction == "defensive":  # open distance from the enemy
            step = budget
            dx = _clamp(from_pos.x - enemy.position.x, step)
            dy = _clamp(from_pos.y - enemy.position.y, step)
        elif direction in ("flank_left", "flank_right"):
            # Rotate the sign-clamped mech→enemy axis by 90 degrees.  This is
            # structurally perpendicular, so a flank cannot collapse into the
            # old toward/away beeline even when the model asks for one.
            axis_x = _sign(enemy.position.x - from_pos.x)
            axis_y = _sign(enemy.position.y - from_pos.y)
            if direction == "flank_left":
                perp_x, perp_y = axis_y, -axis_x
            else:
                perp_x, perp_y = -axis_y, axis_x
            dx = perp_x * budget
            dy = perp_y * budget
        else:  # toward_cover
            # Obstacles are impassable in the current arena contract.  Move
            # toward the nearest obstacle but stop one legal cell before it;
            # an empty arena or already-adjacent cover is a deterministic no-op.
            cover_targets = sorted(
                self._obstacles,
                key=lambda cell: (
                    max(abs(cell[0] - from_pos.x), abs(cell[1] - from_pos.y)),
                    cell[0],
                    cell[1],
                ),
            )
            if not cover_targets:
                return
            cover = ModelSOPosition(x=cover_targets[0][0], y=cover_targets[0][1])
            distance = chebyshev(from_pos, cover)
            step = min(budget, max(0, distance - 1))
            dx = _clamp(cover.x - from_pos.x, step)
            dy = _clamp(cover.y - from_pos.y, step)

        intended = ModelSOPosition(
            x=min(max(from_pos.x + dx, 0), self._arena_size - 1),
            y=min(max(from_pos.y + dy, 0), self._arena_size - 1),
        )
        to_pos = self._walk_to(from_pos, intended)
        moved = chebyshev(from_pos, to_pos)
        if moved == 0 and self._obstacles:
            to_pos = greedy_sidestep(
                from_pos,
                enemy.position,
                obstacles=self._obstacles,
                size=self._arena_size,
                toward=direction == "toward_enemy",
                forbidden=frozenset({(enemy.position.x, enemy.position.y)}),
            )
            moved = chebyshev(from_pos, to_pos)
        if moved == 0:
            return  # pinned against the arena edge, terrain, or already adjacent

        self._bus.publish(
            self._make_subject_event(
                SOEventType.MOVEMENT_RESOLVED,
                tick=state.tick,
                mech=mech,
                payload={
                    "from": {"x": from_pos.x, "y": from_pos.y},
                    "to": {"x": to_pos.x, "y": to_pos.y},
                    "ticks_consumed": 1,
                    "pressure_consumed": moved,
                },
                caused_by_intent=intent,
            )
        )

    def _walk_to(
        self,
        from_pos: ModelSOPosition,
        intended: ModelSOPosition,
    ) -> ModelSOPosition:
        last = from_pos
        for x, y in chebyshev_line(from_pos, intended):
            if (x, y) in self._obstacles:
                break
            last = ModelSOPosition(x=x, y=y)
        return last

    def _resolve_weapon_fire(
        self,
        intent: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> None:
        payload = ModelSOWeaponFireIntentPayload.model_validate(intent.payload)
        weapon_id = payload.weapon_id
        spec = self._catalog.weapons.get(weapon_id)
        if spec is None:
            raise UnknownWeaponError(weapon_id, owner_id=mech.mech_id)

        target_param = payload.target_mech_id
        target = (
            state.mech_states.get(target_param)
            if target_param is not None
            else self._living_opponent(state, mech)
        )
        if target is None:
            self._bus.publish(
                self._make_subject_event(
                    SOEventType.WEAPON_FIRE_REJECTED,
                    tick=state.tick,
                    mech=mech,
                    payload=ModelSOWeaponFireRejectedPayload(
                        weapon_id=weapon_id,
                        target_id=target_param,
                        reason="target_not_found",
                    ).model_dump(mode="json"),
                    caused_by_intent=intent,
                )
            )
            return

        distance = chebyshev(mech.position, target.position)
        try:
            validate_weapon_fire_intent(
                weapon_id=weapon_id,
                pressure_cost=spec.pressure_cost,
                current_pressure=mech.boiler.pressure_current,
                weapon_cooldown=mech.weapon_cooldowns.get(weapon_id, 0),
                distance=distance,
                weapon_range=spec.range,
                target_alive=target.alive and target.pilot_alive,
            )
        except ReducerError as exc:
            reason = str(exc).split(":", 1)[0]
            if reason not in {
                "insufficient_pressure",
                "weapon_on_cooldown",
                "target_out_of_range",
                "target_not_alive",
            }:
                raise RuntimeError(
                    f"weapon validation returned an unregistered rejection reason: {reason!r}"
                ) from exc
            self._bus.publish(
                self._make_subject_event(
                    SOEventType.WEAPON_FIRE_REJECTED,
                    tick=state.tick,
                    mech=mech,
                    payload=ModelSOWeaponFireRejectedPayload(
                        weapon_id=weapon_id,
                        target_id=target.mech_id,
                        reason=cast(WeaponFireRejectionReason, reason),
                    ).model_dump(mode="json"),
                    caused_by_intent=intent,
                )
            )
            return

        if not line_of_sight_clear(mech.position, target.position, self._obstacles):
            self._bus.publish(
                self._make_subject_event(
                    SOEventType.WEAPON_FIRED,
                    tick=state.tick,
                    mech=mech,
                    payload={
                        "weapon_id": weapon_id,
                        "target_id": target.mech_id,
                        "hit_probability": 0.0,
                        "pressure_cost": spec.pressure_cost,
                        "heat_generated": spec.heat_generated,
                    },
                    caused_by_intent=intent,
                )
            )
            return

        curve = [(point.range, point.hit_probability) for point in spec.accuracy_curve]
        base_accuracy = interpolate_accuracy(curve, distance)
        lock_confidence = 0.0
        for observation in self._sensor_buffer:
            if observation.subject.mech_id != mech.mech_id:
                continue
            sensor_payload = ModelSOSensorObservationPayload.model_validate(observation.payload)
            if sensor_payload.enemy_mech_id == target.mech_id:
                lock_confidence = max(lock_confidence, sensor_payload.confidence)
        hit_probability = resolve_hit_probability(
            base_accuracy,
            lock_confidence,
            target.evasion,
            mech.accuracy_penalty_next_fire,
        )
        hit = roll_hit(
            rng=self._rng,
            tick=state.tick,
            mech_id=mech.mech_id,
            hit_probability=hit_probability,
        )

        self._bus.publish(
            self._make_subject_event(
                SOEventType.WEAPON_FIRED,
                tick=state.tick,
                mech=mech,
                payload={
                    "weapon_id": weapon_id,
                    "target_id": target.mech_id,
                    "hit_probability": hit_probability,
                    "pressure_cost": spec.pressure_cost,
                    "heat_generated": spec.heat_generated,
                },
                caused_by_intent=intent,
            )
        )
        if not hit:
            return

        # --- Damage chain (Task 25) ---------------------------------------
        damage_type = spec.damage_type
        effectiveness = spec.target_class_effectiveness[target.chassis_class]
        damage_raw = int(spec.damage * effectiveness)
        armor_reduction = compute_armor_reduction(
            damage_raw=damage_raw,
            armor_value=target.armor_value,
            weapon_damage_type=damage_type,
        )
        absorbed = armor_reduction.absorbed
        vulnerability = self._catalog.chassis[target.chassis_id].penalties.heat_weapon_vulnerability
        effective = compute_effective_damage_after_vulnerability(
            damage_after_armor=damage_raw - absorbed,
            weapon_damage_type=damage_type,
            heat_weapon_vulnerability=vulnerability,
        )

        self._bus.publish(
            self._make_subject_event(
                SOEventType.HIT_RESOLVED,
                tick=state.tick,
                mech=mech,
                payload={
                    "attacker_id": mech.mech_id,
                    "defender_id": target.mech_id,
                    "result": {"hit": True, "damage_after_armor": effective},
                },
            )
        )
        self._bus.publish(
            self._make_subject_event(
                SOEventType.ARMOR_ABSORBED,
                tick=state.tick,
                mech=target,
                payload={
                    "target_id": target.mech_id,
                    "absorbed_amount": absorbed,
                    # Post-hit armor value; the fold degrades armor_value to this.
                    "armor_after": armor_reduction.armor_after,
                },
            )
        )
        # Re-read the target post-WEAPON_FIRED fold (its hp is unchanged by the
        # firing, but the fold is the single source of truth).
        target_now = self.fold.state.mech_states[target.mech_id]
        hp_after = max(0, target_now.hp - effective)
        self._bus.publish(
            self._make_subject_event(
                SOEventType.DAMAGE_APPLIED,
                tick=state.tick,
                mech=target,
                payload={
                    "target_id": target.mech_id,
                    "damage": effective,
                    "cause": "weapon_hit",
                    "hp_after": hp_after,
                    "source_mech_id": mech.mech_id,
                },
            )
        )
        if hp_after == 0:
            self._bus.publish(
                self._make_subject_event(
                    SOEventType.MECH_DESTROYED,
                    tick=state.tick,
                    mech=target,
                    payload={"cause": "weapon_damage", "source_mech_id": mech.mech_id},
                )
            )

    def _resolve_mode_switch(
        self,
        intent: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> None:
        try:
            payload = ModelSOModeSwitchIntentPayload.model_validate(intent.payload)
        except ValidationError:
            return  # malformed/unknown mode intent is non-canonical and silently dropped
        to_mode = payload.target_mode
        if mech.transition_ticks_remaining > 0:
            return  # already mid-transition
        transition = self._catalog.transitions.get((mech.current_mode, to_mode))
        if transition is None:
            return  # unknown directed pair
        if not validate_mode_switch(mech, transition, mech.current_mode, state.tick):
            return  # silent drop — PILOT_DECISION_MADE records the attempt
        self._bus.publish(
            build_mode_transition_started_event(
                event_factory=self._events,
                match_id=self._match_id,
                correlation_id=self._correlation_id,
                causation_id=intent.envelope.message_id,
                tick=state.tick,
                mech=mech,
                transition=transition,
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_mech(
        self,
        loadout: ModelSOLoadout,
        *,
        mech_id: str,
        player_id: str,
        side: Literal["red", "blue"],
        position: ModelSOPosition,
        facing: int,
    ) -> ModelSOMechRuntimeState:
        chassis = self._catalog.chassis[loadout.chassis_id]
        boiler_spec = self._catalog.boilers[loadout.boiler_id]
        for weapon_id in loadout.modules.weapons:
            _require_weapon_spec(self._catalog, weapon_id, owner_id=loadout.id)
        boiler = ModelSOBoilerState(
            match_id=self._match_id,
            mech_id=mech_id,
            tick=0,
            # Start at half pressure: regeneration is observable from tick 1.
            pressure_current=boiler_spec.pressure_capacity // 2,
            pressure_maximum=boiler_spec.pressure_capacity,
            regeneration_per_tick=boiler_spec.regen_per_tick,
            heat_current=0,
            heat_redline_threshold=boiler_spec.redline_threshold,
            heat_rupture_threshold=boiler_spec.rupture_threshold,
            heat_vent_rate=boiler_spec.vent_rate,
            status_redline=False,
            status_rupture_warning=False,
            status_disabled=False,
            status_ruptured=False,
            modifier_heat_weapon_pressure=1.0,
            modifier_venting_penalty=0.0,
            modifier_mode_switch_heat_delta=0,
        )
        return ModelSOMechRuntimeState(
            mech_id=mech_id,
            player_id=player_id,
            side=side,
            loadout_id=loadout.id,
            pilot_id=loadout.pilot_id,
            chassis_id=chassis.id,
            chassis_class=chassis.chassis_class,
            sensor_ids=tuple(loadout.modules.sensors),
            gizmo_ids=tuple(loadout.modules.gizmos),
            base_speed=chassis.constraints.base_speed,
            position=position,
            facing=facing,
            speed=mode_effective_speed(chassis.constraints.base_speed, _INITIAL_MODE),
            hp=chassis.constraints.base_hp,
            hp_max=chassis.constraints.base_hp,
            armor_value=chassis.constraints.base_armor,
            armor_max=chassis.constraints.base_armor,
            current_mode=_INITIAL_MODE,
            weapon_cooldowns={weapon_id: 0 for weapon_id in loadout.modules.weapons},
            boiler=boiler,
        )

    def _make_match_event(
        self, event_type: SOEventType, *, tick: int, payload: dict[str, Any]
    ) -> ModelSOEventEnvelope:
        return self._events.make(
            match_id=self._match_id,
            tick=tick,
            sequence_in_tick=0,  # bus re-stamps
            event_type=event_type,
            producer_node=_PRODUCER_NODE,
            subject=_MATCH_SUBJECT,
            payload=payload,
            # Match-scoped correlation id, shared across all events of this match
            # (the ONEX workflow identity). Root events (MATCH_STARTED) carry no
            # causation_id; subsequent events chain off it where applicable.
            correlation_id=self._correlation_id,
        )

    def _make_subject_event(
        self,
        event_type: SOEventType,
        *,
        tick: int,
        mech: ModelSOMechRuntimeState,
        payload: dict[str, Any],
        caused_by_intent: ModelSOEventEnvelope | None = None,
    ) -> ModelSOEventEnvelope:
        """Build a mech-scoped event; optionally chains causation off an intent.

        When *caused_by_intent* is set (a resolved event produced from a pilot
        intent), the new event's causation_id links to that intent's
        message_id — the ONEX causation chain that lets a downstream consumer
        trace WEAPON_FIRED back to the WEAPON_FIRE_INTENT that triggered it.
        """
        if caused_by_intent is not None:
            return self._events.caused_by(
                caused_by_intent,
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,  # bus re-stamps
                event_type=event_type,
                producer_node=_PRODUCER_NODE,
                subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
                payload=payload,
            )
        return self._events.make(
            match_id=self._match_id,
            tick=tick,
            sequence_in_tick=0,  # bus re-stamps
            event_type=event_type,
            producer_node=_PRODUCER_NODE,
            subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
            payload=payload,
            correlation_id=self._correlation_id,
        )


# ---------------------------------------------------------------------------
# Budget validation (Task 34 entrypoint step: "validate budgets")
# ---------------------------------------------------------------------------


def _module_budgets(
    loadout: ModelSOLoadout, catalog: MatchContractCatalog
) -> list[ModelSOModuleBudget]:
    """Normalize fielded modules into budget entries (design §15.3 axes).

    Normalization conventions (documented, per module category):
      - weapons: 1 slot; no steady-state pressure draw (firing costs are
        event-based); ``heat_generated`` as the per-activation heat proxy;
        active in assault.  Weapon contracts carry no mass field, so the mass
        axis covers gizmos only at MVP.
      - sensors: 1 slot; steady-state ``pressure_draw_per_tick`` /
        ``heat_per_tick`` / ``signature_impact``; active in every mode.
      - gizmos: contract-declared mass + slots; active in every mode.
    """
    if loadout.modules.cooling or loadout.modules.armor:
        raise ValueError(
            f"loadout {loadout.id!r} fields cooling/armor modules, but no cooling/armor "
            "module contracts exist in contracts_data/ yet"
        )
    entries: list[ModelSOModuleBudget] = []
    for weapon_id in loadout.modules.weapons:
        weapon = _require_weapon_spec(catalog, weapon_id, owner_id=loadout.id)
        entries.append(
            ModelSOModuleBudget(
                module_id=weapon_id,
                mass=0,
                slots=1,
                pressure_draw=0.0,
                heat_output=float(weapon.heat_generated),
                signature_impact=0.0,
                active_modes=(ModeId.ASSAULT,),
            )
        )
    for sensor_id in loadout.modules.sensors:
        sensor = catalog.sensors[sensor_id]
        entries.append(
            ModelSOModuleBudget(
                module_id=sensor_id,
                mass=0,
                slots=1,
                pressure_draw=sensor.pressure_draw_per_tick,
                heat_output=sensor.heat_per_tick,
                signature_impact=sensor.signature_impact,
                active_modes=_ALL_MODES,
            )
        )
    for gizmo_id in loadout.modules.gizmos:
        gizmo = catalog.gizmos[gizmo_id]
        # ModelSOGizmoSpec keeps constraints as a free-form dict; re-validate
        # through the typed constraints model for mass/slots access.
        constraints = ModelSOGizmoConstraints.model_validate(gizmo.constraints)
        entries.append(
            ModelSOModuleBudget(
                module_id=gizmo_id,
                mass=constraints.mass,
                slots=constraints.slots,
                pressure_draw=0.0,
                heat_output=0.0,
                signature_impact=0.0,
                active_modes=_ALL_MODES,
            )
        )
    return entries


def _require_weapon_spec(
    catalog: MatchContractCatalog,
    weapon_id: str,
    *,
    owner_id: str,
) -> ModelSOWeaponSpec:
    """Resolve one weapon contract or fail with a stable typed error."""
    spec = catalog.weapons.get(weapon_id)
    if spec is None:
        raise UnknownWeaponError(weapon_id, owner_id=owner_id)
    return spec


def _require_valid_budgets(loadout: ModelSOLoadout, catalog: MatchContractCatalog) -> None:
    """Raise ``ValueError`` listing every violated budget axis (fail fast)."""
    violations = validate_loadout_budgets(
        loadout,
        catalog.chassis[loadout.chassis_id],
        catalog.boilers[loadout.boiler_id],
        _module_budgets(loadout, catalog),
    )
    if violations:
        details = ", ".join(
            f"{violation.kind.value} used={violation.used} max={violation.max}"
            for violation in violations
        )
        raise ValueError(f"loadout {loadout.id!r} violates budgets: {details}")
