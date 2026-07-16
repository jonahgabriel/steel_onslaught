"""Closed application overlay for the current Slice-1 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _ClosedBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ModelSOInProcessBusBinding(_ClosedBinding):
    kind: Literal["in_process"]


class ModelSOSQLiteEventLedgerBinding(_ClosedBinding):
    kind: Literal["sqlite"]
    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    event_schema: Literal["canonical_event_v1"]


class ModelSOSQLiteLeaderboardBinding(_ClosedBinding):
    kind: Literal["sqlite"]
    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    storage_schema: Literal["leaderboard_v1"]


class ModelSOFilesystemLearningArtifactsBinding(_ClosedBinding):
    kind: Literal["filesystem_yaml"]
    evaluation_root: Path
    lineage_root: Path


class ModelSOContractBindings(_ClosedBinding):
    catalog_dir: Path
    pilot_registry_dir: Path


class ModelSOSystemClockBinding(_ClosedBinding):
    kind: Literal["system_utc"]


class ModelSOSystemIdentityBinding(_ClosedBinding):
    kind: Literal["system"]


BusBinding = Annotated[ModelSOInProcessBusBinding, Field(discriminator="kind")]
EventLedgerBinding = Annotated[ModelSOSQLiteEventLedgerBinding, Field(discriminator="kind")]
LeaderboardBinding = Annotated[ModelSOSQLiteLeaderboardBinding, Field(discriminator="kind")]
LearningArtifactsBinding = Annotated[
    ModelSOFilesystemLearningArtifactsBinding, Field(discriminator="kind")
]
ClockBinding = Annotated[ModelSOSystemClockBinding, Field(discriminator="kind")]
IdentityBinding = Annotated[ModelSOSystemIdentityBinding, Field(discriminator="kind")]


class ModelSOApplicationOverlay(_ClosedBinding):
    """Complete adapter and contract selection for one process."""

    schema_version: Literal["1"]
    bus: BusBinding
    event_ledger: EventLedgerBinding
    leaderboard: LeaderboardBinding
    learning_artifacts: LearningArtifactsBinding
    contracts: ModelSOContractBindings
    clock: ClockBinding
    identity: IdentityBinding


__all__ = [
    "ModelSOApplicationOverlay",
    "ModelSOContractBindings",
    "ModelSOFilesystemLearningArtifactsBinding",
    "ModelSOInProcessBusBinding",
    "ModelSOSQLiteEventLedgerBinding",
    "ModelSOSQLiteLeaderboardBinding",
    "ModelSOSystemClockBinding",
    "ModelSOSystemIdentityBinding",
]
