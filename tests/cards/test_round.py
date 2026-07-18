"""Pure card-round value and replay-honesty tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope, ModelSODeckState
from steel_onslaught.cards.registers import ModelSOSeatResolutionContext
from steel_onslaught.cards.round import (
    CardRoundReplayDriftError,
    CardRoundRuntime,
    CardRoundValidationError,
    ModelSOCardRoundSequence,
    build_discarded,
    validate_card_round,
)
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SORegisterFillReason,
    SORegisterOutcome,
)

pytestmark = pytest.mark.unit


def _card(card_id: str, category: SOCardCategory, priority: int) -> ModelSOCard:
    effect = (
        ModelSOCardEffect(direction="toward_enemy", speed="full")
        if category is SOCardCategory.MOVEMENT
        else ModelSOCardEffect()
    )
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=category,
        priority=priority,
        heat_cost=0,
        effect=effect,
    )


def _runtime(*, selected: str | None = "deck.test.round") -> CardRoundRuntime:
    cards = ModelSOCardCatalog(
        cards=(
            _card("card.test.advance", SOCardCategory.MOVEMENT, 20),
            _card("card.test.advance_alt", SOCardCategory.MOVEMENT, 10),
            _card("card.test.vent", SOCardCategory.VENT, 5),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.round",
        display_name="Round test",
        hand_size=3,
        register_count=2,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=2) for card in cards.cards),
    )
    snapshot = ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=selected,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )
    from steel_onslaught.cards.registers import RegisterExecutionReducer

    return CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=DealerCompute(),
        reducer=RegisterExecutionReducer(cards),
        round_length=3,
    )


def _scope(seat: str) -> ModelSODealerScope:
    return ModelSODealerScope(match_id="match.test.01", match_seed=41, tick=0, seat=seat)


def _plan(seat: str, first: str, second: str) -> ModelSOPlanCommittedPayload:
    return ModelSOPlanCommittedPayload(
        seat=seat,
        registers=(
            ModelSOPlanRegister(register_index=0, card_id=first),
            ModelSOPlanRegister(register_index=1, card_id=second),
        ),
        rationale=None,
        confidence=1.0,
    )


def test_runtime_derives_typed_four_value_sequence_in_canonical_order() -> None:
    runtime = _runtime()
    deal_b = runtime.deal(scope=_scope("b"))
    deal_a = runtime.deal(scope=_scope("a"))
    plan_a = _plan("a", str(deal_a.hand[0]), str(deal_a.hand[1]))
    plan_b = _plan("b", str(deal_b.hand[0]), str(deal_b.hand[1]))
    context_a = ModelSOSeatResolutionContext(
        seat="a",
        register_count=2,
        initiative=5,
        plan=plan_a,
    )
    context_b = ModelSOSeatResolutionContext(
        seat="b",
        register_count=2,
        initiative=10,
        plan=plan_b,
    )

    sequence = runtime.sequence(
        deals=(deal_b, deal_a),
        contexts=(context_b, context_a),
    )

    assert tuple(value.seat for value in sequence.hand_dealt) == ("a", "b")
    assert tuple(value.seat for value in sequence.plan_committed) == ("a", "b")
    assert tuple(value.seat for value in sequence.cards_discarded) == ("a", "b")
    assert len(sequence.register_resolved) == 6  # 3 round slots x 2 seats
    assert [row.register_index for row in sequence.register_resolved] == [0, 0, 1, 1, 2, 2]
    assert sequence.register_resolved[-1].outcome is SORegisterOutcome.AUTO_REMAIN
    assert sequence.register_resolved[-1].fill_reason is SORegisterFillReason.SHORT_DECK
    assert sequence.register_resolved[-1].card_id is None
    assert sequence.values[:2] == sequence.hand_dealt
    runtime.verify_replay(sequence)


def test_round_values_are_byte_stable_under_input_permutation() -> None:
    runtime = _runtime()
    deal_a = runtime.deal(scope=_scope("a"))
    deal_b = runtime.deal(scope=_scope("b"))
    context_a = ModelSOSeatResolutionContext(
        seat="a",
        register_count=2,
        initiative=1,
        plan=_plan("a", str(deal_a.hand[0]), str(deal_a.hand[1])),
    )
    context_b = ModelSOSeatResolutionContext(
        seat="b",
        register_count=2,
        initiative=1,
        plan=_plan("b", str(deal_b.hand[0]), str(deal_b.hand[1])),
    )
    first = runtime.sequence(deals=(deal_a, deal_b), contexts=(context_a, context_b))
    second = runtime.sequence(deals=(deal_b, deal_a), contexts=(context_b, context_a))
    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_deal_validation_preserves_reshuffle_truth_after_discard_reuse() -> None:
    runtime = _runtime()
    cards = runtime.snapshot.selected_deck.card_multiset()
    state = ModelSODeckState(draw_pile=(cards[0],), discard_pile=cards[1:])
    deal = runtime.deal(scope=_scope("a"), state=state)
    assert deal.payload.reshuffled is True
    assert len(deal.hand) == runtime.snapshot.selected_deck.hand_size


def test_heat_lock_repeats_previous_card_and_is_not_short_deck() -> None:
    runtime = _runtime()
    deal = runtime.deal(scope=_scope("a"))
    current = _plan("a", str(deal.hand[0]), str(deal.hand[1]))
    previous = _plan("a", str(deal.hand[1]), str(deal.hand[0]))
    context = ModelSOSeatResolutionContext(
        seat="a",
        register_count=2,
        initiative=1,
        lock_depth=1,
        plan=ModelSOPlanCommittedPayload(
            seat="a",
            registers=(
                ModelSOPlanRegister(register_index=0, card_id=current.registers[0].card_id),
            ),
            rationale=None,
            confidence=1.0,
        ),
        previous_plan=previous,
    )
    sequence = runtime.sequence(deals=(deal,), contexts=(context,))
    locked = sequence.register_resolved[1]
    assert locked.outcome is SORegisterOutcome.HEAT_LOCKED
    assert locked.card_id == previous.registers[1].card_id
    assert locked.fill_reason is None


def test_replay_drift_is_loud_and_unknown_cards_never_discard() -> None:
    runtime = _runtime()
    deal = runtime.deal(scope=_scope("a"))
    plan = _plan("a", str(deal.hand[0]), str(deal.hand[1]))
    context = ModelSOSeatResolutionContext(seat="a", register_count=2, initiative=1, plan=plan)
    sequence = runtime.sequence(deals=(deal,), contexts=(context,))
    tampered = sequence.model_copy(
        update={
            "register_resolved": (
                sequence.register_resolved[0].model_copy(
                    update={"priority": sequence.register_resolved[0].priority + 1}
                ),
                *sequence.register_resolved[1:],
            )
        }
    )
    with pytest.raises(CardRoundReplayDriftError, match="drift"):
        runtime.verify_replay(tampered)
    with pytest.raises(CardRoundValidationError, match="absent"):
        build_discarded(deal.payload, card_ids=("card.test.missing",))


def test_discard_subset_is_explicit_and_must_conserve_hand_multiplicity() -> None:
    runtime = _runtime()
    deal = runtime.deal(scope=_scope("a"))
    discarded = build_discarded(
        deal.payload,
        card_ids=(deal.hand[0],),
        reason="played",
    )
    assert discarded.card_ids == (deal.hand[0],)
    with pytest.raises(CardRoundValidationError, match="absent"):
        build_discarded(deal.payload, card_ids=("card.test.advance",) * 4)


def test_sequence_model_rejects_noncanonical_order_and_unknown_fields() -> None:
    runtime = _runtime()
    deal = runtime.deal(scope=_scope("a"))
    plan = _plan("a", str(deal.hand[0]), str(deal.hand[1]))
    context = ModelSOSeatResolutionContext(seat="a", register_count=2, initiative=1, plan=plan)
    sequence = runtime.sequence(deals=(deal,), contexts=(context,))
    raw = sequence.model_dump(mode="json")
    raw["unknown"] = True
    with pytest.raises(ValidationError, match="extra"):
        ModelSOCardRoundSequence.model_validate(raw)

    duplicate_raw = sequence.model_dump(mode="python")
    duplicate_raw["hand_dealt"] = (
        duplicate_raw["hand_dealt"][0],
        duplicate_raw["hand_dealt"][0],
    )
    with pytest.raises(ValidationError, match="unique"):
        ModelSOCardRoundSequence.model_validate(duplicate_raw)

    unknown_deck = sequence.model_copy(
        update={
            "hand_dealt": (
                sequence.hand_dealt[0].model_copy(update={"deck_id": "deck.test.missing"}),
            )
        }
    )
    with pytest.raises(CardRoundValidationError, match="unknown card-round deck"):
        validate_card_round(unknown_deck, runtime.snapshot, runtime.reducer)
