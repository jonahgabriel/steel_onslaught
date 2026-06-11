"""Tests for the CLI text renderer — Task 28 invariants."""

from __future__ import annotations

import io
from typing import Any

import pytest
import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.projections.cli.renderer import CliTextRenderer
from steel_onslaught.reducers.lifecycle import ReducerMatchLifecycle

MATCH_ID = "match.2026-04-30.renderer-test"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _env(
    event_type: SOEventType,
    payload: dict[str, Any],
    *,
    tick: int = 0,
    seq: int = 0,
    mech_id: str = "mech.red.01",
    player_id: str = "player.red",
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=MATCH_ID,
        tick=tick,
        sequence_in_tick=seq,
        event_type=event_type,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
        payload=payload,
        emitted_at="2026-04-30T00:00:00+00:00",
    )


def _renderer() -> tuple[CliTextRenderer, io.StringIO]:
    out = io.StringIO()
    return CliTextRenderer(out=out, color=False), out


def _match_started_payload() -> dict[str, Any]:
    return {
        "seed": 12345,
        "max_ticks": 200,
        "mechs": [
            {
                "mech_id": "mech.red.01",
                "chassis_id": "chassis.heavy.ironclad_mk1",
                "pilot_id": "pilot.example.predictive_v1",
            },
            {
                "mech_id": "mech.blue.01",
                "chassis_id": "chassis.light.scout_mk1",
                "pilot_id": "pilot.example.aggressive_v1",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Wildcard subscription
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_attach_subscribes_to_all_event_types() -> None:
    renderer, out = _renderer()
    bus = InProcessEventBus()
    renderer.attach(bus)

    bus.publish(
        _env(
            SOEventType.BOILER_UPDATED,
            {
                "pressure_before": 64,
                "pressure_after": 52,
                "heat_before": 72,
                "heat_after": 80,
            },
            tick=0,
        )
    )
    bus.publish(
        _env(
            SOEventType.VICTORY_DECLARED,
            {"winner_player_id": "player.17", "reason": "last_mech_standing"},
        )
    )

    text = out.getvalue()
    assert "boiler:" in text
    assert "VICTORY" in text


# ---------------------------------------------------------------------------
# Line formats (exact, color disabled)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_started_line() -> None:
    renderer, out = _renderer()
    renderer.handle(_env(SOEventType.MATCH_STARTED, _match_started_payload(), tick=0))
    assert out.getvalue() == "[Tick 0] MATCH STARTED (seed 12345, max_ticks 200)\n"


@pytest.mark.unit
def test_decision_line_with_mode_detail_and_labels() -> None:
    renderer, out = _renderer()
    renderer.handle(_env(SOEventType.MATCH_STARTED, _match_started_payload(), tick=0))
    out.seek(0)
    out.truncate(0)

    renderer.handle(
        _env(
            SOEventType.PILOT_DECISION_MADE,
            {
                "action": "switch_mode",
                "action_params": {"target_mode": "assault"},
                "reason_code": "mode_advantage",
                "confidence": 0.81,
                "considered_actions": [],
            },
            tick=142,
        )
    )
    assert out.getvalue() == (
        "[Tick 142] mech.red.01 (Heavy Ironclad Mk1, Predictive V1) "
        "decided: SWITCH_MODE → assault (conf 0.81)\n"
    )


@pytest.mark.unit
def test_decision_line_without_labels_or_params() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.PILOT_DECISION_MADE,
            {
                "action": "vent",
                "action_params": {},
                "reason_code": "heat_critical",
                "confidence": 1.0,
                "considered_actions": [],
            },
            tick=7,
        )
    )
    assert out.getvalue() == "[Tick 7] mech.red.01 decided: VENT (conf 1.00)\n"


@pytest.mark.unit
def test_decision_line_with_weapon_detail() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.PILOT_DECISION_MADE,
            {
                "action": "fire_weapon",
                "action_params": {"weapon_id": "weapon.light.machine_gun"},
                "reason_code": "target_in_range",
                "confidence": 0.9,
                "considered_actions": [],
            },
            tick=9,
        )
    )
    assert out.getvalue() == (
        "[Tick 9] mech.red.01 decided: FIRE_WEAPON → machine_gun (conf 0.90)\n"
    )


@pytest.mark.unit
def test_boiler_line() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.BOILER_UPDATED,
            {
                "pressure_before": 64,
                "pressure_after": 52,
                "heat_before": 72,
                "heat_after": 80,
            },
            tick=142,
        )
    )
    assert out.getvalue() == "[Tick 142] mech.red.01 boiler: pressure 64 → 52, heat 72 → 80\n"


@pytest.mark.unit
def test_weapon_fired_line() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.WEAPON_FIRED,
            {
                "weapon_id": "weapon.light.machine_gun",
                "target_id": "mech.blue.01",
                "hit_probability": 0.59,
            },
            tick=148,
        )
    )
    assert out.getvalue() == (
        "[Tick 148] mech.red.01 fired machine_gun at mech.blue.01 — predicted hit 0.59\n"
    )


@pytest.mark.unit
def test_damage_applied_line() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.DAMAGE_APPLIED,
            {"target_id": "mech.blue.01", "damage": 5},
            tick=149,
            mech_id="mech.blue.01",
            player_id="player.blue",
        )
    )
    assert out.getvalue() == "[Tick 149] HIT mech.blue.01 took 5 dmg\n"


@pytest.mark.unit
def test_redline_lines() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.HEAT_REDLINE_ENTERED,
            {"heat": 84, "redline_threshold": 80},
            tick=12,
        )
    )
    renderer.handle(
        _env(
            SOEventType.HEAT_REDLINE_EXITED,
            {"heat": 70, "redline_threshold": 80},
            tick=15,
        )
    )
    assert out.getvalue() == (
        "[Tick 12] mech.red.01 REDLINE entered (heat 84 ≥ 80)\n"
        "[Tick 15] mech.red.01 redline exited (heat 70 < 80)\n"
    )


@pytest.mark.unit
def test_destruction_and_rupture_lines() -> None:
    renderer, out = _renderer()
    renderer.handle(_env(SOEventType.BOILER_OVERLOADED, {}, tick=20))
    renderer.handle(_env(SOEventType.BOILER_RUPTURED, {"cause": "heat"}, tick=21))
    renderer.handle(_env(SOEventType.PILOT_KILLED, {}, tick=21))
    renderer.handle(_env(SOEventType.MECH_DESTROYED, {}, tick=21))
    assert out.getvalue() == (
        "[Tick 20] mech.red.01 boiler OVERLOADED\n"
        "[Tick 21] mech.red.01 BOILER RUPTURED\n"
        "[Tick 21] mech.red.01 PILOT KILLED\n"
        "[Tick 21] mech.red.01 DESTROYED\n"
    )


@pytest.mark.unit
def test_victory_line() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.VICTORY_DECLARED,
            {"winner_player_id": "player.17", "reason": "last_mech_standing"},
            tick=162,
            mech_id="*",
            player_id="*",
        )
    )
    assert out.getvalue() == "[Tick 162] VICTORY: player.17 (last mech standing)\n"


@pytest.mark.unit
def test_match_ended_lines() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.MATCH_ENDED,
            {"reason": "draw_max_ticks", "winner_id": None},
            tick=200,
            mech_id="*",
            player_id="*",
        )
    )
    renderer.handle(
        _env(
            SOEventType.MATCH_ENDED,
            {"reason": "last_mech_standing", "winner_id": "player.17"},
            tick=200,
            mech_id="*",
            player_id="*",
        )
    )
    assert out.getvalue() == (
        "[Tick 200] MATCH ENDED (draw max ticks)\n"
        "[Tick 200] MATCH ENDED (last mech standing, winner player.17)\n"
    )


# ---------------------------------------------------------------------------
# Silence for uninteresting events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_uninteresting_events_render_nothing() -> None:
    renderer, out = _renderer()
    renderer.handle(_env(SOEventType.MATCH_TICK, {}, tick=3))
    renderer.handle(_env(SOEventType.MOVE_INTENT, {"direction": "toward_enemy"}, tick=3))
    renderer.handle(_env(SOEventType.VENT_INTENT, {}, tick=3))
    renderer.handle(
        _env(
            SOEventType.SENSOR_OBSERVATION,
            {"enemy_mech_id": "mech.blue.01", "distance_estimate": 9.7, "confidence": 0.9},
            tick=3,
        )
    )
    renderer.handle(_env(SOEventType.MATCH_SCORED, {"scores": {}}, tick=3))
    assert out.getvalue() == ""


# ---------------------------------------------------------------------------
# ANSI color
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_color_codes_emitted_when_enabled() -> None:
    out = io.StringIO()
    renderer = CliTextRenderer(out=out, color=True)
    renderer.handle(
        _env(
            SOEventType.VICTORY_DECLARED,
            {"winner_player_id": "player.17", "reason": "last_mech_standing"},
            tick=162,
        )
    )
    text = out.getvalue()
    assert "\x1b[" in text
    assert text.endswith("\x1b[0m\n")


@pytest.mark.unit
def test_no_color_codes_when_disabled() -> None:
    renderer, out = _renderer()
    renderer.handle(
        _env(
            SOEventType.VICTORY_DECLARED,
            {"winner_player_id": "player.17", "reason": "last_mech_standing"},
            tick=162,
        )
    )
    assert "\x1b[" not in out.getvalue()


# ---------------------------------------------------------------------------
# The renderer is a pure projection — it never modifies match state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_renderer_does_not_modify_match_state() -> None:
    """Same event sequence with and without renderer yields identical state.

    The renderer subscribing must not cause any ReducerError, and the
    lifecycle reducer's folded state must be unaffected by its presence.
    """

    def _drive(with_renderer: bool) -> object:
        bus = InProcessEventBus()
        if with_renderer:
            renderer = CliTextRenderer(out=io.StringIO(), color=False)
            renderer.attach(bus)
        lifecycle = ReducerMatchLifecycle(MATCH_ID, bus=bus)
        bus.subscribe(lifecycle.handle)
        mech = {
            "mech_id": "mech.red.01",
            "player_id": "player.red",
            "loadout_id": "loadout.example.aggressive_light",
            "pilot_id": "pilot.example.aggressive_v1",
            "chassis_id": "chassis.light.scout_mk1",
            "chassis_class": "light",
            "base_speed": 4,
            "position": {"x": 0, "y": 0},
            "facing": 0,
            "speed": 4,
            "hp": 100,
            "hp_max": 100,
            "armor_value": 10,
            "current_mode": "recon",
            "boiler": {
                "match_id": MATCH_ID,
                "mech_id": "mech.red.01",
                "tick": 0,
                "pressure_current": 25,
                "pressure_maximum": 50,
                "regeneration_per_tick": 8,
                "heat_current": 0,
                "heat_redline_threshold": 65,
                "heat_rupture_threshold": 80,
                "heat_vent_rate": 6,
                "status_redline": False,
                "status_rupture_warning": False,
                "status_disabled": False,
                "status_ruptured": False,
                "modifier_heat_weapon_pressure": 1.0,
                "modifier_venting_penalty": 0.0,
                "modifier_mode_switch_heat_delta": 0,
            },
        }
        bus.publish(
            _env(
                SOEventType.MATCH_STARTED,
                {"seed": 1, "max_ticks": 3, "mechs": [mech]},
                tick=0,
                mech_id="*",
                player_id="*",
            )
        )
        for tick in (1, 2, 3):
            bus.publish(_env(SOEventType.MATCH_TICK, {}, tick=tick, mech_id="*", player_id="*"))
        return lifecycle.state

    assert _drive(with_renderer=True) == _drive(with_renderer=False)
