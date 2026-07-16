"""Hermetic proof of the production assembly seam."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from steel_onslaught.bus.protocol import EventHandler
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match import composition
from steel_onslaught.match.composition import RuntimeDependencies
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.pilots.schemas import PilotProtocol
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
    def on_match_scored(self, payload: dict[str, Any]) -> None:
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


def _loadout(name: str) -> ModelSOLoadout:
    return ModelSOLoadout.model_validate(
        {
            "id": f"loadout.fake.{name}",
            "chassis_id": "chassis.fake",
            "boiler_id": "boiler.fake",
            "pilot_id": "pilot.fake",
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

    def pilot_factory(_: object) -> PilotProtocol:
        return cast(PilotProtocol, object())

    dependencies = RuntimeDependencies(
        bus=bus,
        ledger=ledger,
        leaderboard=cast(LeaderboardRepository, _Leaderboard()),
        clock=clock,
        identities=identities,
        event_factory=event_factory,
        catalog=cast(MatchContractCatalog, _Catalog()),
        pilot_registry=cast(Any, _Registry()),
        pilot_factory=cast(Any, pilot_factory),
        learning_artifacts=cast(Any, object()),
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
