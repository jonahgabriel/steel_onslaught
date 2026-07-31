"""OMN-15489 — the seat pilot spec must be causal in card mode.

Unit half of the regression. These tests pin the *decision* difference at the
rule boundary with no provider anywhere in the picture: the same programming
observation and the same proposed plan, differing only in the seat's
``ModelSOPilotSpec`` parameters, must produce different committed rounds.

Before the fix this module's subject does not exist at all — card-mode
programming resolved programmers from the overlay's
``contracts.card_catalog.programmers`` bindings and never referenced the
resolved seat pilot, so ``vent_at_heat_margin`` and its siblings had a
structural ZERO effect on any card decision.
"""

from __future__ import annotations

from typing import cast

import pytest

from steel_onslaught.cards.pilot_policy import (
    RULE_HANDLER_ID,
    PilotPolicyCategoryRule,
    seat_policy_rule_for_spec,
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
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
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
    PilotProtocol,
)
from tests.runtime import pilot_from_spec

pytestmark = pytest.mark.unit

_TEMPLATE_PARAMS: dict[str, object] = {
    "vent_at_heat_margin": 5,
    "idle_vent_heat_threshold": 90,
    "mode_switch_pressure_floor": 12,
    "mode_switch_heat_ceiling": 80,
    "weapon_preference": "highest_damage",
}


def _spec(**overrides: object) -> ModelSOPilotSpec:
    parameters = {**_TEMPLATE_PARAMS, **overrides}
    return ModelSOPilotSpec.model_validate(
        {
            "id": "pilot.learn.test",
            "display_name": "Test learn spec",
            "archetype": "aggressive",
            "lineage": {"parent": "pilot.template.aggressive"},
            "parameters": parameters,
        }
    )


def _rule(**overrides: object) -> PilotPolicyCategoryRule:
    """Build the seat rule the way the composition root does: injected pilot."""

    spec = _spec(**overrides)
    return PilotPolicyCategoryRule(spec, pilot=pilot_from_spec(spec))


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


_CARDS = (
    _card("card.atk.primary", SOCardCategory.ATTACK, 600, weapon_slot=0),
    _card("card.atk.secondary", SOCardCategory.ATTACK, 500, weapon_slot=1),
    _card("card.mv.advance", SOCardCategory.MOVEMENT, 300, direction="toward_enemy", speed="full"),
    _card("card.sp.assault", SOCardCategory.SPECIAL, 250, target_mode=ModeId.ASSAULT),
    _card("card.vt.vent", SOCardCategory.VENT, 200),
)


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    catalog = ModelSOCardCatalog(cards=tuple(sorted(_CARDS, key=lambda card: str(card.id))))
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.omn15489",
        display_name="omn15489",
        hand_size=3,
        register_count=3,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=2) for card in catalog.cards),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=catalog,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(catalog, (deck,)),
    )


def _observation(
    *,
    hand: tuple[str, ...],
    heat: int = 0,
    pressure: int = 40,
    mode: ModeId = ModeId.ASSAULT,
    enemy_distance: float | None = None,
) -> ModelSOProgrammingObservation:
    boiler = ModelSOBoilerState(
        match_id="match.omn15489",
        mech_id="mech.red.01",
        tick=1,
        pressure_current=pressure,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=heat,
        heat_redline_threshold=80,
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
                tick=1,
                distance_estimate=enemy_distance,
                confidence=0.9,
            )
        ]
    )
    pilot_observation = ModelSOPilotObservation(
        match_id="match.omn15489",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=1,
        match_elapsed_ticks=1,
        boiler=boiler,
        weapons=[
            # Slot 0 is the high-damage/high-heat weapon, slot 1 the cool one:
            # the two ``weapon_preference`` policies select opposite slots.
            ModelSOPilotWeaponView(
                weapon_id="weapon.cannon",
                damage=9,
                range=20,
                pressure_cost=1,
                heat_generated=9,
                cooldown_remaining_ticks=0,
            ),
            ModelSOPilotWeaponView(
                weapon_id="weapon.laser",
                damage=3,
                range=20,
                pressure_cost=1,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            ),
        ],
        current_mode=mode,
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
        free_indices=tuple(range(len(hand))),
    )


def _plan(*card_ids: str, rationale: str | None = "stub") -> ModelSOPlanCommittedPayload:
    return ModelSOPlanCommittedPayload(
        seat="red",
        registers=tuple(
            ModelSOPlanRegister(register_index=index, card_id=card_id)
            for index, card_id in enumerate(card_ids)
        ),
        rationale=rationale,
        confidence=0.5,
    )


def _cards_of(plan: ModelSOPlanCommittedPayload) -> tuple[str, ...]:
    return tuple(str(register.card_id) for register in plan.registers)


# ---------------------------------------------------------------------------
# The central differential: candidate vs parent must change a card decision.
# ---------------------------------------------------------------------------


def test_vent_at_heat_margin_changes_the_committed_round() -> None:
    """RUN B's perturbed parameter (5 -> 4) must be causal, not decorative.

    At heat 95 with rupture 100 the near-rupture guard fires for margin 5
    (95 >= 100-5) and does NOT fire for margin 4 (95 < 100-4). The two seats
    therefore commit different rounds from the same hand and the same proposed
    plan — the exact discrimination the duel gate was silently missing.
    """

    hand = ("card.mv.advance", "card.atk.primary", "card.vt.vent")
    observation = _observation(hand=hand, heat=95, enemy_distance=1.0)
    proposed = _plan("card.mv.advance", "card.atk.primary", "card.atk.primary")

    parent = _rule(vent_at_heat_margin=5).apply(observation, proposed)
    candidate = _rule(vent_at_heat_margin=4).apply(observation, proposed)

    assert _cards_of(parent) != _cards_of(candidate)
    assert "card.vt.vent" in _cards_of(parent)
    assert "card.vt.vent" not in _cards_of(candidate)
    assert parent.rationale is not None and RULE_HANDLER_ID in parent.rationale


def test_weapon_preference_selects_the_matching_attack_slot() -> None:
    """``weapon_preference`` is causal: the two policies pick opposite slots."""

    hand = ("card.mv.advance", "card.atk.primary", "card.atk.secondary")
    observation = _observation(hand=hand, heat=0, enemy_distance=1.0)
    proposed = _plan("card.mv.advance", "card.mv.advance", "card.mv.advance")

    highest = _rule(weapon_preference="highest_damage").apply(observation, proposed)
    lowest = _rule(weapon_preference="lowest_heat").apply(observation, proposed)

    assert "card.atk.primary" in _cards_of(highest)  # slot 0 == weapon.cannon
    assert "card.atk.secondary" in _cards_of(lowest)  # slot 1 == weapon.laser
    assert _cards_of(highest) != _cards_of(lowest)


def test_mode_switch_pressure_floor_changes_the_committed_round() -> None:
    """The mode-switch pair is causal through the SPECIAL card's target_mode."""

    hand = ("card.mv.advance", "card.sp.assault", "card.mv.advance")
    observation = _observation(hand=hand, heat=0, pressure=12, mode=ModeId.RECON)
    proposed = _plan("card.mv.advance", "card.mv.advance", "card.mv.advance")

    reachable = _rule(mode_switch_pressure_floor=12).apply(observation, proposed)
    unreachable = _rule(mode_switch_pressure_floor=13).apply(observation, proposed)

    assert "card.sp.assault" in _cards_of(reachable)
    assert "card.sp.assault" not in _cards_of(unreachable)


# ---------------------------------------------------------------------------
# Boundary behaviour — the rule must not become a silent plan rewriter.
# ---------------------------------------------------------------------------


def test_noop_when_the_plan_already_expresses_the_decision() -> None:
    hand = ("card.vt.vent", "card.mv.advance", "card.atk.primary")
    observation = _observation(hand=hand, heat=95, enemy_distance=1.0)
    proposed = _plan("card.vt.vent", "card.mv.advance", "card.atk.primary")
    result = _rule().apply(observation, proposed)
    assert result == proposed


def test_noop_when_the_hand_cannot_satisfy_the_decision() -> None:
    hand = ("card.mv.advance", "card.mv.advance", "card.atk.primary")
    observation = _observation(hand=hand, heat=95, enemy_distance=1.0)
    proposed = _plan("card.mv.advance", "card.mv.advance", "card.atk.primary")
    result = _rule().apply(observation, proposed)
    assert result == proposed


def test_rule_is_idempotent() -> None:
    hand = ("card.mv.advance", "card.atk.primary", "card.vt.vent")
    observation = _observation(hand=hand, heat=95, enemy_distance=1.0)
    proposed = _plan("card.mv.advance", "card.atk.primary", "card.atk.primary")
    rule = _rule()
    once = rule.apply(observation, proposed)
    twice = rule.apply(observation, once)
    assert _cards_of(twice) == _cards_of(once)


def test_rule_passes_the_program_for_seat_handler_boundary() -> None:
    """The rule is a real ``CardProgrammingRuleHandler``, not a lookalike."""

    hand = ("card.mv.advance", "card.atk.primary", "card.vt.vent")
    observation = _observation(hand=hand, heat=95, enemy_distance=1.0)
    plan = program_for_seat(None, observation, rule_handlers=(_rule(),))
    assert "card.vt.vent" in _cards_of(plan)


# ---------------------------------------------------------------------------
# Scoping — provider-backed seats must never enter this pure seam.
# ---------------------------------------------------------------------------


def test_llm_spec_gets_no_seat_rule() -> None:
    llm_spec = ModelSOPilotSpec.model_validate(
        {
            "id": "pilot.llm.test",
            "display_name": "LLM",
            "archetype": "llm",
            "lineage": {"parent": "pilot.template.llm"},
            "parameters": {"provider": "stub", "persona": "berserker"},
        }
    )
    stub_pilot = cast(PilotProtocol, object())
    assert seat_policy_rule_for_spec(llm_spec, pilot=stub_pilot) is None
    with pytest.raises(ValueError, match="deterministic archetype"):
        PilotPolicyCategoryRule(llm_spec, pilot=stub_pilot)


def test_untyped_spec_fails_closed_rather_than_silently_dropping_the_policy() -> None:
    """A dropped seat policy IS the bypass; it must never be a quiet ``None``."""

    with pytest.raises(TypeError, match="typed ModelSOPilotSpec"):
        seat_policy_rule_for_spec(
            cast(ModelSOPilotSpec, object()), pilot=cast(PilotProtocol, object())
        )


def test_rule_identity_is_bound_to_the_exact_spec_parameters() -> None:
    """Provenance must distinguish candidate from parent, not collapse them."""

    parent = _rule(vent_at_heat_margin=5).metadata
    candidate = _rule(vent_at_heat_margin=4).metadata
    assert parent.handler_id == candidate.handler_id == RULE_HANDLER_ID
    assert parent.implementation_sha256 != candidate.implementation_sha256
