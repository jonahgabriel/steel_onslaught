"""Card runtime snapshot identity and passive match-start provenance tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
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
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import match_runner, runtime_dependencies


class _MemoryLedger:
    def __init__(self, events: list[ModelSOEventEnvelope]) -> None:
        self.events = events

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return (event for event in self.events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return (
            event for event in self.events if event.match_id == match_id and event.tick > after_tick
        )


def _snapshot(
    *, priority: int = 100, selected: str | None = "deck.test.standard"
) -> ModelSOCardRuntimeSnapshot:
    card = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.test.advance",
        display_name="Advance",
        category=SOCardCategory.MOVEMENT,
        priority=priority,
        heat_cost=0,
        effect=ModelSOCardEffect(direction="toward_enemy", speed="full"),
    )
    cards = ModelSOCardCatalog(cards=(card,))
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.standard",
        display_name="Standard",
        hand_size=1,
        register_count=1,
        cards=(ModelSODeckEntry(card_id=card.id, count=1),),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=selected,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _run_started(
    snapshot: ModelSOCardRuntimeSnapshot,
) -> tuple[ModelSOEventEnvelope, list[ModelSOEventEnvelope], object]:
    events: list[ModelSOEventEnvelope] = []
    bus = InProcessEventBus()
    bus.subscribe(events.append)
    runner, runtime = match_runner(
        bus=bus,
        match_id="match.01JABCDE0123456789ABCDEFGX",
        seed=7,
        loadout_a=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        loadout_b=load_loadout(Path("contracts_data/loadouts/example_predictive_heavy.yaml")),
        max_ticks=1,
        card_runtime_snapshot=snapshot,
    )
    runner.run()
    return (
        next(event for event in events if event.event_type is SOEventType.MATCH_STARTED),
        events,
        runtime,
    )


@pytest.mark.unit
def test_replay_retains_snapshot_identity_and_validates_start_provenance() -> None:
    runtime = runtime_dependencies()
    snapshot = _snapshot()
    event, _events, _runner_runtime = _run_started(snapshot)
    replay = ReplayEngine(
        _MemoryLedger([event]),
        event.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        card_runtime_snapshot=snapshot,
    )

    assert replay.card_runtime_snapshot is snapshot
    assert replay.card_catalog is snapshot.card_catalog
    assert replay.reconstruct_at_tick(0).tick == 0


@pytest.mark.unit
def test_replay_rejects_missing_or_mismatched_snapshot_provenance() -> None:
    runtime = runtime_dependencies()
    snapshot = _snapshot()
    started, _events, _runner_runtime = _run_started(snapshot)
    missing_event_raw = started.model_dump(mode="json")
    missing_event_raw["payload"].pop("card_runtime_provenance")
    started = ModelSOEventEnvelope.model_validate(missing_event_raw)
    missing = ReplayEngine(
        _MemoryLedger([started]),
        started.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        card_runtime_snapshot=snapshot,
    )
    with pytest.raises(ValueError, match="does not match"):
        missing.reconstruct_at_tick(0)

    mismatched = ReplayEngine(
        _MemoryLedger([_run_started(snapshot)[0]]),
        started.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        card_runtime_snapshot=_snapshot(priority=999),
    )
    with pytest.raises(ValueError, match="does not match"):
        mismatched.reconstruct_at_tick(0)


@pytest.mark.unit
def test_snapshot_rejects_tampered_content_digest() -> None:
    snapshot = _snapshot()
    raw = snapshot.model_dump(mode="python")
    raw["content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="content_sha256"):
        ModelSOCardRuntimeSnapshot.model_validate(raw)


@pytest.mark.integration
def test_runner_persists_passive_card_runtime_provenance_without_activation() -> None:
    events: list[ModelSOEventEnvelope] = []
    bus = InProcessEventBus()
    bus.subscribe(events.append)
    snapshot = _snapshot()
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.01JABCDE0123456789ABCDEFGX",
        seed=7,
        loadout_a=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        loadout_b=load_loadout(Path("contracts_data/loadouts/example_predictive_heavy.yaml")),
        max_ticks=1,
        card_runtime_snapshot=snapshot,
    )
    runner.run()

    started = next(event for event in events if event.event_type is SOEventType.MATCH_STARTED)
    provenance = snapshot.provenance
    assert provenance is not None
    assert started.payload["card_runtime_provenance"] == provenance.model_dump(mode="json")
    assert not any(
        event.event_type
        in {
            SOEventType.HAND_DEALT,
            SOEventType.PLAN_COMMITTED,
            SOEventType.REGISTER_RESOLVED,
            SOEventType.CARDS_DISCARDED,
        }
        for event in events
    )
