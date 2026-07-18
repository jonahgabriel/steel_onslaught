"""Pure deterministic reducer for programmed card registers.

The reducer consumes explicit, immutable seat contexts and an injected
``ModelSOCardCatalog``. It computes ``REGISTER_RESOLVED`` payloads only; event
envelopes, runners, producers, and runtime wiring belong to later slices.

For every register index all seats resolve simultaneously. The returned order
is deterministic: card priority descending, initiative descending, then seat
identifier ascending. A short deck produces explicit ``AUTO_REMAIN`` rows,
while heat-lock repeats the prior card as ``HEAT_LOCKED``. The two outcomes are
never conflated, so replay preserves why a register did not use the current
plan.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.cards.actions import action_for_card
from steel_onslaught.contracts.card import (
    CardId,
    ModelSOCardCatalog,
)
from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
    SORegisterFillReason,
    SORegisterOutcome,
)
from steel_onslaught.pilots.schemas import SOPilotAction

_REMAIN_ACTION = SOPilotAction.REMAIN.value
_REMAIN_PRIORITY = 0


class RegisterPlanError(ValueError):
    """A committed plan does not satisfy the seat's register invariants."""


class RegisterReplayDriftError(AssertionError):
    """Recorded resolutions differ from a fresh deterministic reconstruction."""


class ModelSOSeatResolutionContext(BaseModel):
    """Immutable ledger-derived inputs for one seat in one register round."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    seat: StrictStr = Field(min_length=1)
    register_count: StrictInt = Field(ge=1)
    initiative: StrictInt = Field(ge=0)
    lock_depth: StrictInt = Field(default=0, ge=0)
    plan: ModelSOPlanCommittedPayload
    previous_plan: ModelSOPlanCommittedPayload | None = None

    @model_validator(mode="after")
    def _plans_belong_to_seat(self) -> ModelSOSeatResolutionContext:
        if self.plan.seat != self.seat:
            raise ValueError(
                f"plan seat {self.plan.seat!r} does not match context seat {self.seat!r}"
            )
        if self.previous_plan is not None and self.previous_plan.seat != self.seat:
            raise ValueError(
                "previous_plan seat "
                f"{self.previous_plan.seat!r} does not match context seat {self.seat!r}"
            )
        return self

    def card_at(self, plan: ModelSOPlanCommittedPayload | None, index: int) -> CardId | None:
        """Return the card assigned to ``index`` in an optional plan."""
        if plan is None:
            return None
        for register in plan.registers:
            if register.register_index == index:
                return register.card_id
        return None

    def locked_indices(self) -> frozenset[int]:
        """Return the suffix locked by heat, preserving one free register."""
        return heat_locked_indices(self.lock_depth, self.register_count)

    def validate_plan(self) -> None:
        """Require exactly every in-range, currently free register once."""
        locked = self.locked_indices()
        expected = {index for index in range(self.register_count) if index not in locked}
        programmed = tuple(register.register_index for register in self.plan.registers)
        if len(programmed) != len(set(programmed)):
            raise RegisterPlanError(
                f"seat {self.seat!r} plan programs a register more than once: {sorted(programmed)}"
            )
        if set(programmed) != expected:
            raise RegisterPlanError(
                f"seat {self.seat!r} plan must program exactly its free registers "
                f"{sorted(expected)} (register_count={self.register_count}, "
                f"locked={sorted(locked)}); got {sorted(programmed)}"
            )


def _require_non_bool_int(value: object, *, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {value!r}")
    return value


def heat_locked_indices(lock_depth: int, register_count: int) -> frozenset[int]:
    """Return the heat-locked suffix, capped so one register remains free."""
    depth = _require_non_bool_int(lock_depth, name="lock_depth", minimum=0)
    count = _require_non_bool_int(register_count, name="register_count", minimum=1)
    capped = min(depth, count - 1)
    return frozenset(range(count - capped, count))


def _validate_contexts(contexts: tuple[ModelSOSeatResolutionContext, ...]) -> None:
    if not contexts:
        raise ValueError("contexts must contain at least one seat")
    seats = tuple(context.seat for context in contexts)
    if len(seats) != len(set(seats)):
        raise ValueError(f"contexts must have unique seat ids, got {sorted(seats)}")
    for context in contexts:
        context.validate_plan()


def _resolve_one(
    context: ModelSOSeatResolutionContext,
    index: int,
    cards: ModelSOCardCatalog,
) -> tuple[CardId | None, str, int, SORegisterOutcome, SORegisterFillReason | None]:
    if index < 0:
        raise ValueError(f"register index must be >= 0, got {index}")

    # A register beyond the seat's contract is an explicit short-deck fill.
    if index >= context.register_count:
        return (
            None,
            _REMAIN_ACTION,
            _REMAIN_PRIORITY,
            SORegisterOutcome.AUTO_REMAIN,
            SORegisterFillReason.SHORT_DECK,
        )

    # Heat lock repeats the prior card. A missing prior card cannot be encoded
    # as HEAT_LOCKED under the closed payload contract, so fail loudly rather
    # than inventing a null-card heat-lock fact.
    if index in context.locked_indices():
        previous_card_id = context.card_at(context.previous_plan, index)
        if previous_card_id is None:
            raise RegisterPlanError(
                f"seat {context.seat!r} heat-locked register {index} has no prior card to repeat"
            )
        card = cards.require(previous_card_id)
        return (
            previous_card_id,
            action_for_card(card).value,
            card.priority,
            SORegisterOutcome.HEAT_LOCKED,
            None,
        )

    card_id = context.card_at(context.plan, index)
    if card_id is None:  # guarded by validate_plan
        raise RegisterPlanError(f"seat {context.seat!r} free register {index} is unprogrammed")
    card = cards.require(card_id)
    return card_id, action_for_card(card).value, card.priority, SORegisterOutcome.RESOLVED, None


def resolve_register(
    contexts: tuple[ModelSOSeatResolutionContext, ...],
    index: int,
    cards: ModelSOCardCatalog,
) -> tuple[ModelSORegisterResolvedPayload, ...]:
    """Resolve one register for every seat in canonical priority order."""
    register_index = _require_non_bool_int(index, name="register index", minimum=0)
    _validate_contexts(contexts)
    resolved = [(context, *_resolve_one(context, register_index, cards)) for context in contexts]
    resolved.sort(key=lambda row: (-row[3], -row[0].initiative, row[0].seat))
    return tuple(
        ModelSORegisterResolvedPayload(
            seat=context.seat,
            register_index=register_index,
            card_id=card_id,
            action=action,
            outcome=outcome,
            priority=priority,
            priority_rank=rank,
            fill_reason=fill_reason,
        )
        for rank, (context, card_id, action, priority, outcome, fill_reason) in enumerate(resolved)
    )


def resolve_round(
    contexts: tuple[ModelSOSeatResolutionContext, ...],
    round_length: int,
    cards: ModelSOCardCatalog,
) -> tuple[ModelSORegisterResolvedPayload, ...]:
    """Resolve registers ``0..round_length-1`` in deterministic fold order."""
    length = _require_non_bool_int(round_length, name="round_length", minimum=1)
    _validate_contexts(contexts)
    out: list[ModelSORegisterResolvedPayload] = []
    for index in range(length):
        out.extend(resolve_register(contexts, index, cards))
    return tuple(out)


class RegisterExecutionReducer:
    """Stateless facade over the pure reducer with an explicit catalog binding."""

    def __init__(self, cards: ModelSOCardCatalog) -> None:
        self._cards = cards

    def resolve_round(
        self,
        contexts: tuple[ModelSOSeatResolutionContext, ...],
        round_length: int,
    ) -> tuple[ModelSORegisterResolvedPayload, ...]:
        return resolve_round(contexts, round_length, self._cards)

    def verify_replay(
        self,
        recorded: tuple[ModelSORegisterResolvedPayload, ...],
        contexts: tuple[ModelSOSeatResolutionContext, ...],
        round_length: int,
    ) -> None:
        verify_register_replay(recorded, contexts, round_length, self._cards)


def verify_register_replay(
    recorded: tuple[ModelSORegisterResolvedPayload, ...],
    contexts: tuple[ModelSOSeatResolutionContext, ...],
    round_length: int,
    cards: ModelSOCardCatalog,
) -> None:
    """Fail loudly unless the recorded rows exactly re-derive from the plans."""
    recomputed = resolve_round(contexts, round_length, cards)
    if recomputed != recorded:
        raise RegisterReplayDriftError(
            "register-plan replay drift: re-resolving the recorded plans did not reproduce "
            f"the REGISTER_RESOLVED sequence (recorded {len(recorded)} rows, "
            f"recomputed {len(recomputed)} rows)"
        )


__all__ = [
    "ModelSOSeatResolutionContext",
    "RegisterExecutionReducer",
    "RegisterPlanError",
    "RegisterReplayDriftError",
    "heat_locked_indices",
    "resolve_register",
    "resolve_round",
    "verify_register_replay",
]
