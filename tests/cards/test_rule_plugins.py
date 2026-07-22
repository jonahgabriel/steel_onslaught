"""Tests for the plug-in rule surface: two real handlers + discoverable catalog.

These prove the rule-pack surface is genuinely pluggable (more than one working
handler), discoverable (an enumerable catalog with human descriptions), and
fail-closed (unknown handler ids are rejected by ``select``).
"""

from __future__ import annotations

import pytest

from steel_onslaught.cards.rules import (
    CardProgrammingRuleError,
    CardProgrammingRuleRegistry,
    CloseTheGapRuleHandler,
    EnsureMovementCardRuleHandler,
    PreferAttackCardsRuleHandler,
    default_rule_registry,
)
from steel_onslaught.contracts.boiler import ModelSOBoilerState
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
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import (
    ModelSOProgrammingObservation,
    program_for_seat,
)
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
)

pytestmark = pytest.mark.unit


def _card(card_id: str, category: SOCardCategory, priority: int, **effect: object) -> ModelSOCard:
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=category,
        priority=priority,
        heat_cost=0,
        effect=ModelSOCardEffect(**effect),  # type: ignore[arg-type]
    )


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    catalog_cards = sorted(
        (
            _card(
                "card.mv.advance",
                SOCardCategory.MOVEMENT,
                20,
                direction="toward_enemy",
                speed="full",
            ),
            _card(
                "card.mv.retreat",
                SOCardCategory.MOVEMENT,
                18,
                direction="away_from_enemy",
                speed="full",
            ),
            _card("card.mv.strafe", SOCardCategory.MOVEMENT, 15, direction="right", speed="full"),
            _card("card.atk.fire", SOCardCategory.ATTACK, 5, weapon_slot=0),
            _card("card.vt.vent", SOCardCategory.VENT, 10),
        ),
        key=lambda card: card.id,
    )
    cards = ModelSOCardCatalog(cards=tuple(catalog_cards))
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.plugins",
        display_name="plugins",
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


def _observation(
    *,
    hand: tuple[str, ...],
    free_indices: tuple[int, ...],
    enemy_distance: float | None = None,
    weapon_range: int = 1,
) -> ModelSOProgrammingObservation:
    boiler = ModelSOBoilerState(
        match_id="match.test",
        mech_id="mech.red.01",
        tick=0,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=0,
        heat_redline_threshold=80,
        heat_capacity=100,
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )
    readings = (
        []
        if enemy_distance is None
        else [
            ModelSOSensorReading(
                enemy_mech_id="mech.blue.01",
                tick=0,
                distance_estimate=enemy_distance,
                confidence=0.9,
            )
        ]
    )
    pilot_observation = ModelSOPilotObservation(
        match_id="match.test",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=0,
        match_elapsed_ticks=0,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.test",
                damage=1,
                range=weapon_range,
                pressure_cost=1,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            ),
        ],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=1, y=1),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=readings,
    )
    return ModelSOProgrammingObservation(
        pilot_observation=pilot_observation,
        card_runtime_snapshot=_snapshot(),
        seat="red",
        hand=hand,
        free_indices=free_indices,
    )


# --- EnsureMovementCardRuleHandler -----------------------------------------


def test_ensure_movement_injects_movement_when_plan_is_stationary() -> None:
    observation = _observation(
        hand=("card.atk.fire", "card.vt.vent", "card.mv.advance"),
        free_indices=(0, 1, 2),
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.atk.fire"),
            ModelSOPlanRegister(register_index=1, card_id="card.vt.vent"),
            ModelSOPlanRegister(register_index=2, card_id="card.vt.vent"),
        ),
        rationale="llm",
        confidence=0.6,
    )
    result = EnsureMovementCardRuleHandler().apply(observation, proposed)
    assert result.registers[-1].card_id == "card.mv.advance"
    assert result.rationale == "llm; rule:ensure_movement_card"


def test_ensure_movement_is_noop_when_plan_already_moves() -> None:
    observation = _observation(
        hand=("card.mv.advance", "card.atk.fire", "card.vt.vent"),
        free_indices=(0, 1, 2),
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.mv.advance"),
            ModelSOPlanRegister(register_index=1, card_id="card.atk.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vt.vent"),
        ),
        rationale="llm",
        confidence=0.6,
    )
    assert EnsureMovementCardRuleHandler().apply(observation, proposed) == proposed


# --- CloseTheGapRuleHandler -------------------------------------------------


def test_close_the_gap_swaps_retreat_for_approach_when_out_of_range() -> None:
    observation = _observation(
        hand=("card.mv.retreat", "card.mv.advance", "card.atk.fire", "card.vt.vent"),
        free_indices=(0, 1, 2),
        enemy_distance=9.0,
        weapon_range=3,
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.mv.retreat"),
            ModelSOPlanRegister(register_index=1, card_id="card.atk.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vt.vent"),
        ),
        rationale=None,
        confidence=0.5,
    )
    result = CloseTheGapRuleHandler().apply(observation, proposed)
    assert result.registers[0].card_id == "card.mv.advance"
    assert result.rationale == "rule:close_the_gap"


def test_close_the_gap_is_noop_in_range() -> None:
    observation = _observation(
        hand=("card.mv.retreat", "card.mv.advance", "card.atk.fire"),
        free_indices=(0, 1, 2),
        enemy_distance=2.0,
        weapon_range=3,
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.mv.retreat"),
            ModelSOPlanRegister(register_index=1, card_id="card.atk.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vt.vent"),
        ),
        rationale="hold",
        confidence=0.5,
    )
    assert CloseTheGapRuleHandler().apply(observation, proposed) == proposed


def test_close_the_gap_is_noop_without_sensor_contact() -> None:
    observation = _observation(
        hand=("card.mv.retreat", "card.mv.advance", "card.atk.fire"),
        free_indices=(0, 1, 2),
        enemy_distance=None,
        weapon_range=3,
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.mv.retreat"),
            ModelSOPlanRegister(register_index=1, card_id="card.atk.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vt.vent"),
        ),
        rationale="x",
        confidence=0.5,
    )
    assert CloseTheGapRuleHandler().apply(observation, proposed) == proposed


def test_close_the_gap_leaves_retreat_when_no_approach_card_available() -> None:
    # Advance is already consumed, so no toward_enemy card remains to swap in.
    observation = _observation(
        hand=("card.mv.retreat", "card.mv.advance", "card.atk.fire"),
        free_indices=(0, 1, 2),
        enemy_distance=9.0,
        weapon_range=3,
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.mv.retreat"),
            ModelSOPlanRegister(register_index=1, card_id="card.mv.advance"),
            ModelSOPlanRegister(register_index=2, card_id="card.atk.fire"),
        ),
        rationale="x",
        confidence=0.5,
    )
    assert CloseTheGapRuleHandler().apply(observation, proposed) == proposed


def test_two_handlers_compose_through_program_for_seat() -> None:
    observation = _observation(
        hand=("card.mv.retreat", "card.mv.advance", "card.atk.fire", "card.vt.vent"),
        free_indices=(0, 1, 2),
        enemy_distance=9.0,
        weapon_range=3,
    )
    proposed = ModelSOPlanCommittedPayload(
        seat="red",
        registers=(
            ModelSOPlanRegister(register_index=0, card_id="card.mv.retreat"),
            ModelSOPlanRegister(register_index=1, card_id="card.atk.fire"),
            ModelSOPlanRegister(register_index=2, card_id="card.vt.vent"),
        ),
        rationale="llm",
        confidence=0.5,
    )

    class _Programmer:
        def program(self, _obs: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
            return proposed

    registry = default_rule_registry()
    handlers = registry.select(("close_the_gap", "ensure_movement_card"))
    planned = program_for_seat(_Programmer(), observation, rule_handlers=handlers)
    # close_the_gap turns the retreat into an approach; the plan then already
    # moves, so ensure_movement is a no-op — a real ordered composition.
    assert planned.registers[0].card_id == "card.mv.advance"


# --- Discoverable, fail-closed catalog --------------------------------------


def test_default_registry_exposes_at_least_two_described_handlers() -> None:
    catalog = default_rule_registry().catalog(())
    ids = {descriptor.handler_id for descriptor in catalog.available}
    assert {"prefer_attack_cards", "ensure_movement_card", "close_the_gap"} <= ids
    for descriptor in catalog.available:
        assert descriptor.display_name
        assert descriptor.description
    assert catalog.enabled_handler_ids == ()


def test_catalog_marks_enabled_selection_in_order() -> None:
    catalog = default_rule_registry().catalog(("close_the_gap", "prefer_attack_cards"))
    assert catalog.enabled_handler_ids == ("close_the_gap", "prefer_attack_cards")


def test_select_fails_closed_on_unknown_handler() -> None:
    with pytest.raises(CardProgrammingRuleError, match="not registered"):
        default_rule_registry().select(("no_such_rule",))


def test_registry_rejects_handler_without_descriptor() -> None:
    class _NoDescriptor:
        metadata = PreferAttackCardsRuleHandler.metadata

        def apply(
            self,
            observation: ModelSOProgrammingObservation,
            proposed_plan: ModelSOPlanCommittedPayload,
        ) -> ModelSOPlanCommittedPayload:
            return proposed_plan

    registry = CardProgrammingRuleRegistry(pack_id="rules.test", handlers=(_NoDescriptor(),))
    with pytest.raises(CardProgrammingRuleError, match="ModelSOCardRuleHandlerDescriptor"):
        registry.catalog(())
