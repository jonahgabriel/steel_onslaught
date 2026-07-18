"""Closed-schema tests for the sole Slice-1 application overlay."""

import json
from pathlib import Path
from shutil import copytree

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.export_frontend_bootstrap import export_frontend_bootstrap
from steel_onslaught.cli.serve import build_frontend_bootstrap
from steel_onslaught.commands.authority import canonical_overlay_sha256
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOFrontendBootstrap,
)
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
    validate_player_roster_against_overlay,
)
from steel_onslaught.match.composition import (
    build_llm_dependencies,
    load_application_overlay,
    load_match_contract_catalog,
    load_pilot_registry,
)
from tests.overlay import complete_test_overlay

_CONTRACTS_DATA = Path(__file__).parent.parent.parent / "contracts_data"


def _require_object_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _overlay_data(tmp_path: Path) -> dict[str, object]:
    return complete_test_overlay(
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


def _http_provider() -> dict[str, object]:
    return {
        "kind": "openai_compatible",
        "provider_id": "primary",
        "endpoint_url": "https://provider.test/v1/chat/completions",
        "model": "explicit-model",
        "secret_ref": {"kind": "opaque", "ref": "secret://llm/primary"},
        "timeout_seconds": 30.0,
        "max_tokens": None,
        "retry": {
            "max_attempts": 3,
            "initial_backoff_seconds": 0.25,
            "backoff_multiplier": 2.0,
        },
    }


def _model_identity(
    *, identity_id: str = "model_identity.primary", provider_id: str = "stub"
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "kind": "steel_onslaught.model_identity",
        "model_identity_id": identity_id,
        "display_name": "Primary local model",
        "provider_binding_id": provider_id,
    }


def _selector_overlay_and_roster(
    tmp_path: Path,
) -> tuple[ModelSOApplicationOverlay, ModelSOPlayerRosterBinding]:
    raw = _overlay_data(tmp_path)
    llm = dict(_require_object_dict(raw["llm"]))
    identities = (
        ("local", "Local Model"),
        ("openrouter", "OpenRouter Model"),
        ("glm", "GLM Model"),
        ("gemini", "Gemini Model"),
        ("unrostered", "Configured but unrostered"),
    )
    llm["providers"] = [
        {"kind": "stub", "provider_id": identity_id, "model": f"{identity_id}-fixture"}
        for identity_id, _display_name in identities
    ]
    llm["model_identities"] = [
        {
            "schema_version": "1",
            "kind": "steel_onslaught.model_identity",
            "model_identity_id": f"model_identity.{identity_id}",
            "display_name": display_name,
            "provider_binding_id": identity_id,
        }
        for identity_id, display_name in identities
    ]
    raw["llm"] = llm
    overlay = ModelSOApplicationOverlay.model_validate(raw)

    human = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser Operator",
        human_identity_id="human_identity.local_operator",
        pilot_spec_id="pilot.human.browser",
        input_source="browser_command",
    )
    models = tuple(
        ModelSOModelPlayerOptionBinding(
            kind="model",
            option_id=f"player_option.{identity_id}_model",
            display_name=display_name,
            model_identity_id=f"model_identity.{identity_id}",
            pilot_spec_id=f"pilot.llm.{identity_id}",
            persona_id="operator",
            input_source="llm_completion",
        )
        for identity_id, display_name in identities
        if identity_id != "unrostered"
    )
    all_ids = (human.option_id, *(option.option_id for option in models))
    roster = ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.player_selector",
        options=(human, *models),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.playable.red_light",
                allowed_option_ids=all_ids,
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.playable.blue_light",
                allowed_option_ids=tuple(option.option_id for option in models),
            ),
        ),
    )
    return overlay, roster


def _with_http_provider(tmp_path: Path) -> dict[str, object]:
    raw = _overlay_data(tmp_path)
    llm = dict(_require_object_dict(raw["llm"]))
    llm["providers"] = [_http_provider()]
    llm["secret_resolver"] = {"kind": "injected"}
    raw["llm"] = llm
    return raw


@pytest.mark.unit
def test_model_identity_registry_resolves_only_explicit_provider_bindings(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    llm = _require_object_dict(raw["llm"])
    llm["model_identities"] = (_model_identity(),)

    overlay = ModelSOApplicationOverlay.model_validate(raw)

    assert overlay.llm.model_identities[0].model_identity_id == "model_identity.primary"
    assert overlay.llm.model_identities[0].provider_binding_id == "stub"


@pytest.mark.unit
def test_model_identity_registry_rejects_unknown_and_duplicate_refs(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    llm = _require_object_dict(raw["llm"])
    llm["model_identities"] = (_model_identity(provider_id="missing"),)
    with pytest.raises(ValueError, match="unknown provider bindings"):
        ModelSOApplicationOverlay.model_validate(raw)

    llm["model_identities"] = (_model_identity(), _model_identity())
    with pytest.raises(ValueError, match="unique model_identity_id"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_model_identity_registry_is_required_even_when_explicitly_empty(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    llm = _require_object_dict(raw["llm"])
    assert llm["model_identities"] == []
    del llm["model_identities"]

    with pytest.raises(ValueError, match="model_identities"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_roster_model_option_resolves_overlay_identity_and_provider_chain(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    llm = _require_object_dict(raw["llm"])
    llm["model_identities"] = (_model_identity(),)
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    option = ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id="player_option.primary",
        display_name="Primary model",
        model_identity_id="model_identity.primary",
        pilot_spec_id="pilot.llm.primary",
        persona_id="berserker",
        input_source="llm_completion",
    )
    roster = ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.primary",
        options=(option,),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.playable.red_light",
                allowed_option_ids=(option.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.playable.blue_light",
                allowed_option_ids=(option.option_id,),
            ),
        ),
    )

    validate_player_roster_against_overlay(roster=roster, overlay=overlay)

    unknown = roster.model_copy(
        update={
            "options": (option.model_copy(update={"model_identity_id": "model_identity.unknown"}),)
        }
    )
    with pytest.raises(ValueError, match="unknown model identities"):
        validate_player_roster_against_overlay(roster=unknown, overlay=overlay)


class _NamedGraphResolver:
    def resolve(self, reference: object) -> str:
        return "fixture-secret"


@pytest.mark.unit
def test_full_named_provider_graph_resolves_every_shipped_llm_spec(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    llm = dict(_require_object_dict(raw["llm"]))
    llm["providers"] = [
        {"kind": "stub", "provider_id": "stub", "model": "fixture-stub"},
        *[
            {
                "kind": "openai_compatible",
                "provider_id": provider_id,
                "endpoint_url": f"https://{provider_id}.fixture.invalid/v1/chat/completions",
                "model": model,
                "secret_ref": {"kind": "opaque", "ref": f"secret://llm/{provider_id}"},
                "timeout_seconds": 30.0,
                "max_tokens": None,
                "retry": {
                    "max_attempts": 1,
                    "initial_backoff_seconds": 0.0,
                    "backoff_multiplier": 1.0,
                },
            }
            for provider_id, model in (
                ("qwen35", "Qwen3.6-35B-A3B"),
                ("qwen27", "Qwen3.6-27B-MTP-IQ4_XS.gguf"),
                ("deepseek", "deepseek-v4-pro"),
                ("glm-5.2", "glm-5.2"),
            )
        ],
    ]
    llm["secret_resolver"] = {"kind": "injected"}
    raw["llm"] = llm
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    dependencies = build_llm_dependencies(
        overlay,
        secret_resolver=_NamedGraphResolver(),
    )
    try:
        registry = load_pilot_registry(_CONTRACTS_DATA / "pilots")
        shipped = {
            spec.id: spec for spec in registry.as_mapping().values() if spec.archetype == "llm"
        }
        assert {spec.parameters.provider for spec in shipped.values()} == {  # type: ignore[union-attr]
            "stub",
            "qwen35",
            "qwen27",
            "deepseek",
            "glm-5.2",
        }
        for spec in shipped.values():
            dependencies.pilot_factory.from_spec(spec)
    finally:
        dependencies.close()


@pytest.mark.unit
def test_overlay_is_complete_and_frozen(tmp_path: Path) -> None:
    overlay = ModelSOApplicationOverlay.model_validate(_overlay_data(tmp_path))

    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    with pytest.raises(ValueError, match="frozen"):
        overlay.event_ledger.path = tmp_path / "other.sqlite3"


@pytest.mark.unit
def test_overlay_rejects_unknown_nested_policy(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    assert isinstance(raw["event_ledger"], dict)
    ledger = dict(raw["event_ledger"])
    ledger["implicit_fallback"] = True
    raw["event_ledger"] = ledger

    with pytest.raises(ValueError, match="implicit_fallback"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_overlay_selected_catalog_rejects_unknown_nested_boiler_compatibility(
    tmp_path: Path,
) -> None:
    catalog_dir = tmp_path / "catalog"
    copytree(_CONTRACTS_DATA, catalog_dir)
    boiler_path = catalog_dir / "boilers" / "compact_v1.yaml"
    boiler = yaml.safe_load(boiler_path.read_text(encoding="utf-8"))
    assert isinstance(boiler, dict)
    compatibility = boiler["compatibility"]
    assert isinstance(compatibility, dict)
    compatibility["implicit_compatibility_fallback"] = True
    boiler_path.write_text(yaml.safe_dump(boiler), encoding="utf-8")

    raw_overlay = _overlay_data(tmp_path)
    overlay_path = tmp_path / "application.yaml"
    serialized = ModelSOApplicationOverlay.model_validate(raw_overlay).model_dump(mode="json")
    overlay_path.write_text(yaml.safe_dump(serialized), encoding="utf-8")
    overlay = load_application_overlay(overlay_path)

    with pytest.raises(ValueError, match="implicit_compatibility_fallback"):
        load_match_contract_catalog(overlay.contracts.catalog_dir)


@pytest.mark.unit
def test_overlay_rejects_unsupported_adapter_kind(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    raw["bus"] = {"kind": "redis"}

    with pytest.raises(ValueError, match="in_process"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "binding",
    [
        "bus",
        "event_ledger",
        "leaderboard",
        "learning_artifacts",
        "evaluation_storage",
        "contracts",
        "llm",
        "clock",
        "identity",
        "frontend_transport",
    ],
)
def test_overlay_requires_every_binding(tmp_path: Path, binding: str) -> None:
    raw = _overlay_data(tmp_path)
    del raw[binding]
    with pytest.raises(ValueError, match=binding):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("binding", "unsupported"),
    [
        ("bus", {"kind": "redis"}),
        ("event_ledger", {"kind": "postgres"}),
        ("leaderboard", {"kind": "memory"}),
        ("learning_artifacts", {"kind": "s3"}),
        ("evaluation_storage", {"kind": "postgres"}),
        ("clock", {"kind": "local_time"}),
        ("identity", {"kind": "random_int"}),
        ("frontend_transport", {"kind": "server_sent_events"}),
    ],
)
def test_overlay_rejects_every_unsupported_binding_kind(
    tmp_path: Path,
    binding: str,
    unsupported: dict[str, str],
) -> None:
    raw = _overlay_data(tmp_path)
    raw[binding] = unsupported
    with pytest.raises(ValueError, match="kind"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_overlay_relative_paths_resolve_from_overlay_directory(tmp_path: Path) -> None:
    raw = _overlay_data(Path("."))
    overlay_path = tmp_path / "application.yaml"
    serialized = ModelSOApplicationOverlay.model_validate(raw).model_dump(mode="json")
    overlay_path.write_text(yaml.safe_dump(serialized), encoding="utf-8")

    overlay = load_application_overlay(overlay_path)

    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.contracts.catalog_dir == tmp_path / "catalog"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765/events",
        "ws://user@127.0.0.1:8765/events",
        "ws://127.0.0.1:8765",
        "ws://127.0.0.1:8765/events?match=ambient",
        "ws://127.0.0.1:8765/events#fragment",
    ],
)
def test_frontend_transport_rejects_non_closed_websocket_authority(
    tmp_path: Path, url: str
) -> None:
    raw = _overlay_data(tmp_path)
    frontend = dict(_require_object_dict(raw["frontend_transport"]))
    frontend["websocket_url"] = url
    raw["frontend_transport"] = frontend

    with pytest.raises(ValueError, match="websocket_url"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_frontend_transport_is_frozen_and_rejects_unknown_policy(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    frontend = dict(_require_object_dict(raw["frontend_transport"]))
    frontend["ambient_fallback"] = True
    raw["frontend_transport"] = frontend
    with pytest.raises(ValueError, match="ambient_fallback"):
        ModelSOApplicationOverlay.model_validate(raw)

    overlay = ModelSOApplicationOverlay.model_validate(_overlay_data(tmp_path))
    with pytest.raises(ValueError, match="frozen"):
        overlay.frontend_transport.milliseconds_per_tick = 1000


@pytest.mark.unit
def test_public_frontend_bootstrap_exposes_no_storage_or_secret_authority(tmp_path: Path) -> None:
    overlay = ModelSOApplicationOverlay.model_validate(_overlay_data(tmp_path))
    first = build_frontend_bootstrap(overlay)
    second = build_frontend_bootstrap(overlay)

    assert first == second
    assert len(first.overlay_sha256) == 64
    serialized = first.model_dump_json()
    assert str(tmp_path) not in serialized
    assert "event_ledger" not in serialized
    assert "secret" not in serialized
    assert first.frontend_transport == overlay.frontend_transport
    assert first.player_roster is None


@pytest.mark.unit
def test_frontend_bootstrap_reuses_command_overlay_digest_for_non_ascii_model_name(
    tmp_path: Path,
) -> None:
    raw = _overlay_data(tmp_path)
    llm = dict(_require_object_dict(raw["llm"]))
    llm["providers"] = [{"kind": "stub", "provider_id": "unicode", "model": "fixture"}]
    identity = _model_identity(identity_id="model_identity.unicode", provider_id="unicode")
    identity["display_name"] = "Pilote Étoile 火"
    llm["model_identities"] = [identity]
    raw["llm"] = llm
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    expected_digest = canonical_overlay_sha256(overlay)

    bootstrap = build_frontend_bootstrap(overlay)
    overlay_path = tmp_path / "application.json"
    output_path = tmp_path / "frontend_bootstrap.json"
    overlay_path.write_text(json.dumps(overlay.model_dump(mode="json")), encoding="utf-8")
    exported = export_frontend_bootstrap(overlay_path, output_path)

    assert bootstrap.overlay_sha256 == expected_digest
    assert exported.overlay_sha256 == expected_digest
    assert json.loads(output_path.read_text(encoding="utf-8"))["overlay_sha256"] == expected_digest


@pytest.mark.unit
def test_public_frontend_bootstrap_fixture_is_python_typescript_contract_parity() -> None:
    fixture = (
        _CONTRACTS_DATA.parent / "frontend/src/__tests__/fixtures/bootstrap/frontend_bootstrap.json"
    )
    fixture_json = fixture.read_text(encoding="utf-8")
    raw = json.loads(fixture_json)
    bootstrap = ModelSOFrontendBootstrap.model_validate_json(fixture_json)

    assert bootstrap.model_dump(mode="json") == raw


@pytest.mark.unit
def test_generated_vite_bootstrap_is_exact_overlay_projection(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    frontend = dict(_require_object_dict(raw["frontend_transport"]))
    frontend["websocket_url"] = "ws://binding.example.test:9876/closed/events"
    raw["frontend_transport"] = frontend
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    overlay_path = tmp_path / "application.json"
    overlay_path.write_text(json.dumps(overlay.model_dump(mode="json")), encoding="utf-8")
    output_path = tmp_path / ".steel-onslaught-bootstrap.generated.json"

    generated = export_frontend_bootstrap(overlay_path, output_path)

    assert generated == build_frontend_bootstrap(overlay)
    assert json.loads(output_path.read_text(encoding="utf-8")) == generated.model_dump(mode="json")
    assert output_path.read_bytes().endswith(b"\n")


@pytest.mark.unit
def test_explicit_roster_export_is_derived_safe_and_does_not_discover_models(
    tmp_path: Path,
) -> None:
    overlay, roster = _selector_overlay_and_roster(tmp_path)
    overlay_path = tmp_path / "application.json"
    roster_path = tmp_path / "player_roster.json"
    output_path = tmp_path / "frontend_bootstrap.json"
    overlay_path.write_text(json.dumps(overlay.model_dump(mode="json")), encoding="utf-8")
    roster_path.write_text(json.dumps(roster.model_dump(mode="json")), encoding="utf-8")

    bootstrap = export_frontend_bootstrap(
        overlay_path,
        output_path,
        roster_path=roster_path,
    )

    projection = bootstrap.player_roster
    assert projection == roster.public_projection()
    assert projection is not None
    assert projection.roster_sha256 == roster.canonical_sha256()
    assert [option.kind for option in projection.options] == [
        "human",
        "model",
        "model",
        "model",
        "model",
    ]
    assert [
        option.model_identity_id for option in projection.options if option.kind == "model"
    ] == [
        "model_identity.local",
        "model_identity.openrouter",
        "model_identity.glm",
        "model_identity.gemini",
    ]
    serialized = bootstrap.model_dump(mode="json")

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                nested_key for nested in value.values() for nested_key in keys(nested)
            }
        if isinstance(value, list):
            return {nested_key for nested in value for nested_key in keys(nested)}
        return set()

    assert keys(serialized).isdisjoint(
        {
            "provider_binding_id",
            "endpoint_url",
            "secret_ref",
            "key",
            "token",
            "header",
            "resolver",
            "path",
        }
    )
    document = output_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in document
    assert "model_identity.unrostered" not in document
    assert "provider_binding_id" not in document
    assert "secret_ref" not in document


@pytest.mark.unit
def test_replay_bootstrap_has_no_browser_command_capability(tmp_path: Path) -> None:
    """Replay remains receive-only until an explicit gateway binding is composed."""

    overlay = ModelSOApplicationOverlay.model_validate(_overlay_data(tmp_path))

    bootstrap = build_frontend_bootstrap(overlay)

    assert bootstrap.player_roster is None
    assert bootstrap.command_gateway is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "websocket_url",
    [
        "http://127.0.0.1:8765/commands",
        "ws://user@127.0.0.1:8765/commands",
        "ws://127.0.0.1:8765",
        "ws://127.0.0.1:8765/commands?token=ambient",
        "ws://127.0.0.1:8765/commands#fragment",
        "ws://example.test:8765/commands",
    ],
)
def test_browser_command_gateway_binding_is_closed_loopback_and_secret_free(
    websocket_url: str,
) -> None:
    from steel_onslaught.contracts.application import ModelSOFrontendCommandGatewayBinding

    with pytest.raises(ValueError, match="websocket_url"):
        ModelSOFrontendCommandGatewayBinding(
            kind="websocket",
            contract="steel_onslaught.browser_command_gateway.v1",
            websocket_url=websocket_url,
            authority_scope="injected_process_session",
        )

    with pytest.raises(ValueError, match="ambient_fallback"):
        ModelSOFrontendCommandGatewayBinding.model_validate(
            {
                "kind": "websocket",
                "contract": "steel_onslaught.browser_command_gateway.v1",
                "websocket_url": "ws://127.0.0.1:8765/commands",
                "authority_scope": "injected_process_session",
                "ambient_fallback": True,
            }
        )


@pytest.mark.unit
def test_live_bootstrap_requires_explicit_roster_and_gateway_and_exposes_no_authority(
    tmp_path: Path,
) -> None:
    from steel_onslaught.contracts.application import ModelSOFrontendCommandGatewayBinding

    overlay, roster = _selector_overlay_and_roster(tmp_path)
    gateway = ModelSOFrontendCommandGatewayBinding(
        kind="websocket",
        contract="steel_onslaught.browser_command_gateway.v1",
        websocket_url="ws://127.0.0.1:8765/commands",
        authority_scope="injected_process_session",
    )

    bootstrap = build_frontend_bootstrap(
        overlay,
        roster=roster,
        command_gateway=gateway,
    )

    assert bootstrap.player_roster == roster.public_projection()
    assert bootstrap.command_gateway == gateway
    document = bootstrap.model_dump_json()
    for forbidden in (
        "principal_id",
        "session_id",
        "human_identity_id",
        "provider_binding_id",
        "endpoint_url",
        "secret_ref",
        "pilot_spec_id",
        "persona_id",
        "loadout_id",
        "token",
        "authorization",
    ):
        assert forbidden not in document.lower()


@pytest.mark.unit
def test_roster_export_rejects_unconfigured_model_identity(tmp_path: Path) -> None:
    overlay, roster = _selector_overlay_and_roster(tmp_path)
    model = roster.options[1]
    assert isinstance(model, ModelSOModelPlayerOptionBinding)
    forged = roster.model_copy(
        update={
            "options": (
                roster.options[0],
                model.model_copy(update={"model_identity_id": "model_identity.unconfigured"}),
                *roster.options[2:],
            )
        }
    )
    overlay_path = tmp_path / "application.json"
    roster_path = tmp_path / "player_roster.json"
    overlay_path.write_text(json.dumps(overlay.model_dump(mode="json")), encoding="utf-8")
    roster_path.write_text(json.dumps(forged.model_dump(mode="json")), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown model identities"):
        export_frontend_bootstrap(
            overlay_path,
            tmp_path / "frontend_bootstrap.json",
            roster_path=roster_path,
        )


@pytest.mark.unit
def test_frontend_bootstrap_export_has_no_endpoint_or_storage_fallback() -> None:
    source = (_CONTRACTS_DATA.parent / "scripts/export_frontend_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "SQLite" not in source
    assert 'add_argument("--ledger"' not in source
    assert "8765" not in source
    assert "load_application_overlay" in source


@pytest.mark.unit
@pytest.mark.parametrize(
    "field",
    [
        "provider_id",
        "endpoint_url",
        "model",
        "secret_ref",
        "timeout_seconds",
        "max_tokens",
        "retry",
    ],
)
def test_http_provider_requires_every_historical_field(tmp_path: Path, field: str) -> None:
    raw = _with_http_provider(tmp_path)
    llm = raw["llm"]
    assert isinstance(llm, dict)
    provider = dict(llm["providers"][0])
    del provider[field]
    llm["providers"] = [provider]
    with pytest.raises(ValueError, match=field):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_http_provider_accepts_explicit_nullable_max_tokens(tmp_path: Path) -> None:
    overlay = ModelSOApplicationOverlay.model_validate(_with_http_provider(tmp_path))
    provider = overlay.llm.providers[0]
    assert provider.max_tokens is None  # type: ignore[union-attr]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("max_tokens",), "128"),
        (("timeout_seconds",), "30.0"),
        (("retry", "max_attempts"), "3"),
        (("retry", "initial_backoff_seconds"), float("inf")),
    ],
)
def test_http_provider_rejects_coercion_and_non_finite_values(
    tmp_path: Path, path: tuple[str, ...], value: object
) -> None:
    raw = _with_http_provider(tmp_path)
    llm = raw["llm"]
    assert isinstance(llm, dict)
    provider = dict(llm["providers"][0])
    if len(path) == 1:
        provider[path[0]] = value
    else:
        nested = dict(provider[path[0]])
        nested[path[1]] = value
        provider[path[0]] = nested
    llm["providers"] = [provider]
    with pytest.raises(ValueError):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "endpoint",
    [
        "provider.test/chat",
        "ftp://provider.test/chat",
        "https://user@provider.test/chat",
        "https://provider.test/chat?q=secret",
    ],
)
def test_http_provider_rejects_non_complete_or_credential_bearing_endpoint(
    tmp_path: Path, endpoint: str
) -> None:
    raw = _with_http_provider(tmp_path)
    llm = raw["llm"]
    assert isinstance(llm, dict)
    provider = dict(llm["providers"][0])
    provider["endpoint_url"] = endpoint
    llm["providers"] = [provider]
    with pytest.raises(ValueError, match="endpoint_url"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_llm_registry_rejects_unknown_kind_unknown_field_and_duplicate_id(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    llm = raw["llm"]
    assert isinstance(llm, dict)
    llm["providers"] = [{"kind": "implicit", "provider_id": "x", "model": "x"}]
    with pytest.raises(ValueError, match="kind"):
        ModelSOApplicationOverlay.model_validate(raw)

    llm["providers"] = [
        {"kind": "stub", "provider_id": "same", "model": "a", "fallback": True},
    ]
    with pytest.raises(ValueError, match="fallback"):
        ModelSOApplicationOverlay.model_validate(raw)

    llm["providers"] = [
        {"kind": "stub", "provider_id": "same", "model": "a"},
        {"kind": "stub", "provider_id": "same", "model": "b"},
    ]
    with pytest.raises(ValueError, match="unique provider_id"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_secret_bearing_provider_requires_injected_resolver_and_bounded_ref(tmp_path: Path) -> None:
    raw = _with_http_provider(tmp_path)
    llm = raw["llm"]
    assert isinstance(llm, dict)
    llm["secret_resolver"] = {"kind": "none"}
    with pytest.raises(ValueError, match="secret-bearing"):
        ModelSOApplicationOverlay.model_validate(raw)

    llm["secret_resolver"] = {"kind": "injected"}
    provider = dict(llm["providers"][0])
    provider["secret_ref"] = {"kind": "opaque", "ref": "sk-raw-secret"}
    llm["providers"] = [provider]
    with pytest.raises(ValueError, match="secret_ref"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_card_catalog_is_an_explicit_typed_overlay_binding(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    contracts = _require_object_dict(raw["contracts"])
    contracts["card_catalog"] = {
        "kind": "filesystem_yaml",
        "cards_dir": "card_contracts",
        "decks_dir": "deck_contracts",
    }
    overlay_path = tmp_path / "overlay.yaml"
    overlay_path.write_text(
        yaml.safe_dump(json.loads(json.dumps(raw, default=str))),
        encoding="utf-8",
    )

    overlay = load_application_overlay(overlay_path)
    assert overlay.contracts.card_catalog is not None
    assert overlay.contracts.card_catalog.cards_dir == tmp_path / "card_contracts"
    assert overlay.contracts.card_catalog.decks_dir == tmp_path / "deck_contracts"

    bad = dict(_require_object_dict(contracts["card_catalog"]))
    bad["default_deck_id"] = "deck.standard"
    contracts["card_catalog"] = bad
    with pytest.raises(ValueError, match="default_deck_id"):
        ModelSOApplicationOverlay.model_validate(raw)
