"""Tests for the persona contract registry (D6 — personas as YAML contracts).

The shipped personas now live in ``contracts_data/pilots/personas/*.yaml`` and
``llm/personas.py`` is a thin loader. These tests cover the contract load, the
preserved public API, and the byte-exact system-prompt assembly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.llm.personas import _JSON_INSTRUCTION as JSON_INSTRUCTION
from steel_onslaught.llm.personas import (
    BERSERKER,
    OPPORTUNIST,
    PERSONAS,
    SNIPER,
    Persona,
    PersonaRegistry,
    PersonaResolutionError,
    get_persona,
    load_persona,
)

# ---------------------------------------------------------------------------
# Public API preserved (llm/pilot.py + main.py depend on this shape)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_shipped_personas_present() -> None:
    assert set(PERSONAS) == {"berserker", "sniper", "opportunist"}
    for persona in (BERSERKER, SNIPER, OPPORTUNIST):
        assert isinstance(persona, Persona)


@pytest.mark.unit
def test_persona_singletons_have_expected_fields() -> None:
    assert BERSERKER.persona_id == "berserker"
    assert BERSERKER.display_name == "Berserker"
    assert SNIPER.display_name == "Sniper"
    assert OPPORTUNIST.display_name == "Opportunist"
    for persona in (BERSERKER, SNIPER, OPPORTUNIST):
        assert persona.temperature == 0.7
        assert persona.system_prompt.endswith(JSON_INSTRUCTION)


@pytest.mark.unit
def test_get_persona_roundtrip_and_unknown() -> None:
    assert get_persona("berserker") is BERSERKER
    with pytest.raises(KeyError):
        get_persona("nonexistent")


@pytest.mark.unit
def test_doctrine_keywords_survive_yaml_fold() -> None:
    assert "RECKLESS BERSERKER" in BERSERKER.system_prompt
    assert "overheat and risk rupture" in BERSERKER.system_prompt  # fold joins lines w/ spaces
    assert "MAINTAIN MAXIMUM STANDOFF RANGE" in SNIPER.system_prompt
    assert "confidence is high (>= 0.7)" in SNIPER.system_prompt
    assert "read the situation and exploit the largest opening" in OPPORTUNIST.system_prompt


# ---------------------------------------------------------------------------
# Registry.load conventions (mirrors PilotSpecRegistry.load)
# ---------------------------------------------------------------------------


def _write_persona(dir_path: Path, name: str, persona_id: str) -> Path:
    path = dir_path / f"{name}.yaml"
    path.write_text(
        f"persona_id: {persona_id}\n"
        f"display_name: Test {persona_id}\n"
        "temperature: 0.3\n"
        "doctrine: >-\n"
        "  First line of doctrine.\n"
        "  Second line.\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
def test_registry_load_from_custom_dir(tmp_path: Path) -> None:
    _write_persona(tmp_path, "alpha", "alpha")
    _write_persona(tmp_path, "beta", "beta")
    registry = PersonaRegistry.load(tmp_path)
    assert registry.get("alpha") is not None
    assert set(registry.as_dict()) == {"alpha", "beta"}
    alpha = registry.get("alpha")
    assert alpha is not None
    assert alpha.temperature == 0.3
    # Folded doctrine (lines joined by spaces) + shared JSON instruction.
    assert alpha.system_prompt == "First line of doctrine. Second line." + JSON_INSTRUCTION


@pytest.mark.unit
def test_registry_load_rejects_duplicate_id(tmp_path: Path) -> None:
    _write_persona(tmp_path, "a", "dup")
    _write_persona(tmp_path, "b", "dup")
    with pytest.raises(PersonaResolutionError, match="duplicate_persona_id"):
        PersonaRegistry.load(tmp_path)


@pytest.mark.unit
def test_load_persona_rejects_unknown_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        "persona_id: x\ndisplay_name: X\ndoctrine: hi\nbogus_field: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):  # extra=forbid
        load_persona(path)
