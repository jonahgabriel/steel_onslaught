"""Tests for ModelSOMechRuntimeState + ModelSOMatchState — Task 18.

``ModelSOMechRuntimeState`` is defined comprehensively up front: downstream
reducer tasks (19-26) are forbidden from editing ``match/state.py``, so every
field they need must already exist and be exercised here.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.match.state import (
    ModelSOMatchState,
    ModelSOMechRuntimeState,
    SOMatchEndReason,
    SOMatchStatus,
)
from steel_onslaught.pilots.schemas import ModelSOPosition

MATCH_ID = "match.2026-04-30.test"


def _boiler(mech_id: str) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=MATCH_ID,
        mech_id=mech_id,
        tick=0,
        pressure_current=60,
        pressure_maximum=90,
        regeneration_per_tick=3,
        heat_current=0,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=4,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _mech_kwargs(mech_id: str = "mech.red.01", player_id: str = "player.red") -> dict[str, Any]:
    return {
        "mech_id": mech_id,
        "player_id": player_id,
        "loadout_id": "loadout.example.aggressive_light",
        "pilot_id": "pilot.aggressive.01",
        "chassis_id": "chassis.light.scout_mk1",
        "chassis_class": "light",
        "base_speed": 4,
        "position": ModelSOPosition(x=0, y=0),
        "facing": 90,
        "speed": 4,
        "hp": 100,
        "hp_max": 100,
        "armor_value": 10,
        "current_mode": "recon",
        "weapon_cooldowns": {"weapon.machine_gun": 0},
        "boiler": _boiler(mech_id),
    }


def _mech(
    mech_id: str = "mech.red.01",
    player_id: str = "player.red",
    **overrides: Any,
) -> ModelSOMechRuntimeState:
    kwargs = _mech_kwargs(mech_id, player_id)
    kwargs.update(overrides)
    return ModelSOMechRuntimeState(**kwargs)


# ---------------------------------------------------------------------------
# ModelSOMechRuntimeState — comprehensive field coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mech_runtime_state_round_trip() -> None:
    mech = _mech()
    blob = mech.model_dump_json()
    parsed = ModelSOMechRuntimeState.model_validate_json(blob)
    assert parsed == mech


@pytest.mark.unit
def test_mech_runtime_state_has_every_downstream_field() -> None:
    """Tasks 19-26 read these fields and cannot edit state.py — all must exist."""
    mech = _mech()
    # Task 19 movement: position, facing, speed limits.
    assert mech.position == ModelSOPosition(x=0, y=0)
    assert mech.facing == 90
    assert mech.base_speed == 4
    assert mech.speed == 4
    # Task 20 sensors: equipped sensors, jamming, dropout, lock.
    assert mech.sensor_ids == ()
    assert mech.jamming_intensity == 0.0
    assert mech.sensor_dropout_ticks_remaining == 0
    assert mech.under_sensor_lock is False
    # Task 21 pilot tick: alive flag, hp view.
    assert mech.alive is True
    assert mech.pilot_alive is True
    assert mech.hp == 100
    assert mech.hp_max == 100
    # Task 22 boiler: boiler state reference.
    assert mech.boiler.pressure_current == 60
    # Task 23 mode: current mode, lock, transition bookkeeping.
    assert mech.current_mode == "recon"
    assert mech.mode_lock_until == 0
    assert mech.transition_ticks_remaining == 0
    assert mech.transition_to_mode is None
    assert mech.mode_switch_disabled_until == 0
    # Task 24 weapons: cooldown map, evasion, chassis class for effectiveness.
    assert mech.weapon_cooldowns == {"weapon.machine_gun": 0}
    assert mech.evasion == 0.0
    assert mech.chassis_class == "light"
    # Task 25 damage: armor value.
    assert mech.armor_value == 10
    # Task 26 failure cascade: redline/overload counters, gizmos for survival roll.
    assert mech.redline_consecutive_ticks == 0
    assert mech.overloaded is False
    assert mech.overloaded_consecutive_ticks == 0
    assert mech.accuracy_penalty_next_fire == 0.0
    assert mech.gizmo_ids == ()


@pytest.mark.unit
def test_mech_runtime_state_is_frozen() -> None:
    mech = _mech()
    with pytest.raises(ValidationError):
        mech.hp = 50


@pytest.mark.unit
def test_facing_must_be_below_360() -> None:
    with pytest.raises(ValidationError):
        _mech(facing=360)


@pytest.mark.unit
def test_facing_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        _mech(facing=-1)


@pytest.mark.unit
def test_hp_cannot_exceed_hp_max() -> None:
    with pytest.raises(ValidationError):
        _mech(hp=101, hp_max=100)


@pytest.mark.unit
def test_negative_weapon_cooldown_rejected() -> None:
    with pytest.raises(ValidationError):
        _mech(weapon_cooldowns={"weapon.machine_gun": -1})


@pytest.mark.unit
def test_transition_ticks_without_target_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        _mech(transition_ticks_remaining=2, transition_to_mode=None)


@pytest.mark.unit
def test_transition_target_without_ticks_rejected() -> None:
    with pytest.raises(ValidationError):
        _mech(transition_ticks_remaining=0, transition_to_mode="assault")


@pytest.mark.unit
def test_in_flight_transition_is_valid() -> None:
    mech = _mech(transition_ticks_remaining=2, transition_to_mode="assault")
    assert mech.transition_to_mode == "assault"


@pytest.mark.unit
def test_hp_percent_property() -> None:
    assert _mech(hp=25, hp_max=100).hp_percent == 25.0
    assert _mech(hp=100, hp_max=100).hp_percent == 100.0


# ---------------------------------------------------------------------------
# ModelSOMatchState
# ---------------------------------------------------------------------------


def _match_state(**overrides: Any) -> ModelSOMatchState:
    kwargs: dict[str, Any] = {
        "match_id": MATCH_ID,
        "tick": 0,
        "status": SOMatchStatus.RUNNING,
        "seed": 42,
        "max_ticks": 200,
        "mech_states": {},
        "winner_id": None,
        "end_reason": None,
    }
    kwargs.update(overrides)
    return ModelSOMatchState(**kwargs)


@pytest.mark.unit
def test_match_state_round_trip() -> None:
    mech = _mech()
    state = _match_state(mech_states={mech.mech_id: mech})
    parsed = ModelSOMatchState.model_validate_json(state.model_dump_json())
    assert parsed == state


@pytest.mark.unit
def test_ended_match_requires_end_reason() -> None:
    with pytest.raises(ValidationError):
        _match_state(status=SOMatchStatus.ENDED, end_reason=None)


@pytest.mark.unit
def test_draw_state_has_no_winner() -> None:
    state = _match_state(
        tick=200,
        status=SOMatchStatus.ENDED,
        winner_id=None,
        end_reason=SOMatchEndReason.DRAW_MAX_TICKS,
    )
    assert state.winner_id is None
    assert state.end_reason is SOMatchEndReason.DRAW_MAX_TICKS


@pytest.mark.unit
def test_running_match_cannot_carry_winner() -> None:
    with pytest.raises(ValidationError):
        _match_state(status=SOMatchStatus.RUNNING, winner_id="player.red")


@pytest.mark.unit
def test_running_match_cannot_carry_end_reason() -> None:
    with pytest.raises(ValidationError):
        _match_state(status=SOMatchStatus.RUNNING, end_reason=SOMatchEndReason.ABORTED)


@pytest.mark.unit
def test_tick_cannot_exceed_max_ticks() -> None:
    with pytest.raises(ValidationError):
        _match_state(tick=201, max_ticks=200)


@pytest.mark.unit
def test_mech_states_keys_must_match_mech_ids() -> None:
    mech = _mech(mech_id="mech.red.01")
    with pytest.raises(ValidationError):
        _match_state(mech_states={"mech.blue.99": mech})


@pytest.mark.unit
def test_surviving_player_ids() -> None:
    red = _mech("mech.red.01", "player.red")
    blue = _mech("mech.blue.01", "player.blue", alive=False)
    state = _match_state(mech_states={red.mech_id: red, blue.mech_id: blue})
    assert state.surviving_player_ids() == frozenset({"player.red"})


@pytest.mark.unit
def test_dead_pilot_does_not_survive() -> None:
    red = _mech("mech.red.01", "player.red", pilot_alive=False)
    blue = _mech("mech.blue.01", "player.blue")
    state = _match_state(mech_states={red.mech_id: red, blue.mech_id: blue})
    assert state.surviving_player_ids() == frozenset({"player.blue"})


@pytest.mark.unit
def test_player_ids_includes_dead_players() -> None:
    red = _mech("mech.red.01", "player.red", alive=False)
    blue = _mech("mech.blue.01", "player.blue")
    state = _match_state(mech_states={red.mech_id: red, blue.mech_id: blue})
    assert state.player_ids() == frozenset({"player.red", "player.blue"})


@pytest.mark.unit
def test_living_mechs_skips_dead_mechs() -> None:
    red = _mech("mech.red.01", "player.red", alive=False)
    blue = _mech("mech.blue.01", "player.blue")
    state = _match_state(mech_states={red.mech_id: red, blue.mech_id: blue})
    assert [m.mech_id for m in state.living_mechs()] == ["mech.blue.01"]
