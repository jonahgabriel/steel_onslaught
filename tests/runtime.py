"""Strict deterministic dependency factories for runtime-facing tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.composition import (
    load_match_contract_catalog,
    load_pilot_registry,
)
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.pilots.aggressive import AggressivePilot
from steel_onslaught.pilots.defensive import DefensivePilot
from steel_onslaught.pilots.predictive import PredictivePilot
from steel_onslaught.pilots.schemas import ModelSOPosition, PilotProtocol

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACTS = _REPO_ROOT / "contracts_data"
_NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def pilot_from_spec(spec: ModelSOPilotSpec) -> PilotProtocol:
    """Test-only deterministic pilot fixture; production construction stays at the root."""
    match spec.archetype:
        case "aggressive":
            return AggressivePilot(spec=spec)
        case "defensive":
            return DefensivePilot(spec=spec)
        case "predictive":
            return PredictivePilot(spec=spec)
    raise ValueError(f"unknown pilot archetype {spec.archetype!r} (spec id: {spec.id!r})")


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
    arena: ModelSOArenaSpec


def runtime_dependencies() -> TestRuntime:
    identities = SequentialIdentities()
    catalog = load_match_contract_catalog(_CONTRACTS)
    return TestRuntime(
        event_factory=EventFactory(clock=FixedClock(), identities=identities),
        catalog=catalog,
        arena=catalog.arenas["open_field"],
    )


def match_runner(
    *,
    bus: EventBus,
    match_id: str,
    seed: int,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    max_ticks: int | None,
    side_a: str = "a",
    side_b: str = "b",
    spawn_a: ModelSOPosition | None = None,
    spawn_b: ModelSOPosition | None = None,
    arena_override: ModelSOArenaSpec | None = None,
    pilots_override: Mapping[str, PilotProtocol] | None = None,
) -> tuple[MatchRunner, TestRuntime]:
    runtime = runtime_dependencies()
    if arena_override is not None and (spawn_a is not None or spawn_b is not None):
        raise ValueError("arena_override cannot be combined with spawn overrides")
    arena = arena_override or runtime.arena
    if spawn_a is not None or spawn_b is not None:
        arena = ModelSOArenaSpec(
            schema_version="0.1.0",
            kind="steel_onslaught.arena",
            arena_id="test_open_field",
            display_name="Injected test open field",
            size=40,
            spawn_a=spawn_a or arena.spawn_a,
            spawn_b=spawn_b or arena.spawn_b,
            obstacles=(),
            rects=(),
        )
    if runtime.arena != arena or runtime.catalog.arenas.get(arena.arena_id) != arena:
        runtime = TestRuntime(
            event_factory=runtime.event_factory,
            catalog=MatchContractCatalog(
                arenas={**runtime.catalog.arenas, arena.arena_id: arena},
                chassis=runtime.catalog.chassis,
                boilers=runtime.catalog.boilers,
                sensors=runtime.catalog.sensors,
                weapons=runtime.catalog.weapons,
                gizmos=runtime.catalog.gizmos,
                transitions=runtime.catalog.transitions,
            ),
            arena=arena,
        )
    identities = runtime.event_factory.identities
    if pilots_override is None:
        registry = load_pilot_registry(_CONTRACTS / "pilots")
        pilots = {
            f"mech.{side_a}.01": pilot_from_spec(registry.resolve(loadout_a)),
            f"mech.{side_b}.01": pilot_from_spec(registry.resolve(loadout_b)),
        }
    else:
        pilots = dict(pilots_override)
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
        arena=arena,
        pilots=pilots,
        max_ticks=max_ticks,
        side_a=side_a,
        side_b=side_b,
    )
    return runner, runtime


__all__ = [
    "FixedClock",
    "SequentialIdentities",
    "TestRuntime",
    "match_runner",
    "pilot_from_spec",
    "runtime_dependencies",
]
