"""Hermetic proof of the production assembly seam."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from steel_onslaught.bus.protocol import EventHandler
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
from steel_onslaught.contracts.commands import (
    ModelSOStartMatchCommand,
    ModelSOStartMatchSeatSelection,
    canonical_command_sha256,
)
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
from steel_onslaught.llm.schemas import ModelSOLlmPilotSelection, ProtocolLlmCompletionObserver
from steel_onslaught.match import composition
from steel_onslaught.match.composition import RuntimeDependencies
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.pilots.human import HumanPilot
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol
from steel_onslaught.projections.leaderboard.protocol import (
    LeaderboardRepository,
    ModelSOLeaderboardEntry,
)


class _Bus:
    def __init__(self) -> None:
        self.handlers: list[EventHandler] = []

    def publish(self, event: ModelSOEventEnvelope) -> None:
        for handler in tuple(self.handlers):
            handler(event)

    def subscribe(
        self,
        handler: EventHandler,
        event_types: list[SOEventType] | None = None,
    ) -> int:
        del event_types
        self.handlers.append(handler)
        return len(self.handlers)

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


def _loadout(name: str) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(
        {
            "id": f"loadout.fake.{name}",
            "chassis_id": "chassis.fake",
            "boiler_id": "boiler.fake",
            "pilot_id": "pilot.fake.v1",
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


def _selection_overlay(tmp_path: Any) -> ModelSOApplicationOverlay:
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
                "pilot_registry_dir": tmp_path / "pilots",
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
        pilot_spec_id="pilot.fake.v1",
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
    )
    identity = MatchIdentity(
        match_id=identities.new_match_id(),
        correlation_id=identities.new_correlation_id(),
    )

    stack = composition.assemble_match_with_dependencies(
        dependencies=dependencies,
        red=_loadout("red"),
        blue=_loadout("blue"),
        seed=7,
        max_ticks=3,
        identity=identity,
    )

    assert stack.identity is identity
    assert stack.runner.identity is identity
    assert stack.ledger is ledger
    assert stack.bus is bus
    assert len(bus.handlers) == 7


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
                "loadout.fake.red": _loadout("red"),
                "loadout.fake.blue": _loadout("blue"),
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
    blue = _loadout("blue")
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
    bindings = {
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
    assert live_calls == [("local", ("pilot.fake.v1",))]
    stack.close()
