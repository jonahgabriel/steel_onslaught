"""Lineage YAML persistence under contracts_data/lineage/.

Record identity is the SHA-256 of the inner ModelSOLineageRecord (wall-clock
excluded). First-write-wins: identical inner records map to the same path
regardless of when they were written. The clock is injected by the caller —
wall-clock reads are confined to the CLI boundary (Architectural Decision #4).

Path scheme:
    <root>/<archetype>/<spec_hash>/<record_digest>.yaml

The archetype and spec_hash segments come from the record itself; the
record_digest is derived from the record's canonical JSON, excluding
recorded_at.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, field_validator

from steel_onslaught.contracts.lineage import ModelSOLineageRecord


class ModelSOPersistedLineageRecord(BaseModel):
    """Persistence envelope: the pure record plus wall-clock attribution added
    AT PERSISTENCE TIME (addendum §6 deviation note) — recorded_at is a required
    field with NO default; the clock is injected by the caller.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    record: ModelSOLineageRecord
    recorded_at: datetime  # timezone-aware required (validator); never defaulted

    @field_validator("recorded_at")
    @classmethod
    def _require_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware (tzinfo required)")
        return v


def record_digest(record: ModelSOLineageRecord) -> str:
    """SHA-256 over the canonical JSON (sort_keys, compact separators) of the
    INNER record only — recorded_at is excluded from identity (Decision #4).
    """
    blob = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_lineage_record(
    record: ModelSOLineageRecord, *, root: Path, recorded_at: datetime
) -> Path:
    """Write YAML to root/<archetype>/<spec_hash>/<record_digest>.yaml.

    First write wins: if the path exists, leave the file untouched and return
    the existing path (idempotent re-runs; identical inner record => identical
    path regardless of clock).
    """
    digest = record_digest(record)
    target_dir = root / record.archetype / record.spec_hash
    target_path = target_dir / f"{digest}.yaml"

    if target_path.exists():
        return target_path

    target_dir.mkdir(parents=True, exist_ok=True)

    envelope = ModelSOPersistedLineageRecord(record=record, recorded_at=recorded_at)
    # Serialize via model_dump to get plain Python types, then YAML-dump.
    # mode="json" gives us JSON-compatible types (str for datetime, etc.) which
    # yaml.dump renders cleanly without custom tags.
    data = envelope.model_dump(mode="json")
    content = yaml.dump(data, default_flow_style=False, sort_keys=True, allow_unicode=True)
    target_path.write_text(content, encoding="utf-8")

    return target_path


def load_lineage_records(root: Path) -> list[ModelSOPersistedLineageRecord]:
    """Load every record under root, sorted by (archetype, spec_hash, digest)
    — a deterministic order, no mtime reliance. Unparseable files raise.
    """
    results: list[tuple[str, str, str, ModelSOPersistedLineageRecord]] = []

    if not root.exists():
        return []

    for yaml_file in root.rglob("*.yaml"):
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected a YAML mapping in {yaml_file}, got {type(raw).__name__}")
        envelope = ModelSOPersistedLineageRecord.model_validate(raw)
        archetype = envelope.record.archetype
        sh = envelope.record.spec_hash
        digest = record_digest(envelope.record)
        results.append((archetype, sh, digest, envelope))

    results.sort(key=lambda t: (t[0], t[1], t[2]))
    return [t[3] for t in results]
