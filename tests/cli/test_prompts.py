"""Tests for `so prompts` and `so rules` — the code-free experiment CLIs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from steel_onslaught.cli.main import main
from steel_onslaught.match.composition import (
    load_application_overlay,
    project_effective_prompt_provenance,
)
from steel_onslaught.pilots.inspection import project_rule_catalog

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY = _REPO_ROOT / "contracts_data/overlays/standard_v1_qwen.yaml"


def test_prompts_show_json_matches_composition_projection() -> None:
    result = CliRunner().invoke(main, ["prompts", "show", "--overlay", str(_OVERLAY), "--json"])
    assert result.exit_code == 0, result.output
    emitted = json.loads(result.output)
    expected = project_effective_prompt_provenance(load_application_overlay(_OVERLAY))
    assert emitted == expected.model_dump(mode="json")


def test_rules_list_marks_the_installed_and_enabled_handlers() -> None:
    result = CliRunner().invoke(main, ["rules", "list", "--overlay", str(_OVERLAY)])
    assert result.exit_code == 0, result.output
    assert "ensure_movement_card" in result.output
    assert "close_the_gap" in result.output
    assert "prefer_attack_cards" in result.output


def test_rules_list_json_is_the_typed_catalog() -> None:
    result = CliRunner().invoke(main, ["rules", "list", "--overlay", str(_OVERLAY), "--json"])
    assert result.exit_code == 0, result.output
    emitted = json.loads(result.output)
    expected = project_rule_catalog(load_application_overlay(_OVERLAY))
    assert emitted == expected.model_dump(mode="json")


def test_prompts_set_writes_a_valid_overlay_that_records_the_edit(tmp_path: Path) -> None:
    doctrine = tmp_path / "doctrine.txt"
    doctrine.write_text("CHARGE and never disengage.", encoding="utf-8")
    out = tmp_path / "edited.yaml"

    # The base overlay binds the qwen35 personas; pick one it actually uses.
    base = project_effective_prompt_provenance(load_application_overlay(_OVERLAY))
    persona_id = base.prompts[0].persona_id

    result = CliRunner().invoke(
        main,
        [
            "prompts",
            "set",
            "--overlay",
            str(_OVERLAY),
            "--persona",
            persona_id,
            "--doctrine-file",
            str(doctrine),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()

    # The written overlay is loadable and its effective prompt is the edit,
    # marked as an operator override, so a match started from it records it.
    edited = project_effective_prompt_provenance(load_application_overlay(out))
    edited_prompt = edited.require(persona_id)
    assert edited_prompt.source == "operator_override"
    assert edited_prompt.prompt_text.startswith("CHARGE and never disengage.")


def test_rules_set_writes_an_enabled_selection(tmp_path: Path) -> None:
    out = tmp_path / "ruled.yaml"
    result = CliRunner().invoke(
        main,
        [
            "rules",
            "set",
            "--overlay",
            str(_OVERLAY),
            "--handler",
            "close_the_gap",
            "--handler",
            "ensure_movement_card",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    catalog = project_rule_catalog(load_application_overlay(out))
    assert catalog.enabled_handler_ids == ("close_the_gap", "ensure_movement_card")


def test_rules_set_fails_closed_on_unknown_handler(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "rules",
            "set",
            "--overlay",
            str(_OVERLAY),
            "--handler",
            "no_such_rule",
            "--out",
            str(tmp_path / "x.yaml"),
        ],
    )
    assert result.exit_code != 0
    assert "no_such_rule" in result.output
