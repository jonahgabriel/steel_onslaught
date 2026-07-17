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
import re
from collections.abc import Callable
from dataclasses import dataclass

from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
)

# A stub decision function: given the user-prompt text (the serialized
# observation), return the JSON string the pilot will parse.
_StubDecisionFn = Callable[[str], str]

_BERSERKER_POINT_BLANK_DISTANCE = 3.0
_SNIPER_MIN_CONFIDENCE = 0.7
_SNIPER_BAND_INNER = 0.6
_PROACTIVE_VENT_HEAT_FRACTION = 0.6
_OPPORTUNIST_DISENGAGE_HP = 30.0
_OPPORTUNIST_ENEMY_OVERHEAT_FRACTION = 0.6


@dataclass(frozen=True)
class _WeaponView:
    weapon_id: str
    range: float
    pressure_cost: int
    cooldown: int


@dataclass(frozen=True)
class _ParsedObservation:
    detected: bool
    nearest_distance: float | None
    best_confidence: float | None
    enemy_heat: float | None
    has_los: bool
    heat_current: int
    heat_rupture: int
    redline: bool
    pressure_current: int
    hp_percent: float
    weapons: tuple[_WeaponView, ...]


_HEADER_RE = re.compile(r"^--- YOUR MECH \(tick \d+\) ---$", re.MULTILINE)
_HP_RE = re.compile(
    r"^hp: (?P<hp>\d+(?:\.\d+)?)%  mode: \S+  mode_lock_expired: (?:True|False)$",
    re.MULTILINE,
)
_POSITION_RE = re.compile(
    r"^position: \(-?\d+,-?\d+\)  under_sensor_lock: (?:True|False)$",
    re.MULTILINE,
)
_TERRAIN_RE = re.compile(
    r"^terrain: line_of_sight_to_enemy: (?P<los>True|False)  "
    r"blocked_directions: \[(?P<blocked>[a-z, ]*)\]$",
    re.MULTILINE,
)
_BOILER_RE = re.compile(
    r"^boiler: pressure (?P<pressure>\d+)/(?P<pressure_max>\d+)  "
    r"heat (?P<heat>\d+)/(?P<rupture>\d+)  redline: (?P<redline>True|False)$",
    re.MULTILINE,
)
_WEAPON_RE = re.compile(
    r"^  - (?P<wid>[^:\s]+): damage=\d+ range=(?P<range>\d+(?:\.\d+)?) "
    r"pressure_cost=(?P<pc>\d+) heat_generated=\d+ "
    r"cooldown_remaining_ticks: (?P<cd>\d+)$"
)
_ENEMY_RE = re.compile(
    r"^  tick \d+: distance_estimate=(?P<distance>\d+(?:\.\d+)?) "
    r"confidence=(?P<confidence>\d+(?:\.\d+)?)"
    r"(?: heat_estimate=(?P<heat>\d+(?:\.\d+)?))?$"
)
_VALID_DIRECTIONS = frozenset({"n", "ne", "e", "se", "s", "sw", "w", "nw"})
_ENEMY_HEADER = "--- ENEMY (noisy sensor readings, newest last) ---"
_NO_ENEMY = "--- ENEMY: no sensor readings (enemy not detected) ---"


def _require_single(pattern: re.Pattern[str], user_prompt: str, field: str) -> re.Match[str]:
    matches = tuple(pattern.finditer(user_prompt))
    if len(matches) != 1:
        raise ValueError(f"stub prompt requires exactly one valid {field}")
    return matches[0]


def _parse_observation(user_prompt: str) -> _ParsedObservation:
    """Parse the exact current ``LLMPilot`` observation format, fail-loud."""
    _require_single(_HEADER_RE, user_prompt, "mech header")
    hp_match = _require_single(_HP_RE, user_prompt, "hp/mode line")
    _require_single(_POSITION_RE, user_prompt, "position line")
    terrain_match = _require_single(_TERRAIN_RE, user_prompt, "terrain line")
    boiler_match = _require_single(_BOILER_RE, user_prompt, "boiler line")

    if user_prompt.splitlines().count("weapons:") != 1:
        raise ValueError("stub prompt requires exactly one weapons section")

    blocked_text = terrain_match.group("blocked")
    blocked = tuple(part.strip() for part in blocked_text.split(",") if part.strip())
    if any(direction not in _VALID_DIRECTIONS for direction in blocked):
        raise ValueError("stub prompt contains an invalid blocked direction")

    weapon_lines = [line for line in user_prompt.splitlines() if line.startswith("  - ")]
    weapons: list[_WeaponView] = []
    for line in weapon_lines:
        match = _WEAPON_RE.fullmatch(line)
        if match is None:
            raise ValueError("stub prompt contains a malformed weapon line")
        weapons.append(
            _WeaponView(
                weapon_id=match.group("wid"),
                range=float(match.group("range")),
                pressure_cost=int(match.group("pc")),
                cooldown=int(match.group("cd")),
            )
        )
    if len({weapon.weapon_id for weapon in weapons}) != len(weapons):
        raise ValueError("stub prompt contains duplicate weapon ids")

    lines = user_prompt.splitlines()
    enemy_lines = [line for line in lines if line.startswith("  tick ")]
    has_enemy_header = lines.count(_ENEMY_HEADER) == 1
    has_no_enemy_marker = lines.count(_NO_ENEMY) == 1
    if has_enemy_header == has_no_enemy_marker:
        raise ValueError("stub prompt requires exactly one valid enemy section")
    if has_no_enemy_marker and enemy_lines:
        raise ValueError("stub prompt mixes no-enemy and enemy-reading sections")
    if has_enemy_header and not enemy_lines:
        raise ValueError("stub prompt enemy section requires a sensor reading")

    distances: list[float] = []
    confidences: list[float] = []
    enemy_heats: list[float] = []
    for line in enemy_lines:
        match = _ENEMY_RE.fullmatch(line)
        if match is None:
            raise ValueError("stub prompt contains a malformed enemy reading")
        distances.append(float(match.group("distance")))
        confidences.append(float(match.group("confidence")))
        if match.group("heat") is not None:
            enemy_heats.append(float(match.group("heat")))

    return _ParsedObservation(
        detected=bool(enemy_lines),
        nearest_distance=min(distances) if distances else None,
        best_confidence=max(confidences) if confidences else None,
        enemy_heat=max(enemy_heats) if enemy_heats else None,
        has_los=terrain_match.group("los") == "True",
        heat_current=int(boiler_match.group("heat")),
        heat_rupture=int(boiler_match.group("rupture")),
        redline=boiler_match.group("redline") == "True",
        pressure_current=int(boiler_match.group("pressure")),
        hp_percent=float(hp_match.group("hp")),
        weapons=tuple(weapons),
    )


def _first_ready_weapon_id(user_prompt: str) -> str | None:
    for line in user_prompt.splitlines():
        if not line.startswith("  - "):
            continue
        if "cooldown_remaining_ticks: 0" in line:
            return line.removeprefix("  - ").split(":", 1)[0]
    return None


def _ready_weapon_in_range(user_prompt: str, obs: _ParsedObservation) -> _WeaponView | None:
    """Return the first ready weapon only when firing it is valid now."""
    weapon_id = _first_ready_weapon_id(user_prompt)
    if weapon_id is None:
        return None
    matches = tuple(weapon for weapon in obs.weapons if weapon.weapon_id == weapon_id)
    if len(matches) != 1:
        raise ValueError("stub prompt ready weapon id does not resolve uniquely")
    weapon = matches[0]
    if weapon.cooldown != 0:
        raise ValueError("stub prompt ready weapon has a nonzero cooldown")
    if obs.nearest_distance is None:
        return None
    if obs.pressure_current < weapon.pressure_cost or weapon.range < obs.nearest_distance:
        return None
    return weapon


def _heat_pressing(obs: _ParsedObservation) -> bool:
    if obs.redline:
        return True
    if obs.heat_rupture <= 0:
        raise ValueError("stub prompt heat rupture threshold must be positive")
    return obs.heat_current >= _PROACTIVE_VENT_HEAT_FRACTION * obs.heat_rupture


def _decision(
    action: str,
    *,
    confidence: float,
    rationale: str,
    params: dict[str, str] | None = None,
) -> str:
    action_params = params if params is not None else {}
    if action == "fire_weapon" and not action_params.get("weapon_id"):
        raise ValueError("stub fire decisions require an explicit weapon id")
    return json.dumps(
        {
            "action": action,
            "action_params": action_params,
            "confidence": confidence,
            "rationale": rationale,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _berserker_decision(user_prompt: str) -> str:
    """Reckless brawler: close to point-blank and spray through cover."""
    obs = _parse_observation(user_prompt)
    if not obs.detected:
        return _decision(
            "move",
            confidence=0.7,
            rationale="No lock yet — charge toward the enemy's last bearing.",
            params={"direction": "toward_enemy"},
        )
    ready_weapon = _ready_weapon_in_range(user_prompt, obs)
    if ready_weapon is not None and (
        not obs.has_los
        or (
            obs.nearest_distance is not None
            and obs.nearest_distance <= _BERSERKER_POINT_BLANK_DISTANCE
        )
    ):
        return _decision(
            "fire_weapon",
            confidence=0.8,
            rationale="A weapon can bite — fire now and keep pressing.",
            params={"weapon_id": ready_weapon.weapon_id},
        )
    return _decision(
        "move",
        confidence=0.75,
        rationale="Close the distance and force a point-blank exchange.",
        params={"direction": "toward_enemy"},
    )


def _max_weapon_range(obs: _ParsedObservation) -> float | None:
    if not obs.weapons:
        return None
    return max(weapon.range for weapon in obs.weapons)


def _sniper_decision(user_prompt: str) -> str:
    """Methodical marksman: hold range, vent early, fire on a clean lock."""
    obs = _parse_observation(user_prompt)
    if not obs.detected:
        return _decision(
            "move",
            confidence=0.55,
            rationale="No contact — advance to a forward overwatch line.",
            params={"direction": "toward_enemy"},
        )
    if _heat_pressing(obs):
        return _decision(
            "vent",
            confidence=0.6,
            rationale="Bleed heat now so the next shot stays safe.",
        )
    max_range = _max_weapon_range(obs)
    if max_range is None:
        return _decision(
            "move",
            confidence=0.6,
            rationale="Unarmed — keep defensive distance.",
            params={"direction": "defensive"},
        )
    if obs.nearest_distance is None:
        raise ValueError("detected enemy requires a distance estimate")
    if obs.nearest_distance > max_range:
        return _decision(
            "move",
            confidence=0.65,
            rationale="Enemy beyond the standoff band — advance to weapon range.",
            params={"direction": "toward_enemy"},
        )
    if obs.nearest_distance < max_range * _SNIPER_BAND_INNER:
        return _decision(
            "move",
            confidence=0.7,
            rationale="Enemy inside the standoff band — kite back.",
            params={"direction": "defensive"},
        )
    ready_weapon = _ready_weapon_in_range(user_prompt, obs)
    if (
        ready_weapon is not None
        and obs.has_los
        and obs.best_confidence is not None
        and obs.best_confidence >= _SNIPER_MIN_CONFIDENCE
    ):
        return _decision(
            "fire_weapon",
            confidence=0.85,
            rationale="Clean high-confidence lock — take the measured shot.",
            params={"weapon_id": ready_weapon.weapon_id},
        )
    return _decision(
        "move",
        confidence=0.55,
        rationale="No clean lock — kite back and break contact.",
        params={"direction": "defensive"},
    )


def _opportunist_decision(user_prompt: str) -> str:
    """Patient exploiter: punish overheat, seek openings, cut bad trades."""
    obs = _parse_observation(user_prompt)
    if not obs.detected:
        return _decision(
            "remain",
            confidence=0.6,
            rationale="Watch and wait for the enemy to overextend.",
        )
    if obs.hp_percent < _OPPORTUNIST_DISENGAGE_HP:
        if _heat_pressing(obs):
            return _decision(
                "vent",
                confidence=0.6,
                rationale="The trade is lost and the boiler is hot — vent before breaking off.",
            )
        return _decision(
            "move",
            confidence=0.7,
            rationale="The attrition trade is lost — disengage and reset.",
            params={"direction": "defensive"},
        )
    if obs.heat_rupture <= 0:
        raise ValueError("stub prompt heat rupture threshold must be positive")
    enemy_overheating = (
        obs.enemy_heat is not None
        and obs.enemy_heat >= _OPPORTUNIST_ENEMY_OVERHEAT_FRACTION * obs.heat_rupture
    )
    ready_weapon = _ready_weapon_in_range(user_prompt, obs)
    if enemy_overheating and ready_weapon is not None and obs.has_los:
        return _decision(
            "fire_weapon",
            confidence=0.9,
            rationale="The enemy boiler is glowing — punish it now.",
            params={"weapon_id": ready_weapon.weapon_id},
        )
    if enemy_overheating:
        return _decision(
            "move",
            confidence=0.75,
            rationale="The enemy is overheating — press in for the strike.",
            params={"direction": "toward_enemy"},
        )
    if (
        ready_weapon is not None
        and obs.has_los
        and obs.best_confidence is not None
        and obs.best_confidence >= _SNIPER_MIN_CONFIDENCE
    ):
        return _decision(
            "fire_weapon",
            confidence=0.8,
            rationale="A clean opening appeared — take the shot.",
            params={"weapon_id": ready_weapon.weapon_id},
        )
    if not obs.has_los:
        return _decision(
            "move",
            confidence=0.65,
            rationale="No clean angle — move toward a firing lane.",
            params={"direction": "toward_enemy"},
        )
    return _decision(
        "remain",
        confidence=0.5,
        rationale="Bide time and wait for a larger opening.",
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
    "opportunist": _opportunist_decision,
    "tuner": _tuner_decision,
}


class StubLlmClient:
    """Deterministic, no-network LLM client keyed on persona id.

    The persona id is carried by the typed completion request. An unscripted
    persona raises ``KeyError`` — fail-fast, no silent REMAIN fallback
    masquerading as a real decision.
    """

    def __init__(self, *, model: str) -> None:
        self._model = model

    def complete(
        self,
        request: ModelSOLlmCompletionRequest,
    ) -> LlmResponse:
        decision_fn = _PERSONA_STUBS[request.persona]  # KeyError on unscripted persona
        text = decision_fn(request.user_prompt)
        return LlmResponse(
            text=text,
            usage=LlmUsage(
                prompt_tokens=len(request.user_prompt) // 4,
                completion_tokens=20,
                cost_usd=0.0,
            ),
            model=self._model,
            finish_reason="stop",
        )


__all__ = ["StubLlmClient"]
