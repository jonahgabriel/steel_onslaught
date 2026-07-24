"""Tests for the ReplayEngine — Task 27 invariants.

Critical invariants:
- reconstruct_at_tick(final_tick) == live_final_state (round-trip determinism)
- reconstruct_at_tick(N).tick == N for all N <= final_tick
- step_forward() then step_backward() yields the same state as reconstructing at N
- all_ticks() returns sorted list of distinct tick numbers present in the ledger
- events_at_tick(tick) returns all events with that tick, in canonical order
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
import ulid
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec, neutral_historical_arena_snapshot
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanDecisionSource,
    ModelSOHumanSeatAssignment,
    ModelSOMatchLaunchProvenance,
    ModelSOModelSeatAssignment,
)
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.immutable import thaw_json_mapping
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.composition import load_loadout, load_pilot_registry
from steel_onslaught.match.fold import MatchContractCatalog, MissingMatchContractError
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.match.state import ModelSOMatchState, SOMatchStatus
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPosition,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.movement import chebyshev
from steel_onslaught.replay.engine import ReplayEngine
from tests.fixtures.event_samples import build_sample_envelopes
from tests.match.test_runner_move_intent import _MATCH_SUBJECT, _mech_payload, _onex_envelope
from tests.runtime import match_runner, pilot_from_spec, runtime_dependencies
from tests.sqlite_ledger import open_sqlite_ledger

LOADOUT_A = Path("contracts_data/loadouts/example_aggressive_light.yaml")
LOADOUT_B = Path("contracts_data/loadouts/example_predictive_heavy.yaml")

MATCH_ID = "match.2026-04-30.replay-test"
SEED = 12345
MAX_TICKS = 5  # short so tests run fast


class _ReplayHumanDecisionPilot:
    source = ModelSOHumanDecisionSource(
        kind="human",
        input_source="browser_command",
        command_id=UUID("33333333-3333-4333-8333-333333333333"),
        turn_id="turn.match_01jabcde.tick_000001.red",
        observation_sha256="6" * 64,
    )

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        del observation
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            action_params={},
            reason_code=SOPilotReasonCode.HUMAN_INPUT,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0),),
            decision_source=self.source,
        )


class _MemoryLedger:
    def __init__(self, events: list[ModelSOEventEnvelope]) -> None:
        self._events = events

    def append(self, event: ModelSOEventEnvelope) -> None:
        self._events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return (event for event in self._events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return (
            event
            for event in self._events
            if event.match_id == match_id and event.tick > after_tick
        )


def _arena_for_replay(*, obstacle: bool) -> ModelSOArenaSpec:
    return ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="replay_wall" if obstacle else "replay_open",
        display_name="Replay movement test arena",
        size=40,
        spawn_a=ModelSOPosition(x=5, y=5),
        spawn_b=ModelSOPosition(x=35, y=35),
        obstacles=(ModelSOPosition(x=6, y=5),) if obstacle else (),
        rects=(),
    )


def _started_for_arena(
    arena: ModelSOArenaSpec,
) -> tuple[ModelSOEventEnvelope, MatchContractCatalog, EventFactory]:
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    runner, runtime = match_runner(
        bus=bus,
        match_id="match.test.replay-forged-movement",
        seed=SEED,
        loadout_a=load_loadout(LOADOUT_A),
        loadout_b=load_loadout(LOADOUT_B),
        max_ticks=1,
        arena_override=arena,
    )
    runner.run()
    started = next(event for event in events if event.event_type is SOEventType.MATCH_STARTED)
    return started, runtime.catalog, runtime.event_factory


def _forged_movement(
    started: ModelSOEventEnvelope,
    destination: ModelSOPosition,
) -> ModelSOEventEnvelope:
    origin = ModelSOPosition(x=5, y=5)
    raw = started.model_dump(mode="json")
    raw.update(
        {
            "event_id": "01J00000000000000000000000",
            "tick": 1,
            "sequence_in_tick": 0,
            "event_type": SOEventType.MOVEMENT_RESOLVED.value,
            "producer_node": "node.test.forged",
            "subject": {"mech_id": "mech.a.01", "player_id": "player.a"},
            "payload": {
                "from": origin.model_dump(mode="json"),
                "to": destination.model_dump(mode="json"),
                "ticks_consumed": 1,
                "pressure_consumed": chebyshev(origin, destination),
            },
        }
    )
    return ModelSOEventEnvelope.model_validate(raw)


@pytest.mark.integration
def test_replay_uses_injected_catalog_without_lookup() -> None:
    event = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    runtime = runtime_dependencies()

    replay = ReplayEngine(
        _MemoryLedger([event]),
        event.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )

    assert replay._catalog is runtime.catalog


@pytest.mark.integration
def test_replay_retains_the_same_immutable_card_snapshot_as_composition() -> None:
    event = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    runtime = runtime_dependencies()
    cards = ModelSOCardCatalog(
        cards=(
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.advance",
                display_name="Advance",
                category=SOCardCategory.MOVEMENT,
                priority=100,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
        )
    )
    replay = ReplayEngine(
        _MemoryLedger([event]),
        event.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        card_catalog=cards,
    )

    assert replay.card_catalog is cards
    assert cards.cards[0].priority == 100


@pytest.mark.unit
def test_replay_rejects_empty_stream_without_identity_fallback() -> None:
    runtime = runtime_dependencies()
    with pytest.raises(ValueError, match="no events"):
        ReplayEngine(
            _MemoryLedger([]),
            "match.empty",
            catalog=runtime.catalog,
            event_factory=runtime.event_factory,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("destination", "has_wall", "error"),
    [
        (ModelSOPosition(x=7, y=5), True, "obstacle_blocked"),
        (ModelSOPosition(x=-1, y=5), False, "arena_bounds"),
        (ModelSOPosition(x=6, y=5), True, "obstacle_blocked"),
    ],
    ids=["cross-wall-path", "out-of-bounds-destination", "obstacle-endpoint"],
)
def test_replay_rejects_forged_arena_movement(
    destination: ModelSOPosition,
    has_wall: bool,
    error: str,
) -> None:
    arena = _arena_for_replay(obstacle=has_wall)
    started, catalog, event_factory = _started_for_arena(arena)
    movement = _forged_movement(started, destination)
    replay = ReplayEngine(
        _MemoryLedger([started, movement]),
        started.match_id,
        catalog=catalog,
        event_factory=event_factory,
    )

    with pytest.raises(ReducerError, match=error):
        replay.reconstruct_at_tick(1)


@pytest.mark.integration
def test_historical_arena_migration_requires_explicit_offline_opt_in(
    tmp_path: Path,
) -> None:
    _live_state, ledger = _run_and_record(tmp_path, max_ticks=1)
    current = next(ledger.read_all(MATCH_ID))
    raw = current.model_dump(mode="json")
    del raw["payload"]["arena"]
    historical = ModelSOEventEnvelope.model_validate(raw)
    runtime = runtime_dependencies()
    default_replay = ReplayEngine(
        _MemoryLedger([historical]),
        historical.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )

    with pytest.raises(ValueError, match="explicit offline arena migration"):
        default_replay.reconstruct_at_tick(0)

    explicit = ReplayEngine(
        _MemoryLedger([historical]),
        historical.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        historical_arena_migration=neutral_historical_arena_snapshot(
            size=40,
            spawn_a=ModelSOPosition(x=5, y=5),
            spawn_b=ModelSOPosition(x=35, y=35),
        ),
    )
    assert explicit.reconstruct_at_tick(0).status is SOMatchStatus.RUNNING

    mismatched = ReplayEngine(
        _MemoryLedger([historical]),
        historical.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        historical_arena_migration=neutral_historical_arena_snapshot(
            size=40,
            spawn_a=ModelSOPosition(x=4, y=4),
            spawn_b=ModelSOPosition(x=35, y=35),
        ),
    )
    with pytest.raises(ValidationError, match="canonical roster order"):
        mismatched.reconstruct_at_tick(0)


def _run_and_record(
    tmp_path: Path,
    *,
    match_id: str = MATCH_ID,
    seed: int = SEED,
    max_ticks: int = MAX_TICKS,
) -> tuple[ModelSOMatchState, SQLiteLedger]:
    """Run a match and record all events to a SQLite ledger.

    Returns the live final state and an open ledger (same file) for replay.
    """
    ledger_path = tmp_path / f"{match_id}.sqlite"
    ledger = open_sqlite_ledger(ledger_path)
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)

    runner, _runtime = match_runner(
        bus=bus,
        match_id=match_id,
        seed=seed,
        loadout_a=load_loadout(LOADOUT_A),
        loadout_b=load_loadout(LOADOUT_B),
        max_ticks=max_ticks,
    )
    live_state = runner.run()
    return live_state, ledger


def _replay(ledger: SQLiteLedger, match_id: str = MATCH_ID) -> ReplayEngine:
    runtime = runtime_dependencies()
    return ReplayEngine(
        ledger,
        match_id=match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )


def _catalog_without(
    catalog: MatchContractCatalog,
    contract_kind: Literal["chassis", "sensor", "weapon", "gizmo"],
    contract_id: str,
) -> MatchContractCatalog:
    chassis = dict(catalog.chassis)
    boilers = dict(catalog.boilers)
    sensors = dict(catalog.sensors)
    weapons = dict(catalog.weapons)
    gizmos = dict(catalog.gizmos)
    transitions = dict(catalog.transitions)
    match contract_kind:
        case "chassis":
            chassis.pop(contract_id)
        case "sensor":
            sensors.pop(contract_id)
        case "weapon":
            weapons.pop(contract_id)
        case "gizmo":
            gizmos.pop(contract_id)
    return MatchContractCatalog(
        arenas=dict(catalog.arenas),
        chassis=chassis,
        boilers=boilers,
        sensors=sensors,
        weapons=weapons,
        gizmos=gizmos,
        transitions=transitions,
    )


# ---------------------------------------------------------------------------
# Round-trip determinism (the critical invariant from the plan)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_replay_reproduces_live_state(tmp_path: Path) -> None:
    """reconstruct_at_tick(final_tick) must equal the live final state exactly."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state


@pytest.mark.integration
def test_sqlite_replay_preserves_selected_launch_and_human_decision_provenance(
    tmp_path: Path,
) -> None:
    match_id = "match.01JABCDE0123456789ABCDEFGX"
    red = load_loadout(LOADOUT_A)
    blue = load_loadout(LOADOUT_B)
    provenance = ModelSOMatchLaunchProvenance(
        schema_version="1",
        kind="steel_onslaught.match_launch_provenance",
        match_id=match_id,
        launch_command_id=UUID("11111111-1111-4111-8111-111111111111"),
        launch_command_sha256="1" * 64,
        overlay_sha256="2" * 64,
        roster_id="roster.local_play",
        roster_sha256="3" * 64,
        seat_assignments=(
            ModelSOHumanSeatAssignment(
                kind="human",
                side="red",
                player_id="player.red",
                option_id="player_option.browser_human",
                loadout_id=red.id,
                pilot_spec_id=red.pilot_id,
                option_sha256="4" * 64,
                human_identity_id="human_identity.local_operator",
                input_source="browser_command",
            ),
            ModelSOModelSeatAssignment(
                kind="model",
                side="blue",
                player_id="player.blue",
                option_id="player_option.local_stub",
                loadout_id=blue.id,
                pilot_spec_id=blue.pilot_id,
                option_sha256="5" * 64,
                model_identity_id="model_identity.local_stub",
                persona_id="predictive",
                input_source="llm_completion",
            ),
        ),
    )
    runtime = runtime_dependencies()
    registry = load_pilot_registry(Path("contracts_data/pilots"))
    ledger = open_sqlite_ledger(tmp_path / "selected-provenance.sqlite")
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)
    runner = MatchRunner(
        identity=MatchIdentity(
            match_id=match_id,
            correlation_id=runtime.event_factory.identities.new_correlation_id(),
        ),
        seed=SEED,
        loadout_a=red,
        loadout_b=blue,
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
        arena=runtime.arena,
        pilots={
            "mech.red.01": _ReplayHumanDecisionPilot(),
            "mech.blue.01": pilot_from_spec(registry.resolve(blue)),
        },
        max_ticks=2,
        side_a="red",
        side_b="blue",
        launch_provenance=provenance,
    )

    live_final = runner.run()
    persisted = list(ledger.read_all(match_id))
    started = persisted[0]
    human_decision = next(
        event
        for event in persisted
        if event.event_type is SOEventType.PILOT_DECISION_MADE
        and event.subject.mech_id == "mech.red.01"
    )
    assert thaw_json_mapping(started.payload)["launch_provenance"] == provenance.model_dump(
        mode="json"
    )
    assert thaw_json_mapping(human_decision.payload)[
        "decision_source"
    ] == _ReplayHumanDecisionPilot.source.model_dump(mode="json")

    replay = ReplayEngine(
        ledger,
        match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    replayed_started = replay.events_at_tick(0)[0]
    replayed_decision = next(
        event
        for event in replay.events_at_tick(human_decision.tick)
        if event.event_id == human_decision.event_id
    )
    replayed_final = replay.reconstruct_at_tick(live_final.tick)

    assert replayed_final == live_final
    assert replayed_final.status is SOMatchStatus.ENDED
    assert replayed_final.end_reason is live_final.end_reason
    assert thaw_json_mapping(replayed_started.payload)[
        "launch_provenance"
    ] == provenance.model_dump(mode="json")
    assert thaw_json_mapping(replayed_decision.payload)[
        "decision_source"
    ] == _ReplayHumanDecisionPilot.source.model_dump(mode="json")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("contract_kind", "contract_id"),
    [
        ("chassis", "chassis.light.scout_mk1"),
        ("weapon", "weapon.light.machine_gun"),
        ("sensor", "sensor.short_range_scanner"),
        ("gizmo", "gizmo.control.targeting_assist"),
        ("gizmo", "gizmo.cooling.emergency_condenser"),
    ],
    ids=["chassis", "weapon", "sensor", "non-safety-gizmo", "safety-gizmo"],
)
def test_replay_rejects_missing_match_started_contract_reference(
    tmp_path: Path,
    contract_kind: Literal["chassis", "sensor", "weapon", "gizmo"],
    contract_id: str,
) -> None:
    _live_state, ledger = _run_and_record(tmp_path)
    runtime = runtime_dependencies()
    catalog = _catalog_without(runtime.catalog, contract_kind, contract_id)
    replay = ReplayEngine(
        ledger,
        match_id=MATCH_ID,
        catalog=catalog,
        event_factory=runtime.event_factory,
    )

    with pytest.raises(MissingMatchContractError) as error:
        replay.reconstruct_at_tick(0)

    assert error.value.contract_kind == contract_kind
    assert error.value.contract_id == contract_id
    assert error.value.owner_id.startswith("mech.")


@pytest.mark.integration
def test_replay_rejects_missing_mode_transition_contract(tmp_path: Path) -> None:
    live_state, ledger = _run_and_record(tmp_path)
    runtime = runtime_dependencies()
    transitions = dict(runtime.catalog.transitions)
    transitions.pop((ModeId.RECON, ModeId.ASSAULT))
    catalog = MatchContractCatalog(
        arenas=dict(runtime.catalog.arenas),
        chassis=dict(runtime.catalog.chassis),
        boilers=dict(runtime.catalog.boilers),
        sensors=dict(runtime.catalog.sensors),
        weapons=dict(runtime.catalog.weapons),
        gizmos=dict(runtime.catalog.gizmos),
        transitions=transitions,
    )
    replay = ReplayEngine(
        ledger,
        match_id=MATCH_ID,
        catalog=catalog,
        event_factory=runtime.event_factory,
    )

    with pytest.raises(MissingMatchContractError) as error:
        replay.reconstruct_at_tick(live_state.tick)

    assert error.value.contract_kind == "transition"
    assert error.value.contract_id == "recon->assault"
    assert error.value.owner_id.startswith("mech.")


# ---------------------------------------------------------------------------
# reconstruct_at_tick(N).tick == N for N <= final_tick
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reconstruct_at_tick_has_correct_tick(tmp_path: Path) -> None:
    """Reconstructed state at tick N records tick == N."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)
    # Check a few intermediate ticks (match runs MAX_TICKS ticks, 0-indexed start)
    for t in range(1, live_state.tick + 1):
        state = replay.reconstruct_at_tick(t)
        assert state.tick == t, f"at tick {t}: state.tick={state.tick}"


# ---------------------------------------------------------------------------
# step_forward / step_backward round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_step_forward_then_backward_round_trips(tmp_path: Path) -> None:
    """step_forward() then step_backward() must yield the same state as
    reconstruct_at_tick(original_tick)."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)

    final_tick = live_state.tick
    # Start in the middle so both directions have room.
    mid_tick = max(1, final_tick // 2)
    state_at_mid = replay.reconstruct_at_tick(mid_tick)

    # Step stepper to mid_tick first.
    replay.reconstruct_at_tick(mid_tick)  # positions cursor at mid_tick

    # Forward then backward must return to mid_tick state.
    replay.step_forward()
    state_back = replay.step_backward()
    assert state_back.tick == mid_tick
    assert state_back == state_at_mid, (
        "step_forward+step_backward must yield the same state as reconstruct_at_tick"
    )


# ---------------------------------------------------------------------------
# all_ticks()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_all_ticks_returns_sorted_unique_list(tmp_path: Path) -> None:
    """all_ticks() returns a sorted list with no duplicates."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)
    ticks = replay.all_ticks()

    assert isinstance(ticks, list)
    assert ticks == sorted(set(ticks)), "all_ticks() must be sorted and deduplicated"
    assert ticks[0] == 0, "tick 0 (MATCH_STARTED) must be present"
    assert ticks[-1] == live_state.tick


# ---------------------------------------------------------------------------
# events_at_tick()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_events_at_tick_returns_events_in_canonical_order(tmp_path: Path) -> None:
    """events_at_tick(N) must return only events with tick==N, sorted by
    (sequence_in_tick ASC, event_id ASC)."""
    _live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)

    for tick in replay.all_ticks():
        events = replay.events_at_tick(tick)
        assert all(e.tick == tick for e in events), (
            f"events_at_tick({tick}) returned events with wrong tick numbers"
        )
        # Verify canonical ordering within the tick.
        seqs = [(e.sequence_in_tick, e.event_id) for e in events]
        assert seqs == sorted(seqs), (
            f"events_at_tick({tick}) not in canonical (sequence_in_tick, event_id) order"
        )


@pytest.mark.integration
def test_events_at_tick_returns_empty_for_nonexistent_tick(tmp_path: Path) -> None:
    """events_at_tick() for a tick not in the ledger returns an empty list."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)
    result = replay.events_at_tick(live_state.tick + 9999)
    assert result == []


# ---------------------------------------------------------------------------
# step_forward / step_backward boundary conditions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_step_forward_at_final_tick_returns_same_state(tmp_path: Path) -> None:
    """step_forward() at the last tick must return the same (final) state."""
    live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)
    replay.reconstruct_at_tick(live_state.tick)  # position at end
    at_end = replay.step_forward()
    assert at_end.status is SOMatchStatus.ENDED
    assert at_end.tick == live_state.tick  # cannot advance past end


@pytest.mark.integration
def test_step_backward_at_tick_zero_returns_same_state(tmp_path: Path) -> None:
    """step_backward() at tick 0 must not go below 0."""
    _live_state, ledger = _run_and_record(tmp_path)
    replay = _replay(ledger)
    replay.reconstruct_at_tick(0)  # position at start
    at_start = replay.step_backward()
    assert at_start.tick == 0  # cannot go below 0


# ---------------------------------------------------------------------------
# covered_advance -- the live resolver's LOS-shadow output must replay
# byte-identically (card.movement.covered_advance, SO-SEEKCOVER).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_replay_reproduces_covered_advance_movement(tmp_path: Path) -> None:
    """A live ``covered_advance`` move (LOS-shadow selection, not degrade)
    must fold to the exact same ``ModelSOMatchState`` on replay.

    Reuses the exact obstacle geometry hand-verified in
    ``tests/match/test_runner_move_intent.py`` (obstacle at (14, 9) shadows
    (13, 9); the visible plain-advance target (14, 10) is rejected). This
    proves the reducer replay-folds the resolver's *live* MOVEMENT_RESOLVED
    event without re-deriving it -- the actual invariant behind
    ``all_replay_valid`` (see that module's determinism test for the
    resolver-purity half of this guarantee).
    """
    match_id = "match.replay.covered-advance"
    ledger = open_sqlite_ledger(tmp_path / f"{match_id}.sqlite")
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(ledger.append)
    bus.subscribe(events.append)

    a_pos = ModelSOPosition(x=10, y=10)
    b_pos = ModelSOPosition(x=20, y=10)
    arena = ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="replay_covered_advance",
        display_name="Replay covered-advance test arena",
        size=40,
        spawn_a=a_pos,
        spawn_b=b_pos,
        obstacles=(ModelSOPosition(x=14, y=9),),
        rects=(),
    )
    runner, runtime = match_runner(
        bus=bus,
        match_id=match_id,
        seed=1,
        loadout_a=load_loadout(LOADOUT_A),
        loadout_b=load_loadout(LOADOUT_B),
        max_ticks=2,
        arena_override=arena,
    )
    a_payload = _mech_payload("mech.a.01", "player.a")
    a_payload["position"] = a_pos.model_dump(mode="json")
    b_payload = _mech_payload("mech.b.01", "player.b")
    b_payload["position"] = b_pos.model_dump(mode="json")
    bus.publish(
        ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=match_id,
            tick=0,
            sequence_in_tick=0,
            event_type=SOEventType.MATCH_STARTED,
            producer_node="node.test",
            subject=_MATCH_SUBJECT,
            payload={
                "seed": 1,
                "max_ticks": 2,
                "mechs": [a_payload, b_payload],
                "arena": arena.to_snapshot().model_dump(mode="json"),
            },
            envelope=_onex_envelope(match_id),
        )
    )
    mech = runner.fold.state.mech_states["mech.a.01"]
    bus.publish(
        ModelSOEventEnvelope(
            event_id=ulid.new().str,
            match_id=match_id,
            tick=1,
            sequence_in_tick=0,
            event_type=SOEventType.MOVE_INTENT,
            producer_node="node.test",
            subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
            payload={"direction": "covered_advance"},
            envelope=_onex_envelope(match_id),
        )
    )
    runner._resolve_move(events[-1], runner.fold.state, mech)

    movement = next(event for event in events if event.event_type is SOEventType.MOVEMENT_RESOLVED)
    assert movement.payload["to"] == {"x": 13, "y": 9}  # pins the LOS-shadow branch, not degrade

    live_state = runner.fold.state
    replay = ReplayEngine(
        ledger,
        match_id=match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state
    assert reconstructed.mech_states["mech.a.01"].position == ModelSOPosition(x=13, y=9)
