"""Learning artifact ports; evaluators never own filesystem or codec I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from steel_onslaught.contracts.lineage import ModelSOLineageRecord
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence

if TYPE_CHECKING:
    from steel_onslaught.events.envelope import ModelSOEventEnvelope
    from steel_onslaught.llm.experiment import (
        ModelSOExperimentRow,
        ModelSOExperimentSummary,
        ModelSOTunerUsage,
    )


@dataclass(frozen=True)
class EvaluationWorkspace:
    key: str


@dataclass(frozen=True)
class MaterializedLoadout:
    loadout: ModelSOLoadout
    path: Path


@dataclass(frozen=True)
class LearningContextArtifacts:
    """Durable evidence selected for one LLM tuner context arm.

    The artifact store owns how these values are read (SQLite/YAML today,
    another adapter later).  Values are already canonical, deterministic text
    fragments when they cross this port; the tuner never reads a file itself.
    """

    replay_traces: tuple[str, ...] = ()
    decision_diffs: tuple[str, ...] = ()
    exemplars: tuple[str, ...] = ()


class LearningArtifactStore(Protocol):
    def write_after_match_evidence(self, evidence: ModelSOAfterMatchLearningEvidence) -> Path: ...

    def prepare_evaluation(self, index: int) -> EvaluationWorkspace: ...

    def materialize_loadout(
        self,
        workspace: EvaluationWorkspace,
        *,
        base: ModelSOLoadout,
        spec: ModelSOPilotSpec,
        role: str,
    ) -> MaterializedLoadout: ...

    def write_lineage(
        self,
        record: ModelSOLineageRecord,
        *,
        recorded_at: datetime,
    ) -> Path: ...

    def write_experiment_summary(self, summary: ModelSOExperimentSummary) -> Path: ...

    def write_experiment_rows(self, rows: tuple[ModelSOExperimentRow, ...]) -> Path: ...

    def write_tuner_usage(
        self,
        usage: ModelSOTunerUsage,
        *,
        lineage_record: Path | None,
    ) -> Path: ...

    def write_llm_event(self, event: ModelSOEventEnvelope) -> Path: ...

    def read_context_artifacts(
        self,
        *,
        archetype: str,
        limit: int = 5,
    ) -> LearningContextArtifacts: ...


__all__ = [
    "EvaluationWorkspace",
    "LearningArtifactStore",
    "LearningContextArtifacts",
    "MaterializedLoadout",
]
