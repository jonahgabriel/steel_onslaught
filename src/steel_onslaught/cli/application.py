"""Typed CLI application capability ingress with no service locator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.llm.schemas import ProtocolSecretResolver
from steel_onslaught.match.composition import (
    AdaptationDependencies,
    LearningDependencies,
    LiveMatchStack,
    ManagedDuelExecutor,
    RuntimeDependencies,
    assemble_match_live,
    build_adaptation_dependencies,
    build_duel_executor,
    build_learning_dependencies,
    build_runtime_dependencies,
)


@dataclass(frozen=True)
class CliRuntimeCapabilities:
    secret_resolver: ProtocolSecretResolver | None


class CliApplicationFactory:
    """Capture explicit capabilities once for all CLI composition roots."""

    def __init__(self, capabilities: CliRuntimeCapabilities) -> None:
        self._capabilities = capabilities

    @classmethod
    def packaged(cls) -> CliApplicationFactory:
        """The packaged executable has no ambient secret authority."""
        return cls(CliRuntimeCapabilities(secret_resolver=None))

    def runtime(self, overlay: ModelSOApplicationOverlay) -> RuntimeDependencies:
        return build_runtime_dependencies(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
        )

    def match(
        self,
        *,
        overlay: ModelSOApplicationOverlay,
        red_loadout_path: Path,
        blue_loadout_path: Path,
        seed: int,
        max_ticks: int | None,
    ) -> LiveMatchStack:
        return assemble_match_live(
            overlay=overlay,
            red_loadout_path=red_loadout_path,
            blue_loadout_path=blue_loadout_path,
            seed=seed,
            max_ticks=max_ticks,
            secret_resolver=self._capabilities.secret_resolver,
        )

    def learning(self, overlay: ModelSOApplicationOverlay) -> LearningDependencies:
        return build_learning_dependencies(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
        )

    def duel(self, overlay: ModelSOApplicationOverlay) -> ManagedDuelExecutor:
        return build_duel_executor(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
        )

    def adaptation(self, overlay: ModelSOApplicationOverlay) -> AdaptationDependencies:
        return build_adaptation_dependencies(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
        )


__all__ = ["CliApplicationFactory", "CliRuntimeCapabilities"]
