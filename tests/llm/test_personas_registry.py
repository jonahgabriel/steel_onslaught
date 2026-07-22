"""Tests for explicit immutable persona contract registries."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.llm.personas import _JSON_INSTRUCTION as JSON_INSTRUCTION
from steel_onslaught.llm.personas import (
    Persona,
    PersonaRegistry,
    PersonaResolutionError,
    load_persona,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHIPPED_PERSONAS = _REPO_ROOT / "contracts_data/pilots/personas"


def _write_persona(
    directory: Path,
    filename: str,
    persona_id: str,
    *,
    temperature: str = "0.3",
) -> Path:
    path = directory / f"{filename}.yaml"
    path.write_text(
        f"persona_id: {persona_id}\n"
        f"display_name: Test {persona_id}\n"
        f"temperature: {temperature}\n"
        "doctrine: >-\n"
        "  First line of doctrine.\n"
        "  Second line.\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
def test_shipped_registry_is_loaded_only_from_explicit_path() -> None:
    registry = PersonaRegistry.load(_SHIPPED_PERSONAS)
    assert set(registry.as_mapping()) == {"berserker", "sniper", "opportunist", "card_opportunist"}
    berserker = registry.require("berserker")
    assert isinstance(berserker, Persona)
    assert berserker.display_name == "Berserker"
    assert berserker.temperature == 0.7
    assert "RECKLESS BERSERKER" in berserker.system_prompt
    assert berserker.system_prompt.endswith(JSON_INSTRUCTION)


@pytest.mark.unit
def test_shipped_sniper_persona_carries_strict_output_discipline() -> None:
    """The verbose sniper doctrine drives a reasoning gateway to leak
    chain-of-thought/`<think>` output, which is the sniper-specific
    provider_semantic_failure driver.  The shipped doctrine now forbids that at
    the source while KEEPING its behavioural identity (the loopback fixture and
    the long-range asymmetry both key on ``METHODICAL SNIPER``)."""
    registry = PersonaRegistry.load(_SHIPPED_PERSONAS)
    sniper_prompt = registry.require("sniper").system_prompt
    # Behavioural identity + fixture anchor preserved.
    assert "METHODICAL SNIPER" in sniper_prompt
    assert "STANDOFF" in sniper_prompt
    # Strict single-JSON output discipline added (mirrors card_opportunist).
    assert "<think>" in sniper_prompt
    assert "chain-of-thought" in sniper_prompt
    assert "ONLY the required JSON object" in sniper_prompt
    assert "code fences" in sniper_prompt
    # The fixed JSON output contract still terminates the prompt verbatim.
    assert sniper_prompt.endswith(JSON_INSTRUCTION)


@pytest.mark.unit
def test_registry_load_from_custom_dir_preserves_contract_values(tmp_path: Path) -> None:
    _write_persona(tmp_path, "alpha", "alpha")
    _write_persona(tmp_path, "beta", "beta")
    registry = PersonaRegistry.load(tmp_path)
    assert set(registry.as_mapping()) == {"alpha", "beta"}
    alpha = registry.require("alpha")
    assert alpha.temperature == 0.3
    assert alpha.system_prompt == "First line of doctrine. Second line." + JSON_INSTRUCTION


@pytest.mark.unit
def test_registry_mapping_is_immutable(tmp_path: Path) -> None:
    _write_persona(tmp_path, "alpha", "alpha")
    mapping = PersonaRegistry.load(tmp_path).as_mapping()
    with pytest.raises(TypeError):
        mapping["replacement"] = mapping["alpha"]  # type: ignore[index]


@pytest.mark.unit
def test_registry_rejects_unknown_persona(tmp_path: Path) -> None:
    _write_persona(tmp_path, "alpha", "alpha")
    with pytest.raises(PersonaResolutionError, match="unknown_persona"):
        PersonaRegistry.load(tmp_path).require("missing")


@pytest.mark.unit
def test_registry_rejects_missing_directory_and_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PersonaRegistry.load(tmp_path / "absent")
    with pytest.raises(PersonaResolutionError, match="must not be empty"):
        PersonaRegistry.load(tmp_path)


@pytest.mark.unit
def test_registry_load_rejects_duplicate_id(tmp_path: Path) -> None:
    _write_persona(tmp_path, "a", "dup")
    _write_persona(tmp_path, "b", "dup")
    with pytest.raises(PersonaResolutionError, match="duplicate_persona_id"):
        PersonaRegistry.load(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        "persona_id: x\ndisplay_name: X\ndoctrine: hi\nbogus_field: 1\n",
        "persona_id: x\ndisplay_name: X\ndoctrine: hi\n",
        'persona_id: x\ndisplay_name: X\ndoctrine: hi\ntemperature: "0.3"\n',
    ],
)
def test_load_persona_rejects_unknown_missing_and_coerced_fields(tmp_path: Path, body: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_persona(path)


@pytest.mark.unit
def test_shipped_berserker_persona_carries_dealt_hand_discipline() -> None:
    """The live RED-brawler abort driver: on a hand whose doctrine-preferred
    card has fewer copies than free registers (e.g. one ADVANCE + two VENT),
    the berserker spam-fills every register with its preferred card — a
    structurally perfect plan the multiset validator rejects, repeated
    near-verbatim on every reprompt until the budget exhausts as
    ``invalid_action_parameters``.  The shipped doctrine now subordinates
    aggression to the dealt hand while KEEPING the RECKLESS BERSERKER
    identity the registry test above anchors on."""

    registry = PersonaRegistry.load(_SHIPPED_PERSONAS)
    berserker_prompt = registry.require("berserker").system_prompt
    # Behavioural identity preserved.
    assert "RECKLESS BERSERKER" in berserker_prompt
    assert "CLOSE TO POINT-BLANK RANGE IMMEDIATELY" in berserker_prompt
    # Dealt-hand discipline added (the invalid_action_parameters fix).
    assert "FIGHT WITH THE HAND YOU ARE DEALT" in berserker_prompt
    assert "available_copies" in berserker_prompt
    assert "Never program more copies of a card than were dealt" in berserker_prompt
    # The fixed JSON output contract still terminates the prompt verbatim.
    assert berserker_prompt.endswith(JSON_INSTRUCTION)
