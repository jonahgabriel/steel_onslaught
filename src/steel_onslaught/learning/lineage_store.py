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


def _relative_storage_path(path: Path, *, root: Path) -> Path:
    """Return ``path`` relative to ``root`` without permitting path escapes."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Lineage storage path is outside its root: {path}") from exc

    try:
        resolved_relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Lineage storage path escapes its root: {relative.as_posix()}") from exc
    if resolved_relative != relative:
        raise ValueError(
            "Lineage storage path resolves to a different location: "
            f"{relative.as_posix()} -> {resolved_relative.as_posix()}"
        )
    return relative


def _validate_storage_identity(
    path: Path, *, root: Path, record: ModelSOLineageRecord
) -> tuple[str, str, str]:
    """Prove that record content and every identity-bearing path segment agree."""
    relative = _relative_storage_path(path, root=root)
    if len(relative.parts) != 3:
        raise ValueError(
            "Lineage storage path must be <archetype>/<spec_hash>/<record_digest>.yaml, "
            f"got {relative.as_posix()}"
        )

    path_archetype, path_spec_hash, filename = relative.parts
    if path_archetype != record.archetype:
        raise ValueError(
            "Lineage archetype directory mismatch: "
            f"record has {record.archetype!r}, path has {path_archetype!r}"
        )
    if path_spec_hash != record.spec_hash:
        raise ValueError(
            "Lineage spec_hash directory mismatch: "
            f"record has {record.spec_hash!r}, path has {path_spec_hash!r}"
        )

    digest = record_digest(record)
    expected_filename = f"{digest}.yaml"
    if filename != expected_filename:
        raise ValueError(
            "Lineage record digest filename mismatch: "
            f"canonical record requires {expected_filename!r}, path has {filename!r}"
        )
    return path_archetype, path_spec_hash, digest


def _load_validated_lineage_file(
    path: Path, *, root: Path
) -> tuple[ModelSOPersistedLineageRecord, tuple[str, str, str]]:
    """Parse one envelope and prove its canonical content-addressed location."""
    if not path.is_file():
        relative = _relative_storage_path(path, root=root)
        raise ValueError(f"Expected a lineage YAML file at {relative.as_posix()}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(raw).__name__}")
    envelope = ModelSOPersistedLineageRecord.model_validate(raw)
    identity = _validate_storage_identity(path, root=root, record=envelope.record)
    return envelope, identity


def write_lineage_record(
    record: ModelSOLineageRecord, *, root: Path, recorded_at: datetime
) -> Path:
    """Write YAML to root/<archetype>/<spec_hash>/<record_digest>.yaml.

    First write wins: if the path exists, validate its content-addressed
    identity, leave it untouched, and return it. A corrupt or misplaced target
    fails closed instead of being accepted as an idempotent re-run.
    """
    digest = record_digest(record)
    target_dir = root / record.archetype / record.spec_hash
    target_path = target_dir / f"{digest}.yaml"
    envelope = ModelSOPersistedLineageRecord(record=record, recorded_at=recorded_at)
    _validate_storage_identity(target_path, root=root, record=record)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Serialize via model_dump to get plain Python types, then YAML-dump.
    # mode="json" gives us JSON-compatible types (str for datetime, etc.) which
    # yaml.dump renders cleanly without custom tags.
    data = envelope.model_dump(mode="json")
    content = yaml.dump(data, default_flow_style=False, sort_keys=True, allow_unicode=True)
    try:
        with target_path.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except FileExistsError:
        existing, _ = _load_validated_lineage_file(target_path, root=root)
        if existing.record != record:
            raise ValueError(
                "Existing lineage target does not contain the requested canonical record: "
                f"{target_path.relative_to(root).as_posix()}"
            ) from None
        return target_path

    persisted, _ = _load_validated_lineage_file(target_path, root=root)
    if persisted != envelope:
        raise ValueError(
            "Persisted lineage envelope differs from the requested envelope: "
            f"{target_path.relative_to(root).as_posix()}"
        )

    return target_path


def load_lineage_records(root: Path) -> list[ModelSOPersistedLineageRecord]:
    """Load every record under root, sorted by (archetype, spec_hash, digest)
    — a deterministic order, no mtime reliance. Unparseable files raise.
    """
    results: list[tuple[str, str, str, ModelSOPersistedLineageRecord]] = []

    if not root.exists():
        return []

    # Tuner usage sidecars share the lineage tree but are not lineage
    # envelopes.  They have an explicit suffix and must not be interpreted as
    # records when a context arm reads promoted exemplars.
    for yaml_file in sorted(root.rglob("*.yaml"), key=lambda path: path.as_posix()):
        if yaml_file.name.endswith(".usage.yaml"):
            continue
        envelope, (archetype, sh, digest) = _load_validated_lineage_file(yaml_file, root=root)
        results.append((archetype, sh, digest, envelope))

    results.sort(key=lambda t: (t[0], t[1], t[2]))
    return [t[3] for t in results]
