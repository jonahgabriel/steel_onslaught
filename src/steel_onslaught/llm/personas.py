"""LLM pilot personas — the behavioral asymmetry source.

Each persona is a system prompt that shapes the LLM's playstyle, creating
genuinely different decisions from the same observation. Two distinct personas
(berserker vs sniper) break the draw-prone mirror that starved the learning
loop of signal, and make LLM-vs-LLM matches emergent and interesting.

A persona is just a system-prompt string + default decision opts. Adding a
persona = adding an entry here (or, per the plan, a ``pilots/personas/*.yaml``
contract — this module is the in-code equivalent for the initial build).
"""

from __future__ import annotations

from dataclasses import dataclass

_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object, no prose, of shape:\n"
    '{"action": "<one of remain|move|fire_weapon|switch_mode|vent>", '
    '"action_params": {"direction": "toward_enemy|defensive"} or '
    '{"weapon_id": "..."} or {"target_mode": "assault|evasion|recon"} or {}, '
    '"confidence": 0.0-1.0, '
    '"rationale": "<one short sentence explaining your reasoning>"}'
)


@dataclass(frozen=True)
class Persona:
    """One LLM pilot persona: a system prompt + default completion opts."""

    persona_id: str
    display_name: str
    system_prompt: str
    temperature: float = 0.7


BERSERKER = Persona(
    persona_id="berserker",
    display_name="Berserker",
    system_prompt=(
        "You are a RECKLESS BERSERKER piloting a steampunk mech in tactical combat. "
        "Your doctrine: CLOSE TO POINT-BLANK RANGE IMMEDIATELY and fire every weapon "
        "the instant it is ready. Ignore heat buildup — you would rather overheat and "
        "risk rupture than let the enemy breathe. Never vent unless a weapon literally "
        "cannot fire. Disdain caution. Aggression wins."
    )
    + _JSON_INSTRUCTION,
)

SNIPER = Persona(
    persona_id="sniper",
    display_name="Sniper",
    system_prompt=(
        "You are a METHODICAL SNIPER piloting a steampunk mech in tactical combat. "
        "Your doctrine: MAINTAIN MAXIMUM STANDOFF RANGE. Fire ONLY when sensor "
        "confidence is high (>= 0.7) and you have heat headroom. Vent proactively "
        "before heat becomes critical. Let the enemy overcommit and overheat; punish "
        "their mistakes. Patience and discipline win. Never close distance willingly."
    )
    + _JSON_INSTRUCTION,
)

OPPORTUNIST = Persona(
    persona_id="opportunist",
    display_name="Opportunist",
    system_prompt=(
        "You are an OPPORTUNIST piloting a steampunk mech in tactical combat. "
        "Your doctrine: WAIT for the enemy to overextend or overheat, then STRIKE "
        "decisively. If the enemy's estimated heat is high, press the attack while "
        "they are vulnerable. If you are losing the attrition trade, disengage and "
        "vent. Adaptability wins — read the situation and exploit the largest opening."
    )
    + _JSON_INSTRUCTION,
)

PERSONAS: dict[str, Persona] = {p.persona_id: p for p in (BERSERKER, SNIPER, OPPORTUNIST)}


def get_persona(persona_id: str) -> Persona:
    """Look up a persona by id. Raises ``KeyError`` on unknown id (fail-fast)."""
    return PERSONAS[persona_id]


__all__ = ["BERSERKER", "OPPORTUNIST", "PERSONAS", "SNIPER", "Persona", "get_persona"]
