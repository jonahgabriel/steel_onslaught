"""Hermetic proof that an injected LLM programmer reaches card-round production."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from steel_onslaught.cards.dealer import ModelSODealerScope
from steel_onslaught.contracts.application import ModelSOCardProgrammerBinding
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
from steel_onslaught.contracts.pilot import (
    ModelSOLlmPilotParams,
    ModelSOPilotLineage,
    ModelSOPilotSpec,
)
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.llm.personas import Persona, PersonaRegistry
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ProtocolLlmClient,
    ProtocolLlmClientFactory,
)
from steel_onslaught.match.card_adapter import ModelSOCardSeatRequest
from steel_onslaught.match.composition import (
    LlmDependencies,
    build_card_programmers,
    build_card_runner_adapter,
)
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

pytestmark = pytest.mark.unit


class _ProgrammingClient(ProtocolLlmClient):
    """Deterministic fake provider; no network or ambient configuration."""

    def __init__(self) -> None:
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        return LlmResponse(
            text=json.dumps(
                {
                    "registers": [
                        {"register_index": 0, "card_id": "card.test.advance"},
                    ],
                    "confidence": 0.75,
                    "rationale": "advance while preserving distance",
                }
            ),
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="injected-programming-fixture",
            finish_reason="stop",
        )


class _Clients(ProtocolLlmClientFactory):
    def __init__(self, client: ProtocolLlmClient) -> None:
        self._client = client

    def client_for(self, provider_id: str) -> ProtocolLlmClient:
        if provider_id != "provider.red":
            raise ValueError(f"unexpected provider {provider_id!r}")
        return self._client


class _Closer:
    def close(self) -> None:
        return


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    card = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.test.advance",
        display_name="Advance",
        category=SOCardCategory.MOVEMENT,
        priority=10,
        heat_cost=0,
        effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
    )
    catalog = ModelSOCardCatalog(cards=(card,))
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.llm_programmer",
        display_name="LLM programmer fixture",
        hand_size=1,
        register_count=1,
        cards=(ModelSODeckEntry(card_id=card.id, count=1),),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=catalog,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(catalog, (deck,)),
    )


def _pilot_spec() -> ModelSOPilotSpec:
    return ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id="pilot.llm.red",
        display_name="Fixture LLM",
        archetype="llm",
        lineage=ModelSOPilotLineage(parent=None),
        parameters=ModelSOLlmPilotParams(persona="opportunist", provider="provider.red"),
    )


def _llm_dependencies(client: ProtocolLlmClient) -> LlmDependencies:
    return LlmDependencies(
        client_factory=_Clients(client),
        persona_registry=PersonaRegistry(
            {"opportunist": Persona("opportunist", "Opportunist", "vary the plan", 0.4)}
        ),
        # These fields are not used by card programming, but are part of the
        # explicit application dependency graph and intentionally have no
        # ambient/provider fallback.
        pilot_factory=cast(Any, object()),
        tuner_generator=cast(Any, object()),
        closer=_Closer(),
    )


def _seat_request() -> ModelSOCardSeatRequest:
    boiler = ModelSOBoilerState(
        match_id="match.test.llm-programmer",
        mech_id="mech.red.01",
        tick=4,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=0,
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
    observation = ModelSOPilotObservation(
        match_id="match.test.llm-programmer",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=4,
        match_elapsed_ticks=4,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.test.primary",
                damage=10,
                range=15,
                pressure_cost=2,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            )
        ],
        current_mode=ModeId.RECON,
        mode_lock_expired=True,
        position=ModelSOPosition(x=1, y=1),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=[],
    )
    return ModelSOCardSeatRequest(
        seat="red",
        dealer_scope=ModelSODealerScope(
            match_id=observation.match_id,
            match_seed=17,
            tick=observation.tick,
            seat="red",
        ),
        pilot_observation=observation,
        initiative=0,
    )


def test_injected_llm_programmer_is_called_by_card_round_adapter() -> None:
    client = _ProgrammingClient()
    programmers = build_card_programmers(
        (ModelSOCardProgrammerBinding(side="red", pilot_spec_id="pilot.llm.red"),),
        registry=PilotSpecRegistry({"pilot.llm.red": _pilot_spec()}),
        llm=_llm_dependencies(client),
    )
    adapter = build_card_runner_adapter(snapshot=_snapshot(), programmers=programmers)

    emission = adapter.produce(
        seats=(_seat_request(),),
        round_index=0,
        tick=4,
        causation_id="round.test.llm-programmer",
    )

    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.evidence_context is not None
    assert request.evidence_context.match_id == "match.test.llm-programmer"
    assert '"free_indices":[0]' in request.user_prompt
    assert emission.sequence is not None
    assert emission.sequence.plan_committed[0].registers[0].card_id == "card.test.advance"
    assert emission.actions[0].event_type is SOEventType.MOVE_INTENT
