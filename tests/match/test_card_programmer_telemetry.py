"""Match-scoped telemetry for explicitly bound card programmers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.application import ModelSOCardProgrammerBinding
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.pilot import (
    ModelSOLlmPilotParams,
    ModelSOPilotLineage,
    ModelSOPilotSpec,
)
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.llm.personas import Persona, PersonaRegistry
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ProtocolLlmClient,
    ProtocolLlmClientFactory,
)
from steel_onslaught.match.composition import (
    ApplicationPilotFactory,
    CardProgrammerFactory,
    LlmDependencies,
    RuntimeDependencies,
    assemble_match_with_dependencies,
    build_card_programmers,
    build_card_runner_adapter,
    load_card_catalog,
    load_loadout,
    load_match_contract_catalog,
    load_pilot_registry,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.state import SOMatchStatus
from steel_onslaught.projections.leaderboard.protocol import (
    LeaderboardRepository,
    ModelSOLeaderboardEntry,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import FixedClock, SequentialIdentities, pilot_from_spec

pytestmark = pytest.mark.integration

_ROOT = Path("contracts_data")
_RED_LOADOUT = _ROOT / "loadouts/example_aggressive_light.yaml"
_BLUE_LOADOUT = _ROOT / "loadouts/example_predictive_heavy.yaml"


class _Ledger:
    def __init__(self) -> None:
        self.events: list[ModelSOEventEnvelope] = []

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return iter(event for event in self.events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return iter(
            event for event in self.events if event.match_id == match_id and event.tick > after_tick
        )

    def read_match_ids(self) -> Iterator[str]:
        return iter(sorted({event.match_id for event in self.events}))

    def contains_match(self, match_id: str) -> bool:
        return any(event.match_id == match_id for event in self.events)

    def read_at(
        self,
        match_id: str,
        tick: int,
        *,
        event_types: frozenset[SOEventType] | None,
    ) -> Iterator[ModelSOEventEnvelope]:
        return iter(
            event
            for event in self.events
            if event.match_id == match_id
            and event.tick == tick
            and (event_types is None or event.event_type in event_types)
        )


class _Leaderboard(LeaderboardRepository):
    def on_match_scored(self, payload: Any) -> None:
        del payload

    def top_n(self, n: int) -> list[ModelSOLeaderboardEntry]:
        del n
        return []

    def player_record(self, player_id: str) -> dict[str, int]:
        del player_id
        return {"wins": 0, "losses": 0, "draws": 0}

    def draw_count(self) -> int:
        return 0


class _Closer:
    def close(self) -> None:
        return


class _CardProgrammingClient:
    """Return a valid whole-round plan from the canonical prompt hand."""

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        prompt = json.loads(request.user_prompt)
        hand = prompt["hand"]
        free_indices = prompt["registers"]["free_indices"]
        registers = [
            {"register_index": index, "card_id": card["card_id"]}
            for index, card in zip(free_indices, hand, strict=True)
        ]
        return LlmResponse(
            text=json.dumps({"registers": registers, "confidence": 0.9, "rationale": "fixture"}),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=3, cost_usd=0.0),
            model="card-programmer-fixture",
            finish_reason="stop",
        )


class _LengthProgrammingClient:
    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        return LlmResponse(
            text='{"registers":[]}',
            usage=LlmUsage(prompt_tokens=5, completion_tokens=3, cost_usd=None),
            model="card-programmer-fixture",
            finish_reason="length",
        )


class _TimeoutProgrammingClient:
    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        raise LlmCompletionBoundaryError("timeout", retryable=True)


class _InvalidActionProgrammingClient:
    """Always answer with a well-formed plan naming a card absent from the hand.

    This is the live stall reproduced hermetically: the completion parses
    against the closed response model (so it is not ``malformed_json``) but the
    canonical plan validator rejects it as ``invalid_action_parameters`` on
    every attempt — exactly the Qwen failure that froze the match at tick 31.
    """

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.calls += 1
        prompt = json.loads(request.user_prompt)
        free_indices = prompt["registers"]["free_indices"]
        registers = [
            {"register_index": index, "card_id": "card.telemetry.not_in_hand"}
            for index in free_indices
        ]
        return LlmResponse(
            text=json.dumps(
                {"registers": registers, "confidence": 0.5, "rationale": "invalid plan"}
            ),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=176, cost_usd=0.0),
            model="Qwen3.6-35B-A3B",
            finish_reason="stop",
        )


class _InvalidThenValidProgrammingClient:
    """Reject exactly the first plan, then play validly forever after.

    Proves the happy-retry path: a single semantic slip is self-corrected on
    the same model and the match keeps advancing rather than aborting.
    """

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.calls += 1
        prompt = json.loads(request.user_prompt)
        free_indices = prompt["registers"]["free_indices"]
        hand = prompt["hand"]
        if self.calls == 1:
            registers = [
                {"register_index": index, "card_id": "card.telemetry.not_in_hand"}
                for index in free_indices
            ]
            rationale = "invalid plan"
        else:
            registers = [
                {"register_index": index, "card_id": card["card_id"]}
                for index, card in zip(free_indices, hand, strict=True)
            ]
            rationale = "valid recovery"
        return LlmResponse(
            text=json.dumps({"registers": registers, "confidence": 0.7, "rationale": rationale}),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=6, cost_usd=0.0),
            model="Qwen3.6-35B-A3B",
            finish_reason="stop",
        )


class _Clients(ProtocolLlmClientFactory):
    def __init__(self, client: ProtocolLlmClient) -> None:
        self.client = client

    def client_for(self, provider_id: str) -> ProtocolLlmClient:
        if provider_id != "provider.card.fixture":
            raise ValueError(f"unexpected provider {provider_id!r}")
        return self.client


def _llm_dependencies(client: ProtocolLlmClient) -> LlmDependencies:
    personas = PersonaRegistry(
        {
            "sniper": Persona("sniper", "Sniper", "sniper", 0.2),
            "berserker": Persona("berserker", "Berserker", "berserker", 0.6),
        }
    )
    clients = _Clients(client)
    return LlmDependencies(
        client_factory=clients,
        persona_registry=personas,
        pilot_factory=ApplicationPilotFactory(clients=clients, personas=personas),
        tuner_generator=cast(Any, object()),
        closer=_Closer(),
    )


def _card_snapshot() -> ModelSOCardRuntimeSnapshot:
    binding = type(
        "CardBinding",
        (),
        {
            "cards_dir": (_ROOT / "cards").resolve(),
            "decks_dir": (_ROOT / "cards").resolve(),
            "deck_id": None,
            "card_mode_enabled": False,
        },
    )()
    catalog = load_card_catalog(binding)
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.telemetry.fixture",
        display_name="Telemetry fixture",
        hand_size=2,
        register_count=2,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in catalog.cards[:4]),
    )
    from steel_onslaught.contracts.card_runtime import canonical_card_runtime_sha256

    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=catalog,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(catalog, (deck,)),
    )


def _pilot_spec(
    *,
    spec_id: str = "pilot.card.telemetry",
    persona: str = "sniper",
) -> ModelSOPilotSpec:
    """Build one telemetry card-programmer spec.

    Two seats need two specs: ``build_card_programmers`` fails closed when
    both live seats resolve to the same (provider, persona) identity, because
    that is a mirror match rather than a contest.  The telemetry fixture
    therefore differentiates the seats by persona.
    """

    return ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id=spec_id,
        display_name="Card telemetry fixture",
        archetype="llm",
        lineage=ModelSOPilotLineage(parent=None),
        parameters=ModelSOLlmPilotParams(
            provider="provider.card.fixture",
            persona=persona,
        ),
    )


def _blue_pilot_spec() -> ModelSOPilotSpec:
    return _pilot_spec(spec_id="pilot.card.telemetry_blue", persona="berserker")


def _compose(
    *,
    cadence: str,
    client: ProtocolLlmClient | None = None,
) -> tuple[RuntimeDependencies, Any, _Ledger, ModelSOCardRuntimeSnapshot]:
    runtime_root = load_match_contract_catalog(_ROOT)
    full_registry = load_pilot_registry(_ROOT / "pilots")
    full_registry = PilotSpecRegistry(
        {
            **full_registry.as_mapping(),
            _pilot_spec().id: _pilot_spec(),
            _blue_pilot_spec().id: _blue_pilot_spec(),
        }
    )
    snapshot = _card_snapshot()
    llm = _llm_dependencies(client or _CardProgrammingClient())
    bindings = (
        ModelSOCardProgrammerBinding(side="red", pilot_spec_id="pilot.card.telemetry"),
        ModelSOCardProgrammerBinding(side="blue", pilot_spec_id="pilot.card.telemetry_blue"),
    )
    factory = CardProgrammerFactory(bindings=bindings, registry=full_registry, llm=llm)
    raw_programmers = build_card_programmers(bindings, registry=full_registry, llm=llm)
    adapter = build_card_runner_adapter(snapshot=snapshot, programmers=raw_programmers)
    identities = SequentialIdentities()
    event_factory = EventFactory(clock=FixedClock(), identities=identities)
    bus = InProcessEventBus()
    ledger = _Ledger()
    dependencies = RuntimeDependencies(
        bus=bus,
        ledger=ledger,
        leaderboard=_Leaderboard(),
        clock=FixedClock(),
        identities=identities,
        event_factory=event_factory,
        catalog=runtime_root,
        arena=runtime_root.arenas["open_field"],
        pilot_registry=full_registry,
        pilot_factory=cast(Any, object()),
        closer=_Closer(),
        card_catalog=snapshot.card_catalog,
        card_runtime_snapshot=snapshot,
        card_adapter=adapter,
        card_programmers=raw_programmers,
        card_programmer_factory=factory,
        card_cadence=cast(Any, cadence),
    )
    red = load_loadout(_RED_LOADOUT)
    blue = load_loadout(_BLUE_LOADOUT)
    pilots = {
        "mech.red.01": pilot_from_spec(full_registry.resolve(red)),
        "mech.blue.01": pilot_from_spec(full_registry.resolve(blue)),
    }
    identity = MatchIdentity(
        match_id=f"match.telemetry.{cadence}",
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
    )
    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=red,
        blue=blue,
        seed=17,
        max_ticks=5 if cadence == "paced" else 3,
        identity=identity,
        pilots_override=pilots,
    )
    return dependencies, stack, ledger, snapshot


@pytest.mark.parametrize("cadence", ["atomic", "paced"])
def test_card_programmer_telemetry_is_match_scoped_and_replayable(cadence: str) -> None:
    dependencies, stack, ledger, snapshot = _compose(cadence=cadence)
    assert dependencies.card_adapter is not None
    assert stack.card_adapter is not dependencies.card_adapter
    assert dependencies.card_programmers is not None
    assert stack.card_adapter is not None and stack.card_adapter.programmers is not None
    assert stack.card_adapter.programmers["red"] is not dependencies.card_programmers["red"]
    match_red = cast(Any, stack.card_adapter.programmers["red"])
    shared_red = cast(Any, dependencies.card_programmers["red"])
    assert match_red._client.__class__.__name__ == "ObservedLlmClient"
    assert shared_red._client.__class__.__name__ == "_CardProgrammingClient"

    final = stack.runner.run()
    assert final.status.value == "ended"
    events = ledger.events
    requests = [
        event for event in events if event.event_type is SOEventType.LLM_COMPLETION_REQUESTED
    ]
    terminals = {
        SOEventType.LLM_COMPLETION_RESOLVED,
        SOEventType.LLM_COMPLETION_FAILED,
    }
    assert requests
    for request in requests:
        outcomes = [
            event
            for event in events
            if event.event_type in terminals
            and event.envelope.causation_id == request.envelope.message_id
        ]
        assert len(outcomes) == 1
        assert outcomes[0].correlation_id == request.correlation_id
        assert outcomes[0].payload["provider_id"] == "provider.card.fixture"
    assert len(requests) == sum(event.event_type in terminals for event in events)

    replay = ReplayEngine(
        ledger,
        stack.match_id,
        catalog=dependencies.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=snapshot,
        validate_card_events=True,
    )
    assert replay.reconstruct_at_tick(final.tick) == final


def test_paced_max_tick_closes_active_round_before_scoring() -> None:
    """A max-tick terminal must discard an in-flight paced round first."""

    _dependencies, stack, ledger, _snapshot = _compose(cadence="paced")
    # The normal fixture runs long enough to finish each two-register round.
    # Force the lifecycle boundary while register one of the first round is
    # still latched, matching the live split-deck overlay's five-register
    # cadence.
    stack.runner._max_ticks = 2

    final = stack.runner.run()

    assert final.status is SOMatchStatus.ENDED
    discarded = [
        event for event in ledger.events if event.event_type is SOEventType.CARDS_DISCARDED
    ]
    assert discarded
    assert discarded[-1].payload["reason"] == "cancelled:max_ticks"
    assert any(event.event_type is SOEventType.MATCH_SCORED for event in ledger.events)


@pytest.mark.parametrize(
    ("client", "reason_code"),
    [
        (_LengthProgrammingClient(), "length"),
        (_TimeoutProgrammingClient(), "timeout"),
    ],
)
def test_provider_boundary_ends_match_before_hand_dealt(
    client: ProtocolLlmClient,
    reason_code: str,
) -> None:
    _dependencies, stack, ledger, _snapshot = _compose(cadence="atomic", client=client)

    final = stack.runner.run()

    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason.value == "aborted"
    event_types = [event.event_type for event in ledger.events]
    assert SOEventType.MATCH_STARTED in event_types
    assert SOEventType.MATCH_ENDED in event_types
    failed = [
        event for event in ledger.events if event.event_type is SOEventType.LLM_COMPLETION_FAILED
    ]
    assert len(failed) == 1
    assert failed[0].payload["reason_code"] == reason_code
    assert SOEventType.HAND_DEALT not in event_types
    assert event_types.index(SOEventType.LLM_COMPLETION_FAILED) < event_types.index(
        SOEventType.MATCH_ENDED
    )


@pytest.mark.parametrize("cadence", ["atomic", "paced"])
def test_semantic_failure_reaches_a_classified_terminal_not_a_stall(cadence: str) -> None:
    """The live stall fix: a persistently invalid plan ENDS the match cleanly.

    Before the fix a ``LlmSemanticError`` propagated past the boundary-only
    handler and the match froze with no terminal (observed live: pinned at
    tick 31, 344 events, no ``match_ended``). Now the pilot reprompts the same
    model within a bounded budget and, on exhaustion, the runner records a
    DISTINCT ``provider_semantic_failure`` terminal. The per-attempt failure
    evidence (provider, model, semantic code) is durable in the ledger.
    """

    client = _InvalidActionProgrammingClient()
    dependencies, stack, ledger, snapshot = _compose(cadence=cadence, client=client)

    final = stack.runner.run()

    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason is not None
    assert final.end_reason.value == "provider_semantic_failure"

    event_types = [event.event_type for event in ledger.events]
    assert SOEventType.MATCH_STARTED in event_types
    assert SOEventType.MATCH_ENDED in event_types

    ended = [event for event in ledger.events if event.event_type is SOEventType.MATCH_ENDED]
    assert len(ended) == 1
    assert ended[0].payload["reason"] == "provider_semantic_failure"
    assert ended[0].payload["winner_id"] is None

    # Bounded retry: four same-model attempts (one initial + three reprompts,
    # the balance-round-2 default) for the first-programmed seat, each producing
    # durable failed evidence, before the match terminates. This is the
    # "retries then terminate" proof — the loop stays bounded (never a stall).
    failed = [
        event for event in ledger.events if event.event_type is SOEventType.LLM_COMPLETION_FAILED
    ]
    assert client.calls == 4
    assert len(failed) == 4
    for event in failed:
        assert event.payload["reason_code"] == "invalid_response"
        assert event.payload["semantic_failure_code"] == "invalid_action_parameters"
        assert event.payload["provider_id"] == "provider.card.fixture"
        assert event.payload["model"] == "Qwen3.6-35B-A3B"

    # The classified terminal follows the exhausted attempts; no partial round
    # was committed (the plan never validated, so nothing was dealt).
    assert event_types.index(SOEventType.LLM_COMPLETION_FAILED) < event_types.index(
        SOEventType.MATCH_ENDED
    )
    assert SOEventType.HAND_DEALT not in event_types

    # replay == live: the semantic-failure terminal folds back deterministically
    # from the recorded ledger (the LLM is never re-invoked on replay).
    replay = ReplayEngine(
        ledger,
        stack.match_id,
        catalog=dependencies.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=snapshot,
        validate_card_events=True,
    )
    reconstructed = replay.reconstruct_at_tick(final.tick)
    assert reconstructed == final
    assert reconstructed.end_reason is not None
    assert reconstructed.end_reason.value == "provider_semantic_failure"


def test_semantic_retry_recovers_and_the_match_keeps_playing() -> None:
    """Happy-retry end to end: one invalid plan, then the match plays on.

    A single semantic slip is self-corrected on the same model — the match
    deals hands, commits plans, resolves registers, and reaches an ordinary
    (non-provider-failure) terminal instead of aborting.
    """

    client = _InvalidThenValidProgrammingClient()
    _dependencies, stack, ledger, _snapshot = _compose(cadence="atomic", client=client)

    final = stack.runner.run()

    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason is not None
    # The match ends on its own terms, never on the provider-failure terminal.
    assert final.end_reason.value != "provider_semantic_failure"

    event_types = [event.event_type for event in ledger.events]
    # The recovered round actually happened: cards were dealt and resolved.
    assert SOEventType.HAND_DEALT in event_types
    assert SOEventType.PLAN_COMMITTED in event_types
    assert SOEventType.REGISTER_RESOLVED in event_types

    failed = [
        event for event in ledger.events if event.event_type is SOEventType.LLM_COMPLETION_FAILED
    ]
    resolved = [
        event for event in ledger.events if event.event_type is SOEventType.LLM_COMPLETION_RESOLVED
    ]
    # Exactly one rejected attempt was recovered; the rest resolved cleanly.
    assert len(failed) == 1
    assert failed[0].payload["semantic_failure_code"] == "invalid_action_parameters"
    assert resolved
