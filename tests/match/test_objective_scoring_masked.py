"""SO-OBJ-MASK — ``objective_display: masked``, the masked-objective-view flag.

The live-stakes complement to SO-OBJ-DECOY
(``tests/match/test_objective_scoring_decoy.py``, PR #210/#212). DECOY
suppressed the PAYOUT while keeping the pilot's VIEW unchanged; this flag
suppresses the VIEW while keeping the payout unchanged. What this file proves,
mirrored and inverted from DECOY's own four claims:

A. **Default is byte-invisible.** Same golden file
   (``tests/match/golden/arena_contract_hashes.json``, minted from pre-flag
   ``main``) proves ``objective_display`` defaulting to ``"visible"`` and
   excluded from serialization moves no shipped arena's
   ``arena_contract_hash`` — the same self-verification argument DECOY's own
   Claim A makes, reused rather than re-derived, because both flags share the
   identical additive mechanism (``exclude_if`` at the default).

B. **Masked scores exactly like visible, through a real match.** The SAME
   ``_HoldPilot`` match ``test_objective_match_e2e.py`` drives to a
   ``vp_threshold`` terminal is re-run with ONLY ``objective_display``
   flipped, and reaches the IDENTICAL terminal — same ``vp_totals``, same
   ``OBJECTIVE_SCORED`` sequence, same ``VICTORY_DECLARED`` — proving
   ``MatchStateFold`` never reads this field.

C. **The pilot never sees it, for the whole match, despite real scoring.**
   This is the experimental point: the SAME match's captured observations
   carry ``objectives == ()`` and ``victory_points is None`` on EVERY tick,
   including the tick the match actually wins on VP — the observation is
   structurally identical to what an objective-free arena already produces,
   even though ``vp_totals`` is climbing in the background.

D. **It is fail-closed against the no-op it would otherwise silently be.**
   ``objective_display="masked"`` on an objective-free arena is rejected at
   the contract boundary, mirroring DECOY's own guard for the same reason:
   masking a view that would already be empty is not a mode.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import (
    ModelSOArenaSpec,
    arena_contract_hash,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchStartedPayload,
    ModelSOObjectiveScoredPayload,
)
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import match_runner
from tests.sqlite_ledger import open_sqlite_ledger

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_GOLDEN_DIR = Path(__file__).parent / "golden"
_CONTRACTS_DIR = Path("contracts_data")


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


def _vp_arena(objective_display: str = "visible") -> ModelSOArenaSpec:
    """Red spawns adjacent to its objective; blue holds far away.

    Copied field-for-field from ``tests/match/test_objective_match_e2e.py``
    (and from DECOY's own ``_vp_arena``) so the masked run below is the SAME
    match that file drives to a ``vp_threshold`` terminal, with one field
    changed and nothing else.
    """

    return ModelSOArenaSpec.model_validate(
        {
            "schema_version": "0.1.0",
            "kind": "steel_onslaught.arena",
            "arena_id": "test_vp_masked" if objective_display == "masked" else "test_vp_visible",
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
            "objective_display": objective_display,
            "sudden_death_start_tick": 100,
            "sudden_death_damage_base": 8,
        }
    )


# ---------------------------------------------------------------------------
# A. Default OFF ("visible") is byte-invisible against pre-flag goldens
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_shipped_arena_contract_hashes_match_pre_flag_goldens() -> None:
    """Every pre-existing arena digests exactly as it did before this flag.

    Reuses the same golden file DECOY's own equivalent test reads
    (``tests/match/golden/arena_contract_hashes.json``, minted from
    pre-``objective_scoring``/pre-``objective_display`` ``main``): if
    ``objective_display`` serialized at its default, every one of these
    digests would move.
    """

    from steel_onslaught.match.composition import load_match_contract_catalog

    golden = json.loads((_GOLDEN_DIR / "arena_contract_hashes.json").read_text(encoding="utf-8"))
    catalog = load_match_contract_catalog(_CONTRACTS_DIR)
    for arena_id, expected in sorted(golden.items()):
        arena = catalog.arenas[arena_id]
        assert arena_contract_hash(arena.to_snapshot()) == expected, (
            f"arena_contract_hash drifted for {arena_id!r}; the objective_display "
            "flag must stay excluded from serialization at its default"
        )


@pytest.mark.unit
def test_visible_default_is_absent_from_serialization_and_masked_is_present() -> None:
    """The key exists on the wire ONLY when it carries information."""

    visible = _vp_arena().to_snapshot().model_dump(mode="json")
    masked = _vp_arena("masked").to_snapshot().model_dump(mode="json")
    assert "objective_display" not in visible
    assert masked["objective_display"] == "masked"
    # And the masked arena is therefore a DIFFERENT contract, correctly.
    assert arena_contract_hash(_vp_arena().to_snapshot()) != arena_contract_hash(
        _vp_arena("masked").to_snapshot()
    )


@pytest.mark.unit
def test_masked_survives_a_snapshot_round_trip() -> None:
    """A replay parses the mode back out of the recorded bytes, not config."""

    snapshot = _vp_arena("masked").to_snapshot()
    reparsed = type(snapshot).model_validate(snapshot.model_dump(mode="json"))
    assert reparsed.objective_display == "masked"
    assert reparsed == snapshot


# ---------------------------------------------------------------------------
# B + C. A real masked match: payout unaffected, objectives never shown
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_masked_match_scores_normally_and_never_shows_objectives(tmp_path: Path) -> None:
    """The match that hits a VP terminal at tick 4 still hits it at tick 4 —
    the pilot just never sees why."""

    match_id = "match.test.vp-masked"
    ledger = open_sqlite_ledger(tmp_path / "vp-masked.sqlite")
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
        max_ticks=None,
        arena_override=_vp_arena("masked"),
        pilots_override={"mech.a.01": red_pilot, "mech.b.01": _HoldPilot()},
    )

    final = runner.run()

    # B. Scoring is UNCHANGED from the visible twin
    # (test_objective_match_e2e.py::
    # test_real_match_reaches_vp_threshold_terminal_with_replay_and_evidence):
    # same terminal, same winner, same VP totals, same tick.
    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason is SOMatchEndReason.VP_THRESHOLD
    assert final.winner_id == "player.a"
    assert final.vp_totals == {"player.a": 4, "player.b": 0}
    assert final.tick == 4

    events = list(ledger.read_all(match_id))
    scored_rounds = [
        ModelSOObjectiveScoredPayload.model_validate(e.payload)
        for e in events
        if e.event_type is SOEventType.OBJECTIVE_SCORED
    ]
    assert [p.cumulative_vp["player.a"] for p in scored_rounds] == [1, 2, 3, 4]
    assert any(e.event_type is SOEventType.VICTORY_DECLARED for e in events)

    # MATCH_STARTED recorded the masked contract, self-verified against the
    # embedded snapshot -- the flag is durable provenance even though it
    # changes nothing about how the fold scored this match.
    started = next(e for e in events if e.event_type is SOEventType.MATCH_STARTED)
    started_payload = ModelSOMatchStartedPayload.model_validate(started.payload)
    assert started_payload.arena.objective_display == "masked"
    assert started_payload.arena_contract_hash == arena_contract_hash(
        _vp_arena("masked").to_snapshot()
    )

    # C. The pilot was NEVER told about the objective, on any tick, including
    # the tick the match was actually won on VP.
    assert red_pilot.observations, "the pilot must have been asked to decide"
    for observation in red_pilot.observations:
        assert observation.objectives == ()
        assert observation.victory_points is None

    # Replay identity: a bus-less refold of the recorded stream reproduces the
    # SAME real VP state (unlike DECOY, which reproduces zero) -- the display
    # flag never touched what actually happened.
    replay = ReplayEngine(
        ledger,
        match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    reconstructed = replay.reconstruct_at_tick(final.tick)
    assert reconstructed == final
    assert reconstructed.vp_totals == {"player.a": 4, "player.b": 0}


@pytest.mark.integration
def test_visible_twin_reaches_the_identical_terminal(tmp_path: Path) -> None:
    """Sanity control: the ONLY thing that changed is what the pilot saw.

    Runs the exact same fixture with ``objective_display`` left at its
    default and asserts the terminal is identical to the masked run above --
    proving the comparison is attributable to the display flag alone, not to
    an accidental difference in the two arena fixtures.
    """

    match_id = "match.test.vp-visible-twin"
    ledger = open_sqlite_ledger(tmp_path / "vp-visible-twin.sqlite")
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)

    loadout = load_loadout(_LOADOUT)
    red_pilot = _HoldPilot()
    runner, _ = match_runner(
        bus=bus,
        match_id=match_id,
        seed=11,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=None,
        arena_override=_vp_arena("visible"),
        pilots_override={"mech.a.01": red_pilot, "mech.b.01": _HoldPilot()},
    )
    final = runner.run()

    assert final.end_reason is SOMatchEndReason.VP_THRESHOLD
    assert final.vp_totals == {"player.a": 4, "player.b": 0}
    assert final.tick == 4
    # And this time the pilot WAS told, on every tick.
    assert red_pilot.observations
    for observation in red_pilot.observations:
        assert observation.objectives != ()
        assert observation.victory_points is not None


# ---------------------------------------------------------------------------
# D. Fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_masked_without_objectives_is_rejected_at_the_contract_boundary() -> None:
    """A mask with nothing to hide is a configured no-op, not a mode."""

    with pytest.raises(ValidationError, match="declares objective_display='masked'"):
        ModelSOArenaSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.arena",
                "arena_id": "test_mask_empty",
                "display_name": "empty mask",
                "size": 40,
                "spawn_a": {"x": 5, "y": 5},
                "spawn_b": {"x": 35, "y": 35},
                "obstacles": [],
                "rects": [],
                "objective_display": "masked",
            }
        )
