"""Pure contract and allowlist tests for card-programming rule plugins."""

from __future__ import annotations

import pytest

from steel_onslaught.cards.rules import (
    CardProgrammingRuleError,
    CardProgrammingRuleRegistry,
    EnsureMovementCardRuleHandler,
    PreferAttackCardsRuleHandler,
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
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import (
    ModelSOProgrammingObservation,
    program_for_seat,
)
from tests.cards.test_programming import _observation

pytestmark = pytest.mark.unit


def _fire_snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.advance",
                display_name="advance",
                category=SOCardCategory.MOVEMENT,
                priority=20,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.advance_alt",
                display_name="advance alt",
                category=SOCardCategory.MOVEMENT,
                priority=15,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="right", speed="full"),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.fire",
                display_name="fire",
                category=SOCardCategory.ATTACK,
                priority=5,
                heat_cost=4,
                effect=ModelSOCardEffect(weapon_slot=0),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id="card.test.vent",
                display_name="vent",
                category=SOCardCategory.VENT,
                priority=10,
                heat_cost=0,
                effect=ModelSOCardEffect(),
            ),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.rules",
        display_name="rules",
        hand_size=3,
        register_count=3,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in cards.cards),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def test_prefer_attack_handler_replaces_only_available_non_attack_slots() -> None:
    observation = _observation(
        _fire_snapshot(),
        hand=("card.test.advance", "card.test.fire", "card.test.vent", "card.test.advance_alt"),
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.test.advance"),
            ModelSOPlanRegister(register_index=1, card_id="card.test.vent"),
            ModelSOPlanRegister(register_index=2, card_id="card.test.advance_alt"),
        ),
        rationale="llm",
        confidence=0.7,
    )
    handler = PreferAttackCardsRuleHandler()
    result = handler.apply(observation, proposed)

    assert tuple(register.card_id for register in result.registers) == (
        "card.test.fire",
        "card.test.vent",
        "card.test.advance_alt",
    )
    assert result.rationale == "llm; rule:prefer_attack_cards"

    class ProposedProgrammer:
        def program(self, _observation):  # type: ignore[no-untyped-def]
            return proposed

    planned = program_for_seat(ProposedProgrammer(), observation, rule_handlers=(handler,))
    assert tuple(register.card_id for register in planned.registers) == (
        "card.test.fire",
        "card.test.vent",
        "card.test.advance_alt",
    )


def test_ensure_movement_handler_replaces_only_the_last_slot_when_missing() -> None:
    observation = _observation(
        _fire_snapshot(),
        hand=("card.test.fire", "card.test.vent", "card.test.advance", "card.test.advance_alt"),
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.test.fire"),
            ModelSOPlanRegister(register_index=1, card_id="card.test.vent"),
        ),
        rationale="llm",
        confidence=0.7,
    )

    result = EnsureMovementCardRuleHandler().apply(observation, proposed)

    assert tuple(register.card_id for register in result.registers) == (
        "card.test.fire",
        "card.test.advance",
    )
    assert result.rationale == "llm; rule:ensure_movement_card"


def test_ensure_movement_handler_is_a_noop_when_plan_already_moves() -> None:
    observation = _observation(
        _fire_snapshot(),
        hand=("card.test.fire", "card.test.advance", "card.test.vent"),
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.test.advance"),
            ModelSOPlanRegister(register_index=1, card_id="card.test.fire"),
        ),
        rationale="llm",
        confidence=0.7,
    )

    assert EnsureMovementCardRuleHandler().apply(observation, proposed) == proposed


def test_rule_registry_is_allowlisted_and_content_addressed() -> None:
    registry = CardProgrammingRuleRegistry(
        pack_id="rules.test",
        handlers=(PreferAttackCardsRuleHandler(),),
    )
    selected = registry.select(("prefer_attack_cards",))
    assert selected[0].metadata.handler_id == "prefer_attack_cards"
    first = registry.provenance(("prefer_attack_cards",))
    second = registry.provenance(("prefer_attack_cards",))
    assert first == second
    assert len(first.content_sha256) == 64
    assert first.handlers[0].version == "v1.0.0"

    with pytest.raises(CardProgrammingRuleError, match="not registered"):
        registry.select(("missing",))
    with pytest.raises(CardProgrammingRuleError, match="duplicate selected"):
        registry.select(("prefer_attack_cards", "prefer_attack_cards"))


def test_rule_handler_outputs_are_revalidated_against_observation() -> None:
    class InvalidHandler:
        metadata = PreferAttackCardsRuleHandler.metadata

        def apply(
            self,
            observation: ModelSOProgrammingObservation,
            proposed: ModelSOPlanCommittedPayload,
        ) -> ModelSOPlanCommittedPayload:
            del observation
            return proposed.model_copy(
                update={
                    "registers": (
                        ModelSOPlanRegister(register_index=0, card_id="card.test.missing"),
                    )
                }
            )

    observation = _observation(
        _fire_snapshot(), hand=("card.test.advance", "card.test.fire"), free_indices=(0, 1)
    )
    with pytest.raises(ValueError, match="program must contain exactly"):
        program_for_seat(
            None,
            observation,
            rule_handlers=(InvalidHandler(),),
        )
