"""Allowlisted resolution handlers for utility cards (Phase 2).

The repo operating rule requires that resolution effects be **allowlisted
handlers selected by a typed overlay**, with handler ids content-addressed and
visible in replay — the same discipline as ``CardProgrammingRuleRegistry`` at
the programming phase.  This is the first *resolution-phase* registry of that
shape: a frozen allowlist keyed by ``utility_kind`` whose ``select`` authority
fails closed on unknown / duplicate / empty ids.

Each handler is pure: it validates the resolved card's parameters and returns
the closed ``ModelSOUtilityDeployedPayload`` the runner publishes.  No handler
touches a balance knob (damage/evasion/range) — U-GATE requires "no balance
knob touched"; the effect is expressed only through LOS/lock/targeting consults
in the weapon-fire resolver.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from steel_onslaught.contracts.card import SOUtilityKind
from steel_onslaught.events.payloads import ModelSOUtilityDeployedPayload
from steel_onslaught.pilots.schemas import ModelSOPosition


class UtilityHandlerSelectionError(ValueError):
    """A utility handler id could not be resolved from the allowlist pack."""


class ModelSOUtilityHandlerDescriptor(BaseModel):
    """Content-addressed, replay-visible descriptor for one handler."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    handler_id: StrictStr = Field(min_length=1)
    utility_kind: SOUtilityKind
    version: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)

    @property
    def implementation_sha256(self) -> str:
        """Deterministic digest over the handler identity (FQCN + version)."""

        material = f"{self.handler_id}:{self.utility_kind}:{self.version}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class UtilityResolutionHandler:
    """One pure resolution handler that builds a UTILITY_DEPLOYED payload."""

    descriptor: ModelSOUtilityHandlerDescriptor

    def deploy(
        self,
        *,
        card_id: str,
        radius: int,
        duration_ticks: int,
        origin: ModelSOPosition,
    ) -> ModelSOUtilityDeployedPayload:
        """Return the closed deployed-effect payload for this handler's kind."""

        return ModelSOUtilityDeployedPayload(
            card_id=card_id,
            utility_kind=self.descriptor.utility_kind,
            origin=origin,
            radius=radius,
            duration_ticks=duration_ticks,
        )


class ModelSOUtilityHandlerPackProvenance(BaseModel):
    """Replay-visible provenance for a selected utility handler pack."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pack_id: StrictStr = Field(min_length=1)
    handlers: tuple[ModelSOUtilityHandlerDescriptor, ...] = Field(min_length=1)

    @property
    def content_sha256(self) -> str:
        material = ";".join(f"{d.handler_id}:{d.implementation_sha256}" for d in self.handlers)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class UtilityResolutionRegistry:
    """Immutable, fail-closed allowlist of utility resolution handlers."""

    pack_id: str
    handlers: tuple[UtilityResolutionHandler, ...]

    def __post_init__(self) -> None:
        ids = [handler.descriptor.handler_id for handler in self.handlers]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate utility handler ids in pack {self.pack_id!r}")
        kinds = [handler.descriptor.utility_kind for handler in self.handlers]
        if len(kinds) != len(set(kinds)):
            raise ValueError(f"duplicate utility handler kinds in pack {self.pack_id!r}")

    @property
    def _by_id(self) -> Mapping[str, UtilityResolutionHandler]:
        return MappingProxyType(
            {handler.descriptor.handler_id: handler for handler in self.handlers}
        )

    @property
    def _by_kind(self) -> Mapping[SOUtilityKind, UtilityResolutionHandler]:
        return MappingProxyType(
            {handler.descriptor.utility_kind: handler for handler in self.handlers}
        )

    def select(self, handler_ids: Sequence[str]) -> UtilityResolutionRegistry:
        """Return a sub-registry of the named handlers, failing closed."""

        if not handler_ids:
            raise UtilityHandlerSelectionError(
                f"utility handler selection for pack {self.pack_id!r} must be non-empty"
            )
        if len(handler_ids) != len(set(handler_ids)):
            raise UtilityHandlerSelectionError(
                f"duplicate utility handler ids selected from pack {self.pack_id!r}"
            )
        by_id = self._by_id
        selected: list[UtilityResolutionHandler] = []
        for handler_id in handler_ids:
            handler = by_id.get(handler_id)
            if handler is None:
                raise UtilityHandlerSelectionError(
                    f"utility handler {handler_id!r} is not registered in pack {self.pack_id!r}"
                )
            selected.append(handler)
        return UtilityResolutionRegistry(pack_id=self.pack_id, handlers=tuple(selected))

    def for_kind(self, utility_kind: SOUtilityKind) -> UtilityResolutionHandler:
        """Resolve one handler by kind or fail closed (unselected kind)."""

        handler = self._by_kind.get(utility_kind)
        if handler is None:
            raise UtilityHandlerSelectionError(
                f"no selected utility handler for kind {utility_kind!r} in pack {self.pack_id!r}"
            )
        return handler

    def provenance(self) -> ModelSOUtilityHandlerPackProvenance:
        return ModelSOUtilityHandlerPackProvenance(
            pack_id=self.pack_id,
            handlers=tuple(handler.descriptor for handler in self.handlers),
        )


_DEFAULT_PACK_ID = "utility.resolution.v1"

_DEFAULT_DESCRIPTORS: tuple[ModelSOUtilityHandlerDescriptor, ...] = (
    ModelSOUtilityHandlerDescriptor(
        handler_id="utility.smoke.v1",
        utility_kind="smoke",
        version="1",
        description="LOS-blocking smoke cloud over an area for a duration.",
    ),
    ModelSOUtilityHandlerDescriptor(
        handler_id="utility.chaff.v1",
        utility_kind="chaff",
        version="1",
        description="Targeting-debuff aura on the deploying mech.",
    ),
    ModelSOUtilityHandlerDescriptor(
        handler_id="utility.flares.v1",
        utility_kind="flares",
        version="1",
        description="Decoy that spoils a sensor lock for a duration.",
    ),
)


def default_utility_registry() -> UtilityResolutionRegistry:
    """The canonical pack of all three counterplay handlers."""

    return UtilityResolutionRegistry(
        pack_id=_DEFAULT_PACK_ID,
        handlers=tuple(
            UtilityResolutionHandler(descriptor=descriptor) for descriptor in _DEFAULT_DESCRIPTORS
        ),
    )


DEFAULT_UTILITY_HANDLER_IDS: tuple[str, ...] = tuple(
    descriptor.handler_id for descriptor in _DEFAULT_DESCRIPTORS
)


__all__ = [
    "DEFAULT_UTILITY_HANDLER_IDS",
    "ModelSOUtilityHandlerDescriptor",
    "ModelSOUtilityHandlerPackProvenance",
    "UtilityHandlerSelectionError",
    "UtilityResolutionHandler",
    "UtilityResolutionRegistry",
    "default_utility_registry",
]
