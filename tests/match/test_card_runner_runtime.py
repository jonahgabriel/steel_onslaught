"""Opt-in card-round composition proofs for ``MatchRunner``."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cards.dealer import DealerCompute
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.card_adapter import CardRunnerAdapter
from steel_onslaught.match.composition import load_card_catalog, load_loadout, load_pilot_registry
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.match.state import SOMatchStatus
from steel_onslaught.replay.card_round import (
    CardRoundReplayError,
    parse_card_round_events,
    validate_card_round_events,
)
from tests.runtime import FixedClock, SequentialIdentities, pilot_from_spec, runtime_dependencies

pytestmark = pytest.mark.integration

_ROOT = Path("contracts_data")
_LOADOUT_A = _ROOT / "loadouts/example_aggressive_light.yaml"
_LOADOUT_B = _ROOT / "loadouts/example_predictive_heavy.yaml"


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = load_card_catalog(
        type(
            "CardBinding",
            (),
            {
                "cards_dir": (_ROOT / "cards").resolve(),
                "decks_dir": (_ROOT / "cards").resolve(),
                "deck_id": None,
                "card_mode_enabled": False,
            },
        )()
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.runner",
        display_name="Runner test deck",
        hand_size=2,
        register_count=2,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in cards.cards[:4]),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _run(*, card_enabled: bool, max_ticks: int = 2) -> list[ModelSOEventEnvelope]:
    runtime = runtime_dependencies()
    identities = SequentialIdentities()
    factory = EventFactory(clock=FixedClock(), identities=identities)
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    loadout_a = load_loadout(_LOADOUT_A)
    loadout_b = load_loadout(_LOADOUT_B)
    registry = load_pilot_registry(_ROOT / "pilots")
    pilots = {
        "mech.a.01": pilot_from_spec(registry.resolve(loadout_a)),
        "mech.b.01": pilot_from_spec(registry.resolve(loadout_b)),
    }
    snapshot = _snapshot()
    adapter = None
    if card_enabled:
        dealer = DealerCompute()
        reducer = RegisterExecutionReducer(snapshot.card_catalog)
        card_runtime = CardRoundRuntime(
            card_runtime_snapshot=snapshot,
            dealer=dealer,
            reducer=reducer,
            round_length=2,
        )
        adapter = CardRunnerAdapter(
            registers_enabled=True,
            card_round_runtime=card_runtime,
            dealer=dealer,
            reducer=reducer,
        )
    runner = MatchRunner(
        identity=MatchIdentity("match.test.card-runner", UUID(int=900)),
        seed=17,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        bus=bus,
        event_factory=factory,
        catalog=runtime.catalog,
        arena=runtime.arena,
        pilots=pilots,
        max_ticks=max_ticks,
        card_runtime_snapshot=snapshot,
        card_adapter=adapter,
    )
    assert runner.run().status is SOMatchStatus.ENDED
    return events


def test_default_runner_has_no_card_events() -> None:
    events = _run(card_enabled=False)
    assert not {
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    }.intersection(event.event_type for event in events)


def test_opt_in_card_events_have_subjects_and_causal_intents() -> None:
    events = _run(card_enabled=True)
    card_events = [
        event
        for event in events
        if event.event_type
        in {
            SOEventType.HAND_DEALT,
            SOEventType.PLAN_COMMITTED,
            SOEventType.REGISTER_RESOLVED,
            SOEventType.CARDS_DISCARDED,
            SOEventType.MOVE_INTENT,
            SOEventType.WEAPON_FIRE_INTENT,
            SOEventType.MODE_SWITCH_INTENT,
            SOEventType.VENT_INTENT,
        }
    ]
    assert card_events
    assert {event.subject.mech_id for event in card_events} == {"mech.a.01", "mech.b.01"}
    tick_by_event = {
        event.envelope.message_id: event
        for event in events
        if event.event_type is SOEventType.MATCH_TICK
    }
    first_hand_by_tick: set[int] = set()
    for event in card_events:
        assert event.envelope.causation_id is not None
        if event.event_type is SOEventType.HAND_DEALT:
            if event.tick not in first_hand_by_tick:
                assert event.envelope.causation_id in tick_by_event
                first_hand_by_tick.add(event.tick)
            else:
                assert event.envelope.causation_id in {
                    prior.envelope.message_id for prior in card_events if prior.tick == event.tick
                }
    assert any(event.event_type is SOEventType.MOVEMENT_RESOLVED for event in events)
    assert any(event.event_type is SOEventType.WEAPON_FIRED for event in events)


def test_card_rounds_repeat_with_explicit_deck_state() -> None:
    events = _run(card_enabled=True, max_ticks=3)
    hands = [event for event in events if event.event_type is SOEventType.HAND_DEALT]
    discards = [event for event in events if event.event_type is SOEventType.CARDS_DISCARDED]
    assert len(hands) == 4
    assert len(discards) == 4
    assert {event.tick for event in hands} == {1, 2}
    assert all(event.payload["deck_id"] == "deck.test.runner" for event in hands)


def test_card_round_replay_validates_and_rejects_tampering() -> None:
    events = _run(card_enabled=True, max_ticks=2)
    card_types = {
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    }
    card_events = [event for event in events if event.tick == 1 and event.event_type in card_types]
    snapshot = _snapshot()
    replay = validate_card_round_events(
        card_events,
        snapshot=snapshot,
        expected_match_id="match.test.card-runner",
    )
    assert len(replay.register_resolved) == 4
    parsed = parse_card_round_events(
        card_events,
        snapshot=snapshot,
        expected_match_id="match.test.card-runner",
    )
    tick_root = next(event for event in events if event.event_type is SOEventType.MATCH_TICK)
    assert parsed.events[0].causation_id == tick_root.envelope.message_id

    register = next(
        index
        for index, event in enumerate(card_events)
        if event.event_type is SOEventType.REGISTER_RESOLVED
    )
    tampered_payload = dict(card_events[register].payload)
    tampered_payload["action"] = "remain"
    tampered = list(card_events)
    tampered[register] = card_events[register].model_copy(update={"payload": tampered_payload})
    with pytest.raises(CardRoundReplayError):
        validate_card_round_events(tampered, snapshot=snapshot)
