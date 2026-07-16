"""Exact loadout pilot-id resolution over an injected, validated registry."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec


class PilotResolutionError(ValueError):
    """A loadout's pilot could not be resolved to a valid pilot spec."""


class PilotSpecRegistry:
    """Index of shipped pilot specs, keyed by spec ``id``."""

    def __init__(self, specs: dict[str, ModelSOPilotSpec]) -> None:
        self._specs = dict(specs)

    def get(self, spec_id: str) -> ModelSOPilotSpec | None:
        """Return the registered spec for *spec_id*, or None."""
        return self._specs.get(spec_id)

    def as_mapping(self) -> Mapping[str, ModelSOPilotSpec]:
        return MappingProxyType(self._specs)

    def resolve(self, loadout: ModelSOLoadout) -> ModelSOPilotSpec:
        """Resolve an exact pilot id; paths and archetype guesses are forbidden."""
        if loadout.pilot_spec_path is not None:
            raise PilotResolutionError(
                "pilot_spec_path is an ingress concern; inject its validated spec into "
                f"the registry before resolving loadout {loadout.id!r}"
            )
        registered = self._specs.get(loadout.pilot_id)
        if registered is not None:
            return registered
        raise PilotResolutionError(f"unknown exact pilot_id {loadout.pilot_id!r}")
