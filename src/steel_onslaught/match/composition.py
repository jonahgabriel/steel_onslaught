"""Sole Slice-1 production composition and configuration ingress."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import ulid
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import ModelSOGizmoSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.mode import ModelSOModeTransition
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.contracts.pilot_registry import PilotResolutionError, PilotSpecRegistry
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import Clock, EventFactory, IdentityProvider
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.ledger.protocol import QueryableEventLedger
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger
from steel_onslaught.match.duel import (
    DuelExecutor,
    DuelResult,
    ModelSOEvaluationStorageKey,
    run_duel,
)
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import (
    ARENA_SIZE_CELLS,
    MatchIdentity,
    MatchRunner,
    _require_valid_budgets,
)
from steel_onslaught.match.state import ModelSOMatchState, SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol
from steel_onslaught.projections.leaderboard.handler import (
    LeaderboardHandler,
    ModelSOSQLiteLeaderboardConfig,
)
from steel_onslaught.projections.leaderboard.protocol import LeaderboardRepository
from steel_onslaught.reducers.scoring import ReducerScoring, verify_replay_validity


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemIdentityProvider:
    def new_match_id(self) -> str:
        return f"match.{ulid.new().str}"

    def new_correlation_id(self) -> UUID:
        return uuid4()

    def new_event_id(self) -> str:
        return ulid.new().str

    def new_message_id(self) -> UUID:
        return uuid4()


PilotFactory = Callable[[ModelSOPilotSpec], PilotProtocol]


@dataclass(frozen=True)
class RuntimeDependencies:
    bus: EventBus
    ledger: QueryableEventLedger
    leaderboard: LeaderboardRepository
    clock: Clock
    identities: IdentityProvider
    event_factory: EventFactory
    catalog: MatchContractCatalog
    pilot_registry: PilotSpecRegistry
    pilot_factory: PilotFactory


@dataclass(frozen=True)
class LearningDependencies:
    """Ports required by offline learning without opening live runtime stores."""

    clock: Clock
    artifacts: LearningArtifactStore


@dataclass(frozen=True)
class LiveMatchStack:
    identity: MatchIdentity
    bus: EventBus
    runner: MatchRunner
    ledger: QueryableEventLedger
    scoring: ReducerScoring
    leaderboard: LeaderboardRepository
    event_factory: EventFactory
    catalog: MatchContractCatalog

    @property
    def match_id(self) -> str:
        return self.identity.match_id


def load_application_overlay(path: Path) -> ModelSOApplicationOverlay:
    """Read exactly one operator-supplied overlay and validate before adapter I/O."""
    overlay_path = path.resolve(strict=True)
    raw: Any = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    base = overlay_path.parent

    def resolved(candidate: Path) -> Path:
        return candidate if candidate.is_absolute() else (base / candidate).resolve()

    event_ledger = overlay.event_ledger.model_copy(
        update={"path": resolved(overlay.event_ledger.path)}
    )
    leaderboard = overlay.leaderboard.model_copy(
        update={"path": resolved(overlay.leaderboard.path)}
    )
    contracts = overlay.contracts.model_copy(
        update={
            "catalog_dir": resolved(overlay.contracts.catalog_dir),
            "pilot_registry_dir": resolved(overlay.contracts.pilot_registry_dir),
        }
    )
    learning_artifacts = overlay.learning_artifacts.model_copy(
        update={
            "evaluation_root": resolved(overlay.learning_artifacts.evaluation_root),
            "lineage_root": resolved(overlay.learning_artifacts.lineage_root),
        }
    )
    evaluation_storage = overlay.evaluation_storage.model_copy(
        update={"root": resolved(overlay.evaluation_storage.root)}
    )
    return overlay.model_copy(
        update={
            "event_ledger": event_ledger,
            "leaderboard": leaderboard,
            "contracts": contracts,
            "learning_artifacts": learning_artifacts,
            "evaluation_storage": evaluation_storage,
        }
    )


def _load_specs[ModelT: BaseModel](directory: Path, model: type[ModelT]) -> dict[str, ModelT]:
    if not directory.is_dir():
        raise FileNotFoundError(f"required contract directory does not exist: {directory}")
    specs: dict[str, ModelT] = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        spec_id = str(spec.id)  # type: ignore[attr-defined]
        if spec_id in specs:
            raise ValueError(f"duplicate contract id {spec_id!r} under {directory}")
        specs[spec_id] = spec
    if not specs:
        raise ValueError(f"required contract directory contains no YAML specs: {directory}")
    return specs


def load_match_contract_catalog(directory: Path) -> MatchContractCatalog:
    transitions: dict[tuple[str, str], ModelSOModeTransition] = {}
    transitions_dir = directory / "modes" / "transitions"
    if not transitions_dir.is_dir():
        raise FileNotFoundError(f"required contract directory does not exist: {transitions_dir}")
    for path in sorted(transitions_dir.glob("*.yaml")):
        spec = ModelSOModeTransition.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        key = (spec.from_mode, spec.to_mode)
        if key in transitions:
            raise ValueError(f"duplicate mode transition {key!r} under {transitions_dir}")
        transitions[key] = spec
    if not transitions:
        raise ValueError(f"required contract directory contains no YAML specs: {transitions_dir}")
    return MatchContractCatalog(
        chassis=_load_specs(directory / "chassis", ModelSOChassisSpec),
        boilers=_load_specs(directory / "boilers", ModelSOBoilerSpec),
        sensors=_load_specs(directory / "sensors", ModelSOSensorSpec),
        weapons=_load_specs(directory / "weapons", ModelSOWeaponSpec),
        gizmos=_load_specs(directory / "gizmos", ModelSOGizmoSpec),
        transitions=transitions,
    )


def load_pilot_spec(path: Path) -> ModelSOPilotSpec:
    return ModelSOPilotSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_pilot_registry(directory: Path) -> PilotSpecRegistry:
    specs = _load_specs(directory, ModelSOPilotSpec)
    return PilotSpecRegistry(specs)


def load_loadout(path: Path) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def pilot_from_spec(spec: ModelSOPilotSpec) -> PilotProtocol:
    match spec.archetype:
        case "aggressive":
            return AggressivePilot(spec=spec)
        case "defensive":
            return DefensivePilot(spec=spec)
        case "predictive":
            return PredictivePilot(spec=spec)
    raise ValueError(f"unknown pilot archetype {spec.archetype!r} (spec id: {spec.id!r})")


def build_runtime_dependencies(overlay: ModelSOApplicationOverlay) -> RuntimeDependencies:
    """Construct every selected outer adapter exactly once."""
    clock: Clock = SystemClock()
    identities: IdentityProvider = SystemIdentityProvider()
    event_factory = EventFactory(clock=clock, identities=identities)
    bus: EventBus = InProcessEventBus()
    ledger = SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=overlay.event_ledger.path,
            journal_mode=overlay.event_ledger.journal_mode,
            check_same_thread=overlay.event_ledger.check_same_thread,
            transaction_mode=overlay.event_ledger.transaction_mode,
            event_schema=overlay.event_ledger.event_schema,
        )
    )
    leaderboard = LeaderboardHandler(
        ModelSOSQLiteLeaderboardConfig(
            path=overlay.leaderboard.path,
            journal_mode=overlay.leaderboard.journal_mode,
            check_same_thread=overlay.leaderboard.check_same_thread,
            transaction_mode=overlay.leaderboard.transaction_mode,
            storage_schema=overlay.leaderboard.storage_schema,
        ),
        clock=clock,
    )
    return RuntimeDependencies(
        bus=bus,
        ledger=ledger,
        leaderboard=leaderboard,
        clock=clock,
        identities=identities,
        event_factory=event_factory,
        catalog=load_match_contract_catalog(overlay.contracts.catalog_dir),
        pilot_registry=load_pilot_registry(overlay.contracts.pilot_registry_dir),
        pilot_factory=pilot_from_spec,
    )


def build_learning_dependencies(overlay: ModelSOApplicationOverlay) -> LearningDependencies:
    """Bind only learning ports; global event and leaderboard stores stay unopened."""
    return LearningDependencies(
        clock=SystemClock(),
        artifacts=YamlFilesystemLearningArtifactStore(
            ModelSOFilesystemLearningArtifactsConfig(
                evaluation_root=overlay.learning_artifacts.evaluation_root,
                lineage_root=overlay.learning_artifacts.lineage_root,
            )
        ),
    )


def build_duel_executor(overlay: ModelSOApplicationOverlay) -> DuelExecutor:
    """Bind the learning/balance duel capability at the sole adapter root."""
    storage_namespaces: dict[str, Path] = {}

    def execute(
        *,
        loadout_a: ModelSOLoadout,
        loadout_b: ModelSOLoadout,
        seed: int,
        max_ticks: int,
        storage: ModelSOEvaluationStorageKey,
        match_id: str,
        loadout_path_a: Path | None,
        loadout_path_b: Path | None,
        side_a: str,
        side_b: str,
    ) -> DuelResult:
        storage_root = storage_namespaces.get(storage.namespace)
        if storage_root is None:
            base = overlay.evaluation_storage.root / storage.namespace
            storage_root = base
            suffix = 1
            while (storage_root / f"{storage.duel}.sqlite3").exists():
                suffix += 1
                storage_root = base.with_name(f"{base.name}_{suffix:04d}")
            storage_namespaces[storage.namespace] = storage_root
        storage_root.mkdir(parents=True, exist_ok=True)
        ledger_path = storage_root / f"{storage.duel}.sqlite3"
        if ledger_path.exists():
            raise FileExistsError(
                f"evaluation storage already exists: {storage.namespace}/{storage.duel}"
            )
        evaluation = overlay.evaluation_storage
        ledger_binding = overlay.event_ledger.model_copy(
            update={
                "path": ledger_path,
                "journal_mode": evaluation.journal_mode,
                "check_same_thread": evaluation.check_same_thread,
                "transaction_mode": evaluation.transaction_mode,
                "event_schema": evaluation.event_schema,
            }
        )
        leaderboard_binding = overlay.leaderboard.model_copy(
            update={
                "path": ledger_path,
                "journal_mode": evaluation.journal_mode,
                "check_same_thread": evaluation.check_same_thread,
                "transaction_mode": evaluation.transaction_mode,
                "storage_schema": evaluation.leaderboard_schema,
            }
        )
        duel_overlay = overlay.model_copy(
            update={
                "event_ledger": ledger_binding,
                "leaderboard": leaderboard_binding,
            }
        )
        dependencies = build_runtime_dependencies(duel_overlay)
        identity = MatchIdentity(
            match_id=match_id,
            correlation_id=dependencies.identities.new_correlation_id(),
        )
        return run_duel(
            dependencies=dependencies,
            identity=identity,
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            seed=seed,
            max_ticks=max_ticks,
            loadout_path_a=loadout_path_a,
            loadout_path_b=loadout_path_b,
            side_a=side_a,
            side_b=side_b,
        )

    return execute


def _resolved_pilot(
    loadout: ModelSOLoadout,
    *,
    loadout_path: Path | None,
    dependencies: RuntimeDependencies,
) -> PilotProtocol:
    if loadout.pilot_spec_path is None:
        spec = dependencies.pilot_registry.resolve(loadout)
    else:
        if loadout_path is None:
            raise PilotResolutionError(
                f"loadout {loadout.id!r} declares pilot_spec_path but no explicit source path"
            )
        spec_path = Path(loadout.pilot_spec_path)
        if not spec_path.is_absolute():
            spec_path = loadout_path.parent / spec_path
        spec = load_pilot_spec(spec_path)
        if spec.id != loadout.pilot_id or spec.lineage.parent is None:
            raise PilotResolutionError(
                f"invalid explicit pilot spec binding for loadout {loadout.id!r}: {spec_path}"
            )
    return dependencies.pilot_factory(spec)


def assemble_match_with_dependencies(
    *,
    dependencies: RuntimeDependencies,
    red: ModelSOLoadout,
    blue: ModelSOLoadout,
    seed: int,
    max_ticks: int,
    identity: MatchIdentity,
    red_loadout_path: Path | None = None,
    blue_loadout_path: Path | None = None,
    side_a: str = "red",
    side_b: str = "blue",
) -> LiveMatchStack:
    """Pure DI seam used by production root and hermetic tests."""
    _require_valid_budgets(red, dependencies.catalog)
    _require_valid_budgets(blue, dependencies.catalog)
    mech_a = f"mech.{side_a}.01"
    mech_b = f"mech.{side_b}.01"
    pilots = {
        mech_a: _resolved_pilot(red, loadout_path=red_loadout_path, dependencies=dependencies),
        mech_b: _resolved_pilot(blue, loadout_path=blue_loadout_path, dependencies=dependencies),
    }
    dependencies.bus.subscribe(dependencies.ledger.append)
    runner = MatchRunner(
        identity=identity,
        seed=seed,
        loadout_a=red,
        loadout_b=blue,
        bus=dependencies.bus,
        event_factory=dependencies.event_factory,
        catalog=dependencies.catalog,
        pilots=pilots,
        max_ticks=max_ticks,
        side_a=side_a,
        side_b=side_b,
        spawn_a=ModelSOPosition(x=5, y=5),
        spawn_b=ModelSOPosition(x=35, y=35),
        arena_size=ARENA_SIZE_CELLS,
    )
    scoring = ReducerScoring(
        identity.match_id,
        identity.correlation_id,
        emit=dependencies.bus.publish,
        event_factory=dependencies.event_factory,
        replay_validity_check=lambda: verify_replay_validity(
            dependencies.ledger,
            identity.match_id,
            runner.fold.state,
            catalog=dependencies.catalog,
            event_factory=dependencies.event_factory,
        ),
    )
    dependencies.bus.subscribe(scoring.handle)

    def _on_match_scored(event: ModelSOEventEnvelope) -> None:
        if event.payload.get("kind") == "steel_onslaught.match_scored":
            dependencies.leaderboard.on_match_scored(event.payload)

    dependencies.bus.subscribe(_on_match_scored, event_types=[SOEventType.MATCH_SCORED])
    return LiveMatchStack(
        identity=identity,
        bus=dependencies.bus,
        runner=runner,
        ledger=dependencies.ledger,
        scoring=scoring,
        leaderboard=dependencies.leaderboard,
        event_factory=dependencies.event_factory,
        catalog=dependencies.catalog,
    )


def assemble_match_live(
    *,
    overlay: ModelSOApplicationOverlay,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int,
) -> LiveMatchStack:
    dependencies = build_runtime_dependencies(overlay)
    identity = MatchIdentity(
        match_id=dependencies.identities.new_match_id(),
        correlation_id=dependencies.identities.new_correlation_id(),
    )
    return assemble_match_with_dependencies(
        dependencies=dependencies,
        red=load_loadout(red_loadout_path),
        blue=load_loadout(blue_loadout_path),
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
        identity=identity,
    )


def run_composed_match(
    *,
    overlay: ModelSOApplicationOverlay,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int,
) -> ModelSOMatchState:
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
    )
    final = stack.runner.run()
    if final.status is not SOMatchStatus.ENDED:
        raise RuntimeError(f"match {stack.match_id!r} did not terminate: {final.status.value}")
    if final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS and final.winner_id is not None:
        raise RuntimeError("draw recorded a winner — lifecycle invariant violated")
    return final


__all__ = [
    "LearningDependencies",
    "LiveMatchStack",
    "RuntimeDependencies",
    "assemble_match_live",
    "assemble_match_with_dependencies",
    "build_duel_executor",
    "build_learning_dependencies",
    "build_runtime_dependencies",
    "load_application_overlay",
    "load_loadout",
    "load_match_contract_catalog",
    "load_pilot_registry",
    "load_pilot_spec",
    "pilot_from_spec",
    "run_composed_match",
]
