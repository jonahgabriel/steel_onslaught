"""Tests for the minimal synchronous match runner — Task 28."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanSeatAssignment,
    ModelSOMatchLaunchProvenance,
    ModelSOModelSeatAssignment,
)
from steel_onslaught.contracts.weapon import UnknownWeaponError
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.immutable import thaw_json_mapping
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.composition import load_loadout, load_pilot_registry
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from tests.runtime import match_runner, pilot_from_spec, runtime_dependencies
from tests.sqlite_ledger import open_sqlite_ledger

LOADOUT_A = Path("contracts_data/loadouts/example_aggressive_light.yaml")
LOADOUT_B = Path("contracts_data/loadouts/example_predictive_heavy.yaml")

MATCH_ID = "match.2026-04-30.runner-test"


def _run_match(
    *,
    seed: int = 12345,
    max_ticks: int = 8,
    ledger: SQLiteLedger | None = None,
) -> tuple[Any, list[ModelSOEventEnvelope]]:
    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    if ledger is not None:
        bus.subscribe(ledger.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=seed,
        loadout_a=load_loadout(LOADOUT_A),
        loadout_b=load_loadout(LOADOUT_B),
        max_ticks=max_ticks,
    )
    final = runner.run()
    return final, collected


@pytest.mark.integration
def test_run_terminates_at_bound_with_draw() -> None:
    final, _events = _run_match(max_ticks=8)
    assert final.status is SOMatchStatus.ENDED
    assert final.tick == 8
    # Both mechs survive the minimal stack (no damage path wired) -> draw.
    assert final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert final.winner_id is None


@pytest.mark.integration
def test_first_event_is_match_started_recording_seed() -> None:
    _, events = _run_match(seed=777, max_ticks=3)
    first = events[0]
    assert first.event_type is SOEventType.MATCH_STARTED
    assert first.tick == 0
    assert first.payload["seed"] == 777
    assert first.payload["max_ticks"] == 3
    assert len(first.payload["mechs"]) == 2


@pytest.mark.integration
def test_authorized_run_emits_exact_launch_provenance() -> None:
    match_id = "match.01JABCDE0123456789ABCDEFGX"
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
                loadout_id="loadout.example.aggressive_light",
                pilot_spec_id="pilot.template.aggressive",
                option_sha256="4" * 64,
                human_identity_id="human_identity.local_operator",
                input_source="browser_command",
            ),
            ModelSOModelSeatAssignment(
                kind="model",
                side="blue",
                player_id="player.blue",
                option_id="player_option.local_model",
                loadout_id="loadout.example.predictive_heavy",
                pilot_spec_id="pilot.template.predictive",
                option_sha256="5" * 64,
                model_identity_id="model_identity.local_model",
                persona_id="predictive",
                input_source="llm_completion",
            ),
        ),
    )
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    runtime = runtime_dependencies()
    red = load_loadout(LOADOUT_A)
    blue = load_loadout(LOADOUT_B)
    registry = load_pilot_registry(Path("contracts_data/pilots"))
    runner = MatchRunner(
        identity=MatchIdentity(
            match_id=match_id,
            correlation_id=runtime.event_factory.identities.new_correlation_id(),
        ),
        seed=777,
        loadout_a=red,
        loadout_b=blue,
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
        arena=runtime.arena,
        pilots={
            "mech.red.01": pilot_from_spec(registry.resolve(red)),
            "mech.blue.01": pilot_from_spec(registry.resolve(blue)),
        },
        max_ticks=1,
        side_a="red",
        side_b="blue",
        launch_provenance=provenance,
    )

    runner.run()

    assert events[0].event_type is SOEventType.MATCH_STARTED
    assert thaw_json_mapping(events[0].payload)["launch_provenance"] == provenance.model_dump(
        mode="json"
    )


@pytest.mark.integration
def test_match_tick_emitted_for_every_tick() -> None:
    _, events = _run_match(max_ticks=5)
    ticks = [e.tick for e in events if e.event_type is SOEventType.MATCH_TICK]
    assert ticks == [1, 2, 3, 4, 5]


@pytest.mark.integration
def test_same_seed_produces_identical_event_stream() -> None:
    _, events_one = _run_match(seed=12345, max_ticks=8)
    _, events_two = _run_match(seed=12345, max_ticks=8)

    def fingerprint(
        events: list[ModelSOEventEnvelope],
    ) -> list[tuple[int, int, SOEventType, Mapping[str, Any]]]:
        return [(e.tick, e.sequence_in_tick, e.event_type, e.payload) for e in events]

    assert fingerprint(events_one) == fingerprint(events_two)


@pytest.mark.integration
def test_pilot_decisions_emitted_per_living_mech_per_tick() -> None:
    _, events = _run_match(max_ticks=4)
    decisions = [e for e in events if e.event_type is SOEventType.PILOT_DECISION_MADE]
    # 2 living mechs x 4 ticks; the terminal tick (4) ends the match before
    # pilots are invoked, so 2 mechs x 3 ticks = 6 decisions.
    assert len(decisions) == 6
    assert {e.subject.mech_id for e in decisions} == {"mech.a.01", "mech.b.01"}


@pytest.mark.integration
def test_run_with_ledger_persists_all_events_in_canonical_order(tmp_path: Path) -> None:
    ledger = open_sqlite_ledger(tmp_path / "ledger.sqlite")
    _, collected = _run_match(max_ticks=5, ledger=ledger)

    persisted = list(ledger.read_all(MATCH_ID))
    assert len(persisted) == len(collected)
    assert [(e.tick, e.sequence_in_tick) for e in persisted] == [
        (e.tick, e.sequence_in_tick) for e in collected
    ]


@pytest.mark.unit
def test_unknown_pilot_archetype_fails_fast() -> None:
    loadout = load_loadout(LOADOUT_A)
    bad = loadout.model_copy(update={"pilot_id": "pilot.example.unknown_v1"})
    bus = InProcessEventBus()
    with pytest.raises(ValueError, match="unknown exact pilot_id"):
        match_runner(
            bus=bus,
            match_id=MATCH_ID,
            seed=1,
            loadout_a=bad,
            loadout_b=load_loadout(LOADOUT_B),
            max_ticks=3,
        )[0].run()


@pytest.mark.unit
def test_unknown_loadout_weapon_fails_with_typed_deterministic_error() -> None:
    loadout = load_loadout(LOADOUT_A)
    unknown_id = "weapon.light.absent"
    bad = loadout.model_copy(
        update={
            "modules": loadout.modules.model_copy(update={"weapons": [unknown_id]}),
        }
    )
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=1,
        loadout_a=bad,
        loadout_b=load_loadout(LOADOUT_B),
        max_ticks=3,
    )

    with pytest.raises(UnknownWeaponError) as raised:
        runner.run()

    assert raised.value.weapon_id == unknown_id
    assert raised.value.owner_id == loadout.id
    assert str(raised.value) == (
        f"unknown_weapon_id: weapon {unknown_id!r} referenced by {loadout.id!r} "
        "is absent from the injected weapon catalog"
    )
