"""Explicit, immutable persona contracts loaded only by the composition root."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr

_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object, no prose, of shape:\n"
    '{"action": "<one of remain|move|fire_weapon|switch_mode|vent>", '
    '"action_params": {"direction": "toward_enemy|defensive"} or '
    '{"weapon_id": "..."} or {"target_mode": "assault|evasion|recon"} or {}, '
    '"confidence": 0.0-1.0, '
    '"rationale": "<one short sentence explaining your reasoning>"}'
)


class PersonaResolutionError(ValueError):
    """An explicitly selected persona registry is invalid or incomplete."""


@dataclass(frozen=True)
class Persona:
    persona_id: str
    display_name: str
    system_prompt: str
    temperature: float


class ModelSOPersonaContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    persona_id: StrictStr = Field(min_length=1)
    display_name: StrictStr = Field(min_length=1)
    doctrine: StrictStr = Field(min_length=1)
    temperature: StrictFloat = Field(ge=0.0, le=2.0)


def load_persona(path: Path) -> Persona:
    contract = ModelSOPersonaContract.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return Persona(
        persona_id=contract.persona_id,
        display_name=contract.display_name,
        system_prompt=contract.doctrine + _JSON_INSTRUCTION,
        temperature=contract.temperature,
    )


class PersonaRegistry:
    """Immutable registry with no package-relative or import-time loading."""

    def __init__(self, personas: Mapping[str, Persona]) -> None:
        if not personas:
            raise PersonaResolutionError("persona registry must not be empty")
        self._personas = MappingProxyType(dict(personas))

    @classmethod
    def load(cls, personas_dir: Path) -> PersonaRegistry:
        if not personas_dir.is_dir():
            raise FileNotFoundError(
                f"required persona contract directory does not exist: {personas_dir}"
            )
        personas: dict[str, Persona] = {}
        for path in sorted(personas_dir.glob("*.yaml")):
            persona = load_persona(path)
            if persona.persona_id in personas:
                raise PersonaResolutionError(
                    f"duplicate_persona_id: {persona.persona_id!r} declared more "
                    f"than once under {personas_dir}"
                )
            personas[persona.persona_id] = persona
        return cls(personas)

    def require(self, persona_id: str) -> Persona:
        try:
            return self._personas[persona_id]
        except KeyError as exc:
            raise PersonaResolutionError(f"unknown_persona: {persona_id!r}") from exc

    def as_mapping(self) -> Mapping[str, Persona]:
        return self._personas


__all__ = [
    "ModelSOPersonaContract",
    "Persona",
    "PersonaRegistry",
    "PersonaResolutionError",
    "load_persona",
]
