"""Pure validation of a recorded card-round wire sequence.

This is deliberately a replay *input* seam, not a replay engine.  It parses
the four card event payloads through the canonical consumed-payload registry,
checks their phase/order/seat/deck invariants, and returns typed values for a
later fold owner.  It does not read a ledger, construct envelopes, publish on
a bus, or mutate match state.

Wire limits are explicit: card payloads do not carry the full dealer draw and
discard piles or a runtime content digest.  The validator can therefore prove
the selected deck id, known-card membership, hand/plan/discard multisets, and
envelope correlation/causation/order, but it cannot prove hidden dealer state
from payloads alone.  A later composition root must retain the immutable
``ModelSOCardRoundDeal`` values from the producer when that stronger proof is
required.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from steel_onslaught.cards.actions import action_for_card
from steel_onslaught.contracts.card import CardCatalogError
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeProvenance,
    ModelSOCardRuntimeSnapshot,
)
from steel_onslaught.events.card_payloads import (
    SPLIT_DECK_MARKER,
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
    SORegisterOutcome,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    CURRENT_CONSUMED_PAYLOAD_MODELS,
    ModelSOMatchStartedPayload,
)

_CARD_EVENT_TYPES = (
    SOEventType.HAND_DEALT,
    SOEventType.PLAN_COMMITTED,
    SOEventType.REGISTER_RESOLVED,
    SOEventType.CARDS_DISCARDED,
)
_CARD_EVENT_TYPE_SET = frozenset(_CARD_EVENT_TYPES)

type CardRoundPayload = (
    ModelSOHandDealtPayload
    | ModelSOPlanCommittedPayload
    | ModelSORegisterResolvedPayload
    | ModelSOCardsDiscardedPayload
)


class CardRoundReplayError(ValueError):
    """A card-round event stream is not a valid canonical wire sequence."""


class _ClosedReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOParsedCardRoundEvent(_ClosedReplayModel):
    """Strictly parsed card payload plus deterministic envelope metadata."""

    event_type: SOEventType
    match_id: StrictStr = Field(min_length=1)
    correlation_id: UUID
    event_id: StrictStr = Field(min_length=26, max_length=26)
    tick: StrictInt = Field(ge=0)
    sequence_in_tick: StrictInt = Field(ge=0)
    message_id: UUID
    causation_id: UUID | None
    payload: CardRoundPayload


class ModelSOCardRoundReplay(_ClosedReplayModel):
    """Validated four-phase payload values for one card round."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.card_round_replay"] = "steel_onslaught.card_round_replay"
    match_id: StrictStr = Field(min_length=1)
    correlation_id: UUID
    deck_id: StrictStr = Field(min_length=1)
    events: tuple[ModelSOParsedCardRoundEvent, ...] = Field(min_length=1)
    hand_dealt: tuple[ModelSOHandDealtPayload, ...] = Field(min_length=1)
    plan_committed: tuple[ModelSOPlanCommittedPayload, ...] = Field(min_length=1)
    register_resolved: tuple[ModelSORegisterResolvedPayload, ...] = Field(min_length=1)
    cards_discarded: tuple[ModelSOCardsDiscardedPayload, ...] = Field(min_length=1)
    cancelled: StrictBool = False


@dataclass(frozen=True, slots=True)
class _ParsedRound:
    events: tuple[ModelSOParsedCardRoundEvent, ...]
    hand_dealt: tuple[ModelSOHandDealtPayload, ...]
    plan_committed: tuple[ModelSOPlanCommittedPayload, ...]
    register_resolved: tuple[ModelSORegisterResolvedPayload, ...]
    cards_discarded: tuple[ModelSOCardsDiscardedPayload, ...]


def _parse_event(event: ModelSOEventEnvelope) -> ModelSOParsedCardRoundEvent:
    if not isinstance(event, ModelSOEventEnvelope):
        raise TypeError("card-round replay requires ModelSOEventEnvelope values")
    if event.event_type not in _CARD_EVENT_TYPES:
        raise CardRoundReplayError(
            f"card-round replay accepts only {_CARD_EVENT_TYPES!r}; got {event.event_type!r}"
        )
    model = CURRENT_CONSUMED_PAYLOAD_MODELS[event.event_type]
    try:
        payload = model.model_validate(event.payload)
    except ValueError as exc:
        raise CardRoundReplayError(
            f"invalid {event.event_type.value} payload at {event.event_id!r}: {exc}"
        ) from exc
    return ModelSOParsedCardRoundEvent(
        event_type=event.event_type,
        match_id=event.match_id,
        correlation_id=event.correlation_id,
        event_id=event.event_id,
        tick=event.tick,
        sequence_in_tick=event.sequence_in_tick,
        message_id=event.envelope.message_id,
        causation_id=event.envelope.causation_id,
        payload=cast(CardRoundPayload, payload),
    )


def _phase(event_type: SOEventType) -> int:
    return _CARD_EVENT_TYPES.index(event_type)


def _typed_payloads(
    events: tuple[ModelSOParsedCardRoundEvent, ...],
) -> _ParsedRound:
    hands: list[ModelSOHandDealtPayload] = []
    plans: list[ModelSOPlanCommittedPayload] = []
    resolved: list[ModelSORegisterResolvedPayload] = []
    discarded: list[ModelSOCardsDiscardedPayload] = []
    for event in events:
        match event.event_type:
            case SOEventType.HAND_DEALT:
                hands.append(cast(ModelSOHandDealtPayload, event.payload))
            case SOEventType.PLAN_COMMITTED:
                plans.append(cast(ModelSOPlanCommittedPayload, event.payload))
            case SOEventType.REGISTER_RESOLVED:
                resolved.append(cast(ModelSORegisterResolvedPayload, event.payload))
            case SOEventType.CARDS_DISCARDED:
                discarded.append(cast(ModelSOCardsDiscardedPayload, event.payload))
    if not hands or not plans or not resolved or not discarded:
        raise CardRoundReplayError(
            "card-round replay requires HAND_DEALT, PLAN_COMMITTED, REGISTER_RESOLVED, "
            "and CARDS_DISCARDED phases"
        )
    return _ParsedRound(
        events=events,
        hand_dealt=tuple(hands),
        plan_committed=tuple(plans),
        register_resolved=tuple(resolved),
        cards_discarded=tuple(discarded),
    )


def _validate_structure(
    parsed: _ParsedRound,
    *,
    snapshot: ModelSOCardRuntimeSnapshot,
    expected_match_id: str | None,
    expected_provenance: ModelSOCardRuntimeProvenance | None,
) -> tuple[str, UUID]:
    expected_deck = snapshot.selected_deck if snapshot.selected_deck_id is not None else None
    split_hands = tuple(hand.partitions is not None for hand in parsed.hand_dealt)
    if any(split_hands) and not all(split_hands):
        raise CardRoundReplayError(
            "card-round replay cannot mix split and single-deck HAND_DEALT values"
        )
    split_runtime = bool(split_hands) and all(split_hands)
    if expected_deck is None and not split_runtime:
        raise CardRoundReplayError("card-round replay requires an explicitly selected deck")
    if expected_provenance is not None and expected_provenance != snapshot.provenance:
        raise CardRoundReplayError("card runtime provenance does not match replay snapshot")

    match_id = expected_match_id or ""
    correlation_id: UUID | None = None
    previous_order: tuple[int, int, str] | None = None
    previous_phase = 0
    previous_messages: set[UUID] = set()
    for index, event in enumerate(parsed.events):
        if expected_match_id is not None and event.match_id != expected_match_id:
            raise CardRoundReplayError("card-round event match_id differs from expected match")
        if index == 0:
            match_id = event.match_id
        elif event.match_id != match_id:
            raise CardRoundReplayError("card-round events must share one match_id")
        if correlation_id is None:
            correlation_id = event.correlation_id
        elif event.correlation_id != correlation_id:
            raise CardRoundReplayError("card-round events must share one correlation_id")
        order = (event.tick, event.sequence_in_tick, event.event_id)
        if previous_order is not None and order <= previous_order:
            raise CardRoundReplayError("card-round events are not in canonical ledger order")
        previous_order = order
        current_phase = _phase(event.event_type)
        if current_phase < previous_phase:
            raise CardRoundReplayError("card-round phases are out of order")
        previous_phase = current_phase
        if index > 0:
            if event.causation_id is None or event.causation_id not in previous_messages:
                raise CardRoundReplayError(
                    "every card event after the root must be caused by an earlier card event"
                )
        previous_messages.add(event.message_id)

    assert correlation_id is not None
    for hand in parsed.hand_dealt:
        if split_runtime:
            if hand.deck_id != SPLIT_DECK_MARKER or hand.partitions is None:
                raise CardRoundReplayError(
                    "split HAND_DEALT values require the deck.split marker and partitions"
                )
            if hand.hand_size != len(hand.card_ids):
                raise CardRoundReplayError("split HAND_DEALT hand_size differs from card_ids")
            partition_cards = (
                (hand.partitions.movement, "movement"),
                (hand.partitions.weapon, "weapon"),
            )
            if sum(len(partition.card_ids) for partition, _ in partition_cards) != hand.hand_size:
                raise CardRoundReplayError(
                    "split HAND_DEALT partitions do not account for the complete hand"
                )
            for partition, partition_name in partition_cards:
                try:
                    deck = snapshot.require_deck(partition.deck_id)
                except (KeyError, ValueError) as exc:
                    raise CardRoundReplayError(
                        f"split HAND_DEALT names unknown {partition_name} deck "
                        f"{partition.deck_id!r}"
                    ) from exc
                if len(partition.card_ids) != partition.requested_count:
                    raise CardRoundReplayError(
                        f"split HAND_DEALT {partition_name} partition count differs from request"
                    )
                declared = Counter(str(card_id) for card_id in deck.card_multiset())
                dealt = Counter(str(card_id) for card_id in partition.card_ids)
                if dealt - declared:
                    raise CardRoundReplayError(
                        f"split HAND_DEALT values exceed {partition_name} deck multiset"
                    )
                for card_id in partition.card_ids:
                    try:
                        snapshot.card_catalog.require(card_id)
                    except CardCatalogError as exc:
                        raise CardRoundReplayError(
                            f"HAND_DEALT names an unknown card {card_id!r}"
                        ) from exc
        else:
            assert expected_deck is not None
            if hand.deck_id != expected_deck.id:
                raise CardRoundReplayError(
                    f"HAND_DEALT deck {hand.deck_id!r} differs from selected deck "
                    f"{expected_deck.id!r}"
                )
            if hand.hand_size != expected_deck.hand_size:
                raise CardRoundReplayError("HAND_DEALT hand_size differs from selected deck")
            for card_id in hand.card_ids:
                try:
                    snapshot.card_catalog.require(card_id)
                except CardCatalogError as exc:
                    raise CardRoundReplayError(
                        f"HAND_DEALT names an unknown card {card_id!r}"
                    ) from exc

    seats = tuple(hand.seat for hand in parsed.hand_dealt)
    if seats != tuple(sorted(seats)) or len(seats) != len(set(seats)):
        raise CardRoundReplayError("HAND_DEALT seats must be unique and ascending")
    if tuple(plan.seat for plan in parsed.plan_committed) != seats:
        raise CardRoundReplayError("PLAN_COMMITTED seats must match HAND_DEALT order")
    if tuple(discard.seat for discard in parsed.cards_discarded) != seats:
        raise CardRoundReplayError("CARDS_DISCARDED seats must match HAND_DEALT order")

    if not split_runtime:
        assert expected_deck is not None
        declared = Counter(str(card_id) for card_id in expected_deck.card_multiset())
        dealt = Counter(str(card_id) for hand in parsed.hand_dealt for card_id in hand.card_ids)
        if dealt - declared:
            raise CardRoundReplayError("HAND_DEALT values exceed the selected deck card multiset")
    hands = {
        hand.seat: Counter(str(card_id) for card_id in hand.card_ids) for hand in parsed.hand_dealt
    }
    for plan in parsed.plan_committed:
        chosen = Counter(str(register.card_id) for register in plan.registers)
        if chosen - hands[plan.seat]:
            raise CardRoundReplayError(f"PLAN_COMMITTED seat {plan.seat!r} uses an absent card")
    seen_registers: set[tuple[str, int]] = set()
    priority_ranks_by_register: dict[int, list[int]] = {}
    seats_by_register: dict[int, set[str]] = {}
    last_register_index = -1
    last_priority_rank = -1
    register_seats: set[str] = set()
    for row in parsed.register_resolved:
        if row.seat not in hands:
            raise CardRoundReplayError(f"REGISTER_RESOLVED names unknown seat {row.seat!r}")
        key = (row.seat, row.register_index)
        if key in seen_registers:
            raise CardRoundReplayError("REGISTER_RESOLVED repeats a seat/register pair")
        seen_registers.add(key)
        register_seats.add(row.seat)
        seats_by_register.setdefault(row.register_index, set()).add(row.seat)
        priority_ranks_by_register.setdefault(row.register_index, []).append(row.priority_rank)
        if row.register_index < last_register_index or (
            row.register_index == last_register_index and row.priority_rank < last_priority_rank
        ):
            raise CardRoundReplayError("REGISTER_RESOLVED rows are out of register/priority order")
        if row.register_index != last_register_index:
            last_priority_rank = -1
        last_register_index = row.register_index
        last_priority_rank = row.priority_rank
        if row.card_id is not None:
            try:
                card = snapshot.card_catalog.require(row.card_id)
            except CardCatalogError as exc:
                raise CardRoundReplayError(
                    f"REGISTER_RESOLVED names an unknown card {row.card_id!r}"
                ) from exc
            if row.action != action_for_card(card).value:
                raise CardRoundReplayError(
                    f"REGISTER_RESOLVED action {row.action!r} does not match card {row.card_id!r}"
                )
            if row.card_id not in hands[row.seat]:
                raise CardRoundReplayError(
                    f"REGISTER_RESOLVED seat {row.seat!r} uses a card absent from its hand"
                )
        if row.outcome is SORegisterOutcome.AUTO_REMAIN and row.card_id is not None:
            raise CardRoundReplayError("AUTO_REMAIN cannot name a card")
        if row.outcome is SORegisterOutcome.AUTO_REMAIN and row.action != "remain":
            raise CardRoundReplayError("AUTO_REMAIN rows must use the remain action")
    for register_index, priority_ranks in priority_ranks_by_register.items():
        emitted_seats = seats_by_register[register_index]
        expected_seats = set(seats)
        if emitted_seats != expected_seats or len(emitted_seats) != len(expected_seats):
            raise CardRoundReplayError(
                "REGISTER_RESOLVED register "
                f"{register_index} seats must match HAND_DEALT seats; "
                f"got {sorted(emitted_seats)!r}, expected {list(seats)!r}"
            )
        expected_ranks = list(range(len(priority_ranks)))
        if priority_ranks != expected_ranks:
            raise CardRoundReplayError(
                "REGISTER_RESOLVED priority_rank values for register "
                f"{register_index} must be unique and contiguous from 0; "
                f"got {priority_ranks!r}"
            )
    if register_seats != set(seats):
        raise CardRoundReplayError("REGISTER_RESOLVED seats must match HAND_DEALT seats")
    for discarded in parsed.cards_discarded:
        if discarded.seat not in hands:
            raise CardRoundReplayError(f"CARDS_DISCARDED names unknown seat {discarded.seat!r}")
        chosen = Counter(str(card_id) for card_id in discarded.card_ids)
        if chosen - hands[discarded.seat]:
            raise CardRoundReplayError(
                f"CARDS_DISCARDED seat {discarded.seat!r} uses an absent card"
            )
    return match_id, correlation_id


def validate_card_round_events(
    events: Sequence[ModelSOEventEnvelope],
    *,
    snapshot: ModelSOCardRuntimeSnapshot,
    expected_match_id: str | None = None,
    expected_provenance: ModelSOCardRuntimeProvenance | None = None,
) -> ModelSOCardRoundReplay:
    """Parse and validate one canonical card-event sequence without side effects."""

    if not isinstance(snapshot, ModelSOCardRuntimeSnapshot):
        raise TypeError("card-round replay requires ModelSOCardRuntimeSnapshot")
    if not events:
        raise CardRoundReplayError("card-round replay requires at least one event")
    parsed_events = tuple(_parse_event(event) for event in events)
    parsed = _typed_payloads(parsed_events)
    match_id, correlation_id = _validate_structure(
        parsed,
        snapshot=snapshot,
        expected_match_id=expected_match_id,
        expected_provenance=expected_provenance,
    )
    cancelled_reasons = {
        discarded.reason.startswith("cancelled:") for discarded in parsed.cards_discarded
    }
    if len(cancelled_reasons) > 1:
        raise CardRoundReplayError(
            "CARDS_DISCARDED reasons must not mix cancelled and committed rows"
        )
    return ModelSOCardRoundReplay(
        match_id=match_id,
        correlation_id=correlation_id,
        deck_id=(
            snapshot.selected_deck.id
            if snapshot.selected_deck_id is not None
            else SPLIT_DECK_MARKER
        ),
        events=parsed.events,
        hand_dealt=parsed.hand_dealt,
        plan_committed=parsed.plan_committed,
        register_resolved=parsed.register_resolved,
        cards_discarded=parsed.cards_discarded,
        cancelled=next(iter(cancelled_reasons), False),
    )


def _card_round_root(
    event: ModelSOEventEnvelope,
    *,
    card_events_by_message: dict[UUID, ModelSOEventEnvelope],
) -> UUID | None:
    """Return the external causation root for one card lifecycle event.

    Card lifecycle events form one causal chain per round while intent events
    may be interleaved in the ledger and are deliberately not part of the
    lifecycle payload batch.  Walking only lifecycle message ids keeps the
    grouping boundary explicit without treating a card intent as a new round.
    """

    root = event.causation_id
    visited: set[UUID] = set()
    while root in card_events_by_message:
        if root in visited:
            raise CardRoundReplayError("card event causation graph contains a cycle")
        visited.add(root)
        parent = card_events_by_message[root]
        root = parent.causation_id
    return root


def _validate_match_started_provenance(
    events: Sequence[ModelSOEventEnvelope],
    *,
    snapshot: ModelSOCardRuntimeSnapshot,
    expected_provenance: ModelSOCardRuntimeProvenance | None,
) -> None:
    """Validate the retained card snapshot against MATCH_STARTED once.

    The engine invokes this stream-level check before prefix folding.  Keeping
    it here also gives live consumers a single validator for the same
    evidence, rather than relying on a fold to notice a drifted start payload.
    """

    started = [event for event in events if event.event_type is SOEventType.MATCH_STARTED]
    if len(started) != 1:
        raise CardRoundReplayError("card-event replay requires exactly one MATCH_STARTED event")
    try:
        payload = ModelSOMatchStartedPayload.model_validate(started[0].payload)
    except ValueError as exc:
        raise CardRoundReplayError("MATCH_STARTED payload is not canonical") from exc
    recorded = payload.card_runtime_provenance
    expected = expected_provenance if expected_provenance is not None else snapshot.provenance
    if expected is None:
        if recorded is not None:
            raise CardRoundReplayError(
                "MATCH_STARTED carries card runtime provenance but snapshot has none"
            )
        return
    if recorded is None or recorded != expected:
        raise CardRoundReplayError("card runtime provenance does not match replay snapshot")


def validate_card_event_stream(
    events: Sequence[ModelSOEventEnvelope],
    *,
    snapshot: ModelSOCardRuntimeSnapshot,
    expected_match_id: str | None = None,
    expected_provenance: ModelSOCardRuntimeProvenance | None = None,
) -> tuple[ModelSOCardRoundReplay, ...]:
    """Validate every complete card round in a canonical match event stream.

    Card lifecycle events can be interleaved with card-produced intents and
    ordinary combat events.  This helper extracts lifecycle events, groups them
    by the stable external causation root, and validates each complete batch
    only after the full ledger list is available.  In particular, it never
    feeds a HAND_DEALT or PLAN_COMMITTED prefix into :func:`parse_card_round_events`.

    An empty lifecycle stream is valid and returns an empty tuple; callers can
    use the same hook for ordinary no-card replays without changing their
    state-fold behavior.
    """

    if not isinstance(snapshot, ModelSOCardRuntimeSnapshot):
        raise TypeError("card-event replay requires ModelSOCardRuntimeSnapshot")
    if not events:
        return ()
    card_events = tuple(event for event in events if event.event_type in _CARD_EVENT_TYPE_SET)
    if not card_events:
        return ()
    _validate_match_started_provenance(
        events,
        snapshot=snapshot,
        expected_provenance=expected_provenance,
    )
    by_message: dict[UUID, ModelSOEventEnvelope] = {}
    for event in card_events:
        message_id = event.envelope.message_id
        if message_id in by_message:
            raise CardRoundReplayError("card lifecycle message ids must be unique")
        by_message[message_id] = event

    grouped: dict[UUID | None, list[ModelSOEventEnvelope]] = {}
    group_order: list[UUID | None] = []
    for event in card_events:
        root = _card_round_root(event, card_events_by_message=by_message)
        if root not in grouped:
            grouped[root] = []
            group_order.append(root)
        grouped[root].append(event)

    replays: list[ModelSOCardRoundReplay] = []
    for root in group_order:
        batch = grouped[root]
        if root is None:
            raise CardRoundReplayError("card round root causation must not be null")
        replay = validate_card_round_events(
            batch,
            snapshot=snapshot,
            expected_match_id=expected_match_id,
            expected_provenance=expected_provenance,
        )
        replays.append(replay)
    return tuple(replays)


parse_card_round_events = validate_card_round_events


__all__ = [
    "CardRoundReplayError",
    "ModelSOCardRoundReplay",
    "ModelSOParsedCardRoundEvent",
    "parse_card_round_events",
    "validate_card_event_stream",
    "validate_card_round_events",
]
