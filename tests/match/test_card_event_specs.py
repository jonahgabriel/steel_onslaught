"""Pure card event-spec builder proofs."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import pytest

from steel_onslaught.cards.actions import compile_card_action
from steel_onslaught.cards.dealer import ModelSODeckState
from steel_onslaught.cards.registers import ModelSOSeatResolutionContext, RegisterExecutionReducer
from steel_onslaught.cards.round import ModelSOCardRoundSequence
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SORegisterOutcome,
)
from steel_onslaught.events.envelope import ModelSOEventSubject, SOEventType
from steel_onslaught.events.payloads import ModelSOMoveIntentPayload
from steel_onslaught.match.card_adapter import (
    ModelSOCardIntentProjection,
    ModelSOCardRoundEmission,
    ModelSOCardRoundValue,
)
from steel_onslaught.match.card_event_specs import (
    CardRoundEventSpecError,
    build_card_round_event_specs,
)

pytestmark = pytest.mark.unit

_ROOT = UUID("11111111-1111-4111-8111-111111111111")
_IDS = tuple(UUID(int=index) for index in range(10, 15))


def _emission() -> ModelSOCardRoundEmission:
    card = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.test.advance",
        display_name="Advance",
        category=SOCardCategory.MOVEMENT,
        priority=10,
        heat_cost=0,
        effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
    )
    cards = ModelSOCardCatalog(cards=(card,))
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.spec",
        display_name="Spec deck",
        hand_size=1,
        register_count=1,
        cards=(ModelSODeckEntry(card_id=card.id, count=1),),
    )
    plan = ModelSOPlanCommittedPayload(
        seat="a",
        registers=(ModelSOPlanRegister(register_index=0, card_id=card.id),),
        rationale=None,
        confidence=1.0,
    )
    hand = ModelSOHandDealtPayload(
        seat="a",
        deck_id=deck.id,
        card_ids=(card.id,),
        hand_size=1,
        deck_remaining=0,
        reshuffled=False,
    )
    context = ModelSOSeatResolutionContext(
        seat="a",
        register_count=1,
        initiative=0,
        plan=plan,
    )
    resolved = RegisterExecutionReducer(cards).resolve_round((context,), 1)
    discarded = ModelSOCardsDiscardedPayload(seat="a", card_ids=(card.id,), reason="played")
    sequence = ModelSOCardRoundSequence(
        schema_version="0.1.0",
        kind="steel_onslaught.card_round_sequence",
        round_length=1,
        hand_dealt=(hand,),
        plan_committed=(plan,),
        register_resolved=resolved,
        cards_discarded=(discarded,),
        contexts=(context,),
    )
    translation = compile_card_action(card)
    action = ModelSOCardIntentProjection(
        seat="a",
        register_index=0,
        card_id=card.id,
        action=translation.action,
        translation=translation,
        event_type=SOEventType.MOVE_INTENT,
        payload=ModelSOMoveIntentPayload(direction="toward_enemy", speed="full"),
        outcome=SORegisterOutcome.RESOLVED,
    )
    values = (
        ModelSOCardRoundValue(
            stage="HAND_DEALT",
            ordinal=0,
            seat="a",
            value_id="round:hand",
            caused_by="round",
            payload=hand,
        ),
        ModelSOCardRoundValue(
            stage="PLAN_COMMITTED",
            ordinal=1,
            seat="a",
            value_id="round:plan",
            caused_by="round:hand",
            payload=plan,
        ),
        ModelSOCardRoundValue(
            stage="REGISTER_RESOLVED",
            ordinal=2,
            seat="a",
            value_id="round:register",
            caused_by="round:plan",
            payload=resolved[0],
        ),
        ModelSOCardRoundValue(
            stage="CARDS_DISCARDED",
            ordinal=3,
            seat="a",
            value_id="round:discard",
            caused_by="round:register",
            payload=discarded,
        ),
    )
    return ModelSOCardRoundEmission(
        registers_enabled=True,
        round_index=0,
        tick=3,
        causation_id="round.test",
        values=values,
        actions=(action,),
        sequence=sequence,
        deck_state=ModelSODeckState(draw_pile=(), discard_pile=(card.id,)),
    )


def _subjects() -> Mapping[str, ModelSOEventSubject]:
    return {"a": ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a")}


def test_builder_maps_values_and_actions_with_explicit_uuid_chain() -> None:
    specs = build_card_round_event_specs(
        _emission(),
        root_causation_id=_ROOT,
        seat_subjects=_subjects(),
        message_ids=_IDS,
    )
    assert [spec.event_type for spec in specs] == [
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.MOVE_INTENT,
        SOEventType.CARDS_DISCARDED,
    ]
    assert specs[0].causation_id == _ROOT
    assert specs[1].causation_id == specs[0].message_id
    assert specs[3].causation_id == specs[2].message_id
    assert all(spec.subject == _subjects()["a"] for spec in specs)
    assert specs[3].payload == ModelSOMoveIntentPayload(direction="toward_enemy", speed="full")


def test_builder_rejects_missing_subject_or_uuid_count_and_suppressed_output() -> None:
    with pytest.raises(CardRoundEventSpecError, match="message_ids"):
        build_card_round_event_specs(
            _emission(),
            root_causation_id=_ROOT,
            seat_subjects=_subjects(),
            message_ids=_IDS[:-1],
        )
    with pytest.raises(CardRoundEventSpecError, match="subject"):
        build_card_round_event_specs(
            _emission(),
            root_causation_id=_ROOT,
            seat_subjects={},
            message_ids=_IDS,
        )
    suppressed = ModelSOCardRoundEmission(
        registers_enabled=False,
        round_index=0,
        tick=3,
        causation_id="round.suppressed",
        suppressed_reason="registers_disabled",
    )
    with pytest.raises(CardRoundEventSpecError, match="suppressed"):
        build_card_round_event_specs(
            suppressed,
            root_causation_id=_ROOT,
            seat_subjects={},
            message_ids=(_IDS[0],),
        )
