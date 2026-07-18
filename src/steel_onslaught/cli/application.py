"""Typed CLI application capability ingress with no service locator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.llm.schemas import (
    ProtocolHttpTransport,
    ProtocolSecretResolver,
    ProtocolSleeper,
)
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
    build_selected_runtime_dependencies,
)


@dataclass(frozen=True)
class CliRuntimeCapabilities:
    secret_resolver: ProtocolSecretResolver | None
    http_transport: ProtocolHttpTransport | None = None
    sleeper: ProtocolSleeper | None = None


class CliApplicationFactory:
    """Capture explicit capabilities once for all CLI composition roots."""

    def __init__(self, capabilities: CliRuntimeCapabilities) -> None:
        self._capabilities = capabilities

    @classmethod
    def packaged(cls) -> CliApplicationFactory:
        """The packaged executable has no ambient secret authority."""
        return cls(CliRuntimeCapabilities(secret_resolver=None))

    @classmethod
    def live(
        cls,
        *,
        secret_resolver: ProtocolSecretResolver,
        http_transport: ProtocolHttpTransport,
        sleeper: ProtocolSleeper | None = None,
    ) -> CliApplicationFactory:
        """Build an explicitly injected live-provider CLI capability graph.

        The packaged CLI intentionally has no credential or transport
        authority.  Callers that want a real provider must supply both ports
        at this boundary; no environment, endpoint, or key discovery is
        performed by the CLI.
        """

        return cls(
            CliRuntimeCapabilities(
                secret_resolver=secret_resolver,
                http_transport=http_transport,
                sleeper=sleeper,
            )
        )

    @property
    def live_enabled(self) -> bool:
        """Whether this factory carries the complete injected live graph."""

        return (
            self._capabilities.secret_resolver is not None
            and self._capabilities.http_transport is not None
        )

    def runtime(self, overlay: ModelSOApplicationOverlay) -> RuntimeDependencies:
        return build_runtime_dependencies(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
            http_transport=self._capabilities.http_transport,
            sleeper=self._capabilities.sleeper,
        )

    def selected_runtime(
        self,
        overlay: ModelSOApplicationOverlay,
        provider_selection: str | tuple[str, ...],
        pilot_spec_ids: tuple[str, ...],
    ) -> RuntimeDependencies:
        """Compose exactly the selected provider and pilot lanes for one launch."""

        if not self.live_enabled:
            raise ValueError("live CLI composition requires injected secret and HTTP capabilities")
        if isinstance(provider_selection, tuple):
            return build_selected_runtime_dependencies(
                overlay,
                selected_provider_ids=provider_selection,
                selected_pilot_spec_ids=pilot_spec_ids,
                secret_resolver=self._capabilities.secret_resolver,
                http_transport=self._capabilities.http_transport,
                sleeper=self._capabilities.sleeper,
            )
        return build_selected_runtime_dependencies(
            overlay,
            selected_provider_id=provider_selection,
            selected_pilot_spec_ids=pilot_spec_ids,
            secret_resolver=self._capabilities.secret_resolver,
            http_transport=self._capabilities.http_transport,
            sleeper=self._capabilities.sleeper,
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
            http_transport=self._capabilities.http_transport,
            sleeper=self._capabilities.sleeper,
        )

    def learning(self, overlay: ModelSOApplicationOverlay) -> LearningDependencies:
        return build_learning_dependencies(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
            http_transport=self._capabilities.http_transport,
            sleeper=self._capabilities.sleeper,
        )

    def duel(self, overlay: ModelSOApplicationOverlay) -> ManagedDuelExecutor:
        return build_duel_executor(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
            http_transport=self._capabilities.http_transport,
            sleeper=self._capabilities.sleeper,
        )

    def adaptation(self, overlay: ModelSOApplicationOverlay) -> AdaptationDependencies:
        return build_adaptation_dependencies(
            overlay,
            secret_resolver=self._capabilities.secret_resolver,
            http_transport=self._capabilities.http_transport,
            sleeper=self._capabilities.sleeper,
        )


__all__ = ["CliApplicationFactory", "CliRuntimeCapabilities"]
