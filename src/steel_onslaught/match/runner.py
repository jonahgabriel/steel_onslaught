"""Minimal synchronous tick-loop match runner — Task 28.

Composes the reducer stack available today — lifecycle (Task 18), boiler
(Task 22), sensors (Task 20), pilot tick (Task 21) — into a deterministic
synchronous match loop driven over an ``EventBus``.  Task 34 finalises the
full wiring (movement, mode, weapons, damage, failure cascade, leaderboard
handler, WebSocket bridge).

Per tick the runner:
  1. publishes ``MATCH_TICK`` (the lifecycle reducer folds it and terminates
     the match at the ``max_ticks`` bound),
  2. folds each mech's boiler reducer (pressure regen / heat vent emissions),
  3. folds the sensor reducer (deterministic noisy ``SENSOR_OBSERVATION``s),
  4. folds the pilot tick reducer (``PILOT_DECISION_MADE`` + intent events).

All stochastic behaviour flows through ``MatchRng`` sub-seeds inside the
reducers, so the full event stream is a pure function of
``(seed, loadouts, max_ticks)``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ulid
import yaml  # type: ignore[import-untyped]

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec, ModelSOBoilerState
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchStatus,
)
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol
from steel_onslaught.reducers.boiler import ReducerBoiler
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle
from steel_onslaught.reducers.pilot_tick import ReducerPilotTick
from steel_onslaught.reducers.sensors import ReducerSensors

_PRODUCER_NODE = "node.match.runner"

# Match-scoped events have no single mech/player subject.
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# Resolve contracts_data/ relative to this file's package tree (same
# convention as ledger/migrate.py): src/steel_onslaught/match/runner.py
# -> project root is 4 levels up.
_CONTRACTS_DATA_DIR = Path(__file__).parent.parent.parent.parent / "contracts_data"

# Fixed spawn geometry for the minimal two-mech duel.  10 Chebyshev cells
# apart so short-range sensors (range 15) acquire from tick 1.
_SPAWN_A = ModelSOPosition(x=0, y=0)
_SPAWN_B = ModelSOPosition(x=10, y=10)
_FACING_A = 45
_FACING_B = 225

# Provisional combat stats until the loadout-derived values land (Task 34).
_INITIAL_HP = 100
_INITIAL_ARMOR = 10
_INITIAL_MODE = "recon"


def load_loadout(path: Path) -> ModelSOLoadout:
    """Load and validate one loadout contract YAML."""
    return ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _load_chassis_index(directory: Path) -> dict[str, ModelSOChassisSpec]:
    specs = [
        ModelSOChassisSpec.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        for f in sorted(directory.glob("*.yaml"))
    ]
    return {spec.id: spec for spec in specs}


def _load_boiler_index(directory: Path) -> dict[str, ModelSOBoilerSpec]:
    specs = [
        ModelSOBoilerSpec.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        for f in sorted(directory.glob("*.yaml"))
    ]
    return {spec.id: spec for spec in specs}


def _load_sensor_index(directory: Path) -> dict[str, ModelSOSensorSpec]:
    specs = [
        ModelSOSensorSpec.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        for f in sorted(directory.glob("*.yaml"))
    ]
    return {spec.id: spec for spec in specs}


def _pilot_for(pilot_id: str) -> PilotProtocol:
    """Map a loadout ``pilot_id`` to its archetype implementation."""
    if "aggressive" in pilot_id:
        return AggressivePilot()
    if "defensive" in pilot_id:
        return DefensivePilot()
    if "predictive" in pilot_id:
        return PredictivePilot()
    raise ValueError(f"unknown pilot archetype in pilot_id {pilot_id!r}")


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
    ) -> None:
        self._match_id = match_id
        self._seed = seed
        self._loadout_a = loadout_a
        self._loadout_b = loadout_b
        self._bus = bus
        self._max_ticks = max_ticks
        data_dir = contracts_data_dir if contracts_data_dir is not None else _CONTRACTS_DATA_DIR
        self._chassis_index = _load_chassis_index(data_dir / "chassis")
        self._boiler_index = _load_boiler_index(data_dir / "boilers")
        self._sensor_index = _load_sensor_index(data_dir / "sensors")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> ModelSOMatchState:
        """Drive the match to termination; return the final match state."""
        lifecycle = ReducerMatchLifecycle(self._match_id, bus=self._bus)
        self._bus.subscribe(lifecycle.handle)

        mech_a = self._build_mech(
            self._loadout_a,
            mech_id="mech.a.01",
            player_id="player.a",
            position=_SPAWN_A,
            facing=_FACING_A,
        )
        mech_b = self._build_mech(
            self._loadout_b,
            mech_id="mech.b.01",
            player_id="player.b",
            position=_SPAWN_B,
            facing=_FACING_B,
        )
        mechs = (mech_a, mech_b)
        pilots: dict[str, PilotProtocol] = {
            mech.mech_id: _pilot_for(mech.pilot_id) for mech in mechs
        }

        # Buffer SENSOR_OBSERVATION events per tick for the pilot reducer.
        sensor_buffer: list[ModelSOEventEnvelope] = []
        self._bus.subscribe(sensor_buffer.append, event_types=[SOEventType.SENSOR_OBSERVATION])

        self._bus.publish(
            self._make_event(
                SOEventType.MATCH_STARTED,
                tick=0,
                payload={
                    "seed": self._seed,
                    "max_ticks": self._max_ticks,
                    "mechs": [mech.model_dump(mode="json") for mech in mechs],
                },
            )
        )

        state = ModelSOMatchState(
            match_id=self._match_id,
            tick=0,
            status=SOMatchStatus.RUNNING,
            seed=self._seed,
            max_ticks=self._max_ticks,
            mech_states={mech.mech_id: mech for mech in mechs},
        )
        boiler_reducers = {
            mech.mech_id: ReducerBoiler(mech.mech_id, state, emit=self._bus.publish)
            for mech in mechs
        }

        while lifecycle.state.status is SOMatchStatus.RUNNING:
            next_tick = lifecycle.state.tick + 1
            tick_event = self._make_event(SOEventType.MATCH_TICK, tick=next_tick, payload={})
            self._bus.publish(tick_event)
            if lifecycle.state.status is not SOMatchStatus.RUNNING:
                break  # terminal tick — the lifecycle reducer ended the match

            state = state.model_copy(update={"tick": next_tick})
            for reducer in boiler_reducers.values():
                state = reducer.apply(tick_event, state)

            sensor_buffer.clear()
            sensors = ReducerSensors(
                self._match_id, state, self._sensor_index, emit=self._bus.publish
            )
            sensors.apply(tick_event)

            pilot_tick = ReducerPilotTick(
                self._match_id,
                state,
                pilots,
                sensor_events=list(sensor_buffer),
                emit=self._bus.publish,
            )
            pilot_tick.apply(tick_event)

        # Terminal authority (status/winner/end_reason) comes from the
        # lifecycle reducer; mech runtime detail from the runner's fold.
        return lifecycle.state.model_copy(update={"mech_states": state.mech_states})

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
        chassis = self._chassis_index[loadout.chassis_id]
        boiler_spec = self._boiler_index[loadout.boiler_id]
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

    def _make_event(
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
