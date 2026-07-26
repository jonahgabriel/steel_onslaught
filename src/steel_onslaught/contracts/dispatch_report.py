"""Golden-chain agent dispatch report contracts (SO-REPORT-CONTRACT).

Background (the failure this module exists to close). On 2026-07-25, seven
dispatched agents completed correct underlying work and then returned bare
acknowledgements -- ``"Done."``, ``"Task complete."``,
``"No further action taken."`` -- in place of any typed result. The worst
class filled a required 4-field schema with the literal string ``"test"`` in
every field, and it VALIDATED, because the schema checked shape only (field
present, field is a string) and never checked content. Shape-only validation
and prose exhortation ("please return a real report") are both proven
insufficient by that data.

This module treats the agent final report as a seam like any other seam in
this program (mirrors ``check_preregistration_timing.py`` /
``check_contamination_gate.py``): every dispatch role gets a closed, typed
contract whose required fields carry CONTENT anchors, not mere shape --

* a git SHA field (name ends ``_sha``) must resolve against a real commit --
  checked by ``scripts/check_report_contract.py`` via ``git cat-file -e`` in
  a caller-supplied ``--git-dir``, never by this module alone (a pydantic
  model has no git access);
* ``pr_number`` must be a positive integer;
* ``verdict`` is drawn from a closed, role-specific enum -- never a free
  string;
* artifact-path fields (name ends ``_paths``) must resolve to files that
  actually exist under a caller-supplied ``--repo-root`` -- again checked by
  the validator script, not this module;
* every free-text field is rejected on placeholder literals (``"test"``,
  ``"todo"``, ``"placeholder"``, ``"lorem"``, ...), on bare-acknowledgement
  literals (``"done"``, ``"task complete"``, ``"no further action taken"``,
  ...), on any report under ``_MIN_SUBSTANTIVE_LENGTH`` characters, and on
  repetitive low-content padding used to defeat the length floor without
  saying anything -- a banned literal repeated with separators past the
  minimum length (``"Done. Done. Done. Done. Done. Done. Done."``) or a
  short unit repeated with no separators at all (keyboard-mash filler like
  ``"asdfasdfasdfasdfasdfasdfasdfasdfasdfasdfasdf"``) are both rejected, not
  just the exact single-literal case.

Four dispatch roles are modeled here: ``implementer`` (builds/fixes code and
opens or updates a PR), ``verifier`` (independently re-checks an
implementer's claim against live evidence), ``lander`` (merges/finalizes a
PR), and ``scout`` (investigates/discovers, no PR required). Each role's
model is closed (``extra="forbid"``) and discriminated on its own ``role``
Literal, mirroring ``contracts/commands.py``'s ``PlayerAction`` union.

Field-name-suffix convention (load-bearing for the validator script): any
field ending ``_sha`` is a git-commit content anchor; any field ending
``_paths`` is a list-of-artifact-paths content anchor. New roles/fields that
follow this convention are picked up by ``check_report_contract.py``
automatically -- no per-field wiring needed there.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
)

# --------------------------------------------------------------------------
# Shared field types
# --------------------------------------------------------------------------

# Git commits are 40-hex-char SHA-1 (or, on a sha256 object-format repo,
# 64-hex-char) object ids; ``git cat-file -e`` also accepts abbreviated
# short SHAs, so the floor is a conservative 7 characters. This is a SHAPE
# check only -- whether the SHA actually resolves to a real commit is a
# content anchor checked by ``check_report_contract.py`` against a caller
# -supplied ``--git-dir``, never here.
GitSha = Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{7,64}$")]

PrNumber = Annotated[StrictInt, Field(gt=0)]

_MIN_SUBSTANTIVE_LENGTH = 40

# Exact-match (post-normalization) literal placeholder fills. Deliberately a
# closed set of known-bad literals, not a substring/contains check -- a real
# report that happens to use the word "test" in a sentence (e.g. "ran the
# integration test suite") must never be flagged.
_PLACEHOLDER_LITERALS = frozenset(
    {
        "test",
        "todo",
        "placeholder",
        "lorem",
        "lorem ipsum",
        "n/a",
        "na",
        "tbd",
        "xxx",
        "fixme",
        "wip",
        "asdf",
        "foo",
        "foo bar",
        "example",
        "sample",
        "string",
        "changeme",
        "unknown",
    }
)

# Exact-match (post-normalization) bare-acknowledgement fills -- the class
# proven in the 2026-07-25 incident: real work happened, but the returned
# report carries no typed result content at all.
_BARE_ACKNOWLEDGEMENT_LITERALS = frozenset(
    {
        "done",
        "task complete",
        "task completed",
        "no further action taken",
        "no further action needed",
        "no further action required",
        "complete",
        "completed",
        "finished",
        "all done",
        "ok",
        "okay",
        "ack",
        "acknowledged",
        "confirmed",
        "will do",
        "sounds good",
        "got it",
        "on it",
        "yes",
        "no",
        "nothing further",
        "n/a - complete",
    }
)


def _normalize_for_literal_match(value: str) -> str:
    """Lowercase, strip whitespace, and strip trailing sentence punctuation.

    ``"Done."`` and ``"done"`` must compare equal; matching stays exact
    (never substring), so a genuine report that mentions "test" or "done"
    inside a longer sentence is never flagged.
    """
    stripped = value.strip().lower()
    return stripped.rstrip(".!? \t").strip()


# Splits on one-or-more sentence-terminating characters, used by the
# repeated-padding detector below to find "Done. Done. Done." style repeats
# of a single literal that individually normalize past the exact-match check
# (the whole string ``"done. done. done."`` is not itself equal to ``"done"``)
# but are transparently the same banned literal repeated to pad length.
_SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?]+")

# A blob is treated as degenerate keyboard-mash filler once a repeating unit
# of at most this many characters accounts for this fraction of the
# alphanumeric-only content -- e.g. "asdfasdfasdf..." (unit "asdf", period 4)
# covers 100% of itself. Kept conservative (short unit, high coverage, >=3
# repeats) so real prose is never caught by accidental short repeats.
_MAX_DEGENERATE_UNIT_LENGTH = 16
_MIN_DEGENERATE_COMPACT_LENGTH = 12
_MIN_DEGENERATE_COVERAGE_RATIO = 0.9
_MIN_DEGENERATE_REPEATS = 3


def _is_repetitive_padding(stripped: str) -> bool:
    """True if ``stripped`` is content-free padding used to defeat the
    length minimum, rather than genuine substantive text.

    Two independent detectors, because the two adversarial classes look
    nothing alike on the wire:

    1. A single word/phrase repeated with sentence-style separators, e.g.
       ``"Done. Done. Done. Done. Done. Done. Done."`` -- splitting on
       ``.``/``!``/``?`` yields >=3 non-empty segments that all normalize to
       the exact same text. This catches a banned literal (or any other
       single phrase) padded past ``_MIN_SUBSTANTIVE_LENGTH`` by repetition,
       which the whole-string exact-literal match above cannot see because
       the padded string as a whole is never equal to the bare literal.
    2. A short unit repeated with NO separators at all, e.g. keyboard-mash
       filler like ``"asdfasdfasdfasdfasdfasdfasdfasdfasdfasdfasdf"`` --
       there is nothing to split on, so this checks whether the
       alphanumeric-only content is (almost) entirely a short repeating
       unit.
    """
    segments = [seg.strip() for seg in _SENTENCE_SPLIT_PATTERN.split(stripped) if seg.strip()]
    if len(segments) >= _MIN_DEGENERATE_REPEATS:
        normalized_segments = {seg.lower() for seg in segments}
        if len(normalized_segments) == 1:
            return True

    compact = re.sub(r"[^a-z0-9]", "", stripped.lower())
    if len(compact) >= _MIN_DEGENERATE_COMPACT_LENGTH:
        max_period = min(_MAX_DEGENERATE_UNIT_LENGTH, len(compact) // _MIN_DEGENERATE_REPEATS)
        for period in range(1, max_period + 1):
            unit = compact[:period]
            repeats = len(compact) // period
            if repeats < _MIN_DEGENERATE_REPEATS:
                continue
            covered = unit * repeats
            if compact.startswith(covered) and len(covered) / len(compact) >= (
                _MIN_DEGENERATE_COVERAGE_RATIO
            ):
                return True
    return False


def validate_substantive_report_text(value: str, *, field_name: str = "report text") -> str:
    """Reject placeholder literals, bare acknowledgements, and short filler.

    Raises ``ValueError`` with a SPECIFIC, distinguishable reason per
    violation class -- callers (pydantic ``field_validator``s below, and any
    future free-text report field) get one shared, tested implementation
    rather than three ad hoc regexes copy-pasted per field.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} is empty or whitespace-only")

    normalized = _normalize_for_literal_match(stripped)
    if normalized in _PLACEHOLDER_LITERALS:
        raise ValueError(
            f"{field_name} is the literal placeholder value {stripped!r} -- "
            "not a substantive report"
        )
    if normalized in _BARE_ACKNOWLEDGEMENT_LITERALS:
        raise ValueError(
            f"{field_name} is a bare acknowledgement ({stripped!r}) with no typed result content"
        )
    if _is_repetitive_padding(stripped):
        raise ValueError(
            f"{field_name} is repetitive low-content padding ({stripped!r}) -- a short "
            "literal or unit repeated to defeat the length minimum, not a substantive report"
        )
    if len(stripped) < _MIN_SUBSTANTIVE_LENGTH:
        raise ValueError(
            f"{field_name} is only {len(stripped)} chars (minimum {_MIN_SUBSTANTIVE_LENGTH}) -- "
            "too short to be a substantive report"
        )
    return stripped


# --------------------------------------------------------------------------
# Role + verdict enums
# --------------------------------------------------------------------------


class SODispatchRole(StrEnum):
    """The four dispatch roles this program's report contracts cover."""

    IMPLEMENTER = "implementer"
    VERIFIER = "verifier"
    LANDER = "lander"
    SCOUT = "scout"


class SOImplementerVerdict(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class SOVerifierVerdict(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class SOLanderVerdict(StrEnum):
    MERGED = "merged"
    BLOCKED = "blocked"
    ABORTED = "aborted"


class SOScoutVerdict(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------
# Per-role report contracts
# --------------------------------------------------------------------------


class _ClosedStrictReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ModelSOImplementerReport(_ClosedStrictReport):
    """Final report for a build/fix agent that opened or updated a PR."""

    role: Literal["implementer"]
    pr_number: PrNumber
    branch: StrictStr = Field(min_length=1)
    head_sha: GitSha
    verdict: SOImplementerVerdict
    files_changed_paths: list[StrictStr] = Field(min_length=1)
    summary: StrictStr

    @field_validator("summary")
    @classmethod
    def _summary_is_substantive(cls, value: str) -> str:
        return validate_substantive_report_text(value, field_name="summary")


class ModelSOVerifierReport(_ClosedStrictReport):
    """Final report for an independent verifier re-checking an implementer's claim."""

    role: Literal["verifier"]
    pr_number: PrNumber
    verified_sha: GitSha
    verdict: SOVerifierVerdict
    evidence_paths: list[StrictStr] = Field(min_length=1)
    summary: StrictStr

    @field_validator("summary")
    @classmethod
    def _summary_is_substantive(cls, value: str) -> str:
        return validate_substantive_report_text(value, field_name="summary")


class ModelSOLanderReport(_ClosedStrictReport):
    """Final report for the agent that merges/lands a PR."""

    role: Literal["lander"]
    pr_number: PrNumber
    merge_sha: GitSha
    verdict: SOLanderVerdict
    summary: StrictStr

    @field_validator("summary")
    @classmethod
    def _summary_is_substantive(cls, value: str) -> str:
        return validate_substantive_report_text(value, field_name="summary")


class ModelSOScoutReport(_ClosedStrictReport):
    """Final report for a discovery/investigation agent (no PR required)."""

    role: Literal["scout"]
    verdict: SOScoutVerdict
    findings_paths: list[StrictStr] = Field(min_length=1)
    summary: StrictStr
    pr_number: PrNumber | None = None

    @field_validator("summary")
    @classmethod
    def _summary_is_substantive(cls, value: str) -> str:
        return validate_substantive_report_text(value, field_name="summary")


DispatchReport = (
    ModelSOImplementerReport | ModelSOVerifierReport | ModelSOLanderReport | ModelSOScoutReport
)

ROLE_TO_MODEL: dict[SODispatchRole, type[BaseModel]] = {
    SODispatchRole.IMPLEMENTER: ModelSOImplementerReport,
    SODispatchRole.VERIFIER: ModelSOVerifierReport,
    SODispatchRole.LANDER: ModelSOLanderReport,
    SODispatchRole.SCOUT: ModelSOScoutReport,
}


__all__ = [
    "ROLE_TO_MODEL",
    "DispatchReport",
    "GitSha",
    "ModelSOImplementerReport",
    "ModelSOLanderReport",
    "ModelSOScoutReport",
    "ModelSOVerifierReport",
    "PrNumber",
    "SODispatchRole",
    "SOImplementerVerdict",
    "SOLanderVerdict",
    "SOScoutVerdict",
    "SOVerifierVerdict",
    "validate_substantive_report_text",
]
