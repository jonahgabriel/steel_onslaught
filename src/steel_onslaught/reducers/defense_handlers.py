"""Allowlisted resolution handlers for defense/damage-mitigation (armor seam).

Damage resolution was previously a single hardcoded call
(``compute_armor_reduction``) imported directly into ``match/runner.py``.
This module gives it the same discipline every other resolution seam in this
repo already has — ``cards/rules.py`` (card-programming rules) and
``cards/utility_handlers.py`` (utility deploy effects): a frozen,
content-addressed allowlist selected by handler id from a typed overlay
binding, with the active selection recorded into ``MATCH_STARTED`` for
replay/audit.

Each handler exposes ``handle(request) -> result``: a single typed request
in, a single typed result out — no envelope, no wrapper, no inline coercion.
This is deliberately the same minimal shape as every other pure resolution
step in the codebase; there is no runtime here to own dispatch, so the
registry itself is the entire "runtime" a handler needs.

``HandlerArmorV1`` is a pure adapter over ``reducers.damage
.compute_armor_reduction`` — the existing, independently unit-tested
degrading/capped-mitigation math is not reimplemented here, so this seam is
byte-identical to pre-refactor behavior by construction, not by convention.

Adding a new defense mechanic (shields, ablative plating, resistances) is a
new handler class + one id added to ``defense_handler_pack.handler_ids`` in
an overlay — no change to this module's registry/provenance machinery and no
change to the engine call site. This PR ships only the single ``armor``
handler; a multi-handler resolution pipeline (e.g. a shield layer resolved
before armor) is an explicit follow-up seam, not built here — see
``DefenseResolutionRegistry.active``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from steel_onslaught.contracts.weapon import WeaponDamageType
from steel_onslaught.reducers.damage import compute_armor_reduction

__all__ = [
    "DEFAULT_DEFENSE_HANDLER_IDS",
    "DefenseHandlerSelectionError",
    "DefenseResolutionHandlerProtocol",
    "DefenseResolutionRegistry",
    "HandlerArmorV1",
    "ModelSODefenseHandlerDescriptor",
    "ModelSODefenseHandlerPackProvenance",
    "ModelSODefenseResolutionRequest",
    "ModelSODefenseResolutionResult",
    "default_defense_registry",
]


class DefenseHandlerSelectionError(ValueError):
    """A defense handler id could not be resolved from the allowlist pack."""


class ModelSODefenseResolutionRequest(BaseModel):
    """Typed input to one defense-resolution handler's ``handle()``.

    Field-for-field this is exactly what ``compute_armor_reduction`` already
    consumes today (``match/runner.py``'s weapon-fire resolution): the raw
    pre-mitigation damage, the target's current mitigation pool, and the
    incoming weapon's damage type (heat/standard/pressure carry different
    mitigation caps).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    damage_raw: StrictInt = Field(ge=0)
    armor_value: StrictInt = Field(ge=0)
    weapon_damage_type: WeaponDamageType


class ModelSODefenseResolutionResult(BaseModel):
    """Typed output of one defense-resolution handler's ``handle()``.

    Field-for-field mirrors ``ArmorReduction`` (``reducers/damage.py``) so a
    handler result needs no translation at any existing call site:
    ``absorbed`` in ``[0, damage_raw]``, ``armor_after`` in
    ``[0, armor_value]``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    absorbed: StrictInt = Field(ge=0)
    armor_after: StrictInt = Field(ge=0)


class ModelSODefenseHandlerDescriptor(BaseModel):
    """Content-addressed, replay-visible identity for one handler."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    handler_id: StrictStr = Field(min_length=1)
    version: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)

    @property
    def implementation_sha256(self) -> str:
        """Deterministic digest over the handler identity (id + version)."""

        material = f"{self.handler_id}:{self.version}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ModelSODefenseHandlerPackProvenance(BaseModel):
    """Content-addressed, ledger-visible identity of a selected defense pack.

    Recorded on every ``MATCH_STARTED`` (see ``match/runner.py``) — unlike
    ``balance_rule_pack``/``utility_handler_pack``, which are opt-in and only
    recorded when an overlay activates them, defense resolution always runs
    (every hit goes through a mitigation handler), so its active pack is
    always named in the ledger, default or not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pack_id: StrictStr = Field(min_length=1)
    handlers: tuple[ModelSODefenseHandlerDescriptor, ...] = Field(min_length=1)
    content_sha256: StrictStr = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


def _pack_digest(pack_id: str, handlers: tuple[ModelSODefenseHandlerDescriptor, ...]) -> str:
    payload = {
        "pack_id": pack_id,
        "handlers": [{"handler_id": h.handler_id, "version": h.version} for h in handlers],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DefenseResolutionHandlerProtocol(Protocol):
    """One pure defense-resolution handler.

    ``handle`` is the minimal single-parameter dispatch shape used across
    this repo's compute seams: a typed request in, a typed result out, no
    wrapper, no coercion.
    """

    descriptor: ModelSODefenseHandlerDescriptor

    def handle(
        self, payload: ModelSODefenseResolutionRequest
    ) -> ModelSODefenseResolutionResult: ...


class HandlerArmorV1:
    """Canonical armor-absorption handler (degrading, capped-mitigation).

    Pure adapter: delegates the actual math to ``compute_armor_reduction``,
    which stays independently unit-tested in ``tests/reducers/test_damage
    .py``. This handler exists to give that math a stable, allowlisted
    identity a match contract can select and a ledger can record — not to
    re-derive it.
    """

    descriptor: ModelSODefenseHandlerDescriptor = ModelSODefenseHandlerDescriptor(
        handler_id="defense.armor.v1",
        version="1",
        description=(
            "Degrading, capped-mitigation armor absorption per weapon damage "
            "type (heat 50% / standard 75% / pressure 90% max absorption)."
        ),
    )

    def handle(self, payload: ModelSODefenseResolutionRequest) -> ModelSODefenseResolutionResult:
        reduction = compute_armor_reduction(
            damage_raw=payload.damage_raw,
            armor_value=payload.armor_value,
            weapon_damage_type=payload.weapon_damage_type,
        )
        return ModelSODefenseResolutionResult(
            absorbed=reduction.absorbed,
            armor_after=reduction.armor_after,
        )


@dataclass(frozen=True, slots=True)
class DefenseResolutionRegistry:
    """Immutable, fail-closed allowlist of defense-resolution handlers."""

    pack_id: str
    handlers: tuple[DefenseResolutionHandlerProtocol, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.pack_id, str) or not self.pack_id:
            raise DefenseHandlerSelectionError("defense pack id must be a non-empty string")
        ids = [handler.descriptor.handler_id for handler in self.handlers]
        if len(ids) != len(set(ids)):
            raise DefenseHandlerSelectionError(
                f"duplicate defense handler ids in pack {self.pack_id!r}"
            )

    @property
    def _by_id(self) -> Mapping[str, DefenseResolutionHandlerProtocol]:
        return MappingProxyType(
            {handler.descriptor.handler_id: handler for handler in self.handlers}
        )

    def select(self, handler_ids: Sequence[str]) -> DefenseResolutionRegistry:
        """Return a sub-registry of the named handlers, failing closed."""

        if not handler_ids:
            raise DefenseHandlerSelectionError(
                f"defense handler selection for pack {self.pack_id!r} must be non-empty"
            )
        if len(handler_ids) != len(set(handler_ids)):
            raise DefenseHandlerSelectionError(
                f"duplicate defense handler ids selected from pack {self.pack_id!r}"
            )
        by_id = self._by_id
        selected: list[DefenseResolutionHandlerProtocol] = []
        for handler_id in handler_ids:
            handler = by_id.get(handler_id)
            if handler is None:
                raise DefenseHandlerSelectionError(
                    f"defense handler {handler_id!r} is not registered in pack {self.pack_id!r}"
                )
            selected.append(handler)
        return DefenseResolutionRegistry(pack_id=self.pack_id, handlers=tuple(selected))

    @property
    def active(self) -> DefenseResolutionHandlerProtocol:
        """The single handler resolving this seam's one mitigation slot today.

        This PR wires exactly one active handler per match (today always
        ``defense.armor.v1``). A future multi-handler mitigation pipeline
        (e.g. a shield layer resolved before armor) needs its own composition
        seam at the ``match/runner.py`` call site — this property fails
        closed rather than silently picking a handler when more than one is
        selected, so that follow-up work is forced to be explicit.
        """

        if len(self.handlers) != 1:
            raise DefenseHandlerSelectionError(
                f"defense pack {self.pack_id!r} must resolve to exactly one active "
                f"handler; got {len(self.handlers)} — a multi-handler mitigation "
                "pipeline is not implemented"
            )
        return self.handlers[0]

    def provenance(self) -> ModelSODefenseHandlerPackProvenance:
        descriptors = tuple(handler.descriptor for handler in self.handlers)
        return ModelSODefenseHandlerPackProvenance(
            pack_id=self.pack_id,
            handlers=descriptors,
            content_sha256=_pack_digest(self.pack_id, descriptors),
        )


_DEFAULT_PACK_ID = "defense.resolution.v1"


def default_defense_registry() -> DefenseResolutionRegistry:
    """The canonical pack: the single byte-identical-to-today armor handler."""

    return DefenseResolutionRegistry(pack_id=_DEFAULT_PACK_ID, handlers=(HandlerArmorV1(),))


DEFAULT_DEFENSE_HANDLER_IDS: tuple[str, ...] = (HandlerArmorV1.descriptor.handler_id,)
