"""Explicit offline-only projections for immutable historical ledgers."""

from __future__ import annotations

from steel_onslaught.contracts.arena import ModelSOCurrentLiveArenaSnapshot
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType


def migrate_historical_match_started_arena(
    event: ModelSOEventEnvelope,
    *,
    arena: ModelSOCurrentLiveArenaSnapshot,
) -> ModelSOEventEnvelope:
    """Add caller-supplied neutral arena truth to one pre-terrain start event."""

    if event.event_type is not SOEventType.MATCH_STARTED:
        return event
    raw = event.model_dump(mode="json")
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise TypeError("historical MATCH_STARTED payload must be an object")
    if "arena" in payload:
        return event
    raw["payload"] = {**payload, "arena": arena.model_dump(mode="json")}
    return ModelSOEventEnvelope.model_validate(raw)


__all__ = ["migrate_historical_match_started_arena"]
