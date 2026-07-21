"""Contract/data checks for the Qwen27 tactical comparison overlay."""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.contracts.application import ModelSOOpenAICompatibleProviderBinding
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_card_runtime_snapshot,
    load_pilot_registry,
)

_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY = _ROOT / "contracts_data/overlays/tactical_v1_qwen27.yaml"


@pytest.mark.unit
def test_tactical_qwen27_overlay_binds_exact_lab_provider_and_model() -> None:
    overlay = load_application_overlay(_OVERLAY)

    assert overlay.contracts.card_catalog is not None
    binding = overlay.contracts.card_catalog
    assert binding.card_mode_enabled is True
    assert binding.deck_id == "deck.tactical.v1"
    assert binding.card_cadence == "paced"
    assert binding.cards_dir == (_ROOT / "contracts_data/cards").resolve()
    assert binding.decks_dir == (_ROOT / "contracts_data/decks").resolve()
    assert tuple(programmer.pilot_spec_id for programmer in binding.programmers) == (
        "pilot.llm.qwen27",
        "pilot.llm.qwen27_opportunist",
    )

    provider = overlay.llm.providers[0]
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "qwen27"
    assert provider.model == "Qwen3.6-27B-MTP-IQ4_XS.gguf"
    assert provider.endpoint_url == (
        "http://omninode-pc.tail75df5e.ts.net:8001/v1/chat/completions"
    )
    assert provider.secret_ref is None
    assert overlay.llm.model_identities[0].provider_binding_id == "qwen27"
    assert overlay.llm.personas_dir == (_ROOT / "contracts_data/pilots/personas").resolve()
    assert (
        overlay.contracts.pilot_registry_dir
        == (_ROOT / "contracts_data/pilots/tactical_qwen27").resolve()
    )


@pytest.mark.unit
def test_tactical_qwen27_overlay_resolves_full_pilot_registry_and_deck() -> None:
    overlay = load_application_overlay(_OVERLAY)
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    spec = registry.get("pilot.llm.qwen27")

    assert spec is not None
    assert isinstance(spec.parameters, ModelSOLlmPilotParams)
    assert spec.parameters.provider == "qwen27"
    assert spec.parameters.persona == "sniper"

    assert overlay.contracts.card_catalog is not None
    snapshot = load_card_runtime_snapshot(overlay.contracts.card_catalog)
    assert snapshot.selected_deck_id == "deck.tactical.v1"
    assert snapshot.selected_deck is not None
    assert snapshot.selected_deck.total_cards() == 30
