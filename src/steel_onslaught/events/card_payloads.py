"""Closed payload contracts for the card-program lifecycle events.

The models define the wire protocol only.  No dealer, reducer, runner, or
frontend behavior is activated by this module; those consumers are separate
follow-up slices.  Card ids reuse the canonical :class:`CardId` contract so a
card event cannot introduce an untyped identifier vocabulary.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from steel_onslaught.contracts.card import CardId


class _ClosedCardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SORegisterOutcome(StrEnum):
    """The canonical terminal outcome for one register resolution."""

    RESOLVED = "resolved"
    AUTO_REMAIN = "auto_remain"
    HEAT_LOCKED = "heat_locked"


class SORegisterFillReason(StrEnum):
    """Why a register was filled without a card."""

    SHORT_DECK = "short_deck"


class ModelSOHandDealtPayload(_ClosedCardPayload):
    """A seat's freshly dealt hand and remaining draw-pile count."""

    seat: StrictStr = Field(min_length=1)
    deck_id: StrictStr = Field(min_length=1)
    card_ids: tuple[CardId, ...] = Field(min_length=1)
    hand_size: StrictInt = Field(ge=1)
    deck_remaining: StrictInt = Field(ge=0)
    reshuffled: StrictBool

    @model_validator(mode="after")
    def _hand_size_matches_cards(self) -> Self:
        if self.hand_size != len(self.card_ids):
            raise ValueError("hand_size must equal the number of card_ids")
        return self


class ModelSOPlanRegister(_ClosedCardPayload):
    """One card assigned to a zero-based register slot."""

    register_index: StrictInt = Field(ge=0)
    card_id: CardId


class ModelSOPlanCommittedPayload(_ClosedCardPayload):
    """A seat's ordered register program and decision metadata."""

    seat: StrictStr = Field(min_length=1)
    registers: tuple[ModelSOPlanRegister, ...]
    rationale: StrictStr | None = Field(...)
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _register_indexes_are_unique(self) -> Self:
        indexes = tuple(register.register_index for register in self.registers)
        if len(indexes) != len(set(indexes)):
            raise ValueError("plan_committed register_index values must be unique")
        return self


class ModelSORegisterResolvedPayload(_ClosedCardPayload):
    """One register's resolution in the canonical priority order."""

    seat: StrictStr = Field(min_length=1)
    register_index: StrictInt = Field(ge=0)
    card_id: CardId | None = Field(...)
    action: StrictStr = Field(min_length=1)
    outcome: SORegisterOutcome
    priority: StrictInt = Field(ge=0)
    priority_rank: StrictInt = Field(ge=0)
    fill_reason: SORegisterFillReason | None = Field(...)

    @model_validator(mode="after")
    def _fill_reason_matches_outcome(self) -> Self:
        if self.outcome is SORegisterOutcome.AUTO_REMAIN:
            if self.card_id is not None:
                raise ValueError("auto_remain register_resolved events cannot name a card")
            if self.fill_reason is None:
                raise ValueError("auto_remain register_resolved events require fill_reason")
        elif self.card_id is None:
            raise ValueError(f"{self.outcome.value} register_resolved events require a card")
        elif self.fill_reason is not None:
            raise ValueError("fill_reason is only valid for auto_remain outcomes")
        return self


class ModelSOCardsDiscardedPayload(_ClosedCardPayload):
    """Cards leaving a seat's hand, with an explicit discard reason."""

    seat: StrictStr = Field(min_length=1)
    card_ids: tuple[CardId, ...] = Field(min_length=1)
    reason: StrictStr = Field(min_length=1)


__all__ = [
    "ModelSOCardsDiscardedPayload",
    "ModelSOHandDealtPayload",
    "ModelSOPlanCommittedPayload",
    "ModelSOPlanRegister",
    "ModelSORegisterResolvedPayload",
    "SORegisterFillReason",
    "SORegisterOutcome",
]
