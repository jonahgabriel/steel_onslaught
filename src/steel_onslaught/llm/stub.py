"""Deterministic stub LLM client for offline development and tests.

Table-driven: map a persona id → a decision function that inspects the
serialized observation and returns a canned JSON response. No network.

This lets the entire LLM pilot + tuner be developed and tested offline, with
full determinism. The fail-fast convention (KeyError on unscripted input)
mirrors the repo's ``FakeEvaluator`` stub — a missing persona entry surfaces
loudly rather than silently returning REMAIN.

The JSON shape returned matches what the real client parses: the pilot's
expected response schema ``{"action": ..., "action_params": {...},
"confidence": ..., "rationale": "..."}``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from steel_onslaught.llm.schemas import LlmResponse, LlmUsage

# A stub decision function: given the user-prompt text (the serialized
# observation), return the JSON string the pilot will parse.
_StubDecisionFn = Callable[[str], str]


def _berserker_decision(user_prompt: str) -> str:
    """Aggressive: close distance and fire, ignore heat."""
    # Fire only if a weapon is ready AND the enemy is in range (distance <= 12,
    # the longest light-weapon range). Else close distance.
    has_ready_weapon = "cooldown_remaining_ticks: 0" in user_prompt
    enemy_close = "distance_estimate=" in user_prompt and any(
        _parse_distance(line) <= 12
        for line in user_prompt.splitlines()
        if "distance_estimate=" in line
    )
    if has_ready_weapon and enemy_close:
        return json.dumps(
            {
                "action": "fire_weapon",
                "action_params": {},
                "confidence": 0.8,
                "rationale": "CLOSE AND BURN — fire the first ready weapon.",
            }
        )
    return json.dumps(
        {
            "action": "move",
            "action_params": {"direction": "toward_enemy"},
            "confidence": 0.7,
            "rationale": "CLOSE THE DISTANCE — get into firing range.",
        }
    )


def _parse_distance(line: str) -> float:
    """Extract the distance_estimate value from a sensor-reading prompt line."""
    try:
        return float(line.split("distance_estimate=")[1].split()[0])
    except (IndexError, ValueError):
        return 999.0


def _sniper_decision(user_prompt: str) -> str:
    """Defensive: maintain range, vent proactively, fire only on high confidence."""
    # The prompt formats enemy readings as "confidence=0.90" (2dp). Fire when
    # confidence >= 0.8; vent when heat > 0; else maintain range.
    if (
        "confidence=0.8" in user_prompt
        or "confidence=0.9" in user_prompt
        or "confidence=1.0" in user_prompt
    ):
        return json.dumps(
            {
                "action": "fire_weapon",
                "action_params": {},
                "confidence": 0.85,
                "rationale": "High-confidence lock — take the shot.",
            }
        )
    if "heat_current: 0" not in user_prompt and "heat_current:" in user_prompt:
        # heat > 0 — vent to stay cool
        return json.dumps(
            {
                "action": "vent",
                "action_params": {},
                "confidence": 0.5,
                "rationale": "Vent to keep the boiler cool for the next shot.",
            }
        )
    return json.dumps(
        {
            "action": "move",
            "action_params": {"direction": "defensive"},
            "confidence": 0.6,
            "rationale": "Maintain standoff range; wait for a clean lock.",
        }
    )


def _tuner_decision(user_prompt: str) -> str:
    """Tuner stub: propose parameter sets that differ from the parent.

    Parses the parent params from the prompt and returns 2 proposals with
    slightly different values (within the declared bounds). This gives the
    tuner a working offline path.
    """

    # Extract parent params from the "Current parent parameters:" line.
    # The format is: "Current parent parameters: k=v, k=v, ..."
    p1: dict[str, object] = {}
    p2: dict[str, object] = {}
    for line in user_prompt.splitlines():
        if "Current parent parameters:" not in line:
            continue
        params_str = line.split("Current parent parameters:")[1].strip()
        for pair in params_str.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, val = pair.split("=", 1)
            name, val = name.strip(), val.strip().strip("'\"")
            try:
                v: object = float(val) if "." in val else int(val)
            except ValueError:
                v = val
            p1[name] = v
            p2[name] = v
        break
    # Modify one numeric param in each proposal
    for pname in list(p1):
        pval = p1[pname]
        if isinstance(pval, (int, float)) and pval != 0:
            p1[pname] = max(0, pval - 1)  # small step down
            break
    for pname in list(p2):
        pval = p2[pname]
        if isinstance(pval, (int, float)):
            p2[pname] = pval + 1  # small step up
            break
    proposals = [p1, p2]
    return json.dumps(proposals)


_PERSONA_STUBS: dict[str, _StubDecisionFn] = {
    "berserker": _berserker_decision,
    "sniper": _sniper_decision,
    "tuner": _tuner_decision,
}


class StubLlmClient:
    """Deterministic, no-network LLM client keyed on persona id.

    The persona id is passed via ``opts["persona"]`` (the pilot threads it
    through). An unscripted persona raises ``KeyError`` — fail-fast, no silent
    REMAIN fallback masquerading as a real decision.
    """

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **opts: Any,
    ) -> LlmResponse:
        persona = opts.get("persona", "berserker")
        decision_fn = _PERSONA_STUBS[persona]  # KeyError on unscripted persona
        text = decision_fn(user_prompt)
        return LlmResponse(
            text=text,
            usage=LlmUsage(prompt_tokens=len(user_prompt) // 4, completion_tokens=20),
            model="stub",
            finish_reason="stop",
        )


__all__ = ["StubLlmClient"]
