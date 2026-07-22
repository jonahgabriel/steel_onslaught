"""c11 Overpressure Cooldown handler — plan-time heat-lockout gating tests.

These prove the KEY behaviour: the overpressure_cooldown handler swaps an
overheating attack register for a vent (and does nothing without the handler),
that it maps the attack card's weapon_slot to the correct weapon's heat, and
that its rule pack is content-addressed for replay.
"""

from __future__ import annotations

import pytest

from steel_onslaught.cards.rules import (
    CardProgrammingRuleRegistry,
    OverpressureCooldownRuleHandler,
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
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation, program_for_seat
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

pytestmark = pytest.mark.unit

_FIRE_PRIMARY = "card.attack.fire_primary"
_FIRE_SECONDARY = "card.attack.fire_secondary"
_VENT = "card.vent.emergency_vent"
_ADVANCE = "card.move.advance"


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id=_FIRE_PRIMARY,
                display_name="fire primary",
                category=SOCardCategory.ATTACK,
                priority=600,
                heat_cost=0,
                effect=ModelSOCardEffect(weapon_slot=0),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id=_FIRE_SECONDARY,
                display_name="fire secondary",
                category=SOCardCategory.ATTACK,
                priority=550,
                heat_cost=0,
                effect=ModelSOCardEffect(weapon_slot=1),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id=_ADVANCE,
                display_name="advance",
                category=SOCardCategory.MOVEMENT,
                priority=100,
                heat_cost=0,
                effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
            ModelSOCard(
                schema_version="0.1.0",
                kind="steel_onslaught.card",
                id=_VENT,
                display_name="vent",
                category=SOCardCategory.VENT,
                priority=200,
                heat_cost=0,
                effect=ModelSOCardEffect(),
            ),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.c11",
        display_name="c11",
        hand_size=5,
        register_count=5,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=4) for card in cards.cards),
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
    snapshot: ModelSOCardRuntimeSnapshot,
    *,
    heat_current: int,
    heat_capacity: int,
    vent_rate: int,
    artillery_heat: int = 20,
    harpoon_heat: int = 12,
    artillery_cd: int = 0,
    harpoon_cd: int = 0,
    hand: tuple[str, ...],
) -> ModelSOProgrammingObservation:
    boiler = ModelSOBoilerState(
        match_id="match.c11",
        mech_id="mech.b.01",
        tick=0,
        pressure_current=90,
        pressure_maximum=90,
        regeneration_per_tick=5,
        heat_current=heat_current,
        heat_capacity=heat_capacity,
        heat_redline_threshold=80,
        heat_rupture_threshold=100,
        heat_vent_rate=vent_rate,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )
    pilot = ModelSOPilotObservation(
        match_id="match.c11",
        mech_id="mech.b.01",
        player_id="player.b",
        tick=0,
        match_elapsed_ticks=0,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.siege.artillery_mortar",
                damage=45,
                range=50,
                pressure_cost=20,
                heat_generated=artillery_heat,
                cooldown_remaining_ticks=artillery_cd,
            ),
            ModelSOPilotWeaponView(
                weapon_id="weapon.heavy.harpoon_gun",
                damage=28,
                range=30,
                pressure_cost=14,
                heat_generated=harpoon_heat,
                cooldown_remaining_ticks=harpoon_cd,
            ),
        ],
        current_mode=ModeId.RECON,
        mode_lock_expired=True,
        position=ModelSOPosition(x=55, y=55),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=[],
    )
    return ModelSOProgrammingObservation(
        pilot_observation=pilot,
        card_runtime_snapshot=snapshot,
        seat="b",
        hand=hand,
        free_indices=tuple(range(len(hand))),
    )


def _plan(*card_ids: str) -> ModelSOPlanCommittedPayload:
    return ModelSOPlanCommittedPayload(
        seat="b",
        registers=tuple(
            ModelSOPlanRegister(register_index=index, card_id=card_id)
            for index, card_id in enumerate(card_ids)
        ),
        rationale="planner",
        confidence=1.0,
    )


def test_handler_swaps_overheating_attack_for_vent_and_is_a_noop_without_it() -> None:
    """The KEY test: the second shot overheats -> forced vent WITH the handler.

    heat_current 20, capacity 28, vent 4: register 0 artillery (heat 20) alone
    is heat_after_vent(16)+20=36 >= 28, so it must be swapped for the later
    vent. Without the handler the plan is unchanged (the fix is load-bearing).
    """

    snapshot = _snapshot()
    hand = (_FIRE_PRIMARY, _FIRE_SECONDARY, _VENT, _ADVANCE, _ADVANCE)
    observation = _observation(snapshot, heat_current=20, heat_capacity=28, vent_rate=4, hand=hand)
    proposed = _plan(_FIRE_PRIMARY, _FIRE_SECONDARY, _VENT, _ADVANCE, _ADVANCE)

    without = program_for_seat(_Programmer(proposed), observation)
    assert [r.card_id for r in without.registers] == list(hand)

    handler = OverpressureCooldownRuleHandler()
    gated = program_for_seat(_Programmer(proposed), observation, rule_handlers=(handler,))
    # register 0 becomes the vent; the deferred artillery moves to the vent's slot.
    assert gated.registers[0].card_id == _VENT
    assert _FIRE_PRIMARY in [r.card_id for r in gated.registers]
    assert gated.registers != proposed.registers
    assert "rule:overpressure_cooldown" in (gated.rationale or "")


def test_handler_is_noop_when_shot_fits_under_the_ceiling() -> None:
    """Cool boiler + one affordable shot: nothing is swapped."""

    snapshot = _snapshot()
    hand = (_FIRE_PRIMARY, _VENT, _ADVANCE, _ADVANCE, _ADVANCE)
    observation = _observation(snapshot, heat_current=0, heat_capacity=60, vent_rate=4, hand=hand)
    proposed = _plan(*hand)
    handler = OverpressureCooldownRuleHandler()
    result = program_for_seat(_Programmer(proposed), observation, rule_handlers=(handler,))
    assert [r.card_id for r in result.registers] == list(hand)


def test_handler_reads_the_weapon_slot_specific_heat() -> None:
    """Slot 1 (harpoon) is hot enough to gate while slot 0 (artillery) is not.

    With a tiny artillery heat (2) and a large harpoon heat (40), only the
    fire_secondary register (weapon_slot 1) crosses the ceiling — proving the
    handler indexes weapons[card.effect.weapon_slot], not a fixed weapon.
    """

    snapshot = _snapshot()
    hand = (_FIRE_PRIMARY, _FIRE_SECONDARY, _VENT, _ADVANCE, _ADVANCE)
    observation = _observation(
        snapshot,
        heat_current=0,
        heat_capacity=28,
        vent_rate=4,
        artillery_heat=2,
        harpoon_heat=40,
        hand=hand,
    )
    proposed = _plan(*hand)
    handler = OverpressureCooldownRuleHandler()
    result = program_for_seat(_Programmer(proposed), observation, rule_handlers=(handler,))
    cards = [r.card_id for r in result.registers]
    # register 0 artillery (heat 2) fires; the harpoon at register 1 is swapped
    # with the vent at register 2.
    assert cards[0] == _FIRE_PRIMARY
    assert cards[1] == _VENT
    assert _FIRE_SECONDARY in cards[2:]


def test_cooldown_rejected_attack_is_not_swapped() -> None:
    """An attack whose weapon is still on cooldown fires nothing, so it is left
    in place (no phantom vent that overcounts the tax)."""

    snapshot = _snapshot()
    hand = (_FIRE_PRIMARY, _VENT, _ADVANCE, _ADVANCE, _ADVANCE)
    observation = _observation(
        snapshot,
        heat_current=27,
        heat_capacity=28,
        vent_rate=4,
        artillery_cd=3,  # not ready this round
        hand=hand,
    )
    proposed = _plan(*hand)
    handler = OverpressureCooldownRuleHandler()
    result = program_for_seat(_Programmer(proposed), observation, rule_handlers=(handler,))
    assert [r.card_id for r in result.registers] == list(hand)


def test_rule_pack_is_content_addressed_and_registered() -> None:
    registry = default_rule_registry()
    assert "overpressure_cooldown" in {h.metadata.handler_id for h in registry.handlers}
    first = registry.provenance(("overpressure_cooldown",))
    second = registry.provenance(("overpressure_cooldown",))
    assert first == second
    assert len(first.content_sha256) == 64
    # Selecting an unknown id still fails closed alongside the new handler.
    with pytest.raises(Exception, match="not registered"):
        CardProgrammingRuleRegistry(
            pack_id="rules.card_programming_v1",
            handlers=(OverpressureCooldownRuleHandler(),),
        ).select(("missing",))


class _Programmer:
    def __init__(self, plan: ModelSOPlanCommittedPayload) -> None:
        self._plan = plan

    def program(self, _observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
        return self._plan
