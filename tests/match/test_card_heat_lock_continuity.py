"""Heat-lock continuity across consecutive card rounds (cards-02).

``PLAN_COMMITTED`` carries only the registers a pilot was FREE to program, so a
heat-locked register is absent from it.  The runner used to carry that plan
forward verbatim as the next round's ``previous_plan``.  The first locked round
worked (the previous plan still programmed every register); the SECOND
consecutive locked round could not find a prior card for the locked index, and
the resulting ``RegisterPlanError`` escaped the adapter into the runner and
killed the match mid-fight.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope
from steel_onslaught.cards.registers import RegisterExecutionReducer, RegisterPlanError
from steel_onslaught.cards.round import CardRoundRuntime, carry_forward_plans
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.card_payloads import SORegisterOutcome
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.card_adapter import (
    CardRunnerAdapter,
    ModelSOCardRoundEmission,
    ModelSOCardSeatRequest,
)
from steel_onslaught.match.composition import load_card_catalog, load_loadout, load_pilot_registry
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.match.state import SOMatchStatus
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
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
        id="deck.test.heat_lock",
        display_name="Heat-lock test deck",
        hand_size=2,
        register_count=2,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=4) for card in cards.cards[:4]),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _adapter(snapshot: ModelSOCardRuntimeSnapshot) -> CardRunnerAdapter:
    dealer = DealerCompute()
    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    return CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=CardRoundRuntime(
            card_runtime_snapshot=snapshot,
            dealer=dealer,
            reducer=reducer,
            round_length=2,
        ),
        dealer=dealer,
        reducer=reducer,
    )


def _observation(seat: str, tick: int) -> ModelSOPilotObservation:
    boiler = ModelSOBoilerState(
        match_id="match.test.heat-lock",
        mech_id=f"mech.{seat}.01",
        tick=tick,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=85,
        heat_redline_threshold=80,
        heat_capacity=100,
        heat_rupture_threshold=100,
        heat_vent_rate=5,
        status_redline=True,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )
    return ModelSOPilotObservation(
        match_id="match.test.heat-lock",
        mech_id=f"mech.{seat}.01",
        player_id=f"player.{seat}",
        tick=tick,
        match_elapsed_ticks=tick,
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


def _seat(
    tick: int,
    *,
    lock_depth: int,
    previous_plan: Any | None,
) -> ModelSOCardSeatRequest:
    return ModelSOCardSeatRequest(
        seat="a",
        dealer_scope=ModelSODealerScope(
            match_id="match.test.heat-lock",
            match_seed=77,
            tick=tick,
            seat="a",
        ),
        pilot_observation=_observation("a", tick),
        initiative=1,
        lock_depth=lock_depth,
        previous_plan=previous_plan,
        weapon_ids=("weapon.test.primary",),
    )


def _round(
    adapter: CardRunnerAdapter,
    *,
    tick: int,
    round_index: int,
    lock_depth: int,
    previous_plan: Any | None,
    deck_state: Any | None,
) -> ModelSOCardRoundEmission:
    return adapter.produce(
        seats=(_seat(tick, lock_depth=lock_depth, previous_plan=previous_plan),),
        round_index=round_index,
        tick=tick,
        causation_id=f"round.heat-lock.{round_index}",
        starting_deck_state=deck_state,
    )


def test_two_consecutive_heat_locked_rounds_resolve() -> None:
    """Three rounds with the SAME register locked twice in a row must resolve."""
    snapshot = _snapshot()
    adapter = _adapter(snapshot)

    first = _round(
        adapter, tick=1, round_index=0, lock_depth=0, previous_plan=None, deck_state=None
    )
    assert first.sequence is not None
    carried = carry_forward_plans(first.sequence)

    second = _round(
        adapter,
        tick=2,
        round_index=1,
        lock_depth=1,
        previous_plan=carried["a"],
        deck_state=first.deck_state,
    )
    assert second.sequence is not None
    locked_second = [
        row
        for row in second.sequence.register_resolved
        if row.outcome is SORegisterOutcome.HEAT_LOCKED
    ]
    assert [row.register_index for row in locked_second] == [1]

    # The committed plan for round 2 programs ONLY register 0 — this is exactly
    # the value the runner used to carry forward, and it cannot answer "what
    # was in register 1?".
    assert [r.register_index for r in second.sequence.plan_committed[0].registers] == [0]

    third = _round(
        adapter,
        tick=3,
        round_index=2,
        lock_depth=1,
        previous_plan=carry_forward_plans(second.sequence)["a"],
        deck_state=second.deck_state,
    )
    assert third.sequence is not None
    locked_third = [
        row
        for row in third.sequence.register_resolved
        if row.outcome is SORegisterOutcome.HEAT_LOCKED
    ]
    assert [row.register_index for row in locked_third] == [1]
    # The repeat chains through the second round's resolved row, not through a
    # plan that never contained the locked register.
    assert locked_third[0].card_id == locked_second[0].card_id


def test_carrying_plan_committed_forward_is_the_regression() -> None:
    """The pre-fix carry-forward still fails loudly — the bug was real."""
    snapshot = _snapshot()
    adapter = _adapter(snapshot)

    first = _round(
        adapter, tick=1, round_index=0, lock_depth=0, previous_plan=None, deck_state=None
    )
    assert first.sequence is not None
    second = _round(
        adapter,
        tick=2,
        round_index=1,
        lock_depth=1,
        previous_plan=first.sequence.plan_committed[0],
        deck_state=first.deck_state,
    )
    assert second.sequence is not None

    with pytest.raises((RegisterPlanError, ValueError), match="no prior card to repeat"):
        _round(
            adapter,
            tick=3,
            round_index=2,
            lock_depth=1,
            # The pre-fix runner assignment:
            # {plan.seat: plan for plan in sequence.plan_committed}
            previous_plan=second.sequence.plan_committed[0],
            deck_state=second.deck_state,
        )


class _Ledger:
    def __init__(self) -> None:
        self.events: list[ModelSOEventEnvelope] = []

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return (event for event in self.events if event.match_id == match_id)


def test_runner_survives_consecutive_redlined_card_rounds() -> None:
    """A seat redlined across every card round must not kill the match.

    ``lock_depth`` is derived from ``boiler.status_redline``, so a seat that
    stays redlined locks the same register round after round.  The redline flag
    is forced here after each fold so the lock is guaranteed rather than
    hoped for; the assertion is simply that the match reaches a terminal
    instead of dying on an escaped ``RegisterPlanError``.
    """
    runtime = runtime_dependencies()
    factory = EventFactory(clock=FixedClock(), identities=SequentialIdentities())
    bus = InProcessEventBus()
    ledger = _Ledger()
    bus.subscribe(ledger.append)
    loadout_a = load_loadout(_LOADOUT_A)
    loadout_b = load_loadout(_LOADOUT_B)
    registry = load_pilot_registry(_ROOT / "pilots")
    snapshot = _snapshot()
    runner = MatchRunner(
        identity=MatchIdentity("match.test.heat-lock-runner", UUID(int=901)),
        seed=17,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        bus=bus,
        event_factory=factory,
        catalog=runtime.catalog,
        arena=runtime.arena,
        pilots={
            "mech.a.01": pilot_from_spec(registry.resolve(loadout_a)),
            "mech.b.01": pilot_from_spec(registry.resolve(loadout_b)),
        },
        max_ticks=6,
        card_runtime_snapshot=snapshot,
        card_adapter=_adapter(snapshot),
    )

    def force_redline(event: ModelSOEventEnvelope) -> None:
        if event.event_type is not SOEventType.MATCH_TICK:
            return
        states = runner.fold._mech_states
        mech = states.get("mech.a.01")
        if mech is None or mech.boiler.status_redline:
            return
        states["mech.a.01"] = mech.model_copy(
            update={"boiler": mech.boiler.model_copy(update={"status_redline": True})}
        )

    bus.subscribe(force_redline)

    final = runner.run()

    assert final.status is SOMatchStatus.ENDED
    locked = [
        event
        for event in ledger.events
        if event.event_type is SOEventType.REGISTER_RESOLVED
        and event.payload["outcome"] == SORegisterOutcome.HEAT_LOCKED.value
        and event.payload["seat"] == "a"
    ]
    # More than one locked round is the whole point: the first one always
    # worked, the second is what used to raise.
    assert len({event.tick for event in locked}) >= 2
