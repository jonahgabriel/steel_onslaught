"""Sole Slice-1 production composition and configuration ingress."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self
from uuid import UUID, uuid4

import httpx
import ulid
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOStubLlmProviderBinding,
)
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.gizmo import ModelSOGizmoSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.mode import ModeId, ModelSOModeTransition
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams, ModelSOPilotSpec
from steel_onslaught.contracts.pilot_registry import PilotResolutionError, PilotSpecRegistry
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import Clock, EventFactory, IdentityProvider
from steel_onslaught.events.payloads import ModelSOMatchScoredPayload
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.ledger.protocol import QueryableEventLedger
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger
from steel_onslaught.llm.client_http import (
    HttpxJsonTransport,
    NoSecretResolver,
    OpenAICompatibleClient,
    StaticLlmClientFactory,
    SystemSleeper,
)
from steel_onslaught.llm.effect import (
    LedgerLlmCompletionObserver,
    ObservedLlmClient,
)
from steel_onslaught.llm.personas import PersonaRegistry
from steel_onslaught.llm.pilot import LLMPilot
from steel_onslaught.llm.schemas import (
    ModelSOLlmPilotSelection,
    ProtocolHttpTransport,
    ProtocolLlmClient,
    ProtocolLlmClientFactory,
    ProtocolLlmCompletionObserver,
    ProtocolPilotFactory,
    ProtocolResourceCloser,
    ProtocolSecretResolver,
    ProtocolSleeper,
)
from steel_onslaught.llm.stub import StubLlmClient
from steel_onslaught.llm.tuner import LlmTunerGenerator, ProtocolTunerGenerator
from steel_onslaught.match.duel import (
    DuelExecutor,
    DuelResult,
    ModelSOEvaluationStorageKey,
    PilotDuelExecutor,
    run_duel,
    run_pilot_duel,
)
from steel_onslaught.match.evaluation_storage import (
    EvaluationStorageAllocator,
    SQLiteEvaluationStorageAllocator,
)
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import (
    MatchIdentity,
    MatchRunner,
    _require_valid_budgets,
)
from steel_onslaught.match.state import ModelSOMatchState, SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import PilotProtocol
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


class NoopResourceCloser:
    def close(self) -> None:
        return


class IdempotentResourceCloser:
    """Close one owned resource at most once across nested stack lifetimes."""

    def __init__(self, resource: ProtocolResourceCloser) -> None:
        self._resource = resource
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._resource.close()


class ManagedDuelExecutor:
    """Callable duel root with an explicit owned-resource lifetime."""

    def __init__(self, *, executor: DuelExecutor, closer: ProtocolResourceCloser) -> None:
        self._executor = executor
        self._closer = closer

    def __call__(
        self,
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
        return self._executor(
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            seed=seed,
            max_ticks=max_ticks,
            storage=storage,
            match_id=match_id,
            loadout_path_a=loadout_path_a,
            loadout_path_b=loadout_path_b,
            side_a=side_a,
            side_b=side_b,
        )

    def close(self) -> None:
        self._closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class ApplicationPilotFactory:
    """Only factory permitted to instantiate pilot implementations."""

    def __init__(
        self,
        *,
        clients: ProtocolLlmClientFactory,
        personas: PersonaRegistry,
        observer: ProtocolLlmCompletionObserver | None = None,
    ) -> None:
        self._clients = clients
        self._personas = personas
        self._observer = observer

    def with_observer(self, observer: ProtocolLlmCompletionObserver) -> ProtocolPilotFactory:
        return ApplicationPilotFactory(
            clients=self._clients,
            personas=self._personas,
            observer=observer,
        )

    def from_spec(self, spec: ModelSOPilotSpec) -> PilotProtocol:
        match spec.archetype:
            case "aggressive":
                return AggressivePilot(spec=spec)
            case "defensive":
                return DefensivePilot(spec=spec)
            case "predictive":
                return PredictivePilot(spec=spec)
            case "llm":
                if not isinstance(spec.parameters, ModelSOLlmPilotParams):
                    raise TypeError("llm pilot spec must carry ModelSOLlmPilotParams")
                return self.llm_pilot(
                    ModelSOLlmPilotSelection(
                        provider_id=spec.parameters.provider,
                        persona_id=spec.parameters.persona,
                        opponent_trace=None,
                    )
                )
        raise ValueError(f"unknown pilot archetype {spec.archetype!r} (spec id: {spec.id!r})")

    def llm_pilot(self, selection: ModelSOLlmPilotSelection) -> PilotProtocol:
        client = self._clients.client_for(selection.provider_id)
        if self._observer is not None:
            client = ObservedLlmClient(
                base=client,
                provider_id=selection.provider_id,
                observer=self._observer,
            )
        if selection.opponent_trace is not None:
            from steel_onslaught.llm.adaptation import OpponentAwareClient

            client = OpponentAwareClient(base=client, trace_block=selection.opponent_trace)
        return LLMPilot(
            client=client,
            persona=self._personas.require(selection.persona_id),
        )


@dataclass(frozen=True)
class RuntimeDependencies:
    bus: EventBus
    ledger: QueryableEventLedger
    leaderboard: LeaderboardRepository
    clock: Clock
    identities: IdentityProvider
    event_factory: EventFactory
    catalog: MatchContractCatalog
    arena: ModelSOArenaSpec
    pilot_registry: PilotSpecRegistry
    pilot_factory: ProtocolPilotFactory
    closer: ProtocolResourceCloser

    def close(self) -> None:
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True)
class LlmDependencies:
    client_factory: ProtocolLlmClientFactory
    persona_registry: PersonaRegistry
    pilot_factory: ProtocolPilotFactory
    tuner_generator: ProtocolTunerGenerator
    closer: ProtocolResourceCloser

    def close(self) -> None:
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True)
class LearningDependencies:
    """Ports required by offline learning without opening live runtime stores."""

    clock: Clock
    artifacts: LearningArtifactStore
    duel_executor: DuelExecutor
    tuner_generator: ProtocolTunerGenerator
    closer: ProtocolResourceCloser

    def close(self) -> None:
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True)
class AdaptationDependencies:
    duel_executor: PilotDuelExecutor
    closer: ProtocolResourceCloser

    def close(self) -> None:
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


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
    closer: ProtocolResourceCloser

    def close(self) -> None:
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

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
            "experiment_root": resolved(overlay.learning_artifacts.experiment_root),
        }
    )
    evaluation_storage = overlay.evaluation_storage.model_copy(
        update={"root": resolved(overlay.evaluation_storage.root)}
    )
    llm = overlay.llm.model_copy(update={"personas_dir": resolved(overlay.llm.personas_dir)})
    return overlay.model_copy(
        update={
            "event_ledger": event_ledger,
            "leaderboard": leaderboard,
            "contracts": contracts,
            "learning_artifacts": learning_artifacts,
            "evaluation_storage": evaluation_storage,
            "llm": llm,
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


def _load_arena_specs(directory: Path) -> dict[str, ModelSOArenaSpec]:
    if not directory.is_dir():
        raise FileNotFoundError(f"required contract directory does not exist: {directory}")
    specs: dict[str, ModelSOArenaSpec] = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = ModelSOArenaSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if spec.arena_id in specs:
            raise ValueError(f"duplicate arena id {spec.arena_id!r} under {directory}")
        specs[spec.arena_id] = spec
    if not specs:
        raise ValueError(f"required contract directory contains no YAML specs: {directory}")
    return specs


def load_match_contract_catalog(directory: Path) -> MatchContractCatalog:
    transitions: dict[tuple[ModeId, ModeId], ModelSOModeTransition] = {}
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
        arenas=_load_arena_specs(directory / "arenas"),
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


def _validate_llm_pilot_bindings(
    registry: PilotSpecRegistry,
    llm: LlmDependencies,
) -> None:
    for spec in registry.as_mapping().values():
        if spec.archetype != "llm":
            continue
        if not isinstance(spec.parameters, ModelSOLlmPilotParams):
            raise TypeError(f"llm pilot spec {spec.id!r} has invalid parameters")
        llm.client_factory.client_for(spec.parameters.provider)
        llm.persona_registry.require(spec.parameters.persona)


def load_loadout(path: Path) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def build_llm_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> LlmDependencies:
    """Build the immutable LLM dependency graph from the validated overlay."""
    binding = overlay.llm.secret_resolver
    secret_bearing = tuple(
        provider
        for provider in overlay.llm.providers
        if isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
        and provider.secret_ref is not None
    )
    if binding.kind == "none":
        if secret_resolver is not None:
            raise ValueError("llm.secret_resolver kind 'none' rejects an injected resolver")
        if secret_bearing:
            provider_ids = sorted(provider.provider_id for provider in secret_bearing)
            raise ValueError(
                "llm.secret_resolver kind 'none' cannot bind secret-bearing providers: "
                f"{provider_ids}"
            )
        resolved_secrets: ProtocolSecretResolver = NoSecretResolver()
    else:
        if secret_resolver is None:
            raise ValueError("llm.secret_resolver kind 'injected' requires a resolver capability")
        resolved_secrets = secret_resolver

    persona_registry = PersonaRegistry.load(overlay.llm.personas_dir)
    http_providers = tuple(
        provider
        for provider in overlay.llm.providers
        if isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    )
    resolved_transport: ProtocolHttpTransport | None
    resolved_sleeper: ProtocolSleeper | None
    closer: ProtocolResourceCloser
    if http_providers:
        if http_transport is None:
            http_client = httpx.Client(trust_env=False)
            resolved_transport = HttpxJsonTransport(http_client)
            closer = IdempotentResourceCloser(http_client)
        else:
            resolved_transport = http_transport
            closer = NoopResourceCloser()
        resolved_sleeper = sleeper if sleeper is not None else SystemSleeper()
    else:
        if http_transport is not None or sleeper is not None:
            raise ValueError("HTTP capabilities were injected but no HTTP provider is selected")
        resolved_transport = None
        resolved_sleeper = None
        closer = NoopResourceCloser()

    try:
        clients: dict[str, ProtocolLlmClient] = {}
        for provider in overlay.llm.providers:
            if isinstance(provider, ModelSOStubLlmProviderBinding):
                clients[provider.provider_id] = StubLlmClient(model=provider.model)
            else:
                assert resolved_transport is not None
                assert resolved_sleeper is not None
                clients[provider.provider_id] = OpenAICompatibleClient(
                    config=provider,
                    transport=resolved_transport,
                    secret_resolver=resolved_secrets,
                    sleeper=resolved_sleeper,
                )
        client_factory = StaticLlmClientFactory(clients)
        pilot_factory = ApplicationPilotFactory(
            clients=client_factory,
            personas=persona_registry,
        )
        return LlmDependencies(
            client_factory=client_factory,
            persona_registry=persona_registry,
            pilot_factory=pilot_factory,
            tuner_generator=LlmTunerGenerator(client_factory),
            closer=closer,
        )
    except Exception:
        closer.close()
        raise


def build_runtime_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    llm_dependencies: LlmDependencies | None = None,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> RuntimeDependencies:
    """Construct every selected outer adapter exactly once."""
    if llm_dependencies is not None and any(
        capability is not None for capability in (secret_resolver, http_transport, sleeper)
    ):
        raise ValueError("prebuilt llm_dependencies cannot be combined with root capabilities")
    owns_llm = llm_dependencies is None
    llm = llm_dependencies or build_llm_dependencies(
        overlay,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )
    try:
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
        pilot_registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
        _validate_llm_pilot_bindings(pilot_registry, llm)
        catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
        try:
            arena = catalog.arenas[overlay.contracts.arena_id]
        except KeyError as exc:
            raise ValueError(
                f"unknown arena_id {overlay.contracts.arena_id!r} in application overlay"
            ) from exc
        return RuntimeDependencies(
            bus=bus,
            ledger=ledger,
            leaderboard=leaderboard,
            clock=clock,
            identities=identities,
            event_factory=event_factory,
            catalog=catalog,
            arena=arena,
            pilot_registry=pilot_registry,
            pilot_factory=llm.pilot_factory,
            closer=llm.closer if owns_llm else NoopResourceCloser(),
        )
    except Exception:
        if owns_llm:
            llm.close()
        raise


def build_learning_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> LearningDependencies:
    """Bind only learning ports; global event and leaderboard stores stay unopened."""
    llm = build_llm_dependencies(
        overlay,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )
    try:
        evaluation_storage = build_evaluation_storage_allocator(overlay)
        clock: Clock = SystemClock()
        identities: IdentityProvider = SystemIdentityProvider()
        artifacts = YamlFilesystemLearningArtifactStore(
            ModelSOFilesystemLearningArtifactsConfig(
                evaluation_root=overlay.learning_artifacts.evaluation_root,
                lineage_root=overlay.learning_artifacts.lineage_root,
                experiment_root=overlay.learning_artifacts.experiment_root,
            )
        )

        def emit_tuner_event(event: ModelSOEventEnvelope) -> None:
            artifacts.write_llm_event(event)

        tuner_observer = LedgerLlmCompletionObserver(
            correlation_id=identities.new_correlation_id(),
            event_factory=EventFactory(clock=clock, identities=identities),
            emit=emit_tuner_event,
        )
        observed_tuner_factory = StaticLlmClientFactory(
            {
                provider.provider_id: ObservedLlmClient(
                    base=llm.client_factory.client_for(provider.provider_id),
                    provider_id=provider.provider_id,
                    observer=tuner_observer,
                )
                for provider in overlay.llm.providers
            }
        )
        return LearningDependencies(
            clock=clock,
            artifacts=artifacts,
            duel_executor=build_duel_executor_with_dependencies(
                overlay,
                evaluation_storage=evaluation_storage,
                llm_dependencies=llm,
            ),
            tuner_generator=LlmTunerGenerator(observed_tuner_factory),
            closer=llm.closer,
        )
    except Exception:
        llm.close()
        raise


def build_duel_executor(
    overlay: ModelSOApplicationOverlay,
    *,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> ManagedDuelExecutor:
    """Bind the learning/balance duel capability at the sole adapter root."""
    llm = build_llm_dependencies(
        overlay,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )
    try:
        return ManagedDuelExecutor(
            executor=build_duel_executor_with_dependencies(
                overlay,
                evaluation_storage=build_evaluation_storage_allocator(overlay),
                llm_dependencies=llm,
            ),
            closer=llm.closer,
        )
    except Exception:
        llm.close()
        raise


def build_adaptation_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> AdaptationDependencies:
    """Bind adaptation to root-built pilots and canonical evaluation evidence."""
    llm = build_llm_dependencies(
        overlay,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )
    try:
        return AdaptationDependencies(
            duel_executor=build_pilot_duel_executor_with_dependencies(
                overlay,
                evaluation_storage=build_evaluation_storage_allocator(overlay),
                llm_dependencies=llm,
            ),
            closer=llm.closer,
        )
    except Exception:
        llm.close()
        raise


def build_evaluation_storage_allocator(
    overlay: ModelSOApplicationOverlay,
) -> EvaluationStorageAllocator:
    """Bind the operator-selected evaluation evidence adapter exactly once."""
    binding = overlay.evaluation_storage
    if binding.kind == "sqlite":
        return SQLiteEvaluationStorageAllocator(binding)
    raise ValueError(f"unsupported evaluation storage adapter kind: {binding.kind!r}")


def build_duel_executor_with_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    evaluation_storage: EvaluationStorageAllocator,
    llm_dependencies: LlmDependencies,
) -> DuelExecutor:
    """Assemble the duel capability over an injected evidence allocator."""

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
        claim = evaluation_storage.claim(storage)
        ledger_binding = overlay.event_ledger.model_copy(
            update={
                "path": claim.path,
                "journal_mode": claim.journal_mode,
                "check_same_thread": claim.check_same_thread,
                "transaction_mode": claim.transaction_mode,
                "event_schema": claim.event_schema,
            }
        )
        leaderboard_binding = overlay.leaderboard.model_copy(
            update={
                "path": claim.path,
                "journal_mode": claim.journal_mode,
                "check_same_thread": claim.check_same_thread,
                "transaction_mode": claim.transaction_mode,
                "storage_schema": claim.leaderboard_schema,
            }
        )
        duel_overlay = overlay.model_copy(
            update={
                "event_ledger": ledger_binding,
                "leaderboard": leaderboard_binding,
            }
        )
        dependencies = build_runtime_dependencies(
            duel_overlay,
            llm_dependencies=llm_dependencies,
        )
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


def build_pilot_duel_executor_with_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    evaluation_storage: EvaluationStorageAllocator,
    llm_dependencies: LlmDependencies,
) -> PilotDuelExecutor:
    """Assemble the adaptation duel capability over canonical allocated storage."""

    def execute(
        *,
        loadout_a: ModelSOLoadout,
        loadout_b: ModelSOLoadout,
        pilot_a: ModelSOLlmPilotSelection,
        pilot_b: ModelSOLlmPilotSelection,
        seed: int,
        max_ticks: int,
        storage: ModelSOEvaluationStorageKey,
        match_id: str,
        side_a: str,
        side_b: str,
    ) -> DuelResult:
        claim = evaluation_storage.claim(storage)
        duel_overlay = overlay.model_copy(
            update={
                "event_ledger": overlay.event_ledger.model_copy(
                    update={
                        "path": claim.path,
                        "journal_mode": claim.journal_mode,
                        "check_same_thread": claim.check_same_thread,
                        "transaction_mode": claim.transaction_mode,
                        "event_schema": claim.event_schema,
                    }
                ),
                "leaderboard": overlay.leaderboard.model_copy(
                    update={
                        "path": claim.path,
                        "journal_mode": claim.journal_mode,
                        "check_same_thread": claim.check_same_thread,
                        "transaction_mode": claim.transaction_mode,
                        "storage_schema": claim.leaderboard_schema,
                    }
                ),
            }
        )
        dependencies = build_runtime_dependencies(
            duel_overlay,
            llm_dependencies=llm_dependencies,
        )
        identity = MatchIdentity(
            match_id=match_id,
            correlation_id=dependencies.identities.new_correlation_id(),
        )
        bound_factory = dependencies.pilot_factory.with_observer(
            LedgerLlmCompletionObserver(
                correlation_id=identity.correlation_id,
                event_factory=dependencies.event_factory,
                emit=dependencies.bus.publish,
            )
        )
        return run_pilot_duel(
            dependencies=dependencies,
            identity=identity,
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            pilot_a=bound_factory.llm_pilot(pilot_a),
            pilot_b=bound_factory.llm_pilot(pilot_b),
            seed=seed,
            max_ticks=max_ticks,
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
    return dependencies.pilot_factory.from_spec(spec)


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
    pilots_override: Mapping[str, PilotProtocol] | None = None,
) -> LiveMatchStack:
    """Pure DI seam used by production root and hermetic tests."""
    _require_valid_budgets(red, dependencies.catalog)
    _require_valid_budgets(blue, dependencies.catalog)
    mech_a = f"mech.{side_a}.01"
    mech_b = f"mech.{side_b}.01"
    if pilots_override is None:
        bound_pilot_factory = dependencies.pilot_factory.with_observer(
            LedgerLlmCompletionObserver(
                correlation_id=identity.correlation_id,
                event_factory=dependencies.event_factory,
                emit=dependencies.bus.publish,
            )
        )
        match_dependencies = replace(dependencies, pilot_factory=bound_pilot_factory)
        pilots = {
            mech_a: _resolved_pilot(
                red, loadout_path=red_loadout_path, dependencies=match_dependencies
            ),
            mech_b: _resolved_pilot(
                blue, loadout_path=blue_loadout_path, dependencies=match_dependencies
            ),
        }
    else:
        required = {mech_a, mech_b}
        if set(pilots_override) != required:
            raise ValueError(
                f"pilots_override keys must be exactly {sorted(required)}; "
                f"got {sorted(pilots_override)}"
            )
        pilots = dict(pilots_override)
    dependencies.bus.subscribe(dependencies.ledger.append)
    runner = MatchRunner(
        identity=identity,
        seed=seed,
        loadout_a=red,
        loadout_b=blue,
        bus=dependencies.bus,
        event_factory=dependencies.event_factory,
        catalog=dependencies.catalog,
        arena=dependencies.arena,
        pilots=pilots,
        max_ticks=max_ticks,
        side_a=side_a,
        side_b=side_b,
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
        payload = ModelSOMatchScoredPayload.model_validate(event.payload)
        dependencies.leaderboard.on_match_scored(payload)

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
        closer=dependencies.closer,
    )


def assemble_match_live(
    *,
    overlay: ModelSOApplicationOverlay,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> LiveMatchStack:
    dependencies = build_runtime_dependencies(
        overlay,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )
    try:
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
    except Exception:
        dependencies.close()
        raise


def run_composed_match(
    *,
    overlay: ModelSOApplicationOverlay,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> ModelSOMatchState:
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )
    try:
        final = stack.runner.run()
        if final.status is not SOMatchStatus.ENDED:
            raise RuntimeError(f"match {stack.match_id!r} did not terminate: {final.status.value}")
        if final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS and final.winner_id is not None:
            raise RuntimeError("draw recorded a winner — lifecycle invariant violated")
        return final
    finally:
        stack.close()


__all__ = [
    "AdaptationDependencies",
    "ApplicationPilotFactory",
    "IdempotentResourceCloser",
    "LearningDependencies",
    "LiveMatchStack",
    "LlmDependencies",
    "RuntimeDependencies",
    "assemble_match_live",
    "assemble_match_with_dependencies",
    "build_adaptation_dependencies",
    "build_duel_executor",
    "build_duel_executor_with_dependencies",
    "build_evaluation_storage_allocator",
    "build_learning_dependencies",
    "build_llm_dependencies",
    "build_pilot_duel_executor_with_dependencies",
    "build_runtime_dependencies",
    "load_application_overlay",
    "load_loadout",
    "load_match_contract_catalog",
    "load_pilot_registry",
    "load_pilot_spec",
    "run_composed_match",
]
