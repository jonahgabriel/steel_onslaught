"""Cross-boundary seat-identity proof for the split-deck demo overlay.

Two independent unit suites cannot prove this property: the defect was an
overlay whose ``deck_policy`` declared ``red=berserker``/``blue=sniper`` while
both ``programmers`` entries resolved to the same berserker pilot spec.  Every
individual layer was internally consistent; only the seam between the shipped
overlay, ``build_card_programmers``, and the durable
``LLM_COMPLETION_REQUESTED`` evidence shows the mirror match.  This module
therefore drives the real ``contracts_data`` overlay end to end and reads the
persona identity back off the emitted payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.player_selection import Side
from steel_onslaught.events.card_payloads import SOPlanSource
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.llm.effect import LedgerLlmCompletionObserver
from steel_onslaught.llm.schemas import (
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
    ModelSOOpenAIResponseChoice,
    ModelSOOpenAIResponseMessage,
    ModelSOOpenAIResponseUsage,
)
from steel_onslaught.match.composition import (
    SeatIdentityError,
    build_card_programmers,
    build_llm_dependencies,
    load_application_overlay,
    load_card_runtime_snapshot,
    load_pilot_registry,
)
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
)
from tests.runtime import FixedClock, SequentialIdentities

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_DEMO_OVERLAY = _ROOT / "contracts_data/overlays/tactical_split_v1_qwen.yaml"
_CORRELATION_ID = UUID("4c2d5f8a-1111-4d2e-9a55-000000000001")


class _UnusedSecretResolver:
    """Satisfy the overlay's ``injected`` resolver kind for its keyless provider.

    The split overlay declares ``secret_resolver.kind: injected`` so the browser
    catalog launch can bind the catalog's secret-bearing GLM seats. Its own sole
    provider (``qwen35``) is keyless (``secret_ref: null``), so composition never
    calls ``resolve`` here — but it does require a resolver capability to exist.
    Any actual resolution attempt is a wiring bug, so this one fails loudly.
    """

    def resolve(self, reference: object) -> str:
        raise AssertionError(f"keyless split overlay resolved a secret: {reference!r}")


class _PlanTransport:
    """Answer every completion with a plan built from the prompt's own hand."""

    def __init__(self) -> None:
        self.personas: list[str] = []

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        del url, headers, timeout_seconds
        prompt = json.loads(request.messages[1].content)
        free_indices = prompt["registers"]["free_indices"]
        # ``hand`` is the dealt multiset in order; ``legal_hand`` is deduped.
        hand = [entry["card_id"] for entry in prompt["hand"]]
        registers = [
            {"register_index": index, "card_id": card_id}
            for index, card_id in zip(free_indices, hand, strict=True)
        ]
        content = json.dumps(
            {"registers": registers, "confidence": 0.7, "rationale": "seat identity fixture"}
        )
        return ModelSOOpenAIChatResponse(
            choices=(
                ModelSOOpenAIResponseChoice(
                    message=ModelSOOpenAIResponseMessage(content=content),
                    finish_reason="stop",
                ),
            ),
            usage=ModelSOOpenAIResponseUsage(prompt_tokens=11, completion_tokens=7),
            model="seat-identity-fixture",
        )


def _pilot_observation(
    *, mech_id: str, player_id: str, enemy_mech_id: str
) -> ModelSOPilotObservation:
    boiler = ModelSOBoilerState(
        match_id="match.seat_identity",
        mech_id=mech_id,
        tick=3,
        pressure_current=30,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=10,
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
        match_id="match.seat_identity",
        mech_id=mech_id,
        player_id=player_id,
        tick=3,
        match_elapsed_ticks=3,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.primary",
                damage=10,
                range=15,
                pressure_cost=3,
                heat_generated=2,
                cooldown_remaining_ticks=0,
            )
        ],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=4, y=6),
        hp_percent=91.0,
        under_sensor_lock=False,
        has_line_of_sight_to_enemy=True,
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id=enemy_mech_id,
                tick=3,
                distance_estimate=9.0,
                confidence=0.7,
                heat_estimate=35.0,
            )
        ],
    )


def _split_observation(
    *,
    overlay: ModelSOApplicationOverlay,
    snapshot: ModelSOCardRuntimeSnapshot,
    side: Side,
) -> ModelSOProgrammingObservation:
    """Build one seat's split hand from the overlay's own declared quotas."""

    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    assert card_binding.deck_policy is not None
    seat = card_binding.deck_policy.for_side(side)
    movement = tuple(snapshot.require_deck(str(seat.movement_deck_id)).card_multiset())
    weapon = tuple(snapshot.require_deck(str(seat.weapon_deck_id)).card_multiset())
    hand = movement[: seat.hand_quota.movement] + weapon[: seat.hand_quota.weapon]
    mech_id = f"mech.{side}.01"
    enemy_mech_id = "mech.blue.01" if side == "red" else "mech.red.01"
    return ModelSOProgrammingObservation(
        pilot_observation=_pilot_observation(
            mech_id=mech_id,
            player_id=f"player.{side}",
            enemy_mech_id=enemy_mech_id,
        ),
        card_runtime_snapshot=snapshot,
        seat=side,
        hand=hand,
        free_indices=tuple(range(seat.register_count)),
        register_count=seat.register_count,
        hand_deck_ids=(str(seat.movement_deck_id), str(seat.weapon_deck_id)),
    )


def _requested_personas_by_seat(overlay: ModelSOApplicationOverlay) -> dict[str, str]:
    """Drive both overlay seats and read persona identity off the ledger events."""

    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    snapshot = load_card_runtime_snapshot(card_binding)
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    events: list[ModelSOEventEnvelope] = []
    llm = build_llm_dependencies(
        overlay, http_transport=_PlanTransport(), secret_resolver=_UnusedSecretResolver()
    )
    try:
        observer = LedgerLlmCompletionObserver(
            correlation_id=_CORRELATION_ID,
            event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
            emit=events.append,
        )
        programmers = build_card_programmers(
            card_binding.programmers,
            registry=registry,
            llm=llm,
            deck_policy=card_binding.deck_policy,
            observer=observer,
            correlation_id=_CORRELATION_ID,
        )
        personas: dict[str, str] = {}
        for side in ("red", "blue"):
            before = len(events)
            plan = programmers[side].program(
                _split_observation(overlay=overlay, snapshot=snapshot, side=side)
            )
            assert plan.seat == side
            # A live seat must have been decided by the provider, never by the
            # deterministic planner standing in for it.
            assert plan.plan_source is SOPlanSource.LLM
            requested = [
                event
                for event in events[before:]
                if event.event_type is SOEventType.LLM_COMPLETION_REQUESTED
            ]
            assert len(requested) == 1
            personas[side] = str(requested[0].payload["persona_id"])
        return personas
    finally:
        llm.close()


@pytest.mark.integration
def test_split_demo_overlay_drives_two_distinct_seat_personas() -> None:
    """The shipped demo overlay must not run berserker-vs-berserker."""

    overlay = load_application_overlay(_DEMO_OVERLAY)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    assert card_binding.deck_policy is not None
    archetypes = {str(seat.side): seat.archetype for seat in card_binding.deck_policy.seats}
    assert archetypes == {"red": "berserker", "blue": "sniper"}

    personas = _requested_personas_by_seat(overlay)

    assert personas["red"] != personas["blue"]
    assert personas["blue"] == "sniper"
    assert personas["red"] == "berserker"
    # The declared seat archetype is what the provider was actually asked as.
    assert personas == archetypes


@pytest.mark.integration
def test_collapsed_seat_overlay_fails_closed_before_binding_a_provider() -> None:
    """Re-introducing the mirror binding must fail composition, not run."""

    overlay = load_application_overlay(_DEMO_OVERLAY)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    collapsed = card_binding.model_copy(
        update={
            "programmers": tuple(
                programmer.model_copy(update={"pilot_spec_id": "pilot.llm.qwen35"})
                for programmer in card_binding.programmers
            )
        }
    )
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    llm = build_llm_dependencies(
        overlay, http_transport=_PlanTransport(), secret_resolver=_UnusedSecretResolver()
    )
    try:
        with pytest.raises(SeatIdentityError, match="does not match the declared seat archetype"):
            build_card_programmers(
                collapsed.programmers,
                registry=registry,
                llm=llm,
                deck_policy=collapsed.deck_policy,
            )
    finally:
        llm.close()


@pytest.mark.integration
def test_same_persona_on_both_seats_fails_closed() -> None:
    """Archetype-matched but identical seats are still a mirror match."""

    overlay = load_application_overlay(_DEMO_OVERLAY)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    assert card_binding.deck_policy is not None
    mirrored_policy = card_binding.deck_policy.model_copy(
        update={
            "seats": tuple(
                seat.model_copy(update={"archetype": "berserker"})
                for seat in card_binding.deck_policy.seats
            )
        }
    )
    mirrored = card_binding.model_copy(
        update={
            "programmers": tuple(
                programmer.model_copy(update={"pilot_spec_id": "pilot.llm.qwen35"})
                for programmer in card_binding.programmers
            )
        }
    )
    registry = load_pilot_registry(overlay.contracts.pilot_registry_dir)
    llm = build_llm_dependencies(
        overlay, http_transport=_PlanTransport(), secret_resolver=_UnusedSecretResolver()
    )
    try:
        with pytest.raises(SeatIdentityError, match="distinct card programmer identities"):
            build_card_programmers(
                mirrored.programmers,
                registry=registry,
                llm=llm,
                deck_policy=mirrored_policy,
            )
    finally:
        llm.close()
