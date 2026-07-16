"""Tests for the pilot orchestrator invocation reducer — Task 21.

Invariants from the plan:
- Pilot is called exactly once per living mech per tick.
- Dead mechs (alive=False or pilot_alive=False) are not consulted.
- PILOT_DECISION_MADE is emitted before any downstream intent events.
- Pilot side effects do not leak into match state.
- Intent events are emitted to translate decisions into downstream actions:
    MOVE          -> MOVE_INTENT
    FIRE_WEAPON   -> WEAPON_FIRE_INTENT
    SWITCH_MODE   -> MODE_SWITCH_INTENT
    VENT          -> VENT_INTENT
    REMAIN / DISENGAGE / EMERGENCY_SHUTDOWN / ACTIVATE_MODULE -> no intent event
- Non-MATCH_TICK events are ignored.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.weapon import UnknownWeaponError
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPosition,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.reducers.pilot_tick import ReducerPilotTick

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

MATCH_ID = "match.pilot.001"
MECH_RED = "mech.red.01"
MECH_BLUE = "mech.blue.01"
PLAYER_RED = "player.red"
PLAYER_BLUE = "player.blue"
ULID = "01JABCDE0123456789ABCDEFGX"
_TEST_CORRELATION_ID = UUID(int=1)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC)


class _FixedIdentities:
    def new_match_id(self) -> str:
        return "match.test.fixed"

    def new_correlation_id(self) -> UUID:
        return _TEST_CORRELATION_ID

    def new_event_id(self) -> str:
        return ULID

    def new_message_id(self) -> UUID:
        return UUID(int=2)


_EVENT_FACTORY = EventFactory(clock=_FixedClock(), identities=_FixedIdentities())


def _onex_envelope(
    entity_id: str, emitted_at: datetime = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC)
) -> ModelEnvelope:
    """Composed ONEX ModelEnvelope."""
    return ModelEnvelope(
        message_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        entity_id=entity_id,
        emitted_at=emitted_at,
    )


def _boiler(
    pressure: int = 60,
    heat: int = 10,
    match_id: str = MATCH_ID,
    mech_id: str = MECH_RED,
) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=match_id,
        mech_id=mech_id,
        tick=0,
        pressure_current=pressure,
        pressure_maximum=100,
        regeneration_per_tick=4,
        heat_current=heat,
        heat_redline_threshold=80,
        heat_rupture_threshold=95,
        heat_vent_rate=2,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _mech(
    mech_id: str = MECH_RED,
    player_id: str = PLAYER_RED,
    alive: bool = True,
    pilot_alive: bool = True,
    pressure: int = 60,
    heat: int = 10,
    mode_lock_until: int = 0,
    weapon_cooldowns: dict[str, int] | None = None,
) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=player_id,
        loadout_id="loadout.test.01",
        pilot_id="pilot.test.01",
        chassis_id="chassis.light.scout_mk1",
        chassis_class="light",
        base_speed=2,
        position=ModelSOPosition(x=0, y=0),
        facing=90,
        speed=2,
        hp=100,
        hp_max=100,
        armor_value=5,
        armor_max=5,
        alive=alive,
        pilot_alive=pilot_alive,
        current_mode=ModeId.RECON,
        mode_lock_until=mode_lock_until,
        boiler=_boiler(pressure=pressure, heat=heat, mech_id=mech_id),
        weapon_cooldowns=weapon_cooldowns or {},
    )


def _match_state(
    mechs: list[ModelSOMechRuntimeState] | None = None,
    tick: int = 5,
) -> ModelSOMatchState:
    mech_list = mechs if mechs is not None else [_mech()]
    return ModelSOMatchState(
        match_id=MATCH_ID,
        tick=tick,
        status=SOMatchStatus.RUNNING,
        seed=42,
        max_ticks=200,
        mech_states={m.mech_id: m for m in mech_list},
    )


def _tick_event(tick: int = 5) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ULID,
        match_id=MATCH_ID,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        payload={},
        envelope=_onex_envelope(MATCH_ID),
    )


def _other_event() -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ULID,
        match_id=MATCH_ID,
        tick=5,
        sequence_in_tick=0,
        event_type=SOEventType.BOILER_UPDATED,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=MECH_RED, player_id=PLAYER_RED),
        payload={"heat": 10},
        envelope=_onex_envelope(MATCH_ID),
    )


# A pilot stub that always returns a fixed REMAIN decision and records call count.
class _StubPilot:
    def __init__(self, action: SOPilotAction = SOPilotAction.REMAIN) -> None:
        self.call_count = 0
        self._action = action
        self.last_observation: ModelSOPilotObservation | None = None

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        self.call_count += 1
        self.last_observation = observation
        return ModelSOPilotDecision(
            action=self._action,
            action_params={},
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=0.5,
            considered_actions=[ModelSOConsideredAction(action=self._action, score=0.5)],
        )


class _MovePilot:
    """Always returns MOVE."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.MOVE,
            action_params={"direction": "toward_enemy"},
            reason_code=SOPilotReasonCode.CLOSING_DISTANCE,
            confidence=0.7,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.MOVE, score=0.7)],
        )


class _FirePilot:
    """Always returns FIRE_WEAPON (requires a ready weapon in the observation)."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.FIRE_WEAPON,
            action_params={"weapon_id": "weapon.test.gun"},
            reason_code=SOPilotReasonCode.TARGET_IN_RANGE,
            confidence=0.9,
            considered_actions=[
                ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=0.9)
            ],
        )


class _SwitchModePilot:
    """Always returns SWITCH_MODE."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.SWITCH_MODE,
            action_params={"target_mode": "assault"},
            reason_code=SOPilotReasonCode.MODE_ADVANTAGE,
            confidence=0.8,
            considered_actions=[
                ModelSOConsideredAction(action=SOPilotAction.SWITCH_MODE, score=0.8)
            ],
        )


class _VentPilot:
    """Always returns VENT."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.VENT,
            action_params={},
            reason_code=SOPilotReasonCode.HEAT_CRITICAL,
            confidence=1.0,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.VENT, score=1.0)],
        )


def _make_reducer(
    state: ModelSOMatchState,
    pilots: dict[str, Any],
    sensor_events: list[ModelSOEventEnvelope] | None = None,
) -> tuple[ReducerPilotTick, list[ModelSOEventEnvelope]]:
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerPilotTick(
        match_id=MATCH_ID,
        state=state,
        pilots=pilots,
        sensor_events=sensor_events or [],
        emit=emitted.append,
        weapon_specs={},
        correlation_id=_TEST_CORRELATION_ID,
        event_factory=_EVENT_FACTORY,
    )
    return reducer, emitted


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_constructor_requires_explicit_weapon_specs() -> None:
    with pytest.raises(TypeError):
        ReducerPilotTick(  # type: ignore[call-arg]
            match_id=MATCH_ID,
            state=_match_state(),
            pilots={},
            sensor_events=[],
            emit=lambda _event: None,
            correlation_id=_TEST_CORRELATION_ID,
            event_factory=_EVENT_FACTORY,
        )


@pytest.mark.unit
def test_missing_weapon_contract_fails_closed_with_typed_error() -> None:
    unknown_id = "weapon.light.absent"
    state = _match_state([_mech(weapon_cooldowns={unknown_id: 0})])
    reducer, _emitted = _make_reducer(state, {MECH_RED: _StubPilot()})

    with pytest.raises(UnknownWeaponError) as raised:
        reducer.apply(_tick_event())

    assert raised.value.weapon_id == unknown_id
    assert raised.value.owner_id == MECH_RED
    assert str(raised.value) == (
        f"unknown_weapon_id: weapon {unknown_id!r} referenced by {MECH_RED!r} "
        "is absent from the injected weapon catalog"
    )


@pytest.mark.unit
def test_pilot_called_once_per_living_mech() -> None:
    """Pilot.decide is called exactly once per living mech on MATCH_TICK."""
    stub = _StubPilot()
    state = _match_state([_mech()])
    reducer, _ = _make_reducer(state, {MECH_RED: stub})
    reducer.apply(_tick_event())
    assert stub.call_count == 1


@pytest.mark.unit
def test_two_living_mechs_both_piloted() -> None:
    """Both living mechs have their pilots called once each."""
    stub_red = _StubPilot()
    stub_blue = _StubPilot()
    state = _match_state([_mech(MECH_RED, PLAYER_RED), _mech(MECH_BLUE, PLAYER_BLUE)])
    reducer, _ = _make_reducer(state, {MECH_RED: stub_red, MECH_BLUE: stub_blue})
    reducer.apply(_tick_event())
    assert stub_red.call_count == 1
    assert stub_blue.call_count == 1


@pytest.mark.unit
def test_dead_mech_hull_not_consulted() -> None:
    """A mech with alive=False must not have its pilot called."""
    stub = _StubPilot()
    dead = _mech(alive=False)
    state = _match_state([dead])
    reducer, _ = _make_reducer(state, {MECH_RED: stub})
    reducer.apply(_tick_event())
    assert stub.call_count == 0


@pytest.mark.unit
def test_dead_pilot_not_consulted() -> None:
    """A mech with pilot_alive=False must not have its pilot called."""
    stub = _StubPilot()
    dead_pilot = _mech(pilot_alive=False)
    state = _match_state([dead_pilot])
    reducer, _ = _make_reducer(state, {MECH_RED: stub})
    reducer.apply(_tick_event())
    assert stub.call_count == 0


@pytest.mark.unit
def test_pilot_decision_made_emitted_before_intents() -> None:
    """PILOT_DECISION_MADE event comes before any intent event in emission order."""
    state = _match_state([_mech()])
    reducer, emitted = _make_reducer(state, {MECH_RED: _MovePilot()})
    reducer.apply(_tick_event())

    types = [e.event_type for e in emitted]
    assert SOEventType.PILOT_DECISION_MADE in types
    decision_idx = types.index(SOEventType.PILOT_DECISION_MADE)
    intent_indices = [i for i, t in enumerate(types) if t == SOEventType.MOVE_INTENT]
    # Every intent must appear after the PILOT_DECISION_MADE
    for intent_idx in intent_indices:
        assert decision_idx < intent_idx, "PILOT_DECISION_MADE must precede intent events"


@pytest.mark.unit
def test_move_decision_emits_move_intent() -> None:
    """A MOVE decision produces a MOVE_INTENT event."""
    state = _match_state([_mech()])
    reducer, emitted = _make_reducer(state, {MECH_RED: _MovePilot()})
    reducer.apply(_tick_event())

    intent_events = [e for e in emitted if e.event_type == SOEventType.MOVE_INTENT]
    assert len(intent_events) == 1
    assert intent_events[0].subject.mech_id == MECH_RED


@pytest.mark.unit
def test_fire_weapon_decision_emits_weapon_fire_intent() -> None:
    """A FIRE_WEAPON decision produces a WEAPON_FIRE_INTENT event."""

    # Mech needs a ready weapon with enough pressure for the schema availability check
    mech = _mech(pressure=60)
    state = _match_state([mech])
    reducer, emitted = _make_reducer(state, {MECH_RED: _FirePilot()})
    reducer.apply(_tick_event())

    intent_events = [e for e in emitted if e.event_type == SOEventType.WEAPON_FIRE_INTENT]
    assert len(intent_events) == 1
    assert intent_events[0].payload["weapon_id"] == "weapon.test.gun"


@pytest.mark.unit
def test_switch_mode_decision_emits_mode_switch_intent() -> None:
    """A SWITCH_MODE decision produces a MODE_SWITCH_INTENT event."""
    # mode_lock_until=0, tick=5 => mode lock expired
    mech = _mech(mode_lock_until=0, pressure=60)
    state = _match_state([mech])
    reducer, emitted = _make_reducer(state, {MECH_RED: _SwitchModePilot()})
    reducer.apply(_tick_event())

    intent_events = [e for e in emitted if e.event_type == SOEventType.MODE_SWITCH_INTENT]
    assert len(intent_events) == 1
    assert intent_events[0].payload["target_mode"] == "assault"


@pytest.mark.unit
def test_vent_decision_emits_vent_intent() -> None:
    """A VENT decision produces a VENT_INTENT event."""
    state = _match_state([_mech()])
    reducer, emitted = _make_reducer(state, {MECH_RED: _VentPilot()})
    reducer.apply(_tick_event())

    intent_events = [e for e in emitted if e.event_type == SOEventType.VENT_INTENT]
    assert len(intent_events) == 1


@pytest.mark.unit
def test_remain_decision_emits_no_intent() -> None:
    """A REMAIN decision produces no downstream intent event."""
    state = _match_state([_mech()])
    reducer, emitted = _make_reducer(state, {MECH_RED: _StubPilot(SOPilotAction.REMAIN)})
    reducer.apply(_tick_event())

    intent_types = {
        SOEventType.MOVE_INTENT,
        SOEventType.WEAPON_FIRE_INTENT,
        SOEventType.MODE_SWITCH_INTENT,
        SOEventType.VENT_INTENT,
    }
    assert not any(e.event_type in intent_types for e in emitted)


@pytest.mark.unit
def test_non_match_tick_event_is_ignored() -> None:
    """Non-MATCH_TICK events are passed through without calling pilots."""
    stub = _StubPilot()
    state = _match_state([_mech()])
    reducer, emitted = _make_reducer(state, {MECH_RED: stub})
    reducer.apply(_other_event())
    assert stub.call_count == 0
    assert emitted == []


@pytest.mark.unit
def test_pilot_side_effects_do_not_affect_match_state() -> None:
    """Pilot side effects (mutation of observation) must not change match state."""

    class _SideEffectPilot:
        """Modifies a shared list as a side effect — only that list should change."""

        side_effects: list[str] = []  # noqa: RUF012

        def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
            _SideEffectPilot.side_effects.append("called")
            return ModelSOPilotDecision(
                action=SOPilotAction.REMAIN,
                action_params={},
                reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
                confidence=0.5,
                considered_actions=[
                    ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.5)
                ],
            )

    state_before = _match_state([_mech()])
    reducer, _ = _make_reducer(state_before, {MECH_RED: _SideEffectPilot()})
    reducer.apply(_tick_event())

    # The match state accessible from the reducer must equal the pre-tick state
    # (pilot_tick does not mutate match state — it only emits events).
    assert reducer.state == state_before
    assert _SideEffectPilot.side_effects == ["called"]


@pytest.mark.unit
def test_pilot_decision_payload_contains_action_and_reason() -> None:
    """PILOT_DECISION_MADE payload must contain action and reason_code fields."""
    state = _match_state([_mech()])
    reducer, emitted = _make_reducer(state, {MECH_RED: _StubPilot()})
    reducer.apply(_tick_event())

    decision_events = [e for e in emitted if e.event_type == SOEventType.PILOT_DECISION_MADE]
    assert len(decision_events) == 1
    payload = decision_events[0].payload
    assert "action" in payload
    assert "reason_code" in payload
    assert "considered_actions" in payload


@pytest.mark.unit
def test_sensor_events_passed_to_observation() -> None:
    """Recent SENSOR_OBSERVATION events are included in the pilot's observation."""
    sensor_event = ModelSOEventEnvelope(
        event_id=ULID,
        match_id=MATCH_ID,
        tick=5,
        sequence_in_tick=0,
        event_type=SOEventType.SENSOR_OBSERVATION,
        producer_node="node.reducer.sensors",
        subject=ModelSOEventSubject(mech_id=MECH_RED, player_id=PLAYER_RED),
        payload={
            "enemy_mech_id": MECH_BLUE,
            "distance_estimate": 12.5,
            "confidence": 0.7,
        },
        envelope=_onex_envelope(MATCH_ID),
    )

    stub = _StubPilot()
    state = _match_state([_mech()])
    reducer, _ = _make_reducer(state, {MECH_RED: stub}, sensor_events=[sensor_event])
    reducer.apply(_tick_event())

    assert stub.last_observation is not None
    assert len(stub.last_observation.enemy_observations) == 1
    assert stub.last_observation.enemy_observations[0].enemy_mech_id == MECH_BLUE
