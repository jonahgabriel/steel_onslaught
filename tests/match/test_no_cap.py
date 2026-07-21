"""No-cap live/replay convergence and explicit-cap regression proofs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import ModelSOMatchStartedPayload
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.replay.engine import ReplayEngine
from tests.fixtures.event_samples import build_sample_envelopes
from tests.runtime import match_runner

_RED_PASSIVE = Path("contracts_data/loadouts/proof_red_defensive_passive.yaml")
_BLUE_PASSIVE = Path("contracts_data/loadouts/proof_blue_defensive_passive.yaml")


@pytest.mark.unit
def test_match_started_cap_key_is_required_but_nullable() -> None:
    payload = dict(build_sample_envelopes()[SOEventType.MATCH_STARTED].payload)
    payload["max_ticks"] = None
    assert ModelSOMatchStartedPayload.model_validate(payload).max_ticks is None
    payload.pop("max_ticks")
    with pytest.raises(ValidationError, match="max_ticks"):
        ModelSOMatchStartedPayload.model_validate(payload)


class _MemoryLedger:
    def __init__(self) -> None:
        self.events: list[ModelSOEventEnvelope] = []

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return iter(event for event in self.events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return iter(
            event for event in self.events if event.match_id == match_id and event.tick > after_tick
        )


@pytest.mark.integration
def test_no_cap_uses_arena_pressure_and_replays_exactly() -> None:
    """Symmetric passive loadouts converge to a DRAW, not to a side.

    ``proof_red_defensive_passive`` and ``proof_blue_defensive_passive`` are
    byte-for-byte identical apart from their ids: same chassis, same boiler,
    same pilot template, no weapons, no sensors.  Neither can damage the other,
    so the only attrition is the arena's sudden-death pulse — which hits both
    mechs for the same amount on the same tick.  The only correct terminal is
    ``draw_mutual_destruction``.

    This assertion previously read ``LAST_MECH_STANDING``, which encoded the
    match-runner-fold-01 side bias as an expectation: sudden death damaged and
    destroyed mechs one at a time in ``mech_id`` order and broke on the first
    kill, so ``mech.a.01`` always died before ``mech.b.01`` absorbed the same
    lethal pulse and ``player.b`` always won at full HP.
    """
    bus = InProcessEventBus()
    ledger = _MemoryLedger()
    bus.subscribe(ledger.append)
    runner, runtime = match_runner(
        bus=bus,
        match_id="match.no-cap.pressure",
        seed=17,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=None,
    )

    live = runner.run()

    assert live.status is SOMatchStatus.ENDED
    assert live.end_reason is SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION
    assert live.winner_id is None
    assert [mech.hp for mech in live.mech_states.values()] == [0, 0]
    assert not [mech for mech in live.mech_states.values() if mech.alive]
    assert live.max_ticks is None
    start_tick = runtime.arena.sudden_death_start_tick
    assert start_tick is not None
    assert live.tick > start_tick
    pressure = [
        event
        for event in ledger.events
        if event.event_type is SOEventType.DAMAGE_APPLIED
        and event.payload.get("cause") == "sudden_death"
    ]
    assert pressure
    assert all(event.payload.get("source_mech_id") is None for event in pressure)
    destroyed = [event for event in ledger.events if event.event_type is SOEventType.MECH_DESTROYED]
    assert destroyed
    assert all(event.payload.get("source_mech_id") is None for event in destroyed)
    replay = ReplayEngine(
        ledger,
        live.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
    )
    assert replay.reconstruct_at_tick(live.tick) == live


@pytest.mark.integration
def test_explicit_cap_remains_draw_backstop_without_pressure() -> None:
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.explicit-cap.draw",
        seed=17,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=60,
    )

    live = runner.run()

    assert live.status is SOMatchStatus.ENDED
    assert live.tick == 60
    assert live.max_ticks == 60
    assert live.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert not [
        event
        for event in events
        if event.event_type is SOEventType.DAMAGE_APPLIED
        and event.payload.get("cause") == "sudden_death"
    ]
