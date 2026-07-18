"""Context-arm provenance and fail-closed artifact tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.learning.protocols import ModelSONumericBound
from steel_onslaught.llm.context_arms import (
    ContextArm,
    MissingContextArtifactError,
    assemble_arm_context,
)

_BOUNDS = {"aggression": ModelSONumericBound(minimum=0.0, maximum=1.0, step=0.1)}
_COMMON = {
    "archetype": "aggressive",
    "parent_params": {"aggression": 0.5},
    "bounds": _BOUNDS,
}


@pytest.mark.unit
def test_llm_off_is_deterministic_and_has_no_artifact_requirement() -> None:
    first = assemble_arm_context(ContextArm.LLM_OFF, **_COMMON)
    second = assemble_arm_context(ContextArm.LLM_OFF, **_COMMON)

    assert first.prompt_addendum == second.prompt_addendum
    assert first.context_manifest_hash == second.context_manifest_hash
    assert len(first.context_manifest_hash) == 64


@pytest.mark.unit
def test_rich_arms_have_distinct_prompts_and_content_manifests(tmp_path: Path) -> None:
    design_doc = tmp_path / "design.md"
    design_doc.write_text("# Design\nUse bounded decisions.\n", encoding="utf-8")
    contexts = (
        assemble_arm_context(
            ContextArm.LLM_REPLAY_TRACE,
            **_COMMON,
            replay_traces=['{"tick":1,"action":"move"}'],
        ),
        assemble_arm_context(
            ContextArm.LLM_DECISION_DIFF,
            **_COMMON,
            decision_diffs=['{"tick":1,"parent":"move","winner":"vent"}'],
        ),
        assemble_arm_context(
            ContextArm.LLM_EXEMPLAR,
            **_COMMON,
            exemplars=['{"spec_hash":"promoted"}'],
        ),
        assemble_arm_context(
            ContextArm.LLM_FULL_DESIGN_DOC,
            **_COMMON,
            design_doc_path=design_doc,
        ),
    )

    assert len({context.prompt_addendum for context in contexts}) == len(contexts)
    assert len({context.context_manifest_hash for context in contexts}) == len(contexts)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("arm", "kwargs", "artifact_name"),
    [
        (ContextArm.LLM_REPLAY_TRACE, {}, "replay trace"),
        (ContextArm.LLM_DECISION_DIFF, {}, "decision diff"),
        (ContextArm.LLM_EXEMPLAR, {}, "exemplar"),
    ],
)
def test_rich_arms_fail_closed_when_artifacts_are_missing(
    arm: ContextArm,
    kwargs: dict[str, object],
    artifact_name: str,
) -> None:
    with pytest.raises(MissingContextArtifactError, match=artifact_name):
        assemble_arm_context(arm, **_COMMON, **kwargs)


@pytest.mark.unit
def test_negative_control_fails_closed_when_design_doc_is_missing(tmp_path: Path) -> None:
    with pytest.raises(MissingContextArtifactError, match="design document"):
        assemble_arm_context(
            ContextArm.LLM_FULL_DESIGN_DOC,
            **_COMMON,
            design_doc_path=tmp_path / "missing.md",
        )
