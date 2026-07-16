"""Explicit YAML/filesystem adapter for offline learning evidence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from steel_onslaught.contracts.lineage import ModelSOLineageRecord
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.learning.artifacts import EvaluationWorkspace, MaterializedLoadout
from steel_onslaught.learning.lineage_store import write_lineage_record


class ModelSOFilesystemLearningArtifactsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_root: Path
    lineage_root: Path


class YamlFilesystemLearningArtifactStore:
    def __init__(self, config: ModelSOFilesystemLearningArtifactsConfig) -> None:
        self._config = config

    def _workspace_path(self, workspace: EvaluationWorkspace) -> Path:
        return self._config.evaluation_root / workspace.key

    def prepare_evaluation(self, index: int) -> EvaluationWorkspace:
        self._config.evaluation_root.mkdir(parents=True, exist_ok=True)
        base_key = f"eval_{index:04d}"
        suffix = 1
        while True:
            key = base_key if suffix == 1 else f"{base_key}_{suffix:04d}"
            workspace = EvaluationWorkspace(key=key)
            try:
                self._workspace_path(workspace).mkdir(exist_ok=False)
            except FileExistsError:
                suffix += 1
                continue
            return workspace

    @staticmethod
    def _write_exclusive_or_verify(path: Path, content: bytes) -> None:
        """Create one artifact without replacing any prior evidence."""
        try:
            with path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise FileExistsError(
                    f"refusing to replace non-identical learning artifact: {path}"
                ) from None

    def materialize_loadout(
        self,
        workspace: EvaluationWorkspace,
        *,
        base: ModelSOLoadout,
        spec: ModelSOPilotSpec,
        role: str,
    ) -> MaterializedLoadout:
        workspace_path = self._workspace_path(workspace)
        spec_path = workspace_path / f"{spec.id}.yaml"
        self._write_exclusive_or_verify(
            spec_path,
            yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False).encode("utf-8"),
        )
        hash_fragment = spec.id.rsplit("_", 1)[-1]
        loadout = ModelSOLoadout.model_validate(
            {
                **base.model_dump(),
                "id": f"loadout.learn.{role}_{hash_fragment}",
                "pilot_id": spec.id,
                "pilot_spec_path": spec_path.name,
            }
        )
        loadout_path = workspace_path / f"{loadout.id}.yaml"
        self._write_exclusive_or_verify(
            loadout_path,
            yaml.safe_dump(loadout.model_dump(mode="json"), sort_keys=False).encode("utf-8"),
        )
        return MaterializedLoadout(loadout=loadout, path=loadout_path)

    def write_lineage(
        self,
        record: ModelSOLineageRecord,
        *,
        recorded_at: datetime,
    ) -> Path:
        return write_lineage_record(
            record,
            root=self._config.lineage_root,
            recorded_at=recorded_at,
        )


__all__ = [
    "ModelSOFilesystemLearningArtifactsConfig",
    "YamlFilesystemLearningArtifactStore",
]
