"""Preferred-range policy handler tests."""

from __future__ import annotations

import pytest

from steel_onslaught.cards.rules import (
    PreferredRangePolicyError,
    PreferredRangeRuleHandler,
    default_rule_registry,
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
from steel_onslaught.contracts.range_policy import ModelSOPreferredRangePolicy
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation
from steel_onslaught.pilots.schemas import ModelSOSensorReading
from tests.cards.test_programming import _observation

pytestmark = pytest.mark.unit


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=tuple(
            sorted(
                (
                    ModelSOCard(
                        schema_version="0.1.0",
                        kind="steel_onslaught.card",
                        id="card.movement.reposition",
                        display_name="Reposition",
                        category=SOCardCategory.MOVEMENT,
                        priority=380,
                        heat_cost=0,
                        effect=ModelSOCardEffect(direction="away_from_enemy", speed="full"),
                    ),
                    ModelSOCard(
                        schema_version="0.1.0",
                        kind="steel_onslaught.card",
                        id="card.movement.advance",
                        display_name="Advance",
                        category=SOCardCategory.MOVEMENT,
                        priority=400,
                        heat_cost=0,
                        effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
                    ),
                    ModelSOCard(
                        schema_version="0.1.0",
                        kind="steel_onslaught.card",
                        id="card.attack.fire",
                        display_name="Fire",
                        category=SOCardCategory.ATTACK,
                        priority=200,
                        heat_cost=3,
                        effect=ModelSOCardEffect(weapon_slot=0),
                    ),
                    ModelSOCard(
                        schema_version="0.1.0",
                        kind="steel_onslaught.card",
                        id="card.vent.emergency",
                        display_name="Vent",
                        category=SOCardCategory.VENT,
                        priority=100,
                        heat_cost=0,
                        effect=ModelSOCardEffect(),
                    ),
                ),
                key=lambda card: str(card.id),
            )
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.range",
        display_name="Range test",
        hand_size=4,
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


def _outside_range_observation(
    *, include_advance: bool = True, distance: float = 12.0
) -> ModelSOProgrammingObservation:
    snapshot = _snapshot()
    hand: tuple[str, ...] = (
        "card.movement.reposition",
        "card.attack.fire",
        "card.vent.emergency",
        "card.movement.advance",
    )
    if not include_advance:
        hand = hand[:3]
    observation = _observation(snapshot, hand=hand, free_indices=(0, 1, 2))
    pilot_observation = observation.pilot_observation.model_copy(
        update={
            "enemy_observations": [
                ModelSOSensorReading(
                    enemy_mech_id="mech.blue.01",
                    tick=2,
                    distance_estimate=distance,
                    confidence=0.9,
                )
            ]
        }
    )
    return observation.model_copy(update={"pilot_observation": pilot_observation})


def _policy() -> ModelSOPreferredRangePolicy:
    return ModelSOPreferredRangePolicy(
        policy_id="range_policy.berserker_short",
        archetype="berserker",
        preferred_min=0,
        preferred_max=6,
        outside_range_direction="toward_enemy",
    )


def test_berserker_reposition_is_repaired_to_approach_outside_short_range() -> None:
    observation = _outside_range_observation()
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.movement.reposition"),
            ModelSOPlanRegister(register_index=1, card_id="card.attack.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vent.emergency"),
        ),
        rationale="llm",
        confidence=0.7,
    )

    result = PreferredRangeRuleHandler(_policy()).apply(observation, proposed)

    assert tuple(register.card_id for register in result.registers) == (
        "card.movement.advance",
        "card.attack.fire",
        "card.vent.emergency",
    )
    assert result.rationale == "llm; range_policy:range_policy.berserker_short:approach"


def test_berserker_plan_is_unchanged_inside_short_range() -> None:
    observation = _outside_range_observation(distance=4.0)
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.movement.reposition"),
            ModelSOPlanRegister(register_index=1, card_id="card.attack.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vent.emergency"),
        ),
        rationale="llm",
        confidence=0.7,
    )

    assert PreferredRangeRuleHandler(_policy()).apply(observation, proposed) == proposed


def test_berserker_away_plan_fails_closed_without_approach_card() -> None:
    observation = _outside_range_observation(include_advance=False)
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.movement.reposition"),
            ModelSOPlanRegister(register_index=1, card_id="card.attack.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vent.emergency"),
        ),
        rationale=None,
        confidence=0.7,
    )

    with pytest.raises(PreferredRangePolicyError, match="forbids away movement"):
        PreferredRangeRuleHandler(_policy()).apply(observation, proposed)


def test_berserker_policy_cannot_opt_out_of_approach_guard() -> None:
    with pytest.raises(ValueError, match="must forbid away movement"):
        ModelSOPreferredRangePolicy(
            policy_id="range_policy.berserker_bad",
            archetype="berserker",
            preferred_min=0,
            preferred_max=6,
            outside_range_direction="toward_enemy",
            forbid_away_outside_range=False,
        )


def test_preferred_range_policy_is_allowlisted_only_when_injected() -> None:
    assert default_rule_registry().select(()) == ()
    registry = default_rule_registry(preferred_range_policy=_policy())
    selected = registry.select(("preferred_range_guard",))
    assert isinstance(selected[0], PreferredRangeRuleHandler)
    assert selected[0].metadata.handler_id == "preferred_range_guard"
