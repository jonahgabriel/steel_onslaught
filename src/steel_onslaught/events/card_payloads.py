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


class SOCardPartition(StrEnum):
    """The explicit piles in a split card hand.

    ``UTILITY`` is the Phase 2 third pile (smoke/chaff/flares counterplay); it
    is only present in a hand when the seat declares a utility deck and a
    positive utility quota, so pre-Phase-2 split hands stay two-partition and
    byte-identical.
    """

    MOVEMENT = "movement"
    WEAPON = "weapon"
    UTILITY = "utility"


class SOPlanSource(StrEnum):
    """Who actually authored one committed register plan.

    Recording the authorship on the event makes a *substituted* plan durably
    classified in the ledger and detectable by replay instead of silently
    indistinguishable from a real provider decision.  The classification is
    only useful if it separates the three genuinely different cases, so the
    deterministic planner running by design is not the same member as the
    deterministic planner standing in for a failed provider:

    ``LLM``
        A provider completion authored this plan.
    ``DETERMINISTIC_PLANNER``
        The priority planner authored it *by design* — a seat with no bound
        card programmer (a human seat, a deterministic pilot, or a hermetic /
        replay match).  Nothing was substituted and nothing failed.
    ``DETERMINISTIC_FALLBACK``
        A seat that *was* bound to a provider fell back to the priority
        planner after a classified provider failure.  This member is the
        only real substitution signal.
    ``UNSPECIFIED``
        The authoring seam did not classify the plan.  This is the model
        default so that events persisted before this field existed stay
        honestly unknown instead of being retroactively relabelled as a
        provider decision or as a substitution that never happened.
    """

    LLM = "llm"
    DETERMINISTIC_PLANNER = "deterministic_planner"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    UNSPECIFIED = "unspecified"


SPLIT_DECK_MARKER = "deck.split"


class ModelSOHandPartitionPayload(_ClosedCardPayload):
    """Typed truth for one partition of a split hand.

    A zero quota is represented by an empty ``card_ids`` tuple rather than by
    omitting the partition.  This keeps the hand display and replay contract
    total while preserving the closed event schema.
    """

    partition: SOCardPartition
    deck_id: StrictStr = Field(min_length=1)
    card_ids: tuple[CardId, ...] = ()
    requested_count: StrictInt = Field(ge=0)
    deck_remaining: StrictInt = Field(ge=0)
    reshuffled: StrictBool

    @model_validator(mode="after")
    def _count_matches_cards(self) -> Self:
        if self.requested_count != len(self.card_ids):
            raise ValueError("partition requested_count must equal card_ids length")
        return self


class ModelSOHandPartitionsPayload(_ClosedCardPayload):
    """Movement/weapon (and optional Phase 2 utility) partition metadata.

    ``utility`` defaults to ``None`` and is excluded from serialization when
    absent, so every pre-Phase-2 split-hand payload stays byte-identical.  It
    is only populated when the seat is dealt a positive utility quota.
    """

    movement: ModelSOHandPartitionPayload
    weapon: ModelSOHandPartitionPayload
    utility: ModelSOHandPartitionPayload | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def _partitions_are_named_correctly(self) -> Self:
        if self.movement.partition is not SOCardPartition.MOVEMENT:
            raise ValueError("movement partition must be named movement")
        if self.weapon.partition is not SOCardPartition.WEAPON:
            raise ValueError("weapon partition must be named weapon")
        utility_count = 0
        if self.utility is not None:
            if self.utility.partition is not SOCardPartition.UTILITY:
                raise ValueError("utility partition must be named utility")
            utility_count = self.utility.requested_count
        if self.movement.requested_count + self.weapon.requested_count + utility_count < 1:
            raise ValueError("split hand must contain at least one card")
        return self


class ModelSOHandDealtPayload(_ClosedCardPayload):
    """A seat's freshly dealt hand and remaining draw-pile count."""

    seat: StrictStr = Field(min_length=1)
    deck_id: StrictStr = Field(min_length=1)
    card_ids: tuple[CardId, ...] = Field(min_length=1)
    hand_size: StrictInt = Field(ge=1)
    deck_remaining: StrictInt = Field(ge=0)
    reshuffled: StrictBool
    partitions: ModelSOHandPartitionsPayload | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    register_count: StrictInt | None = Field(
        default=None,
        ge=1,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def _hand_size_matches_cards(self) -> Self:
        if self.hand_size != len(self.card_ids):
            raise ValueError("hand_size must equal the number of card_ids")
        if self.partitions is not None:
            if self.deck_id != SPLIT_DECK_MARKER:
                raise ValueError(f"split hand payloads must use deck marker {SPLIT_DECK_MARKER!r}")
            utility_partition = self.partitions.utility
            utility_cards = () if utility_partition is None else utility_partition.card_ids
            utility_count = 0 if utility_partition is None else utility_partition.requested_count
            partition_cards = (
                *self.partitions.movement.card_ids,
                *self.partitions.weapon.card_ids,
                *utility_cards,
            )
            if tuple(partition_cards) != tuple(self.card_ids):
                raise ValueError("split hand partitions must preserve card_ids order")
            if self.hand_size != (
                self.partitions.movement.requested_count
                + self.partitions.weapon.requested_count
                + utility_count
            ):
                raise ValueError("split hand_size must equal partition quotas")
            if self.register_count is None:
                raise ValueError("split hand payloads require register_count")
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
    # Fail-safe default: a plan is credited to a provider only when the LLM
    # boundary explicitly says so, and it is called a substitution only when a
    # substitution actually happened.  An omitted field (every plan_committed
    # event persisted before this field existed) is therefore ``unspecified``,
    # not ``deterministic_fallback``; defaulting to the substitution member
    # would retroactively relabel historical evidence.
    plan_source: SOPlanSource = SOPlanSource.UNSPECIFIED
    # Spatial-representation arms R1/R2 (2026-07-24): a one-line runtime
    # receipt that spatial data was rendered and read for this plan. Two
    # distinct sources feed this ONE field, by representation:
    #   * ``grid_scaffold`` (R2): the model is asked for one extra field,
    #     ``spatial_read`` -- its own stated one-line read of the ASCII grid
    #     before selecting registers. ``None`` if the model omitted it (a
    #     genuine compliance signal -- never backfilled).
    #   * ``grid`` (R1, no scaffold): the model is NEVER asked for one, so
    #     ``llm.programming`` computes a deterministic summary from the same
    #     real per-round grid/movement-preview/weapon-range-flag data the
    #     prompt rendered (``match.spatial_preview.compute_spatial_read_receipt``).
    #     This closes the SO-COMP-INT/SO-SPATIAL-RECEIPT gap (PR #208):
    #     before this, EVERY R1 arm's ``plan_committed`` payloads carried
    #     null ``spatial_read`` (0/302, 0/500, 0/358, 0/590 across all four
    #     factorial arms), so R1 attribution rested solely on the overlay's
    #     ``pilot_spec_id`` -- a configuration fact, never a runtime one.
    #
    # Fail-safe default, same rationale as ``plan_source`` above: ``None``
    # only when no spatial representation was active at all
    # (``spatial_representation == "none"``, or every plan_committed event
    # persisted before this field existed). Absence here is never evidence
    # of model behavior for R2's model-supplied case, and is never reachable
    # at all for an opted-in R1 seat.
    spatial_read: StrictStr | None = None

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
    "SPLIT_DECK_MARKER",
    "ModelSOCardsDiscardedPayload",
    "ModelSOHandDealtPayload",
    "ModelSOHandPartitionPayload",
    "ModelSOHandPartitionsPayload",
    "ModelSOPlanCommittedPayload",
    "ModelSOPlanRegister",
    "ModelSORegisterResolvedPayload",
    "SOCardPartition",
    "SOPlanSource",
    "SORegisterFillReason",
    "SORegisterOutcome",
]
