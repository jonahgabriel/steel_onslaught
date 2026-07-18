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
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.contracts.card import CardId, ModelSOCard
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.schemas import ModelSOPilotObservation

_RegisterIndex = Annotated[StrictInt, Field(ge=0)]


class ProgrammingPilotError(ValueError):
    """A whole-round programmer did not satisfy the typed programming boundary."""


class _ClosedProgrammingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


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

    @model_validator(mode="after")
    def _validate_hand_and_registers(self) -> ModelSOProgrammingObservation:
        try:
            deck = self.card_runtime_snapshot.selected_deck
        except ValueError as exc:
            raise ValueError(
                "programming observation requires a card runtime snapshot with "
                "an explicitly selected deck"
            ) from exc

        indices = self.free_indices
        if indices != tuple(sorted(indices)):
            raise ValueError("free_indices must be in ascending canonical order")
        if len(indices) != len(set(indices)):
            raise ValueError("free_indices must be unique")
        if any(index >= deck.register_count for index in indices):
            raise ValueError(
                f"free_indices must be below deck register_count {deck.register_count}"
            )
        if len(indices) > len(self.hand):
            raise ValueError(
                f"hand contains {len(self.hand)} cards but {len(indices)} free registers "
                "must be programmed"
            )

        deck_counts = Counter(str(card_id) for card_id in deck.card_multiset())
        hand_counts = Counter(str(card_id) for card_id in self.hand)
        missing = hand_counts - deck_counts
        if missing:
            raise ValueError(
                f"hand contains card ids not available in selected deck: {sorted(missing)}"
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
    """Build a deterministic priority/id plan without consulting a pilot."""

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
    )


def program_for_seat(
    programmer: ProgrammingPilot | None,
    observation: ModelSOProgrammingObservation,
) -> ModelSOPlanCommittedPayload:
    """Return one strictly validated deterministic whole-round plan.

    With ``programmer=None`` the adapter selects cards by descending authored
    priority and ascending card id.  An explicit whole-round programmer may
    supply a different plan, but its output is validated against the same
    snapshot/hand/register boundary.  Decide-only pilots are rejected rather
    than called, preserving the no-LLM/no-network property of this seam.
    """

    if programmer is None:
        return _validate_plan(_priority_plan(observation), observation)
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
    return _validate_plan(program_method(observation), observation)


__all__ = [
    "ModelSOProgrammingObservation",
    "ProgrammingPilot",
    "ProgrammingPilotError",
    "program_for_seat",
]
