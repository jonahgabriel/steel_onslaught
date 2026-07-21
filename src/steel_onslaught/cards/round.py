"""Pure card-round values and validation.

This module is the seam between the already landed card primitives and a later
runtime producer.  It deliberately deals in payload values, not event
envelopes: a caller supplies an immutable card/deck snapshot, a
``DealerCompute`` and a ``RegisterExecutionReducer`` and receives the four
typed values that a card round would publish.

There is no runner, fold, bus, filesystem, provider, or wall-clock authority
here.  The only state retained by :class:`CardRoundRuntime` is the explicit
immutable dependency graph supplied by its caller.  Replaying a sequence
therefore means validating the same payload values against the same snapshot
and reducing the same seat contexts again.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.cards.dealer import (
    DealerCompute,
    ModelSODealerScope,
    ModelSODeckState,
    ModelSOSplitDeckState,
)
from steel_onslaught.cards.registers import (
    ModelSOSeatResolutionContext,
    RegisterExecutionReducer,
    RegisterPlanError,
    RegisterReplayDriftError,
)
from steel_onslaught.cards.split_deck import SplitDeckDealerAdapter
from steel_onslaught.contracts.card import CardId
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    ModelSORegisterResolvedPayload,
)


class CardRoundValidationError(ValueError):
    """A card-round payload sequence is not derivable from its inputs."""


class CardRoundReplayDriftError(RegisterReplayDriftError):
    """Recorded register values differ from a fresh deterministic reduction."""


class _ClosedRoundModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOCardRoundDeal(_ClosedRoundModel):
    """A pure dealer result paired with its typed ``HAND_DEALT`` value.

    ``ModelSODeckState`` contains only draw/discard piles; the returned hand is
    carried by ``payload``.  Keeping both values together lets a later
    composition root carry the exact immutable dealer state without inventing
    an event-bus or storage dependency.
    """

    seat: StrictStr = Field(min_length=1)
    deck_id: StrictStr = Field(min_length=1)
    payload: ModelSOHandDealtPayload
    state: ModelSODeckState | None = None
    split_state: ModelSOSplitDeckState | None = None

    @model_validator(mode="after")
    def _payload_matches_result(self) -> Self:
        if self.payload.seat != self.seat:
            raise CardRoundValidationError(
                f"HAND_DEALT seat {self.payload.seat!r} does not match deal seat {self.seat!r}"
            )
        if self.payload.deck_id != self.deck_id:
            raise CardRoundValidationError(
                f"HAND_DEALT deck {self.payload.deck_id!r} does not match deal deck "
                f"{self.deck_id!r}"
            )
        if self.payload.partitions is None:
            if self.state is None or self.split_state is not None:
                raise CardRoundValidationError(
                    "single-deck HAND_DEALT values require one deck state"
                )
            if self.payload.deck_remaining != len(self.state.draw_pile):
                raise CardRoundValidationError(
                    "HAND_DEALT deck_remaining must equal the resulting draw-pile length"
                )
        elif self.state is not None:
            raise CardRoundValidationError("split HAND_DEALT values cannot carry single deck state")
        elif self.split_state is None:
            raise CardRoundValidationError("split HAND_DEALT values require split deck state")
        if tuple(self.payload.card_ids) and len(self.payload.card_ids) != self.payload.hand_size:
            raise CardRoundValidationError("HAND_DEALT hand_size must equal card_ids length")
        return self

    @property
    def hand(self) -> tuple[CardId, ...]:
        """Return the immutable dealt hand in dealer order."""

        return self.payload.card_ids


class ModelSOCardRoundSequence(_ClosedRoundModel):
    """The typed values for one complete card round.

    The four fields intentionally mirror the four first-class card payloads.
    ``contexts`` is pure replay input and is never serialized as an event; it
    records the ledger-derived initiative/heat/previous-plan inputs needed to
    re-run the register reducer without hidden state.
    """

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.card_round_sequence"] = Field(...)
    round_length: StrictInt = Field(ge=1)
    hand_dealt: tuple[ModelSOHandDealtPayload, ...] = Field(min_length=1)
    plan_committed: tuple[ModelSOPlanCommittedPayload, ...] = Field(min_length=1)
    register_resolved: tuple[ModelSORegisterResolvedPayload, ...] = Field(...)
    cards_discarded: tuple[ModelSOCardsDiscardedPayload, ...] = Field(min_length=1)
    contexts: tuple[ModelSOSeatResolutionContext, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_structural_order(self) -> Self:
        hand_seats = tuple(payload.seat for payload in self.hand_dealt)
        plan_seats = tuple(payload.seat for payload in self.plan_committed)
        discard_seats = tuple(payload.seat for payload in self.cards_discarded)
        context_seats = tuple(context.seat for context in self.contexts)
        if hand_seats != tuple(sorted(hand_seats)):
            raise CardRoundValidationError("HAND_DEALT values must be in ascending seat order")
        if len(hand_seats) != len(set(hand_seats)):
            raise CardRoundValidationError("card-round seat ids must be unique")
        if plan_seats != hand_seats:
            raise CardRoundValidationError(
                "PLAN_COMMITTED values must contain the same seats as HAND_DEALT in order"
            )
        if discard_seats != hand_seats:
            raise CardRoundValidationError(
                "CARDS_DISCARDED values must contain the same seats as HAND_DEALT in order"
            )
        if context_seats != hand_seats:
            raise CardRoundValidationError(
                "resolution contexts must contain the same seats as HAND_DEALT in order"
            )
        for plan in self.plan_committed:
            indexes = tuple(register.register_index for register in plan.registers)
            if indexes != tuple(sorted(indexes)):
                raise CardRoundValidationError(
                    f"PLAN_COMMITTED registers for seat {plan.seat!r} must be ascending"
                )
        return self

    @property
    def values(
        self,
    ) -> tuple[
        ModelSOHandDealtPayload
        | ModelSOPlanCommittedPayload
        | ModelSORegisterResolvedPayload
        | ModelSOCardsDiscardedPayload,
        ...,
    ]:
        """Return payload values grouped in canonical lifecycle order.

        This is a value-only convenience for tests and future producers.  It
        does not create envelopes or claim that a bus has emitted anything.
        """

        return (
            *self.hand_dealt,
            *self.plan_committed,
            *self.register_resolved,
            *self.cards_discarded,
        )


def _sorted_by_seat[T](values: tuple[T, ...], *, seat: Callable[[T], str]) -> tuple[T, ...]:
    """Return a deterministic seat ordering without mutating caller values."""

    return tuple(sorted(values, key=seat))


def _validate_deck_multiset(
    snapshot: ModelSOCardRuntimeSnapshot,
    *,
    deck_id: str,
    hand: tuple[CardId, ...],
    state: ModelSODeckState,
) -> None:
    """Prove that a dealer result accounts for exactly one deck multiset."""

    deck = snapshot.require_deck(deck_id)
    declared = Counter(str(card_id) for card_id in deck.card_multiset())
    accounted = Counter(str(card_id) for card_id in (*hand, *state.draw_pile, *state.discard_pile))
    if accounted != declared:
        raise CardRoundValidationError(
            f"dealer result for deck {deck_id!r} does not conserve the declared card multiset"
        )
    for card_id in hand:
        snapshot.card_catalog.require(card_id)


def _validate_split_deck_multisets(
    snapshot: ModelSOCardRuntimeSnapshot,
    deal: ModelSOCardRoundDeal,
) -> None:
    """Prove both independent piles and their partition metadata."""

    payload = deal.payload
    partitions = payload.partitions
    split_state = deal.split_state
    if partitions is None or split_state is None:
        raise CardRoundValidationError(
            "split hand validation requires partition metadata and state"
        )
    assert split_state is not None
    for partition, state in (
        (partitions.movement, split_state.movement),
        (partitions.weapon, split_state.weapon),
    ):
        _validate_deck_multiset(
            snapshot,
            deck_id=partition.deck_id,
            hand=partition.card_ids,
            state=state,
        )
        if partition.deck_remaining != len(state.draw_pile):
            raise CardRoundValidationError(
                f"{partition.partition.value} partition deck_remaining does not match state"
            )


def validate_hand_dealt(
    snapshot: ModelSOCardRuntimeSnapshot,
    deal: ModelSOCardRoundDeal,
) -> ModelSOHandDealtPayload:
    """Validate one ``HAND_DEALT`` value against explicit snapshot content."""

    if deal.payload.partitions is not None:
        _validate_split_deck_multisets(snapshot, deal)
        return deal.payload
    if deal.state is None:
        raise CardRoundValidationError("single-deck HAND_DEALT values require deck state")
    if deal.deck_id not in {str(deck.id) for deck in snapshot.decks}:
        raise CardRoundValidationError(f"unknown card-round deck {deal.deck_id!r}")
    deck = snapshot.require_deck(deal.deck_id)
    payload = deal.payload
    if payload.hand_size != deck.hand_size:
        raise CardRoundValidationError(
            f"HAND_DEALT hand_size {payload.hand_size} does not match deck {deck.id!r} "
            f"hand_size {deck.hand_size}"
        )
    _validate_deck_multiset(
        snapshot,
        deck_id=deal.deck_id,
        hand=payload.card_ids,
        state=deal.state,
    )
    return payload


def build_hand_dealt(
    snapshot: ModelSOCardRuntimeSnapshot,
    dealer: DealerCompute,
    *,
    scope: ModelSODealerScope,
    state: ModelSODeckState | None = None,
) -> ModelSOCardRoundDeal:
    """Deal one explicit hand without constructing a round runtime object."""

    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    return CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=1,
    ).deal(scope=scope, state=state)


def validate_plan_for_hand(
    snapshot: ModelSOCardRuntimeSnapshot,
    hand: ModelSOHandDealtPayload,
    plan: ModelSOPlanCommittedPayload,
    *,
    register_count: int,
    initiative: int = 0,
    lock_depth: int = 0,
    previous_plan: ModelSOPlanCommittedPayload | None = None,
) -> ModelSOSeatResolutionContext:
    """Build and validate one reducer context from ``HAND_DEALT`` + plan.

    The hand is a multiset, so duplicate physical cards are counted rather than
    collapsed into a set.  Heat locks are delegated to the existing reducer
    policy: the suffix is capped to preserve one free register and a locked
    slot must repeat a real previous card.  A register beyond ``register_count``
    is intentionally left to the reducer's explicit ``AUTO_REMAIN`` policy.
    """

    if hand.seat != plan.seat:
        raise CardRoundValidationError(
            f"PLAN_COMMITTED seat {plan.seat!r} does not match HAND_DEALT seat {hand.seat!r}"
        )
    if hand.partitions is None:
        try:
            deck = snapshot.require_deck(hand.deck_id)
        except KeyError as exc:
            raise CardRoundValidationError(f"unknown card-round deck {hand.deck_id!r}") from exc
        if register_count != deck.register_count:
            raise CardRoundValidationError(
                f"register_count {register_count} does not match deck {deck.id!r} "
                f"register_count {deck.register_count}"
            )
    elif hand.register_count != register_count:
        raise CardRoundValidationError(
            f"register_count {register_count} does not match split hand register_count "
            f"{hand.register_count}"
        )
    available = Counter(str(card_id) for card_id in hand.card_ids)
    chosen = Counter(str(register.card_id) for register in plan.registers)
    if chosen - available:
        raise CardRoundValidationError(
            f"PLAN_COMMITTED seat {plan.seat!r} uses cards not present in its hand: "
            f"{sorted(chosen - available)}"
        )
    for card_id in hand.card_ids:
        snapshot.card_catalog.require(card_id)
    try:
        context = ModelSOSeatResolutionContext(
            seat=plan.seat,
            register_count=register_count,
            initiative=initiative,
            lock_depth=lock_depth,
            plan=plan,
            previous_plan=previous_plan,
        )
    except (TypeError, ValueError) as exc:
        raise CardRoundValidationError(str(exc)) from exc
    try:
        context.validate_plan()
    except RegisterPlanError as exc:
        raise CardRoundValidationError(str(exc)) from exc
    return context


def build_discarded(
    hand: ModelSOHandDealtPayload,
    *,
    card_ids: tuple[CardId, ...] | None = None,
    reason: str = "end_of_round",
) -> ModelSOCardsDiscardedPayload:
    """Build a strict ``CARDS_DISCARDED`` value from an explicit hand.

    The default is the round boundary policy: discard the complete dealt hand
    in dealer order.  Callers may provide a played subset, but it must be a
    multiset subset of the hand; ``AUTO_REMAIN`` rows and heat-locked repeats
    can therefore never manufacture a card that was not actually dealt.
    """

    if not isinstance(reason, str) or not reason:
        raise CardRoundValidationError("discard reason must be a non-empty string")
    chosen = hand.card_ids if card_ids is None else card_ids
    if not chosen:
        raise CardRoundValidationError("CARDS_DISCARDED requires at least one card")
    if Counter(str(card_id) for card_id in chosen) - Counter(
        str(card_id) for card_id in hand.card_ids
    ):
        raise CardRoundValidationError(
            f"CARDS_DISCARDED seat {hand.seat!r} names cards absent from its hand"
        )
    return ModelSOCardsDiscardedPayload(seat=hand.seat, card_ids=chosen, reason=reason)


def validate_card_round(
    sequence: ModelSOCardRoundSequence,
    snapshot: ModelSOCardRuntimeSnapshot,
    reducer: RegisterExecutionReducer,
) -> None:
    """Validate all four payload groups and prove deterministic replay parity."""

    if reducer.card_catalog is not snapshot.card_catalog:
        raise CardRoundValidationError(
            "card-round reducer must use the exact catalog object from the runtime snapshot"
        )
    # The sequence carries event values, not dealer state.  Validate the values
    # that do not require hidden state here; callers using ``CardRoundRuntime``
    # get the stronger multiset/state proof from the deal objects it retains.
    for payload in sequence.hand_dealt:
        if payload.partitions is not None:
            if payload.register_count is None:
                raise CardRoundValidationError(
                    f"split HAND_DEALT for seat {payload.seat!r} requires register_count"
                )
            for partition in (payload.partitions.movement, payload.partitions.weapon):
                snapshot.require_deck(partition.deck_id)
                for card_id in partition.card_ids:
                    snapshot.card_catalog.require(card_id)
            continue
        try:
            deck = snapshot.require_deck(payload.deck_id)
        except KeyError as exc:
            raise CardRoundValidationError(f"unknown card-round deck {payload.deck_id!r}") from exc
        if payload.hand_size != deck.hand_size:
            raise CardRoundValidationError(
                f"HAND_DEALT hand_size for seat {payload.seat!r} does not match its deck"
            )
        for card_id in payload.card_ids:
            snapshot.card_catalog.require(card_id)
    hand_by_seat = {payload.seat: payload for payload in sequence.hand_dealt}
    for context, plan in zip(sequence.contexts, sequence.plan_committed, strict=True):
        hand = hand_by_seat[context.seat]
        if context.plan != plan:
            raise CardRoundValidationError(
                f"context plan for seat {context.seat!r} differs from PLAN_COMMITTED value"
            )
        if hand.partitions is not None:
            if hand.register_count is None:
                raise CardRoundValidationError(
                    f"split HAND_DEALT for seat {context.seat!r} requires register_count"
                )
            if context.register_count != hand.register_count:
                raise CardRoundValidationError(
                    f"context register_count for split seat {context.seat!r} does not match hand"
                )
        else:
            try:
                deck = snapshot.require_deck(hand.deck_id)
            except KeyError as exc:
                raise CardRoundValidationError(f"unknown card-round deck {hand.deck_id!r}") from exc
            if context.register_count != deck.register_count:
                raise CardRoundValidationError(
                    f"context register_count for seat {context.seat!r} does not match deck"
                )
        available = Counter(str(card_id) for card_id in hand.card_ids)
        chosen = Counter(str(register.card_id) for register in plan.registers)
        if chosen - available:
            raise CardRoundValidationError(
                f"PLAN_COMMITTED seat {context.seat!r} uses cards absent from HAND_DEALT"
            )
        try:
            context.validate_plan()
        except RegisterPlanError as exc:
            raise CardRoundValidationError(str(exc)) from exc
    expected = reducer.resolve_round(sequence.contexts, sequence.round_length)
    if expected != sequence.register_resolved:
        raise CardRoundReplayDriftError(
            "card-round REGISTER_RESOLVED values drift from the explicit plans and catalog"
        )
    hand_by_seat = {payload.seat: payload for payload in sequence.hand_dealt}
    for discarded in sequence.cards_discarded:
        hand = hand_by_seat[discarded.seat]
        if Counter(str(card_id) for card_id in discarded.card_ids) - Counter(
            str(card_id) for card_id in hand.card_ids
        ):
            raise CardRoundValidationError(
                f"CARDS_DISCARDED seat {discarded.seat!r} names cards absent from HAND_DEALT"
            )


def carry_forward_plans(
    sequence: ModelSOCardRoundSequence,
) -> dict[str, ModelSOPlanCommittedPayload]:
    """Project a completed round into the ``previous_plan`` the next round needs.

    ``PLAN_COMMITTED`` only carries the registers a pilot was FREE to program,
    so a register that stayed heat-locked is absent from it.  Carrying that
    plan forward verbatim makes the next round unresolvable whenever the same
    register is locked twice in a row: the heat-lock repeat looks up its prior
    card, finds nothing, and ``RegisterPlanError`` escapes into the runner and
    kills the match.

    ``REGISTER_RESOLVED`` is the complete per-register truth — ``RESOLVED``
    rows carry the programmed card and ``HEAT_LOCKED`` rows carry the repeated
    one — so the resolved rows, not the plan, are what the next round must
    inherit.  ``AUTO_REMAIN`` rows name no card and are dropped: a short-deck
    register has nothing to repeat, which the reducer already rejects loudly
    rather than inventing a null-card heat lock.

    Decision metadata (``rationale``/``confidence``) is preserved from the
    seat's committed plan; only the register program is widened.
    """

    registers_by_seat: dict[str, list[ModelSOPlanRegister]] = {}
    for row in sequence.register_resolved:
        if row.card_id is None:
            continue
        registers_by_seat.setdefault(row.seat, []).append(
            ModelSOPlanRegister(register_index=row.register_index, card_id=row.card_id)
        )
    carried: dict[str, ModelSOPlanCommittedPayload] = {}
    for plan in sequence.plan_committed:
        registers = tuple(
            sorted(
                registers_by_seat.get(plan.seat, []),
                key=lambda register: register.register_index,
            )
        )
        carried[plan.seat] = (
            plan
            if registers == plan.registers
            else plan.model_copy(update={"registers": registers})
        )
    return carried


def resolve_card_round(
    reducer: RegisterExecutionReducer,
    contexts: tuple[ModelSOSeatResolutionContext, ...],
    round_length: int,
) -> tuple[ModelSORegisterResolvedPayload, ...]:
    """Resolve one round through the already-bound pure reducer."""

    return reducer.resolve_round(contexts, round_length)


def verify_card_round_replay(
    sequence: ModelSOCardRoundSequence,
    snapshot: ModelSOCardRuntimeSnapshot,
    reducer: RegisterExecutionReducer,
) -> None:
    """Standalone replay-honesty helper for a recorded value sequence."""

    validate_card_round(sequence, snapshot, reducer)


@dataclass(frozen=True, slots=True)
class CardRoundRuntime:
    """Explicit pure dependencies for deriving one card-round value sequence."""

    card_runtime_snapshot: ModelSOCardRuntimeSnapshot
    dealer: DealerCompute
    reducer: RegisterExecutionReducer
    round_length: int
    split_deck_adapter: SplitDeckDealerAdapter | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.card_runtime_snapshot, ModelSOCardRuntimeSnapshot):
            raise TypeError("card round requires ModelSOCardRuntimeSnapshot")
        if not isinstance(self.dealer, DealerCompute):
            raise TypeError("card round requires DealerCompute")
        if not isinstance(self.reducer, RegisterExecutionReducer):
            raise TypeError("card round requires RegisterExecutionReducer")
        if self.reducer.card_catalog is not self.card_runtime_snapshot.card_catalog:
            raise CardRoundValidationError(
                "card round reducer must use the exact snapshot card catalog object"
            )
        if isinstance(self.round_length, bool) or not isinstance(self.round_length, int):
            raise TypeError("round_length must be an integer")
        if self.round_length < 1:
            raise ValueError("round_length must be >= 1")
        # A runtime activation must be explicit; passive snapshots cannot be
        # accidentally turned into card gameplay by this pure helper.
        if self.card_runtime_snapshot.selected_deck_id is None and self.split_deck_adapter is None:
            raise CardRoundValidationError("card round requires an explicitly selected deck")
        if self.split_deck_adapter is not None:
            if self.split_deck_adapter.snapshot is not self.card_runtime_snapshot:
                raise CardRoundValidationError(
                    "split-deck runtime and snapshot must share identity"
                )
            if self.split_deck_adapter.dealer is not self.dealer:
                raise CardRoundValidationError("split-deck runtime and dealer must share identity")

    @property
    def deck_id(self) -> str:
        return str(self.card_runtime_snapshot.selected_deck.id)

    @property
    def snapshot(self) -> ModelSOCardRuntimeSnapshot:
        """Short alias for the immutable card/deck snapshot dependency."""

        return self.card_runtime_snapshot

    def deal(
        self,
        *,
        scope: ModelSODealerScope,
        state: ModelSODeckState | None = None,
    ) -> ModelSOCardRoundDeal:
        """Deal one complete hand under an explicit deterministic scope."""

        if scope.seat == "":
            raise CardRoundValidationError("dealer scope seat must be non-empty")
        deck = self.card_runtime_snapshot.selected_deck
        result = (
            self.dealer.spawn_deal_for_seat(deck=deck, scope=scope)
            if state is None
            else self.dealer.deal_hand_for_seat(state=state, count=deck.hand_size, scope=scope)
        )
        if result.exhausted:
            raise CardRoundValidationError(
                f"dealer exhausted selected deck {deck.id!r} before a complete hand was dealt"
            )
        payload = ModelSOHandDealtPayload(
            seat=scope.seat,
            deck_id=deck.id,
            card_ids=result.hand,
            hand_size=deck.hand_size,
            deck_remaining=len(result.state.draw_pile),
            reshuffled=result.reshuffled,
        )
        deal = ModelSOCardRoundDeal(
            seat=scope.seat,
            deck_id=deck.id,
            payload=payload,
            state=result.state,
        )
        validate_hand_dealt(self.card_runtime_snapshot, deal)
        return deal

    def sequence(
        self,
        *,
        deals: tuple[ModelSOCardRoundDeal, ...],
        contexts: tuple[ModelSOSeatResolutionContext, ...],
        cards_discarded: tuple[ModelSOCardsDiscardedPayload, ...] | None = None,
    ) -> ModelSOCardRoundSequence:
        """Derive the four payload groups in deterministic lifecycle order."""

        canonical_deals = _sorted_by_seat(deals, seat=lambda value: value.seat)
        canonical_contexts = _sorted_by_seat(contexts, seat=lambda value: value.seat)
        if not canonical_deals or not canonical_contexts:
            raise CardRoundValidationError("card round requires at least one seat")
        if tuple(deal.seat for deal in canonical_deals) != tuple(
            context.seat for context in canonical_contexts
        ):
            raise CardRoundValidationError("deals and resolution contexts must contain equal seats")
        for deal in canonical_deals:
            validate_hand_dealt(self.card_runtime_snapshot, deal)
        hand_by_seat = {deal.seat: deal.payload for deal in canonical_deals}
        plans = tuple(context.plan for context in canonical_contexts)
        for context in canonical_contexts:
            validate_plan_for_hand(
                self.card_runtime_snapshot,
                hand_by_seat[context.seat],
                context.plan,
                register_count=context.register_count,
                initiative=context.initiative,
                lock_depth=context.lock_depth,
                previous_plan=context.previous_plan,
            )
        resolved = self.reducer.resolve_round(canonical_contexts, self.round_length)
        discarded = (
            _sorted_by_seat(cards_discarded, seat=lambda value: value.seat)
            if cards_discarded is not None
            else tuple(build_discarded(hand_by_seat[seat]) for seat in hand_by_seat)
        )
        sequence = ModelSOCardRoundSequence(
            schema_version="0.1.0",
            kind="steel_onslaught.card_round_sequence",
            round_length=self.round_length,
            hand_dealt=tuple(deal.payload for deal in canonical_deals),
            plan_committed=plans,
            register_resolved=resolved,
            cards_discarded=discarded,
            contexts=canonical_contexts,
        )
        validate_card_round(sequence, self.card_runtime_snapshot, self.reducer)
        return sequence

    # Explicit verb aliases keep the value-only seam readable at call sites
    # while retaining one implementation and one proof surface.
    build_sequence = sequence

    def verify_replay(self, sequence: ModelSOCardRoundSequence) -> None:
        """Re-derive and validate a recorded sequence, failing loudly on drift."""

        try:
            validate_card_round(sequence, self.card_runtime_snapshot, self.reducer)
        except CardRoundReplayDriftError:
            raise
        except (CardRoundValidationError, RegisterReplayDriftError) as exc:
            raise CardRoundReplayDriftError(str(exc)) from exc


# Friendly aliases for callers that prefer the model-style context name.
ModelSOCardRoundContext = CardRoundRuntime


__all__ = [
    "CardRoundReplayDriftError",
    "CardRoundRuntime",
    "CardRoundValidationError",
    "ModelSOCardRoundContext",
    "ModelSOCardRoundDeal",
    "ModelSOCardRoundSequence",
    "build_discarded",
    "build_hand_dealt",
    "carry_forward_plans",
    "resolve_card_round",
    "validate_card_round",
    "validate_hand_dealt",
    "validate_plan_for_hand",
    "verify_card_round_replay",
]
