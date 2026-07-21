"""Composition wires an overlay persona override into recorded prompt provenance.

This is the load-bearing determinism proof for the human-editable prompt: an
override declared in the overlay must reach the ``LlmDependencies`` prompt
provenance (which the runner writes into MATCH_STARTED), stamped as an operator
override and carrying the edited text.  Without this wiring an edited prompt
would run but never be recorded, and replay would silently diverge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.match.composition import build_llm_dependencies
from tests.overlay import complete_test_overlay

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "contracts_data"


def _overlay(
    root: Path, *, persona_overrides: list[dict[str, object]] | None = None
) -> dict[str, object]:
    raw = complete_test_overlay(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": root / "events.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": root / "leaderboard.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "storage_schema": "leaderboard_v1",
            },
            "learning_artifacts": {
                "kind": "filesystem_yaml",
                "evaluation_root": str(root / "evaluations"),
                "lineage_root": str(root / "lineage"),
            },
            "evaluation_storage": {
                "kind": "sqlite",
                "root": str(root / "evaluation_storage"),
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
                "leaderboard_schema": "leaderboard_v1",
            },
            "contracts": {
                "catalog_dir": str(_CONTRACTS),
                "pilot_registry_dir": str(_CONTRACTS / "pilots/fire_dense_qwen"),
                "arena_id": "open_field",
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
        },
        root,
    )
    if persona_overrides is not None:
        raw_llm = raw["llm"]
        assert isinstance(raw_llm, dict)
        raw = {**raw, "llm": {**raw_llm, "persona_overrides": persona_overrides}}
    return raw


def test_overlay_persona_override_reaches_recorded_prompt_provenance(tmp_path: Path) -> None:
    overlay = ModelSOApplicationOverlay.model_validate(
        _overlay(
            tmp_path,
            persona_overrides=[
                {
                    "persona_id": "sniper",
                    "doctrine": "Hold the ridge and never advance past cover.",
                    "temperature": 0.1,
                }
            ],
        )
    )
    with build_llm_dependencies(overlay) as llm:
        provenance = llm.prompt_provenance
        assert provenance is not None
        sniper = provenance.require("sniper")
        assert sniper.source == "operator_override"
        assert sniper.temperature == 0.1
        assert sniper.prompt_text.startswith("Hold the ridge and never advance past cover.")
        # A different, untouched persona stays contract-sourced.
        assert provenance.require("berserker").source == "contract"
        # The persona registry the pilots fly with carries the edited prompt.
        assert llm.persona_registry.require("sniper").system_prompt.startswith(
            "Hold the ridge and never advance past cover."
        )


def test_overlay_without_override_records_all_contract_prompts(tmp_path: Path) -> None:
    overlay = ModelSOApplicationOverlay.model_validate(_overlay(tmp_path))
    with build_llm_dependencies(overlay) as llm:
        provenance = llm.prompt_provenance
        assert provenance is not None
        assert provenance.prompts  # non-empty
        assert all(prompt.source == "contract" for prompt in provenance.prompts)
