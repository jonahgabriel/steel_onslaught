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
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload
from steel_onslaught.llm.effect import LlmSemanticError
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.programming import LLMProgrammingPilot
from steel_onslaught.llm.schemas import (
    LlmResponse,
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
def test_default_failure_policy_rejects_invalid_or_unsafe_plans(response_text: str) -> None:
    pilot = LLMProgrammingPilot(client=_ResponseClient(response_text), persona=_persona())

    with pytest.raises(LlmSemanticError):
        program_for_seat(pilot, _observation())


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
    assert len(client.requests) == 1
