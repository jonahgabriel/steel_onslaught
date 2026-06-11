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

``run_match`` (Task 34) is the Proof-of-Life entrypoint: it wires the ledger,
the scoring reducer (with the replay-validity hard gate), and the leaderboard
handler around a ``MatchRunner`` and drives one duel to termination.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ulid
import yaml  # type: ignore[import-untyped]

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.budget import ModelSOModuleBudget, validate_loadout_budgets
from steel_onslaught.contracts.gizmo import ModelSOGizmoConstraints
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol
from steel_onslaught.projections.leaderboard.handler import LeaderboardHandler
from steel_onslaught.reducers.damage import (
    WeaponDamageType,
    compute_armor_reduction,
    compute_effective_damage_after_vulnerability,
)
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.mode import (
    build_mode_transition_started_event,
    validate_mode_switch,
)
from steel_onslaught.reducers.movement import chebyshev, effective_speed
from steel_onslaught.reducers.pilot_tick import ReducerPilotTick
from steel_onslaught.reducers.scoring import ReducerScoring, verify_replay_validity
from steel_onslaught.reducers.sensors import ReducerSensors
from steel_onslaught.reducers.weapons import (
    interpolate_accuracy,
    resolve_hit_probability,
    roll_hit,
    validate_weapon_fire_intent,
)

_PRODUCER_NODE = "node.match.runner"

# Match-scoped events have no single mech/player subject.
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# Arena: square grid of this many cells per side (positions 0..size-1).
ARENA_SIZE_CELLS = 40

# Default spawn geometry for the minimal two-mech duel (Task 28 tests).
# 10 Chebyshev cells apart so short-range sensors (range 15) acquire from tick 1.
_SPAWN_A = ModelSOPosition(x=0, y=0)
_SPAWN_B = ModelSOPosition(x=10, y=10)
_FACING_A = 45
_FACING_B = 225

# Combat stats: hull/armor are not part of any contract yet (no hp field on
# chassis contracts), so every mech fields the same provisional hull.
_INITIAL_HP = 100
_INITIAL_ARMOR = 10
_INITIAL_MODE = "recon"

# All mode names a module may be active in (budget normalization).
_ALL_MODES = ("recon", "assault", "evasion")

_INTENT_EVENT_TYPES = [
    SOEventType.MOVE_INTENT,
    SOEventType.WEAPON_FIRE_INTENT,
    SOEventType.MODE_SWITCH_INTENT,
    SOEventType.VENT_INTENT,
]


def load_loadout(path: Path) -> ModelSOLoadout:
    """Load and validate one loadout contract YAML."""
    return ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


_PILOTS_DIR = Path(__file__).parent.parent.parent.parent / "contracts_data" / "pilots"


def _load_aggressive_template() -> AggressivePilot:
    """Load the template aggressive spec and return a spec-driven pilot."""
    from steel_onslaught.contracts.pilot import ModelSOPilotSpec

    raw = yaml.safe_load((_PILOTS_DIR / "template_aggressive.yaml").read_text(encoding="utf-8"))
    spec = ModelSOPilotSpec.model_validate(raw)
    return AggressivePilot(spec=spec)


def _pilot_for(pilot_id: str) -> PilotProtocol:
    """Map a loadout ``pilot_id`` to its archetype implementation."""
    if "aggressive" in pilot_id:
        return _load_aggressive_template()
    if "defensive" in pilot_id:
        return DefensivePilot()
    if "predictive" in pilot_id:
        return PredictivePilot()
    raise ValueError(f"unknown pilot archetype in pilot_id {pilot_id!r}")


def _clamp(value: int, magnitude: int) -> int:
    return max(-magnitude, min(magnitude, value))


class MatchRunner:
    """Synchronous tick-loop driver for one two-mech match."""

    def __init__(
        self,
        *,
        match_id: str,
        seed: int,
        loadout_a: ModelSOLoadout,
        loadout_b: ModelSOLoadout,
        bus: EventBus,
        max_ticks: int = 200,
        contracts_data_dir: Path | None = None,
        catalog: MatchContractCatalog | None = None,
        side_a: str = "a",
        side_b: str = "b",
        spawn_a: ModelSOPosition = _SPAWN_A,
        spawn_b: ModelSOPosition = _SPAWN_B,
        facing_a: int = _FACING_A,
        facing_b: int = _FACING_B,
        arena_size: int = ARENA_SIZE_CELLS,
    ) -> None:
        self._match_id = match_id
        self._seed = seed
        self._rng = MatchRng(match_seed=seed)
        self._loadout_a = loadout_a
        self._loadout_b = loadout_b
        self._bus = bus
        self._max_ticks = max_ticks
        self._side_a = side_a
        self._side_b = side_b
        self._spawn_a = spawn_a
        self._spawn_b = spawn_b
        self._facing_a = facing_a
        self._facing_b = facing_b
        self._arena_size = arena_size
        self._catalog = (
            catalog if catalog is not None else MatchContractCatalog.load(contracts_data_dir)
        )

        # Canonical state fold — the same fold the replay engine uses.
        # Subscribed at construction time so callers can order later
        # subscribers (scoring, leaderboard) AFTER the fold.
        self.fold = MatchStateFold(match_id, bus=bus, catalog=self._catalog)
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

    def run(self) -> ModelSOMatchState:
        """Drive the match to termination; return the final match state."""
        mech_a = self._build_mech(
            self._loadout_a,
            mech_id=f"mech.{self._side_a}.01",
            player_id=f"player.{self._side_a}",
            position=self._spawn_a,
            facing=self._facing_a,
        )
        mech_b = self._build_mech(
            self._loadout_b,
            mech_id=f"mech.{self._side_b}.01",
            player_id=f"player.{self._side_b}",
            position=self._spawn_b,
            facing=self._facing_b,
        )
        mechs = (mech_a, mech_b)
        pilots: dict[str, PilotProtocol] = {
            mech.mech_id: _pilot_for(mech.pilot_id) for mech in mechs
        }

        self._bus.publish(
            self._make_match_event(
                SOEventType.MATCH_STARTED,
                tick=0,
                payload={
                    "seed": self._seed,
                    "max_ticks": self._max_ticks,
                    "mechs": [mech.model_dump(mode="json") for mech in mechs],
                },
            )
        )

        while self.fold.state.status is SOMatchStatus.RUNNING:
            next_tick = self.fold.state.tick + 1
            self._sensor_buffer.clear()
            self._intent_buffer.clear()

            tick_event = self._make_match_event(SOEventType.MATCH_TICK, tick=next_tick, payload={})
            self._bus.publish(tick_event)
            if self.fold.state.status is not SOMatchStatus.RUNNING:
                break  # terminal tick (max_ticks bound or failure-cascade kill)

            ReducerSensors(
                self._match_id, self.fold.state, self._catalog.sensors, emit=self._bus.publish
            ).apply(tick_event)

            ReducerPilotTick(
                self._match_id,
                self.fold.state,
                pilots,
                sensor_events=list(self._sensor_buffer),
                emit=self._bus.publish,
                weapon_specs=self._catalog.weapons,
            ).apply(tick_event)

            for intent in list(self._intent_buffer):
                if self.fold.state.status is not SOMatchStatus.RUNNING:
                    break  # an earlier resolution ended the match
                self._resolve_intent(intent)

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
            case _:
                pass  # VENT_INTENT: ambient venting only (boiler vents per tick)

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
        direction = str(intent.payload.get("direction", ""))
        if direction not in {"toward_enemy", "defensive"}:
            return  # hold position (defensive "maintain range" / disengage-in-place)
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
        else:  # defensive: open distance from the enemy
            step = budget
            dx = _clamp(from_pos.x - enemy.position.x, step)
            dy = _clamp(from_pos.y - enemy.position.y, step)

        to_pos = ModelSOPosition(
            x=min(max(from_pos.x + dx, 0), self._arena_size - 1),
            y=min(max(from_pos.y + dy, 0), self._arena_size - 1),
        )
        moved = chebyshev(from_pos, to_pos)
        if moved == 0:
            return  # pinned against the arena edge or already adjacent

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
            )
        )

    def _resolve_weapon_fire(
        self,
        intent: ModelSOEventEnvelope,
        state: ModelSOMatchState,
        mech: ModelSOMechRuntimeState,
    ) -> None:
        weapon_id = str(intent.payload.get("weapon_id", ""))
        spec = self._catalog.weapons.get(weapon_id)
        if spec is None:
            return

        target_param = intent.payload.get("target_mech_id")
        target = (
            state.mech_states.get(str(target_param))
            if target_param is not None
            else self._living_opponent(state, mech)
        )
        if target is None:
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
        except ReducerError:
            return  # rejected: PILOT_DECISION_MADE already records the attempt

        curve = [(point.range, point.hit_probability) for point in spec.accuracy_curve]
        base_accuracy = interpolate_accuracy(curve, distance)
        lock_confidence = max(
            (
                float(observation.payload["confidence"])
                for observation in self._sensor_buffer
                if observation.subject.mech_id == mech.mech_id
                and str(observation.payload.get("enemy_mech_id")) == target.mech_id
            ),
            default=0.0,
        )
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
            )
        )
        if not hit:
            return

        # --- Damage chain (Task 25) ---------------------------------------
        damage_type = WeaponDamageType.HEAT if "heat" in weapon_id else WeaponDamageType.STANDARD
        effectiveness = spec.target_class_effectiveness.get(target.chassis_class, 1.0)
        damage_raw = int(spec.damage * effectiveness)
        absorbed = compute_armor_reduction(
            damage_raw=damage_raw,
            armor_value=target.armor_value,
            weapon_damage_type=damage_type,
        )
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
                payload={"target_id": target.mech_id, "absorbed_amount": absorbed},
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
        to_mode = str(intent.payload.get("target_mode", ""))
        if mech.transition_ticks_remaining > 0:
            return  # already mid-transition
        transition = self._catalog.transitions.get((mech.current_mode, to_mode))
        if transition is None:
            return  # unknown directed pair
        if not validate_mode_switch(mech, transition, mech.current_mode, state.tick):
            return  # silent drop — PILOT_DECISION_MADE records the attempt
        self._bus.publish(
            build_mode_transition_started_event(
                match_id=self._match_id,
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
        position: ModelSOPosition,
        facing: int,
    ) -> ModelSOMechRuntimeState:
        chassis = self._catalog.chassis[loadout.chassis_id]
        boiler_spec = self._catalog.boilers[loadout.boiler_id]
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
            loadout_id=loadout.id,
            pilot_id=loadout.pilot_id,
            chassis_id=chassis.id,
            chassis_class=chassis.chassis_class,
            sensor_ids=tuple(loadout.modules.sensors),
            gizmo_ids=tuple(loadout.modules.gizmos),
            base_speed=chassis.constraints.base_speed,
            position=position,
            facing=facing,
            speed=chassis.constraints.base_speed,
            hp=_INITIAL_HP,
            hp_max=_INITIAL_HP,
            armor_value=_INITIAL_ARMOR,
            current_mode=_INITIAL_MODE,
            weapon_cooldowns={weapon_id: 0 for weapon_id in loadout.modules.weapons},
            boiler=boiler,
        )

    def _make_match_event(
        self, event_type: SOEventType, *, tick: int, payload: dict[str, Any]
    ) -> ModelSOEventEnvelope:
        return ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=self._match_id,
            tick=tick,
            sequence_in_tick=0,  # bus re-stamps
            event_type=event_type,
            producer_node=_PRODUCER_NODE,
            subject=_MATCH_SUBJECT,
            payload=payload,
            emitted_at=datetime.now(UTC).isoformat(),
        )

    def _make_subject_event(
        self,
        event_type: SOEventType,
        *,
        tick: int,
        mech: ModelSOMechRuntimeState,
        payload: dict[str, Any],
    ) -> ModelSOEventEnvelope:
        return ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=self._match_id,
            tick=tick,
            sequence_in_tick=0,  # bus re-stamps
            event_type=event_type,
            producer_node=_PRODUCER_NODE,
            subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
            payload=payload,
            emitted_at=datetime.now(UTC).isoformat(),
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
        weapon = catalog.weapons[weapon_id]
        entries.append(
            ModelSOModuleBudget(
                module_id=weapon_id,
                mass=0,
                slots=1,
                pressure_draw=0.0,
                heat_output=float(weapon.heat_generated),
                signature_impact=0.0,
                active_modes=("assault",),
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


# ---------------------------------------------------------------------------
# Proof-of-Life entrypoint (Task 34)
# ---------------------------------------------------------------------------


def run_match(
    *,
    red_loadout: str | Path,
    blue_loadout: str | Path,
    seed: int,
    max_ticks: int,
    ledger_path: Path,
    leaderboard_path: Path,
    contracts_data_dir: Path | None = None,
) -> ModelSOMatchState:
    """Wire the full Task 1-33 stack and drive one red-vs-blue duel to its end.

    Composition (plan Task 34 step 3): load loadouts -> validate budgets ->
    spawn match (40x40 arena, 30 cells apart) -> register the canonical fold,
    scoring reducer (replay-validity hard gate), and leaderboard handler ->
    run the tick loop until VICTORY_DECLARED or the max_ticks bound -> emit
    the MATCH_ENDED re-statement -> MATCH_SCORED -> ledger flushed per event.

    Subscriber order matters and is fixed here: ledger first (the canonical
    record the replay-validity check reads), then the runner's fold, then
    scoring, then the leaderboard projection.
    """
    catalog = MatchContractCatalog.load(contracts_data_dir)
    red = load_loadout(Path(red_loadout))
    blue = load_loadout(Path(blue_loadout))
    _require_valid_budgets(red, catalog)
    _require_valid_budgets(blue, catalog)

    bus = InProcessEventBus()
    ledger = SQLiteLedger(ledger_path)
    bus.subscribe(ledger.append)  # 1st: every event lands in the ledger first

    match_id = f"match.{ulid.new().str}"
    runner = MatchRunner(  # 2nd: the canonical fold subscribes in __init__
        match_id=match_id,
        seed=seed,
        loadout_a=red,
        loadout_b=blue,
        bus=bus,
        max_ticks=max_ticks,
        catalog=catalog,
        side_a="red",
        side_b="blue",
        spawn_a=ModelSOPosition(x=5, y=5),
        spawn_b=ModelSOPosition(x=35, y=35),  # Chebyshev 30 apart on a 40x40 grid
        arena_size=ARENA_SIZE_CELLS,
    )

    scoring = ReducerScoring(  # 3rd: scores on the terminal event
        match_id,
        emit=bus.publish,
        replay_validity_check=lambda: verify_replay_validity(ledger, match_id, runner.fold.state),
    )
    bus.subscribe(scoring.handle)

    leaderboard = LeaderboardHandler(leaderboard_path)  # 4th: projection

    def _on_match_scored(event: ModelSOEventEnvelope) -> None:
        # The lifecycle reducer emits a skinny draw-backstop MATCH_SCORED;
        # only the scoring reducer's full payload feeds the leaderboard.
        if event.payload.get("kind") == "steel_onslaught.match_scored":
            leaderboard.on_match_scored(event.payload)

    bus.subscribe(_on_match_scored, event_types=[SOEventType.MATCH_SCORED])

    final = runner.run()

    # Hard gate (plan Task 29/34): a match whose ledger does not replay to the
    # live state must never be reported as healthy.
    if final.status is not SOMatchStatus.ENDED:
        raise RuntimeError(f"match {match_id!r} did not terminate: {final.status.value}")
    if final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS and final.winner_id is not None:
        raise RuntimeError("draw recorded a winner — lifecycle invariant violated")
    return final
