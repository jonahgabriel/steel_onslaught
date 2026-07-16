"""Tests for the sensor observation reducer — Task 20.

Invariants verified:
- Two replays with identical events produce identical observation noise (deterministic RNG).
- Out-of-range targets emit zero SENSOR_OBSERVATION events.
- Confidence is always in [0, 1].
- Thermal sensor includes heat_estimate iff target heat >= 30.
- Acoustic sensor includes mode_estimate iff target speed >= 2.
- Sensors with sensor_dropout_ticks_remaining > 0 emit zero observations (dark).
- Observations are emitted via the bus.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
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
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.sensors import ReducerSensors

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MATCH_ID = "match.sensor.001"
MECH_RED = "mech.red.01"
MECH_BLUE = "mech.blue.01"
PLAYER_RED = "player.red"
PLAYER_BLUE = "player.blue"
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
        return "01JABCDE0123456789ABCDEFGX"

    def new_message_id(self) -> UUID:
        return UUID(int=2)


_EVENT_FACTORY = EventFactory(clock=_FixedClock(), identities=_FixedIdentities())


def _sensors(
    state: ModelSOMatchState,
    sensor_specs: dict[str, ModelSOSensorSpec],
    emit: Callable[[ModelSOEventEnvelope], None],
) -> ReducerSensors:
    return ReducerSensors(
        MATCH_ID,
        state,
        sensor_specs,
        emit,
        correlation_id=_TEST_CORRELATION_ID,
        event_factory=_EVENT_FACTORY,
    )


_SENSOR_RADAR = ModelSOSensorSpec(
    id="sensor.long_range_radar",
    display_name="Long-Range Radar Array",
    range=40,
    precision=0.6,
    latency_ticks=1,
    pressure_draw_per_tick=3.0,
    heat_per_tick=1.0,
    signature_impact=8.0,
    jamming_vulnerability_score=0.6,
)
_SENSOR_THERMAL = ModelSOSensorSpec(
    id="sensor.thermal_detector",
    display_name="Thermal Signature Detector",
    range=25,
    precision=0.75,
    latency_ticks=0,
    pressure_draw_per_tick=1.5,
    heat_per_tick=0.5,
    signature_impact=3.0,
    jamming_vulnerability_score=0.2,
)
_SENSOR_ACOUSTIC = ModelSOSensorSpec(
    id="sensor.acoustic_detector",
    display_name="Acoustic Motion Detector",
    range=20,
    precision=0.7,
    latency_ticks=0,
    pressure_draw_per_tick=1.0,
    heat_per_tick=0.25,
    signature_impact=2.0,
    jamming_vulnerability_score=0.15,
)


def _boiler(
    heat: int = 0,
    pressure: int = 60,
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
    position: ModelSOPosition | None = None,
    sensor_ids: tuple[str, ...] = ("sensor.long_range_radar",),
    jamming_intensity: float = 0.0,
    heat: int = 0,
    speed: int = 2,
    sensor_dropout_ticks_remaining: int = 0,
) -> ModelSOMechRuntimeState:
    pos = position or ModelSOPosition(x=0, y=0)
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=player_id,
        loadout_id="loadout.test.01",
        pilot_id="pilot.test.01",
        chassis_id="chassis.light.scout_mk1",
        chassis_class="light",
        base_speed=2,
        position=pos,
        facing=90,
        speed=speed,
        hp=100,
        hp_max=100,
        armor_value=5,
        armor_max=5,
        current_mode="recon",
        sensor_ids=sensor_ids,
        jamming_intensity=jamming_intensity,
        sensor_dropout_ticks_remaining=sensor_dropout_ticks_remaining,
        boiler=_boiler(heat=heat, mech_id=mech_id),
    )


def _match_state(
    mech_red: ModelSOMechRuntimeState | None = None,
    mech_blue: ModelSOMechRuntimeState | None = None,
    tick: int = 5,
) -> ModelSOMatchState:
    red = mech_red or _mech(mech_id=MECH_RED, player_id=PLAYER_RED)
    blue = mech_blue or _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),
    )
    return ModelSOMatchState(
        match_id=MATCH_ID,
        tick=tick,
        status=SOMatchStatus.RUNNING,
        seed=42,
        max_ticks=200,
        mech_states={red.mech_id: red, blue.mech_id: blue},
    )


def _tick_event(tick: int = 5, match_id: str = MATCH_ID) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEFGX",
        match_id=match_id,
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        payload={},
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id=match_id,
            emitted_at=datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_in_range_target_emits_sensor_observation() -> None:
    """When the target is within sensor range, at least one SENSOR_OBSERVATION is emitted."""
    emitted: list[ModelSOEventEnvelope] = []

    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}
    state = _match_state()
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs_events = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert len(obs_events) > 0


@pytest.mark.unit
def test_out_of_range_target_emits_no_observations() -> None:
    """An enemy at distance > sensor.range must produce zero SENSOR_OBSERVATION events."""
    emitted: list[ModelSOEventEnvelope] = []

    # Short-range scanner has range=15; place enemy at distance=20
    sensor_short = ModelSOSensorSpec(
        id="sensor.short_range_scanner",
        display_name="Short-Range Scanner",
        range=15,
        precision=0.9,
        latency_ticks=0,
        pressure_draw_per_tick=1.0,
        heat_per_tick=0.2,
        signature_impact=2.0,
        jamming_vulnerability_score=0.3,
    )
    sensor_specs = {sensor_short.id: sensor_short}
    red = _mech(sensor_ids=(sensor_short.id,))
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=20, y=0),  # distance=20 > range=15
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs_events = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs_events == []


@pytest.mark.unit
def test_confidence_in_zero_to_one_range() -> None:
    """Confidence in every emitted SENSOR_OBSERVATION must be in [0, 1]."""
    emitted: list[ModelSOEventEnvelope] = []

    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}
    state = _match_state()
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs_events = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs_events, "expected at least one observation"
    for evt in obs_events:
        conf = evt.payload["confidence"]
        assert 0.0 <= conf <= 1.0, f"confidence out of range: {conf}"


@pytest.mark.unit
def test_deterministic_noise_same_seed_same_result() -> None:
    """Two replay runs with identical match state produce identical distance_estimate."""
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}
    state = _match_state()

    emitted_a: list[ModelSOEventEnvelope] = []
    reducer_a = _sensors(state, sensor_specs, emitted_a.append)
    reducer_a.apply(_tick_event())

    emitted_b: list[ModelSOEventEnvelope] = []
    reducer_b = _sensors(state, sensor_specs, emitted_b.append)
    reducer_b.apply(_tick_event())

    obs_a = [e for e in emitted_a if e.event_type == SOEventType.SENSOR_OBSERVATION]
    obs_b = [e for e in emitted_b if e.event_type == SOEventType.SENSOR_OBSERVATION]

    assert len(obs_a) == len(obs_b), "event counts differ"
    for a, b in zip(obs_a, obs_b, strict=True):
        assert a.payload["distance_estimate"] == b.payload["distance_estimate"]
        assert a.payload["confidence"] == b.payload["confidence"]


@pytest.mark.unit
def test_different_seeds_produce_different_noise() -> None:
    """Different match seeds should (almost certainly) produce different distance estimates."""
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}
    state_42 = _match_state()  # seed=42
    state_99 = ModelSOMatchState(
        match_id=MATCH_ID,
        tick=5,
        status=SOMatchStatus.RUNNING,
        seed=99,  # different seed
        max_ticks=200,
        mech_states=state_42.mech_states,
    )

    emitted_42: list[ModelSOEventEnvelope] = []
    _sensors(state_42, sensor_specs, emitted_42.append).apply(_tick_event())

    emitted_99: list[ModelSOEventEnvelope] = []
    _sensors(state_99, sensor_specs, emitted_99.append).apply(_tick_event())

    obs_42 = [
        e.payload["distance_estimate"]
        for e in emitted_42
        if e.event_type == SOEventType.SENSOR_OBSERVATION
    ]
    obs_99 = [
        e.payload["distance_estimate"]
        for e in emitted_99
        if e.event_type == SOEventType.SENSOR_OBSERVATION
    ]

    assert obs_42 != obs_99, "different seeds must produce different noise"


@pytest.mark.unit
def test_thermal_sensor_includes_heat_estimate_when_target_heat_ge_30() -> None:
    """Thermal sensor includes heat_estimate iff target heat >= 30."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_THERMAL.id: _SENSOR_THERMAL}

    red = _mech(sensor_ids=(_SENSOR_THERMAL.id,))
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),  # in range (10 <= 25)
        heat=35,  # >= 30, so heat_estimate should be present
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs, "expected thermal observation"
    assert obs[0].payload.get("heat_estimate") is not None


@pytest.mark.unit
def test_thermal_sensor_omits_heat_estimate_when_target_heat_lt_30() -> None:
    """Thermal sensor omits heat_estimate when target heat < 30."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_THERMAL.id: _SENSOR_THERMAL}

    red = _mech(sensor_ids=(_SENSOR_THERMAL.id,))
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),
        heat=20,  # < 30, so heat_estimate should be absent
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs, "expected thermal observation"
    assert obs[0].payload.get("heat_estimate") is None


@pytest.mark.unit
def test_acoustic_sensor_includes_mode_estimate_when_target_speed_ge_2() -> None:
    """Acoustic sensor includes mode_estimate iff target speed >= 2."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_ACOUSTIC.id: _SENSOR_ACOUSTIC}

    red = _mech(sensor_ids=(_SENSOR_ACOUSTIC.id,))
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),  # in range (10 <= 20)
        speed=3,  # >= 2, so mode_estimate should be present
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs, "expected acoustic observation"
    assert obs[0].payload.get("mode_estimate") is not None


@pytest.mark.unit
def test_acoustic_sensor_omits_mode_estimate_when_target_speed_lt_2() -> None:
    """Acoustic sensor omits mode_estimate when target speed < 2."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_ACOUSTIC.id: _SENSOR_ACOUSTIC}

    red = _mech(sensor_ids=(_SENSOR_ACOUSTIC.id,))
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),
        speed=1,  # < 2, so mode_estimate should be absent
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs, "expected acoustic observation"
    assert obs[0].payload.get("mode_estimate") is None


@pytest.mark.unit
def test_sensor_dropout_emits_no_observations() -> None:
    """A mech with sensor_dropout_ticks_remaining > 0 emits zero observations."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}

    red = _mech(
        sensor_ids=(_SENSOR_RADAR.id,),
        sensor_dropout_ticks_remaining=2,  # sensors are dark
    )
    # blue has no sensors so it cannot emit observations either
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs == [], "dropout should suppress all observations"


@pytest.mark.unit
def test_jamming_reduces_confidence() -> None:
    """Jamming intensity reduces effective confidence (confidence = precision * (1 - jamming))."""
    emitted_clear: list[ModelSOEventEnvelope] = []
    emitted_jammed: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}

    # No jamming
    red_clear = _mech(sensor_ids=(_SENSOR_RADAR.id,), jamming_intensity=0.0)
    state_clear = _match_state(mech_red=red_clear)
    _sensors(state_clear, sensor_specs, emitted_clear.append).apply(_tick_event())

    # With jamming
    red_jammed = _mech(sensor_ids=(_SENSOR_RADAR.id,), jamming_intensity=0.5)
    state_jammed = _match_state(mech_red=red_jammed)
    _sensors(state_jammed, sensor_specs, emitted_jammed.append).apply(_tick_event())

    obs_clear = [e for e in emitted_clear if e.event_type == SOEventType.SENSOR_OBSERVATION]
    obs_jammed = [e for e in emitted_jammed if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs_clear and obs_jammed
    # Jammed confidence should be lower
    assert obs_jammed[0].payload["confidence"] < obs_clear[0].payload["confidence"]


@pytest.mark.unit
def test_mech_without_sensors_emits_no_observations() -> None:
    """A mech with no sensor_ids emits no SENSOR_OBSERVATION events."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}

    red = _mech(sensor_ids=())  # no sensors at all
    # blue also has no sensors so neither side can observe
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),
        sensor_ids=(),
    )
    state = _match_state(mech_red=red, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs == []


@pytest.mark.unit
def test_dead_mech_emits_no_observations() -> None:
    """A mech that is not alive emits no sensor observations."""
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}

    red = _mech(sensor_ids=(_SENSOR_RADAR.id,))
    # Mark red as dead; blue also has no sensors so it won't observe either
    red_dead = red.model_copy(update={"alive": False})
    blue = _mech(
        mech_id=MECH_BLUE,
        player_id=PLAYER_BLUE,
        position=ModelSOPosition(x=10, y=0),
        sensor_ids=(),
    )
    state = _match_state(mech_red=red_dead, mech_blue=blue)
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs == []


@pytest.mark.unit
def test_observation_payload_has_required_fields() -> None:
    """Every SENSOR_OBSERVATION payload must contain enemy_mech_id, distance_estimate, confidence."""  # noqa: E501
    emitted: list[ModelSOEventEnvelope] = []
    sensor_specs = {_SENSOR_RADAR.id: _SENSOR_RADAR}
    state = _match_state()
    reducer = _sensors(state, sensor_specs, emitted.append)
    reducer.apply(_tick_event())

    obs = [e for e in emitted if e.event_type == SOEventType.SENSOR_OBSERVATION]
    assert obs
    for evt in obs:
        assert "enemy_mech_id" in evt.payload
        assert "distance_estimate" in evt.payload
        assert "confidence" in evt.payload
