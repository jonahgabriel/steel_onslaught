"""Strict deterministic dependency factories for runtime-facing tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.composition import (
    load_match_contract_catalog,
    load_pilot_registry,
    pilot_from_spec,
)
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.pilots.schemas import ModelSOPosition

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACTS = _REPO_ROOT / "contracts_data"
_NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return _NOW


class SequentialIdentities:
    def __init__(self) -> None:
        self._event = 0
        self._message = 0

    def new_match_id(self) -> str:
        return "match.test.injected"

    def new_correlation_id(self) -> UUID:
        return UUID("11111111-1111-1111-1111-111111111111")

    def new_event_id(self) -> str:
        self._event += 1
        return f"01J{self._event:023d}"

    def new_message_id(self) -> UUID:
        self._message += 1
        return UUID(int=self._message)


@dataclass(frozen=True)
class TestRuntime:
    event_factory: EventFactory
    catalog: MatchContractCatalog


def runtime_dependencies() -> TestRuntime:
    identities = SequentialIdentities()
    return TestRuntime(
        event_factory=EventFactory(clock=FixedClock(), identities=identities),
        catalog=load_match_contract_catalog(_CONTRACTS),
    )


def match_runner(
    *,
    bus: EventBus,
    match_id: str,
    seed: int,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    max_ticks: int,
    side_a: str = "a",
    side_b: str = "b",
    spawn_a: ModelSOPosition | None = None,
    spawn_b: ModelSOPosition | None = None,
) -> tuple[MatchRunner, TestRuntime]:
    runtime = runtime_dependencies()
    resolved_spawn_a = spawn_a or ModelSOPosition(x=0, y=0)
    resolved_spawn_b = spawn_b or ModelSOPosition(x=10, y=10)
    identities = runtime.event_factory.identities
    registry = load_pilot_registry(_CONTRACTS / "pilots")
    pilots = {
        f"mech.{side_a}.01": pilot_from_spec(registry.resolve(loadout_a)),
        f"mech.{side_b}.01": pilot_from_spec(registry.resolve(loadout_b)),
    }
    runner = MatchRunner(
        identity=MatchIdentity(
            match_id=match_id,
            correlation_id=identities.new_correlation_id(),
        ),
        seed=seed,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
        pilots=pilots,
        max_ticks=max_ticks,
        side_a=side_a,
        side_b=side_b,
        spawn_a=resolved_spawn_a,
        spawn_b=resolved_spawn_b,
    )
    return runner, runtime


__all__ = [
    "FixedClock",
    "SequentialIdentities",
    "TestRuntime",
    "match_runner",
    "runtime_dependencies",
]
