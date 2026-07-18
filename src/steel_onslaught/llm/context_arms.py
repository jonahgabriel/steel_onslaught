"""Context arms for the LLM tuner (addendum §3.3).

Each arm assembles a different context for the tuner's prompt, from minimal
(task statement only) to rich (replay traces, decision diffs, exemplars, full
design doc). The negative-control arm (``llm_full_design_doc``) is mandatory
in every experiment run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import BoundsDict


class ContextArm(StrEnum):
    """The five addendum §3.3 context arms."""

    LLM_OFF = "llm_off"
    LLM_REPLAY_TRACE = "llm_replay_trace"
    LLM_DECISION_DIFF = "llm_decision_diff"
    LLM_EXEMPLAR = "llm_exemplar"
    LLM_FULL_DESIGN_DOC = "llm_full_design_doc"  # NEGATIVE CONTROL


class MissingContextArtifactError(ValueError):
    """A requested context arm has no durable artifact to consume."""


@dataclass(frozen=True)
class ArmContext:
    """The assembled context for one arm's tuner prompt."""

    arm: ContextArm
    prompt_addendum: str  # text appended to the base tuner prompt
    context_manifest_hash: str


def _manifest_hash(arm: ContextArm, sections: tuple[tuple[str, str], ...]) -> str:
    """Hash artifact identities, not filesystem paths or iteration order."""
    manifest = {
        "arm": arm.value,
        "sections": tuple(
            {"name": name, "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
            for name, value in sections
        ),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required_artifacts(arm: ContextArm, name: str, values: list[str] | None) -> tuple[str, ...]:
    """Require non-empty, non-blank durable fragments for rich arms."""
    if not values:
        raise MissingContextArtifactError(
            f"context arm {arm.value!r} requires durable {name} artifacts; none were found"
        )
    normalized = tuple(value for value in values[:5] if value.strip())
    if not normalized:
        raise MissingContextArtifactError(
            f"context arm {arm.value!r} requires non-empty durable {name} artifacts"
        )
    return normalized


def _format_bounds(bounds: BoundsDict) -> str:
    """Compact bounds → text for the prompt."""
    lines = []
    for name, bound in sorted(bounds.items()):
        lines.append(f"  {name}: {bound}")
    return "\n".join(lines)


def _format_params(params: ParamDict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(params.items()))


def assemble_arm_context(
    arm: ContextArm,
    *,
    archetype: str,
    parent_params: ParamDict,
    bounds: BoundsDict,
    design_doc_path: Path | None = None,
    replay_traces: list[str] | None = None,
    decision_diffs: list[str] | None = None,
    exemplars: list[str] | None = None,
) -> ArmContext:
    """Assemble the context addendum for one arm.

    Rich arms fail closed when their declared durable artifact is absent.  A
    missing trace must never silently become the ``llm_off`` prompt, because
    that would invalidate the arm comparison.  The returned manifest hash is
    content-addressed and is persisted by the experiment harness.
    """
    base = (
        f"Archetype: {archetype}\n"
        f"Current parent parameters: {_format_params(parent_params)}\n"
        f"Parameter bounds and steps:\n{_format_bounds(bounds)}\n"
    )

    if arm is ContextArm.LLM_OFF:
        return ArmContext(
            arm=arm,
            prompt_addendum=base,
            context_manifest_hash=_manifest_hash(arm, (("base", base),)),
        )

    if arm is ContextArm.LLM_FULL_DESIGN_DOC:
        if design_doc_path is None or not design_doc_path.is_file():
            raise MissingContextArtifactError(
                "context arm 'llm_full_design_doc' requires an existing design document"
            )
        doc_text = design_doc_path.read_text(encoding="utf-8")[:4000]  # cap token cost
        if not doc_text.strip():
            raise MissingContextArtifactError(
                "context arm 'llm_full_design_doc' requires a non-empty design document"
            )
        return ArmContext(
            arm=arm,
            prompt_addendum=base + f"\n--- FULL DESIGN DOC ---\n{doc_text}\n",
            context_manifest_hash=_manifest_hash(arm, (("base", base), ("design_doc", doc_text))),
        )

    addendum = base
    sections: list[tuple[str, str]] = [("base", base)]
    if arm is ContextArm.LLM_REPLAY_TRACE:
        traces = _required_artifacts(arm, "replay trace", replay_traces)
        addendum += "\n--- REPLAY TRACES (parent's lost duels) ---\n"
        trace_text = "\n".join(traces) + "\n"
        addendum += trace_text
        sections.append(("replay_traces", trace_text))

    if arm is ContextArm.LLM_DECISION_DIFF:
        diffs = _required_artifacts(arm, "decision diff", decision_diffs)
        addendum += "\n--- DECISION DIFFS (where parent diverged from winners) ---\n"
        diff_text = "\n".join(diffs) + "\n"
        addendum += diff_text
        sections.append(("decision_diffs", diff_text))

    if arm is ContextArm.LLM_EXEMPLAR:
        lineage_exemplars = _required_artifacts(arm, "exemplar", exemplars)
        addendum += "\n--- EXEMPLARS (promoted lineage records) ---\n"
        exemplar_text = "\n".join(lineage_exemplars) + "\n"
        addendum += exemplar_text
        sections.append(("exemplars", exemplar_text))

    return ArmContext(
        arm=arm,
        prompt_addendum=addendum,
        context_manifest_hash=_manifest_hash(arm, tuple(sections)),
    )


__all__ = [
    "ArmContext",
    "ContextArm",
    "MissingContextArtifactError",
    "assemble_arm_context",
]
