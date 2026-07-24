"""Stub-only proofs for the whole-round LLM programming seam."""

from __future__ import annotations

import json
from pathlib import Path

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
from steel_onslaught.llm.personas import Persona, PersonaRegistry
from steel_onslaught.llm.programming import (
    _DEFAULT_SEMANTIC_RETRY_LIMIT,
    LLMProgrammingPilot,
    _serialize_programming_observation,
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
    ModelSOEnemyWeaponThreat,
    ModelSOObjectiveView,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    ModelSOVictoryPointsView,
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


def test_programming_instructions_clamp_doctrine_to_dealt_copies() -> None:
    """The code-owned output contract explicitly subordinates persona doctrine
    to the ``available_copies`` multiset — the live RED-brawler abort was a
    doctrinally-consistent ``advance``x5 plan against a single dealt copy,
    repeated near-verbatim across the whole repair budget.  Existing strict-plan
    anchors must survive so the fix tightens, never loosens, the contract."""

    from steel_onslaught.llm.programming import programming_system_prompt

    # Collapse the hard-wrapped prompt so phrase assertions cannot be broken
    # by a reflow of the instruction block's line wrapping.
    prompt = " ".join(programming_system_prompt(_persona()).split())
    # New copy-clamp prohibitions (the invalid_action_parameters fix).
    assert "at most ONE register" in prompt
    assert "persona doctrine never overrides" in prompt
    assert "fill the remaining registers with other legal_hand cards" in prompt
    # Existing anchors are still present (unchanged contract surface).
    assert "registers" in prompt
    assert "ONLY legal card IDs" in prompt
    assert "available_copies" in prompt


def test_over_copy_plan_repair_names_the_violation_and_forbids_action_shape() -> None:
    """The exact live failure shape: the model programs MORE copies of one card
    than were dealt (``advance`` in both free registers, one copy dealt).  The
    repair request must (1) echo the precise multiset rejection back to the
    model, (2) keep the full observation so ``legal_hand`` is available for a
    corrected pick, and (3) forbid the per-tick ``action``/``action_params``
    shape — the observed secondary repair failure where the persona's per-tick
    JSON instruction wins over the whole-round shape after a rejection."""

    client = _SequenceClient(
        [
            _response(
                registers=[
                    {"register_index": 0, "card_id": "card.test.advance"},
                    {"register_index": 2, "card_id": "card.test.advance"},
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
    # One rejected completion + one successful repair; no third call.
    assert len(client.requests) == 2
    repair = client.requests[1]
    # (1) The precise rejection reaches the model.
    assert "invalid_action_parameters" in repair.system_prompt
    assert "card.test.advance" in repair.system_prompt
    # (2) The full observation (legal_hand allowlist) is retained.
    assert '"legal_hand"' in repair.user_prompt
    assert '"available_copies"' in repair.user_prompt
    # (3) The whole-round shape is re-asserted against the per-tick shape.
    assert "NEVER the per-tick" in repair.system_prompt
    assert "action_params" in repair.system_prompt


def test_over_copy_exhaustion_still_classifies_invalid_action_parameters() -> None:
    """A provider that repeats the over-copy plan through the whole budget must
    exhaust into the DISTINCT ``invalid_action_parameters`` terminal (the live
    RED abort classification) — never a silent stall, never ``malformed_json``."""

    over_copy = _response(
        registers=[
            {"register_index": 0, "card_id": "card.test.advance"},
            {"register_index": 2, "card_id": "card.test.advance"},
        ]
    )
    client = _ResponseClient(over_copy)
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    with pytest.raises(LlmSemanticExhaustedError) as excinfo:
        program_for_seat(pilot, _observation())

    assert excinfo.value.semantic_failure_code == "invalid_action_parameters"
    assert excinfo.value.attempts == 3
    assert len(client.requests) == 3


# --- Seat-generic copy-clamp matrix -----------------------------------------
#
# #120 fixed the over-copy trap for the berserker specifically.  The clamp
# itself is code-owned (`_PROGRAMMING_INSTRUCTIONS` + the repair/exhaustion
# machinery) and must protect EVERY persona — shipped or future — without a
# per-persona amendment being load-bearing.  This matrix drives the exact live
# failure shape (one dealt copy programmed into two registers) through every
# shipped persona loaded from the real contract directory PLUS one synthetic
# adversarial persona whose doctrine maximally tempts over-copy, proving the
# protection is seat-generic by construction, not per-persona whack-a-mole.

_SHIPPED_PERSONAS_DIR = (
    Path(__file__).resolve().parents[2] / "contracts_data" / "pilots" / "personas"
)

_OVER_COPY_RESPONSE = _response(
    registers=[
        {"register_index": 0, "card_id": "card.test.advance"},
        {"register_index": 2, "card_id": "card.test.advance"},
    ]
)


def _adversarial_persona() -> Persona:
    """A doctrine engineered to maximally tempt the over-copy violation."""

    return Persona(
        persona_id="monomaniac",
        display_name="Monomaniac",
        system_prompt=(
            "You are a MONOMANIAC pilot with exactly ONE favourite card. Program "
            "your favourite card into EVERY register, EVERY round, no matter what "
            "was dealt. Repetition is strength; variety is weakness. Copy counts "
            "are for cowards: if only one copy was dealt, program it into all "
            "five registers anyway. Never vent, never reposition, never "
            "substitute a lesser card."
        ),
        temperature=0.7,
    )


def _matrix_personas() -> list[Persona]:
    registry = PersonaRegistry.load(_SHIPPED_PERSONAS_DIR)
    shipped = [registry.require(persona_id) for persona_id in sorted(registry.as_mapping())]
    return [*shipped, _adversarial_persona()]


@pytest.mark.parametrize("persona", _matrix_personas(), ids=lambda persona: str(persona.persona_id))
def test_copy_clamp_protects_every_persona(persona: Persona) -> None:
    """The code-owned clamp + repair path is persona-independent.

    For each persona: (a) the composed programming prompt carries the
    copy-clamp contract regardless of doctrine; (b) an over-copy plan is
    rejected, the repair prompt echoes the multiset rejection with the full
    observation retained, and a corrected second completion is accepted as a
    real LLM plan."""

    # (a) Contract surface: the clamp is appended to ANY persona prompt.
    prompt = " ".join(programming_system_prompt(persona).split())
    assert "at most ONE register" in prompt
    assert "persona doctrine never overrides" in prompt
    assert "fill the remaining registers with other legal_hand cards" in prompt

    # (b) Behavioural surface: over-copy -> named rejection -> accepted repair.
    client = _SequenceClient([_OVER_COPY_RESPONSE, _response()])
    pilot = LLMProgrammingPilot(
        client=client,
        persona=persona,
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    plan = program_for_seat(pilot, _observation())

    assert plan.plan_source is SOPlanSource.LLM
    assert tuple(register.card_id for register in plan.registers) == (
        "card.test.advance",
        "card.test.vent",
    )
    assert len(client.requests) == 2
    repair = client.requests[1]
    assert "invalid_action_parameters" in repair.system_prompt
    assert "never exceeds available_copies" in repair.system_prompt
    assert '"legal_hand"' in repair.user_prompt
    assert '"available_copies"' in repair.user_prompt


def test_adversarial_over_copy_doctrine_still_exhausts_classified() -> None:
    """Even a doctrine built to defeat the clamp cannot escape the classified
    terminal: a provider that never self-corrects exhausts the bounded budget
    into ``invalid_action_parameters`` — never a stall, never a silent
    deterministic substitution."""

    client = _ResponseClient(_OVER_COPY_RESPONSE)
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_adversarial_persona(),
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    with pytest.raises(LlmSemanticExhaustedError) as excinfo:
        program_for_seat(pilot, _observation())

    assert excinfo.value.semantic_failure_code == "invalid_action_parameters"
    assert excinfo.value.attempts == 3
    assert len(client.requests) == 3


def _objective_observation() -> ModelSOProgrammingObservation:
    """The same observation as ``_observation`` but on an objective arena."""

    base = _observation()
    pilot = base.pilot_observation.model_copy(
        update={
            "objectives": (
                ModelSOObjectiveView(
                    objective_id="objective.north_works",
                    cell=ModelSOPosition(x=30, y=22),
                    vp_per_round=1,
                    control="enemy",
                    own_distance_chebyshev=9,
                ),
                ModelSOObjectiveView(
                    objective_id="objective.west_yard",
                    cell=ModelSOPosition(x=18, y=30),
                    vp_per_round=1,
                    control="own",
                    own_distance_chebyshev=1,
                ),
            ),
            "victory_points": ModelSOVictoryPointsView(own_vp=4, enemy_vp=7, vp_threshold=15),
        }
    )
    return base.model_copy(update={"pilot_observation": pilot})


# --- Utility-surfacing confound fix (C) -------------------------------------
#
# The utility-battery ledger recorded qwen35 keeping drafted utility cards at
# ~2-6% (red 7/406=0.0172, blue 23/406=0.0567 vs 0.50 chance).  Two removable
# surfacing biases in this prompt caused it: the card definition serialized the
# engine-only resolution ``priority`` (utility 280-300 < movement 400 < attack
# 600) beside "place the strongest card in each register", teaching the model
# to read the lowest-priority category as the weakest/discardable one; and
# utility was the only category whose effect never stated its tactical payoff.
# The fix removes ``priority`` from the model-facing surface for every category
# and adds an authored ``description`` the utility cards populate.


def test_card_definition_omits_priority_and_surfaces_description() -> None:
    """The model-facing card definition must not leak resolution ``priority``
    as a strength signal, and must surface an authored tactical description."""

    from steel_onslaught.llm.programming import _card_definition

    movement = _card("card.test.advance", SOCardCategory.MOVEMENT, 400)
    utility = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.utility.smoke",
        display_name="Deploy Smoke",
        category=SOCardCategory.UTILITY,
        priority=300,
        heat_cost=25,
        description="Blocks enemy line-of-sight within the effect radius for its duration.",
        effect=ModelSOCardEffect(utility_kind="smoke", radius=1, duration_ticks=2),
    )

    movement_def = _card_definition(movement)
    utility_def = _card_definition(utility)

    # FIX 1: ``priority`` is never serialized, for ANY category.
    assert "priority" not in movement_def
    assert "priority" not in utility_def

    # FIX 2: an authored description reaches the utility card definition...
    assert utility_def["description"] == (
        "Blocks enemy line-of-sight within the effect radius for its duration."
    )
    # ...while a card without one omits the key entirely (byte-identical surface).
    assert "description" not in movement_def


def test_serialized_programming_prompt_never_leaks_priority() -> None:
    """No card ``priority`` field survives into the whole-round prompt bytes."""

    serialized = _serialize_programming_observation(_observation())
    assert '"priority"' not in serialized


# --- Prompt-arms ARM S: cover map + enemy weapon threat surfacing (2026-07-24) -
#
# The 2026-07-24 brawler prompt-content audit found the whole-round prompt
# carried zero cover/obstacle information (only single-bit LOS/adjacency
# derivatives) and zero enemy weapon-range information of any kind. These
# tests prove both neutral facts reach the serialized prompt, and that an
# obstacle-free / enemy-free observation still renders both keys as an empty
# list rather than omitting them (a stable, always-present shape for the
# model and for downstream parsers).


def test_serialized_prompt_surfaces_cover_cells() -> None:
    observation = _observation()
    pilot = observation.pilot_observation.model_copy(
        update={
            "cover_cells": (
                ModelSOPosition(x=20, y=30),
                ModelSOPosition(x=36, y=30),
            )
        }
    )
    observation = observation.model_copy(update={"pilot_observation": pilot})

    serialized = _serialize_programming_observation(observation)
    payload = json.loads(serialized)

    assert payload["own_observation"]["cover_cells"] == [
        {"x": 20, "y": 30},
        {"x": 36, "y": 30},
    ]


def test_serialized_prompt_surfaces_enemy_weapon_threat() -> None:
    observation = _observation()
    pilot = observation.pilot_observation.model_copy(
        update={
            "enemy_weapon_threat": (
                ModelSOEnemyWeaponThreat(
                    enemy_mech_id="mech.blue.01",
                    weapon_id="weapon.siege.artillery_mortar",
                    range=50,
                    damage=20,
                ),
            )
        }
    )
    observation = observation.model_copy(update={"pilot_observation": pilot})

    serialized = _serialize_programming_observation(observation)
    payload = json.loads(serialized)

    assert payload["enemy_weapon_threat"] == [
        {
            "enemy_mech_id": "mech.blue.01",
            "weapon_id": "weapon.siege.artillery_mortar",
            "range": 50,
            "damage": 20,
        }
    ]


def test_serialized_prompt_renders_empty_cover_and_threat_as_empty_lists() -> None:
    """No cover / no living enemy still renders both keys, as empty lists."""
    serialized = _serialize_programming_observation(_observation())
    payload = json.loads(serialized)

    assert payload["own_observation"]["cover_cells"] == []
    assert payload["enemy_weapon_threat"] == []


# --- Show-dont-tell spatial representation arms R1/R2 (2026-07-24) ---------
#
# ARM R1/R2 add a rendered viewport map, resolver-backed per-dealt-movement-
# card consequence previews, and in-range weapon-card flags. Every field is
# populated ONLY when the observation carries them (an unopted seat's
# ``ModelSOProgrammingObservation.spatial_grid`` stays ``None``), so an
# unopted seat's serialized prompt must be BYTE-IDENTICAL to the pre-arm
# shape -- these tests pin both the opted-in and the opted-out cases.


def test_serialized_prompt_omits_spatial_keys_when_not_opted_in() -> None:
    """The default (unopted) observation carries no spatial_grid: the
    serialized prompt must not gain any new keys at all."""
    baseline = _serialize_programming_observation(_observation())
    payload = json.loads(baseline)

    assert "spatial_grid" not in payload["own_observation"]
    assert "movement_previews" not in payload
    assert "weapon_range_flags" not in payload
    assert "legend" not in payload


def test_serialized_prompt_surfaces_spatial_grid_and_previews_when_opted_in() -> None:
    from steel_onslaught.match.spatial_preview import (
        compute_movement_previews,
        compute_weapon_range_flags,
        render_ascii_grid,
    )

    observation = _observation()
    self_pos = observation.pilot_observation.position
    enemy_pos = ModelSOPosition(x=self_pos.x + 6, y=self_pos.y)
    grid = render_ascii_grid(
        self_pos=self_pos,
        enemy_pos=enemy_pos,
        obstacles=frozenset(),
        objectives=(),
        arena_size=40,
    )
    previews = compute_movement_previews(
        hand_cards=observation.hand_cards,
        from_pos=self_pos,
        budget=4,
        enemy_pos=enemy_pos,
        obstacles=frozenset(),
        arena_size=40,
    )
    flags = compute_weapon_range_flags(
        hand_cards=observation.hand_cards,
        weapon_ids=(),
        weapon_views=observation.pilot_observation.weapons,
        distance_current=6,
    )
    observation = observation.model_copy(
        update={
            "spatial_grid": grid,
            "movement_previews": previews,
            "weapon_range_flags": flags,
        }
    )

    serialized = _serialize_programming_observation(observation)
    payload = json.loads(serialized)

    assert payload["own_observation"]["spatial_grid"]["radius"] == grid.radius
    assert len(payload["own_observation"]["spatial_grid"]["rows"]) == len(grid.rows)
    assert payload["movement_previews"]
    assert payload["movement_previews"][0]["card_id"] in {
        str(card_id) for card_id in observation.hand
    }
    assert "legend" in payload
    assert payload["legend"]["S"]


def test_programming_system_prompt_stays_byte_identical_for_none_representation() -> None:
    """``spatial_representation="none"`` (the default) is a no-op on the prompt."""
    with_default = programming_system_prompt(_persona())
    with_explicit_none = programming_system_prompt(_persona(), spatial_representation="none")
    assert with_default == with_explicit_none


def test_programming_system_prompt_adds_grid_addendum_only_for_grid() -> None:
    base = programming_system_prompt(_persona())
    grid = programming_system_prompt(_persona(), spatial_representation="grid")
    assert grid != base
    assert grid.startswith(base)
    assert "spatial_grid" in grid
    assert "spatial_read" not in grid  # R2-only field, not mentioned by R1


def test_programming_system_prompt_adds_scaffold_addendum_only_for_grid_scaffold() -> None:
    grid = programming_system_prompt(_persona(), spatial_representation="grid")
    scaffold = programming_system_prompt(_persona(), spatial_representation="grid_scaffold")
    assert scaffold != grid
    assert scaffold.startswith(grid)
    assert "spatial_read" in scaffold


def test_llm_programming_pilot_exposes_spatial_representation_property() -> None:
    pilot_default = LLMProgrammingPilot(client=_ResponseClient("{}"), persona=_persona())
    assert pilot_default.spatial_representation == "none"

    pilot_r2 = LLMProgrammingPilot(
        client=_ResponseClient("{}"),
        persona=_persona(),
        spatial_representation="grid_scaffold",
    )
    assert pilot_r2.spatial_representation == "grid_scaffold"
    assert "spatial_read" in pilot_r2.system_prompt()


def test_llm_programming_pilot_rejects_unknown_spatial_representation() -> None:
    with pytest.raises(ValueError, match="spatial_representation"):
        LLMProgrammingPilot(
            client=_ResponseClient("{}"),
            persona=_persona(),
            spatial_representation="bogus",  # type: ignore[arg-type]
        )


def test_grid_scaffold_seat_accepts_plan_missing_spatial_read_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A scaffold field must never become a new abort source (schema-tolerant)."""
    observation = _observation().model_copy(update={"spatial_read_required": True})
    plan_json = json.dumps(
        {
            "registers": [
                {"register_index": 0, "card_id": "card.test.vent"},
                {"register_index": 2, "card_id": "card.test.advance"},
            ],
            "confidence": 0.9,
            "rationale": "no spatial_read field here",
        }
    )
    client = _ResponseClient(plan_json)
    pilot = LLMProgrammingPilot(
        client=client, persona=_persona(), spatial_representation="grid_scaffold"
    )

    import logging

    with caplog.at_level(logging.WARNING, logger="steel_onslaught.llm.programming"):
        plan = pilot.program(observation)

    assert plan.plan_source is SOPlanSource.LLM
    assert any("spatial_read" in record.message for record in caplog.records)


def test_grid_scaffold_seat_accepts_plan_with_spatial_read() -> None:
    observation = _observation().model_copy(update={"spatial_read_required": True})
    plan_json = json.dumps(
        {
            "registers": [
                {"register_index": 0, "card_id": "card.test.vent"},
                {"register_index": 2, "card_id": "card.test.advance"},
            ],
            "confidence": 0.9,
            "rationale": "vent then advance",
            "spatial_read": "clear line of sight, no cover nearby",
        }
    )
    client = _ResponseClient(plan_json)
    pilot = LLMProgrammingPilot(
        client=client, persona=_persona(), spatial_representation="grid_scaffold"
    )
    plan = pilot.program(observation)
    assert plan.plan_source is SOPlanSource.LLM


def test_objective_free_programming_prompt_has_no_objectives_block() -> None:
    """Pre-Phase-4 prompt shape is preserved byte-for-byte off objective arenas."""

    serialized = _serialize_programming_observation(_observation())
    assert '"objectives"' not in serialized


def test_objective_programming_prompt_block_is_deterministic_and_additive() -> None:
    """The objectives block adds exactly one key, deterministically ordered."""

    with_objectives = _serialize_programming_observation(_objective_observation())
    without = _serialize_programming_observation(_observation())

    parsed = json.loads(with_objectives)
    block = parsed.pop("objectives")
    # Additive-only: removing the block restores the objective-free prompt.
    assert json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == without

    assert block["vp_threshold"] == 15
    assert block["own_vp"] == 4
    assert block["enemy_vp"] == 7
    assert "first side to reach" in block["rule"]
    assert [cell["objective_id"] for cell in block["cells"]] == [
        "objective.north_works",
        "objective.west_yard",
    ]
    assert block["cells"][1] == {
        "objective_id": "objective.west_yard",
        "cell": {"x": 18, "y": 30},
        "vp_per_round": 1,
        "control": "own",
        "own_distance_chebyshev": 1,
    }
    # Deterministic: same observation, same bytes.
    assert _serialize_programming_observation(_objective_observation()) == with_objectives


# --- Objectives-block under-fill clamp ---------------------------------------
#
# The O-GATE battery (evidence: docs/evidence/2026-07-22-ogate-objectives-battery.md)
# measured a NEW invalid_action_parameters class that #124 had at 0/840 without
# the objectives block: 11/413 first-attempt completions (~2.7 per 100, blue 6 /
# red 5) emitted a structurally valid but massively under-filled register plan
# (31-41 completion tokens with finish_reason=stop, versus 89-119 for every one
# of the 402 accepted 5-register plans) and were rejected with "program must
# contain exactly the observation free_indices in canonical order" — proven from
# the ledger by reconstructing the repair-prompt correction note (identical
# 553-char note on all 11 repair requests).  The objectives rule line was the
# only imperative text inside the user payload; the fix subordinates it to the
# wire contract (objectives change WHICH cards, never the response shape).


def test_objective_rule_subordinates_objectives_to_the_register_contract() -> None:
    """The objectives rule line must re-anchor the whole-round wire contract.

    An imperative rendered inside observation data competes with the code-owned
    instruction block; the O-GATE ledger showed it winning ~2.7% of the time as
    single-action under-filled plans.  The rule must therefore state that
    objective play changes card CHOICE only and re-assert the full-register
    requirement, and must name objective ids/cells as map data so they cannot
    leak into card_id or register values.
    """

    serialized = _serialize_programming_observation(_objective_observation())
    rule = json.loads(serialized)["objectives"]["rule"]
    assert "never the response shape" in rule
    assert "fill EVERY free register exactly once" in rule
    assert "legal_hand card ids" in rule
    assert "never card ids or register values" in rule
    # The objective imperative survives, subordinated to the full program.
    assert "scoring or denying objectives" in rule
    # The victory rule the block exists to teach is intact.
    assert "first side to reach" in rule


_UNDER_FILLED_RESPONSE = _response(
    registers=[{"register_index": 0, "card_id": "card.test.advance"}],
    rationale="Advance toward the west yard objective.",
)


def test_under_filled_plan_rejects_then_repairs_on_objective_arena() -> None:
    """The exact O-GATE failing shape: under-fill -> named rejection -> repair.

    A structurally valid single-register plan against a two-free-register
    objective observation must be rejected as ``invalid_action_parameters``
    (never ``malformed_json``), the repair prompt must echo the exact
    free_indices rejection with the full observation (legal_hand) retained,
    and a corrected full plan on the bounded retry must be accepted as a real
    LLM plan — the 11/11 first-retry recovery the O-GATE ledger recorded.
    """

    client = _SequenceClient([_UNDER_FILLED_RESPONSE, _response()])
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    plan = program_for_seat(pilot, _objective_observation())

    assert plan.plan_source is SOPlanSource.LLM
    assert tuple(register.register_index for register in plan.registers) == (0, 2)
    assert len(client.requests) == 2
    repair = client.requests[1]
    assert "invalid_action_parameters" in repair.system_prompt
    assert "free_indices in canonical order" in repair.system_prompt
    assert "fills every free register exactly once" in repair.system_prompt
    assert '"legal_hand"' in repair.user_prompt
    # The repaired request still carries the subordinated objectives block.
    assert '"objectives"' in repair.user_prompt
    assert "never the response shape" in repair.user_prompt


def test_under_fill_exhaustion_still_classifies_invalid_action_parameters() -> None:
    """A provider that never grows the plan exhausts into the classified
    ``invalid_action_parameters`` terminal — never a stall, never
    ``malformed_json``."""

    client = _ResponseClient(_UNDER_FILLED_RESPONSE)
    pilot = LLMProgrammingPilot(
        client=client,
        persona=_persona(),
        provider_id="provider.card.test",
        semantic_retry_limit=2,
    )

    with pytest.raises(LlmSemanticExhaustedError) as excinfo:
        program_for_seat(pilot, _objective_observation())

    assert excinfo.value.semantic_failure_code == "invalid_action_parameters"
    assert excinfo.value.attempts == 3
    assert len(client.requests) == 3
