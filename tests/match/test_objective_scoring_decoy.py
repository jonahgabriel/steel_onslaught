"""SO-OBJ-DECOY — ``objective_scoring: decoy``, the non-scoring-objectives flag.

What this file proves, in the order the flag has to earn trust:

A. **Default is byte-invisible.**  ``tests/match/golden/arena_contract_hashes.json``
   was MINTED FROM ``main`` (the pre-flag tree) by hashing every shipped arena
   contract.  With the flag defaulting to ``"scoring"`` and excluded from
   serialization at that value, this tree must reproduce those digests exactly.
   ``arena_contract_hash`` feeds ``MATCH_STARTED.arena_contract_hash``, which is
   self-verifying against the embedded snapshot, so a drift here would
   invalidate every historical ledger — the strongest available single check
   that the flag is additive.  The goldens were not minted from this tree's own
   output; a golden minted from the code it guards proves nothing.

B. **Decoy suppresses exactly the payout, through a real match.**  The same
   ``_HoldPilot`` match that reaches a ``vp_threshold`` terminal in
   ``test_objective_match_e2e`` is re-run with one field changed, and drives the
   full seam chain (runner → bus → fold → ledger → replay).  Zero
   ``OBJECTIVE_SCORED``, zero VP, no VP victory, and the replay reproduces the
   suppression from the RECORDED snapshot rather than from live config.

C. **The pilot still SEES the objectives.**  This is the experimental point, not
   a nicety: an arm whose pilots stopped being told about objectives would just
   be a slower ``foundry_60_asym_v1_noobj``.  The same match's captured
   observations carry all three fields the prompt renders — cells,
   ``vp_per_round``, and the ``vp_threshold`` scoreboard.

D. **It is fail-closed against the one mechanism it silently breaks.**  A
   ``utility_incentive`` (SO-UTIL-MECH) pays into ``vp_totals``, and a decoy
   arena never settles ``vp_totals``.  That combination is rejected at the
   composition boundary and again at the ``MATCH_STARTED`` payload boundary —
   the live AND replay paths — rather than paying into a dead total.  ``decoy``
   on an objective-free arena is likewise rejected at the contract boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import (
    ModelSOArenaSpec,
    arena_contract_hash,
)
from steel_onslaught.contracts.incentive import ModelSOUtilityIncentive
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import ModelSOMatchStartedPayload
from steel_onslaught.match.composition import (
    build_runtime_dependencies,
    load_application_overlay,
    load_loadout,
    load_match_contract_catalog,
)
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.match.utility_incentive_fixtures import arena_payload, match_started_payload
from tests.runtime import match_runner
from tests.sqlite_ledger import open_sqlite_ledger

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_GOLDEN_DIR = Path(__file__).parent / "golden"
_CONTRACTS_DIR = Path("contracts_data")
_DECOY_OVERLAY = (
    _CONTRACTS_DIR / "overlays" / "tactical_split_overdeal_utility_asym_v1_decoyobj_qwen.yaml"
)


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


def _vp_arena(objective_scoring: str = "scoring") -> ModelSOArenaSpec:
    """Red spawns adjacent to its objective; blue holds far away.

    Copied field-for-field from ``tests/match/test_objective_match_e2e.py`` so
    the decoy run below is the SAME match that file drives to a ``vp_threshold``
    terminal, with one field changed and nothing else.
    """

    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_vp_decoy" if objective_scoring == "decoy" else "test_vp_e2e",
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
            "objective_scoring": objective_scoring,
            "sudden_death_start_tick": 100,
            "sudden_death_damage_base": 8,
        }
    )


# ---------------------------------------------------------------------------
# A. Default OFF ("scoring") is byte-invisible against pre-change goldens
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_shipped_arena_contract_hashes_match_pre_flag_goldens() -> None:
    """Every pre-existing arena digests exactly as it did before the flag.

    ``arena_contract_hash`` is the canonical sha256 of the snapshot's
    ``model_dump``.  If ``objective_scoring`` serialized at its default, every
    one of these digests would move and every recorded
    ``MATCH_STARTED.arena_contract_hash`` in every historical ledger would fail
    its own self-verification.
    """

    golden = json.loads((_GOLDEN_DIR / "arena_contract_hashes.json").read_text(encoding="utf-8"))
    catalog = load_match_contract_catalog(_CONTRACTS_DIR)
    for arena_id, expected in sorted(golden.items()):
        arena = catalog.arenas[arena_id]
        assert arena_contract_hash(arena.to_snapshot()) == expected, (
            f"arena_contract_hash drifted for {arena_id!r}; the objective_scoring "
            "flag must stay excluded from serialization at its default"
        )


@pytest.mark.unit
def test_scoring_default_is_absent_from_serialization_and_decoy_is_present() -> None:
    """The key exists on the wire ONLY when it carries information."""

    scoring = _vp_arena().to_snapshot().model_dump(mode="json")
    decoy = _vp_arena("decoy").to_snapshot().model_dump(mode="json")
    assert "objective_scoring" not in scoring
    assert decoy["objective_scoring"] == "decoy"
    # And the decoy arena is therefore a DIFFERENT contract, correctly.
    assert arena_contract_hash(_vp_arena().to_snapshot()) != arena_contract_hash(
        _vp_arena("decoy").to_snapshot()
    )


@pytest.mark.unit
def test_decoy_survives_a_snapshot_round_trip() -> None:
    """A replay parses the mode back out of the recorded bytes, not config."""

    snapshot = _vp_arena("decoy").to_snapshot()
    reparsed = type(snapshot).model_validate(snapshot.model_dump(mode="json"))
    assert reparsed.objective_scoring == "decoy"
    assert reparsed == snapshot


# ---------------------------------------------------------------------------
# B + C. A real decoy match: payout suppressed, objectives still shown
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_decoy_match_scores_nothing_and_still_shows_objectives(tmp_path: Path) -> None:
    """The match that hits a VP terminal at tick 4 now never scores at all."""

    match_id = "match.test.vp-decoy"
    ledger = open_sqlite_ledger(tmp_path / "vp-decoy.sqlite")
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)

    loadout = load_loadout(_LOADOUT)
    red_pilot = _HoldPilot()
    runner, runtime = match_runner(
        bus=bus,
        match_id=match_id,
        seed=11,
        loadout_a=loadout,
        loadout_b=loadout,
        # The scoring twin ends at tick 4 on the VP threshold; this arm has no
        # VP path at all, so the run needs an explicit ceiling.
        max_ticks=12,
        arena_override=_vp_arena("decoy"),
        pilots_override={"mech.a.01": red_pilot, "mech.b.01": _HoldPilot()},
    )

    final = runner.run()

    # B. Nothing scored, nothing was declared, and no VP accrued — while the
    # scoring twin reached {"player.a": 4} and a VP_THRESHOLD terminal.
    assert final.end_reason is not SOMatchEndReason.VP_THRESHOLD
    assert final.vp_totals in ({}, {"player.a": 0, "player.b": 0})
    events = list(ledger.read_all(match_id))
    assert [e for e in events if e.event_type is SOEventType.OBJECTIVE_SCORED] == []
    assert [e for e in events if e.event_type is SOEventType.VICTORY_DECLARED] == []
    assert final.status is SOMatchStatus.ENDED
    # The match ran well past the tick the scoring twin ended on, so "no
    # terminal" is a suppressed payout, not a short match.
    assert final.tick > 4

    # MATCH_STARTED recorded the decoy contract, self-verified against the
    # embedded snapshot — the replay path reads the mode from here.
    started = next(e for e in events if e.event_type is SOEventType.MATCH_STARTED)
    started_payload = ModelSOMatchStartedPayload.model_validate(started.payload)
    assert started_payload.arena.objective_scoring == "decoy"
    assert started_payload.arena_contract_hash == arena_contract_hash(
        _vp_arena("decoy").to_snapshot()
    )

    # C. The pilot was still TOLD about the objective every tick: cells,
    # vp_per_round, and a live vp_threshold scoreboard reading 0-0.
    assert red_pilot.observations, "the pilot must have been asked to decide"
    for observation in red_pilot.observations:
        assert len(observation.objectives) == 1
        objective = observation.objectives[0]
        assert objective.objective_id == "objective.red_yard"
        assert objective.vp_per_round == 1
        assert observation.victory_points is not None
        assert observation.victory_points.vp_threshold == 4
        assert observation.victory_points.own_vp == 0
        assert observation.victory_points.enemy_vp == 0
    # The pilot standing ON its objective is what would have scored: control is
    # reported as its own, and it still paid nothing.
    assert any(o.objectives[0].control == "own" for o in red_pilot.observations)

    # Replay identity: a bus-less refold of the recorded stream reproduces the
    # same zero-VP state, so the suppression is durable in the ledger.
    replay = ReplayEngine(
        ledger,
        match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    reconstructed = replay.reconstruct_at_tick(final.tick)
    assert reconstructed == final
    assert not any(vp for vp in reconstructed.vp_totals.values())


# ---------------------------------------------------------------------------
# D. Fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_decoy_without_objectives_is_rejected_at_the_contract_boundary() -> None:
    """A decoy with nothing to decoy is a configured no-op, not a mode."""

    with pytest.raises(ValidationError, match="declares objective_scoring='decoy'"):
        ModelSOArenaSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.arena",
                "arena_id": "test_decoy_empty",
                "display_name": "empty decoy",
                "size": 40,
                "spawn_a": {"x": 5, "y": 5},
                "spawn_b": {"x": 35, "y": 35},
                "obstacles": [],
                "rects": [],
                "objective_scoring": "decoy",
            }
        )


def _decoy_match_started_payload(incentive_dump: dict[str, Any] | None) -> dict[str, Any]:
    """The SO-UTIL-MECH incentive fixture with its arena flipped to decoy."""

    payload = match_started_payload(incentive_dump)
    payload["arena"] = {**arena_payload(), "objective_scoring": "decoy"}
    return payload


@pytest.mark.unit
def test_utility_incentive_on_a_decoy_arena_is_rejected_at_the_payload_boundary() -> None:
    """The bounty pays into vp_totals; a decoy arena never settles vp_totals."""

    incentive = ModelSOUtilityIncentive(vp_per_deploy=2).model_dump(mode="json")
    # Sanity, in both directions, so the rejection below is attributable to the
    # MODE and not to the fixture: the incentive is accepted on the scoring
    # arena, and the decoy arena is accepted without an incentive.
    ModelSOMatchStartedPayload.model_validate(match_started_payload(incentive))
    ModelSOMatchStartedPayload.model_validate(_decoy_match_started_payload(None))

    with pytest.raises(ValidationError, match="decoy-scoring arena"):
        ModelSOMatchStartedPayload.model_validate(_decoy_match_started_payload(incentive))


@pytest.mark.unit
def test_utility_incentive_on_a_decoy_arena_is_rejected_at_composition(tmp_path: Path) -> None:
    """The earlier, friendlier failure: the overlay dies before a battery runs.

    Driven through the REAL composition root against the SHIPPED decoy overlay,
    with only its durable roots redirected into ``tmp_path`` (the battery driver
    rewrites the same paths from ``--state-root``, so redirection is the normal
    operating mode, not a test-only shortcut).  Catching the mis-binding here
    costs nothing; catching it at the payload boundary costs a battery.
    """

    overlay = load_application_overlay(_DECOY_OVERLAY)
    assert overlay.contracts.utility_incentive is None, "the shipped lane binds no bounty"
    contaminated = overlay.model_copy(
        update={
            "event_ledger": overlay.event_ledger.model_copy(
                update={"path": tmp_path / "events.sqlite3"}
            ),
            "leaderboard": overlay.leaderboard.model_copy(
                update={"path": tmp_path / "leaderboard.sqlite3"}
            ),
            "learning_artifacts": overlay.learning_artifacts.model_copy(
                update={
                    "evaluation_root": tmp_path / "evaluations",
                    "lineage_root": tmp_path / "lineage",
                    "experiment_root": tmp_path / "experiments",
                }
            ),
            "evaluation_storage": overlay.evaluation_storage.model_copy(
                update={"root": tmp_path / "evaluation_storage"}
            ),
            "contracts": overlay.contracts.model_copy(
                update={"utility_incentive": ModelSOUtilityIncentive(vp_per_deploy=2)}
            ),
        }
    )
    with pytest.raises(ValueError, match="objective_scoring='decoy'"):
        build_runtime_dependencies(contaminated)
