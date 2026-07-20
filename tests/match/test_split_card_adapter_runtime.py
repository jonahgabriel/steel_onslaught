"""End-to-end proof for the injected split-deck card runtime."""

from __future__ import annotations

import pytest

from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope, ModelSODeckState
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.cards.split_deck import SplitDeckDealerAdapter
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
from steel_onslaught.contracts.player_selection import Side
from steel_onslaught.contracts.split_deck import (
    ModelSOCardDeckPolicy,
    ModelSODeckHandQuota,
    ModelSOSeatDeckPolicy,
)
from steel_onslaught.events.card_payloads import SOCardPartition
from steel_onslaught.match.card_adapter import CardRunnerAdapter, ModelSOCardSeatRequest
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

pytestmark = pytest.mark.unit


def _card(card_id: str, category: SOCardCategory, effect: ModelSOCardEffect) -> ModelSOCard:
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=category,
        priority=10,
        heat_cost=0,
        effect=effect,
    )


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            _card(
                "card.test.advance",
                SOCardCategory.MOVEMENT,
                ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
            _card(
                "card.test.attack",
                SOCardCategory.ATTACK,
                ModelSOCardEffect(weapon_slot=0),
            ),
            _card(
                "card.test.flank_left",
                SOCardCategory.MOVEMENT,
                ModelSOCardEffect(direction="left", speed="full"),
            ),
            _card(
                "card.test.flank_right",
                SOCardCategory.MOVEMENT,
                ModelSOCardEffect(direction="right", speed="full"),
            ),
            _card(
                "card.test.vent",
                SOCardCategory.VENT,
                ModelSOCardEffect(),
            ),
        )
    )
    movement = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.movement",
        display_name="test movement",
        hand_size=3,
        register_count=3,
        cards=tuple(
            ModelSODeckEntry(card_id=card_id, count=2)
            for card_id in (
                "card.test.advance",
                "card.test.flank_left",
                "card.test.flank_right",
            )
        ),
    )
    weapon = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.weapon",
        display_name="test weapon",
        hand_size=3,
        register_count=3,
        cards=(
            ModelSODeckEntry(card_id="card.test.attack", count=4),
            ModelSODeckEntry(card_id="card.test.vent", count=2),
        ),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(movement, weapon),
        selected_deck_id=None,
        content_sha256=canonical_card_runtime_sha256(cards, (movement, weapon)),
    )


def _policy() -> ModelSOCardDeckPolicy:
    return ModelSOCardDeckPolicy(
        schema_version="0.1.0",
        kind="steel_onslaught.card_deck_policy",
        seats=(
            ModelSOSeatDeckPolicy(
                side="red",
                archetype="berserker",
                movement_deck_id="deck.test.movement",
                weapon_deck_id="deck.test.weapon",
                hand_quota=ModelSODeckHandQuota(movement=3, weapon=2),
                register_count=5,
            ),
            ModelSOSeatDeckPolicy(
                side="blue",
                archetype="sniper",
                movement_deck_id="deck.test.movement",
                weapon_deck_id="deck.test.weapon",
                hand_quota=ModelSODeckHandQuota(movement=2, weapon=3),
                register_count=5,
            ),
        ),
    )


def _request(seat: str, side: Side) -> ModelSOCardSeatRequest:
    boiler = ModelSOBoilerState(
        match_id="match.split-runtime",
        mech_id=f"mech.{seat}",
        tick=0,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=0,
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
    observation = ModelSOPilotObservation(
        match_id="match.split-runtime",
        mech_id=f"mech.{seat}",
        player_id=f"player.{seat}",
        tick=0,
        match_elapsed_ticks=0,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.test.primary",
                damage=10,
                range=20,
                pressure_cost=1,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            )
        ],
        current_mode=ModeId.RECON,
        mode_lock_expired=True,
        position=ModelSOPosition(x=10, y=10),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=[],
    )
    return ModelSOCardSeatRequest(
        seat=seat,
        side=side,
        dealer_scope=ModelSODealerScope(
            match_id="match.split-runtime",
            match_seed=812,
            tick=0,
            seat=seat,
        ),
        pilot_observation=observation,
        initiative=0 if side == "red" else 1,
        weapon_ids=("weapon.test.primary",),
    )


def _adapter() -> CardRunnerAdapter:
    snapshot = _snapshot()
    dealer = DealerCompute()
    split = SplitDeckDealerAdapter(snapshot=snapshot, policy=_policy(), dealer=dealer)
    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    runtime = CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=5,
        split_deck_adapter=split,
    )
    return CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=dealer,
        reducer=reducer,
        split_deck_adapter=split,
    )


def test_split_runtime_emits_typed_quotas_and_independent_state() -> None:
    adapter = _adapter()
    red = _request("mech.red", "red")
    blue = _request("mech.blue", "blue")
    first = adapter.produce(
        seats=(blue, red),
        round_index=0,
        tick=0,
        causation_id="split-round-0",
    )
    second = adapter.produce(
        seats=(red, blue),
        round_index=0,
        tick=0,
        causation_id="split-round-0",
    )

    assert first == second
    assert first.deck_state is None
    assert first.split_policy == _policy()
    assert {state.seat for state in first.split_deck_states} == {"mech.red", "mech.blue"}
    assert first.sequence is not None
    by_seat = {payload.seat: payload for payload in first.sequence.hand_dealt}
    assert by_seat["mech.red"].partitions is not None
    assert by_seat["mech.blue"].partitions is not None
    assert by_seat["mech.red"].deck_id == "deck.split"
    assert by_seat["mech.red"].partitions.movement.partition is SOCardPartition.MOVEMENT
    assert by_seat["mech.red"].partitions.weapon.partition is SOCardPartition.WEAPON
    assert len(by_seat["mech.red"].partitions.movement.card_ids) == 3
    assert len(by_seat["mech.red"].partitions.weapon.card_ids) == 2
    assert len(by_seat["mech.blue"].partitions.movement.card_ids) == 2
    assert len(by_seat["mech.blue"].partitions.weapon.card_ids) == 3
    with pytest.raises(ValueError, match="starting_split_deck_states"):
        adapter.produce(
            seats=(red, blue),
            round_index=0,
            tick=0,
            causation_id="split-round-0",
            starting_deck_state=ModelSODeckState(draw_pile=(), discard_pile=()),
        )
