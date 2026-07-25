"""Pure programmed-register pilot boundary.

This module is deliberately separate from the ordinary per-tick pilot
observation.  A programming observation carries the immutable card/deck
snapshot and the dealt hand needed to build one round plan.  It has no
filesystem, event-bus, runner, or provider authority.

``program_for_seat`` accepts an explicit whole-round programmer when one is
provided.  If no programmer is supplied it uses a deterministic priority
ordering over the dealt hand.  A decide-only pilot is never called as an
implicit fallback: doing that could turn this pure seam into an unexpected
LLM/network call.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.contracts.card import CardId, ModelSOCard
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.contracts.incentive import ModelSOUtilityIncentive
from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SOPlanSource,
)
from steel_onslaught.pilots.schemas import ModelSOPilotObservation
from steel_onslaught.pilots.spatial_view import (
    ModelSOMovementPreview,
    ModelSOSpatialGridView,
    ModelSOWeaponRangeFlag,
)

_RegisterIndex = Annotated[StrictInt, Field(ge=0)]


class ProgrammingPilotError(ValueError):
    """A whole-round programmer did not satisfy the typed programming boundary."""


class _ClosedProgrammingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOCardRuleHandlerMetadata(_ClosedProgrammingModel):
    """Stable identity for one injected card-programming rule.

    Rule implementations are application plugins, but their identity is part
    of the match contract.  Requiring an explicit version and implementation
    digest makes an experiment replayable without giving a plugin filesystem
    or event-bus authority.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.card_rule_handler"] = "steel_onslaught.card_rule_handler"
    handler_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    version: StrictStr = Field(
        min_length=5,
        max_length=32,
        pattern=r"^v[0-9]+\.[0-9]+\.[0-9]+$",
    )
    implementation_sha256: StrictStr = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ModelSOCardRuleHandlerDescriptor(_ClosedProgrammingModel):
    """Human-facing description of one installed rule plugin.

    Identity (``metadata``) is what a match records and what replay compares;
    the prose fields exist so an operator can *discover* what is installable
    without reading the implementation.  They are deliberately kept out of the
    provenance model so editing a description can never invalidate an existing
    ledger.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.card_rule_descriptor"] = "steel_onslaught.card_rule_descriptor"
    metadata: ModelSOCardRuleHandlerMetadata
    display_name: StrictStr = Field(min_length=1, max_length=96)
    description: StrictStr = Field(min_length=1, max_length=512)

    @property
    def handler_id(self) -> str:
        """Return the identity id this descriptor documents."""

        return self.metadata.handler_id


class ModelSOCardRuleCatalogProjection(_ClosedProgrammingModel):
    """Enumerable, selectable installed-rule catalog for one pack.

    ``enabled_handler_ids`` is the ordered selection an overlay declared, so a
    single projection answers both "what can I turn on" and "what is on".
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.card_rule_catalog"] = "steel_onslaught.card_rule_catalog"
    pack_id: StrictStr = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_.-]*$")
    available: tuple[ModelSOCardRuleHandlerDescriptor, ...] = ()
    enabled_handler_ids: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def _enabled_ids_are_available(self) -> ModelSOCardRuleCatalogProjection:
        available_ids = [descriptor.handler_id for descriptor in self.available]
        if len(available_ids) != len(set(available_ids)):
            raise ValueError("rule catalog must not list a handler id twice")
        unknown = sorted(set(self.enabled_handler_ids) - set(available_ids))
        if unknown:
            raise ValueError(f"rule catalog enables unavailable handler ids: {unknown}")
        if len(self.enabled_handler_ids) != len(set(self.enabled_handler_ids)):
            raise ValueError("rule catalog enabled_handler_ids must be unique")
        return self


class ModelSOCardRulePackProvenance(_ClosedProgrammingModel):
    """Content-addressed identity for the selected ordered rule pack."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.card_rule_pack"] = "steel_onslaught.card_rule_pack"
    pack_id: StrictStr = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_.-]*$")
    handlers: tuple[ModelSOCardRuleHandlerMetadata, ...] = ()
    content_sha256: StrictStr = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ModelSOProgrammingObservation(_ClosedProgrammingModel):
    """Immutable card-aware view for one seat's plan phase.

    ``ModelSOPilotObservation`` intentionally contains no hand.  This wrapper
    keeps the card view explicit and requires a snapshot with an explicitly
    selected deck; passive card content cannot accidentally become gameplay.
    ``hand`` stores card ids and resolves definitions through the same snapshot
    used by live and replay composition.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.programming_observation"] = (
        "steel_onslaught.programming_observation"
    )
    pilot_observation: ModelSOPilotObservation
    card_runtime_snapshot: ModelSOCardRuntimeSnapshot
    seat: StrictStr = Field(min_length=1)
    hand: tuple[CardId, ...] = Field(default=())
    free_indices: tuple[_RegisterIndex, ...] = Field(default=())
    register_count: StrictInt | None = Field(default=None, ge=1)
    hand_deck_ids: tuple[StrictStr, ...] = ()
    # Show-dont-tell spatial representation arms R1/R2 (2026-07-24).  Populated
    # ONLY when the seat's ``ModelSOLlmPilotParams.spatial_representation``
    # opts in ("grid"/"grid_scaffold"); every other seat's observation stays
    # byte-identical (``None``/``()``/``False``) to the pre-arm shape.  Values
    # are computed by ``match.spatial_preview`` from the SAME resolver/LOS
    # functions the live match uses -- never a strategy hint, only rendered
    # ground-truth facts a pilot with eyes would already have.
    spatial_grid: ModelSOSpatialGridView | None = Field(default=None)
    movement_previews: tuple[ModelSOMovementPreview, ...] = Field(default=())
    weapon_range_flags: tuple[ModelSOWeaponRangeFlag, ...] = Field(default=())
    # R2 only: the wire contract requires one spatial-read sentence before
    # register selection.  Deliberately NOT enforced by a pydantic validator
    # anywhere in this module -- a scaffold field must never become an abort
    # source (see ``llm.programming._parse_response``, which logs and
    # continues when a provider omits it rather than raising).
    spatial_read_required: bool = Field(default=False)
    # Structural in-register utility incentive (SO-UTIL-MECH).  Present ONLY
    # when the match's overlay bound one; ``None`` (the default) leaves the
    # serialized programming prompt byte-identical to the pre-incentive shape
    # -- the incentive keys are simply absent.  This is a GAME-STATE value,
    # not guidance: ``llm.programming`` renders it as numeric card/state
    # fields and adds no instruction text anywhere, which is precisely the
    # contrast this experiment draws against the L-GATE-2 prompt-steering
    # null.
    utility_incentive: ModelSOUtilityIncentive | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_hand_and_registers(self) -> ModelSOProgrammingObservation:
        # Split-deck observations carry both authoritative partition deck ids
        # and a seat-specific register count.  Some composition overlays also
        # retain a selected single-deck id for legacy/replay provenance, so
        # checking ``selected_deck`` first incorrectly rejects the valid
        # split tuple before the provider is ever called.  Treat an explicit
        # multi-deck tuple as the split boundary in either snapshot shape and
        # validate the hand against the union of those named decks.
        split_deck_ids = tuple(self.hand_deck_ids)
        if len(split_deck_ids) > 1:
            if self.register_count is None:
                raise ValueError("split programming observation requires register_count")
            deck_counts: Counter[str] = Counter()
            for deck_id in split_deck_ids:
                deck = self.card_runtime_snapshot.require_deck(str(deck_id))
                deck_counts.update(str(card_id) for card_id in deck.card_multiset())
            register_count = self.register_count
            for card_id in self.hand:
                self.card_runtime_snapshot.card_catalog.require(card_id)
        else:
            try:
                deck = self.card_runtime_snapshot.selected_deck
            except ValueError as exc:
                if self.register_count is None or not split_deck_ids:
                    raise ValueError(
                        "programming observation requires an explicitly selected deck or "
                        "explicit split register/deck inputs"
                    ) from exc
                register_count = self.register_count
                for card_id in self.hand:
                    self.card_runtime_snapshot.card_catalog.require(card_id)
            else:
                register_count = deck.register_count
                if self.register_count is not None and self.register_count != register_count:
                    raise ValueError("register_count differs from selected deck")
                if split_deck_ids and split_deck_ids != (str(deck.id),):
                    raise ValueError("hand_deck_ids differs from selected deck")

        indices = self.free_indices
        if indices != tuple(sorted(indices)):
            raise ValueError("free_indices must be in ascending canonical order")
        if len(indices) != len(set(indices)):
            raise ValueError("free_indices must be unique")
        if any(index >= register_count for index in indices):
            raise ValueError(f"free_indices must be below deck register_count {register_count}")
        if len(indices) > len(self.hand):
            raise ValueError(
                f"hand contains {len(self.hand)} cards but {len(indices)} free registers "
                "must be programmed"
            )

        if self.card_runtime_snapshot.selected_deck_id is not None and len(split_deck_ids) <= 1:
            deck_counts = Counter(str(card_id) for card_id in deck.card_multiset())
            hand_counts = Counter(str(card_id) for card_id in self.hand)
            missing = hand_counts - deck_counts
            if missing:
                raise ValueError(
                    f"hand contains card ids not available in selected deck: {sorted(missing)}"
                )
        elif len(split_deck_ids) > 1:
            hand_counts = Counter(str(card_id) for card_id in self.hand)
            missing = hand_counts - deck_counts
            if missing:
                raise ValueError(
                    f"hand contains card ids not available in split decks: {sorted(missing)}"
                )
        return self

    @property
    def deck(self) -> ModelSODeck:
        """Return the explicitly selected immutable deck."""

        return self.card_runtime_snapshot.selected_deck

    @property
    def hand_cards(self) -> tuple[ModelSOCard, ...]:
        """Resolve the dealt hand through the shared card catalog snapshot."""

        return tuple(
            self.card_runtime_snapshot.card_catalog.require(card_id) for card_id in self.hand
        )


@runtime_checkable
class ProgrammingPilot(Protocol):
    """Optional whole-round programming capability.

    Implementations are injected by a later runtime slice.  This protocol is
    intentionally not implemented by ordinary ``PilotProtocol`` decide-only
    pilots, so this module cannot silently invoke an LLM or another provider.
    """

    def program(
        self, observation: ModelSOProgrammingObservation
    ) -> ModelSOPlanCommittedPayload: ...


@runtime_checkable
class CardProgrammingRuleHandler(Protocol):
    """Pure post-programming rule plugin.

    A handler can adjust a proposed whole-round plan, but it cannot observe or
    mutate runner state.  ``program_for_seat`` validates every handler result
    against the same hand/register snapshot before passing it onward.
    """

    metadata: ModelSOCardRuleHandlerMetadata

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload: ...


def _validate_plan(
    plan: ModelSOPlanCommittedPayload,
    observation: ModelSOProgrammingObservation,
) -> ModelSOPlanCommittedPayload:
    """Validate one programmer result against the immutable observation."""

    if not isinstance(plan, ModelSOPlanCommittedPayload):
        raise TypeError("programmer must return ModelSOPlanCommittedPayload")
    if plan.seat != observation.seat:
        raise ProgrammingPilotError(
            f"program seat {plan.seat!r} does not match observation seat {observation.seat!r}"
        )

    actual_indices = tuple(register.register_index for register in plan.registers)
    if actual_indices != observation.free_indices:
        raise ProgrammingPilotError(
            "program must contain exactly the observation free_indices in canonical order"
        )

    hand_counts = Counter(str(card_id) for card_id in observation.hand)
    chosen_counts = Counter(str(register.card_id) for register in plan.registers)
    missing = chosen_counts - hand_counts
    if missing:
        raise ProgrammingPilotError(
            f"program uses cards not present in the dealt hand: {sorted(missing)}"
        )
    return plan


def _priority_plan(observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
    """Build a deterministic priority/id plan without consulting a pilot.

    This seam has no bound programmer at all, so nothing was substituted: it
    is the by-design planner for human seats, deterministic pilots, and
    hermetic/replay matches.  It is therefore stamped
    ``DETERMINISTIC_PLANNER``.  Only ``LLMProgrammingPilot`` — the one caller
    that *did* have a provider and lost it — restamps the result as
    ``DETERMINISTIC_FALLBACK``.
    """

    ordered = sorted(observation.hand_cards, key=lambda card: (-card.priority, str(card.id)))
    selected = ordered[: len(observation.free_indices)]
    registers = tuple(
        ModelSOPlanRegister(register_index=index, card_id=card.id)
        for index, card in zip(observation.free_indices, selected, strict=True)
    )
    return ModelSOPlanCommittedPayload(
        seat=observation.seat,
        registers=registers,
        rationale=None,
        confidence=1.0,
        plan_source=SOPlanSource.DETERMINISTIC_PLANNER,
    )


def program_for_seat(
    programmer: ProgrammingPilot | None,
    observation: ModelSOProgrammingObservation,
    *,
    rule_handlers: Sequence[CardProgrammingRuleHandler] = (),
) -> ModelSOPlanCommittedPayload:
    """Return one strictly validated deterministic whole-round plan.

    With ``programmer=None`` the adapter selects cards by descending authored
    priority and ascending card id.  An explicit whole-round programmer may
    supply a different plan, but its output is validated against the same
    snapshot/hand/register boundary.  Decide-only pilots are rejected rather
    than called, preserving the no-LLM/no-network property of this seam.
    """

    if programmer is None:
        plan = _validate_plan(_priority_plan(observation), observation)
    else:
        if not isinstance(programmer, ProgrammingPilot):
            if hasattr(programmer, "program"):
                raise ProgrammingPilotError("ProgrammingPilot.program must be callable")
            raise ProgrammingPilotError(
                "program_for_seat requires an explicit ProgrammingPilot; decide-only pilots "
                "cannot be used as an implicit LLM fallback"
            )
        program_method = programmer.program
        if not callable(program_method):
            raise ProgrammingPilotError("ProgrammingPilot.program must be callable")
        plan = _validate_plan(program_method(observation), observation)
    for handler in rule_handlers:
        if not isinstance(handler, CardProgrammingRuleHandler):
            raise ProgrammingPilotError(
                "card programming rule handlers must expose metadata and callable apply"
            )
        if not isinstance(handler.metadata, ModelSOCardRuleHandlerMetadata):
            raise ProgrammingPilotError(
                "card programming rule handler metadata must be the typed handler contract"
            )
        try:
            plan = _validate_plan(handler.apply(observation, plan), observation)
        except ProgrammingPilotError:
            raise
        except (TypeError, ValueError) as exc:
            raise ProgrammingPilotError(
                f"card programming rule handler {handler.metadata.handler_id!r} failed"
            ) from exc
    return plan


__all__ = [
    "CardProgrammingRuleHandler",
    "ModelSOCardRuleCatalogProjection",
    "ModelSOCardRuleHandlerDescriptor",
    "ModelSOCardRuleHandlerMetadata",
    "ModelSOCardRulePackProvenance",
    "ModelSOProgrammingObservation",
    "ProgrammingPilot",
    "ProgrammingPilotError",
    "program_for_seat",
]
