"""Explicit YAML/filesystem adapter for offline learning evidence."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from steel_onslaught.contracts.lineage import ModelSOLineageRecord
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope
from steel_onslaught.learning.artifacts import EvaluationWorkspace, MaterializedLoadout
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.lineage_store import write_lineage_record
from steel_onslaught.llm.experiment import (
    ModelSOExperimentRow,
    ModelSOExperimentSummary,
    ModelSOTunerUsage,
)


class ModelSOFilesystemLearningArtifactsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_root: Path
    lineage_root: Path
    experiment_root: Path


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
        """Atomically publish one artifact without replacing prior evidence."""
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise FileExistsError(
                    f"refusing to replace non-identical learning artifact: {path}"
                ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _claim_identity(self, kind: str, identity: bytes, content_digest: str) -> None:
        claim = self._config.experiment_root / "claims" / kind / f"{self._digest(identity)}.sha256"
        claim.parent.mkdir(parents=True, exist_ok=True)
        self._write_exclusive_or_verify(claim, f"{content_digest}\n".encode("ascii"))

    def write_after_match_evidence(self, evidence: ModelSOAfterMatchLearningEvidence) -> Path:
        """Persist one canonical terminal-match projection atomically.

        The terminal event id is a first-write-wins identity claim.  Replaying
        the same stream is idempotent; a changed projection for an existing
        terminal event fails closed instead of silently replacing evidence.
        """
        content = self._model_yaml(evidence)
        digest = self._digest(content)
        path = self._config.evaluation_root / "matches" / f"{evidence.match_id}.{digest}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_exclusive_or_verify(path, content)
        self._claim_identity("matches", evidence.scored_event_id.encode("utf-8"), digest)
        return path

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

    @staticmethod
    def _model_yaml(model: BaseModel) -> bytes:
        serialized = cast(
            str,
            yaml.safe_dump(
                model.model_dump(mode="json"),
                sort_keys=True,
                allow_unicode=True,
            ),
        )
        return serialized.encode("utf-8")

    def write_experiment_summary(self, summary: ModelSOExperimentSummary) -> Path:
        content = self._model_yaml(summary)
        digest = self._digest(content)
        path = self._config.experiment_root / "summaries" / f"{digest}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_exclusive_or_verify(path, content)
        identity = yaml.safe_dump(
            {
                "experiment_seed": summary.experiment_seed,
                "archetype": summary.archetype,
                "provider": summary.provider,
                "k_trials": summary.k_trials,
            },
            sort_keys=True,
        ).encode("utf-8")
        self._claim_identity("summaries", identity, digest)
        return path

    def write_experiment_rows(self, rows: tuple[ModelSOExperimentRow, ...]) -> Path:
        content = yaml.safe_dump(
            [row.model_dump(mode="json") for row in rows],
            sort_keys=True,
            allow_unicode=True,
        ).encode("utf-8")
        digest = self._digest(content)
        path = self._config.experiment_root / "rows" / f"{digest}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_exclusive_or_verify(path, content)
        identity = yaml.safe_dump(
            [row.run_id for row in rows],
            sort_keys=True,
        ).encode("utf-8")
        self._claim_identity("rows", identity, digest)
        return path

    def write_tuner_usage(
        self,
        usage: ModelSOTunerUsage,
        *,
        lineage_record: Path | None,
    ) -> Path:
        content = self._model_yaml(usage)
        digest = self._digest(content)
        path = (
            lineage_record.parent / f"{lineage_record.stem}.{digest}.usage.yaml"
            if lineage_record is not None
            else self._config.experiment_root / "usage" / f"{usage.run_id}.{digest}.usage.yaml"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_exclusive_or_verify(path, content)
        self._claim_identity("usage", usage.run_id.encode("utf-8"), digest)
        return path

    def write_llm_event(self, event: ModelSOEventEnvelope) -> Path:
        content = self._model_yaml(event)
        path = self._config.experiment_root / "llm_events" / f"{self._digest(content)}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_exclusive_or_verify(path, content)
        self._claim_identity("llm_events", event.event_id.encode("utf-8"), self._digest(content))
        return path


__all__ = [
    "ModelSOFilesystemLearningArtifactsConfig",
    "YamlFilesystemLearningArtifactStore",
]
