"""Hermetic proof of the production assembly seam."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID

import pytest

from steel_onslaught.bus.protocol import AdmissionObserver, EventHandler
from steel_onslaught.commands.authority import (
    ModelSOAuthenticatedSession,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    SessionId,
    canonical_overlay_sha256,
)
from steel_onslaught.commands.coordinator import NonStubModelProviderError
from steel_onslaught.commands.live_provider import (
    LiveProviderGrantBindingError,
    ModelSOLiveProviderLaunchGrant,
    ProcessLocalOneShotLiveProviderCapability,
)
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.commands import (
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
    canonical_command_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.contracts.player_selection import (
    ModelSOHumanPlayerOptionBinding,
    ModelSOHumanSeatAssignment,
    ModelSOMatchLaunchProvenance,
    ModelSOModelPlayerOptionBinding,
    ModelSOModelSeatAssignment,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import ModelSOMatchScoredPayload
from steel_onslaught.ledger.admission_scoped import AdmissionScopedLedger
from steel_onslaught.llm.schemas import ModelSOLlmPilotSelection, ProtocolLlmCompletionObserver
from steel_onslaught.match import composition
from steel_onslaught.match.card_adapter import CardRunnerAdapter
from steel_onslaught.match.composition import RuntimeDependencies, build_card_runner_adapter
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.runtime import ConditionProgressGate
from steel_onslaught.pilots.human import HumanPilot
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol
from steel_onslaught.projections.leaderboard.protocol import (
    LeaderboardRepository,
    ModelSOLeaderboardEntry,
)
from steel_onslaught.reducers import scoring as scoring_module


class _Bus:
    def __init__(self) -> None:
        self.handlers: list[EventHandler] = []
        self.admission_observers: list[AdmissionObserver] = []

    def publish(self, event: ModelSOEventEnvelope) -> None:
        for handler in tuple(self.handlers):
            handler(event)
        # Faithful substitution (OMN-15490): the real bus reports exactly one
        # admission verdict per event after dispatch.  Nothing in this fake
        # refuses, so every event is admitted -- an observer wired here is
        # exercised rather than silently stranded.
        for observer in tuple(self.admission_observers):
            observer.on_event_admitted(event)

    def subscribe(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> int:
        del event_types
        self.handlers.append(handler)
        return len(self.handlers)

    def subscribe_admission(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> int:
        # OMN-15490: dispatch position is identical; the flag only decides
        # whether a refusal rolls the publish tree back.
        return self.subscribe(handler, event_types)

    def enlist_admission_observer(self, observer: AdmissionObserver) -> None:
        self.admission_observers.append(observer)

    def unsubscribe(self, token: int) -> None:
        del token


class _Ledger:
    def __init__(self) -> None:
        self.events: list[ModelSOEventEnvelope] = []

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return iter(event for event in self.events if event.match_id == match_id)

    def read_match_ids(self) -> Iterator[str]:
        return iter(sorted({event.match_id for event in self.events}))

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return iter(
            event for event in self.events if event.match_id == match_id and event.tick > after_tick
        )

    def contains_match(self, match_id: str) -> bool:
        return any(event.match_id == match_id for event in self.events)

    def read_at(
        self,
        match_id: str,
        tick: int,
        *,
        event_types: frozenset[SOEventType] | None,
    ) -> Iterator[ModelSOEventEnvelope]:
        return iter(
            event
            for event in self.events
            if event.match_id == match_id
            and event.tick == tick
            and (event_types is None or event.event_type in event_types)
        )


class _Leaderboard:
    def on_match_scored(self, payload: ModelSOMatchScoredPayload) -> None:
        del payload

    def top_n(self, n: int) -> list[ModelSOLeaderboardEntry]:
        del n
        return []


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 7, 16, tzinfo=UTC)


class _Identities:
    def new_match_id(self) -> str:
        return "match.fake.001"

    def new_correlation_id(self) -> UUID:
        return UUID("11111111-1111-1111-1111-111111111111")

    def new_event_id(self) -> str:
        return "01JABCDE0123456789ABCDEF01"

    def new_message_id(self) -> UUID:
        return UUID("22222222-2222-2222-2222-222222222222")


class _Registry:
    def resolve(self, loadout: ModelSOLoadout) -> object:
        del loadout
        return object()


class _Catalog:
    safety_gizmo_ids: frozenset[str] = frozenset()


class _Closer:
    def close(self) -> None:
        return


class _PilotFactory:
    def with_observer(self, observer: ProtocolLlmCompletionObserver) -> _PilotFactory:
        del observer
        return self

    def from_spec(self, spec: ModelSOPilotSpec) -> PilotProtocol:
        del spec
        return cast(PilotProtocol, object())

    def llm_pilot(self, selection: ModelSOLlmPilotSelection) -> PilotProtocol:
        del selection
        return cast(PilotProtocol, object())


class _Sessions:
    def __init__(self) -> None:
        self.resolve_count = 0
        self._session = ModelSOAuthenticatedSession(
            principal_id="principal.local_operator",
            session_id="session.local_operator",
            human_identity_id="human_identity.local_operator",
            permissions=("match:create", "seat:red"),
        )

    def resolve(
        self,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOAuthenticatedSession | None:
        self.resolve_count += 1
        if (principal_id, session_id) == (
            self._session.principal_id,
            self._session.session_id,
        ):
            return self._session
        return None


class _LiveProviderGrantBindings(TypedDict):
    creator_principal_id: str
    creator_session_id: str
    launch_command_id: UUID
    launch_command_sha256: str
    overlay_sha256: str
    roster_sha256: str
    model_identity_id: str
    provider_id: str


def _loadout(name: str, pilot_spec_id: str = "pilot.fake.v1") -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(
        {
            "id": f"loadout.fake.{name}",
            "chassis_id": "chassis.fake",
            "boiler_id": "boiler.fake",
            "pilot_id": pilot_spec_id,
            "modules": {},
            "budgets": {
                "points_used": 0,
                "points_max": 1,
                "mass_used": 0,
                "mass_max": 1,
                "slots_used": 0,
                "slots_max": 1,
                "expected_heat_peak": 0,
                "expected_signature": 0,
            },
        }
    )


def _card_runtime_snapshot(*, selected: bool) -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.advance",
                display_name="Advance",
                category=SOCardCategory.MOVEMENT,
                priority=100,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.composition",
        display_name="Composition deck",
        hand_size=1,
        register_count=1,
        cards=(ModelSODeckEntry(card_id="card.test.advance", count=1),),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id if selected else None,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _selection_overlay(tmp_path: Any) -> ModelSOApplicationOverlay:
    pilot_registry_dir = tmp_path / "pilots"
    pilot_registry_dir.mkdir()
    for provider_id in ("stub", "local", "openrouter", "glm", "gemini"):
        (pilot_registry_dir / f"fake_{provider_id}.yaml").write_text(
            'schema_version: "0.1.0"\n'
            "kind: steel_onslaught.pilot\n"
            f"id: pilot.fake.{provider_id}\n"
            f"display_name: {provider_id}\n"
            "archetype: llm\n"
            "lineage:\n  parent: pilot.template.llm\n"
            "parameters:\n"
            "  persona: configured\n"
            f"  provider: {provider_id}\n",
            encoding="utf-8",
        )
    (pilot_registry_dir / "fake_v1.yaml").write_text(
        (pilot_registry_dir / "fake_stub.yaml")
        .read_text(encoding="utf-8")
        .replace("id: pilot.fake.stub", "id: pilot.fake.v1"),
        encoding="utf-8",
    )
    providers: list[dict[str, object]] = [
        {"kind": "stub", "provider_id": "stub", "model": "fixture"},
    ]
    for provider_id, endpoint in (
        ("local", "http://127.0.0.1:11434/v1"),
        ("openrouter", "https://openrouter.ai/api/v1"),
        ("glm", "https://open.bigmodel.cn/api/paas/v4"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ):
        providers.append(
            {
                "kind": "openai_compatible",
                "provider_id": provider_id,
                "endpoint_url": endpoint,
                "model": f"{provider_id}-fixture",
                "secret_ref": None,
                "timeout_seconds": 1.0,
                "max_tokens": 16,
                "retry": {
                    "max_attempts": 1,
                    "initial_backoff_seconds": 0.0,
                    "backoff_multiplier": 1.0,
                },
            }
        )
    identities = [
        {
            "schema_version": "1",
            "kind": "steel_onslaught.model_identity",
            "model_identity_id": f"model_identity.{provider_id}",
            "display_name": provider_id,
            "provider_binding_id": provider_id,
        }
        for provider_id in ("stub", "local", "openrouter", "glm", "gemini")
    ]
    return ModelSOApplicationOverlay.model_validate(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": tmp_path / "events.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": tmp_path / "leaderboard.sqlite3",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "storage_schema": "leaderboard_v1",
            },
            "learning_artifacts": {
                "kind": "filesystem_yaml",
                "evaluation_root": tmp_path / "evaluations",
                "lineage_root": tmp_path / "lineage",
                "experiment_root": tmp_path / "experiments",
            },
            "evaluation_storage": {
                "kind": "sqlite",
                "root": tmp_path / "evaluation_storage",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
                "leaderboard_schema": "leaderboard_v1",
            },
            "contracts": {
                "catalog_dir": tmp_path / "catalog",
                "pilot_registry_dir": pilot_registry_dir,
                "arena_id": "open_field",
            },
            "llm": {
                "providers": providers,
                "model_identities": identities,
                "personas_dir": tmp_path / "personas",
                "secret_resolver": {"kind": "none"},
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
            "frontend_transport": {
                "kind": "websocket",
                "contract": "steel_onslaught.frontend_transport.v1",
                "websocket_url": "ws://127.0.0.1:8765/events",
                "event_schema": "canonical_event_v1",
                "milliseconds_per_tick": 500,
            },
        }
    )


def _selection_roster(model_identity: str) -> ModelSOPlayerRosterBinding:
    human = ModelSOHumanPlayerOptionBinding(
        kind="human",
        option_id="player_option.browser_human",
        display_name="Browser pilot",
        human_identity_id="human_identity.local_operator",
        pilot_spec_id="pilot.fake.v1",
        input_source="browser_command",
    )
    model = ModelSOModelPlayerOptionBinding(
        kind="model",
        option_id="player_option.configured_model",
        display_name="Configured model",
        model_identity_id=model_identity,
        pilot_spec_id=(
            "pilot.fake.v1"
            if model_identity == "model_identity.stub"
            else f"pilot.fake.{model_identity.removeprefix('model_identity.')}"
        ),
        persona_id="configured",
        input_source="llm_completion",
    )
    return ModelSOPlayerRosterBinding(
        schema_version="1",
        kind="steel_onslaught.player_roster",
        roster_id="roster.local_play",
        options=(human, model),
        seats=(
            ModelSOSeatLaunchPolicy(
                side="red",
                loadout_id="loadout.fake.red",
                allowed_option_ids=(human.option_id,),
            ),
            ModelSOSeatLaunchPolicy(
                side="blue",
                loadout_id="loadout.fake.blue",
                allowed_option_ids=(model.option_id,),
            ),
        ),
    )


def _selection_command(
    overlay: ModelSOApplicationOverlay,
    roster: ModelSOPlayerRosterBinding,
) -> ModelSOStartMatchCommand:
    return ModelSOStartMatchCommand(
        schema_version="1",
        kind="steel_onslaught.start_match",
        command_id=UUID("33333333-3333-4333-8333-333333333333"),
        expected_overlay_sha256=canonical_overlay_sha256(overlay),
        expected_roster_sha256=roster.canonical_sha256(),
        selections=(
            ModelSOStartMatchSeatSelection(side="red", option_id="player_option.browser_human"),
            ModelSOStartMatchSeatSelection(side="blue", option_id="player_option.configured_model"),
        ),
    )


def _selection_context() -> ModelSOStartMatchAuthorityContext:
    return ModelSOStartMatchAuthorityContext(
        creator_principal_id="principal.local_operator",
        creator_session_id="session.local_operator",
        human_seats=(
            ModelSOHumanSeatAuthorityClaim(
                side="red",
                principal_id="principal.local_operator",
                session_id="session.local_operator",
            ),
        ),
    )


def _option_sha256(
    option: ModelSOHumanPlayerOptionBinding | ModelSOModelPlayerOptionBinding,
) -> str:
    canonical = json.dumps(
        option.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.unit
def test_assembly_accepts_all_fake_ports_without_filesystem_or_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "_require_valid_budgets", lambda *_: None)
    bus = _Bus()
    ledger = _Ledger()
    clock = _Clock()
    identities = _Identities()
    event_factory = EventFactory(clock=clock, identities=identities)

    dependencies = RuntimeDependencies(
        bus=bus,
        ledger=ledger,
        leaderboard=cast(LeaderboardRepository, _Leaderboard()),
        clock=clock,
        identities=identities,
        event_factory=event_factory,
        catalog=cast(MatchContractCatalog, _Catalog()),
        arena=ModelSOArenaSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.arena",
            arena_id="injected_test_arena",
            display_name="Injected test arena",
            size=40,
            spawn_a=ModelSOPosition(x=5, y=5),
            spawn_b=ModelSOPosition(x=35, y=35),
            obstacles=(),
            rects=(),
        ),
        pilot_registry=cast(Any, _Registry()),
        pilot_factory=_PilotFactory(),
        closer=_Closer(),
        card_catalog=ModelSOCardCatalog(
            cards=(
                ModelSOCard(
                    schema_version="0.1.0",
                    kind="steel_onslaught.card",
                    id="card.test.advance",
                    display_name="Advance",
                    category=SOCardCategory.MOVEMENT,
                    priority=100,
                    heat_cost=0,
                    effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
                ),
            )
        ),
    )
    identity = MatchIdentity(
        match_id=identities.new_match_id(),
        correlation_id=identities.new_correlation_id(),
    )

    progress_gate = ConditionProgressGate()
    stack = composition.assemble_match_with_dependencies(
        dependencies=dependencies,
        red=_loadout("red"),
        blue=_loadout("blue"),
        seed=7,
        max_ticks=3,
        identity=identity,
        progress_gate=progress_gate,
        runtime_owner_id="runtime_owner.test",
    )

    assert stack.identity is identity
    assert stack.runner.identity is identity
    # OMN-15490: the stack exposes the admission-scoped facade, which must wrap
    # the INJECTED port -- the assembly still builds no ledger of its own.
    assert isinstance(stack.ledger, AdmissionScopedLedger)
    assert stack.ledger.durable_ledger is ledger
    assert stack.bus is bus
    assert stack.runtime.match_id == stack.match_id
    assert stack.runtime.progress_gate is progress_gate
    assert stack.card_catalog is dependencies.card_catalog
    assert len(bus.handlers) == 7


@pytest.mark.unit
def test_card_runner_adapter_binds_selected_snapshot_and_round_length() -> None:
    snapshot = _card_runtime_snapshot(selected=True)
    adapter = build_card_runner_adapter(snapshot=snapshot)

    assert isinstance(adapter, CardRunnerAdapter)
    assert adapter.registers_enabled is True
    assert adapter.snapshot is snapshot
    assert adapter.card_round_runtime is not None
    assert adapter.card_round_runtime.snapshot is snapshot
    assert adapter.card_round_runtime.round_length == snapshot.selected_deck.register_count
    assert adapter.dealer is adapter.card_round_runtime.dealer
    assert adapter.reducer is adapter.card_round_runtime.reducer


@pytest.mark.unit
def test_card_runner_adapter_fails_closed_without_selected_deck() -> None:
    with pytest.raises(ValueError, match="no explicitly selected deck_id"):
        build_card_runner_adapter(snapshot=_card_runtime_snapshot(selected=False))


@pytest.mark.unit
def test_passive_card_snapshot_does_not_activate_card_mode() -> None:
    snapshot = _card_runtime_snapshot(selected=False)
    dependencies = RuntimeDependencies(
        bus=cast(Any, object()),
        ledger=cast(Any, object()),
        leaderboard=cast(Any, object()),
        clock=cast(Any, object()),
        identities=cast(Any, object()),
        event_factory=cast(Any, object()),
        catalog=cast(Any, object()),
        arena=cast(Any, object()),
        pilot_registry=cast(Any, object()),
        pilot_factory=cast(Any, object()),
        closer=cast(Any, object()),
        card_catalog=snapshot.card_catalog,
        card_runtime_snapshot=snapshot,
    )

    assert dependencies.card_runtime_snapshot is snapshot
    assert dependencies.card_adapter is None

    with pytest.raises(ValueError, match="paced card cadence requires enabled card mode"):
        replace(dependencies, card_cadence="paced")


@pytest.mark.unit
def test_active_card_adapter_is_passed_through_match_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "_require_valid_budgets", lambda *_: None)
    snapshot = _card_runtime_snapshot(selected=True)
    adapter = build_card_runner_adapter(snapshot=snapshot)
    bus = _Bus()
    clock = _Clock()
    identities = _Identities()
    dependencies = RuntimeDependencies(
        bus=bus,
        ledger=_Ledger(),
        leaderboard=cast(LeaderboardRepository, _Leaderboard()),
        clock=clock,
        identities=identities,
        event_factory=EventFactory(clock=clock, identities=identities),
        catalog=cast(MatchContractCatalog, _Catalog()),
        arena=ModelSOArenaSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.arena",
            arena_id="injected_test_arena",
            display_name="Injected test arena",
            size=40,
            spawn_a=ModelSOPosition(x=5, y=5),
            spawn_b=ModelSOPosition(x=35, y=35),
            obstacles=(),
            rects=(),
        ),
        pilot_registry=cast(Any, _Registry()),
        pilot_factory=_PilotFactory(),
        closer=_Closer(),
        card_catalog=snapshot.card_catalog,
        card_runtime_snapshot=snapshot,
        card_adapter=adapter,
        card_cadence="paced",
    )
    stack = composition.assemble_match_with_dependencies(
        dependencies=dependencies,
        red=_loadout("red"),
        blue=_loadout("blue"),
        seed=7,
        max_ticks=3,
        identity=MatchIdentity(
            match_id=identities.new_match_id(),
            correlation_id=identities.new_correlation_id(),
        ),
    )

    assert stack.card_adapter is adapter
    assert stack.runner._card_adapter is adapter
    assert stack.runner._card_cadence == "paced"


@pytest.mark.unit
@pytest.mark.parametrize("validate_card_events", [False, True])
def test_verify_replay_validity_forwards_card_validation_mode(
    monkeypatch: pytest.MonkeyPatch,
    validate_card_events: bool,
) -> None:
    captured: dict[str, object] = {}

    class _Replay:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            captured.update(kwargs)

        def reconstruct_at_tick(self, _tick: int) -> object:
            return live_state

    monkeypatch.setattr(scoring_module, "ReplayEngine", _Replay)
    live_state = cast(Any, type("LiveState", (), {"tick": 3})())
    result = scoring_module.verify_replay_validity(
        cast(Any, object()),
        "match.test",
        live_state,
        catalog=cast(Any, object()),
        event_factory=cast(Any, object()),
        validate_card_events=validate_card_events,
    )

    assert result is True
    assert captured["validate_card_events"] is validate_card_events


@pytest.mark.unit
def test_register_factory_binds_snapshot_without_loader_or_bus_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        composition,
        "load_card_catalog",
        lambda *_args: pytest.fail("register DI must not load card files"),
    )

    class _ForbiddenBus:
        def subscribe(self, *_args: object, **_kwargs: object) -> int:
            raise AssertionError("register DI must not subscribe to the bus")

        def publish(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("register DI must not publish events")

    class _ForbiddenLedger:
        def read_all(self, *_args: object, **_kwargs: object) -> Iterator[Any]:
            raise AssertionError("register DI must not read the ledger")

    # Reuse the actual dependency fixture shape from the neighboring assembly
    # test; only the card snapshot and forbidden outer ports matter here.
    dependencies = RuntimeDependencies(
        bus=cast(Any, _ForbiddenBus()),
        ledger=cast(Any, _ForbiddenLedger()),
        leaderboard=cast(Any, object()),
        clock=cast(Any, object()),
        identities=cast(Any, object()),
        event_factory=cast(Any, object()),
        catalog=cast(Any, object()),
        arena=cast(Any, object()),
        pilot_registry=cast(Any, object()),
        pilot_factory=cast(Any, object()),
        closer=cast(Any, object()),
        card_catalog=ModelSOCardCatalog(
            cards=(
                ModelSOCard(
                    schema_version="0.1.0",
                    kind="steel_onslaught.card",
                    id="card.test.advance",
                    display_name="Advance",
                    category=SOCardCategory.MOVEMENT,
                    priority=100,
                    heat_cost=0,
                    effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
                ),
            )
        ),
    )

    reducer = composition.build_register_execution_reducer(dependencies)
    second = composition.build_register_execution_reducer(dependencies)
    assert reducer.card_catalog is dependencies.card_catalog
    assert second is not reducer
    assert second.card_catalog is reducer.card_catalog

    missing = replace(dependencies, card_catalog=None)
    with pytest.raises(composition.MissingCardCatalogError):
        composition.build_register_execution_reducer(missing)
    with pytest.raises(TypeError, match="requires RuntimeDependencies"):
        composition.build_register_execution_reducer(cast(Any, object()))


@pytest.mark.unit
def test_selected_runtime_forwards_explicit_browser_fallback_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browser live composition may opt into per-turn provider fallback."""
    captured: dict[str, object] = {}
    sentinel = cast(RuntimeDependencies, object())

    def fake_build_runtime(overlay: object, **kwargs: object) -> RuntimeDependencies:
        captured["overlay"] = overlay
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(composition, "build_runtime_dependencies", fake_build_runtime)
    overlay = cast(ModelSOApplicationOverlay, object())
    result = composition.build_selected_runtime_dependencies(
        overlay,
        selected_provider_id="glm",
        selected_pilot_spec_ids=("pilot.live.glm",),
        failure_policy="fallback",
    )

    assert result is sentinel
    assert captured["overlay"] is overlay
    assert captured["selected_provider_id"] == "glm"
    assert captured["selected_pilot_spec_ids"] == ("pilot.live.glm",)
    assert captured["llm_failure_policy"] == "fallback"


@pytest.mark.unit
def test_selected_runtime_forwards_distinct_provider_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = cast(RuntimeDependencies, object())

    def fake_build_runtime(overlay: object, **kwargs: object) -> RuntimeDependencies:
        captured["overlay"] = overlay
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(composition, "build_runtime_dependencies", fake_build_runtime)
    overlay = cast(ModelSOApplicationOverlay, object())
    result = composition.build_selected_runtime_dependencies(
        overlay,
        selected_provider_ids=("local", "openrouter"),
        selected_pilot_spec_ids=("pilot.local", "pilot.openrouter"),
    )

    assert result is sentinel
    assert captured["selected_provider_ids"] == ("local", "openrouter")
    assert captured["selected_pilot_spec_ids"] == ("pilot.local", "pilot.openrouter")


@pytest.mark.unit
def test_selected_human_and_stub_match_admits_before_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setattr(composition, "_require_valid_budgets", lambda *_: None)
    overlay = _selection_overlay(tmp_path)
    roster = _selection_roster("model_identity.stub")
    command = _selection_command(overlay, roster)
    context = _selection_context()
    sessions = _Sessions()
    identity = MatchIdentity(
        match_id="match.01JABCDE0123456789ABCDEFGX",
        correlation_id=UUID("11111111-1111-4111-8111-111111111111"),
    )
    bus = _Bus()
    dependencies = RuntimeDependencies(
        bus=bus,
        ledger=_Ledger(),
        leaderboard=cast(LeaderboardRepository, _Leaderboard()),
        clock=_Clock(),
        identities=_Identities(),
        event_factory=EventFactory(clock=_Clock(), identities=_Identities()),
        catalog=cast(MatchContractCatalog, _Catalog()),
        arena=ModelSOArenaSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.arena",
            arena_id="injected_test_arena",
            display_name="Injected test arena",
            size=40,
            spawn_a=ModelSOPosition(x=5, y=5),
            spawn_b=ModelSOPosition(x=35, y=35),
            obstacles=(),
            rects=(),
        ),
        pilot_registry=cast(Any, _Registry()),
        pilot_factory=_PilotFactory(),
        closer=_Closer(),
    )
    factory_calls = 0

    def runtime_factory(candidate: ModelSOApplicationOverlay) -> RuntimeDependencies:
        nonlocal factory_calls
        assert candidate is overlay
        assert sessions.resolve_count > 0, "authentication/admission must precede runtime factory"
        factory_calls += 1
        return dependencies

    red = _loadout("red")
    blue = _loadout("blue")

    stack = composition.assemble_selected_match_live(
        overlay=overlay,
        roster=roster,
        sessions=sessions,
        command=command,
        context=context,
        identity=identity,
        loadouts={red.id: red, blue.id: blue},
        runtime_factory=runtime_factory,
        seed=7,
        max_ticks=3,
    )

    options = {option.option_id: option for option in roster.options}
    expected = ModelSOMatchLaunchProvenance(
        schema_version="1",
        kind="steel_onslaught.match_launch_provenance",
        match_id=identity.match_id,
        launch_command_id=command.command_id,
        launch_command_sha256=canonical_command_sha256(command),
        overlay_sha256=canonical_overlay_sha256(overlay),
        roster_id=roster.roster_id,
        roster_sha256=roster.canonical_sha256(),
        seat_assignments=(
            ModelSOHumanSeatAssignment(
                kind="human",
                side="red",
                player_id="player.red",
                option_id="player_option.browser_human",
                loadout_id=red.id,
                pilot_spec_id=red.pilot_id,
                option_sha256=_option_sha256(options["player_option.browser_human"]),
                human_identity_id="human_identity.local_operator",
                input_source="browser_command",
            ),
            ModelSOModelSeatAssignment(
                kind="model",
                side="blue",
                player_id="player.blue",
                option_id="player_option.configured_model",
                loadout_id=blue.id,
                pilot_spec_id=blue.pilot_id,
                option_sha256=_option_sha256(options["player_option.configured_model"]),
                model_identity_id="model_identity.stub",
                persona_id="configured",
                input_source="llm_completion",
            ),
        ),
    )

    assert factory_calls == 1
    assert stack.runner._launch_provenance == expected
    assert isinstance(stack.runner._pilots["mech.red.01"], HumanPilot)
    assert "endpoint_url" not in expected.model_dump_json()
    assert "secret_ref" not in expected.model_dump_json()


@pytest.mark.unit
def test_selected_human_loadout_pilot_mismatch_fails_before_runtime_factory(
    tmp_path: Any,
) -> None:
    overlay = _selection_overlay(tmp_path)
    roster = _selection_roster("model_identity.stub")
    factory_calls = 0

    def forbidden_runtime_factory(
        candidate: ModelSOApplicationOverlay,
    ) -> RuntimeDependencies:
        nonlocal factory_calls
        del candidate
        factory_calls += 1
        raise AssertionError("pilot mismatch must fail before runtime construction")

    with pytest.raises(ValueError, match="selected red human loadout pilot_id"):
        composition.assemble_selected_match_live(
            overlay=overlay,
            roster=roster,
            sessions=_Sessions(),
            command=_selection_command(overlay, roster),
            context=_selection_context(),
            identity=MatchIdentity(
                match_id="match.01JABCDE0123456789ABCDEFGX",
                correlation_id=UUID("11111111-1111-4111-8111-111111111111"),
            ),
            loadouts={
                "loadout.fake.red": _loadout("red", "pilot.fake.other"),
                "loadout.fake.blue": _loadout("blue"),
            },
            runtime_factory=forbidden_runtime_factory,
            seed=7,
            max_ticks=3,
        )

    assert factory_calls == 0


@pytest.mark.unit
@pytest.mark.parametrize("provider_id", ["local", "openrouter", "glm", "gemini"])
def test_selected_non_stub_provider_rejects_before_runtime_factory(
    provider_id: str,
    tmp_path: Any,
) -> None:
    overlay = _selection_overlay(tmp_path)
    roster = _selection_roster(f"model_identity.{provider_id}")
    factory_calls = 0

    def forbidden_runtime_factory(
        candidate: ModelSOApplicationOverlay,
    ) -> RuntimeDependencies:
        nonlocal factory_calls
        del candidate
        factory_calls += 1
        raise AssertionError("non-stub selection must fail before runtime construction")

    with pytest.raises(NonStubModelProviderError, match="stub"):
        composition.assemble_selected_match_live(
            overlay=overlay,
            roster=roster,
            sessions=_Sessions(),
            command=_selection_command(overlay, roster),
            context=_selection_context(),
            identity=MatchIdentity(
                match_id="match.01JABCDE0123456789ABCDEFGX",
                correlation_id=UUID("11111111-1111-4111-8111-111111111111"),
            ),
            loadouts={
                "loadout.fake.red": _loadout("red", f"pilot.fake.{provider_id}"),
                "loadout.fake.blue": _loadout("blue", f"pilot.fake.{provider_id}"),
            },
            runtime_factory=forbidden_runtime_factory,
            seed=7,
            max_ticks=3,
        )

    assert factory_calls == 0


@pytest.mark.unit
def test_selected_live_provider_admits_before_only_exact_live_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setattr(composition, "_require_valid_budgets", lambda *_: None)
    overlay = _selection_overlay(tmp_path)
    roster = _selection_roster("model_identity.local")
    command = _selection_command(overlay, roster)
    context = _selection_context()
    identity = MatchIdentity(
        match_id="match.01JABCDE0123456789ABCDEFGX",
        correlation_id=UUID("11111111-1111-4111-8111-111111111111"),
    )
    red = _loadout("red")
    blue = _loadout("blue", "pilot.fake.local")
    dependencies = RuntimeDependencies(
        bus=_Bus(),
        ledger=_Ledger(),
        leaderboard=cast(LeaderboardRepository, _Leaderboard()),
        clock=_Clock(),
        identities=_Identities(),
        event_factory=EventFactory(clock=_Clock(), identities=_Identities()),
        catalog=cast(MatchContractCatalog, _Catalog()),
        arena=ModelSOArenaSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.arena",
            arena_id="injected_test_arena",
            display_name="Injected test arena",
            size=40,
            spawn_a=ModelSOPosition(x=5, y=5),
            spawn_b=ModelSOPosition(x=35, y=35),
            obstacles=(),
            rects=(),
        ),
        pilot_registry=cast(Any, _Registry()),
        pilot_factory=_PilotFactory(),
        closer=_Closer(),
    )
    bindings: _LiveProviderGrantBindings = {
        "creator_principal_id": context.creator_principal_id,
        "creator_session_id": context.creator_session_id,
        "launch_command_id": command.command_id,
        "launch_command_sha256": canonical_command_sha256(command),
        "overlay_sha256": canonical_overlay_sha256(overlay),
        "roster_sha256": roster.canonical_sha256(),
        "model_identity_id": "model_identity.local",
        "provider_id": "local",
    }
    normal_calls = 0
    live_calls: list[tuple[str, tuple[str, ...]]] = []

    def forbidden_runtime_factory(candidate: ModelSOApplicationOverlay) -> RuntimeDependencies:
        nonlocal normal_calls
        del candidate
        normal_calls += 1
        raise AssertionError("live selection must not construct the default runtime")

    def live_runtime_factory(
        candidate: ModelSOApplicationOverlay,
        provider_id: str,
        pilot_spec_ids: tuple[str, ...],
    ) -> RuntimeDependencies:
        assert candidate is overlay
        live_calls.append((provider_id, pilot_spec_ids))
        return dependencies

    mismatched = ModelSOLiveProviderLaunchGrant(**(bindings | {"launch_command_sha256": "f" * 64}))
    with pytest.raises(LiveProviderGrantBindingError, match="launch_command_sha256"):
        composition.assemble_selected_match_live(
            overlay=overlay,
            roster=roster,
            sessions=_Sessions(),
            command=command,
            context=context,
            identity=identity,
            loadouts={red.id: red, blue.id: blue},
            runtime_factory=forbidden_runtime_factory,
            live_provider_capability=ProcessLocalOneShotLiveProviderCapability(grant=mismatched),
            live_runtime_factory=live_runtime_factory,
            seed=7,
            max_ticks=3,
        )
    assert normal_calls == 0
    assert live_calls == []

    sessions = _Sessions()
    capability = ProcessLocalOneShotLiveProviderCapability(
        grant=ModelSOLiveProviderLaunchGrant(**bindings)
    )
    stack = composition.assemble_selected_match_live(
        overlay=overlay,
        roster=roster,
        sessions=sessions,
        command=command,
        context=context,
        identity=identity,
        loadouts={red.id: red, blue.id: blue},
        runtime_factory=forbidden_runtime_factory,
        live_provider_capability=capability,
        live_runtime_factory=live_runtime_factory,
        seed=7,
        max_ticks=3,
    )

    assert sessions.resolve_count > 0
    assert capability.consumption_count == 1
    assert normal_calls == 0
    assert live_calls == [("local", ("pilot.fake.local",))]
    stack.close()
