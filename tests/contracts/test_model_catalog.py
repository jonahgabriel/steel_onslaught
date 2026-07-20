"""Proof for the explicit multi-provider catalog seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.export_frontend_bootstrap import export_frontend_bootstrap
from steel_onslaught.cli.serve import build_frontend_bootstrap
from steel_onslaught.commands.authority import canonical_overlay_sha256
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.model_catalog import (
    ModelSOModelCatalog,
    ModelSOModelCatalogModelOption,
    build_model_catalog,
    model_catalog_source_from_roster,
)
from steel_onslaught.contracts.player_selection import (
    ModelSOModelIdentityBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
)
from steel_onslaught.match.composition import load_model_catalog
from tests.overlay import complete_test_overlay

_HASHES = {
    "human": "a" * 64,
    "qwen35": "b" * 64,
    "qwen27": "c" * 64,
    "glm": "d" * 64,
    "openrouter": "e" * 64,
    "gemini": "f" * 64,
}

_CONTRACTS_DATA = Path(__file__).parents[2] / "contracts_data"


def _revalidate_catalog(catalog: ModelSOModelCatalog, **updates: object) -> ModelSOModelCatalog:
    raw = catalog.model_dump(mode="json")
    for key, value in updates.items():
        if key == "seats":
            if not isinstance(value, tuple) or not all(
                isinstance(seat, ModelSOSeatLaunchPolicy) for seat in value
            ):
                raise TypeError("test catalog seats must be a tuple of seat policies")
            raw[key] = [seat.model_dump(mode="json") for seat in value]
        else:
            raw[key] = value
    return ModelSOModelCatalog.model_validate_json(json.dumps(raw))


def _source_roster(provider: str) -> ModelSOPlayerRosterBinding:
    persona = {
        "qwen35": "berserker",
        "glm": "opportunist",
    }.get(provider, "sniper")
    option = ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id=f"player_option.{provider}.pilot",
        display_name=provider.upper(),
        model_identity_id=f"model_identity.{provider}",
        pilot_spec_id=f"pilot.{provider}.pilot",
        persona_id=persona,
        input_source="llm_completion",
    )
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id=f"roster.{provider}",
        options=(option,),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id=f"loadout.{provider}.red",
                allowed_option_ids=(option.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id=f"loadout.{provider}.blue",
                allowed_option_ids=(option.option_id,),
            ),
        ),
    )


def _human_source_roster() -> ModelSOPlayerRosterBinding:
    from steel_onslaught.contracts.player_selection import ModelSOHumanPlayerOptionBinding

    option = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.human.operator",
        display_name="Human Operator",
        human_identity_id="human_identity.local_operator",
        pilot_spec_id="pilot.human.operator",
        input_source="browser_command",
    )
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.human",
        options=(option,),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.human.red",
                allowed_option_ids=(option.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.human.blue",
                allowed_option_ids=(option.option_id,),
            ),
        ),
    )


def _catalog() -> ModelSOModelCatalog:
    sources = [
        model_catalog_source_from_roster(
            overlay_id="overlay.human",
            overlay_sha256=_HASHES["human"],
            roster=_human_source_roster(),
            model_identities=(),
            provider_models={},
        )
    ]
    configured_models = {
        "qwen35": "Qwen3.6-35B-A3B",
        "qwen27": "Qwen3.6-27B-MTP-IQ4_XS.gguf",
        "glm": "glm-5.2",
        "openrouter": "openrouter/free",
        "gemini": "gemini-2.5-flash",
    }
    for provider, provider_model in configured_models.items():
        source = _source_roster(provider)
        sources.append(
            model_catalog_source_from_roster(
                overlay_id=f"overlay.{provider}",
                overlay_sha256=_HASHES[provider],
                roster=source,
                model_identities=(
                    ModelSOModelIdentityBinding(
                        schema_version="1",
                        kind="steel_onslaught.model_identity",
                        model_identity_id=f"model_identity.{provider}",
                        display_name=provider.upper(),
                        provider_binding_id=provider,
                    ),
                ),
                provider_models={provider: provider_model},
            )
        )
    option_ids = tuple(option.option_id for source in sources for option in source.options)
    return build_model_catalog(
        catalog_id="catalog.configured_models",
        roster_id="roster.configured_models",
        sources=sources,
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.catalog.red",
                allowed_option_ids=option_ids,
                default_option_id="player_option.glm.pilot",
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.catalog.blue",
                allowed_option_ids=option_ids,
                default_option_id="player_option.qwen35.pilot",
            ),
        ),
        default_chassis_ids=(
            "chassis.heavy.ironclad_mk1",
            "chassis.medium.hunter_mk1",
        ),
    )


@pytest.mark.unit
def test_configured_catalog_index_loads_all_current_provider_overlays() -> None:
    catalog = load_model_catalog(_CONTRACTS_DATA / "model_catalogs/configured_v1.yaml")
    assert catalog.catalog_id == "catalog.configured_models"
    assert {option.provider_binding_id for option in catalog.options if option.kind == "model"} == {
        "qwen35",
        "qwen27",
        "glm-5.2",
        "openrouter",
        "gemini",
    }
    assert any(option.kind == "human" for option in catalog.options)
    assert catalog.to_roster_binding().roster_id == "roster.configured_models"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("red_option_id", "blue_option_id", "red_role", "blue_role"),
    (
        (
            "player_option.qwen35_model",
            "player_option.qwen35_sniper",
            "berserker",
            "sniper",
        ),
        (
            "player_option.qwen27_model",
            "player_option.qwen27_opportunist",
            "sniper",
            "opportunist",
        ),
    ),
)
def test_configured_local_qwen_pairings_are_asymmetric_without_mirror(
    red_option_id: str,
    blue_option_id: str,
    red_role: str,
    blue_role: str,
) -> None:
    catalog = load_model_catalog(_CONTRACTS_DATA / "model_catalogs/configured_v1.yaml")
    red = next(option for option in catalog.options if option.option_id == red_option_id)
    blue = next(option for option in catalog.options if option.option_id == blue_option_id)
    assert red.kind == blue.kind == "model"
    assert red.provider_binding_id == blue.provider_binding_id
    assert red.model_identity_id == blue.model_identity_id
    assert red.persona_id == red_role
    assert blue.persona_id == blue_role

    pairing = catalog.pairing_provenance(
        red_option_id=red_option_id,
        blue_option_id=blue_option_id,
    )
    assert pairing.mirror_match_mode is False
    assert pairing.red_role_id == red_role
    assert pairing.blue_role_id == blue_role
    assert pairing.red_loadout_id != pairing.blue_loadout_id
    assert pairing.red_chassis_id != pairing.blue_chassis_id


@pytest.mark.unit
def test_catalog_index_exports_existing_bootstrap_roster_and_metadata(tmp_path: Path) -> None:
    overlay_path = _CONTRACTS_DATA / "overlays/live_glm_cards.yaml"
    output_path = tmp_path / "frontend_bootstrap.json"
    bootstrap = export_frontend_bootstrap(
        overlay_path,
        output_path,
        catalog_index_path=_CONTRACTS_DATA / "model_catalogs/configured_v1.yaml",
    )
    assert bootstrap.player_roster is not None
    assert bootstrap.player_roster.roster_id == "roster.configured_models"
    assert bootstrap.model_catalog is not None
    assert bootstrap.model_catalog.default_option_ids == (
        "player_option.glm_sniper",
        "player_option.glm_opportunist",
    )
    assert bootstrap.model_catalog.mirror_match_mode is False
    assert output_path.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.unit
def test_catalog_merges_human_and_configured_provider_options() -> None:
    catalog = _catalog()
    assert [option.kind for option in catalog.options] == [
        "human",
        "model",
        "model",
        "model",
        "model",
        "model",
    ]
    assert {option.provider_binding_id for option in catalog.options if option.kind == "model"} == {
        "qwen35",
        "qwen27",
        "glm",
        "openrouter",
        "gemini",
    }
    assert catalog.canonical_sha256() == catalog.canonical_sha256()
    assert catalog.to_roster_binding().roster_id == "roster.configured_models"


@pytest.mark.unit
def test_catalog_selection_provenance_carries_every_source_identity() -> None:
    catalog = _catalog()
    provenance = catalog.selection_provenance(
        side="red",
        option_id="player_option.openrouter.pilot",
    )
    assert provenance.source_overlay_id == "overlay.openrouter"
    assert provenance.source_overlay_sha256 == _HASHES["openrouter"]
    assert provenance.source_roster_id == "roster.openrouter"
    assert provenance.provider_binding_id == "openrouter"
    assert provenance.provider_model == "openrouter/free"
    assert provenance.model_identity_id == "model_identity.openrouter"
    assert provenance.pilot_spec_id == "pilot.openrouter.pilot"
    assert provenance.loadout_id == "loadout.catalog.red"
    assert provenance.paired_option_id == "player_option.qwen35.pilot"
    assert provenance.pairing.red_chassis_id == "chassis.heavy.ironclad_mk1"
    assert provenance.pairing.blue_chassis_id == "chassis.medium.hunter_mk1"
    assert "secret" not in provenance.model_dump_json()


@pytest.mark.unit
def test_catalog_public_projection_and_bootstrap_keep_roster_compatibility(tmp_path: Path) -> None:
    catalog = _catalog()
    projection = catalog.public_projection()
    assert projection.options[0].kind == "human"
    model_projection = [option for option in projection.options if option.kind == "model"]
    assert {option.provider_binding_id for option in model_projection} == {
        "qwen35",
        "qwen27",
        "glm",
        "openrouter",
        "gemini",
    }
    serialized = projection.model_dump_json()
    assert "endpoint_url" not in serialized
    assert "secret_ref" not in serialized
    assert "pilot_spec_id" not in serialized

    raw = complete_test_overlay(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": tmp_path / "events.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": tmp_path / "leaderboard.sqlite3",
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
                "root": tmp_path / "evaluation_storage",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
                "leaderboard_schema": "leaderboard_v1",
            },
            "contracts": {
                "catalog_dir": tmp_path / "catalog",
                "pilot_registry_dir": tmp_path / "pilots",
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
        },
        tmp_path,
    )
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    bootstrap = build_frontend_bootstrap(overlay, model_catalog=catalog)
    assert bootstrap.player_roster == catalog.to_roster_binding().public_projection()
    assert bootstrap.model_catalog == projection
    assert bootstrap.overlay_sha256 == canonical_overlay_sha256(overlay)


@pytest.mark.unit
def test_catalog_source_requires_explicit_provider_model_and_rejects_unknown_fields() -> None:
    roster = _source_roster("qwen35")
    with pytest.raises(ValueError, match="no configured model"):
        model_catalog_source_from_roster(
            overlay_id="overlay.qwen35",
            overlay_sha256=_HASHES["qwen35"],
            roster=roster,
            model_identities=(
                ModelSOModelIdentityBinding(
                    schema_version="1",
                    kind="steel_onslaught.model_identity",
                    model_identity_id="model_identity.qwen35",
                    display_name="Qwen35",
                    provider_binding_id="qwen35",
                ),
            ),
            provider_models={},
        )
    with pytest.raises(ValidationError, match="unknown"):
        ModelSOModelCatalogModelOption.model_validate(
            {
                "kind": "model",
                "option_id": "player_option.qwen35.pilot",
                "display_name": "Qwen35",
                "model_identity_id": "model_identity.qwen35",
                "provider_binding_id": "qwen35",
                "provider_model": "Qwen3.6-35B-A3B",
                "pilot_spec_id": "pilot.qwen35.pilot",
                "persona_id": "sniper",
                "input_source": "llm_completion",
                "source_overlay_id": "overlay.qwen35",
                "source_overlay_sha256": _HASHES["qwen35"],
                "source_roster_id": "roster.qwen35",
                "source_roster_sha256": "1" * 64,
                "unknown": True,
            }
        )


@pytest.mark.unit
def test_catalog_rejects_duplicate_options_and_invalid_selection() -> None:
    source = model_catalog_source_from_roster(
        overlay_id="overlay.qwen35",
        overlay_sha256=_HASHES["qwen35"],
        roster=_source_roster("qwen35"),
        model_identities=(
            ModelSOModelIdentityBinding(
                schema_version="1",
                kind="steel_onslaught.model_identity",
                model_identity_id="model_identity.qwen35",
                display_name="Qwen35",
                provider_binding_id="qwen35",
            ),
        ),
        provider_models={"qwen35": "Qwen3.6-35B-A3B"},
    )
    with pytest.raises(ValidationError, match="unique option_id"):
        build_model_catalog(
            catalog_id="catalog.duplicate",
            roster_id="roster.duplicate",
            sources=(source, source),
            seats=(
                ModelSOSeatLaunchPolicy(
                    side="red",
                    loadout_id="loadout.red",
                    allowed_option_ids=("player_option.qwen35.pilot",),
                ),
                ModelSOSeatLaunchPolicy(
                    side="blue",
                    loadout_id="loadout.blue",
                    allowed_option_ids=("player_option.qwen35.pilot",),
                ),
            ),
            default_chassis_ids=(
                "chassis.heavy.ironclad_mk1",
                "chassis.medium.hunter_mk1",
            ),
        )
    catalog = _catalog()
    with pytest.raises(ValueError, match="not allowed"):
        catalog.selection_provenance(side="red", option_id="player_option.unknown")


@pytest.mark.unit
def test_catalog_rejects_duplicate_default_roles_and_allows_explicit_mirror_mode() -> None:
    catalog = _catalog()
    duplicate_defaults = (
        catalog.seats[0].model_copy(update={"default_option_id": "player_option.glm.pilot"}),
        catalog.seats[1].model_copy(update={"default_option_id": "player_option.glm.pilot"}),
    )
    with pytest.raises(ValidationError, match="duplicate default option"):
        _revalidate_catalog(catalog, seats=duplicate_defaults)

    duplicate_roles = (
        catalog.seats[0].model_copy(update={"default_option_id": "player_option.qwen27.pilot"}),
        catalog.seats[1].model_copy(update={"default_option_id": "player_option.openrouter.pilot"}),
    )
    with pytest.raises(ValidationError, match="duplicate default role"):
        _revalidate_catalog(catalog, seats=duplicate_roles)

    mirror = _revalidate_catalog(
        catalog,
        seats=duplicate_defaults,
        mirror_match_mode=True,
    )
    pairing = mirror.pairing_provenance(
        red_option_id="player_option.glm.pilot",
        blue_option_id="player_option.glm.pilot",
    )
    assert pairing.mirror_match_mode is True
    assert pairing.red_role_id == pairing.blue_role_id == "opportunist"


@pytest.mark.unit
def test_catalog_rejects_duplicate_default_loadout_even_for_different_roles() -> None:
    catalog = _catalog()
    duplicate_loadouts = (
        catalog.seats[0],
        catalog.seats[1].model_copy(update={"loadout_id": catalog.seats[0].loadout_id}),
    )
    with pytest.raises(ValidationError, match="duplicate default loadout"):
        _revalidate_catalog(catalog, seats=duplicate_loadouts)
