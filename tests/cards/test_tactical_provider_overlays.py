"""Contract proofs for the optional hosted-model tactical lanes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.application import ModelSOOpenAICompatibleProviderBinding
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.contracts.player_selection import (
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    validate_player_roster_against_overlay,
)
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_loadout,
    load_match_contract_catalog,
    load_pilot_registry,
)
from steel_onslaught.match.runner import _require_valid_budgets

_ROOT = Path(__file__).resolve().parents[2]


class Lane(TypedDict):
    name: str
    overlay: Path
    registry: Path
    roster: Path
    provider: str
    endpoint: str
    model: str
    secret: str
    identity: str
    pilot_ids: set[str]
    loadouts: tuple[Path, Path]


_LANES: tuple[Lane, ...] = (
    {
        "name": "openrouter",
        "overlay": _ROOT / "contracts_data/overlays/tactical_v1_openrouter.yaml",
        "registry": _ROOT / "contracts_data/pilots/tactical_openrouter",
        "roster": _ROOT / "contracts_data/rosters/tactical_v1_openrouter.yaml",
        "provider": "openrouter",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openrouter/free",
        "secret": "secret://llm/openrouter",
        "identity": "model_identity.openrouter",
        "pilot_ids": {"pilot.openrouter.sniper", "pilot.openrouter.opportunist"},
        "loadouts": (
            _ROOT / "contracts_data/loadouts/tactical_openrouter/sniper_ironclad.yaml",
            _ROOT / "contracts_data/loadouts/tactical_openrouter/opportunist_hunter.yaml",
        ),
    },
    {
        "name": "gemini",
        "overlay": _ROOT / "contracts_data/overlays/tactical_v1_gemini.yaml",
        "registry": _ROOT / "contracts_data/pilots/tactical_gemini",
        "roster": _ROOT / "contracts_data/rosters/tactical_v1_gemini.yaml",
        "provider": "gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.5-flash",
        "secret": "secret://llm/gemini",
        "identity": "model_identity.gemini",
        "pilot_ids": {"pilot.gemini.sniper", "pilot.gemini.opportunist"},
        "loadouts": (
            _ROOT / "contracts_data/loadouts/tactical_gemini/sniper_ironclad.yaml",
            _ROOT / "contracts_data/loadouts/tactical_gemini/opportunist_hunter.yaml",
        ),
    },
)


@pytest.mark.unit
@pytest.mark.parametrize("lane", _LANES, ids=lambda lane: lane["name"])
def test_tactical_provider_overlay_binds_a_single_opaque_hosted_model(
    lane: Lane,
) -> None:
    overlay = load_application_overlay(lane["overlay"])

    assert len(overlay.llm.providers) == 1
    provider = overlay.llm.providers[0]
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == lane["provider"]
    assert provider.endpoint_url == lane["endpoint"]
    assert provider.model == lane["model"]
    assert provider.secret_ref is not None
    assert provider.secret_ref.kind == "opaque"
    assert provider.secret_ref.ref == lane["secret"]
    assert overlay.llm.secret_resolver.kind == "injected"

    assert len(overlay.llm.model_identities) == 1
    assert overlay.llm.model_identities[0].model_identity_id == lane["identity"]
    assert overlay.llm.model_identities[0].provider_binding_id == lane["provider"]
    assert overlay.contracts.pilot_registry_dir == lane["registry"].resolve()


@pytest.mark.unit
@pytest.mark.parametrize("lane", _LANES, ids=lambda lane: lane["name"])
def test_tactical_provider_roster_exposes_human_and_model_choices(lane: Lane) -> None:
    overlay = load_application_overlay(lane["overlay"])
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    assert set(registry.as_mapping()) == lane["pilot_ids"]

    for spec in registry.as_mapping().values():
        assert isinstance(spec.parameters, ModelSOLlmPilotParams)
        assert spec.parameters.provider == lane["provider"]

    raw_roster = yaml.safe_load(lane["roster"].read_text(encoding="utf-8"))
    roster = ModelSOPlayerRosterBinding.model_validate_json(json.dumps(raw_roster))
    validate_player_roster_against_overlay(
        roster=roster,
        overlay=overlay,
        pilot_registry=registry,
    )

    projection = roster.public_projection()
    assert {option.kind for option in projection.options} == {"human", "model"}
    model_options = {
        option.option_id: option
        for option in roster.options
        if isinstance(option, ModelSOModelPlayerOptionBinding)
    }
    assert len(model_options) == 2
    assert {option.model_identity_id for option in model_options.values()} == {lane["identity"]}
    assert all(seat.default_option_id in seat.allowed_option_ids for seat in roster.seats)


@pytest.mark.unit
@pytest.mark.parametrize("lane", _LANES, ids=lambda lane: lane["name"])
def test_tactical_provider_loadouts_pass_authoritative_catalog_budgets(
    lane: Lane,
) -> None:
    catalog = load_match_contract_catalog(_ROOT / "contracts_data")
    registry = load_pilot_registry(lane["registry"])
    expected_ids = lane["pilot_ids"]
    for path in lane["loadouts"]:
        loadout = load_loadout(path)
        _require_valid_budgets(loadout, catalog)
        assert loadout.pilot_id in expected_ids
        assert registry.get(loadout.pilot_id) is not None
