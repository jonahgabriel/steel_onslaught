"""L-GATE-2 cross-boundary chain: a promotion changes the NEXT match, auditably.

One test drives the full seam chain through the real composition surfaces:

    admission (``begin_match`` inside ``assemble_match_with_dependencies``)
    -> live card-mode match on the real bus/ledger
    -> terminal ``MATCH_SCORED`` -> ``AfterMatchLearningHandler`` -> promotion
    -> ``POLICY_PROMOTED`` appended + lineage persisted
    -> NEXT match admission snapshots the promoted policy
    -> its ``MATCH_STARTED`` policy provenance cites the new ``policy_id``
    -> its programming prompt (the byte-exact system prompt the provider
       receives) carries the new policy-guidance block.

The live judgment here is a scripted always-promote evaluator — the design's
sanctioned stage-1 double (2026-07-22 §4.4): the chain under test is the SEAM,
not the judgment (``SelectionOutcomeEvaluator`` has its own suite).  The LLM
provider is a deterministic capturing client so the test can assert on the
exact system prompt that crossed the wire; every other surface (bus, ledger,
coordinator, artifact store, card runtime, replay validation at scoring) is
the production object graph.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.lineage import (
    ModelSOLineageEvidence,
    ModelSOLineageGenerator,
    ModelSOLineagePerformance,
    ModelSOLineagePromotion,
    ModelSOLineageRecord,
    SOPromotionStatus,
    meta_hash,
    spec_hash,
)
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.contracts.pilot import (
    ModelSOLlmPilotParams,
    ModelSOPilotLineage,
    ModelSOPilotSpec,
)
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOPolicyPromotedPayload,
)
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.llm.personas import Persona, PersonaRegistry
from steel_onslaught.llm.policy_guidance import render_policy_guidance
from steel_onslaught.llm.programming import (
    _PROGRAMMING_INSTRUCTIONS,
    LLMProgrammingPilot,
    programming_system_prompt,
)
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ProtocolLlmClient,
    ProtocolLlmClientFactory,
)
from steel_onslaught.match.composition import (
    CardProgrammerFactory,
    LiveMatchStack,
    LlmDependencies,
    RuntimeDependencies,
    assemble_match_with_dependencies,
    build_card_runner_adapter,
    build_runtime_dependencies,
    load_card_catalog,
    load_loadout,
)
from steel_onslaught.match.runner import MatchIdentity
from tests.overlay import complete_test_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RED = _REPO_ROOT / "contracts_data/loadouts/proof_red_predictive_ironclad.yaml"
_BLUE = _REPO_ROOT / "contracts_data/loadouts/proof_blue_aggressive_hunter.yaml"
_ARCHETYPE = "aggressive"
_GENESIS_PARAMETERS = {"aggression": 1.0}
_LEARNING_PLAYER = "player.red"
_PERSONA = Persona("persona.fixture", "Fixture", "You are a fixture pilot.", 0.2)


def _overlay(tmp_path: Path, *, live_learning: bool) -> ModelSOApplicationOverlay:
    raw: dict[str, Any] = {
        "schema_version": "1",
        "bus": {"kind": "in_process"},
        "event_ledger": {
            "kind": "sqlite",
            "path": tmp_path / "events.sqlite",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
        },
        "leaderboard": {
            "kind": "sqlite",
            "path": tmp_path / "leaderboard.sqlite",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "storage_schema": "leaderboard_v1",
        },
        "learning_artifacts": {
            "kind": "filesystem_yaml",
            "evaluation_root": tmp_path / "evaluations",
            "lineage_root": tmp_path / "lineage",
        },
        "evaluation_storage": {
            "kind": "sqlite",
            "root": tmp_path / "evaluations",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
            "leaderboard_schema": "leaderboard_v1",
        },
        "contracts": {
            "catalog_dir": _REPO_ROOT / "contracts_data",
            "pilot_registry_dir": _REPO_ROOT / "contracts_data/pilots",
        },
        "clock": {"kind": "system_utc"},
        "identity": {"kind": "system"},
    }
    if live_learning:
        raw["live_learning"] = {
            "kind": "win_damage_differential_v1",
            "archetype": _ARCHETYPE,
            "learning_player_id": _LEARNING_PLAYER,
            "genesis_parameters": dict(_GENESIS_PARAMETERS),
            "parameter": "aggression",
            "step": 0.25,
            "max_value": 3.0,
        }
    return ModelSOApplicationOverlay.model_validate(complete_test_overlay(raw, tmp_path))


def _card_snapshot() -> ModelSOCardRuntimeSnapshot:
    catalog = load_card_catalog(
        type(
            "CardBinding",
            (),
            {
                "cards_dir": (_REPO_ROOT / "contracts_data/cards").resolve(),
                "decks_dir": (_REPO_ROOT / "contracts_data/cards").resolve(),
                "deck_id": None,
                "card_mode_enabled": False,
            },
        )()
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.lgate2",
        display_name="L-GATE-2 chain deck",
        hand_size=2,
        register_count=2,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in catalog.cards[:4]),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=catalog,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(catalog, (deck,)),
    )


class _CapturingProgrammingClient(ProtocolLlmClient):
    """Deterministic legal-plan provider that records every request it saw."""

    def __init__(self) -> None:
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        prompt = json.loads(request.user_prompt)
        available: list[str] = []
        for entry in prompt["legal_hand"]:
            available.extend([entry["card_id"]] * entry["available_copies"])
        registers = [
            {"register_index": index, "card_id": available[position]}
            for position, index in enumerate(sorted(prompt["registers"]["free_indices"]))
        ]
        return LlmResponse(
            text=json.dumps(
                {
                    "registers": registers,
                    "confidence": 0.5,
                    "rationale": "fill free registers in order",
                }
            ),
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="capturing-fixture",
            finish_reason="stop",
        )


class _Clients(ProtocolLlmClientFactory):
    def __init__(self, client: ProtocolLlmClient) -> None:
        self._client = client

    def client_for(self, provider_id: str) -> ProtocolLlmClient:
        if provider_id != "provider.fixture":
            raise ValueError(f"unexpected provider {provider_id!r}")
        return self._client


class _ObservedPilot:
    def __init__(self, client: ProtocolLlmClient) -> None:
        self.client = client


class _PilotFactory:
    """Minimal factory seam: observation wrapping is orthogonal to L-GATE-2."""

    def __init__(self, client: ProtocolLlmClient) -> None:
        self._client = client

    def with_observer(self, _observer: object) -> _PilotFactory:
        return self

    def llm_pilot(self, _selection: object) -> _ObservedPilot:
        return _ObservedPilot(self._client)


class _Closer:
    def close(self) -> None:
        return


def _programmer_factory(client: ProtocolLlmClient) -> CardProgrammerFactory:
    from steel_onslaught.contracts.application import ModelSOCardProgrammerBinding

    spec = ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id="pilot.llm.fixture",
        display_name="Fixture LLM",
        archetype="llm",
        lineage=ModelSOPilotLineage(parent=None),
        parameters=ModelSOLlmPilotParams(persona=_PERSONA.persona_id, provider="provider.fixture"),
    )
    llm = LlmDependencies(
        client_factory=_Clients(client),
        persona_registry=PersonaRegistry({_PERSONA.persona_id: _PERSONA}),
        pilot_factory=cast(Any, _PilotFactory(client)),
        tuner_generator=cast(Any, object()),
        closer=_Closer(),
    )
    return CardProgrammerFactory(
        bindings=(ModelSOCardProgrammerBinding(side="red", pilot_spec_id="pilot.llm.fixture"),),
        registry=PilotSpecRegistry({"pilot.llm.fixture": spec}),
        llm=llm,
    )


@dataclass
class _ScriptedPromoteEvaluator:
    """Design §4.4 stage-1 double: promotion on demand, judgment out of scope."""

    step: float = 0.25
    seen: list[str] = field(default_factory=list)

    def evaluate(
        self,
        *,
        evidence: ModelSOAfterMatchLearningEvidence,
        policy: ModelSOLiveLearningPolicy,
    ) -> ModelSOLineageRecord | None:
        self.seen.append(evidence.match_id)
        current = policy.parameters["aggression"]
        assert isinstance(current, int | float) and not isinstance(current, bool)
        candidate_parameters = {
            **dict(policy.parameters),
            "aggression": round(float(current) + self.step, 6),
        }
        return ModelSOLineageRecord(
            archetype=policy.archetype,
            parameters=candidate_parameters,
            spec_hash=spec_hash(policy.archetype, candidate_parameters),
            parent_hash=policy.spec_hash,
            meta_hash=meta_hash([f"scripted:{evidence.match_id}"]),
            evidence=ModelSOLineageEvidence(search_seeds=(1,), holdout_seeds=(2,)),
            performance=ModelSOLineagePerformance(
                candidate_win_rate=1.0,
                win_rate_delta=0.5,
                overload_rate_delta=0.0,
                draw_rate=0.0,
                p_value=1.0,
                decisive_n=1,
            ),
            generator=ModelSOLineageGenerator(
                generator_id="test.scripted_promote.v1",
                selection_reason=f"scripted promotion after {evidence.match_id}",
            ),
            promotion=ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED),
        )


def _card_dependencies(
    dependencies: RuntimeDependencies, client: ProtocolLlmClient
) -> RuntimeDependencies:
    snapshot = _card_snapshot()
    return replace(
        dependencies,
        card_catalog=snapshot.card_catalog,
        card_runtime_snapshot=snapshot,
        card_adapter=build_card_runner_adapter(snapshot=snapshot),
        card_programmer_factory=_programmer_factory(client),
        # Paced is the production cadence (the live overlays use it) and the
        # only one that closes an in-flight round with a terminal discard when
        # the match ends on the tick cap — atomic leaves the final round
        # incomplete and card-round replay validation rightly rejects it.
        card_cadence="paced",
    )


def _run_card_match(dependencies: RuntimeDependencies, *, seed: int) -> tuple[LiveMatchStack, str]:
    identity = MatchIdentity(
        match_id=dependencies.identities.new_match_id(),
        correlation_id=dependencies.identities.new_correlation_id(),
    )
    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=load_loadout(_RED),
        blue=load_loadout(_BLUE),
        red_loadout_path=_RED,
        blue_loadout_path=_BLUE,
        seed=seed,
        max_ticks=40,
        identity=identity,
    )
    try:
        stack.runner.run()
    finally:
        stack.close()
    return stack, identity.match_id


def _started_payload(
    dependencies: RuntimeDependencies, match_id: str
) -> ModelSOMatchStartedPayload:
    started = next(
        event
        for event in dependencies.ledger.read_all(match_id)
        if event.event_type is SOEventType.MATCH_STARTED
    )
    return ModelSOMatchStartedPayload.model_validate(started.payload)


def _scored_payload(dependencies: RuntimeDependencies, match_id: str) -> ModelSOMatchScoredPayload:
    scored = next(
        event
        for event in dependencies.ledger.read_all(match_id)
        if event.event_type is SOEventType.MATCH_SCORED
    )
    return ModelSOMatchScoredPayload.model_validate(scored.payload)


@pytest.mark.integration
def test_promotion_changes_the_next_matchs_provenance_and_prompt(tmp_path: Path) -> None:
    overlay = _overlay(tmp_path, live_learning=True)
    dependencies = build_runtime_dependencies(overlay)
    coordinator = dependencies.live_learning
    assert coordinator is not None
    assert coordinator.learning_player_id == _LEARNING_PLAYER
    genesis_policy = coordinator.current_policy
    scripted = _ScriptedPromoteEvaluator()
    coordinator.evaluator = scripted

    # ---- Match 1: flies the genesis policy and promotes at its terminal ----
    client_one = _CapturingProgrammingClient()
    _stack_one, match_one = _run_card_match(
        _card_dependencies(dependencies, client_one), seed=12345
    )
    assert scripted.seen == [match_one]

    started_one = _started_payload(dependencies, match_one)
    assert started_one.policy_provenance is not None
    (seat_one,) = started_one.policy_provenance
    assert seat_one.player_id == _LEARNING_PLAYER
    assert seat_one.policy_id == genesis_policy.policy_id
    assert seat_one.generation == 0
    assert seat_one.source_lineage_digest is None

    genesis_guidance = render_policy_guidance(genesis_policy)
    assert client_one.requests, "the learning seat must have programmed via the provider"
    for request in client_one.requests:
        assert request.system_prompt.endswith(genesis_guidance)
    assert '"aggression":1.0' in genesis_guidance

    promoted_event = next(
        event
        for event in dependencies.ledger.read_all(match_one)
        if event.event_type is SOEventType.POLICY_PROMOTED
    )
    promoted = ModelSOPolicyPromotedPayload.model_validate(promoted_event.payload)
    assert promoted.generation == 1
    assert promoted.parent_spec_hash == genesis_policy.spec_hash

    # Replay validity ran inside scoring on the REAL stream (card events and
    # the provenance-carrying MATCH_STARTED included) and stayed green.
    scored_one = _scored_payload(dependencies, match_one)
    assert all(score.replay_validity == 1 for score in scored_one.scores.values())

    # ---- Match 2: the NEXT admission must see the promoted policy ----
    promoted_policy = coordinator.current_policy
    assert promoted_policy.generation == 1
    assert promoted_policy.parameters["aggression"] == 1.25

    # A fresh dependency graph (a new process in production): the policy the
    # next match flies with comes from the DURABLE promotion chain + lineage
    # store, not from process memory.  One bus/ledger pair serves one graph,
    # exactly like the production per-match composition.
    dependencies_two = build_runtime_dependencies(overlay)
    assert dependencies_two.live_learning is not None
    assert dependencies_two.live_learning.current_policy == promoted_policy

    client_two = _CapturingProgrammingClient()
    stack_two, match_two = _run_card_match(
        _card_dependencies(dependencies_two, client_two), seed=777
    )

    started_two = _started_payload(dependencies_two, match_two)
    assert started_two.policy_provenance is not None
    (seat_two,) = started_two.policy_provenance
    # The provenance cites exactly the policy the promotion event minted.
    assert seat_two.policy_id == promoted.policy_id
    assert seat_two.generation == 1
    assert seat_two.spec_hash == promoted.spec_hash
    assert seat_two.source_lineage_digest == promoted.source_lineage_digest

    promoted_guidance = render_policy_guidance(promoted_policy)
    assert client_two.requests
    for request in client_two.requests:
        assert request.system_prompt.endswith(promoted_guidance)
    assert '"aggression":1.25' in promoted_guidance
    assert promoted_guidance != genesis_guidance

    # The composed programmer object agrees byte-for-byte with what was sent.
    programmers = stack_two.card_adapter.programmers if stack_two.card_adapter else None
    assert programmers is not None
    red_programmer = programmers["red"]
    assert isinstance(red_programmer, LLMProgrammingPilot)
    assert red_programmer.system_prompt() == programming_system_prompt(
        _PERSONA, policy_guidance=promoted_guidance
    )
    assert red_programmer.system_prompt() == client_two.requests[0].system_prompt

    scored_two = _scored_payload(dependencies_two, match_two)
    assert all(score.replay_validity == 1 for score in scored_two.scores.values())


@pytest.mark.integration
def test_without_live_learning_the_prompt_and_payload_are_byte_identical(
    tmp_path: Path,
) -> None:
    """Default-cold contract: no policy -> no provenance key, unchanged prompt."""

    overlay = _overlay(tmp_path, live_learning=False)
    dependencies = build_runtime_dependencies(overlay)
    assert dependencies.live_learning is None

    client = _CapturingProgrammingClient()
    _, match_id = _run_card_match(_card_dependencies(dependencies, client), seed=12345)

    started = next(
        event
        for event in dependencies.ledger.read_all(match_id)
        if event.event_type is SOEventType.MATCH_STARTED
    )
    assert "policy_provenance" not in started.payload

    expected = f"{_PERSONA.system_prompt}\n\n{_PROGRAMMING_INSTRUCTIONS}"
    assert client.requests
    for request in client.requests:
        assert request.system_prompt == expected
