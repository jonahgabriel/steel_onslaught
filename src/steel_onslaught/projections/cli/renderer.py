"""ANSI text renderer — Task 28.

``CliTextRenderer`` subscribes to the EventBus with ``event_types=None``
(every event) and writes one human-readable line per *interesting* event to a
text stream.  It is a pure projection: it holds no match state beyond display
labels, never publishes, and never mutates anything a reducer reads.

Determinism: rendered lines contain only tick numbers, ids, and payload
values — never ULIDs, wall-clock timestamps, or ``match_id`` — so two runs
with the same seed produce byte-identical output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TextIO

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType

if TYPE_CHECKING:
    from steel_onslaught.bus.protocol import EventBus, HandlerToken

# ANSI SGR codes.
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"


def _prettify(segment: str) -> str:
    """``ironclad_mk1`` -> ``Ironclad Mk1``."""
    return " ".join(part.capitalize() for part in segment.split("_"))


def _chassis_label(chassis_id: str) -> str:
    """``chassis.heavy.ironclad_mk1`` -> ``Heavy Ironclad Mk1``."""
    return " ".join(_prettify(part) for part in chassis_id.split(".")[1:])


def _pilot_label(pilot_id: str) -> str:
    """``pilot.example.predictive_v1`` -> ``Predictive V1``."""
    return _prettify(pilot_id.rsplit(".", 1)[-1])


def _last_segment(module_id: str) -> str:
    """``weapon.light.machine_gun`` -> ``machine_gun``."""
    return module_id.rsplit(".", 1)[-1]


def _reason_text(reason: str) -> str:
    """``last_mech_standing`` -> ``last mech standing``."""
    return reason.replace("_", " ")


def _decision_detail(params: dict[str, Any]) -> str:
    """Human detail for a pilot decision, from its ``action_params``."""
    if "target_mode" in params:
        return str(params["target_mode"])
    if "weapon_id" in params:
        return _last_segment(str(params["weapon_id"]))
    if "direction" in params:
        return str(params["direction"])
    return ""


class CliTextRenderer:
    """Renders bus events as ANSI text lines on *out*.

    The renderer learns per-mech display labels (chassis, pilot archetype)
    from the ``MATCH_STARTED`` payload; until then decision lines fall back
    to the bare ``mech_id``.
    """

    def __init__(self, out: TextIO, *, color: bool = True) -> None:
        self._out = out
        self._color = color
        # mech_id -> (chassis label, pilot label), learned from MATCH_STARTED.
        self._labels: dict[str, tuple[str, str]] = {}

    def attach(self, bus: EventBus) -> HandlerToken:
        """Subscribe to every event type on *bus*; return the handler token."""
        return bus.subscribe(self.handle, event_types=None)

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """``EventHandler``-shaped entry point — render one event, if mapped."""
        line = self._render(event)
        if line is not None:
            self._out.write(line + "\n")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _paint(self, text: str, *codes: str) -> str:
        if not self._color:
            return text
        return f"{''.join(codes)}{text}{_RESET}"

    def _render(self, event: ModelSOEventEnvelope) -> str | None:
        tick = f"[Tick {event.tick}]"
        mech = event.subject.mech_id
        payload = event.payload

        match event.event_type:
            case SOEventType.MATCH_STARTED:
                self._learn_labels(payload)
                return (
                    f"{tick} MATCH STARTED "
                    f"(seed {payload['seed']}, max_ticks {payload['max_ticks']})"
                )
            case SOEventType.PILOT_DECISION_MADE:
                labels = self._labels.get(mech)
                who = f"{mech} ({labels[0]}, {labels[1]})" if labels is not None else mech
                action = str(payload["action"]).upper()
                detail = _decision_detail(payload["action_params"])
                arrow = f" → {detail}" if detail else ""
                conf = float(payload["confidence"])
                return f"{tick} {who} decided: {action}{arrow} (conf {conf:.2f})"
            case SOEventType.BOILER_UPDATED:
                return (
                    f"{tick} {mech} boiler: "
                    f"pressure {payload['pressure_before']} → {payload['pressure_after']}, "
                    f"heat {payload['heat_before']} → {payload['heat_after']}"
                )
            case SOEventType.HEAT_REDLINE_ENTERED:
                return self._paint(
                    f"{tick} {mech} REDLINE entered "
                    f"(heat {payload['heat']} ≥ {payload['redline_threshold']})",
                    _YELLOW,
                )
            case SOEventType.HEAT_REDLINE_EXITED:
                return (
                    f"{tick} {mech} redline exited "
                    f"(heat {payload['heat']} < {payload['redline_threshold']})"
                )
            case SOEventType.WEAPON_FIRED:
                weapon = _last_segment(str(payload["weapon_id"]))
                probability = float(payload["hit_probability"])
                return (
                    f"{tick} {mech} fired {weapon} at {payload['target_id']} — "
                    f"predicted hit {probability:.2f}"
                )
            case SOEventType.DAMAGE_APPLIED:
                return self._paint(
                    f"{tick} HIT {payload['target_id']} took {payload['damage']} dmg",
                    _RED,
                )
            case SOEventType.BOILER_OVERLOADED:
                return self._paint(f"{tick} {mech} boiler OVERLOADED", _YELLOW, _BOLD)
            case SOEventType.BOILER_RUPTURED:
                return self._paint(f"{tick} {mech} BOILER RUPTURED", _RED, _BOLD)
            case SOEventType.PILOT_KILLED:
                return self._paint(f"{tick} {mech} PILOT KILLED", _RED, _BOLD)
            case SOEventType.MECH_DESTROYED:
                return self._paint(f"{tick} {mech} DESTROYED", _RED, _BOLD)
            case SOEventType.VICTORY_DECLARED:
                winner = payload["winner_player_id"]
                reason = _reason_text(str(payload["reason"]))
                return self._paint(f"{tick} VICTORY: {winner} ({reason})", _GREEN, _BOLD)
            case SOEventType.MATCH_ENDED:
                reason = _reason_text(str(payload["reason"]))
                winner = payload["winner_id"]
                suffix = f", winner {winner}" if winner is not None else ""
                return f"{tick} MATCH ENDED ({reason}{suffix})"
            case _:
                return None  # ticks, intents, observations, scores: not rendered

    def _learn_labels(self, payload: dict[str, Any]) -> None:
        for mech in payload["mechs"]:
            self._labels[str(mech["mech_id"])] = (
                _chassis_label(str(mech["chassis_id"])),
                _pilot_label(str(mech["pilot_id"])),
            )
