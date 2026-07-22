"""Phase A over-deal proofs: deal more cards than you program, then SELECT.

The split-deck card runtime already carries every mechanism selection needs
(the priority planner slices the hand to the free registers, the plan/hand
validators accept ``chosen ⊆ hand``, and the reducer programs exactly the free
registers).  What forced "every dealt card is played" was purely the config:
``hand_quota.hand_size == register_count``.  These tests exercise the opposite —
an over-dealt hand (8 cards) programmed into fewer registers (5) — end to end:
the deal counts, a legal strict-subset program, the unselected cards folding to
discard, replay-exactness, deck conservation, prompt legibility, the shipped
overlay, and a full match reaching a terminal.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope
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
from steel_onslaught.events.card_payloads import SORegisterOutcome
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.programming import LLMProgrammingPilot
from steel_onslaught.llm.schemas import LlmResponse, LlmUsage, ModelSOLlmCompletionRequest
from steel_onslaught.match.card_adapter import CardRunnerAdapter, ModelSOCardSeatRequest
from steel_onslaught.match.composition import (
    RuntimeDependencies,
    assemble_match_with_dependencies,
    build_card_runner_adapter,
    load_application_overlay,
    load_loadout,
    load_match_contract_catalog,
    load_pilot_registry,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation, program_for_seat
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)
from steel_onslaught.projections.leaderboard.protocol import (
    LeaderboardRepository,
    ModelSOLeaderboardEntry,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import FixedClock, SequentialIdentities, pilot_from_spec

pytestmark = pytest.mark.unit

_ROOT = Path("contracts_data")
_OVERDEAL_OVERLAY = _ROOT / "overlays" / "tactical_split_overdeal_v1_qwen.yaml"
_CONTROL_OVERLAY = _ROOT / "overlays" / "tactical_split_v1_qwen.yaml"

# Distinct priorities across both piles so the deterministic priority planner
# has a single, predictable top-5.  Movement: 50/40/30/20; weapon: 45/35/25/15.
# Sorted desc the top five are advance(50) fire_primary(45) flank_left(40)
# fire_secondary(35) flank_right(30); the three dropped are the tail
# reposition(20) vent_low(15) — see ``_DROPPED_WHEN_ALL_DEALT``.
_MOVEMENT_CARDS = (
    ("card.od.advance", "toward_enemy", 50),
    ("card.od.flank_left", "left", 40),
    ("card.od.flank_right", "right", 30),
    ("card.od.reposition", "away_from_enemy", 20),
)
_WEAPON_CARDS = (
    ("card.od.fire_primary", 0, 45),
    ("card.od.fire_secondary", 0, 35),
    ("card.od.vent_high", None, 25),
    ("card.od.vent_low", None, 15),
)
# When both 4-card piles are dealt whole (count-1 decks), the hand is all eight
# cards; the priority planner keeps the top five and drops these three.
_DROPPED_WHEN_ALL_DEALT = frozenset({"card.od.vent_high", "card.od.reposition", "card.od.vent_low"})


def _movement_card(card_id: str, direction: str, priority: int) -> ModelSOCard:
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=SOCardCategory.MOVEMENT,
        priority=priority,
        heat_cost=0,
        effect=ModelSOCardEffect(direction=cast(Any, direction), speed="full"),
    )


def _weapon_card(card_id: str, weapon_slot: int | None, priority: int) -> ModelSOCard:
    if weapon_slot is None:
        category = SOCardCategory.VENT
        effect = ModelSOCardEffect()
    else:
        category = SOCardCategory.ATTACK
        effect = ModelSOCardEffect(weapon_slot=weapon_slot)
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


def _catalog() -> ModelSOCardCatalog:
    cards = (
        *(_movement_card(cid, direction, pri) for cid, direction, pri in _MOVEMENT_CARDS),
        *(_weapon_card(cid, slot, pri) for cid, slot, pri in _WEAPON_CARDS),
    )
    # The catalog contract requires cards sorted by id.
    return ModelSOCardCatalog(cards=tuple(sorted(cards, key=lambda card: str(card.id))))


def _snapshot(*, copies: int) -> ModelSOCardRuntimeSnapshot:
    """Build a split snapshot; ``copies`` sizes each pile for the deal cadence."""

    catalog = _catalog()
    movement = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.od.movement",
        display_name="over-deal movement",
        hand_size=4,
        register_count=4,
        cards=tuple(
            ModelSODeckEntry(card_id=cid, count=copies) for cid, _dir, _pri in _MOVEMENT_CARDS
        ),
    )
    weapon = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.od.weapon",
        display_name="over-deal weapon",
        hand_size=4,
        register_count=4,
        cards=tuple(
            ModelSODeckEntry(card_id=cid, count=copies) for cid, _slot, _pri in _WEAPON_CARDS
        ),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=catalog,
        decks=(movement, weapon),
        selected_deck_id=None,
        content_sha256=canonical_card_runtime_sha256(catalog, (movement, weapon)),
    )


def _policy() -> ModelSOCardDeckPolicy:
    """The shipped over-deal shape: deal 4+4=8, program 5, for both seats."""

    def seat(side: Side, archetype: str) -> ModelSOSeatDeckPolicy:
        return ModelSOSeatDeckPolicy(
            side=side,
            archetype=archetype,
            movement_deck_id="deck.od.movement",
            weapon_deck_id="deck.od.weapon",
            hand_quota=ModelSODeckHandQuota(movement=4, weapon=4),
            register_count=5,
        )

    return ModelSOCardDeckPolicy(
        schema_version="0.1.0",
        kind="steel_onslaught.card_deck_policy",
        seats=(seat("red", "berserker"), seat("blue", "sniper")),
    )


def _pilot_observation(seat: str) -> ModelSOPilotObservation:
    boiler = ModelSOBoilerState(
        match_id="match.overdeal",
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
    return ModelSOPilotObservation(
        match_id="match.overdeal",
        mech_id=f"mech.{seat}",
        player_id=f"player.{seat}",
        tick=0,
        match_elapsed_ticks=0,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.od.primary",
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


def _request(seat: str, side: Side) -> ModelSOCardSeatRequest:
    return ModelSOCardSeatRequest(
        seat=seat,
        side=side,
        dealer_scope=ModelSODealerScope(
            match_id="match.overdeal",
            match_seed=4242,
            tick=0,
            seat=seat,
        ),
        pilot_observation=_pilot_observation(seat),
        initiative=0 if side == "red" else 1,
        weapon_ids=("weapon.od.primary",),
    )


def _adapter(
    *,
    copies: int = 1,
    programmers: Any = None,
) -> CardRunnerAdapter:
    snapshot = _snapshot(copies=copies)
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
        programmers=programmers,
    )


# --------------------------------------------------------------------------- #
# 1. The shipped overlay actually over-deals; the control stays deal==program. #
# --------------------------------------------------------------------------- #


def test_overdeal_overlay_deals_more_than_it_programs() -> None:
    overlay = load_application_overlay(_OVERDEAL_OVERLAY)
    binding = overlay.contracts.card_catalog
    assert binding is not None and binding.deck_policy is not None
    for seat in binding.deck_policy.seats:
        assert seat.hand_quota.hand_size == 8
        assert seat.hand_quota.movement == 4
        assert seat.hand_quota.weapon == 4
        assert seat.register_count == 5
        # The whole point of Phase A: strictly more dealt than programmed.
        assert seat.hand_quota.hand_size > seat.register_count


def test_control_overlay_still_deals_exactly_what_it_programs() -> None:
    overlay = load_application_overlay(_CONTROL_OVERLAY)
    binding = overlay.contracts.card_catalog
    assert binding is not None and binding.deck_policy is not None
    for seat in binding.deck_policy.seats:
        # Control = the current behavior: no selection, every card is played.
        assert seat.hand_quota.hand_size == seat.register_count == 5


# --------------------------------------------------------------------------- #
# 2. The round deals 8 and programs 5 per seat.                                #
# --------------------------------------------------------------------------- #


def test_overdeal_round_deals_eight_and_programs_five() -> None:
    adapter = _adapter()
    emission = adapter.produce(
        seats=(_request("mech.red", "red"), _request("mech.blue", "blue")),
        round_index=0,
        tick=0,
        causation_id="overdeal-round-0",
    )
    assert emission.sequence is not None
    hand_by_seat = {p.seat: p for p in emission.sequence.hand_dealt}
    plan_by_seat = {p.seat: p for p in emission.sequence.plan_committed}
    for seat in ("mech.red", "mech.blue"):
        hand = hand_by_seat[seat]
        assert hand.hand_size == 8
        assert hand.partitions is not None
        assert len(hand.partitions.movement.card_ids) == 4
        assert len(hand.partitions.weapon.card_ids) == 4
        assert hand.register_count == 5
        # Programmed strictly fewer registers than the cards dealt.
        assert len(plan_by_seat[seat].registers) == 5
        assert len(plan_by_seat[seat].registers) < hand.hand_size
    resolved = [
        row
        for row in emission.sequence.register_resolved
        if row.outcome is SORegisterOutcome.RESOLVED
    ]
    # Five real (card-bearing) resolutions per seat, none AUTO_REMAIN.
    assert len(resolved) == 10
    assert all(
        row.outcome is SORegisterOutcome.RESOLVED for row in emission.sequence.register_resolved
    )


# --------------------------------------------------------------------------- #
# 3. Selection is a legal strict subset AND it drops cards sensibly.           #
# --------------------------------------------------------------------------- #


def test_priority_planner_programs_legal_subset_and_drops_lowest_priority() -> None:
    """The gate question: does over-deal prune sensibly, or randomly?

    The deterministic planner keeps the highest-priority cards and drops the
    tail — a legal strict subset of the dealt hand, proving a card CAN be
    dropped and that the drop is sensible (lowest priority), not random.
    """

    snapshot = _snapshot(copies=1)
    dealer = DealerCompute()
    split = SplitDeckDealerAdapter(snapshot=snapshot, policy=_policy(), dealer=dealer)
    scope = ModelSODealerScope(match_id="match.overdeal", match_seed=99, tick=0, seat="mech.red")
    deal = split.deal_for_side(side="red", scope=scope)
    hand = deal.hand
    assert len(hand) == 8  # 4 movement + 4 weapon, over-dealt

    observation = ModelSOProgrammingObservation(
        pilot_observation=_pilot_observation("mech.red"),
        card_runtime_snapshot=snapshot,
        seat="mech.red",
        hand=hand,
        free_indices=(0, 1, 2, 3, 4),
        register_count=5,
        hand_deck_ids=("deck.od.movement", "deck.od.weapon"),
    )
    plan = program_for_seat(None, observation)

    programmed = tuple(reg.card_id for reg in plan.registers)
    assert len(programmed) == 5
    # Legal strict subset: every programmed card is in the hand, and fewer than
    # the hand was programmed.
    assert set(programmed).issubset(set(hand))
    assert len(programmed) < len(hand)
    # A card WAS dropped: the unprogrammed remainder is non-empty.
    dropped = set(hand) - set(programmed)
    assert dropped, "over-deal must leave at least one unprogrammed card"
    # Sensible, not random: the whole 8-card hand is dealt (count-1 piles), so
    # exactly the three lowest-priority cards are dropped.
    assert dropped == set(_DROPPED_WHEN_ALL_DEALT)


# --------------------------------------------------------------------------- #
# 4. Unselected cards fold to discard and the deck multiset is conserved.      #
# --------------------------------------------------------------------------- #


def test_unselected_cards_are_discarded_and_deck_is_conserved() -> None:
    adapter = _adapter()
    emission = adapter.produce(
        seats=(_request("mech.red", "red"),),
        round_index=0,
        tick=0,
        causation_id="overdeal-discard",
    )
    assert emission.sequence is not None
    hand = next(p for p in emission.sequence.hand_dealt if p.seat == "mech.red")
    plan = next(p for p in emission.sequence.plan_committed if p.seat == "mech.red")
    discarded = next(d for d in emission.sequence.cards_discarded if d.seat == "mech.red")

    programmed = {reg.card_id for reg in plan.registers}
    dealt = set(hand.card_ids)
    unselected = dealt - programmed
    assert unselected, "over-deal must produce unselected cards"

    # Every dealt card (played AND unselected) leaves the hand as discard.
    assert set(discarded.card_ids) == dealt
    # The unselected cards are specifically present in the discard set.
    assert unselected.issubset(set(discarded.card_ids))

    # Deck conservation: each partition's persisted state (draw + discard)
    # accounts for exactly the full pile multiset it was dealt from.
    split_state = next(s.state for s in emission.split_deck_states if s.seat == "mech.red")
    snapshot = _snapshot(copies=1)
    movement_deck = snapshot.require_deck("deck.od.movement")
    weapon_deck = snapshot.require_deck("deck.od.weapon")
    movement_pile = (*split_state.movement.draw_pile, *split_state.movement.discard_pile)
    weapon_pile = (*split_state.weapon.draw_pile, *split_state.weapon.discard_pile)
    assert sorted(movement_pile) == sorted(movement_deck.card_multiset())
    assert sorted(weapon_pile) == sorted(weapon_deck.card_multiset())


# --------------------------------------------------------------------------- #
# 5. The over-dealt round is byte-for-byte replay-exact.                       #
# --------------------------------------------------------------------------- #


def test_overdeal_round_is_replay_exact() -> None:
    adapter = _adapter()
    seats = (_request("mech.red", "red"), _request("mech.blue", "blue"))
    first = adapter.produce(seats=seats, round_index=0, tick=0, causation_id="overdeal-replay")
    second = adapter.produce(seats=seats, round_index=0, tick=0, causation_id="overdeal-replay")
    # Same seed + same inputs -> identical emission, including the selection and
    # the discard fold.
    assert first == second
    assert first.sequence is not None
    # The recorded sequence re-derives from its own plans/contexts (no drift).
    adapter.card_round_runtime.verify_replay(first.sequence)  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# 6. The provider prompt makes the "choose which to program" decision legible. #
# --------------------------------------------------------------------------- #


class _SubsetProgrammingClient:
    """Program the FIRST ``program_count`` legal-hand cards, dropping the rest.

    Deliberately selects a strict subset so the fixture itself exercises the
    over-deal decision rather than assuming hand length equals register count.
    """

    def __init__(self) -> None:
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        prompt = json.loads(request.user_prompt)
        free_indices = prompt["registers"]["free_indices"]
        hand_ids = [card["card_id"] for card in prompt["hand"]]
        chosen = hand_ids[: len(free_indices)]
        registers = [
            {"register_index": index, "card_id": card_id}
            for index, card_id in zip(free_indices, chosen, strict=True)
        ]
        return LlmResponse(
            text=json.dumps({"registers": registers, "confidence": 0.9, "rationale": "subset"}),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=3, cost_usd=0.0),
            model="overdeal-fixture",
            finish_reason="stop",
        )


def test_overdeal_prompt_surfaces_the_selection_decision() -> None:
    client = _SubsetProgrammingClient()
    persona = Persona("qwen35", "Qwen35", "Choose a tactical plan.", 0.2)
    adapter = _adapter(programmers={"red": LLMProgrammingPilot(client=client, persona=persona)})

    emission = adapter.produce(
        seats=(_request("mech.red", "red"),),
        round_index=0,
        tick=1,
        causation_id="overdeal-prompt",
    )
    assert emission.sequence is not None
    assert len(client.requests) == 1
    request = client.requests[0]

    prompt = json.loads(request.user_prompt)
    selection = prompt["selection"]
    assert selection["hand_size"] == 8
    assert selection["program_count"] == 5
    assert selection["discard_unprogrammed"] == 3
    assert selection["over_dealt"] is True

    # The code-owned instruction block explicitly names the over-deal decision.
    assert "OVER-DEALT" in request.system_prompt

    # The provider legally programmed a strict subset (5 of 8).
    plan = next(p for p in emission.sequence.plan_committed if p.seat == "mech.red")
    hand = next(h for h in emission.sequence.hand_dealt if h.seat == "mech.red")
    assert len(plan.registers) == 5
    assert set(reg.card_id for reg in plan.registers).issubset(set(hand.card_ids))
    assert len(plan.registers) < hand.hand_size


# --------------------------------------------------------------------------- #
# 7. A full over-deal match reaches a terminal and replays exactly.           #
# --------------------------------------------------------------------------- #


class _Ledger:
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

    def read_match_ids(self) -> Iterator[str]:
        return iter(sorted({event.match_id for event in self.events}))

    def contains_match(self, match_id: str) -> bool:
        return any(event.match_id == match_id for event in self.events)

    def read_at(
        self,
        match_id: str,
        tick: int,
        *,
        event_types: frozenset[SOEventType] | None,
    ) -> Iterator[ModelSOEventEnvelope]:
        return iter(
            event
            for event in self.events
            if event.match_id == match_id
            and event.tick == tick
            and (event_types is None or event.event_type in event_types)
        )


class _Leaderboard(LeaderboardRepository):
    def on_match_scored(self, payload: Any) -> None:
        del payload

    def top_n(self, n: int) -> list[ModelSOLeaderboardEntry]:
        del n
        return []

    def player_record(self, player_id: str) -> dict[str, int]:
        del player_id
        return {"wins": 0, "losses": 0, "draws": 0}

    def draw_count(self) -> int:
        return 0


class _Closer:
    def close(self) -> None:
        return


@pytest.mark.integration
def test_full_overdeal_match_reaches_terminal_and_replays() -> None:
    """End to end: a paced split over-deal match reaches MATCH_ENDED and replays.

    The deterministic priority planner (no LLM) programs 5 of the 8 dealt cards
    every round, so the match is hermetic and byte-stable while still proving
    that the over-deal selection path drives a real match to a terminal.
    """

    runtime_root = load_match_contract_catalog(_ROOT)
    registry = load_pilot_registry(_ROOT / "pilots")
    # Large enough piles to sustain the paced cadence for the capped match.
    snapshot = _snapshot(copies=6)
    adapter = build_card_runner_adapter(
        snapshot=snapshot,
        programmers=None,  # deterministic priority planner -> subset selection
        split_policy=_policy(),
    )
    identities = SequentialIdentities()
    event_factory = EventFactory(clock=FixedClock(), identities=identities)
    dependencies = RuntimeDependencies(
        bus=InProcessEventBus(),
        ledger=_Ledger(),
        leaderboard=_Leaderboard(),
        clock=FixedClock(),
        identities=identities,
        event_factory=event_factory,
        catalog=runtime_root,
        arena=runtime_root.arenas["open_field"],
        pilot_registry=registry,
        pilot_factory=cast(Any, object()),
        closer=_Closer(),
        card_catalog=snapshot.card_catalog,
        card_runtime_snapshot=snapshot,
        card_adapter=adapter,
        card_cadence="paced",
    )
    red = load_loadout(_ROOT / "loadouts/example_aggressive_light.yaml")
    blue = load_loadout(_ROOT / "loadouts/example_predictive_heavy.yaml")
    pilots = {
        "mech.red.01": pilot_from_spec(registry.resolve(red)),
        "mech.blue.01": pilot_from_spec(registry.resolve(blue)),
    }
    identity = MatchIdentity(
        match_id="match.overdeal.full",
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
    )
    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=red,
        blue=blue,
        seed=17,
        max_ticks=12,
        identity=identity,
        pilots_override=pilots,
    )

    final = stack.runner.run()
    assert final.status.value == "ended"

    ledger = cast(_Ledger, dependencies.ledger)
    event_types = [event.event_type for event in ledger.events]
    assert SOEventType.MATCH_STARTED in event_types
    assert SOEventType.MATCH_ENDED in event_types

    # Selection actually happened in the live match: at least one hand was
    # over-dealt (8) while its committed plan programmed only the 5 registers.
    hand_dealt = [e for e in ledger.events if e.event_type is SOEventType.HAND_DEALT]
    plan_committed = [e for e in ledger.events if e.event_type is SOEventType.PLAN_COMMITTED]
    assert hand_dealt, "a card round must have dealt at least one hand"
    assert any(event.payload["hand_size"] == 8 for event in hand_dealt)
    assert plan_committed
    assert all(len(event.payload["registers"]) == 5 for event in plan_committed)

    # replay == live: the terminal folds back deterministically from the ledger.
    replay = ReplayEngine(
        ledger,
        stack.match_id,
        catalog=dependencies.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=snapshot,
        validate_card_events=True,
    )
    assert replay.reconstruct_at_tick(final.tick) == final
