"""Overlay and composition proofs for explicit card-mode programmers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import pytest

from steel_onslaught.contracts.application import (
    ModelSOCardCatalogBinding,
    ModelSOCardProgrammerBinding,
)
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
from steel_onslaught.contracts.pilot import (
    ModelSOAggressivePilotParams,
    ModelSOLlmPilotParams,
    ModelSOPilotLineage,
    ModelSOPilotSpec,
    SOWeaponPreference,
)
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.llm.personas import Persona, PersonaRegistry
from steel_onslaught.llm.programming import LLMProgrammingPilot
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ProtocolLlmClient,
    ProtocolLlmClientFactory,
)
from steel_onslaught.match.composition import (
    LlmDependencies,
    build_card_programmers,
    build_card_runner_adapter,
)
from steel_onslaught.pilots.programming import ProgrammingPilot

pytestmark = pytest.mark.unit


class _Client:
    def __init__(self, name: str) -> None:
        self.name = name

    def complete(self, _request: ModelSOLlmCompletionRequest) -> LlmResponse:
        return LlmResponse(
            text='{"registers":[],"confidence":1.0,"rationale":"fixture"}',
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model=self.name,
            finish_reason="stop",
        )


class _Clients(ProtocolLlmClientFactory):
    def __init__(self, clients: dict[str, ProtocolLlmClient]) -> None:
        self.clients = clients

    def client_for(self, provider_id: str) -> ProtocolLlmClient:
        try:
            return self.clients[provider_id]
        except KeyError as exc:
            raise ValueError(f"missing selected client {provider_id!r}") from exc


class _Closer:
    def close(self) -> None:
        return


def _llm_dependencies(clients: dict[str, ProtocolLlmClient]) -> LlmDependencies:
    return LlmDependencies(
        client_factory=_Clients(clients),
        persona_registry=PersonaRegistry(
            {
                "sniper": Persona("sniper", "Sniper", "sniper", 0.2),
                "opportunist": Persona("opportunist", "Opportunist", "opportunist", 0.4),
            }
        ),
        pilot_factory=cast(Any, object()),
        tuner_generator=cast(Any, object()),
        closer=_Closer(),
    )


def _llm_spec(spec_id: str, provider: str, persona: str) -> ModelSOPilotSpec:
    return ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id=spec_id,
        display_name=spec_id,
        archetype="llm",
        lineage=ModelSOPilotLineage(parent=None),
        parameters=ModelSOLlmPilotParams(persona=persona, provider=provider),
    )


def _binding(side: Literal["red", "blue"], pilot_spec_id: str) -> ModelSOCardProgrammerBinding:
    return ModelSOCardProgrammerBinding(side=side, pilot_spec_id=pilot_spec_id)


def _aggressive_spec() -> ModelSOPilotSpec:
    return ModelSOPilotSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.pilot",
        id="pilot.aggressive.fixture",
        display_name="Aggressive fixture",
        archetype="aggressive",
        lineage=ModelSOPilotLineage(parent=None),
        parameters=ModelSOAggressivePilotParams(
            vent_at_heat_margin=5,
            idle_vent_heat_threshold=60,
            mode_switch_pressure_floor=10,
            mode_switch_heat_ceiling=60,
            weapon_preference=SOWeaponPreference.HIGHEST_DAMAGE,
        ),
    )


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
        id="deck.test.programmer",
        display_name="Programmer",
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


def test_overlay_binding_is_typed_and_explicit_per_seat(tmp_path: Path) -> None:
    binding = ModelSOCardCatalogBinding(
        kind="filesystem_yaml",
        cards_dir=tmp_path,
        decks_dir=tmp_path,
        card_mode_enabled=True,
        deck_id="deck.test.programmer",
        programmers=(
            _binding("red", "pilot.llm.red"),
            _binding("blue", "pilot.llm.blue"),
        ),
    )

    assert tuple(programmer.side for programmer in binding.programmers) == ("red", "blue")
    with pytest.raises(ValueError, match="at most once"):
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=tmp_path,
            decks_dir=tmp_path,
            card_mode_enabled=True,
            deck_id="deck.test.programmer",
            programmers=(
                _binding("red", "pilot.llm.red"),
                _binding("red", "pilot.llm.blue"),
            ),
        )
    with pytest.raises(ValueError, match="unknown_field"):
        ModelSOCardCatalogBinding.model_validate(
            {
                "kind": "filesystem_yaml",
                "cards_dir": tmp_path,
                "decks_dir": tmp_path,
                "unknown_field": True,
            }
        )
    with pytest.raises(ValueError, match="require card_mode_enabled"):
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=tmp_path,
            decks_dir=tmp_path,
            programmers=(_binding("red", "pilot.llm.red"),),
        )


def test_explicit_bindings_resolve_exact_seat_spec_provider_and_persona() -> None:
    red_client = _Client("red-provider")
    blue_client = _Client("blue-provider")
    llm = _llm_dependencies({"provider.red": red_client, "provider.blue": blue_client})
    registry = PilotSpecRegistry(
        {
            "pilot.llm.red": _llm_spec("pilot.llm.red", "provider.red", "sniper"),
            "pilot.llm.blue": _llm_spec("pilot.llm.blue", "provider.blue", "opportunist"),
        }
    )

    programmers = build_card_programmers(
        (
            _binding("red", "pilot.llm.red"),
            _binding("blue", "pilot.llm.blue"),
        ),
        registry=registry,
        llm=llm,
    )

    assert set(programmers) == {"red", "blue"}
    red_pilot = programmers["red"]
    blue_pilot = programmers["blue"]
    assert isinstance(red_pilot, LLMProgrammingPilot)
    assert isinstance(blue_pilot, LLMProgrammingPilot)
    assert red_pilot._client is red_client
    assert red_pilot._persona.persona_id == "sniper"
    assert blue_pilot._client is blue_client
    assert blue_pilot._persona.persona_id == "opportunist"
    assert all(isinstance(pilot, ProgrammingPilot) for pilot in programmers.values())
    adapter = build_card_runner_adapter(snapshot=_snapshot(), programmers=programmers)
    assert adapter.programmers is not None
    assert adapter.programmers["red"] is red_pilot
    assert adapter.programmers["blue"] is blue_pilot


def test_card_adapter_without_overlay_bindings_keeps_deterministic_programmer() -> None:
    adapter = build_card_runner_adapter(snapshot=_snapshot())

    assert adapter.programmers is None


def test_card_programmer_binding_fails_closed_for_unknown_spec() -> None:
    with pytest.raises((ValueError, RuntimeError), match=r"(unknown|must use llm)"):
        build_card_programmers(
            (_binding("red", "pilot.llm.missing"),),
            registry=PilotSpecRegistry({}),
            llm=_llm_dependencies({"provider.red": _Client("red")}),
        )


def test_card_programmer_binding_fails_closed_for_non_llm_spec() -> None:
    with pytest.raises(ValueError, match="must use llm"):
        build_card_programmers(
            (_binding("red", "pilot.aggressive.fixture"),),
            registry=PilotSpecRegistry({"pilot.aggressive.fixture": _aggressive_spec()}),
            llm=_llm_dependencies({"provider.red": _Client("red")}),
        )


@pytest.mark.parametrize(
    ("spec", "clients", "message"),
    [
        (
            _llm_spec("pilot.llm.red", "provider.missing", "sniper"),
            {},
            "missing selected client",
        ),
        (
            _llm_spec("pilot.llm.red", "provider.red", "persona.missing"),
            {"provider.red": _Client("red")},
            "unknown_persona",
        ),
    ],
)
def test_card_programmer_binding_fails_closed_for_missing_provider_or_persona(
    spec: ModelSOPilotSpec,
    clients: dict[str, ProtocolLlmClient],
    message: str,
) -> None:
    with pytest.raises((ValueError, RuntimeError), match=message):
        build_card_programmers(
            (_binding("red", spec.id),),
            registry=PilotSpecRegistry({spec.id: spec}),
            llm=_llm_dependencies(clients),
        )
