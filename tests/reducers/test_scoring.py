"""Tests for the match scoring reducer — Task 29.

On the terminal event (MATCH_ENDED, or VICTORY_DECLARED from the failure
cascade path), the reducer computes per-player scores and emits MATCH_SCORED
per design §22.2.

Score components per player:
- victory: 1 if winner else 0.
- damage_efficiency: damage_dealt / (pressure_consumed + 1).
- pressure_efficiency: 1 - (pressure_wasted / pressure_consumed); 1.0 when
  nothing was consumed.
- overload_penalty: count of BOILER_OVERLOADED events for this player.
- replay_validity: 1 if the replay engine reproduces the live state else 0.
- final_score = victory * 1000 + damage_dealt * 10 + pressure_efficiency * 100
  + replay_validity * 50 - overload_penalty * 100 (floored at 0).

Invariants covered:
- replay_validity == 0 zeroes out >90% of the score (hard determinism gate).
- Winner score > loser score for any non-degenerate match.
- Two replays produce identical final_score values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.runner import MatchRunner, load_loadout
from steel_onslaught.match.state import ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.projections.leaderboard.handler import (
    LeaderboardHandler,
    LeaderboardProjection,
)
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.scoring import (
    ReducerScoring,
    compute_final_score,
    verify_replay_validity,
)

_MATCH_ID = "match.scoring.001"

_MECH_A = "mech.a.01"
_MECH_B = "mech.b.01"
_PLAYER_A = "player.a"
_PLAYER_B = "player.b"

_RUPTURE_THRESHOLD = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_boiler(mech_id: str) -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=_MATCH_ID,
        mech_id=mech_id,
        tick=0,
        pressure_current=40,
        pressure_maximum=80,
        regeneration_per_tick=4,
        heat_current=0,
        heat_redline_threshold=70,
        heat_rupture_threshold=_RUPTURE_THRESHOLD,
        heat_vent_rate=2,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )


def _make_mech(mech_id: str, player_id: str, *, loadout_id: str) -> ModelSOMechRuntimeState:
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=player_id,
        loadout_id=loadout_id,
        pilot_id="pilot.aggressive",
        chassis_id="chassis.medium.hunter_mk1",
        chassis_class="medium",
        base_speed=3,
        position=ModelSOPosition(x=0, y=0),
        facing=0,
        speed=3,
        hp=100,
        hp_max=100,
        armor_value=10,
        current_mode="recon",
        boiler=_make_boiler(mech_id),
    )


_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")
_SUBJECT_A = ModelSOEventSubject(mech_id=_MECH_A, player_id=_PLAYER_A)
_SUBJECT_B = ModelSOEventSubject(mech_id=_MECH_B, player_id=_PLAYER_B)


def _env(
    event_type: SOEventType,
    *,
    tick: int,
    payload: dict[str, Any],
    subject: ModelSOEventSubject = _MATCH_SUBJECT,
    match_id: str = _MATCH_ID,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=match_id,
        tick=tick,
        sequence_in_tick=0,
        event_type=event_type,
        producer_node="node.test.scoring",
        subject=subject,
        payload=payload,
        emitted_at="2026-04-30T00:00:00+00:00",
    )


def _match_started(*, tick: int = 0) -> ModelSOEventEnvelope:
    mechs = [
        _make_mech(_MECH_A, _PLAYER_A, loadout_id="loadout.alpha"),
        _make_mech(_MECH_B, _PLAYER_B, loadout_id="loadout.beta"),
    ]
    return _env(
        SOEventType.MATCH_STARTED,
        tick=tick,
        payload={
            "seed": 7,
            "max_ticks": 10,
            "mechs": [mech.model_dump(mode="json") for mech in mechs],
        },
    )


def _weapon_fired(
    *, tick: int, subject: ModelSOEventSubject, pressure_cost: int, heat_generated: int = 0
) -> ModelSOEventEnvelope:
    return _env(
        SOEventType.WEAPON_FIRED,
        tick=tick,
        subject=subject,
        payload={
            "weapon_id": "module.weapon.machine_gun",
            "pressure_cost": pressure_cost,
            "heat_generated": heat_generated,
        },
    )


def _hit_resolved(
    *, tick: int, attacker_id: str, defender_id: str, damage_after_armor: int, hit: bool = True
) -> ModelSOEventEnvelope:
    return _env(
        SOEventType.HIT_RESOLVED,
        tick=tick,
        subject=ModelSOEventSubject(mech_id=attacker_id, player_id="*"),
        payload={
            "attacker_id": attacker_id,
            "defender_id": defender_id,
            "weapon_id": "module.weapon.machine_gun",
            "result": {
                "hit": hit,
                "damage_raw": damage_after_armor + 4,
                "damage_after_armor": damage_after_armor,
                "critical": False,
            },
        },
    )


def _match_ended(*, tick: int, winner_id: str | None) -> ModelSOEventEnvelope:
    reason = "last_mech_standing" if winner_id is not None else "draw_max_ticks"
    return _env(
        SOEventType.MATCH_ENDED,
        tick=tick,
        payload={"reason": reason, "winner_id": winner_id},
    )


def _standard_duel_events() -> list[ModelSOEventEnvelope]:
    """MATCH_STARTED, one paid hit by player.a, MATCH_ENDED with player.a winning."""
    return [
        _match_started(),
        _weapon_fired(tick=1, subject=_SUBJECT_A, pressure_cost=10, heat_generated=20),
        _hit_resolved(tick=1, attacker_id=_MECH_A, defender_id=_MECH_B, damage_after_armor=8),
        _match_ended(tick=2, winner_id=_PLAYER_A),
    ]


def _score_events(
    events: list[ModelSOEventEnvelope],
    *,
    replay_valid: bool = True,
    match_id: str = _MATCH_ID,
) -> list[ModelSOEventEnvelope]:
    """Fold *events* through a fresh scoring reducer; return its emissions."""
    emitted: list[ModelSOEventEnvelope] = []
    reducer = ReducerScoring(
        match_id,
        emit=emitted.append,
        replay_validity_check=lambda: replay_valid,
    )
    for event in events:
        reducer.apply(event)
    return emitted


def _single_scored_payload(
    events: list[ModelSOEventEnvelope], *, replay_valid: bool = True
) -> dict[str, Any]:
    emitted = _score_events(events, replay_valid=replay_valid)
    scored = [e for e in emitted if e.event_type is SOEventType.MATCH_SCORED]
    assert len(scored) == 1
    return scored[0].payload


# ---------------------------------------------------------------------------
# Emission shape
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_emits_exactly_one_match_scored_on_match_ended() -> None:
    emitted = _score_events(_standard_duel_events())
    scored = [e for e in emitted if e.event_type is SOEventType.MATCH_SCORED]
    assert len(scored) == 1
    assert scored[0].match_id == _MATCH_ID
    assert scored[0].tick == 2


@pytest.mark.unit
def test_payload_matches_design_22_2_shape() -> None:
    payload = _single_scored_payload(_standard_duel_events())
    assert payload["kind"] == "steel_onslaught.match_scored"
    assert payload["match_id"] == _MATCH_ID
    assert payload["winner"] == {"player_id": _PLAYER_A, "mech_id": _MECH_A}
    assert set(payload["scores"]) == {_PLAYER_A, _PLAYER_B}
    for score in payload["scores"].values():
        assert {
            "victory",
            "damage_dealt",
            "damage_efficiency",
            "pressure_efficiency",
            "overload_penalty",
            "replay_validity",
            "final_score",
        } <= set(score)


@pytest.mark.unit
def test_score_components_for_standard_duel() -> None:
    payload = _single_scored_payload(_standard_duel_events())
    score_a = payload["scores"][_PLAYER_A]
    score_b = payload["scores"][_PLAYER_B]

    assert score_a["victory"] == 1
    assert score_a["damage_dealt"] == 8
    assert score_a["damage_efficiency"] == pytest.approx(8 / 11)
    assert score_a["pressure_efficiency"] == pytest.approx(1.0)
    assert score_a["overload_penalty"] == 0
    assert score_a["replay_validity"] == 1
    # 1*1000 + 8*10 + 1.0*100 + 1*50 - 0*100
    assert score_a["final_score"] == 1230

    assert score_b["victory"] == 0
    assert score_b["damage_dealt"] == 0
    assert score_b["pressure_efficiency"] == pytest.approx(1.0)
    # 0 + 0 + 100 + 50 - 0
    assert score_b["final_score"] == 150


# ---------------------------------------------------------------------------
# Invariant 1: replay_validity == 0 zeroes out >90% of the score
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replay_validity_zero_zeroes_out_over_90_percent() -> None:
    valid = _single_scored_payload(_standard_duel_events(), replay_valid=True)
    invalid = _single_scored_payload(_standard_duel_events(), replay_valid=False)

    for player_id in (_PLAYER_A, _PLAYER_B):
        valid_score = valid["scores"][player_id]["final_score"]
        invalid_score = invalid["scores"][player_id]["final_score"]
        assert invalid["scores"][player_id]["replay_validity"] == 0
        assert invalid_score < valid_score * 0.1


@pytest.mark.unit
def test_compute_final_score_hard_gates_on_replay_validity() -> None:
    assert (
        compute_final_score(
            victory=1,
            damage_dealt=100,
            pressure_efficiency=1.0,
            replay_validity=0,
            overload_penalty=0,
        )
        == 0
    )


@pytest.mark.unit
def test_compute_final_score_floors_at_zero() -> None:
    assert (
        compute_final_score(
            victory=0,
            damage_dealt=0,
            pressure_efficiency=0.0,
            replay_validity=1,
            overload_penalty=5,
        )
        == 0
    )


# ---------------------------------------------------------------------------
# Invariant 2: winner score > loser score
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_winner_score_exceeds_loser_score() -> None:
    payload = _single_scored_payload(_standard_duel_events())
    assert payload["winner_score"] > payload["loser_score"]
    assert payload["scores"][_PLAYER_A]["final_score"] > payload["scores"][_PLAYER_B]["final_score"]


# ---------------------------------------------------------------------------
# Invariant 3: two replays produce identical final_score values
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_two_replays_produce_identical_scores() -> None:
    events = _standard_duel_events()
    first = _single_scored_payload(events)
    second = _single_scored_payload(events)
    assert first["scores"] == second["scores"]
    assert first["winner_score"] == second["winner_score"]
    assert first["loser_score"] == second["loser_score"]


# ---------------------------------------------------------------------------
# Component accumulation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overload_penalty_counts_boiler_overloaded_events() -> None:
    events = [
        _match_started(),
        _env(SOEventType.BOILER_OVERLOADED, tick=1, subject=_SUBJECT_B, payload={"heat": 80}),
        _env(SOEventType.BOILER_OVERLOADED, tick=2, subject=_SUBJECT_B, payload={"heat": 85}),
        _match_ended(tick=3, winner_id=_PLAYER_A),
    ]
    payload = _single_scored_payload(events)
    assert payload["scores"][_PLAYER_B]["overload_penalty"] == 2
    # 0 + 0 + 100 + 50 - 200 floors at 0.
    assert payload["scores"][_PLAYER_B]["final_score"] == 0
    assert payload["scores"][_PLAYER_A]["overload_penalty"] == 0


@pytest.mark.unit
def test_mode_transition_pressure_counts_as_consumed() -> None:
    events = [
        _match_started(),
        _env(
            SOEventType.MODE_TRANSITION_STARTED,
            tick=1,
            subject=_SUBJECT_A,
            payload={"costs": {"pressure": 5, "heat": 3}},
        ),
        _hit_resolved(tick=1, attacker_id=_MECH_A, defender_id=_MECH_B, damage_after_armor=6),
        _match_ended(tick=2, winner_id=_PLAYER_A),
    ]
    payload = _single_scored_payload(events)
    # damage_efficiency = 6 / (5 + 1)
    assert payload["scores"][_PLAYER_A]["damage_efficiency"] == pytest.approx(1.0)


@pytest.mark.unit
def test_pressure_drained_at_full_heat_is_wasted() -> None:
    events = [
        _match_started(),
        # Heat pinned at the rupture-threshold cap -> next drain is wasted.
        _env(
            SOEventType.BOILER_UPDATED,
            tick=1,
            subject=_SUBJECT_A,
            payload={
                "pressure_before": 40,
                "pressure_after": 40,
                "heat_before": 90,
                "heat_after": _RUPTURE_THRESHOLD,
            },
        ),
        _weapon_fired(tick=1, subject=_SUBJECT_A, pressure_cost=10),
        # Heat vented below the cap -> next drain is productive.
        _env(
            SOEventType.BOILER_UPDATED,
            tick=2,
            subject=_SUBJECT_A,
            payload={
                "pressure_before": 30,
                "pressure_after": 30,
                "heat_before": _RUPTURE_THRESHOLD,
                "heat_after": 50,
            },
        ),
        _weapon_fired(tick=2, subject=_SUBJECT_A, pressure_cost=10),
        _match_ended(tick=3, winner_id=_PLAYER_A),
    ]
    payload = _single_scored_payload(events)
    # wasted=10, consumed=20 -> efficiency = 1 - 10/20 = 0.5
    assert payload["scores"][_PLAYER_A]["pressure_efficiency"] == pytest.approx(0.5)


@pytest.mark.unit
def test_pressure_drained_while_disabled_is_wasted() -> None:
    events = [
        _match_started(),
        _env(
            SOEventType.BOILER_RUPTURED,
            tick=1,
            subject=_SUBJECT_A,
            payload={"cause": "heat_threshold"},
        ),
        _weapon_fired(tick=1, subject=_SUBJECT_A, pressure_cost=10),
        _match_ended(tick=2, winner_id=_PLAYER_B),
    ]
    payload = _single_scored_payload(events)
    assert payload["scores"][_PLAYER_A]["pressure_efficiency"] == pytest.approx(0.0)


@pytest.mark.unit
def test_self_damage_does_not_count_as_damage_dealt() -> None:
    events = [
        _match_started(),
        _hit_resolved(tick=1, attacker_id=_MECH_A, defender_id=_MECH_A, damage_after_armor=9),
        _match_ended(tick=2, winner_id=_PLAYER_A),
    ]
    payload = _single_scored_payload(events)
    assert payload["scores"][_PLAYER_A]["damage_dealt"] == 0


@pytest.mark.unit
def test_missed_hit_resolved_does_not_count() -> None:
    events = [
        _match_started(),
        _hit_resolved(
            tick=1, attacker_id=_MECH_A, defender_id=_MECH_B, damage_after_armor=9, hit=False
        ),
        _match_ended(tick=2, winner_id=_PLAYER_A),
    ]
    payload = _single_scored_payload(events)
    assert payload["scores"][_PLAYER_A]["damage_dealt"] == 0


# ---------------------------------------------------------------------------
# Terminal triggering + idempotence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_victory_declared_triggers_scoring() -> None:
    events = [
        _match_started(),
        _env(
            SOEventType.VICTORY_DECLARED,
            tick=2,
            payload={"winner_player_id": _PLAYER_A, "reason": "last_mech_standing"},
        ),
    ]
    payload = _single_scored_payload(events)
    assert payload["scores"][_PLAYER_A]["victory"] == 1
    assert payload["scores"][_PLAYER_B]["victory"] == 0


@pytest.mark.unit
def test_scores_exactly_once_for_victory_then_match_ended() -> None:
    events = [
        _match_started(),
        _env(
            SOEventType.VICTORY_DECLARED,
            tick=2,
            payload={"winner_player_id": _PLAYER_A, "reason": "last_mech_standing"},
        ),
        _match_ended(tick=2, winner_id=_PLAYER_A),
        _match_ended(tick=2, winner_id=_PLAYER_A),
    ]
    emitted = _score_events(events)
    scored = [e for e in emitted if e.event_type is SOEventType.MATCH_SCORED]
    assert len(scored) == 1


@pytest.mark.unit
def test_foreign_match_events_are_ignored() -> None:
    events = [
        _match_started(),
        _env(
            SOEventType.MATCH_ENDED,
            tick=2,
            payload={"reason": "last_mech_standing", "winner_id": _PLAYER_A},
            match_id="match.other",
        ),
    ]
    emitted = _score_events(events)
    assert [e for e in emitted if e.event_type is SOEventType.MATCH_SCORED] == []


@pytest.mark.unit
def test_match_ended_before_match_started_raises() -> None:
    reducer = ReducerScoring(_MATCH_ID, emit=lambda _e: None, replay_validity_check=lambda: True)
    with pytest.raises(ReducerError, match="match_not_started"):
        reducer.apply(_match_ended(tick=2, winner_id=_PLAYER_A))


@pytest.mark.unit
def test_unknown_winner_raises() -> None:
    events = [_match_started(), _match_ended(tick=2, winner_id="player.zz")]
    with pytest.raises(ReducerError, match="unknown_winner"):
        _score_events(events)


# ---------------------------------------------------------------------------
# Draws
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_draw_zeroes_victory_and_marks_is_draw() -> None:
    events = [_match_started(), _match_ended(tick=3, winner_id=None)]
    payload = _single_scored_payload(events)
    assert payload["winner"] is None
    assert payload["is_draw"] is True
    assert payload["scores"][_PLAYER_A]["victory"] == 0
    assert payload["scores"][_PLAYER_B]["victory"] == 0
    # Leaderboard convention: alphabetically-first player_id fills the winner slot.
    assert payload["winner_player_id"] == _PLAYER_A


# ---------------------------------------------------------------------------
# Leaderboard contract (Task 30 consumes this payload)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_payload_feeds_leaderboard_handler(tmp_path: Path) -> None:
    payload = _single_scored_payload(_standard_duel_events())
    db_path = tmp_path / "leaderboard.sqlite"
    handler = LeaderboardHandler(db_path)
    handler.on_match_scored(payload)

    rows = LeaderboardProjection(db_path).top_n(1)
    assert len(rows) == 1
    row = rows[0]
    assert row.match_id == _MATCH_ID
    assert row.winner_player_id == _PLAYER_A
    assert row.winner_loadout_id == "loadout.alpha"
    assert row.winner_score == 1230
    assert row.loser_player_id == _PLAYER_B
    assert row.loser_score == 150
    assert row.duration_ticks == 2
    assert row.is_draw is False


# ---------------------------------------------------------------------------
# Replay-validity helper (Task 27 engine, captured at scoring time)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_verify_replay_validity_for_real_match(tmp_path: Path) -> None:
    match_id = "match.scoring.replay-check"
    ledger = SQLiteLedger(tmp_path / f"{match_id}.sqlite")
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)

    runner = MatchRunner(
        match_id=match_id,
        seed=99,
        loadout_a=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        loadout_b=load_loadout(Path("contracts_data/loadouts/example_predictive_heavy.yaml")),
        bus=bus,
        max_ticks=5,
    )
    live_state = runner.run()

    assert verify_replay_validity(ledger, match_id, live_state) is True
    # A mismatched live state must yield False, not raise.
    tampered = live_state.model_copy(update={"seed": live_state.seed + 1})
    assert verify_replay_validity(ledger, match_id, tampered) is False
