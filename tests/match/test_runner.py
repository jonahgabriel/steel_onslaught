"""Tests for the minimal synchronous match runner — Task 28."""

from __future__ import annotations

import json
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
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.pilot import LLMPilot
from steel_onslaught.llm.schemas import LlmResponse, LlmUsage, ModelSOLlmCompletionRequest
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
    defense_handler_ids: tuple[str, ...] | None = None,
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
        defense_handler_ids=defense_handler_ids,
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
def test_match_started_records_default_defense_handler_pack_provenance() -> None:
    """Defense resolution is never off: every new match names its active pack."""
    _, events = _run_match(max_ticks=1)
    payload = events[0].payload
    provenance = payload["defense_handler_pack_provenance"]
    assert provenance["pack_id"] == "defense.resolution.v1"
    assert [h["handler_id"] for h in provenance["handlers"]] == ["defense.armor.v1"]
    assert len(provenance["content_sha256"]) == 64


@pytest.mark.integration
def test_explicit_defense_handler_ids_selection_matches_default() -> None:
    """Explicitly selecting the default handler id is byte-identical to omitting it."""
    _, default_events = _run_match(seed=42, max_ticks=5)
    _, explicit_events = _run_match(seed=42, max_ticks=5, defense_handler_ids=("defense.armor.v1",))
    default_provenance = default_events[0].payload["defense_handler_pack_provenance"]
    explicit_provenance = explicit_events[0].payload["defense_handler_pack_provenance"]
    assert default_provenance == explicit_provenance


@pytest.mark.integration
def test_unknown_defense_handler_id_fails_closed_at_construction() -> None:
    from steel_onslaught.reducers.defense_handlers import DefenseHandlerSelectionError

    with pytest.raises(DefenseHandlerSelectionError, match="not registered"):
        _run_match(max_ticks=1, defense_handler_ids=("defense.shield.v1",))


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


class _AlwaysInvalidWeaponClient:
    """Always answers a well-formed ``fire_weapon`` action naming an unknown
    weapon id -- the hermetic repro of the OMN-15239 live-battery defect
    (``invalid_action_parameters`` on every attempt, never ``malformed_json``).
    """

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.calls += 1
        return LlmResponse(
            text=json.dumps(
                {
                    "action": "fire_weapon",
                    "action_params": {"weapon_id": "weapon.unknown"},
                    "confidence": 0.9,
                    "rationale": "invalid weapon",
                }
            ),
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="fixture",
            finish_reason="stop",
        )


@pytest.mark.integration
def test_plain_decide_semantic_exhaustion_reaches_provider_semantic_failure_terminal() -> None:
    """OMN-15239: the plain (non-card) per-tick ``decide()`` path must reach the
    same graceful ``provider_semantic_failure`` terminal card mode already has
    for a persistent semantic failure -- not an uncaught crash that kills the
    whole match (and, in the live battery, the whole seed: 20/30 default-corner
    skips).

    Before the fix, ``LLMPilot.decide()`` under the ``raise`` failure policy
    (the live-match default; see ``build_llm_dependencies``) raised the bare
    ``LlmSemanticError`` on the FIRST semantic rejection with no retry. That
    exception is not one of the two types the tick loop's ``except`` clauses
    catch (``LlmCompletionBoundaryError``/``LlmSemanticExhaustedError``), so it
    propagated straight out of ``runner.run()`` uncaught.
    """

    client = _AlwaysInvalidWeaponClient()
    persona = Persona(
        persona_id="fixture",
        display_name="Fixture",
        system_prompt="Return a valid pilot action as JSON.",
        temperature=0.5,
    )
    llm_pilot = LLMPilot(client=client, persona=persona, failure_policy="raise")

    registry = load_pilot_registry(Path("contracts_data/pilots"))
    loadout_a = load_loadout(LOADOUT_A)
    loadout_b = load_loadout(LOADOUT_B)
    pilots = {
        "mech.a.01": llm_pilot,
        "mech.b.01": pilot_from_spec(registry.resolve(loadout_b)),
    }

    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=1,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        max_ticks=8,
        pilots_override=pilots,
    )

    final = runner.run()

    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason is SOMatchEndReason.PROVIDER_SEMANTIC_FAILURE
    # Terminated by the semantic-exhaustion path, not by hitting max_ticks.
    assert final.tick < 8

    ended = [e for e in collected if e.event_type is SOEventType.MATCH_ENDED]
    assert ended
    assert ended[-1].payload["reason"] == "provider_semantic_failure"
    assert ended[-1].payload["winner_id"] is None
    # Bounded retry actually happened: more than one real provider call before
    # the terminal, each with its own durable evidence.
    assert client.calls > 1


@pytest.mark.integration
def test_plain_decide_transient_semantic_failure_recovers_and_match_keeps_playing() -> None:
    """OMN-15239 happy-retry end to end: one invalid action, then the match
    plays on to its ordinary terminal instead of aborting."""

    class _InvalidThenRemainClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
            self.calls += 1
            if self.calls == 1:
                text = json.dumps(
                    {
                        "action": "fire_weapon",
                        "action_params": {"weapon_id": "weapon.unknown"},
                        "confidence": 0.9,
                        "rationale": "invalid weapon",
                    }
                )
            else:
                text = json.dumps(
                    {
                        "action": "remain",
                        "action_params": {},
                        "confidence": 0.7,
                        "rationale": "recovered",
                    }
                )
            return LlmResponse(
                text=text,
                usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
                model="fixture",
                finish_reason="stop",
            )

    client = _InvalidThenRemainClient()
    persona = Persona(
        persona_id="fixture",
        display_name="Fixture",
        system_prompt="Return a valid pilot action as JSON.",
        temperature=0.5,
    )
    llm_pilot = LLMPilot(client=client, persona=persona, failure_policy="raise")

    registry = load_pilot_registry(Path("contracts_data/pilots"))
    loadout_a = load_loadout(LOADOUT_A)
    loadout_b = load_loadout(LOADOUT_B)
    pilots = {
        "mech.a.01": llm_pilot,
        "mech.b.01": pilot_from_spec(registry.resolve(loadout_b)),
    }

    bus = InProcessEventBus()
    collected: list[ModelSOEventEnvelope] = []
    bus.subscribe(collected.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id=MATCH_ID,
        seed=1,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        max_ticks=4,
        pilots_override=pilots,
    )

    final = runner.run()

    assert final.status is SOMatchStatus.ENDED
    # The match ends on its own terms (max_ticks draw), never on the
    # provider-failure terminal.
    assert final.end_reason is not SOMatchEndReason.PROVIDER_SEMANTIC_FAILURE
    assert final.tick == 4
    assert client.calls >= 2

    decisions = [e for e in collected if e.event_type is SOEventType.PILOT_DECISION_MADE]
    mech_a_decisions = [e for e in decisions if e.subject.mech_id == "mech.a.01"]
    assert len(mech_a_decisions) == 3
    assert mech_a_decisions[0].payload["reason_code"] == "llm_decision"
