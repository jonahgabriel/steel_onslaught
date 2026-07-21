"""Pure proof for the opt-in card runner adapter."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from steel_onslaught.cards.actions import compile_card_action
from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope, ModelSODeckState
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    ModelSOCardEffect,
    SOCardCategory,
    SOCardDirection,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SORegisterOutcome,
)
from steel_onslaught.events.envelope import ModelSOEventSubject, SOEventType
from steel_onslaught.events.payloads import ModelSOMoveIntentPayload
from steel_onslaught.match.card_adapter import (
    CardRunnerAdapter,
    CardRunnerAdapterError,
    ModelSOCardSeatRequest,
)
from steel_onslaught.match.card_event_specs import build_card_round_event_specs
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation, ProgrammingPilotError
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

pytestmark = pytest.mark.unit


def _card(
    card_id: str,
    category: SOCardCategory,
    priority: int,
    effect: ModelSOCardEffect,
) -> ModelSOCard:
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


def _runtime(*, registers_enabled: bool = True) -> CardRunnerAdapter:
    cards = ModelSOCardCatalog(
        cards=(
            _card(
                "card.test.advance",
                SOCardCategory.MOVEMENT,
                10,
                ModelSOCardEffect(direction="toward_enemy", speed="full"),
            ),
            _card(
                "card.test.attack",
                SOCardCategory.ATTACK,
                40,
                ModelSOCardEffect(weapon_slot=0),
            ),
            _card(
                "card.test.special",
                SOCardCategory.SPECIAL,
                30,
                ModelSOCardEffect(target_mode=ModeId.EVASION),
            ),
            _card(
                "card.test.vent",
                SOCardCategory.VENT,
                20,
                ModelSOCardEffect(),
            ),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.adapter",
        display_name="Adapter deck",
        hand_size=4,
        register_count=2,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=2) for card in cards.cards),
    )
    snapshot = ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )
    dealer = DealerCompute()
    reducer = RegisterExecutionReducer(cards)
    runtime = CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=2,
    )
    return CardRunnerAdapter(
        registers_enabled=registers_enabled,
        card_round_runtime=runtime if registers_enabled else None,
        dealer=dealer if registers_enabled else None,
        reducer=reducer if registers_enabled else None,
    )


def _observation(seat: str) -> ModelSOPilotObservation:
    boiler = ModelSOBoilerState(
        match_id="match.test.adapter",
        mech_id=f"mech.{seat}.01",
        tick=3,
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
    return ModelSOPilotObservation(
        match_id="match.test.adapter",
        mech_id=f"mech.{seat}.01",
        player_id=f"player.{seat}",
        tick=3,
        match_elapsed_ticks=3,
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
        position=ModelSOPosition(x=1, y=1),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=[],
    )


def _request(
    seat: str,
    *,
    lock_depth: int = 0,
    previous_plan: ModelSOPlanCommittedPayload | None = None,
    weapon_ids: tuple[str, ...] = ("weapon.test.primary",),
) -> ModelSOCardSeatRequest:
    return ModelSOCardSeatRequest(
        seat=seat,
        dealer_scope=ModelSODealerScope(
            match_id="match.test.adapter",
            match_seed=77,
            tick=3,
            seat=seat,
        ),
        pilot_observation=_observation(seat),
        initiative=1 if seat == "a" else 2,
        lock_depth=lock_depth,
        previous_plan=previous_plan,
        weapon_ids=weapon_ids,
    )


def _known_starting_state() -> ModelSODeckState:
    """Avoid coupling adapter proofs to a particular shuffle implementation."""

    return ModelSODeckState(
        draw_pile=(
            "card.test.attack",
            "card.test.special",
            "card.test.advance",
            "card.test.vent",
            "card.test.attack",
            "card.test.special",
            "card.test.advance",
            "card.test.vent",
        ),
        discard_pile=(),
    )


class _Program:
    def __init__(self, card_ids: tuple[str, str]) -> None:
        self.card_ids = card_ids

    def program(self, observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
        assert all(card_id in observation.hand for card_id in self.card_ids)
        return ModelSOPlanCommittedPayload(
            seat=observation.seat,
            registers=tuple(
                ModelSOPlanRegister(register_index=index, card_id=card_id)
                for index, card_id in enumerate(self.card_ids)
            ),
            rationale="explicit test program",
            confidence=1.0,
        )


class _DecideOnly:
    def decide(self, _observation: object) -> object:
        return object()


def test_disabled_adapter_emits_zero_card_values_and_events() -> None:
    adapter = _runtime(registers_enabled=False)
    emission = adapter.produce(
        seats=(_request("a"),),
        round_index=0,
        tick=3,
        causation_id="round.test.0",
    )
    assert emission.values == ()
    assert emission.actions == ()
    assert emission.sequence is None
    assert emission.deck_state is None
    assert emission.suppressed_reason == "registers_disabled"


@pytest.mark.parametrize(
    ("direction", "expected_direction"),
    (("left", "flank_left"), ("right", "flank_right")),
)
def test_flank_movement_cards_translate_to_perpendicular_move_intents(
    direction: SOCardDirection, expected_direction: str
) -> None:
    card = _card(
        f"card.test.flank_{direction}",
        SOCardCategory.MOVEMENT,
        11,
        ModelSOCardEffect(direction=direction, speed="full"),
    )
    resolved = CardRunnerAdapter._intent_for_translation(
        compile_card_action(card),
        _request("a"),
    )
    assert resolved is not None, "a fielded weapon slot must compile to an intent"
    event_type, payload = resolved

    assert event_type is SOEventType.MOVE_INTENT
    assert isinstance(payload, ModelSOMoveIntentPayload)
    assert payload.direction == expected_direction
    assert payload.speed == "full"


def test_terminal_boundary_suppresses_enabled_card_round() -> None:
    adapter = _runtime()
    emission = adapter.produce(
        seats=(_request("a"), _request("b")),
        round_index=2,
        tick=99,
        causation_id="round.test.2",
        terminated=True,
    )
    assert emission.values == ()
    assert emission.actions == ()
    assert emission.suppressed_reason == "match_ended"


def test_enabled_round_is_canonical_and_compiles_varied_intents() -> None:
    base = _runtime()
    runtime = base.card_round_runtime
    assert runtime is not None
    programmers: dict[str, _Program] = {
        "a": _Program(("card.test.attack", "card.test.special")),
        "b": _Program(("card.test.advance", "card.test.vent")),
    }
    adapter = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=base.dealer,
        reducer=base.reducer,
        programmers=programmers,
    )
    programmers.clear()
    assert adapter.programmers is not None
    assert "a" in adapter.programmers
    first = adapter.produce(
        seats=(_request("b"), _request("a")),
        round_index=1,
        tick=3,
        causation_id="round.test.1",
        starting_deck_state=_known_starting_state(),
    )
    second = adapter.produce(
        seats=(_request("a"), _request("b")),
        round_index=1,
        tick=3,
        causation_id="round.test.1",
        starting_deck_state=_known_starting_state(),
    )
    assert first == second
    assert first.sequence is not None
    assert [value.stage for value in first.values] == [
        "HAND_DEALT",
        "HAND_DEALT",
        "PLAN_COMMITTED",
        "PLAN_COMMITTED",
        "REGISTER_RESOLVED",
        "REGISTER_RESOLVED",
        "REGISTER_RESOLVED",
        "REGISTER_RESOLVED",
        "CARDS_DISCARDED",
        "CARDS_DISCARDED",
    ]
    assert all(value.caused_by for value in first.values)
    assert {action.event_type for action in first.actions} == {
        SOEventType.WEAPON_FIRE_INTENT,
        SOEventType.MODE_SWITCH_INTENT,
        SOEventType.MOVE_INTENT,
        SOEventType.VENT_INTENT,
    }
    assert all(action.payload is not None for action in first.actions)
    assert first.deck_state is not None
    assert len(first.deck_state.draw_pile) == 0


def test_short_deck_and_heat_lock_remain_typed_outcomes() -> None:
    base = _runtime()
    runtime = base.card_round_runtime
    assert runtime is not None
    short_runtime = replace(runtime, round_length=3)
    short_adapter = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=short_runtime,
        dealer=base.dealer,
        reducer=base.reducer,
        programmers={"a": _Program(("card.test.attack", "card.test.special"))},
    )
    short = short_adapter.produce(
        seats=(_request("a"),),
        round_index=0,
        tick=3,
        causation_id="round.test.short",
        starting_deck_state=_known_starting_state(),
    )
    assert short.sequence is not None
    assert short.sequence.register_resolved[-1].outcome is SORegisterOutcome.AUTO_REMAIN
    assert short.actions[-1].event_type is None
    assert short.actions[-1].payload is None

    adapter = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=base.dealer,
        reducer=base.reducer,
        programmers={
            "a": _Program(("card.test.attack", "card.test.special")),
        },
    )
    first = adapter.produce(
        seats=(_request("a"),),
        round_index=1,
        tick=3,
        causation_id="round.test.heat",
        starting_deck_state=_known_starting_state(),
    )
    assert first.sequence is not None
    first_sequence = first.sequence
    second_adapter = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=base.dealer,
        reducer=base.reducer,
    )
    second = second_adapter.produce(
        seats=(
            _request(
                "a",
                lock_depth=1,
                previous_plan=first_sequence.plan_committed[0],
            ),
        ),
        round_index=2,
        tick=4,
        causation_id="round.test.heat.2",
        starting_deck_state=first.deck_state,
    )
    assert second.sequence is not None
    outcomes = second.sequence.register_resolved
    assert outcomes[1].outcome is SORegisterOutcome.HEAT_LOCKED
    assert outcomes[1].card_id == first_sequence.plan_committed[0].registers[1].card_id


def test_unfielded_weapon_slot_is_inert_not_a_crashed_round() -> None:
    """An attack card naming an unfielded hardpoint must not kill the round.

    Regression for cards-06: ``_intent_for_translation`` raised whenever a
    resolved attack card's ``weapon_slot`` was >= the seat's equipped weapon
    count, and that ``CardRunnerAdapterError`` escaped ``produce`` into the
    runner and terminated the match.  A mech that does not carry the hardpoint
    simply cannot execute the card: the register still RESOLVED (the card was
    played and is discarded), and only its intent is suppressed.
    """
    base = _runtime()
    assert base.card_round_runtime is not None
    emission = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=base.card_round_runtime,
        dealer=base.dealer,
        reducer=base.reducer,
    ).produce(
        seats=(_request("a", weapon_ids=()),),
        round_index=0,
        tick=3,
        causation_id="round.test.weapon-binding",
    )

    assert emission.sequence is not None
    attacks = [
        action
        for action in emission.actions
        if action.card_id is not None and str(action.card_id) == "card.test.attack"
    ]
    assert attacks, "the deterministic deal must include the attack card"
    for action in attacks:
        assert action.unavailable_reason == "weapon_slot_absent"
        assert action.outcome is SORegisterOutcome.RESOLVED
        assert action.event_type is None
        assert action.payload is None
    # The resolved row survives; only the intent is suppressed.
    resolved_attacks = [
        row
        for row in emission.sequence.register_resolved
        if row.card_id is not None and str(row.card_id) == "card.test.attack"
    ]
    assert len(resolved_attacks) == len(attacks)


def test_unfielded_weapon_slot_publishes_no_intent_spec() -> None:
    """The inert projection consumes no message id and produces no INTENT spec."""
    base = _runtime()
    assert base.card_round_runtime is not None
    emission = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=base.card_round_runtime,
        dealer=base.dealer,
        reducer=base.reducer,
    ).produce(
        seats=(_request("a", weapon_ids=()),),
        round_index=0,
        tick=3,
        causation_id="round.test.weapon-binding-specs",
    )
    intent_count = sum(action.event_type is not None for action in emission.actions)
    message_ids = tuple(UUID(int=index + 1) for index in range(len(emission.values) + intent_count))
    specs = build_card_round_event_specs(
        emission,
        root_causation_id=UUID(int=9999),
        seat_subjects={"a": ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a")},
        message_ids=message_ids,
    )
    fired = [
        spec
        for spec in specs
        if spec.stage == "INTENT" and spec.event_type is SOEventType.WEAPON_FIRE_INTENT
    ]
    assert not fired


def test_decide_only_pilot_is_never_an_implicit_programmer() -> None:
    base = _runtime()
    assert base.card_round_runtime is not None
    adapter = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=base.card_round_runtime,
        dealer=base.dealer,
        reducer=base.reducer,
        programmers={"a": _DecideOnly()},  # type: ignore[dict-item]
    )
    with pytest.raises(ProgrammingPilotError, match="decide-only"):
        adapter.produce(
            seats=(_request("a"),),
            round_index=0,
            tick=3,
            causation_id="round.test.no-decide-fallback",
            starting_deck_state=_known_starting_state(),
        )


def test_dependency_identity_mismatch_fails_closed() -> None:
    base = _runtime()
    assert base.card_round_runtime is not None
    with pytest.raises(CardRunnerAdapterError, match="exact CardRoundRuntime"):
        CardRunnerAdapter(
            registers_enabled=True,
            card_round_runtime=base.card_round_runtime,
            dealer=DealerCompute(),
            reducer=base.reducer,
        )
