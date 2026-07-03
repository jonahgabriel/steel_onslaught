"""LLM pilot personas — the behavioral asymmetry source.

Each persona is a system prompt that shapes the LLM's playstyle, creating
genuinely different decisions from the same observation. Two distinct personas
(berserker vs sniper) break the draw-prone mirror that starved the learning
loop of signal, and make LLM-vs-LLM matches emergent and interesting.

Personas are **contract data** now, not code: each lives in
``contracts_data/pilots/personas/*.yaml`` (``persona_id``, ``display_name``,
``temperature``, and the ``doctrine`` body). This module is a thin loader — it
reads + validates those YAMLs (via :class:`PersonaRegistry`, mirroring
``PilotSpecRegistry.load``), appends the shared JSON output instruction, and
exposes the same public API (``Persona`` shape, ``PERSONAS`` map,
``get_persona``, and the ``BERSERKER``/``SNIPER``/``OPPORTUNIST`` singletons)
so ``llm/pilot.py`` and the stub keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object, no prose, of shape:\n"
    '{"action": "<one of remain|move|fire_weapon|switch_mode|vent>", '
    '"action_params": {"direction": "toward_enemy|defensive"} or '
    '{"weapon_id": "..."} or {"target_mode": "assault|evasion|recon"} or {}, '
    '"confidence": 0.0-1.0, '
    '"rationale": "<one short sentence explaining your reasoning>"}'
)

DEFAULT_PERSONAS_DIR = (
    Path(__file__).parent.parent.parent.parent / "contracts_data" / "pilots" / "personas"
)


class PersonaResolutionError(ValueError):
    """A persona contract could not be loaded (missing dir / duplicate id)."""


@dataclass(frozen=True)
class Persona:
    """One LLM pilot persona: a system prompt + default completion opts."""

    persona_id: str
    display_name: str
    system_prompt: str
    temperature: float = 0.7


class _PersonaContract(BaseModel):
    """The on-disk persona contract row (frozen, closed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona_id: str
    display_name: str
    doctrine: str
    temperature: float = 0.7


def load_persona(path: Path) -> Persona:
    """Load + validate one persona contract YAML into a :class:`Persona`.

    The persona's ``system_prompt`` is the contract ``doctrine`` with the shared
    JSON output instruction appended (so every persona speaks the same schema).
    """
    contract = _PersonaContract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return Persona(
        persona_id=contract.persona_id,
        display_name=contract.display_name,
        system_prompt=contract.doctrine + _JSON_INSTRUCTION,
        temperature=contract.temperature,
    )


class PersonaRegistry:
    """Index of shipped persona contracts, keyed by ``persona_id``."""

    def __init__(self, personas: dict[str, Persona]) -> None:
        self._personas = dict(personas)

    @classmethod
    def load(cls, personas_dir: Path | None = None) -> PersonaRegistry:
        """Scan *personas_dir* (default ``contracts_data/pilots/personas/``)."""
        data_dir = personas_dir if personas_dir is not None else DEFAULT_PERSONAS_DIR
        personas: dict[str, Persona] = {}
        for path in sorted(data_dir.glob("*.yaml")):
            persona = load_persona(path)
            if persona.persona_id in personas:
                raise PersonaResolutionError(
                    f"duplicate_persona_id: {persona.persona_id!r} declared more "
                    f"than once under {data_dir}"
                )
            personas[persona.persona_id] = persona
        return cls(personas)

    def get(self, persona_id: str) -> Persona | None:
        """Return the registered persona for *persona_id*, or None."""
        return self._personas.get(persona_id)

    def as_dict(self) -> dict[str, Persona]:
        """Return a copy of the ``persona_id`` -> :class:`Persona` map."""
        return dict(self._personas)


# Load the shipped personas once at import (fail-fast if a contract is bad).
_REGISTRY = PersonaRegistry.load()
PERSONAS: dict[str, Persona] = _REGISTRY.as_dict()

BERSERKER = PERSONAS["berserker"]
SNIPER = PERSONAS["sniper"]
OPPORTUNIST = PERSONAS["opportunist"]


def get_persona(persona_id: str) -> Persona:
    """Look up a persona by id. Raises ``KeyError`` on unknown id (fail-fast)."""
    return PERSONAS[persona_id]


__all__ = [
    "BERSERKER",
    "OPPORTUNIST",
    "PERSONAS",
    "SNIPER",
    "Persona",
    "PersonaRegistry",
    "PersonaResolutionError",
    "get_persona",
    "load_persona",
]
