"""Phase 2 U-GATE wiring proof: the utility pile deals AND deploys in a live match.

This is the cross-boundary regression the Phase 2 scaffold was missing.  It
drives the ENTIRE arm end to end, from the shipped overlay to the ledger:

  overlay ``tactical_split_overdeal_utility_v1_qwen.yaml``
    -> utility pile is dealt into the over-dealt hand (HAND_DEALT carries a
       third ``utility`` partition alongside movement/weapon)
    -> a pilot can PROGRAM a utility card into one of the 5 registers
       (SOPilotAction.DEPLOY_UTILITY)
    -> the Stage-A card adapter projects that register into a
       UTILITY_DEPLOY_INTENT
    -> the runner resolves it via the overlay-selected utility handler pack into
       a canonical UTILITY_DEPLOYED that lands in the ledger, its causation
       chaining from the programmed register's intent.

The programmer is a deterministic fixture that *chooses* the counterplay card
(the real "spend a register on smoke instead of a shot" decision), so the proof
is a genuine pilot selection, not a hand-built intent.  Nothing here touches a
balance knob: the assertion is only that the deploy event is produced and folded,
per the U-GATE "no balance knob touched" requirement.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.programming import LLMProgrammingPilot
from steel_onslaught.llm.schemas import LlmResponse, LlmUsage, ModelSOLlmCompletionRequest
from steel_onslaught.match.composition import (
    RuntimeDependencies,
    assemble_match_with_dependencies,
    build_card_runner_adapter,
    load_application_overlay,
    load_card_runtime_snapshot,
    load_loadout,
    load_match_contract_catalog,
    load_pilot_registry,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.projections.leaderboard.protocol import (
    LeaderboardRepository,
    ModelSOLeaderboardEntry,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import FixedClock, SequentialIdentities, pilot_from_spec

pytestmark = pytest.mark.unit

_ROOT = Path("contracts_data")
_UTILITY_OVERLAY = _ROOT / "overlays" / "tactical_split_overdeal_utility_v1_qwen.yaml"

_UTILITY_PREFIX = "card.utility."


class _UtilityFirstProgrammingClient:
    """A pilot that spends its first registers on the dealt counterplay cards.

    It reads the real over-deal programming prompt and programs the utility
    cards in the hand FIRST, then fills the remaining registers with the other
    dealt cards.  This is a legal strict subset of the over-dealt hand and it
    deterministically exercises the "choose to deploy counterplay" decision so
    every round produces at least one DEPLOY_UTILITY register whenever a utility
    card was dealt.
    """

    def __init__(self) -> None:
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        prompt = json.loads(request.user_prompt)
        free_indices = prompt["registers"]["free_indices"]
        hand_ids = [card["card_id"] for card in prompt["hand"]]
        utility_first = [cid for cid in hand_ids if cid.startswith(_UTILITY_PREFIX)] + [
            cid for cid in hand_ids if not cid.startswith(_UTILITY_PREFIX)
        ]
        chosen = utility_first[: len(free_indices)]
        registers = [
            {"register_index": index, "card_id": card_id}
            for index, card_id in zip(free_indices, chosen, strict=True)
        ]
        return LlmResponse(
            text=json.dumps(
                {"registers": registers, "confidence": 0.9, "rationale": "deploy counterplay"}
            ),
            usage=LlmUsage(prompt_tokens=5, completion_tokens=3, cost_usd=0.0),
            model="utility-fixture",
            finish_reason="stop",
        )


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
def test_utility_pile_deals_and_deploys_in_a_live_match() -> None:
    """The shipped utility overlay deals a utility pile that a pilot deploys.

    Every seam is real: the deck policy, cards, and utility handler pack all
    come from ``tactical_split_overdeal_utility_v1_qwen.yaml``; the match runs
    through the production composition + runner; and the terminal ledger carries
    a canonical UTILITY_DEPLOYED whose causation chains from the programmed
    register that produced its UTILITY_DEPLOY_INTENT.
    """

    overlay = load_application_overlay(_UTILITY_OVERLAY)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None and card_binding.deck_policy is not None
    split_policy = card_binding.deck_policy
    # The overlay is the source of the utility pile: each seat deals a positive
    # utility quota from a declared utility deck.
    assert all(
        seat.utility_deck_id is not None and seat.hand_quota.utility > 0
        for seat in split_policy.seats
    )
    # ...and the source of the handler selection (defect 3): the overlay names
    # the resolution pack, so the runner's fail-closed ``select`` is driven by
    # the typed overlay rather than a hardcoded default.
    utility_pack = overlay.contracts.utility_handler_pack
    assert utility_pack is not None
    utility_handler_ids = tuple(utility_pack.handler_ids)

    snapshot = load_card_runtime_snapshot(card_binding)
    runtime_root = load_match_contract_catalog(_ROOT)
    registry = load_pilot_registry(_ROOT / "pilots")

    persona = Persona("qwen35", "Qwen35", "Choose a tactical plan.", 0.2)
    programmers = {
        "red": LLMProgrammingPilot(client=_UtilityFirstProgrammingClient(), persona=persona),
        "blue": LLMProgrammingPilot(client=_UtilityFirstProgrammingClient(), persona=persona),
    }
    adapter = build_card_runner_adapter(
        snapshot=snapshot,
        programmers=programmers,
        split_policy=split_policy,
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
        arena=runtime_root.arenas[overlay.contracts.arena_id],
        pilot_registry=registry,
        pilot_factory=cast(Any, object()),
        closer=_Closer(),
        card_catalog=snapshot.card_catalog,
        card_runtime_snapshot=snapshot,
        card_adapter=adapter,
        card_cadence="paced",
        utility_handler_ids=utility_handler_ids,
    )
    red = load_loadout(_ROOT / "loadouts/example_aggressive_light.yaml")
    blue = load_loadout(_ROOT / "loadouts/example_predictive_heavy.yaml")
    pilots = {
        "mech.red.01": pilot_from_spec(registry.resolve(red)),
        "mech.blue.01": pilot_from_spec(registry.resolve(blue)),
    }
    identity = MatchIdentity(
        match_id="match.utility.deploy",
        correlation_id=UUID("55555555-5555-5555-5555-555555555555"),
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
    events = ledger.events

    # 1. The utility pile was actually dealt: a HAND_DEALT carries the third
    #    utility partition inside the over-dealt (10-card) hand.
    hand_dealt = [e for e in events if e.event_type is SOEventType.HAND_DEALT]
    assert hand_dealt, "a card round must have dealt at least one hand"
    utility_hands = [
        e for e in hand_dealt if e.payload.get("partitions", {}).get("utility") is not None
    ]
    assert utility_hands, "the utility pile was never dealt into a live hand"
    sample = utility_hands[0]
    assert sample.payload["hand_size"] == 10  # 4 movement + 4 weapon + 2 utility
    utility_partition = sample.payload["partitions"]["utility"]
    assert utility_partition["partition"] == "utility"
    assert utility_partition["requested_count"] == 2
    assert all(cid.startswith(_UTILITY_PREFIX) for cid in utility_partition["card_ids"])

    # 2. A pilot PROGRAMMED a utility card into a register (DEPLOY_UTILITY was
    #    offered and taken), and it RESOLVED as a deploy_utility action.
    plan_committed = [e for e in events if e.event_type is SOEventType.PLAN_COMMITTED]
    programmed_utility = [
        reg["card_id"]
        for e in plan_committed
        for reg in e.payload["registers"]
        if reg["card_id"].startswith(_UTILITY_PREFIX)
    ]
    assert programmed_utility, "no utility card was ever programmed into a register"
    register_resolved = [e for e in events if e.event_type is SOEventType.REGISTER_RESOLVED]
    assert any(e.payload.get("action") == "deploy_utility" for e in register_resolved), (
        "no register resolved as a deploy_utility action"
    )

    # 3. The Stage-A adapter projected it into a UTILITY_DEPLOY_INTENT.
    intents = [e for e in events if e.event_type is SOEventType.UTILITY_DEPLOY_INTENT]
    assert intents, "the programmed utility card produced no UTILITY_DEPLOY_INTENT"

    # 4. The runner resolved it into a canonical UTILITY_DEPLOYED in the ledger,
    #    its causation chaining from the intent that the register produced.
    deployed = [e for e in events if e.event_type is SOEventType.UTILITY_DEPLOYED]
    assert deployed, "no UTILITY_DEPLOYED landed in the ledger"
    intent_message_ids = {e.envelope.message_id for e in intents}
    for event in deployed:
        assert event.causation_id in intent_message_ids, (
            "UTILITY_DEPLOYED must be caused by a UTILITY_DEPLOY_INTENT"
        )
        assert event.payload["utility_kind"] in {"smoke", "chaff", "flares"}
        assert event.payload["kind"] == "steel_onslaught.utility_deployed"
        assert "origin" in event.payload  # runner stamped the deploying cell

    # 5. replay == live: the utility deploy folds back deterministically.
    replay = ReplayEngine(
        ledger,
        stack.match_id,
        catalog=dependencies.catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        card_runtime_snapshot=snapshot,
        validate_card_events=True,
    )
    assert replay.reconstruct_at_tick(final.tick) == final
