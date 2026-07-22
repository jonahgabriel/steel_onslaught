"""End-to-end c11 Overpressure Cooldown proof over a full split-deck match.

Covers, in one deterministic sniper-vs-berserker match on foundry_60:
  - heat_capacity spawn wiring + reducer preservation (the sniper's folded
    boiler still carries the Bessemer-90 c11 ceiling at match end),
  - the allowlisted handler actually firing (forced-vent registers appear and
    peak sniper heat is controlled relative to the same match WITHOUT it),
  - terminal correctness (the match reaches a real terminal, never a runaway),
all from the canonical event ledger — no LLM, replay-exact.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cards.dealer import DealerCompute
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.cards.rules import default_rule_registry
from steel_onslaught.cards.split_deck import SplitDeckDealerAdapter
from steel_onslaught.contracts.application import ModelSOCardCatalogBinding
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.split_deck import (
    ModelSOCardDeckPolicy,
    ModelSODeckHandQuota,
    ModelSOSeatDeckPolicy,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.match.card_adapter import CardRunnerAdapter
from steel_onslaught.match.composition import (
    load_card_runtime_snapshot,
    load_loadout,
    load_match_contract_catalog,
)
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.match.state import ModelSOMatchState, SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from tests.runtime import FixedClock, SequentialIdentities

pytestmark = pytest.mark.integration

_CONTRACTS = Path("contracts_data")
_BRAWLER = "mech.a.01"
_SNIPER = "mech.b.01"
_VENT_CARD = "card.vent.emergency_vent"


class _RemainPilot:
    """Card mode drives the round; this only satisfies the presence check."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.0)],
        )


def _policy() -> ModelSOCardDeckPolicy:
    return ModelSOCardDeckPolicy(
        schema_version="0.1.0",
        kind="steel_onslaught.card_deck_policy",
        seats=(
            ModelSOSeatDeckPolicy(
                side="red",
                archetype="berserker",
                movement_deck_id="deck.movement.v1",
                weapon_deck_id="deck.weapon.v1",
                hand_quota=ModelSODeckHandQuota(movement=3, weapon=2),
                register_count=5,
            ),
            ModelSOSeatDeckPolicy(
                side="blue",
                archetype="sniper",
                movement_deck_id="deck.movement.v1",
                weapon_deck_id="deck.weapon.v1",
                hand_quota=ModelSODeckHandQuota(movement=2, weapon=3),
                register_count=5,
            ),
        ),
    )


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    return load_card_runtime_snapshot(
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=(_CONTRACTS / "cards").resolve(),
            decks_dir=(_CONTRACTS / "decks").resolve(),
            card_mode_enabled=True,
            card_cadence="paced",
            deck_policy=_policy(),
        )
    )


def _adapter(snapshot: ModelSOCardRuntimeSnapshot, *, handler_on: bool) -> CardRunnerAdapter:
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
        programmers=None,  # deterministic priority planner — no LLM
        rule_registry=default_rule_registry(),
        rule_handler_ids=("overpressure_cooldown",) if handler_on else (),
    )


def _run(seed: int, *, handler_on: bool) -> tuple[list[ModelSOEventEnvelope], ModelSOMatchState]:
    catalog = load_match_contract_catalog(_CONTRACTS)
    arena = catalog.arenas["foundry_60"]
    snapshot = _snapshot()
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    runner = MatchRunner(
        identity=MatchIdentity(f"match.c11.{seed}.{handler_on}", UUID(int=seed + 100)),
        seed=seed,
        loadout_a=load_loadout(_CONTRACTS / "loadouts/llm_qwen35_berserker.yaml"),
        loadout_b=load_loadout(_CONTRACTS / "loadouts/qwen35/sniper_ironclad.yaml"),
        bus=bus,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        catalog=catalog,
        arena=arena,
        pilots={_BRAWLER: _RemainPilot(), _SNIPER: _RemainPilot()},
        max_ticks=None,  # uncapped: sudden death bounds the match like the live demo
        card_runtime_snapshot=snapshot,
        card_adapter=_adapter(snapshot, handler_on=handler_on),
        card_cadence="paced",
    )
    final = runner.run()
    return events, final


def _peak_sniper_heat(events: list[ModelSOEventEnvelope]) -> int:
    peak = 0
    for event in events:
        if event.event_type is SOEventType.BOILER_UPDATED and event.subject.mech_id == _SNIPER:
            peak = max(peak, event.payload["heat_after"])
    return peak


def _sniper_vent_registers(events: list[ModelSOEventEnvelope]) -> int:
    return sum(
        1
        for event in events
        if event.event_type is SOEventType.REGISTER_RESOLVED
        and event.payload.get("seat") == "b"
        and event.payload.get("card_id") == _VENT_CARD
    )


def test_c11_match_reaches_terminal_and_preserves_heat_capacity() -> None:
    events, final = _run(seed=3, handler_on=True)

    # Terminal correctness: a real terminal, never a runaway abort.
    assert final.status is SOMatchStatus.ENDED
    assert final.end_reason is not None
    assert final.end_reason is not SOMatchEndReason.ABORTED_RUNAWAY

    # Spawn wiring + reducer preservation: the sniper's folded boiler still
    # carries the Bessemer-90 c11 ceiling (28) after a whole match of folds.
    sniper_boiler = final.mech_states[_SNIPER].boiler
    catalog = load_match_contract_catalog(_CONTRACTS)
    expected = catalog.boilers["boiler.industrial.bessemer_90"].heat_capacity
    assert sniper_boiler.heat_capacity == expected == 28

    # The lockout is event-sourced: heat never exceeds the rupture ceiling.
    assert _peak_sniper_heat(events) <= sniper_boiler.heat_rupture_threshold


def test_c11_handler_controls_sniper_heat_relative_to_no_handler() -> None:
    """The handler is load-bearing: on the SAME retuned economy it holds the
    sniper's peak heat below the no-handler run and spends vent registers."""

    on_events, _ = _run(seed=3, handler_on=True)
    off_events, _ = _run(seed=3, handler_on=False)

    on_peak = _peak_sniper_heat(on_events)
    off_peak = _peak_sniper_heat(off_events)
    redline = (
        load_match_contract_catalog(_CONTRACTS)
        .boilers["boiler.industrial.bessemer_90"]
        .redline_threshold
    )

    # Handler ON keeps peak heat strictly below the uncontrolled economy...
    assert on_peak < off_peak
    # ...and below the redline backstop (the plan-time lockout is the primary
    # gate; the redline register-lock stays a dormant backstop under c11).
    assert on_peak < redline
    # The controlled duty cycle actually spends vent registers.
    assert _sniper_vent_registers(on_events) > 0
