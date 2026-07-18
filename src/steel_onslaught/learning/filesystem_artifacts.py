"""Explicit YAML/filesystem adapter for offline learning evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from steel_onslaught.contracts.lineage import ModelSOLineageRecord
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOPilotDecisionPayload,
)
from steel_onslaught.learning.artifacts import (
    EvaluationWorkspace,
    LearningContextArtifacts,
    MaterializedLoadout,
)
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.lineage_store import load_lineage_records, write_lineage_record
from steel_onslaught.ledger.codec import load_persisted_event
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

    def read_context_artifacts(
        self,
        *,
        archetype: str,
        limit: int = 5,
    ) -> LearningContextArtifacts:
        """Read the canonical durable artifacts used by rich tuner arms.

        Evaluation ledgers are opened read-only and every envelope is decoded
        through the canonical persisted-event codec.  A malformed or legacy
        row raises rather than being silently omitted.  Ordering is by stable
        path/match/tick/sequence, never by filesystem mtime.
        """
        if limit < 1:
            raise ValueError(f"context artifact limit must be positive; got {limit}")

        replay_traces: list[tuple[tuple[str, str, int, int, str], str]] = []
        decision_diffs: list[tuple[tuple[str, str, int, str], str]] = []
        paths = sorted(self._config.evaluation_root.rglob("*.sqlite3"), key=lambda p: p.as_posix())
        for path in paths:
            # EvaluationStorageAllocator owns this shape. Do not interpret a
            # caller's unrelated SQLite database beneath the artifact root as
            # a learning duel (or let its schema affect the arm).
            if not path.name.startswith("seed_") or "_cand_" not in path.stem:
                continue
            matches = self._read_evaluation_ledgers(path)
            for match_id, events in matches.items():
                score_events = [
                    event for event in events if event.event_type is SOEventType.MATCH_SCORED
                ]
                if len(score_events) != 1:
                    continue
                score = ModelSOMatchScoredPayload.model_validate(score_events[0].payload)
                parent_side = self._parent_side(match_id)
                if score.is_draw or score.winner_player_id != f"player.{parent_side}":
                    continue
                decisions = [
                    event for event in events if event.event_type is SOEventType.PILOT_DECISION_MADE
                ]
                for event in decisions:
                    fragment = self._event_fragment(event)
                    key = (
                        path.as_posix(),
                        match_id,
                        event.tick,
                        event.sequence_in_tick,
                        event.event_id,
                    )
                    replay_traces.append((key, fragment))
                winning_side = "blue" if parent_side == "red" else "red"
                parent_decisions = {
                    event.tick: ModelSOPilotDecisionPayload.model_validate(event.payload)
                    for event in decisions
                    if event.subject.mech_id == f"mech.{parent_side}.01"
                }
                winning_decisions = {
                    event.tick: ModelSOPilotDecisionPayload.model_validate(event.payload)
                    for event in decisions
                    if event.subject.mech_id == f"mech.{winning_side}.01"
                }
                for tick in sorted(set(parent_decisions) | set(winning_decisions)):
                    parent = parent_decisions.get(tick)
                    winner = winning_decisions.get(tick)
                    if parent is None or winner is None or parent == winner:
                        continue
                    diff = json.dumps(
                        {
                            "match_id": match_id,
                            "tick": tick,
                            "parent": parent.model_dump(mode="json"),
                            "winner": winner.model_dump(mode="json"),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    decision_diffs.append(((path.as_posix(), match_id, tick, parent_side), diff))

        exemplars: list[tuple[str, str]] = []
        for envelope in load_lineage_records(self._config.lineage_root):
            record = envelope.record
            if record.archetype != archetype or record.promotion.status.value != "promoted":
                continue
            exemplar = json.dumps(
                record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )
            exemplars.append((record.spec_hash, exemplar))

        replay_traces.sort(key=lambda item: item[0])
        decision_diffs.sort(key=lambda item: item[0])
        exemplars.sort(key=lambda item: item[0])
        return LearningContextArtifacts(
            replay_traces=tuple(fragment for _key, fragment in replay_traces[:limit]),
            decision_diffs=tuple(fragment for _key, fragment in decision_diffs[:limit]),
            exemplars=tuple(fragment for _key, fragment in exemplars[:limit]),
        )

    @staticmethod
    def _parent_side(match_id: str) -> str:
        if match_id.endswith("cand_red"):
            return "blue"
        if match_id.endswith("cand_blue"):
            return "red"
        raise ValueError(
            f"evaluation evidence match id does not declare candidate side: {match_id!r}"
        )

    @staticmethod
    def _event_fragment(event: ModelSOEventEnvelope) -> str:
        return json.dumps(
            {
                "event_id": event.event_id,
                "match_id": event.match_id,
                "tick": event.tick,
                "sequence_in_tick": event.sequence_in_tick,
                "subject": event.subject.model_dump(mode="json"),
                "payload": event.model_dump(mode="json")["payload"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _read_evaluation_ledgers(path: Path) -> dict[str, list[ModelSOEventEnvelope]]:
        if not path.is_file():
            raise ValueError(f"evaluation ledger disappeared while reading: {path}")
        uri = f"file:{path.as_posix()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            raise ValueError(f"cannot open evaluation ledger read-only: {path}") from exc
        try:
            try:
                rows = conn.execute(
                    "SELECT event_id, match_id, tick, sequence_in_tick, envelope_json "
                    "FROM events ORDER BY match_id ASC, tick ASC, "
                    "sequence_in_tick ASC, event_id ASC"
                )
            except sqlite3.Error as exc:
                raise ValueError(
                    f"evaluation ledger has no canonical events table: {path}"
                ) from exc
            grouped: dict[str, list[ModelSOEventEnvelope]] = {}
            for event_id, match_id, tick, sequence_in_tick, envelope_json in rows:
                if envelope_json is None:
                    raise ValueError(
                        f"evaluation ledger row {event_id!r} has no canonical envelope"
                    )
                event = load_persisted_event(str(envelope_json))
                if (
                    event.event_id != str(event_id)
                    or event.match_id != str(match_id)
                    or event.tick != int(tick)
                    or event.sequence_in_tick != int(sequence_in_tick)
                ):
                    raise ValueError(
                        f"evaluation ledger projection disagrees with envelope: {path}"
                    )
                grouped.setdefault(event.match_id, []).append(event)
            return grouped
        finally:
            conn.close()


__all__ = [
    "ModelSOFilesystemLearningArtifactsConfig",
    "YamlFilesystemLearningArtifactStore",
]
