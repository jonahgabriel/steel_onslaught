"""Sole Slice-1 production composition and configuration ingress."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NamedTuple, Self, cast
from uuid import UUID, uuid4

import httpx
import ulid
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.cards.dealer import DealerCompute
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.cards.rules import CardProgrammingRuleRegistry, default_rule_registry
from steel_onslaught.cards.split_deck import SplitDeckDealerAdapter
from steel_onslaught.commands.authority import (
    AuthenticatedSessionCapability,
    ModelSOStartMatchAuthorityContext,
    canonical_overlay_sha256,
)
from steel_onslaught.commands.coordinator import (
    ProcessLocalHumanLoopbackCoordinator,
    ProcessLocalMatchLaunchCoordinator,
)
from steel_onslaught.commands.inbox import ProcessLocalHumanDecisionInbox
from steel_onslaught.commands.live_provider import ProcessLocalOneShotLiveProviderCapability
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOCardCatalogBinding,
    ModelSOCardProgrammerBinding,
    ModelSOCloseRangeFalloffBinding,
    ModelSOMovesEvasionBinding,
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOStubLlmProviderBinding,
)
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.card import (
    CardCatalogError,
    ModelSOCard,
    ModelSOCardCatalog,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.commands import ModelSOStartMatchCommand
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.contracts.gizmo import ModelSOGizmoSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.mode import ModeId, ModelSOModeTransition
from steel_onslaught.contracts.model_catalog import (
    ModelSOModelCatalog,
    ModelSOModelCatalogIndex,
    ModelSOModelCatalogSource,
    build_model_catalog,
    model_catalog_source_from_roster,
)
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams, ModelSOPilotSpec
from steel_onslaught.contracts.pilot_registry import PilotResolutionError, PilotSpecRegistry
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanSeatAssignment,
    ModelSOMatchLaunchProvenance,
    ModelSOModelSeatAssignment,
    ModelSOPlayerRosterBinding,
    Side,
    validate_player_roster_against_overlay,
)
from steel_onslaught.contracts.sensor import ModelSOSensorSpec
from steel_onslaught.contracts.split_deck import ModelSOCardDeckPolicy
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import Clock, EventFactory, IdentityProvider
from steel_onslaught.events.payloads import ModelSOMatchScoredPayload
from steel_onslaught.learning.after_match import AfterMatchLearningHandler
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.ledger.protocol import QueryableEventLedger
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger
from steel_onslaught.llm.client_http import (
    BoundedLlmClient,
    HttpxJsonTransport,
    NoSecretResolver,
    OpenAICompatibleClient,
    SelectedOnlyLlmClientBuilder,
    StaticLlmClientFactory,
    SystemSleeper,
)
from steel_onslaught.llm.effect import (
    LedgerLlmCompletionObserver,
    ObservedLlmClient,
)
from steel_onslaught.llm.personas import PersonaRegistry
from steel_onslaught.llm.pilot import LLMPilot, LlmPilotFailurePolicy
from steel_onslaught.llm.programming import PROGRAMMING_INSTRUCTIONS_SHA256, LLMProgrammingPilot
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
from steel_onslaught.match.card_adapter import CardRunnerAdapter
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
from steel_onslaught.match.runtime import (
    ConditionProgressGate,
    MatchRuntime,
    RuntimeProgressGate,
)
from steel_onslaught.match.state import ModelSOMatchState, SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.human import HumanPilot
from steel_onslaught.pilots.persona_prompts import (
    ModelSOMatchPromptProvenance,
    apply_prompt_overrides,
    build_match_prompt_provenance,
)
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.programming import (
    ModelSOCardRulePackProvenance,
    ProgrammingPilot,
)
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
        failure_policy: LlmPilotFailurePolicy = "fallback",
    ) -> None:
        self._clients = clients
        self._personas = personas
        self._observer = observer
        self._failure_policy = failure_policy

    def with_observer(self, observer: ProtocolLlmCompletionObserver) -> ProtocolPilotFactory:
        return ApplicationPilotFactory(
            clients=self._clients,
            personas=self._personas,
            observer=observer,
            failure_policy=self._failure_policy,
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
            failure_policy=self._failure_policy,
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
    learning_artifacts: LearningArtifactStore | None = None
    progress_gate: RuntimeProgressGate | None = None
    # Optional until the card/register runtime slice is activated.  When
    # configured, this is one immutable snapshot shared by the live
    # composition and replay seam; no default package-path discovery is
    # permitted.
    card_catalog: ModelSOCardCatalog | None = None
    # Passive validated card+deck content; register gameplay is a later slice.
    card_runtime_snapshot: ModelSOCardRuntimeSnapshot | None = None
    # Fully composed card mode adapter.  This is present only when the
    # overlay explicitly enables card mode; a passive snapshot never activates
    # register gameplay by itself.
    card_adapter: CardRunnerAdapter | None = None
    # Optional whole-round programmers are an explicit capability.  When
    # absent the card adapter uses its deterministic priority programmer;
    # ordinary decide-only pilots are never used as a fallback.
    card_programmers: Mapping[str, ProgrammingPilot] | None = None
    # Explicit overlay bindings retain their provider/spec resolution in a
    # match-scoped factory.  The raw mapping above remains available for
    # compatibility and injected test graphs, while live composition clones
    # observed programmers per match instead of mutating this dependency.
    card_programmer_factory: CardProgrammerFactory | None = None
    # Card cadence is contract-selected at the application overlay.  Atomic
    # remains the safe default; paced requires an enabled card adapter.
    card_cadence: Literal["atomic", "paced"] = "atomic"
    # Content-addressed selected rule pack copied into MATCH_STARTED.
    card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = None
    # Content-addressed effective persona prompts copied into MATCH_STARTED.
    # A human prompt edit is a decision input; recording it here is what keeps
    # replay honest about what the mechs were actually told.
    prompt_provenance: ModelSOMatchPromptProvenance | None = None
    # Round-3 moves-scaled evasion policy selected by the overlay.  None => the
    # mechanic is off (the comparison arm), so hit resolution is unchanged.
    moves_evasion: ModelSOMovesEvasionBinding | None = None
    # Round-4 close-range accuracy falloff on long weapons.  None => the mechanic
    # is off (the comparison arm), so every weapon keeps a 1.0 multiplier.
    close_range_falloff: ModelSOCloseRangeFalloffBinding | None = None

    def __post_init__(self) -> None:
        if self.card_cadence not in {"atomic", "paced"}:
            raise ValueError("card_cadence must be 'atomic' or 'paced'")
        if self.card_cadence == "paced" and (
            self.card_adapter is None or not self.card_adapter.registers_enabled
        ):
            raise ValueError("paced card cadence requires enabled card mode")
        if self.card_rule_pack_provenance is not None and not isinstance(
            self.card_rule_pack_provenance, ModelSOCardRulePackProvenance
        ):
            raise TypeError(
                "card_rule_pack_provenance must be ModelSOCardRulePackProvenance when supplied"
            )
        snapshot = self.card_runtime_snapshot
        if snapshot is None:
            return
        if self.card_catalog is None:
            object.__setattr__(self, "card_catalog", snapshot.card_catalog)
        elif self.card_catalog is not snapshot.card_catalog:
            raise ValueError("card_catalog and card_runtime_snapshot must share identity")
        adapter = self.card_adapter
        if adapter is not None and not isinstance(adapter, CardRunnerAdapter):
            raise TypeError("card_adapter must be CardRunnerAdapter when supplied")
        if adapter is not None and adapter.registers_enabled:
            if snapshot is None:
                raise ValueError("enabled card_adapter requires an injected card_runtime_snapshot")
            if adapter.snapshot is not snapshot:
                raise ValueError("card_adapter and card_runtime_snapshot must share identity")
        if self.card_programmers is not None:
            object.__setattr__(
                self, "card_programmers", MappingProxyType(dict(self.card_programmers))
            )

    def close(self) -> None:
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class MissingCardCatalogError(ValueError):
    """Register execution was requested without an explicit card snapshot."""


@dataclass(frozen=True)
class LlmDependencies:
    client_factory: ProtocolLlmClientFactory
    persona_registry: PersonaRegistry
    pilot_factory: ProtocolPilotFactory
    tuner_generator: ProtocolTunerGenerator
    closer: ProtocolResourceCloser
    # Effective (post-override) prompt identity for every persona this overlay
    # can bind.  It is a decision input, so it travels with the dependency
    # graph and is written into MATCH_STARTED by the runner.
    prompt_provenance: ModelSOMatchPromptProvenance | None = None

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
    runtime: MatchRuntime
    closer: ProtocolResourceCloser
    card_catalog: ModelSOCardCatalog | None = None
    card_runtime_snapshot: ModelSOCardRuntimeSnapshot | None = None
    card_adapter: CardRunnerAdapter | None = None
    card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = None
    prompt_provenance: ModelSOMatchPromptProvenance | None = None
    _launch_provenance: ModelSOMatchLaunchProvenance | None = None
    _human_inbox: ProcessLocalHumanLoopbackCoordinator | None = None

    def close(self) -> None:
        if self._human_inbox is not None:
            self._human_inbox.shutdown()
        self.closer.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def match_id(self) -> str:
        return self.identity.match_id

    @property
    def launch_provenance(self) -> ModelSOMatchLaunchProvenance:
        """Exact selected-launch truth for an admitted loopback stack."""

        if self._launch_provenance is None:
            raise RuntimeError("legacy match stack has no selected launch provenance")
        return self._launch_provenance

    @property
    def human_inbox(self) -> ProcessLocalHumanLoopbackCoordinator:
        """Authenticated process-local prompt/action surface for human seats."""

        if self._human_inbox is None:
            raise RuntimeError("match stack has no process-local human seat")
        return self._human_inbox


def project_effective_prompt_provenance(
    overlay: ModelSOApplicationOverlay,
) -> ModelSOMatchPromptProvenance:
    """Return the effective, post-override prompt identity for one overlay.

    This is the read-only projection an operator inspection surface renders,
    and it carries the full prompt *text* (unlike the redacted ledger form the
    runner broadcasts).  Each persona's ``prompt_sha256`` here equals the hash
    the runner records in MATCH_STARTED for the same overlay, so an operator
    can read the exact text a match's recorded hash binds.  It is confined to
    the composition root because loading the persona contract directory
    (``PersonaRegistry.load``) is filesystem I/O.
    """

    authored = PersonaRegistry.load(overlay.llm.personas_dir)
    effective, overridden = apply_prompt_overrides(
        authored.as_mapping(),
        overlay.llm.persona_overrides,
    )
    return build_match_prompt_provenance(
        effective,
        overridden_persona_ids=overridden,
        programming_instructions_sha256=PROGRAMMING_INSTRUCTIONS_SHA256,
    )


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
    card_catalog = overlay.contracts.card_catalog
    if card_catalog is not None:
        card_catalog = card_catalog.model_copy(
            update={
                "cards_dir": resolved(card_catalog.cards_dir),
                "decks_dir": resolved(card_catalog.decks_dir),
            }
        )
    contracts = overlay.contracts.model_copy(
        update={
            "catalog_dir": resolved(overlay.contracts.catalog_dir),
            "pilot_registry_dir": resolved(overlay.contracts.pilot_registry_dir),
            "card_catalog": card_catalog,
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


def _load_model_catalog_inputs(
    path: Path,
) -> tuple[ModelSOModelCatalogIndex, tuple[ModelSOApplicationOverlay, ...]]:
    """Load an index and its explicitly declared source overlays."""
    index_path = path.resolve(strict=True)
    index = ModelSOModelCatalogIndex.model_validate_json(
        json.dumps(yaml.safe_load(index_path.read_text(encoding="utf-8")))
    )
    overlays: list[ModelSOApplicationOverlay] = []
    for source_binding in index.sources:
        overlay = load_application_overlay(
            (index_path.parent / source_binding.overlay_path).resolve(strict=True)
        )
        overlays.append(overlay)
    return index, tuple(overlays)


def load_model_catalog(path: Path) -> ModelSOModelCatalog:
    """Load an explicit multi-overlay catalog index and its source contracts.

    Every source path, option alias, provider/model identity, and pilot
    registry is declared by the index.  This loader performs no directory
    discovery and never substitutes a missing provider or roster option.
    """

    index, overlays = _load_model_catalog_inputs(path)
    sources: list[ModelSOModelCatalogSource] = []
    index_path = path.resolve(strict=True)
    for source_binding, overlay in zip(index.sources, overlays, strict=True):
        roster_path = (index_path.parent / source_binding.roster_path).resolve(strict=True)
        roster = ModelSOPlayerRosterBinding.model_validate_json(
            json.dumps(yaml.safe_load(roster_path.read_text(encoding="utf-8")))
        )
        validate_player_roster_against_overlay(
            roster=roster,
            overlay=overlay,
            pilot_registry=load_pilot_registry(overlay.contracts.pilot_registry_dir),
        )
        sources.append(
            model_catalog_source_from_roster(
                overlay_id=source_binding.source_overlay_id,
                overlay_sha256=canonical_overlay_sha256(overlay),
                roster=roster,
                model_identities=overlay.llm.model_identities,
                provider_models={
                    provider.provider_id: provider.model for provider in overlay.llm.providers
                },
                option_id_map={
                    alias.source_option_id: alias.catalog_option_id
                    for alias in source_binding.option_id_map
                },
            )
        )
    return build_model_catalog(
        catalog_id=index.catalog_id,
        roster_id=index.roster_id,
        sources=tuple(sources),
        seats=index.seats,
        default_chassis_ids=(index.default_chassis_ids[0], index.default_chassis_ids[1]),
        mirror_match_mode=index.mirror_match_mode,
        resolve_option_loadouts=True,
    )


def load_model_catalog_runtime_sources(
    path: Path,
) -> tuple[ModelSOModelCatalog, Mapping[str, ModelSOApplicationOverlay]]:
    """Return the catalog and its explicitly named source overlays."""

    index, overlays = _load_model_catalog_inputs(path)
    catalog = load_model_catalog(path)
    return catalog, MappingProxyType(
        {
            binding.source_overlay_id: overlay
            for binding, overlay in zip(index.sources, overlays, strict=True)
        }
    )


def load_model_catalog_runtime_overlay(
    path: Path,
    overlay: ModelSOApplicationOverlay,
) -> tuple[ModelSOModelCatalog, ModelSOApplicationOverlay]:
    """Project catalog source provider bindings into the live overlay.

    The catalog remains the authority for options and provenance, while the
    supplied application overlay remains the authority for storage, cards,
    transport, and injected capabilities. Source overlays contribute only
    their explicitly declared provider/model bindings, allowing a selected
    Qwen, GLM, OpenRouter, or Gemini option to resolve through the same DI
    graph instead of silently falling back to the launch overlay's provider.
    """

    catalog, source_overlay_map = load_model_catalog_runtime_sources(path)
    providers: dict[str, Any] = {
        provider.provider_id: provider for provider in overlay.llm.providers
    }
    identities: dict[str, Any] = {
        identity.model_identity_id: identity for identity in overlay.llm.model_identities
    }
    for source_overlay in source_overlay_map.values():
        for provider in source_overlay.llm.providers:
            existing = providers.get(provider.provider_id)
            if existing is not None and existing != provider:
                raise ValueError(
                    "catalog source provider binding conflicts with launch overlay: "
                    f"{provider.provider_id!r}"
                )
            providers[provider.provider_id] = provider
        for identity in source_overlay.llm.model_identities:
            existing_identity = identities.get(identity.model_identity_id)
            if existing_identity is not None and existing_identity != identity:
                raise ValueError(
                    "catalog source model identity conflicts with launch overlay: "
                    f"{identity.model_identity_id!r}"
                )
            identities[identity.model_identity_id] = identity
    merged_llm = overlay.llm.model_copy(
        update={
            "providers": tuple(providers.values()),
            "model_identities": tuple(identities.values()),
        }
    )
    return catalog, overlay.model_copy(update={"llm": merged_llm})


def load_model_catalog_loadouts(path: Path) -> Mapping[str, ModelSOLoadout]:
    """Load only the loadouts explicitly named by a catalog source index."""

    index_path = path.resolve(strict=True)
    index = ModelSOModelCatalogIndex.model_validate_json(
        json.dumps(yaml.safe_load(index_path.read_text(encoding="utf-8")))
    )
    loadouts: dict[str, ModelSOLoadout] = {}
    for source in index.sources:
        if source.loadout_paths is None:
            continue
        for raw_path in source.loadout_paths:
            loadout_path = (index_path.parent / raw_path).resolve(strict=True)
            loadout = load_loadout(loadout_path)
            existing = loadouts.get(loadout.id)
            if existing is not None and existing != loadout:
                raise ValueError(f"catalog loadout id has conflicting definitions: {loadout.id!r}")
            loadouts[loadout.id] = loadout
    return MappingProxyType(loadouts)


def load_model_catalog_pilot_registry(path: Path) -> PilotSpecRegistry:
    """Merge the exact pilot registries declared by catalog source overlays."""

    _index, source_overlays = _load_model_catalog_inputs(path)
    directories = tuple(
        dict.fromkeys(
            source_overlay.contracts.pilot_registry_dir for source_overlay in source_overlays
        )
    )
    if not directories:
        raise ValueError("catalog source overlays must declare pilot registries")
    return load_pilot_registry(directories[0], additional_directories=directories[1:])


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


def load_card_catalog(binding: ModelSOCardCatalogBinding) -> ModelSOCardCatalog:
    """Load one explicit card YAML root into an immutable catalog snapshot.

    This backward-compatible card-only helper validates the explicit cards
    root.  Call :func:`load_card_runtime_snapshot` when deck content is part of
    the selected composition; no default deck is inferred here.

    The returned value is process-shared immutable content. Its canonical
    digest is persisted in MATCH_STARTED provenance whenever card mode names
    an explicit deck; overlay path hashing alone is not content provenance.
    """
    cards_dir = binding.cards_dir
    if not cards_dir.is_absolute():
        raise ValueError(f"card catalog cards_dir must be absolute: {cards_dir}")
    if not cards_dir.is_dir():
        raise FileNotFoundError(f"required card catalog directory does not exist: {cards_dir}")
    paths = sorted(cards_dir.glob("*.yaml"))
    if not paths:
        raise ValueError(f"required card catalog directory contains no YAML specs: {cards_dir}")

    cards: list[ModelSOCard] = []
    seen_ids: set[str] = set()
    for path in paths:
        card = ModelSOCard.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        card_id = str(card.id)
        if card_id in seen_ids:
            raise ValueError(f"duplicate card id {card_id!r} under {cards_dir}")
        seen_ids.add(card_id)
        cards.append(card)
    cards.sort(key=lambda card: str(card.id))
    return ModelSOCardCatalog(cards=tuple(cards))


def load_deck_catalog(
    decks_dir: Path,
    *,
    card_catalog: ModelSOCardCatalog,
) -> tuple[ModelSODeck, ...]:
    """Load and validate every explicit deck YAML against one card snapshot."""

    if not decks_dir.is_absolute():
        raise ValueError(f"card catalog decks_dir must be absolute: {decks_dir}")
    if not decks_dir.is_dir():
        raise FileNotFoundError(f"required card deck directory does not exist: {decks_dir}")
    paths = sorted(decks_dir.glob("*.yaml"))
    if not paths:
        raise ValueError(f"required card deck directory contains no YAML specs: {decks_dir}")

    decks: list[ModelSODeck] = []
    seen_ids: set[str] = set()
    for path in paths:
        deck = ModelSODeck.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        deck_id = str(deck.id)
        if deck_id in seen_ids:
            raise ValueError(f"duplicate deck id {deck_id!r} under {decks_dir}")
        seen_ids.add(deck_id)
        for entry in deck.cards:
            try:
                card_catalog.require(entry.card_id)
            except CardCatalogError as exc:
                raise ValueError(
                    f"deck {deck_id!r} references unknown card {entry.card_id!r}"
                ) from exc
        decks.append(deck)
    decks.sort(key=lambda deck: str(deck.id))
    return tuple(decks)


def load_card_runtime_snapshot(
    binding: ModelSOCardCatalogBinding,
    *,
    deck_id: str | None = None,
) -> ModelSOCardRuntimeSnapshot:
    """Load one immutable card+deck snapshot from an explicit overlay binding.

    ``deck_id`` is optional only while the snapshot is passive configuration.
    A binding that enables card mode must carry an explicit deck id; neither
    this loader nor the snapshot ever selects the first/sorted deck.
    """

    card_catalog = load_card_catalog(binding)
    decks = load_deck_catalog(binding.decks_dir, card_catalog=card_catalog)
    selected_deck_id = binding.deck_id if deck_id is None else deck_id
    if binding.deck_id is not None and deck_id is not None and binding.deck_id != deck_id:
        raise ValueError(
            f"conflicting explicit deck ids: binding={binding.deck_id!r}, argument={deck_id!r}"
        )
    if binding.deck_policy is not None and deck_id is not None:
        raise ValueError("split-deck policy cannot be combined with an explicit deck_id argument")
    if binding.card_mode_enabled and selected_deck_id is None and binding.deck_policy is None:
        raise ValueError("card mode requires an explicit deck_id")
    if selected_deck_id is not None and selected_deck_id not in {deck.id for deck in decks}:
        raise ValueError(f"unknown selected deck_id {selected_deck_id!r}")
    if binding.deck_policy is not None:
        _validate_split_deck_policy(
            binding.deck_policy,
            decks=decks,
            card_catalog=card_catalog,
        )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=card_catalog,
        decks=decks,
        selected_deck_id=selected_deck_id,
        content_sha256=canonical_card_runtime_sha256(card_catalog, decks),
    )


def _validate_split_deck_policy(
    policy: ModelSOCardDeckPolicy,
    *,
    decks: tuple[ModelSODeck, ...],
    card_catalog: ModelSOCardCatalog,
) -> None:
    """Validate policy deck references and category partitions at load time."""

    decks_by_id = {str(deck.id): deck for deck in decks}
    for seat in policy.seats:
        for deck_id, categories, label in (
            (
                seat.movement_deck_id,
                frozenset({SOCardCategory.MOVEMENT, SOCardCategory.ROTATE}),
                "movement",
            ),
            (
                seat.weapon_deck_id,
                frozenset({SOCardCategory.ATTACK, SOCardCategory.VENT, SOCardCategory.SPECIAL}),
                "weapon",
            ),
        ):
            deck = decks_by_id.get(str(deck_id))
            if deck is None:
                raise ValueError(
                    f"split-deck policy side {seat.side!r} references unknown {label} deck "
                    f"{deck_id!r}"
                )
            for entry in deck.cards:
                card = card_catalog.require(entry.card_id)
                if card.category not in categories:
                    raise ValueError(
                        f"split-deck policy {label} deck {deck.id!r} contains "
                        f"card {card.id!r} from category {card.category.value!r}"
                    )


def build_register_execution_reducer(
    dependencies: RuntimeDependencies,
) -> RegisterExecutionReducer:
    """Bind register execution to the explicit runtime card snapshot.

    This is a construction-only seam.  It does not subscribe the reducer to
    the event bus or activate register gameplay; callers must supply the
    already composed dependency graph.  A card-enabled caller therefore
    cannot silently fall back to package data or a default catalog.
    """
    if not isinstance(dependencies, RuntimeDependencies):
        raise TypeError("register execution requires RuntimeDependencies")
    catalog = dependencies.card_catalog
    if not isinstance(catalog, ModelSOCardCatalog):
        raise MissingCardCatalogError("register execution requires an injected card catalog")
    return RegisterExecutionReducer(catalog)


def build_card_runner_adapter(
    *,
    snapshot: ModelSOCardRuntimeSnapshot,
    programmers: Mapping[str, ProgrammingPilot] | None = None,
    rule_registry: CardProgrammingRuleRegistry | None = None,
    rule_handler_ids: tuple[str, ...] = (),
    split_policy: ModelSOCardDeckPolicy | None = None,
) -> CardRunnerAdapter:
    """Compose the explicit card runtime graph for an enabled overlay.

    The selected deck is taken only from the immutable snapshot.  No package
    data, first-deck ordering, or decide-only pilot is consulted.  A caller
    that has not explicitly selected a deck therefore fails closed in the
    ``CardRoundRuntime`` constructor.
    """

    if not isinstance(snapshot, ModelSOCardRuntimeSnapshot):
        raise TypeError("card runtime requires ModelSOCardRuntimeSnapshot")
    dealer = DealerCompute()
    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    split_deck_adapter = (
        SplitDeckDealerAdapter(snapshot=snapshot, policy=split_policy, dealer=dealer)
        if split_policy is not None
        else None
    )
    runtime = CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=(
            snapshot.selected_deck.register_count
            if split_policy is None
            else max(seat.register_count for seat in split_policy.seats)
        ),
        split_deck_adapter=split_deck_adapter,
    )
    return CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=dealer,
        reducer=reducer,
        split_deck_adapter=split_deck_adapter,
        programmers=programmers,
        rule_registry=rule_registry,
        rule_handler_ids=rule_handler_ids,
    )


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


def load_pilot_registry(
    directory: Path,
    *,
    additional_directories: tuple[Path, ...] = (),
) -> PilotSpecRegistry:
    specs = _load_specs(directory, ModelSOPilotSpec)
    for additional_directory in additional_directories:
        for pilot_id, spec in _load_specs(additional_directory, ModelSOPilotSpec).items():
            existing = specs.get(pilot_id)
            if existing is not None and existing != spec:
                raise ValueError(f"pilot id has conflicting definitions: {pilot_id!r}")
            specs[pilot_id] = spec
    return PilotSpecRegistry(specs)


def _validate_llm_pilot_bindings(
    registry: PilotSpecRegistry,
    llm: LlmDependencies,
    *,
    selected_pilot_spec_ids: tuple[str, ...] | None = None,
) -> None:
    specs = registry.as_mapping()
    if selected_pilot_spec_ids is None:
        selected_specs = tuple(specs.values())
    else:
        selected: list[ModelSOPilotSpec] = []
        for spec_id in selected_pilot_spec_ids:
            try:
                selected.append(specs[spec_id])
            except KeyError as exc:
                raise PilotResolutionError(f"unknown exact pilot_id {spec_id!r}") from exc
        selected_specs = tuple(selected)

    for spec in selected_specs:
        if spec.archetype != "llm":
            continue
        if not isinstance(spec.parameters, ModelSOLlmPilotParams):
            raise TypeError(f"llm pilot spec {spec.id!r} has invalid parameters")
        llm.client_factory.client_for(spec.parameters.provider)
        llm.persona_registry.require(spec.parameters.persona)


class SeatIdentityError(ValueError):
    """Two live card seats did not resolve to distinct, declared identities.

    This is deliberately its own type.  The failure is a composition/contract
    validation failure — the caller asked for a legal, roster-permitted
    pairing that simply is not a contest between two distinct decision-makers
    — so a transport boundary must not report it as an authorization failure.
    """


class SeatProgrammerIdentity(NamedTuple):
    """The two facts that make one card seat its own decision-maker.

    Persona alone is not the identity: the same persona driven by two
    different models is the cleanest model-vs-model contest there is, and
    banning it would break the product.  The same persona on the same
    provider, on both seats, is a mirror match.
    """

    provider: str
    persona: str


def validate_seat_programmer_identity(
    resolved_seats: Mapping[str, SeatProgrammerIdentity],
    *,
    deck_policy: ModelSOCardDeckPolicy | None = None,
) -> None:
    """Fail closed when a seat's programmer is not the seat it claims to be.

    In card mode the card programmer — not the loadout pilot — is the seat's
    decision-maker, so nothing about a seat's advertised identity is true
    until the *resolved* programmer for that side is checked.  Two checks make
    seat identity one validated contract:

    1. Every bound seat must resolve to a distinct ``(provider, persona)``
       identity.  This is unconditional: it is the check that stops a live
       match from running an unannounced mirror.  It applies to the split-deck
       overlays and to the single-deck catalog/roster paths alike, because
       both admit their seats from a runtime selection rather than from the
       overlay's authored default.
    2. When the overlay also declares a split ``deck_policy``, each bound
       seat's resolved persona must equal that seat's declared archetype.
       Without it, ``archetype`` is a label with nothing behind it.

    ``resolved_seats`` is the post-rebind, admitted runtime selection — never
    the overlay's authored template — so a differentiated-looking overlay
    cannot be collapsed by the selection that actually launched.
    """

    if deck_policy is not None:
        mismatched = tuple(
            f"{seat.side}={resolved_seats[seat.side].persona!r} (archetype {seat.archetype!r})"
            for seat in deck_policy.seats
            if seat.side in resolved_seats and resolved_seats[seat.side].persona != seat.archetype
        )
        if mismatched:
            raise SeatIdentityError(
                "card programmer persona does not match the declared seat archetype: "
                + ", ".join(mismatched)
            )
    declared = tuple(sorted(resolved_seats.items()))
    identities = {identity for _side, identity in declared}
    if len(declared) > 1 and len(identities) != len(declared):
        rendered = ", ".join(
            f"{side}={identity.persona!r}@{identity.provider!r}" for side, identity in declared
        )
        raise SeatIdentityError(
            "live card seats must resolve to distinct card programmer identities "
            f"(model + persona); got {rendered}"
        )


def build_card_programmers(
    bindings: tuple[ModelSOCardProgrammerBinding, ...],
    *,
    registry: PilotSpecRegistry,
    llm: LlmDependencies,
    deck_policy: ModelSOCardDeckPolicy | None = None,
    observer: ProtocolLlmCompletionObserver | None = None,
    correlation_id: UUID | None = None,
) -> Mapping[str, ProgrammingPilot]:
    """Resolve explicit card seat bindings into fail-closed LLM programmers.

    The overlay owns only stable seat/spec references.  This helper resolves
    each reference through the already validated pilot registry and injected
    LLM graph, then constructs the whole-round capability with the exact
    provider client and persona selected by that spec.  A missing binding is
    represented by an absent mapping entry; the card adapter then retains its
    deterministic priority programmer for that seat.

    Seat identity is validated here, unconditionally, before any provider
    client is bound: this is the single chokepoint every card path (catalog,
    roster, and injected overlay) funnels through, and the bindings it
    receives are the admitted runtime selection, so it is the only place that
    can prove the seats a live match actually runs are distinct.  When the
    overlay also declares a split ``deck_policy``, the resolved personas are
    additionally checked against that policy's seat archetypes.
    """

    if observer is not None and correlation_id is None:
        raise ValueError("observed card programmers require a match correlation_id")

    resolved: list[tuple[ModelSOCardProgrammerBinding, ModelSOLlmPilotParams]] = []
    bound_sides: set[str] = set()
    for binding in bindings:
        if binding.side in bound_sides:
            raise ValueError(f"card programmer seat {binding.side!r} is bound more than once")
        bound_sides.add(binding.side)
        spec = registry.get(binding.pilot_spec_id)
        if spec is None:
            raise PilotResolutionError(
                f"unknown card programmer pilot_spec_id {binding.pilot_spec_id!r}"
            )
        if spec.archetype != "llm":
            raise ValueError(
                f"card programmer pilot spec {spec.id!r} must use llm archetype; "
                f"got {spec.archetype!r}"
            )
        if not isinstance(spec.parameters, ModelSOLlmPilotParams):
            raise TypeError(f"llm card programmer spec {spec.id!r} has invalid parameters")
        resolved.append((binding, spec.parameters))

    if resolved:
        validate_seat_programmer_identity(
            {
                binding.side: SeatProgrammerIdentity(
                    provider=parameters.provider,
                    persona=parameters.persona,
                )
                for binding, parameters in resolved
            },
            deck_policy=deck_policy,
        )

    programmers: dict[str, ProgrammingPilot] = {}
    for binding, parameters in resolved:
        provider_id = parameters.provider
        if observer is not None:
            observed_factory = llm.pilot_factory.with_observer(observer)
            observed_pilot = observed_factory.llm_pilot(
                ModelSOLlmPilotSelection(
                    provider_id=provider_id,
                    persona_id=parameters.persona,
                    opponent_trace=None,
                )
            )
            client = cast(Any, observed_pilot).client
        else:
            client = llm.client_factory.client_for(provider_id)
        persona = llm.persona_registry.require(parameters.persona)
        programmers[binding.side] = LLMProgrammingPilot(
            client=client,
            persona=persona,
            # The overlay chooses strict abort or explicit typed recovery;
            # this is never an implicit provider/stub fallback.
            failure_policy=binding.failure_policy,
            correlation_id=correlation_id,
            # Names the failing provider on a bounded-retry semantic terminal.
            provider_id=provider_id,
        )
    return MappingProxyType(programmers)


@dataclass(frozen=True, slots=True)
class CardProgrammerFactory:
    """Clone explicitly bound card programmers for one match identity.

    Provider clients and persona/spec resolution belong to the shared runtime
    dependency graph, but completion evidence is match-scoped.  This factory
    therefore creates fresh ``LLMProgrammingPilot`` instances and wraps each
    selected client with its own observed effect only after the match's
    identity, event factory, and bus are available.  The shared
    ``RuntimeDependencies`` and card adapter are never mutated.
    """

    bindings: tuple[ModelSOCardProgrammerBinding, ...]
    registry: PilotSpecRegistry
    llm: LlmDependencies
    deck_policy: ModelSOCardDeckPolicy | None = None

    def for_match(
        self,
        *,
        identity: MatchIdentity,
        observer: ProtocolLlmCompletionObserver,
    ) -> Mapping[str, ProgrammingPilot]:
        return build_card_programmers(
            self.bindings,
            registry=self.registry,
            llm=self.llm,
            deck_policy=self.deck_policy,
            observer=observer,
            correlation_id=identity.correlation_id,
        )


def load_loadout(path: Path) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def build_llm_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    selected_provider_id: str | None = None,
    selected_provider_ids: tuple[str, ...] | None = None,
    pilot_failure_policy: LlmPilotFailurePolicy | None = None,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> LlmDependencies:
    """Build the immutable LLM dependency graph from the validated overlay."""
    if selected_provider_id is not None and selected_provider_ids is not None:
        raise ValueError("selected_provider_id and selected_provider_ids are mutually exclusive")
    if selected_provider_id is None:
        if selected_provider_ids is None:
            providers = overlay.llm.providers
        else:
            providers = SelectedOnlyLlmClientBuilder().select_many(
                providers=overlay.llm.providers,
                selected_provider_ids=selected_provider_ids,
            )
        # Every composition path is fail-closed by default. The unselected
        # path used to default to "fallback", which masked a provider failure
        # behind a deterministic REMAIN instead of surfacing it. A caller that
        # deliberately wants typed recovery passes pilot_failure_policy.
        resolved_failure_policy: LlmPilotFailurePolicy = "raise"
    else:
        providers = (
            SelectedOnlyLlmClientBuilder().select(
                providers=overlay.llm.providers,
                selected_provider_id=selected_provider_id,
            ),
        )
        resolved_failure_policy = "raise"

    if pilot_failure_policy is not None:
        # The selected-provider default remains fail-closed for operator and
        # CLI composition. Browser live sessions may opt into the explicit
        # per-turn fallback policy so one malformed provider action cannot
        # strand an otherwise running match without MATCH_ENDED evidence.
        resolved_failure_policy = pilot_failure_policy

    binding = overlay.llm.secret_resolver
    secret_bearing = tuple(
        provider
        for provider in providers
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

    # Human-editable prompts: an overlay may replace a persona's doctrine
    # without editing the persona contract or any code.  The override is
    # applied here, once, so every pilot and programmer built from this graph
    # flies the same effective prompt, and the effective prompt is recorded.
    authored_registry = PersonaRegistry.load(overlay.llm.personas_dir)
    effective_personas, overridden_persona_ids = apply_prompt_overrides(
        authored_registry.as_mapping(),
        overlay.llm.persona_overrides,
    )
    persona_registry = PersonaRegistry(effective_personas)
    # Ledger/broadcast form: only the binding hash per persona travels into
    # MATCH_STARTED, never the raw prompt text (sanitization gate). The full
    # text is reconstructable from the overlay via project_effective_prompt_*.
    prompt_provenance = build_match_prompt_provenance(
        effective_personas,
        overridden_persona_ids=overridden_persona_ids,
        programming_instructions_sha256=PROGRAMMING_INSTRUCTIONS_SHA256,
        include_text=False,
    )
    http_providers = tuple(
        provider
        for provider in providers
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
        for provider in providers:
            if isinstance(provider, ModelSOStubLlmProviderBinding):
                clients[provider.provider_id] = StubLlmClient(model=provider.model)
            else:
                assert resolved_transport is not None
                assert resolved_sleeper is not None
                client: ProtocolLlmClient = OpenAICompatibleClient(
                    config=provider,
                    transport=resolved_transport,
                    secret_resolver=resolved_secrets,
                    sleeper=resolved_sleeper,
                )
                if selected_provider_id is not None or selected_provider_ids is not None:
                    # A selected live launch is admitted once, then may need
                    # one completion per pilot turn. Keep the completion
                    # budget finite and explicit rather than one-shot.
                    # The browser play horizon is 100 ticks with two pilots;
                    # leave budget for malformed-response repair/fallback
                    # attempts without turning a normal match into a budget
                    # failure at the terminal horizon.
                    client = BoundedLlmClient(client, max_completions=256)
                clients[provider.provider_id] = client
        client_factory = StaticLlmClientFactory(clients)
        pilot_factory = ApplicationPilotFactory(
            clients=client_factory,
            personas=persona_registry,
            failure_policy=resolved_failure_policy,
        )
        return LlmDependencies(
            client_factory=client_factory,
            persona_registry=persona_registry,
            pilot_factory=pilot_factory,
            tuner_generator=LlmTunerGenerator(client_factory),
            closer=closer,
            prompt_provenance=prompt_provenance,
        )
    except Exception:
        closer.close()
        raise


def build_selected_llm_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    selected_provider_id: str | None = None,
    selected_provider_ids: tuple[str, ...] | None = None,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> LlmDependencies:
    """Build one or more explicitly selected, one-attempt live providers."""
    if selected_provider_id is None and selected_provider_ids is None:
        raise ValueError("a selected provider id is required")
    return build_llm_dependencies(
        overlay,
        selected_provider_id=selected_provider_id,
        selected_provider_ids=selected_provider_ids,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )


def build_runtime_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    pilot_registry: PilotSpecRegistry | None = None,
    llm_dependencies: LlmDependencies | None = None,
    selected_provider_id: str | None = None,
    selected_provider_ids: tuple[str, ...] | None = None,
    selected_pilot_spec_ids: tuple[str, ...] | None = None,
    card_programmers: Mapping[str, ProgrammingPilot] | None = None,
    llm_failure_policy: LlmPilotFailurePolicy | None = None,
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> RuntimeDependencies:
    """Construct every selected outer adapter exactly once."""
    if selected_provider_id is not None and selected_provider_ids is not None:
        raise ValueError("selected_provider_id and selected_provider_ids are mutually exclusive")
    if (selected_provider_id is None and selected_provider_ids is None) != (
        selected_pilot_spec_ids is None
    ):
        raise ValueError(
            "selected provider ids and selected_pilot_spec_ids must be supplied together"
        )
    if llm_dependencies is not None and any(
        capability is not None
        for capability in (
            selected_provider_id,
            selected_provider_ids,
            selected_pilot_spec_ids,
            llm_failure_policy,
            secret_resolver,
            http_transport,
            sleeper,
        )
    ):
        raise ValueError("prebuilt llm_dependencies cannot be combined with root capabilities")

    # Validate all static contract inputs before opening any runtime adapters.
    # A malformed optional card root must not allocate LLM, ledger, or
    # leaderboard resources and then fail during composition.
    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    card_binding = overlay.contracts.card_catalog
    card_runtime_snapshot = (
        load_card_runtime_snapshot(card_binding) if card_binding is not None else None
    )
    card_catalog = card_runtime_snapshot.card_catalog if card_runtime_snapshot is not None else None
    card_cadence: Literal["atomic", "paced"] = (
        card_binding.card_cadence if card_binding is not None else "atomic"
    )
    owns_llm = llm_dependencies is None
    llm = llm_dependencies or build_llm_dependencies(
        overlay,
        selected_provider_id=selected_provider_id,
        selected_provider_ids=selected_provider_ids,
        pilot_failure_policy=llm_failure_policy,
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
        learning_artifacts: LearningArtifactStore = YamlFilesystemLearningArtifactStore(
            ModelSOFilesystemLearningArtifactsConfig(
                evaluation_root=overlay.learning_artifacts.evaluation_root,
                lineage_root=overlay.learning_artifacts.lineage_root,
                experiment_root=overlay.learning_artifacts.experiment_root,
            )
        )
        resolved_pilot_registry = pilot_registry or load_pilot_registry(
            overlay.contracts.pilot_registry_dir
        )
        _validate_llm_pilot_bindings(
            resolved_pilot_registry,
            llm,
            selected_pilot_spec_ids=selected_pilot_spec_ids,
        )
        resolved_card_programmers = card_programmers
        card_programmer_factory: CardProgrammerFactory | None = None
        rule_binding = overlay.contracts.balance_rule_pack
        rule_registry: CardProgrammingRuleRegistry | None = None
        rule_handler_ids: tuple[str, ...] = ()
        if rule_binding is not None:
            if card_binding is None or not card_binding.card_mode_enabled:
                raise ValueError("balance_rule_pack requires an explicitly enabled card catalog")
            rule_registry = default_rule_registry()
            if rule_binding.pack_id != rule_registry.pack_id:
                raise ValueError(
                    f"unknown balance rule pack {rule_binding.pack_id!r}; "
                    f"available pack is {rule_registry.pack_id!r}"
                )
            rule_handler_ids = tuple(rule_binding.handler_ids)
        moves_evasion = overlay.contracts.moves_scaled_evasion
        if moves_evasion is not None and (
            card_binding is None or not card_binding.card_mode_enabled
        ):
            raise ValueError("moves_scaled_evasion requires an explicitly enabled card catalog")
        close_range_falloff = overlay.contracts.close_range_falloff
        if card_binding is not None and card_binding.programmers:
            if card_programmers is not None:
                raise ValueError(
                    "explicit overlay card programmer bindings cannot be combined with "
                    "injected card_programmers"
                )
            card_programmer_factory = CardProgrammerFactory(
                bindings=card_binding.programmers,
                registry=resolved_pilot_registry,
                llm=llm,
                deck_policy=card_binding.deck_policy,
            )
            resolved_card_programmers = build_card_programmers(
                card_binding.programmers,
                registry=resolved_pilot_registry,
                llm=llm,
                deck_policy=card_binding.deck_policy,
            )
        if card_binding is not None and card_binding.card_mode_enabled:
            if card_runtime_snapshot is None:
                raise ValueError("enabled card mode requires an injected card runtime snapshot")
            card_adapter = build_card_runner_adapter(
                snapshot=card_runtime_snapshot,
                programmers=resolved_card_programmers,
                rule_registry=rule_registry,
                rule_handler_ids=rule_handler_ids,
                split_policy=card_binding.deck_policy,
            )
        else:
            card_adapter = None
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
            pilot_registry=resolved_pilot_registry,
            pilot_factory=llm.pilot_factory,
            closer=llm.closer if owns_llm else NoopResourceCloser(),
            learning_artifacts=learning_artifacts,
            card_catalog=card_catalog,
            card_runtime_snapshot=card_runtime_snapshot,
            card_adapter=card_adapter,
            card_programmers=resolved_card_programmers,
            card_programmer_factory=card_programmer_factory,
            card_cadence=card_cadence,
            card_rule_pack_provenance=(
                card_adapter.rule_provenance if card_adapter is not None else None
            ),
            prompt_provenance=llm.prompt_provenance,
            moves_evasion=moves_evasion,
            close_range_falloff=close_range_falloff,
        )
    except Exception:
        if owns_llm:
            llm.close()
        raise


def build_selected_runtime_dependencies(
    overlay: ModelSOApplicationOverlay,
    *,
    pilot_registry: PilotSpecRegistry | None = None,
    selected_provider_id: str | None = None,
    selected_provider_ids: tuple[str, ...] | None = None,
    selected_pilot_spec_ids: tuple[str, ...],
    card_programmers: Mapping[str, ProgrammingPilot] | None = None,
    failure_policy: LlmPilotFailurePolicy = "raise",
    secret_resolver: ProtocolSecretResolver | None = None,
    http_transport: ProtocolHttpTransport | None = None,
    sleeper: ProtocolSleeper | None = None,
) -> RuntimeDependencies:
    """Construct runtime ports around one or more selected live providers."""
    if selected_provider_id is None and selected_provider_ids is None:
        raise ValueError("a selected provider id is required")
    return build_runtime_dependencies(
        overlay,
        pilot_registry=pilot_registry,
        selected_provider_id=selected_provider_id,
        selected_provider_ids=selected_provider_ids,
        selected_pilot_spec_ids=selected_pilot_spec_ids,
        card_programmers=card_programmers,
        llm_failure_policy=failure_policy,
        secret_resolver=secret_resolver,
        http_transport=http_transport,
        sleeper=sleeper,
    )


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
    max_ticks: int | None,
    identity: MatchIdentity,
    red_loadout_path: Path | None = None,
    blue_loadout_path: Path | None = None,
    side_a: str = "red",
    side_b: str = "blue",
    pilots_override: Mapping[str, PilotProtocol] | None = None,
    launch_provenance: ModelSOMatchLaunchProvenance | None = None,
    progress_gate: RuntimeProgressGate | None = None,
    runtime_owner_id: str = "runtime_owner.local",
) -> LiveMatchStack:
    """Pure DI seam used by production root and hermetic tests."""
    _require_valid_budgets(red, dependencies.catalog)
    _require_valid_budgets(blue, dependencies.catalog)
    mech_a = f"mech.{side_a}.01"
    mech_b = f"mech.{side_b}.01"
    required = {mech_a, mech_b}
    pilots = dict(pilots_override or {})
    unexpected = set(pilots) - required
    if unexpected:
        raise ValueError(
            f"pilots_override keys must be a subset of {sorted(required)}; "
            f"got unexpected {sorted(unexpected)}"
        )
    match_observer = LedgerLlmCompletionObserver(
        correlation_id=identity.correlation_id,
        event_factory=dependencies.event_factory,
        emit=dependencies.bus.publish,
    )
    if required - set(pilots):
        bound_pilot_factory = dependencies.pilot_factory.with_observer(match_observer)
        match_dependencies = replace(dependencies, pilot_factory=bound_pilot_factory)
        if mech_a not in pilots:
            pilots[mech_a] = _resolved_pilot(
                red, loadout_path=red_loadout_path, dependencies=match_dependencies
            )
        if mech_b not in pilots:
            pilots[mech_b] = _resolved_pilot(
                blue, loadout_path=blue_loadout_path, dependencies=match_dependencies
            )
    # Card programmers are an explicit overlay capability, but their
    # completion evidence is match-scoped.  Clone the adapter with observed
    # pilots after identity/factory/bus construction; keep the shared runtime
    # dependency graph untouched for subsequent matches.
    card_adapter = dependencies.card_adapter
    if dependencies.card_programmer_factory is not None:
        match_card_programmers = dependencies.card_programmer_factory.for_match(
            identity=identity,
            observer=match_observer,
        )
        if card_adapter is not None:
            card_adapter = replace(card_adapter, programmers=match_card_programmers)
    dependencies.bus.subscribe(dependencies.ledger.append)
    resolved_progress_gate = progress_gate or dependencies.progress_gate or ConditionProgressGate()
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
        launch_provenance=launch_provenance,
        card_runtime_snapshot=dependencies.card_runtime_snapshot,
        card_rule_pack_provenance=dependencies.card_rule_pack_provenance,
        prompt_provenance=dependencies.prompt_provenance,
        card_adapter=card_adapter,
        card_cadence=dependencies.card_cadence,
        moves_evasion=dependencies.moves_evasion,
        close_range_falloff=dependencies.close_range_falloff,
        progress_gate=resolved_progress_gate,
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
            card_catalog=dependencies.card_catalog,
            card_runtime_snapshot=dependencies.card_runtime_snapshot,
            card_rule_pack_provenance=dependencies.card_rule_pack_provenance,
            prompt_provenance=dependencies.prompt_provenance,
            validate_card_events=(card_adapter is not None and card_adapter.registers_enabled),
        ),
    )
    dependencies.bus.subscribe(scoring.handle)

    runtime = MatchRuntime(
        match_id=identity.match_id,
        owner_id=runtime_owner_id,
        run_match=runner.run,
        progress_gate=resolved_progress_gate,
        terminal_evidence=lambda match_id: any(
            event.event_type is SOEventType.MATCH_ENDED
            for event in dependencies.ledger.read_all(match_id)
        ),
    )

    def _on_match_scored(event: ModelSOEventEnvelope) -> None:
        payload = ModelSOMatchScoredPayload.model_validate(event.payload)
        dependencies.leaderboard.on_match_scored(payload)

    dependencies.bus.subscribe(_on_match_scored, event_types=[SOEventType.MATCH_SCORED])

    learning_artifacts = dependencies.learning_artifacts
    if learning_artifacts is not None:
        learning_handler = AfterMatchLearningHandler(
            ledger=dependencies.ledger,
            artifacts=learning_artifacts,
        )
        dependencies.bus.subscribe(
            learning_handler.handle,
            event_types=[SOEventType.MATCH_SCORED],
        )
    return LiveMatchStack(
        identity=identity,
        bus=dependencies.bus,
        runner=runner,
        ledger=dependencies.ledger,
        scoring=scoring,
        leaderboard=dependencies.leaderboard,
        event_factory=dependencies.event_factory,
        catalog=dependencies.catalog,
        runtime=runtime,
        closer=dependencies.closer,
        card_catalog=dependencies.card_catalog,
        card_runtime_snapshot=dependencies.card_runtime_snapshot,
        card_rule_pack_provenance=dependencies.card_rule_pack_provenance,
        prompt_provenance=dependencies.prompt_provenance,
        card_adapter=card_adapter,
    )


def assemble_selected_match_live(
    *,
    overlay: ModelSOApplicationOverlay,
    canonical_overlay: ModelSOApplicationOverlay | None = None,
    roster: ModelSOPlayerRosterBinding,
    pilot_registry: PilotSpecRegistry | None = None,
    sessions: AuthenticatedSessionCapability,
    command: ModelSOStartMatchCommand,
    context: ModelSOStartMatchAuthorityContext,
    identity: MatchIdentity,
    loadouts: Mapping[str, ModelSOLoadout],
    runtime_factory: Callable[[ModelSOApplicationOverlay], RuntimeDependencies],
    live_provider_capability: (
        ProcessLocalOneShotLiveProviderCapability
        | Mapping[str, ProcessLocalOneShotLiveProviderCapability]
        | None
    ) = None,
    live_runtime_factory: Callable[..., RuntimeDependencies] | None = None,
    seed: int,
    max_ticks: int | None,
) -> LiveMatchStack:
    """Admit one selected match before constructing its exact runtime lane."""

    if (live_provider_capability is None) != (live_runtime_factory is None):
        raise ValueError(
            "live_provider_capability and live_runtime_factory must be supplied together"
        )

    resolved_pilot_registry = pilot_registry or load_pilot_registry(
        overlay.contracts.pilot_registry_dir
    )
    provenance = ProcessLocalMatchLaunchCoordinator(
        overlay=overlay,
        canonical_overlay=canonical_overlay,
        roster=roster,
        sessions=sessions,
        pilot_registry=resolved_pilot_registry,
        live_provider_capability=live_provider_capability,
    ).admit_start_match(
        command,
        context=context,
        match_id=identity.match_id,
    )
    assignments = {assignment.side: assignment for assignment in provenance.seat_assignments}
    selected_loadouts: dict[str, ModelSOLoadout] = {}
    sides: tuple[Side, Side] = ("red", "blue")
    for side in sides:
        loadout_id = assignments[side].loadout_id
        try:
            loadout = loadouts[loadout_id]
        except KeyError as exc:
            raise ValueError(f"selected {side} loadout is unavailable: {loadout_id!r}") from exc
        if loadout.id != loadout_id:
            raise ValueError(
                f"selected {side} loadout mapping key {loadout_id!r} does not match "
                f"loadout id {loadout.id!r}"
            )
        selected_loadouts[side] = loadout

    model_identities = {
        model_identity.model_identity_id: model_identity
        for model_identity in overlay.llm.model_identities
    }
    providers = {provider.provider_id: provider for provider in overlay.llm.providers}
    selected_live_bindings: list[tuple[str, str]] = []
    for assignment in assignments.values():
        selected_loadout = selected_loadouts[assignment.side]
        if selected_loadout.pilot_id != assignment.pilot_spec_id:
            raise ValueError(
                f"selected {assignment.side} {assignment.kind} loadout pilot_id "
                f"{selected_loadout.pilot_id!r} does not match admitted pilot_spec_id "
                f"{assignment.pilot_spec_id!r}"
            )
        if not isinstance(assignment, ModelSOModelSeatAssignment):
            continue
        model_identity = model_identities[assignment.model_identity_id]
        provider = providers[model_identity.provider_binding_id]
        if not isinstance(provider, ModelSOStubLlmProviderBinding):
            selected_live_bindings.append((provider.provider_id, assignment.pilot_spec_id))

    # The same configured model may occupy both seats with different
    # contract-bound personas (for example GLM sniper vs GLM opportunist).
    # Distinct selected providers are retained as one explicit tuple so the
    # injected runtime factory can compose one client/pilot lane per identity.
    unique_live_providers = list(
        dict.fromkeys(provider_id for provider_id, _pilot_spec_id in selected_live_bindings)
    )
    if unique_live_providers:
        if live_runtime_factory is None:
            raise ValueError("admitted live provider has no live_runtime_factory")
        selected_provider_selection: str | tuple[str, ...] = (
            unique_live_providers[0]
            if len(unique_live_providers) == 1
            else tuple(unique_live_providers)
        )
        selected_pilot_spec_ids = tuple(
            dict.fromkeys(
                assignment.pilot_spec_id
                for assignment in assignments.values()
                if isinstance(assignment, ModelSOModelSeatAssignment)
                and providers[
                    model_identities[assignment.model_identity_id].provider_binding_id
                ].provider_id
                in unique_live_providers
            )
        )
        dependencies = live_runtime_factory(
            overlay,
            selected_provider_selection,
            selected_pilot_spec_ids,
        )
    else:
        dependencies = runtime_factory(overlay)
    try:
        inbox = ProcessLocalHumanLoopbackCoordinator(sessions=sessions)
        human_claims = {claim.side: claim for claim in context.human_seats}
        pilots: dict[str, PilotProtocol] = {}
        for side in sides:
            assignment = assignments[side]
            mech_id = f"mech.{side}.01"
            if isinstance(assignment, ModelSOHumanSeatAssignment):
                try:
                    claim = human_claims[side]
                except KeyError as exc:
                    raise ValueError(
                        f"admitted human seat {side!r} has no authenticated authority claim"
                    ) from exc
                pilots[mech_id] = HumanPilot(
                    inbox=cast(ProcessLocalHumanDecisionInbox, inbox),
                    principal_id=claim.principal_id,
                    session_id=claim.session_id,
                    side=side,
                )

        stack = assemble_match_with_dependencies(
            dependencies=dependencies,
            red=selected_loadouts["red"],
            blue=selected_loadouts["blue"],
            seed=seed,
            max_ticks=max_ticks,
            identity=identity,
            pilots_override=pilots,
            launch_provenance=provenance,
        )
        return replace(
            stack,
            _launch_provenance=provenance,
            _human_inbox=inbox,
        )
    except Exception:
        dependencies.close()
        raise


def assemble_match_live(
    *,
    overlay: ModelSOApplicationOverlay,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    max_ticks: int | None,
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
    max_ticks: int | None,
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
    "CardProgrammerFactory",
    "IdempotentResourceCloser",
    "LearningDependencies",
    "LiveMatchStack",
    "LlmDependencies",
    "MatchRuntime",
    "MissingCardCatalogError",
    "RuntimeDependencies",
    "SeatIdentityError",
    "SeatProgrammerIdentity",
    "assemble_match_live",
    "assemble_match_with_dependencies",
    "assemble_selected_match_live",
    "build_adaptation_dependencies",
    "build_card_programmers",
    "build_card_runner_adapter",
    "build_duel_executor",
    "build_duel_executor_with_dependencies",
    "build_evaluation_storage_allocator",
    "build_learning_dependencies",
    "build_llm_dependencies",
    "build_pilot_duel_executor_with_dependencies",
    "build_register_execution_reducer",
    "build_runtime_dependencies",
    "load_application_overlay",
    "load_card_catalog",
    "load_card_runtime_snapshot",
    "load_deck_catalog",
    "load_loadout",
    "load_match_contract_catalog",
    "load_model_catalog",
    "load_model_catalog_loadouts",
    "load_model_catalog_pilot_registry",
    "load_model_catalog_runtime_overlay",
    "load_model_catalog_runtime_sources",
    "load_pilot_registry",
    "load_pilot_spec",
    "run_composed_match",
    "validate_seat_programmer_identity",
]
