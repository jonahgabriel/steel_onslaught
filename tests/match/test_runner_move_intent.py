"""Regression tests for pilot MOVE/DISENGAGE intent resolution.

Background: the defensive pilot's rule-4 (DISENGAGE) and rule-5 (MOVE) fallbacks
previously emitted empty ``action_params``, and ``_resolve_move`` silently held
position when ``direction`` was absent — so a defensive pilot "decided" to move
but never did.  These tests pin the fix: the defensive pilot now names a
direction, and ``_resolve_move`` fails loud on a malformed direction.

Also covers ``_pilot_from_spec`` raising on an unknown archetype (previously it
returned ``None`` implicitly, leaving a mech that silently never acted).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import ulid
import yaml  # type: ignore[import-untyped]
from omnibase_core.models.common.model_envelope import ModelEnvelope
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.contracts.weapon import UnknownWeaponError
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.pilots.schemas import ModelSOPosition
from tests.runtime import match_runner, pilot_from_spec

_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")


def _onex_envelope(
    entity_id: str, emitted_at: datetime = datetime(2026, 7, 2, tzinfo=UTC)
) -> ModelEnvelope:
    """Composed ONEX ModelEnvelope."""
    return ModelEnvelope(
        message_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        entity_id=entity_id,
        emitted_at=emitted_at,
    )


LOADOUT_DEFENSIVE = Path("contracts_data/loadouts/proof_red_defensive_passive.yaml")
LOADOUT_AGGRESSIVE = Path("contracts_data/loadouts/example_aggressive_light.yaml")
MATCH_ID = "match.test.move-intent"


def _run_defensive_match(*, seed: int = 12345, max_ticks: int = 6) -> list[ModelSOEventEnvelope]:
    """Run a defensive-pilot vs aggressive-pilot match; collect all events.

    Spawns are centered so the defensive mech has room to retreat (the default
    (0,0) corner spawn pins it against the arena edge — a legitimate no-move
    case that would mask the regression we are pinning here).
    """
    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=seed,
        loadout_a=load_loadout(LOADOUT_DEFENSIVE),
        loadout_b=load_loadout(LOADOUT_AGGRESSIVE),
        max_ticks=max_ticks,
        spawn_a=ModelSOPosition(x=20, y=20),
        spawn_b=ModelSOPosition(x=30, y=30),
    )
    runner.run()
    return collected


@pytest.mark.integration
def test_defensive_pilot_actually_moves() -> None:
    """The defensive pilot's MOVE/DISENGAGE intents must produce MOVEMENT_RESOLVED.

    Before the fix, the defensive pilot emitted empty-direction move intents that
    ``_resolve_move`` silently dropped — so no movement ever resolved.  This test
    would have failed (zero movements) against the buggy code.
    """
    events = _run_defensive_match(max_ticks=8)
    movements = [e for e in events if e.event_type is SOEventType.MOVEMENT_RESOLVED]
    assert len(movements) > 0, (
        "defensive pilot produced no MOVEMENT_RESOLVED events — its move intents "
        "are being silently dropped again"
    )
    # Every movement must actually change position (Chebyshev distance > 0).
    for e in movements:
        frm = e.payload["from"]
        to = e.payload["to"]
        assert max(abs(to["x"] - frm["x"]), abs(to["y"] - frm["y"])) > 0


@pytest.mark.integration
def test_defensive_pilot_move_intents_carry_direction() -> None:
    """Every MOVE_INTENT from the defensive pilot carries a recognized direction."""
    events = _run_defensive_match(max_ticks=8)
    # The defensive mech is side 'a' (red) — its mech_id ends in '.a.01'.
    defensive_move_intents = [
        e
        for e in events
        if e.event_type is SOEventType.MOVE_INTENT and e.subject.mech_id.endswith(".a.01")
    ]
    assert len(defensive_move_intents) > 0, "no defensive move intents emitted"
    for e in defensive_move_intents:
        assert e.payload.get("direction") in {"toward_enemy", "defensive"}, (
            f"defensive MOVE_INTENT missing/invalid direction: {e.payload!r}"
        )


@pytest.mark.unit
def test_resolve_move_raises_on_unknown_direction() -> None:
    """A MOVE_INTENT with an unrecognized direction fails loud (not silent hold).

    This is the hardening that converts the original silent-no-op bug into a
    contract violation.  We synthesize a minimal intent and feed it directly.
    """
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=1,
        loadout_a=load_loadout(LOADOUT_AGGRESSIVE),
        loadout_b=load_loadout(LOADOUT_AGGRESSIVE),
        max_ticks=2,
    )
    # Drive a MATCH_STARTED so the fold has mechs to resolve against.
    bus.publish(
        ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=MATCH_ID,
            tick=0,
            sequence_in_tick=0,
            event_type=SOEventType.MATCH_STARTED,
            producer_node="node.test",
            subject=_MATCH_SUBJECT,
            payload={
                "seed": 1,
                "max_ticks": 2,
                "mechs": [
                    _mech_payload("mech.a.01", "player.a"),
                    _mech_payload("mech.b.01", "player.b"),
                ],
            },
            envelope=_onex_envelope(MATCH_ID),
        )
    )
    mech = runner.fold.state.mech_states["mech.a.01"]
    bad_intent = ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=MATCH_ID,
        tick=1,
        sequence_in_tick=0,
        event_type=SOEventType.MOVE_INTENT,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
        payload={"direction": "sideways"},  # not a recognized direction
        envelope=_onex_envelope(MATCH_ID),
    )
    with pytest.raises(ValidationError, match="direction"):
        runner._resolve_move(bad_intent, runner.fold.state, mech)


@pytest.mark.unit
def test_resolve_move_raises_on_missing_direction() -> None:
    """A MOVE_INTENT with no direction key at all also fails loud."""
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=1,
        loadout_a=load_loadout(LOADOUT_AGGRESSIVE),
        loadout_b=load_loadout(LOADOUT_AGGRESSIVE),
        max_ticks=2,
    )
    bus.publish(
        ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=MATCH_ID,
            tick=0,
            sequence_in_tick=0,
            event_type=SOEventType.MATCH_STARTED,
            producer_node="node.test",
            subject=_MATCH_SUBJECT,
            payload={
                "seed": 1,
                "max_ticks": 2,
                "mechs": [
                    _mech_payload("mech.a.01", "player.a"),
                    _mech_payload("mech.b.01", "player.b"),
                ],
            },
            envelope=_onex_envelope(MATCH_ID),
        )
    )
    mech = runner.fold.state.mech_states["mech.a.01"]
    no_dir_intent = ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=MATCH_ID,
        tick=1,
        sequence_in_tick=0,
        event_type=SOEventType.MOVE_INTENT,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
        payload={},  # no direction at all
        envelope=_onex_envelope(MATCH_ID),
    )
    with pytest.raises(ValidationError, match="direction"):
        runner._resolve_move(no_dir_intent, runner.fold.state, mech)


@pytest.mark.unit
def test_resolve_weapon_fire_raises_on_unknown_weapon_id() -> None:
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=1,
        loadout_a=load_loadout(LOADOUT_AGGRESSIVE),
        loadout_b=load_loadout(LOADOUT_AGGRESSIVE),
        max_ticks=2,
    )
    bus.publish(
        ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=MATCH_ID,
            tick=0,
            sequence_in_tick=0,
            event_type=SOEventType.MATCH_STARTED,
            producer_node="node.test",
            subject=_MATCH_SUBJECT,
            payload={
                "seed": 1,
                "max_ticks": 2,
                "mechs": [
                    _mech_payload("mech.a.01", "player.a"),
                    _mech_payload("mech.b.01", "player.b"),
                ],
            },
            envelope=_onex_envelope(MATCH_ID),
        )
    )
    mech = runner.fold.state.mech_states["mech.a.01"]
    unknown_id = "weapon.light.absent"
    intent = ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=MATCH_ID,
        tick=1,
        sequence_in_tick=0,
        event_type=SOEventType.WEAPON_FIRE_INTENT,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech.mech_id, player_id=mech.player_id),
        payload={"weapon_id": unknown_id},
        envelope=_onex_envelope(MATCH_ID),
    )

    with pytest.raises(UnknownWeaponError) as raised:
        runner._resolve_weapon_fire(intent, runner.fold.state, mech)

    assert raised.value.weapon_id == unknown_id
    assert raised.value.owner_id == mech.mech_id


@pytest.mark.unit
def test_pilot_from_spec_raises_on_unknown_archetype() -> None:
    """An unknown archetype fails loud rather than yielding a None pilot.

    ``_pilot_from_spec`` previously returned ``None`` implicitly for an unknown
    archetype, and ``ReducerPilotTick`` silently skips mechs with no pilot entry
    — so the mech would never act.  We bypass validation with ``model_construct``
    (archetype is a Literal, so normal construction rejects this earlier).
    """
    spec = ModelSOPilotSpec.model_construct(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id="pilot.test.bogus",
        display_name="Bogus",
        archetype="bogus",  # not in the Literal
        lineage=None,
        parameters=None,
    )
    with pytest.raises(ValueError, match="unknown pilot archetype"):
        pilot_from_spec(spec)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mech_payload(mech_id: str, player_id: str) -> dict[str, object]:
    """Complete current-live mech snapshot for a MATCH_STARTED payload."""
    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.mech_runtime_state",
        "mech_id": mech_id,
        "player_id": player_id,
        "side": "red" if player_id == "player.a" else "blue",
        "loadout_id": "loadout.a",
        "pilot_id": "pilot.aggressive",
        "chassis_id": "chassis.medium.hunter_mk1",
        "chassis_class": "medium",
        "sensor_ids": [],
        "gizmo_ids": [],
        "base_speed": 4,
        "position": {"x": 5, "y": 5},
        "facing": 45,
        "speed": 4,
        "hp": 100,
        "hp_max": 100,
        "armor_value": 10,
        "armor_max": 10,
        "alive": True,
        "pilot_alive": True,
        "current_mode": "recon",
        "mode_lock_until": 0,
        "transition_ticks_remaining": 0,
        "transition_to_mode": None,
        "sensor_dropout_ticks_remaining": 0,
        "mode_switch_disabled_until": 0,
        "weapon_cooldowns": {},
        "evasion": 0.0,
        "accuracy_penalty_next_fire": 0.0,
        "jamming_intensity": 0.0,
        "under_sensor_lock": False,
        "boiler": {
            "match_id": MATCH_ID,
            "mech_id": mech_id,
            "tick": 0,
            "pressure_current": 30,
            "pressure_maximum": 60,
            "regeneration_per_tick": 5,
            "heat_current": 0,
            "heat_redline_threshold": 80,
            "heat_rupture_threshold": 100,
            "heat_vent_rate": 5,
            "status_redline": False,
            "status_rupture_warning": False,
            "status_disabled": False,
            "status_ruptured": False,
            "modifier_heat_weapon_pressure": 1.0,
            "modifier_venting_penalty": 0.0,
            "modifier_mode_switch_heat_delta": 0,
        },
        "redline_consecutive_ticks": 0,
        "overloaded": False,
        "overloaded_consecutive_ticks": 0,
    }


# Suppress unused-import warning for yaml (kept for parity with sibling tests).
_ = yaml
