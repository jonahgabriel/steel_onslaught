"""Pure card-aware programming observation and adapter tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

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
from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SOPlanSource,
)
from steel_onslaught.pilots.programming import (
    ModelSOProgrammingObservation,
    ProgrammingPilotError,
    program_for_seat,
)
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
)

pytestmark = pytest.mark.unit


def _card(card_id: str, *, category: SOCardCategory, priority: int) -> ModelSOCard:
    effect = (
        ModelSOCardEffect(direction="toward_enemy", speed="full")
        if category is SOCardCategory.MOVEMENT
        else ModelSOCardEffect()
    )
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


def _snapshot(*, selected_deck_id: str | None = "deck.test.standard") -> ModelSOCardRuntimeSnapshot:
    cards = ModelSOCardCatalog(
        cards=(
            _card("card.test.advance", category=SOCardCategory.MOVEMENT, priority=20),
            _card("card.test.advance_alt", category=SOCardCategory.MOVEMENT, priority=20),
            _card("card.test.vent", category=SOCardCategory.VENT, priority=10),
        )
    )
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.standard",
        display_name="Test standard",
        hand_size=3,
        register_count=3,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in cards.cards),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=selected_deck_id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _observation(
    snapshot: ModelSOCardRuntimeSnapshot,
    *,
    hand: tuple[str, ...] = (
        "card.test.vent",
        "card.test.advance",
        "card.test.advance_alt",
    ),
    free_indices: tuple[int, ...] = (0, 1, 2),
) -> ModelSOProgrammingObservation:
    boiler = ModelSOBoilerState(
        match_id="match.test",
        mech_id="mech.red.01",
        tick=0,
        pressure_current=40,
        pressure_maximum=60,
        regeneration_per_tick=5,
        heat_current=0,
        heat_redline_threshold=80,
        heat_capacity=100,
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
    pilot_observation = ModelSOPilotObservation(
        match_id="match.test",
        mech_id="mech.red.01",
        player_id="player.red",
        tick=0,
        match_elapsed_ticks=0,
        boiler=boiler,
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.test",
                damage=1,
                range=1,
                pressure_cost=1,
                heat_generated=1,
                cooldown_remaining_ticks=0,
            ),
        ],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=1, y=1),
        hp_percent=100.0,
        under_sensor_lock=False,
        enemy_observations=[],
    )
    return ModelSOProgrammingObservation(
        pilot_observation=pilot_observation,
        card_runtime_snapshot=snapshot,
        seat="red",
        hand=hand,
        free_indices=free_indices,
    )


def test_observation_is_frozen_and_resolves_cards_from_shared_snapshot() -> None:
    snapshot = _snapshot()
    observation = _observation(snapshot)

    assert observation.model_config["frozen"] is True
    assert observation.card_runtime_snapshot is snapshot
    assert tuple(card.id for card in observation.hand_cards) == observation.hand
    assert observation.deck is snapshot.selected_deck
    with pytest.raises(ValidationError):
        observation.seat = "blue"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"snapshot": _snapshot(selected_deck_id=None)}, "explicitly selected deck"),
        (
            {
                "hand": (
                    "card.test.missing",
                    "card.test.advance",
                    "card.test.vent",
                )
            },
            "not available",
        ),
        ({"free_indices": (1, 0)}, "ascending"),
        ({"free_indices": (0, 0)}, "unique"),
        ({"free_indices": (3,)}, "below deck register_count"),
        ({"hand": ("card.test.advance",), "free_indices": (0, 1)}, "must be programmed"),
    ],
)
def test_observation_fails_closed_for_unbound_or_invalid_programming_inputs(
    kwargs: dict[str, object], error: str
) -> None:
    snapshot = kwargs.pop("snapshot", _snapshot())
    with pytest.raises((ValueError, ValidationError), match=error):
        _observation(snapshot, **kwargs)  # type: ignore[arg-type]


def test_priority_adapter_is_deterministic_and_uses_plan_payload() -> None:
    observation = _observation(_snapshot())
    first = program_for_seat(None, observation)
    second = program_for_seat(None, observation)

    assert first == second
    assert isinstance(first, ModelSOPlanCommittedPayload)
    assert first.seat == "red"
    assert tuple(register.register_index for register in first.registers) == (0, 1, 2)
    assert tuple(register.card_id for register in first.registers) == (
        "card.test.advance",
        "card.test.advance_alt",
        "card.test.vent",
    )


class _ExplicitProgrammer:
    def program(self, observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
        return ModelSOPlanCommittedPayload(
            seat=observation.seat,
            registers=tuple(
                ModelSOPlanRegister(register_index=index, card_id=card_id)
                for index, card_id in zip(
                    observation.free_indices,
                    reversed(observation.hand),
                    strict=True,
                )
            ),
            rationale="explicit",
            confidence=0.75,
        )


def test_explicit_programmer_is_validated_without_decide_fallback() -> None:
    observation = _observation(_snapshot())
    plan = program_for_seat(_ExplicitProgrammer(), observation)
    assert tuple(register.card_id for register in plan.registers) == (
        "card.test.advance_alt",
        "card.test.advance",
        "card.test.vent",
    )

    class DecideOnly:
        def decide(self, _observation: ModelSOPilotObservation) -> object:
            raise AssertionError("decide-only pilot must never be called")

    with pytest.raises(ProgrammingPilotError, match="decide-only"):
        program_for_seat(DecideOnly(), observation)  # type: ignore[arg-type]

    class NonCallableProgram:
        program = None

    with pytest.raises(ProgrammingPilotError, match="must be callable"):
        program_for_seat(NonCallableProgram(), observation)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_plan",
    [
        ModelSOPlanCommittedPayload(
            seat="blue",
            registers=(ModelSOPlanRegister(register_index=0, card_id="card.test.vent"),),
            rationale=None,
            confidence=1.0,
        ),
        ModelSOPlanCommittedPayload(
            seat="red",
            registers=(ModelSOPlanRegister(register_index=1, card_id="card.test.vent"),),
            rationale=None,
            confidence=1.0,
        ),
        ModelSOPlanCommittedPayload(
            seat="red",
            registers=(
                ModelSOPlanRegister(register_index=0, card_id="card.test.vent"),
                ModelSOPlanRegister(register_index=1, card_id="card.test.vent"),
                ModelSOPlanRegister(register_index=2, card_id="card.test.vent"),
            ),
            rationale=None,
            confidence=1.0,
        ),
    ],
)
def test_explicit_programmer_output_is_strictly_rejected(
    bad_plan: ModelSOPlanCommittedPayload,
) -> None:
    observation = _observation(_snapshot())

    class BadProgrammer:
        def program(
            self, _observation: ModelSOProgrammingObservation
        ) -> ModelSOPlanCommittedPayload:
            return bad_plan

    with pytest.raises(ProgrammingPilotError):
        program_for_seat(BadProgrammer(), observation)


def test_unbound_seat_is_classified_as_the_planner_not_as_a_fallback() -> None:
    """A seat with no bound programmer never substituted for anything.

    This is the path a human seat, a deterministic pilot, and every
    hermetic/replay match take.  Labelling it ``deterministic_fallback`` would
    claim a provider failed when no provider was ever involved, which makes
    the one member that means "a live seat lost its provider" useless.
    """

    plan = program_for_seat(None, _observation(_snapshot()))

    assert plan.plan_source is SOPlanSource.DETERMINISTIC_PLANNER


def test_plan_committed_payload_defaults_legacy_events_to_unspecified() -> None:
    """An event persisted before the field existed stays honestly unknown."""

    legacy = ModelSOPlanCommittedPayload.model_validate_json(
        json.dumps(
            {
                "seat": "red",
                "registers": [{"register_index": 0, "card_id": "card.test.advance"}],
                "rationale": None,
                "confidence": 1.0,
            }
        )
    )

    # Specifically NOT relabelled as a substitution that never happened, and
    # not credited to a provider either.
    assert legacy.plan_source is SOPlanSource.UNSPECIFIED
