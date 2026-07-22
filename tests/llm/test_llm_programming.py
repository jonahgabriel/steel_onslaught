"""Stub-only proofs for the whole-round LLM programming seam."""

from __future__ import annotations

import json

import pytest

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, SOPlanSource
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.programming import (
    _DEFAULT_SEMANTIC_RETRY_LIMIT,
    LLMProgrammingPilot,
    programming_system_prompt,
)
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmSemanticExhaustedError,
    LlmUsage,
    ModelSOLlmCompletionRequest,
)
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation, program_for_seat
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
)

pytestmark = pytest.mark.unit


def _card(card_id: str, category: SOCardCategory, priority: int) -> ModelSOCard:
    effect = (
        ModelSOCardEffect(direction="toward_enemy", speed="full")
        if category is SOCardCategory.MOVEMENT
        else ModelSOCardEffect()
    )
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=category,
        priority=priority,
        heat_cost=0,
        effect=effect,
    )


def _observation() -> ModelSOProgrammingObservation:
    cards = ModelSOCardCatalog(
        cards=(
            _card("card.test.advance", SOCardCategory.MOVEMENT, 20),
            _card("card.test.advance_alt", SOCardCategory.MOVEMENT, 5),
            _card("card.test.vent", SOCardCategory.VENT, 10),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.programming",
        display_name="Programming test deck",
        hand_size=3,
        register_count=3,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in cards.cards),
    )
    snapshot = ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )
    boiler = ModelSOBoilerState(
        match_id="match.programming",
        mech_id="mech.red.01",
        tick=7,
        pressure_current=30,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=10,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )
    pilot_observation = ModelSOPilotObservation(
        match_id="match.programming",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=7,
        match_elapsed_ticks=7,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.test.primary",
                damage=10,
                range=15,
                pressure_cost=3,
                heat_generated=2,
                cooldown_remaining_ticks=0,
            )
        ],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=2, y=3),
        hp_percent=82.0,
        under_sensor_lock=False,
        has_line_of_sight_to_enemy=True,
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id="mech.blue.01",
                tick=7,
                distance_estimate=6.0,
                confidence=0.8,
                heat_estimate=40.0,
            )
        ],
    )
    return ModelSOProgrammingObservation(
        pilot_observation=pilot_observation,
        card_runtime_snapshot=snapshot,
        seat="red",
        hand=("card.test.vent", "card.test.advance", "card.test.advance_alt"),
        free_indices=(0, 2),
    )


def _persona() -> Persona:
    return Persona(
        persona_id="opportunist",
        display_name="Opportunist",
        system_prompt="Choose a varied tactical plan.",
        temperature=0.4,
    )


class _ResponseClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        return LlmResponse(
            text=self.text,
            usage=LlmUsage(prompt_tokens=10, completion_tokens=4, cost_usd=0.0),
            model="programming-test",
            finish_reason="stop",
        )


class _SequenceClient:
    """Return each queued response text in order, one per completion call."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._texts) - 1)
        return LlmResponse(
            text=self._texts[index],
            usage=LlmUsage(prompt_tokens=10, completion_tokens=4, cost_usd=0.0),
            model="programming-test",
            finish_reason="stop",
        )


class _FailingClient:
    def complete(self, _request: ModelSOLlmCompletionRequest) -> LlmResponse:
        raise ConnectionError("provider unavailable")


def _response(**overrides: object) -> str:
    value: dict[str, object] = {
        "registers": [
            {"register_index": 0, "card_id": "card.test.advance"},
            {"register_index": 2, "card_id": "card.test.vent"},
        ],
        "confidence": 0.8,
        "rationale": "advance, then vent if heat rises",
    }
    value.update(overrides)
    return json.dumps(value)


def test_programming_request_carries_typed_evidence_and_card_context() -> None:
    client = _ResponseClient(_response())
    pilot = LLMProgrammingPilot(client=client, persona=_persona())
    observation = _observation()

    plan = program_for_seat(pilot, observation)

    assert isinstance(plan, ModelSOPlanCommittedPayload)
    assert plan.plan_source is SOPlanSource.LLM
    assert plan.seat == "red"
    assert tuple(register.register_index for register in plan.registers) == (0, 2)
    assert tuple(register.card_id for register in plan.registers) == (
        "card.test.advance",
        "card.test.vent",
    )
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.evidence_context is not None
    assert request.evidence_context.match_id == "match.programming"
    assert request.evidence_context.mech_id == "mech.red.01"
    assert request.evidence_context.player_id == "player.red"
    assert request.evidence_context.tick == 7
    assert request.json_mode is True
    assert '"deck_id":"deck.test.programming"' in request.user_prompt
    assert '"locked_indices":[1]' in request.user_prompt
    assert '"free_indices":[0,2]' in request.user_prompt
    assert '"card_id":"card.test.advance"' in request.user_prompt
    assert '"enemy_mech_id":"mech.blue.01"' in request.user_prompt
    assert '"own_observation"' in request.user_prompt
    assert '"opponent_observations"' in request.user_prompt
    assert '"registers"' in request.system_prompt
    context = json.loads(request.user_prompt)
    assert "cards" not in context["deck"]
    assert [entry["card_id"] for entry in context["legal_hand"]] == [
        "card.test.vent",
        "card.test.advance",
        "card.test.advance_alt",
    ]
    assert [entry["available_copies"] for entry in context["legal_hand"]] == [1, 1, 1]
    assert "ONLY legal card IDs" in request.system_prompt


def test_split_programming_request_uses_partition_descriptor_before_provider_call() -> None:
    """Split hands must reach the provider instead of failing on ``selected_deck``."""

    base = _observation()
    # Keep the legacy selected id populated as some overlays do; the explicit
    # two-deck tuple still owns this observation's hand authority.
    source_deck = base.card_runtime_snapshot.selected_deck
    movement_deck = source_deck.model_copy(update={"id": "deck.test.movement"})
    weapon_deck = source_deck.model_copy(update={"id": "deck.test.weapon"})
    split_decks = tuple(sorted((movement_deck, weapon_deck), key=lambda deck: str(deck.id)))
    snapshot = base.card_runtime_snapshot.model_copy(
        update={
            "selected_deck_id": "deck.test.movement",
            "decks": split_decks,
            "content_sha256": canonical_card_runtime_sha256(
                base.card_runtime_snapshot.card_catalog, split_decks
            ),
        }
    )
    observation = base.model_copy(
        update={
            "card_runtime_snapshot": snapshot,
            "register_count": 3,
            "hand_deck_ids": ("deck.test.movement", "deck.test.weapon"),
        }
    )
    client = _ResponseClient(_response())

    plan = program_for_seat(LLMProgrammingPilot(client=client, persona=_persona()), observation)

    assert len(plan.registers) == 2
    assert len(client.requests) == 1
    context = json.loads(client.requests[0].user_prompt)
    assert context["deck"] == {
        "deck_id": "deck.split",
        "display_name": "Split movement and weapon decks",
        "hand_size": 3,
        "register_count": 3,
        "partition_deck_ids": ["deck.test.movement", "deck.test.weapon"],
    }
    assert context["registers"]["register_count"] == 3


def test_programming_request_preserves_dealt_hand_multiplicity() -> None:
    base = _observation()
    deck = base.deck.model_copy(
        update={
            "cards": tuple(
                entry.model_copy(update={"count": 2})
                if entry.card_id == "card.test.advance"
                else entry
                for entry in base.deck.cards
            )
        }
    )
    snapshot = base.card_runtime_snapshot.model_copy(
        update={
            "decks": (deck,),
            "selected_deck_id": deck.id,
            "content_sha256": canonical_card_runtime_sha256(
                base.card_runtime_snapshot.card_catalog, (deck,)
            ),
        }
    )
    observation = base.model_copy(
        update={
            "card_runtime_snapshot": snapshot,
            "hand": (
                "card.test.advance",
                "card.test.advance",
                "card.test.vent",
            ),
            "free_indices": (0, 1, 2),
        }
    )
    response = _response(
        registers=[
            {"register_index": 0, "card_id": "card.test.advance"},
            {"register_index": 1, "card_id": "card.test.advance"},
            {"register_index": 2, "card_id": "card.test.vent"},
        ]
    )
    client = _ResponseClient(response)
    plan = program_for_seat(LLMProgrammingPilot(client=client, persona=_persona()), observation)

    assert len(plan.registers) == 3
    context = json.loads(client.requests[0].user_prompt)
    assert [(entry["card_id"], entry["available_copies"]) for entry in context["legal_hand"]] == [
        ("card.test.advance", 2),
        ("card.test.vent", 1),
    ]


@pytest.mark.parametrize(
    "response_text",
    [
        "not json",
        _response(extra="forbidden"),
        _response(registers=[{"register_index": 0, "card_id": "card.test.advance"}]),
        _response(
            registers=[
                {"register_index": 0, "card_id": "card.test.advance"},
                {"register_index": 0, "card_id": "card.test.vent"},
            ]
        ),
        _response(
            registers=[
                {"register_index": 0, "card_id": "card.test.unknown"},
                {"register_index": 2, "card_id": "card.test.vent"},
            ]
        ),
        _response(
            registers=[
                {"register_index": 0, "card_id": "card.test.advance"},
                {"register_index": 2, "card_id": "card.test.advance"},
            ]
        ),
    ],
)
def test_default_failure_policy_exhausts_bounded_retries_on_invalid_plans(
    response_text: str,
) -> None:
    """A persistently-invalid provider terminates, never stalls or dies once.

    Under the live ``raise`` policy an invalid plan is reprompted on the same
    model up to the bounded budget. When every attempt is still invalid the
    pilot raises the DISTINCT ``LlmSemanticExhaustedError`` (not a bare
    ``LlmSemanticError``) so the runner can end the match with a classified
    terminal. The provider is called ``retry_limit + 1`` times — one initial
    attempt plus the bounded reprompts.
    """

    client = _ResponseClient(response_text)
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    with pytest.raises(LlmSemanticExhaustedError) as excinfo:
        program_for_seat(pilot, _observation())

    assert len(client.requests) == 3
    assert excinfo.value.seat == "red"
    assert excinfo.value.attempts == 3
    assert excinfo.value.provider_id == "provider.card.test"
    assert excinfo.value.semantic_failure_code in {
        "malformed_json",
        "unknown_action",
        "action_unavailable",
        "invalid_action_parameters",
    }
    # Each reprompt is a real same-model call annotated with the rejection so
    # the model can self-correct — a bounded loop, never a determinism swap.
    assert client.requests[0].persona == "opportunist"
    assert client.requests[1].persona == "opportunist.repair.1"
    assert client.requests[2].persona == "opportunist.repair.2"
    for repair in client.requests[1:]:
        assert "REJECTED" in repair.system_prompt


def test_programming_instructions_forbid_reasoning_wrappers() -> None:
    """The code-owned output contract explicitly forbids the `<think>`/
    chain-of-thought/markdown-fence wrappers that drive the sniper-specific
    ``provider_semantic_failure`` on a reasoning gateway — while preserving the
    existing strict-plan anchors so the fix does not loosen the contract."""

    prompt = programming_system_prompt(_persona())
    # New strict-output prohibitions (the reasoning-wrapper fix).
    assert "<think>" in prompt
    assert "chain-of-thought" in prompt
    assert "code fences" in prompt
    assert "return only the JSON object" in prompt
    # Existing anchors are still present (unchanged contract surface).
    assert "registers" in prompt
    assert "ONLY legal card IDs" in prompt
    assert "available_copies" in prompt


def test_parser_strips_a_reasoning_wrapper_before_extracting_the_plan() -> None:
    """A reasoning gateway that leaks a `<think>` chain-of-thought (carrying its
    OWN braces) before the JSON still yields a valid plan on the FIRST
    completion.  Without the strip the inner brace defeats the first-'{'/last-'}'
    extraction and the whole match aborts on ``malformed_json``."""

    reasoning = (
        "<think>The sniper holds standoff. Draft register "
        '{"register_index": 9, "card_id": "card.wrong"} then reconsider.</think>\n'
    )
    client = _ResponseClient(reasoning + _response())
    pilot = LLMProgrammingPilot(client=client, persona=_persona())

    plan = program_for_seat(pilot, _observation())

    assert plan.plan_source is SOPlanSource.LLM
    assert tuple(register.register_index for register in plan.registers) == (0, 2)
    # Parsed on the first attempt: no repair reprompt was needed.
    assert len(client.requests) == 1


def test_reasoning_only_response_still_reaches_a_terminal() -> None:
    """#115 guarantee under the stricter contract: a provider that answers every
    time with a `<think>` block but no JSON object never freezes — the bounded
    repair budget is spent and the DISTINCT ``LlmSemanticExhaustedError``
    (``malformed_json``) terminal is raised, one real completion per attempt."""

    client = _ResponseClient("<think>I am still weighing spacing and heat.</think>")
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        provider_id="provider.card.test",
    )

    with pytest.raises(LlmSemanticExhaustedError) as excinfo:
        program_for_seat(pilot, _observation())

    assert excinfo.value.semantic_failure_code == "malformed_json"
    # 1 initial attempt + the bounded reprompt budget, all real completions.
    assert len(client.requests) == _DEFAULT_SEMANTIC_RETRY_LIMIT + 1
    assert excinfo.value.attempts == _DEFAULT_SEMANTIC_RETRY_LIMIT + 1


def test_default_policy_retry_recovers_when_the_model_self_corrects() -> None:
    """Invalid once, then valid: the match continues on the same model.

    The happy-retry path proves the bounded loop is a genuine self-correction
    opportunity, not just a delayed abort.
    """

    client = _SequenceClient(
        [
            _response(
                registers=[
                    {"register_index": 0, "card_id": "card.test.unknown"},
                    {"register_index": 2, "card_id": "card.test.vent"},
                ]
            ),
            _response(),
        ]
    )
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    plan = program_for_seat(pilot, _observation())

    assert plan.plan_source is SOPlanSource.LLM
    assert tuple(register.card_id for register in plan.registers) == (
        "card.test.advance",
        "card.test.vent",
    )
    # Exactly two provider calls: one rejected, one accepted. No third attempt.
    assert len(client.requests) == 2
    assert client.requests[1].persona == "opportunist.repair.1"


def test_default_failure_policy_raises_transport_errors() -> None:
    pilot = LLMProgrammingPilot(client=_FailingClient(), persona=_persona())

    with pytest.raises(ConnectionError, match="provider unavailable"):
        program_for_seat(pilot, _observation())


def test_explicit_fallback_policy_is_deterministic_and_non_llm() -> None:
    client = _ResponseClient("not json")
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        failure_policy="fallback",
    )

    plan = program_for_seat(pilot, _observation())

    assert tuple(register.card_id for register in plan.registers) == (
        "card.test.advance",
        "card.test.vent",
    )
    assert plan.confidence == 1.0
    # The substitution is durably classified, not silent.
    assert plan.plan_source is SOPlanSource.DETERMINISTIC_FALLBACK
    assert len(client.requests) == 1


def test_fallback_policy_still_raises_unclassified_provider_failures() -> None:
    """A live match cannot continue on the deterministic planner."""

    pilot = LLMProgrammingPilot(
        client=_FailingClient(),
        persona=_persona(),
        failure_policy="fallback",
    )

    with pytest.raises(ConnectionError, match="provider unavailable"):
        program_for_seat(pilot, _observation())


def test_explicit_fallback_policy_recovers_invalid_action_parameters() -> None:
    client = _ResponseClient(
        _response(
            registers=[
                {"register_index": 0, "card_id": "card.test.unknown"},
                {"register_index": 2, "card_id": "card.test.vent"},
            ]
        )
    )
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        failure_policy="fallback",
    )

    plan = program_for_seat(pilot, _observation())

    assert tuple(register.card_id for register in plan.registers) == (
        "card.test.advance",
        "card.test.vent",
    )
    assert plan.confidence == 1.0
    assert plan.plan_source is SOPlanSource.DETERMINISTIC_FALLBACK
    assert len(client.requests) == 1
