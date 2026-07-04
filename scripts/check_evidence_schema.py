#!/usr/bin/env python3
"""Schema validator for in-repo evidence tickets (``evidence/SO-NNNN.md``).

Design: ``docs/plans/2026-07-03-evidence-tickets-design.md``. Evidence tickets
are the same-repo (OCC-lite) receipts pattern: one file per work item, a
PRE-REGISTERED acceptance bar, a mechanically re-checkable evidence block, an
explicit ``verifier`` distinct from the builder, and a locked terminal status.

This validator is the §3c "mechanically re-checkable claims" gate. It runs as
the ``evidence-schema`` CI job and (optionally) locally. It asserts every
``evidence/SO-*.md`` file:

* has YAML frontmatter parseable into the pinned schema (no unknown keys),
* has ``id`` matching ``^SO-\\d{4}$`` and equal to the filename stem,
* carries a non-empty ``intent`` and a non-empty PRE-REGISTERED ``acceptance_bar``,
* if CLOSED (``PASS``/``FAILED``): names a ``verifier``, a ``verified_at``
  timestamp, and at least one re-checkable ``checks`` entry — a closed ticket
  with no verifier or no recomputable check is exactly the self-attested
  "should be fine now" receipt the pattern exists to forbid,
* references only ``artifacts`` paths that actually resolve on disk.

Tamper-locking of closed tickets (zero diff vs merge-base) is enforced
separately by ``tests/test_evidence_tickets.py`` (§3b), which runs in the
``python-test`` job on every CI run.

Dependency-light: pydantic + pyyaml (both already project deps).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE_DIR = _REPO_ROOT / "evidence"
_ID_RE = re.compile(r"^SO-\d{4}$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

Status = Literal["OPEN", "PASS", "FAILED"]


class EvidenceBlock(BaseModel):
    """Structured, mechanically re-checkable evidence (§3c)."""

    model_config = ConfigDict(extra="forbid")

    commits: list[str] = Field(default_factory=list)
    suite: dict[str, str] = Field(default_factory=dict)
    ledger: dict[str, str] = Field(default_factory=dict)
    checks: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class EvidenceTicket(BaseModel):
    """One work item's receipt. Schema is closed (``extra="forbid"``)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    status: Status
    intent: str
    acceptance_bar: list[str]
    evidence: EvidenceBlock
    verifier: str | None = None
    verified_at: str | None = None


def _parse_frontmatter(text: str) -> dict[str, object]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError("missing YAML frontmatter (file must start with a --- block)")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter did not parse to a mapping")
    return loaded


def validate_ticket(path: Path) -> list[str]:
    """Return a list of human-readable errors for one evidence file ([] = valid)."""
    errors: list[str] = []
    try:
        raw = _parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path.name}: {exc}"]

    try:
        ticket = EvidenceTicket.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            errors.append(f"{path.name}: field '{loc}': {err['msg']}")
        return errors

    stem = path.stem
    if not _ID_RE.match(ticket.id):
        errors.append(f"{path.name}: id '{ticket.id}' must match SO-NNNN")
    if ticket.id != stem:
        errors.append(f"{path.name}: id '{ticket.id}' must equal filename stem '{stem}'")
    if not ticket.intent.strip():
        errors.append(f"{path.name}: intent must be non-empty")
    if not ticket.acceptance_bar:
        errors.append(f"{path.name}: acceptance_bar must be pre-registered (non-empty)")

    if ticket.status in ("PASS", "FAILED"):
        if not (ticket.verifier and ticket.verifier.strip()):
            errors.append(f"{path.name}: a closed ({ticket.status}) ticket must name a verifier")
        if not (ticket.verified_at and ticket.verified_at.strip()):
            errors.append(f"{path.name}: a closed ({ticket.status}) ticket must set verified_at")
        if not ticket.evidence.checks:
            errors.append(
                f"{path.name}: a closed ({ticket.status}) ticket must cite at least "
                f"one re-checkable evidence.checks entry"
            )

    for artifact in ticket.evidence.artifacts:
        if not (_REPO_ROOT / artifact).exists():
            errors.append(f"{path.name}: evidence.artifacts path does not resolve: {artifact}")

    return errors


def main(argv: list[str] | None = None) -> int:
    files = sorted(_EVIDENCE_DIR.glob("SO-*.md"))
    if not files:
        print(f"No evidence tickets found under {_EVIDENCE_DIR}/ — nothing to validate.")
        return 0

    all_errors: list[str] = []
    for path in files:
        all_errors.extend(validate_ticket(path))

    if all_errors:
        print("Evidence-schema gate FAILED:", file=sys.stderr)
        for err in all_errors:
            print(f"  x {err}", file=sys.stderr)
        return 1

    print(f"Evidence-schema gate OK — {len(files)} ticket(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
