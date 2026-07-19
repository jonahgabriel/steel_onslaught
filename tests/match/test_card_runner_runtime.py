"""Opt-in card-round composition proofs for ``MatchRunner``."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal
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
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import FixedClock, SequentialIdentities, pilot_from_spec, runtime_dependencies

pytestmark = pytest.mark.integration

_ROOT = Path("contracts_data")
_LOADOUT_A = _ROOT / "loadouts/example_aggressive_light.yaml"
_LOADOUT_B = _ROOT / "loadouts/example_predictive_heavy.yaml"


class _ReplayLedger:
    def __init__(self, events: list[ModelSOEventEnvelope]) -> None:
        self._events = events

    def append(self, event: ModelSOEventEnvelope) -> None:
        self._events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return (event for event in self._events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return (
            event
            for event in self._events
            if event.match_id == match_id and event.tick > after_tick
        )


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


def _run(
    *,
    card_enabled: bool,
    max_ticks: int = 2,
    card_cadence: Literal["atomic", "paced"] = "atomic",
    force_decisive: bool = False,
    terminal_observer: Callable[[ModelSOEventEnvelope, list[ModelSOEventEnvelope]], None]
    | None = None,
) -> list[ModelSOEventEnvelope]:
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
        card_cadence=card_cadence,
    )
    if force_decisive:
        original_resolve = runner._resolve_intent
        forced = False

        def resolve_and_force(intent: ModelSOEventEnvelope) -> None:
            nonlocal forced
            original_resolve(intent)
            if forced or runner.fold.state.status is not SOMatchStatus.RUNNING:
                return
            victim = next(iter(runner.fold.state.living_mechs()), None)
            if victim is None:
                return
            bus.publish(
                runner._make_subject_event(
                    SOEventType.MECH_DESTROYED,
                    tick=runner.fold.state.tick,
                    mech=victim,
                    payload={"cause": "test_decisive", "source_mech_id": None},
                )
            )
            forced = True

        runner._resolve_intent = resolve_and_force  # type: ignore[method-assign]
    if terminal_observer is not None:
        bus.subscribe(lambda event: terminal_observer(event, events))
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


def test_replay_engine_default_no_card_path_remains_unvalidated() -> None:
    events = _run(card_enabled=False)
    runtime = runtime_dependencies()
    replay = ReplayEngine(
        _ReplayLedger(events),
        "match.test.card-runner",
        catalog=runtime.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=_snapshot(),
    )
    assert replay.validated_card_rounds == ()
    assert replay.reconstruct_at_tick(2).status is SOMatchStatus.ENDED


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


def test_replay_engine_validates_complete_card_stream_once_and_preserves_state() -> None:
    events = _run(card_enabled=True, max_ticks=3)
    runtime = runtime_dependencies()
    card_snapshot = _snapshot()
    default = ReplayEngine(
        _ReplayLedger(events),
        "match.test.card-runner",
        catalog=runtime.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=card_snapshot,
    )
    validated = ReplayEngine(
        _ReplayLedger(events),
        "match.test.card-runner",
        catalog=runtime.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=card_snapshot,
        validate_card_events=True,
    )
    assert len(validated.validated_card_rounds) == 2
    assert validated.reconstruct_at_tick(3) == default.reconstruct_at_tick(3)


def test_paced_card_round_latches_one_register_per_tick_and_replays_by_root() -> None:
    events = _run(card_enabled=True, max_ticks=5, card_cadence="paced")
    lifecycle_types = {
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    }
    lifecycle = [event for event in events if event.event_type in lifecycle_types]
    hands = [event for event in lifecycle if event.event_type is SOEventType.HAND_DEALT]
    discards = [event for event in lifecycle if event.event_type is SOEventType.CARDS_DISCARDED]
    registers = [event for event in lifecycle if event.event_type is SOEventType.REGISTER_RESOLVED]
    assert len(hands) == len(discards) == 4
    assert {event.tick for event in hands} == {1, 3}
    assert {event.tick for event in discards} == {2, 4}
    assert {event.tick for event in registers} == {1, 2, 3, 4}
    assert all(
        len({event.payload["register_index"] for event in registers if event.tick == tick}) == 1
        for tick in (1, 2, 3, 4)
    )

    runtime = runtime_dependencies()
    replay = ReplayEngine(
        _ReplayLedger(events),
        "match.test.card-runner",
        catalog=runtime.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=_snapshot(),
        validate_card_events=True,
    )
    assert len(replay.validated_card_rounds) == 2
    assert {event.tick for event in replay.validated_card_rounds[0].events} == {1, 2}
    assert {event.tick for event in replay.validated_card_rounds[1].events} == {3, 4}


def test_paced_card_round_cancels_with_terminal_discard_on_max_tick_boundary() -> None:
    events = _run(card_enabled=True, max_ticks=2, card_cadence="paced")
    lifecycle_types = {
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    }
    lifecycle = [event for event in events if event.event_type in lifecycle_types]
    assert lifecycle
    assert {event.event_type for event in lifecycle} == {
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    }
    assert {
        event.payload["register_index"]
        for event in lifecycle
        if event.event_type is SOEventType.REGISTER_RESOLVED
    } == {0}
    discards = [event for event in lifecycle if event.event_type is SOEventType.CARDS_DISCARDED]
    assert {event.payload["reason"] for event in discards} == {"cancelled:max_ticks"}

    runtime = runtime_dependencies()
    replay = ReplayEngine(
        _ReplayLedger(events),
        "match.test.card-runner",
        catalog=runtime.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=_snapshot(),
        validate_card_events=True,
    )
    assert len(replay.validated_card_rounds) == 1
    assert replay.validated_card_rounds[0].cancelled is True


def test_paced_card_round_cancels_after_decisive_death_with_causal_discard() -> None:
    events = _run(
        card_enabled=True,
        max_ticks=5,
        card_cadence="paced",
        force_decisive=True,
    )
    lifecycle_types = {
        SOEventType.HAND_DEALT,
        SOEventType.PLAN_COMMITTED,
        SOEventType.REGISTER_RESOLVED,
        SOEventType.CARDS_DISCARDED,
    }
    lifecycle = [event for event in events if event.event_type in lifecycle_types]
    discards = [event for event in lifecycle if event.event_type is SOEventType.CARDS_DISCARDED]
    assert discards
    assert {event.payload["reason"] for event in discards} == {"cancelled:decisive_death"}
    ended_index = next(
        index for index, event in enumerate(events) if event.event_type is SOEventType.MATCH_ENDED
    )
    assert all(events.index(discard) < ended_index for discard in discards)

    seen_messages: set[UUID] = set()
    for index, event in enumerate(lifecycle):
        if index > 0:
            assert event.envelope.causation_id in seen_messages
        seen_messages.add(event.envelope.message_id)

    runtime = runtime_dependencies()
    replay = ReplayEngine(
        _ReplayLedger(events),
        "match.test.card-runner",
        catalog=runtime.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=_snapshot(),
        validate_card_events=True,
    )
    assert replay.validated_card_rounds[0].cancelled is True


def test_paced_card_round_closes_before_scoring_observes_victory() -> None:
    terminal_snapshots: list[tuple[SOEventType, ...]] = []

    def observe(event: ModelSOEventEnvelope, events: list[ModelSOEventEnvelope]) -> None:
        if event.event_type is SOEventType.VICTORY_DECLARED:
            terminal_snapshots.append(tuple(row.event_type for row in events))

    _run(
        card_enabled=True,
        max_ticks=5,
        card_cadence="paced",
        force_decisive=True,
        terminal_observer=observe,
    )

    assert terminal_snapshots
    snapshot = terminal_snapshots[0]
    assert SOEventType.CARDS_DISCARDED in snapshot
    assert snapshot.index(SOEventType.CARDS_DISCARDED) < snapshot.index(
        SOEventType.VICTORY_DECLARED
    )


@pytest.mark.parametrize("tamper", ["payload", "order", "provenance"])
def test_replay_engine_card_validation_rejects_tampered_stream(tamper: str) -> None:
    events = _run(card_enabled=True, max_ticks=2)
    card_snapshot = _snapshot()
    card_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type
        in {
            SOEventType.HAND_DEALT,
            SOEventType.PLAN_COMMITTED,
            SOEventType.REGISTER_RESOLVED,
            SOEventType.CARDS_DISCARDED,
        }
    ]
    changed = list(events)
    if tamper == "payload":
        index = next(
            index
            for index in card_indexes
            if changed[index].event_type is SOEventType.REGISTER_RESOLVED
        )
        payload = dict(changed[index].payload)
        payload["action"] = "unknown_action"
        changed[index] = changed[index].model_copy(update={"payload": payload})
    elif tamper == "order":
        first, second = card_indexes[:2]
        changed[first], changed[second] = changed[second], changed[first]
    else:
        index = next(
            index
            for index, event in enumerate(changed)
            if event.event_type is SOEventType.MATCH_STARTED
        )
        payload = dict(changed[index].payload)
        provenance = dict(payload["card_runtime_provenance"])
        provenance["content_sha256"] = "0" * 64
        payload["card_runtime_provenance"] = provenance
        changed[index] = changed[index].model_copy(update={"payload": payload})
    runtime = runtime_dependencies()
    with pytest.raises((CardRoundReplayError, ValueError)):
        ReplayEngine(
            _ReplayLedger(changed),
            "match.test.card-runner",
            catalog=runtime.catalog,
            event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
            card_runtime_snapshot=card_snapshot,
            validate_card_events=True,
        )
