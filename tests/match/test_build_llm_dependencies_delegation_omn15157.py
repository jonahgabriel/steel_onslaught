"""``build_llm_dependencies`` golden-stability + delegation wiring (OMN-15157/OMN-15159).

Two things are proven here, per the task's explicit bar:

1. **Golden-stability**: with no ``onex_delegation`` provider binding
   configured, ``build_llm_dependencies`` behaves byte-identically to before
   this ticket -- every resolved client is exactly the same concrete type it
   was previously (``StubLlmClient`` for ``stub`` bindings), and no
   ``LlmBusDelegationClient`` is ever constructed.
2. **Wiring**: when an ``onex_delegation`` binding IS present, exactly one
   ``isinstance`` branch resolves it to ``LlmBusDelegationClient`` and every
   OTHER provider in the same overlay is completely unaffected.

The live call itself is out of scope here (OMN-15170); these tests only
prove `build_llm_dependencies` selects the right client TYPE per binding
kind, using the real (non-network) construction path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.llm.client_delegation import LlmBusDelegationClient
from steel_onslaught.llm.stub import StubLlmClient
from steel_onslaught.match.composition import build_llm_dependencies
from tests.overlay import complete_test_overlay

pytestmark = pytest.mark.unit


def _require_object_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _base_overlay_raw(tmp_path: Path) -> dict[str, object]:
    pilot_registry_dir = tmp_path / "pilots"
    pilot_registry_dir.mkdir(exist_ok=True)
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
                "pilot_registry_dir": pilot_registry_dir,
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
        },
        tmp_path,
    )


def test_golden_stability_no_delegation_binding_configured(tmp_path: Path) -> None:
    """With no delegation binding, every client resolves exactly as before."""
    from steel_onslaught.contracts.application import ModelSOApplicationOverlay

    overlay = ModelSOApplicationOverlay.model_validate(_base_overlay_raw(tmp_path))
    dependencies = build_llm_dependencies(overlay)
    try:
        for provider in overlay.llm.providers:
            client = dependencies.client_factory.client_for(provider.provider_id)
            assert isinstance(client, StubLlmClient)
            assert not isinstance(client, LlmBusDelegationClient)
    finally:
        dependencies.close()


def test_delegation_binding_resolves_to_delegation_client_others_unaffected(
    tmp_path: Path,
) -> None:
    """Adding one onex_delegation provider wires exactly one delegation client;
    every pre-existing stub provider in the same overlay is untouched."""
    from steel_onslaught.contracts.application import ModelSOApplicationOverlay

    raw = _base_overlay_raw(tmp_path)
    llm = _require_object_dict(raw["llm"])
    llm_providers = llm["providers"]
    assert isinstance(llm_providers, list)
    providers: list[object] = list(llm_providers)
    providers.append(
        {
            "kind": "onex_delegation",
            "provider_id": "onex-local-coder-mlx",
            "backend_id": "local-coder-mlx",
            "task_type": "agent_delegation",
            "source": "external-client",
            "model": "mlx-community/Qwen3.6-35B-A3B-8bit",
            "timeout_seconds": 300.0,
            "omnibase_infra_path": tmp_path / "omnibase_infra",
            "state_root": tmp_path / "delegation_state",
        }
    )
    llm["providers"] = providers
    raw["llm"] = llm
    overlay = ModelSOApplicationOverlay.model_validate(raw)

    dependencies = build_llm_dependencies(overlay)
    try:
        delegation_client = dependencies.client_factory.client_for("onex-local-coder-mlx")
        assert isinstance(delegation_client, LlmBusDelegationClient)

        # Every pre-existing stub provider is completely unaffected by the
        # new binding kind being present in the same overlay.
        for provider in overlay.llm.providers:
            if provider.provider_id == "onex-local-coder-mlx":
                continue
            client = dependencies.client_factory.client_for(provider.provider_id)
            assert isinstance(client, StubLlmClient)
    finally:
        dependencies.close()
