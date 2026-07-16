"""Deterministic duel application service over injected runtime dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import ModelSOEventEnvelope
from steel_onslaught.llm.schemas import ModelSOLlmPilotSelection
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.pilots.schemas import PilotProtocol

if TYPE_CHECKING:
    from steel_onslaught.match.composition import RuntimeDependencies


@dataclass(frozen=True)
class DuelResult:
    """Final state plus the canonical evidence emitted by one duel."""

    final_state: ModelSOMatchState
    events: tuple[ModelSOEventEnvelope, ...]


class ModelSOEvaluationStorageKey(BaseModel):
    """Validated logical key resolved by the composition root, never a raw path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    duel: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")


class DuelExecutor(Protocol):
    """Outer-root capability supplied to learning and balance workflows."""

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
    ) -> DuelResult: ...


class PilotDuelExecutor(Protocol):
    """Evidence-backed duel capability for workflows supplying built pilots."""

    def __call__(
        self,
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
    ) -> DuelResult: ...


def run_duel(
    *,
    dependencies: RuntimeDependencies,
    identity: MatchIdentity,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    seed: int,
    max_ticks: int,
    loadout_path_a: Path | None,
    loadout_path_b: Path | None,
    side_a: str,
    side_b: str,
) -> DuelResult:
    """Run one duel without constructing adapters, identities, or contracts."""
    from steel_onslaught.match.composition import assemble_match_with_dependencies

    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=loadout_a,
        blue=loadout_b,
        seed=seed,
        max_ticks=max_ticks,
        identity=identity,
        red_loadout_path=loadout_path_a,
        blue_loadout_path=loadout_path_b,
        side_a=side_a,
        side_b=side_b,
    )
    final = stack.runner.run()
    events: Sequence[ModelSOEventEnvelope] = tuple(dependencies.ledger.read_all(identity.match_id))
    return DuelResult(final_state=final, events=tuple(events))


def run_pilot_duel(
    *,
    dependencies: RuntimeDependencies,
    identity: MatchIdentity,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    pilot_a: PilotProtocol,
    pilot_b: PilotProtocol,
    seed: int,
    max_ticks: int,
    side_a: str,
    side_b: str,
) -> DuelResult:
    """Run a duel with factory-built pilots over canonical runtime evidence."""
    from steel_onslaught.match.composition import assemble_match_with_dependencies

    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=loadout_a,
        blue=loadout_b,
        seed=seed,
        max_ticks=max_ticks,
        identity=identity,
        side_a=side_a,
        side_b=side_b,
        pilots_override={
            f"mech.{side_a}.01": pilot_a,
            f"mech.{side_b}.01": pilot_b,
        },
    )
    final = stack.runner.run()
    events: Sequence[ModelSOEventEnvelope] = tuple(dependencies.ledger.read_all(identity.match_id))
    return DuelResult(final_state=final, events=tuple(events))


__all__ = [
    "DuelExecutor",
    "DuelResult",
    "ModelSOEvaluationStorageKey",
    "PilotDuelExecutor",
    "run_duel",
    "run_pilot_duel",
]
