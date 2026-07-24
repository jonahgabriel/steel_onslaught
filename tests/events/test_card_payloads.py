"""Focused contract tests for the four card lifecycle payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    ModelSORegisterResolvedPayload,
    SORegisterFillReason,
    SORegisterOutcome,
)

pytestmark = pytest.mark.unit


_CARDS = ("card.movement.advance", "card.attack.fire_primary")


def test_card_payloads_are_closed_frozen_and_json_round_trippable() -> None:
    payloads = (
        ModelSOHandDealtPayload(
            seat="a",
            deck_id="deck.fixture.standard",
            card_ids=_CARDS,
            hand_size=2,
            deck_remaining=21,
            reshuffled=False,
        ),
        ModelSOPlanCommittedPayload(
            seat="a",
            registers=tuple(
                ModelSOPlanRegister(register_index=index, card_id=card_id)
                for index, card_id in enumerate(_CARDS)
            ),
            rationale="Advance then fire.",
            confidence=0.75,
        ),
        ModelSORegisterResolvedPayload(
            seat="a",
            register_index=0,
            card_id=_CARDS[0],
            action="move",
            outcome=SORegisterOutcome.RESOLVED,
            priority=20,
            priority_rank=0,
            fill_reason=None,
        ),
        ModelSOCardsDiscardedPayload(seat="a", card_ids=(_CARDS[0],), reason="played"),
    )
    for payload in payloads:
        assert payload.model_config["extra"] == "forbid"
        assert payload.model_config["frozen"] is True
        assert type(payload).model_validate(payload.model_dump(mode="json")) == payload
        with pytest.raises(ValidationError):
            type(payload).model_validate({**payload.model_dump(mode="json"), "unknown": True})


def test_hand_dealt_requires_card_count_to_match_hand_size() -> None:
    with pytest.raises(ValidationError, match="hand_size"):
        ModelSOHandDealtPayload(
            seat="a",
            deck_id="deck.fixture.standard",
            card_ids=_CARDS,
            hand_size=5,
            deck_remaining=21,
            reshuffled=False,
        )


def test_register_resolved_auto_remain_has_explicit_fill_reason() -> None:
    payload = ModelSORegisterResolvedPayload(
        seat="b",
        register_index=4,
        card_id=None,
        action="remain",
        outcome=SORegisterOutcome.AUTO_REMAIN,
        priority=0,
        priority_rank=3,
        fill_reason=SORegisterFillReason.SHORT_DECK,
    )
    assert payload.model_dump(mode="json")["fill_reason"] == "short_deck"

    with pytest.raises(ValidationError, match="fill_reason"):
        ModelSORegisterResolvedPayload.model_validate(
            {
                "seat": "b",
                "register_index": 4,
                "card_id": None,
                "action": "remain",
                "outcome": SORegisterOutcome.AUTO_REMAIN,
                "priority": 0,
                "priority_rank": 3,
            }
        )


def test_plan_committed_rejects_duplicate_register_indexes() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ModelSOPlanCommittedPayload(
            seat="a",
            registers=(
                ModelSOPlanRegister(register_index=0, card_id=_CARDS[0]),
                ModelSOPlanRegister(register_index=0, card_id=_CARDS[1]),
            ),
            rationale=None,
            confidence=0.5,
        )


def test_discard_requires_at_least_one_card_and_resolved_requires_card() -> None:
    with pytest.raises(ValidationError, match="card_ids"):
        ModelSOCardsDiscardedPayload(seat="a", card_ids=(), reason="played")
    with pytest.raises(ValidationError, match="require a card"):
        ModelSORegisterResolvedPayload(
            seat="a",
            register_index=0,
            card_id=None,
            action="move",
            outcome=SORegisterOutcome.RESOLVED,
            priority=20,
            priority_rank=0,
            fill_reason=None,
        )


def test_nullable_wire_fields_are_required_explicitly() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        ModelSOPlanCommittedPayload.model_validate(
            {"seat": "a", "registers": (), "confidence": 0.5}
        )
    with pytest.raises(ValidationError, match="card_id"):
        ModelSORegisterResolvedPayload.model_validate(
            {
                "seat": "a",
                "register_index": 0,
                "action": "remain",
                "outcome": SORegisterOutcome.AUTO_REMAIN,
                "priority": 0,
                "priority_rank": 0,
                "fill_reason": SORegisterFillReason.SHORT_DECK,
            }
        )


def test_card_ids_use_the_canonical_card_id_contract() -> None:
    with pytest.raises(ValidationError, match="card_id"):
        ModelSOPlanRegister(register_index=0, card_id="not-a-card-id")


def test_spatial_read_defaults_to_none_for_non_scaffold_arms() -> None:
    """An arm that never asks for a spatial read gets an explicit null, not a
    dropped key -- the payload validates old events (key absent) and new
    non-scaffold events (key present, null) identically."""
    payload = ModelSOPlanCommittedPayload(
        seat="a",
        registers=tuple(
            ModelSOPlanRegister(register_index=index, card_id=card_id)
            for index, card_id in enumerate(_CARDS)
        ),
        rationale="Advance then fire.",
        confidence=0.75,
    )
    assert payload.spatial_read is None
    dumped = payload.model_dump(mode="json")
    assert dumped["spatial_read"] is None
    # A legacy event persisted before the field existed carries no key at all.
    legacy = dict(dumped)
    del legacy["spatial_read"]
    assert ModelSOPlanCommittedPayload.model_validate(legacy).spatial_read is None


def test_spatial_read_round_trips_for_the_grid_scaffold_arm() -> None:
    payload = ModelSOPlanCommittedPayload(
        seat="a",
        registers=tuple(
            ModelSOPlanRegister(register_index=index, card_id=card_id)
            for index, card_id in enumerate(_CARDS)
        ),
        rationale="Advance then fire.",
        confidence=0.75,
        spatial_read="clear line of sight, no cover nearby",
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["spatial_read"] == "clear line of sight, no cover nearby"
    assert ModelSOPlanCommittedPayload.model_validate(dumped) == payload


def test_plan_register_rejects_nested_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="unknown"):
        ModelSOPlanCommittedPayload.model_validate(
            {
                "seat": "a",
                "registers": [
                    {
                        "register_index": 0,
                        "card_id": _CARDS[0],
                        "unknown": True,
                    }
                ],
                "rationale": None,
                "confidence": 0.5,
            }
        )
