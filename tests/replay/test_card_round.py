"""Pure card-round wire parser and phase FSM proofs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest

from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeProvenance,
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.events.card_payloads import (
    SPLIT_DECK_MARKER,
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOHandPartitionPayload,
    ModelSOHandPartitionsPayload,
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    ModelSORegisterResolvedPayload,
    SOCardPartition,
    SORegisterOutcome,
)
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    make_event,
)
from steel_onslaught.replay.card_round import (
    CardRoundReplayError,
    parse_card_round_events,
)

pytestmark = pytest.mark.unit

_MATCH_ID = "match.test.card-replay"
_CORRELATION = UUID("11111111-1111-4111-8111-111111111111")
_SUBJECT = ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a")
_NOW = datetime(2026, 7, 18, tzinfo=UTC)


def _snapshot(*, register_count: int = 1) -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.advance",
                display_name="Advance",
                category=SOCardCategory.MOVEMENT,
                priority=10,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.attack",
                display_name="Attack",
                category=SOCardCategory.ATTACK,
                priority=20,
                heat_cost=0,
                effect=ModelSOCardEffect(weapon_slot=0),
            ),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.replay",
        display_name="Replay deck",
        hand_size=2,
        register_count=register_count,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=2) for card in cards.cards),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _events() -> list[ModelSOEventEnvelope]:
    hand = ModelSOHandDealtPayload(
        seat="a",
        deck_id="deck.test.replay",
        card_ids=("card.test.advance", "card.test.attack"),
        hand_size=2,
        deck_remaining=2,
        reshuffled=False,
    )
    plan = ModelSOPlanCommittedPayload(
        seat="a",
        registers=(ModelSOPlanRegister(register_index=0, card_id="card.test.advance"),),
        rationale="advance",
        confidence=1.0,
    )
    resolved = ModelSORegisterResolvedPayload(
        seat="a",
        register_index=0,
        card_id="card.test.advance",
        action="move",
        outcome=SORegisterOutcome.RESOLVED,
        priority=10,
        priority_rank=0,
        fill_reason=None,
    )
    discarded = ModelSOCardsDiscardedPayload(
        seat="a",
        card_ids=hand.card_ids,
        reason="end_of_round",
    )
    payloads = (hand, plan, resolved, discarded)
    types = (
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    )
    events = []
    previous: UUID | None = None
    for index, (event_type, payload) in enumerate(zip(types, payloads, strict=True), start=1):
        event = make_event(
            match_id=_MATCH_ID,
            tick=1,
            sequence_in_tick=index,
            event_type=event_type,
            producer_node="node.test.card-replay",
            subject=_SUBJECT,
            payload=payload.model_dump(mode="json"),
            correlation_id=_CORRELATION,
            causation_id=previous,
            event_id=f"01JTEST{index:019d}",
            message_id=UUID(int=index),
            emitted_at=_NOW,
        )
        events.append(event)
        previous = event.envelope.message_id
    return events


def _split_snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = _snapshot().card_catalog
    movement = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.movement",
        display_name="Movement deck",
        hand_size=1,
        register_count=1,
        cards=(ModelSODeckEntry(card_id="card.test.advance", count=2),),
    )
    weapon = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.weapon",
        display_name="Weapon deck",
        hand_size=1,
        register_count=1,
        cards=(ModelSODeckEntry(card_id="card.test.attack", count=2),),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(movement, weapon),
        selected_deck_id=None,
        content_sha256=canonical_card_runtime_sha256(cards, (movement, weapon)),
    )


def _split_events() -> list[ModelSOEventEnvelope]:
    events = _events()
    hand = ModelSOHandDealtPayload.model_validate(events[0].payload).model_copy(
        update={
            "deck_id": SPLIT_DECK_MARKER,
            "register_count": 1,
            "partitions": ModelSOHandPartitionsPayload(
                movement=ModelSOHandPartitionPayload(
                    partition=SOCardPartition.MOVEMENT,
                    deck_id="deck.test.movement",
                    card_ids=("card.test.advance",),
                    requested_count=1,
                    deck_remaining=1,
                    reshuffled=False,
                ),
                weapon=ModelSOHandPartitionPayload(
                    partition=SOCardPartition.WEAPON,
                    deck_id="deck.test.weapon",
                    card_ids=("card.test.attack",),
                    requested_count=1,
                    deck_remaining=1,
                    reshuffled=False,
                ),
            ),
        }
    )
    events[0] = events[0].model_copy(update={"payload": hand.model_dump(mode="json")})
    return events


def _two_seat_events(priority_ranks: tuple[int, int]) -> list[ModelSOEventEnvelope]:
    """Build one-register events with caller-controlled resolution ranks."""
    hands = (
        ModelSOHandDealtPayload(
            seat="a",
            deck_id="deck.test.replay",
            card_ids=("card.test.advance", "card.test.attack"),
            hand_size=2,
            deck_remaining=0,
            reshuffled=False,
        ),
        ModelSOHandDealtPayload(
            seat="b",
            deck_id="deck.test.replay",
            card_ids=("card.test.advance", "card.test.attack"),
            hand_size=2,
            deck_remaining=0,
            reshuffled=False,
        ),
    )
    plans = tuple(
        ModelSOPlanCommittedPayload(
            seat=hand.seat,
            registers=(ModelSOPlanRegister(register_index=0, card_id="card.test.advance"),),
            rationale="advance",
            confidence=1.0,
        )
        for hand in hands
    )
    # The producer emits rows in priority order.  The exact rank values are
    # intentionally injectable so malformed skipped/duplicate streams can be
    # exercised without bypassing the canonical payload models.
    resolutions = (
        ModelSORegisterResolvedPayload(
            seat="b",
            register_index=0,
            card_id="card.test.advance",
            action="move",
            outcome=SORegisterOutcome.RESOLVED,
            priority=10,
            priority_rank=priority_ranks[0],
            fill_reason=None,
        ),
        ModelSORegisterResolvedPayload(
            seat="a",
            register_index=0,
            card_id="card.test.advance",
            action="move",
            outcome=SORegisterOutcome.RESOLVED,
            priority=10,
            priority_rank=priority_ranks[1],
            fill_reason=None,
        ),
    )
    discarded = tuple(
        ModelSOCardsDiscardedPayload(
            seat=hand.seat,
            card_ids=hand.card_ids,
            reason="end_of_round",
        )
        for hand in hands
    )
    payloads = (*hands, *plans, *resolutions, *discarded)
    types = (
        SOEventType.HAND_DEALT,
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
        SOEventType.CARDS_DISCARDED,
    )
    events = []
    previous: UUID | None = None
    for index, (event_type, payload) in enumerate(zip(types, payloads, strict=True), start=1):
        event = make_event(
            match_id=_MATCH_ID,
            tick=1,
            sequence_in_tick=index,
            event_type=event_type,
            producer_node="node.test.card-replay",
            subject=_SUBJECT,
            payload=payload.model_dump(mode="json"),
            correlation_id=_CORRELATION,
            causation_id=previous,
            event_id=f"01JTEST{index:019d}",
            message_id=UUID(int=index),
            emitted_at=_NOW,
        )
        events.append(event)
        previous = event.envelope.message_id
    return events


def _multi_register_events(
    *, omit_second_register_seat: bool = False, cancelled: bool = False
) -> list[ModelSOEventEnvelope]:
    """Build two-seat, two-register lifecycle events.

    A cancelled paced round may contain only the complete registers emitted
    before the terminal boundary.  The malformed variant intentionally keeps
    register zero complete while omitting seat ``a`` from register one, which
    must not pass validation merely because that seat appeared in another
    register.
    """
    hands = tuple(
        ModelSOHandDealtPayload(
            seat=seat,
            deck_id="deck.test.replay",
            card_ids=("card.test.advance", "card.test.attack"),
            hand_size=2,
            deck_remaining=0,
            reshuffled=False,
        )
        for seat in ("a", "b")
    )
    plans = tuple(
        ModelSOPlanCommittedPayload(
            seat=hand.seat,
            registers=(
                ModelSOPlanRegister(register_index=0, card_id="card.test.advance"),
                ModelSOPlanRegister(register_index=1, card_id="card.test.attack"),
            ),
            rationale="advance then attack",
            confidence=1.0,
        )
        for hand in hands
    )
    resolutions = [
        ModelSORegisterResolvedPayload(
            seat="b",
            register_index=0,
            card_id="card.test.advance",
            action="move",
            outcome=SORegisterOutcome.RESOLVED,
            priority=10,
            priority_rank=0,
            fill_reason=None,
        ),
        ModelSORegisterResolvedPayload(
            seat="a",
            register_index=0,
            card_id="card.test.advance",
            action="move",
            outcome=SORegisterOutcome.RESOLVED,
            priority=10,
            priority_rank=1,
            fill_reason=None,
        ),
        ModelSORegisterResolvedPayload(
            seat="b",
            register_index=1,
            card_id="card.test.attack",
            action="fire_weapon",
            outcome=SORegisterOutcome.RESOLVED,
            priority=20,
            priority_rank=0,
            fill_reason=None,
        ),
        ModelSORegisterResolvedPayload(
            seat="a",
            register_index=1,
            card_id="card.test.attack",
            action="fire_weapon",
            outcome=SORegisterOutcome.RESOLVED,
            priority=20,
            priority_rank=1,
            fill_reason=None,
        ),
    ]
    if omit_second_register_seat:
        resolutions.pop()
    if cancelled:
        resolutions = resolutions[:2]
    reason = "cancelled:max_ticks" if cancelled else "end_of_round"
    discarded = tuple(
        ModelSOCardsDiscardedPayload(seat=hand.seat, card_ids=hand.card_ids, reason=reason)
        for hand in hands
    )
    payloads = (*hands, *plans, *resolutions, *discarded)
    types = (
        *(SOEventType.HAND_DEALT for _ in hands),
        *(SOEventType.PLAN_COMMITTED for _ in plans),
        *(SOEventType.REGISTER_RESOLVED for _ in resolutions),
        *(SOEventType.CARDS_DISCARDED for _ in discarded),
    )
    events = []
    previous: UUID | None = None
    for index, (event_type, payload) in enumerate(zip(types, payloads, strict=True), start=1):
        event = make_event(
            match_id=_MATCH_ID,
            tick=1,
            sequence_in_tick=index,
            event_type=event_type,
            producer_node="node.test.card-replay",
            subject=_SUBJECT,
            payload=payload.model_dump(mode="json"),
            correlation_id=_CORRELATION,
            causation_id=previous,
            event_id=f"01JTEST{index:019d}",
            message_id=UUID(int=index),
            emitted_at=_NOW,
        )
        events.append(event)
        previous = event.envelope.message_id
    return events


def _swap(events: list[ModelSOEventEnvelope]) -> list[ModelSOEventEnvelope]:
    return [events[1], events[0], events[2], events[3]]


def _wrong_match(events: list[ModelSOEventEnvelope]) -> list[ModelSOEventEnvelope]:
    return [events[0].model_copy(update={"match_id": "match.other"}), *events[1:]]


def _unknown_payload(events: list[ModelSOEventEnvelope]) -> list[ModelSOEventEnvelope]:
    return [events[0].model_copy(update={"payload": {"unknown": True}}), *events[1:]]


def _missing_causation(events: list[ModelSOEventEnvelope]) -> list[ModelSOEventEnvelope]:
    envelope = events[1].envelope.model_copy(update={"causation_id": None})
    return [events[0], events[1].model_copy(update={"envelope": envelope}), *events[2:]]


def test_parser_strictly_validates_four_phases_and_provenance() -> None:
    snapshot = _snapshot()
    replay = parse_card_round_events(
        _events(),
        snapshot=snapshot,
        expected_match_id=_MATCH_ID,
        expected_provenance=ModelSOCardRuntimeProvenance(
            schema_version="0.1.0",
            kind="steel_onslaught.card_runtime_provenance",
            deck_id=snapshot.selected_deck.id,
            content_sha256=snapshot.content_sha256,
        ),
    )
    assert replay.match_id == _MATCH_ID
    assert replay.deck_id == "deck.test.replay"
    assert [event.event_type for event in replay.events] == [
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    ]
    assert replay.hand_dealt[0].card_ids == replay.cards_discarded[0].card_ids


def test_parser_validates_split_round_without_selected_deck() -> None:
    replay = parse_card_round_events(
        _split_events(),
        snapshot=_split_snapshot(),
        expected_match_id=_MATCH_ID,
    )

    assert replay.deck_id == SPLIT_DECK_MARKER
    assert replay.cancelled is False


@pytest.mark.parametrize(
    "mutate",
    [_swap, _wrong_match, _unknown_payload, _missing_causation],
)
def test_parser_rejects_phase_order_match_payload_and_causation_drift(
    mutate: Callable[[list[ModelSOEventEnvelope]], list[ModelSOEventEnvelope]],
) -> None:
    events = _events()
    changed = mutate(events)
    with pytest.raises(CardRoundReplayError):
        parse_card_round_events(changed, snapshot=_snapshot(), expected_match_id=_MATCH_ID)


def test_parser_rejects_unknown_deck_and_provenance_mismatch() -> None:
    snapshot = _snapshot()
    unknown_deck = _events()[0].model_copy(
        update={"payload": {**_events()[0].payload, "deck_id": "deck.unknown"}}
    )
    with pytest.raises(CardRoundReplayError, match="selected deck"):
        parse_card_round_events(
            [unknown_deck, *_events()[1:]], snapshot=snapshot, expected_match_id=_MATCH_ID
        )
    bad_provenance = ModelSOCardRuntimeProvenance(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_provenance",
        deck_id=snapshot.selected_deck.id,
        content_sha256="0" * 64,
    )
    with pytest.raises(CardRoundReplayError, match="provenance"):
        parse_card_round_events(_events(), snapshot=snapshot, expected_provenance=bad_provenance)


@pytest.mark.parametrize(
    "priority_ranks",
    [
        (0, 2),
        (0, 0),
    ],
    ids=("skipped", "duplicate"),
)
def test_parser_rejects_skipped_or_duplicate_priority_ranks(
    priority_ranks: tuple[int, int],
) -> None:
    """Each register's ranks must match the producer's ``enumerate`` output."""
    with pytest.raises(CardRoundReplayError, match="priority_rank") as exc_info:
        parse_card_round_events(
            _two_seat_events(priority_ranks),
            snapshot=_snapshot(),
            expected_match_id=_MATCH_ID,
        )
    assert f"got {list(priority_ranks)!r}" in str(exc_info.value)


def test_parser_rejects_register_with_an_omitted_hand_seat() -> None:
    """Every emitted register must contain one row for every dealt seat."""
    with pytest.raises(CardRoundReplayError, match="register 1 seats"):
        parse_card_round_events(
            _multi_register_events(omit_second_register_seat=True),
            snapshot=_snapshot(register_count=2),
            expected_match_id=_MATCH_ID,
        )


@pytest.mark.parametrize("cancelled", [False, True], ids=["committed", "paced-cancelled"])
def test_parser_accepts_complete_emitted_registers_and_cancellation_prefix(
    cancelled: bool,
) -> None:
    replay = parse_card_round_events(
        _multi_register_events(cancelled=cancelled),
        snapshot=_snapshot(register_count=2),
        expected_match_id=_MATCH_ID,
    )
    assert replay.cancelled is cancelled
    assert len(replay.register_resolved) == (2 if cancelled else 4)
