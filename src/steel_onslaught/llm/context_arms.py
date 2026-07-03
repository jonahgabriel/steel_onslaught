"""Context arms for the LLM tuner (addendum §3.3).

Each arm assembles a different context for the tuner's prompt, from minimal
(task statement only) to rich (replay traces, decision diffs, exemplars, full
design doc). The negative-control arm (``llm_full_design_doc``) is mandatory
in every experiment run.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class ArmContext:
    """The assembled context for one arm's tuner prompt."""

    arm: ContextArm
    prompt_addendum: str  # text appended to the base tuner prompt


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

    Only ``llm_off`` and ``llm_full_design_doc`` are always available; the
    richer arms need artifacts (replay traces, diffs, exemplars) that the
    experiment harness gathers from the ledger/lineage store. Missing artifacts
    degrade gracefully (the arm runs with what it has).
    """
    base = (
        f"Archetype: {archetype}\n"
        f"Current parent parameters: {_format_params(parent_params)}\n"
        f"Parameter bounds and steps:\n{_format_bounds(bounds)}\n"
    )

    if arm is ContextArm.LLM_OFF:
        return ArmContext(arm=arm, prompt_addendum=base)

    if arm is ContextArm.LLM_FULL_DESIGN_DOC:
        doc_text = ""
        if design_doc_path is not None and design_doc_path.exists():
            doc_text = design_doc_path.read_text(encoding="utf-8")[:4000]  # cap token cost
        return ArmContext(
            arm=arm, prompt_addendum=base + f"\n--- FULL DESIGN DOC ---\n{doc_text}\n"
        )

    addendum = base
    if arm is ContextArm.LLM_REPLAY_TRACE and replay_traces:
        addendum += "\n--- REPLAY TRACES (parent's lost duels) ---\n"
        addendum += "\n".join(replay_traces[:5]) + "\n"

    if arm is ContextArm.LLM_DECISION_DIFF and decision_diffs:
        addendum += "\n--- DECISION DIFFS (where parent diverged from winners) ---\n"
        addendum += "\n".join(decision_diffs[:5]) + "\n"

    if arm is ContextArm.LLM_EXEMPLAR and exemplars:
        addendum += "\n--- EXEMPLARS (promoted lineage records) ---\n"
        addendum += "\n".join(exemplars[:5]) + "\n"

    return ArmContext(arm=arm, prompt_addendum=addendum)


__all__ = ["ArmContext", "ContextArm", "assemble_arm_context"]
