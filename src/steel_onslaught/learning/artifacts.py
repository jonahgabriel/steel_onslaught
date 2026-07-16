"""Learning artifact ports; evaluators never own filesystem or codec I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from steel_onslaught.contracts.lineage import ModelSOLineageRecord
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec


@dataclass(frozen=True)
class EvaluationWorkspace:
    key: str


@dataclass(frozen=True)
class MaterializedLoadout:
    loadout: ModelSOLoadout
    path: Path


class LearningArtifactStore(Protocol):
    def prepare_evaluation(self, index: int) -> EvaluationWorkspace: ...

    def materialize_loadout(
        self,
        workspace: EvaluationWorkspace,
        *,
        base: ModelSOLoadout,
        spec: ModelSOPilotSpec,
        role: str,
    ) -> MaterializedLoadout: ...

    def duel_ledger_path(
        self,
        workspace: EvaluationWorkspace,
        *,
        seed: int,
        candidate_side: str,
    ) -> Path: ...

    def write_lineage(
        self,
        record: ModelSOLineageRecord,
        *,
        recorded_at: datetime,
    ) -> Path: ...


__all__ = [
    "EvaluationWorkspace",
    "LearningArtifactStore",
    "MaterializedLoadout",
]
