"""Backstop test for the duplicated VICTORY_DECLARED authority.

Two independent paths declare victory on the >1 -> ==1 survivor transition:
  - ``ReducerFailureCascade._maybe_declare_victory`` (kills arriving via the
    rupture/failure cascade), and
  - ``MatchStateFold._on_flag_drop`` (kills arriving as a direct
    MECH_DESTROYED/PILOT_KILLED, e.g. from a weapon kill).

Both are guarded to the transition so they don't duplicate.  This test proves
the fold-level declaration is a *real* backstop: with the cascade's declaration
neutered, the fold still declares victory on a direct MECH_DESTROYED.  It
protects the intentional redundancy against a future "remove this duplicate"
cleanup.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.state import SOMatchStatus

_MATCH_ID = "match.test.victory-backstop"
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")


def _env(
    event_type: SOEventType,
    *,
    tick: int,
    subject: ModelSOEventSubject = _MATCH_SUBJECT,
    payload: dict[str, Any] | None = None,
    seq: int = 0,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=_MATCH_ID,
        tick=tick,
        sequence_in_tick=seq,
        event_type=event_type,
        producer_node="node.test",
        subject=subject,
        payload=payload or {},
        emitted_at=datetime.now(UTC).isoformat(),
    )


def _mech_dict(mech_id: str, player_id: str) -> dict[str, Any]:
    """A minimal mech dict for the MATCH_STARTED payload (two mechs, opposite players)."""
    return {
        "mech_id": mech_id,
        "player_id": player_id,
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
        "current_mode": "recon",
        "weapon_cooldowns": {},
        "boiler": {
            "match_id": _MATCH_ID,
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
    }


def _drive_to_two_mechs(fold: MatchStateFold) -> None:
    fold.apply(
        _env(
            SOEventType.MATCH_STARTED,
            tick=0,
            payload={
                "seed": 1,
                "max_ticks": 200,
                "mechs": [
                    _mech_dict("mech.red.01", "player.red"),
                    _mech_dict("mech.blue.01", "player.blue"),
                ],
            },
        )
    )
    assert fold.state.status is SOMatchStatus.RUNNING
    assert len(fold.state.surviving_player_ids()) == 2


@pytest.mark.unit
def test_fold_declares_victory_even_with_cascade_neutered() -> None:
    """The fold-level VICTORY_DECLARED fires even when the cascade's is suppressed.

    This proves ``_on_flag_drop`` is a real backstop, not dead code: a direct
    MECH_DESTROYED (the weapon-kill path) declares victory through the fold
    alone, with the cascade's ``_maybe_declare_victory`` monkeypatched to no-op.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    catalog = MatchContractCatalog.load()

    fold = MatchStateFold(_MATCH_ID, bus=bus, catalog=catalog)
    fold._failure._maybe_declare_victory = lambda *args: None  # type: ignore[method-assign]

    _drive_to_two_mechs(fold)
    fold.apply(
        _env(
            SOEventType.MECH_DESTROYED,
            tick=1,
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
            payload={"cause": "weapon_damage", "source_mech_id": "mech.blue.01"},
        )
    )

    victory = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victory) == 1, "fold must declare victory when the cascade cannot"
    assert victory[0].payload["winner_player_id"] == "player.blue"
    assert victory[0].payload["reason"] == "last_mech_standing"


@pytest.mark.unit
def test_fold_does_not_double_declare_when_cascade_also_fires() -> None:
    """When both paths are active, exactly one VICTORY_DECLARED is emitted.

    The >1 -> ==1 guard on each path prevents duplication: the cascade declares
    first (it runs inside the fold's MATCH_TICK sub-step) and the fold's own
    _on_flag_drop is a no-op on the already-single-survivor state.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    catalog = MatchContractCatalog.load()

    fold = MatchStateFold(_MATCH_ID, bus=bus, catalog=catalog)
    _drive_to_two_mechs(fold)
    fold.apply(
        _env(
            SOEventType.MECH_DESTROYED,
            tick=1,
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
            payload={"cause": "weapon_damage", "source_mech_id": "mech.blue.01"},
        )
    )

    victory = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victory) == 1
