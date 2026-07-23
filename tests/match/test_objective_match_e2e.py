"""Phase 4 cross-boundary regression — a REAL match to a vp_threshold terminal.

Drives the actual seam chain, not unit surrogates: MatchRunner → bus → fold
VP scoring → VICTORY_DECLARED(vp_threshold) → MATCH_ENDED → ReducerScoring
(MATCH_SCORED with the replay-validity hard gate) → SQLite ledger →
ReplayEngine reconstruction → fail-closed evidence reprojection
(``project_match_learning_evidence``) reading ``victory_kind``.

A second test runs on the shipped ``foundry_60_asym_v1`` contract and proves
the finish-line seam: MATCH_STARTED carries the self-verifying
``arena_contract_hash`` and the pilots RECEIVE the objective observation
(without which the O-GATE battery would measure blindness, not play).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec, arena_contract_hash
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOObjectiveScoredPayload,
    ModelSOVictoryDeclaredPayload,
)
from steel_onslaught.learning.post_match import project_match_learning_evidence
from steel_onslaught.match.composition import load_loadout, load_match_contract_catalog
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.reducers.scoring import ReducerScoring, verify_replay_validity
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import match_runner
from tests.sqlite_ledger import open_sqlite_ledger

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")


class _HoldPilot:
    """Deterministic pilot that stands its ground (objective-holding double)."""

    def __init__(self) -> None:
        self.observations: list[ModelSOPilotObservation] = []

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        self.observations.append(observation)
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0),),
        )


def _vp_arena() -> ModelSOArenaSpec:
    """Red spawns adjacent to its objective; blue holds far away."""

    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_vp_e2e",
            "display_name": "VP e2e arena",
            "size": 40,
            "spawn_a": {"x": 5, "y": 5},
            "spawn_b": {"x": 35, "y": 35},
            "obstacles": [],
            "rects": [],
            "objectives": [
                {
                    "objective_id": "objective.red_yard",
                    "cell": {"x": 5, "y": 6},
                    "vp_per_round": 1,
                }
            ],
            "vp_threshold": 4,
            "sudden_death_start_tick": 100,
            "sudden_death_damage_base": 8,
        }
    )


@pytest.mark.integration
def test_real_match_reaches_vp_threshold_terminal_with_replay_and_evidence(
    tmp_path: Path,
) -> None:
    match_id = "match.test.vp-e2e"
    ledger = open_sqlite_ledger(tmp_path / "vp-e2e.sqlite")
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)

    loadout = load_loadout(_LOADOUT)
    runner, runtime = match_runner(
        bus=bus,
        match_id=match_id,
        seed=11,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=None,
        arena_override=_vp_arena(),
        pilots_override={"mech.a.01": _HoldPilot(), "mech.b.01": _HoldPilot()},
    )
    scoring = ReducerScoring(
        match_id,
        runner.identity.correlation_id,
        emit=bus.publish,
        event_factory=runtime.event_factory,
        replay_validity_check=lambda: verify_replay_validity(
            ledger,
            match_id,
            runner.fold.state,
            catalog=runtime.catalog,
            event_factory=runtime.event_factory,
        ),
    )
    bus.subscribe(scoring.handle)

    final = runner.run()

    # Terminal: VP threshold, on play, exactly at the finish line.
    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason is SOMatchEndReason.VP_THRESHOLD
    assert final.winner_id == "player.a"
    assert final.vp_totals == {"player.a": 4, "player.b": 0}
    assert final.tick == 4  # 1 VP/round from tick 1: threshold 4 at tick 4

    # Durable canonical chain in the ledger: scored rounds, the victory with
    # its kind, the MATCH_ENDED restatement, and one MATCH_SCORED.
    events = list(ledger.read_all(match_id))
    scored_rounds = [
        ModelSOObjectiveScoredPayload.model_validate(e.payload)
        for e in events
        if e.event_type is SOEventType.OBJECTIVE_SCORED
    ]
    assert [p.cumulative_vp["player.a"] for p in scored_rounds] == [1, 2, 3, 4]
    victory = next(e for e in events if e.event_type is SOEventType.VICTORY_DECLARED)
    victory_payload = ModelSOVictoryDeclaredPayload.model_validate(victory.payload)
    assert victory_payload.reason is SOMatchEndReason.VP_THRESHOLD
    assert victory_payload.victory_kind == "vp_threshold"
    assert any(e.event_type is SOEventType.MATCH_ENDED for e in events)
    scored = [e for e in events if e.event_type is SOEventType.MATCH_SCORED]
    assert len(scored) == 1
    scored_payload = ModelSOMatchScoredPayload.model_validate(scored[0].payload)
    assert scored_payload.winner_player_id == "player.a"
    assert not scored_payload.is_draw
    # The replay-validity hard gate passed at scoring time (score would be 0
    # otherwise and victory grants 1000).
    assert scored_payload.scores["player.a"].replay_validity == 1

    # MATCH_STARTED names the exact arena/objective contract (self-verified).
    started = next(e for e in events if e.event_type is SOEventType.MATCH_STARTED)
    started_payload = ModelSOMatchStartedPayload.model_validate(started.payload)
    assert started_payload.arena_contract_hash == arena_contract_hash(_vp_arena().to_snapshot())

    # Replay identity through the real engine, VP fold included.
    replay = ReplayEngine(
        ledger,
        match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    reconstructed = replay.reconstruct_at_tick(final.tick)
    assert reconstructed == final
    assert reconstructed.vp_totals == {"player.a": 4, "player.b": 0}

    # Fail-closed evidence reprojection over the FULL stream (the census trap:
    # an unregistered OBJECTIVE_SCORED payload would raise here), and the
    # projector surfaces HOW the match ended.
    evidence = project_match_learning_evidence(events)
    assert evidence.victory_kind == "vp_threshold"
    assert evidence.winner_player_id == "player.a"
    assert evidence.event_counts["objective_scored"] == 4


@pytest.mark.integration
def test_foundry_60_asym_v1_match_carries_hash_and_objective_observations(
    tmp_path: Path,
) -> None:
    """The shipped Phase 4 arena drives hash provenance + pilot objective view."""

    arena = load_match_contract_catalog(Path("contracts_data")).arenas["foundry_60_asym_v1"]
    match_id = "match.test.asym-observe"
    ledger = open_sqlite_ledger(tmp_path / "asym.sqlite")
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)

    loadout = load_loadout(_LOADOUT)
    red_pilot, blue_pilot = _HoldPilot(), _HoldPilot()
    runner, runtime = match_runner(
        bus=bus,
        match_id=match_id,
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=3,
        arena_override=arena,
        pilots_override={"mech.a.01": red_pilot, "mech.b.01": blue_pilot},
    )
    final = runner.run()
    assert final.status is SOMatchStatus.ENDED

    events = list(ledger.read_all(match_id))
    started = next(e for e in events if e.event_type is SOEventType.MATCH_STARTED)
    started_payload = ModelSOMatchStartedPayload.model_validate(started.payload)
    assert started_payload.arena_contract_hash == arena_contract_hash(arena.to_snapshot())
    assert started_payload.arena.vp_threshold == 15
    assert len(started_payload.arena.objectives) == 3

    # PILOTS SEE THE OBJECTIVES: every observation carries the full ladder,
    # viewer-relative control, own distance, and the VP scoreboard.
    assert red_pilot.observations
    observation = red_pilot.observations[0]
    assert [o.objective_id for o in observation.objectives] == [
        "objective.east_gate",
        "objective.north_works",
        "objective.west_yard",
    ]
    west = next(o for o in observation.objectives if o.objective_id == "objective.west_yard")
    assert west.control == "unclaimed"
    assert west.own_distance_chebyshev == 14  # spawn (4,30) -> cell (18,30)
    assert observation.victory_points is not None
    assert observation.victory_points.vp_threshold == 15
    assert observation.victory_points.own_vp == 0

    # Neither side reached anything in 3 ticks: no scoring, and replay of the
    # NEW arena's stream reproduces the live state (old foundry_60 replay
    # coverage lives in tests/replay/test_engine.py, unchanged).
    assert not [e for e in events if e.event_type is SOEventType.OBJECTIVE_SCORED]
    replay = ReplayEngine(
        ledger,
        match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    assert replay.reconstruct_at_tick(final.tick) == final
