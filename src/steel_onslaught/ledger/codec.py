"""Canonical persisted-event codec shared by every ledger adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from steel_onslaught.events.envelope import ModelSOEventEnvelope

_REQUIRED_ENVELOPE_FIELDS = frozenset(
    {"message_id", "correlation_id", "causation_id", "emitted_at", "entity_id"}
)


class PersistedEventFormatError(ValueError):
    """Persisted data is not the complete canonical event protocol."""


class LegacyLedgerFormatError(PersistedEventFormatError):
    """A row predates the canonical composed envelope and needs offline migration."""


def _require_complete_envelope(raw: object) -> None:
    if not isinstance(raw, Mapping):
        raise PersistedEventFormatError("persisted event envelope must be an object")
    missing = _REQUIRED_ENVELOPE_FIELDS - set(raw)
    if missing:
        raise PersistedEventFormatError(
            f"persisted event envelope is missing required fields: {sorted(missing)}"
        )


def dump_persisted_event(event: ModelSOEventEnvelope) -> str:
    """Return the exact canonical JSON representation of ``event``."""
    raw = event.model_dump(mode="json")
    _require_complete_envelope(raw["envelope"])
    return json.dumps(raw, separators=(",", ":"), ensure_ascii=False)


def load_persisted_event(blob: str | bytes | bytearray) -> ModelSOEventEnvelope:
    """Validate canonical JSON without allowing nested ModelEnvelope defaults."""
    try:
        raw: Any = json.loads(blob)
    except (TypeError, ValueError) as exc:
        raise PersistedEventFormatError("persisted event is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise PersistedEventFormatError("persisted event must be a JSON object")
    _require_complete_envelope(raw.get("envelope"))
    return ModelSOEventEnvelope.model_validate(raw)


def load_persisted_event_record(raw: Mapping[str, Any]) -> ModelSOEventEnvelope:
    """Validate an adapter-materialized canonical record without synthesis."""
    _require_complete_envelope(raw.get("envelope"))
    return ModelSOEventEnvelope.model_validate(raw)


__all__ = [
    "LegacyLedgerFormatError",
    "PersistedEventFormatError",
    "dump_persisted_event",
    "load_persisted_event",
    "load_persisted_event_record",
]
