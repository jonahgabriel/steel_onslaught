"""Shared deterministic fixtures for the SO-UTIL-MECH incentive tests.

Deliberately importable on BOTH the pre-incentive tree and this one: every
incentive-specific keyword is passed only when an incentive is supplied, so
the same builder runs against ``main`` to MINT the byte-stability goldens in
``tests/match/golden/`` and against this tree to CHECK them.  That is what
makes the golden a real pre-change lock rather than a self-referential
snapshot of the new code's own output.

Nothing here reads the clock, the filesystem, or an RNG.
"""

from __future__ import annotations

from typing import Any

from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardCatalog,
    SOCardCategory,
)
from steel_onslaught.contracts.card_runtime import (
    ModelSOCardRuntimeSnapshot,
    canonical_card_runtime_sha256,
)
from steel_onslaught.contracts.deck import ModelSODeck, ModelSODeckEntry
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation
from steel_onslaught.pilots.schemas import (
    ModelSOObjectiveView,
    ModelSOPilotObservation,
    ModelSOPilotWeaponView,
    ModelSOPosition,
    ModelSOSensorReading,
    ModelSOVictoryPointsView,
)

INCENTIVE_ARENA_ID = "test_utility_incentive"
MATCH_ID = "match.test.utility-incentive"
VP_THRESHOLD = 6


def _card(
    card_id: str,
    category: SOCardCategory,
    priority: int,
    *,
    effect: dict[str, Any],
    description: str | None = None,
) -> ModelSOCard:
    payload: dict[str, Any] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.card",
        "id": card_id,
        "display_name": card_id.rsplit(".", 1)[-1],
        "category": category.value,
        "priority": priority,
        "heat_cost": 5,
        "effect": effect,
    }
    if description is not None:
        payload["description"] = description
    return ModelSOCard.model_validate(payload)


def card_catalog() -> ModelSOCardCatalog:
    """One movement, one attack, one utility card — the three-pile shape."""

    return ModelSOCardCatalog(
        cards=(
            _card(
                "card.test.advance",
                SOCardCategory.MOVEMENT,
                400,
                effect={"direction": "toward_enemy", "speed": "full"},
            ),
            _card(
                "card.test.smoke",
                SOCardCategory.UTILITY,
                290,
                effect={"utility_kind": "smoke", "radius": 2, "duration_ticks": 2},
                description="Blocks line of sight through the deployed cloud.",
            ),
            _card(
                "card.test.strike",
                SOCardCategory.ATTACK,
                600,
                effect={"weapon_slot": 0},
            ),
        )
    )


def card_runtime_snapshot() -> ModelSOCardRuntimeSnapshot:
    cards = card_catalog()
    deck = ModelSODeck(
        schema_version="0.1.0",
        kind="steel_onslaught.deck",
        id="deck.test.incentive",
        display_name="Incentive test deck",
        hand_size=3,
        register_count=3,
        cards=tuple(ModelSODeckEntry(card_id=card.id, count=1) for card in cards.cards),
    )
    return ModelSOCardRuntimeSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.card_runtime_snapshot",
        card_catalog=cards,
        decks=(deck,),
        selected_deck_id=deck.id,
        content_sha256=canonical_card_runtime_sha256(cards, (deck,)),
    )


def _boiler() -> ModelSOBoilerState:
    return ModelSOBoilerState(
        match_id=MATCH_ID,
        mech_id="mech.red.01",
        tick=7,
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


def pilot_observation() -> ModelSOPilotObservation:
    """An objective/VP-bearing pilot view (the only shape an incentive is legal on)."""

    return ModelSOPilotObservation(
        match_id=MATCH_ID,
        mech_id="mech.red.01",
        player_id="player.red",
        tick=7,
        match_elapsed_ticks=7,
        boiler=_boiler(),
        weapons=[
            ModelSOPilotWeaponView(
                weapon_id="weapon.test.primary",
                damage=10,
                range=15,
                pressure_cost=3,
                heat_generated=2,
                cooldown_remaining_ticks=0,
            )
        ],
        current_mode=ModeId.ASSAULT,
        mode_lock_expired=True,
        position=ModelSOPosition(x=2, y=3),
        hp_percent=82.0,
        under_sensor_lock=False,
        has_line_of_sight_to_enemy=True,
        enemy_observations=[
            ModelSOSensorReading(
                enemy_mech_id="mech.blue.01",
                tick=7,
                distance_estimate=6.0,
                confidence=0.8,
                heat_estimate=40.0,
            )
        ],
        objectives=(
            ModelSOObjectiveView(
                objective_id="objective.yard",
                cell=ModelSOPosition(x=10, y=10),
                vp_per_round=1,
                control="unclaimed",
                own_distance_chebyshev=7,
            ),
        ),
        victory_points=ModelSOVictoryPointsView(
            own_vp=2,
            enemy_vp=1,
            vp_threshold=VP_THRESHOLD,
        ),
    )


def programming_observation(incentive: object | None = None) -> ModelSOProgrammingObservation:
    """Build the observation the serializer renders.

    ``incentive`` is passed as ``object`` and forwarded only when non-None so
    this module still imports and runs on the pre-incentive tree, where
    ``ModelSOProgrammingObservation`` forbids the field entirely.
    """

    kwargs: dict[str, Any] = {
        "pilot_observation": pilot_observation(),
        "card_runtime_snapshot": card_runtime_snapshot(),
        "seat": "red",
        "hand": ("card.test.smoke", "card.test.advance", "card.test.strike"),
        "free_indices": (0, 1),
    }
    if incentive is not None:
        kwargs["utility_incentive"] = incentive
    return ModelSOProgrammingObservation(**kwargs)


def arena_payload() -> dict[str, Any]:
    """A minimal objective arena snapshot, as MATCH_STARTED embeds it."""

    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.arena_snapshot",
        "arena_id": INCENTIVE_ARENA_ID,
        "size": 40,
        "spawn_a": {"x": 5, "y": 5},
        "spawn_b": {"x": 35, "y": 35},
        "obstacles": [],
        "sudden_death_start_tick": 100,
        "sudden_death_damage_base": 8,
        "objectives": [
            {
                "objective_id": "objective.yard",
                "cell": {"x": 20, "y": 20},
                "vp_per_round": 1,
            }
        ],
        "vp_threshold": VP_THRESHOLD,
    }


def mech_payload(
    mech_id: str, player_id: str, *, position: tuple[int, int], side: str
) -> dict[str, Any]:
    """One mech snapshot row for MATCH_STARTED (mirrors the objective-scoring fixture)."""

    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.mech_runtime_state",
        "mech_id": mech_id,
        "player_id": player_id,
        "side": side,
        "loadout_id": "loadout.a",
        "pilot_id": "pilot.aggressive",
        "chassis_id": "chassis.medium.hunter_mk1",
        "chassis_class": "medium",
        "sensor_ids": [],
        "gizmo_ids": [],
        "base_speed": 4,
        "position": {"x": position[0], "y": position[1]},
        "facing": 45,
        "speed": 4,
        "hp": 100,
        "hp_max": 100,
        "armor_value": 10,
        "armor_max": 10,
        "alive": True,
        "pilot_alive": True,
        "current_mode": "recon",
        "mode_lock_until": 0,
        "transition_ticks_remaining": 0,
        "transition_to_mode": None,
        "sensor_dropout_ticks_remaining": 0,
        "mode_switch_disabled_until": 0,
        "weapon_cooldowns": {},
        "evasion": 0.0,
        "accuracy_penalty_next_fire": 0.0,
        "jamming_intensity": 0.0,
        "under_sensor_lock": False,
        "boiler": {
            "match_id": MATCH_ID,
            "mech_id": mech_id,
            "tick": 0,
            "pressure_current": 30,
            "pressure_maximum": 60,
            "regeneration_per_tick": 5,
            "heat_current": 0,
            "heat_redline_threshold": 80,
            "heat_rupture_threshold": 100,
            "heat_vent_rate": 5,
            "status_redline": False,
            "status_rupture_warning": False,
            "status_disabled": False,
            "status_ruptured": False,
            "modifier_heat_weapon_pressure": 1.0,
            "modifier_venting_penalty": 0.0,
            "modifier_mode_switch_heat_delta": 0,
        },
        "redline_consecutive_ticks": 0,
        "overloaded": False,
        "overloaded_consecutive_ticks": 0,
    }


def match_started_payload(incentive_dump: dict[str, Any] | None = None) -> dict[str, Any]:
    """The MATCH_STARTED payload dict; incentive key present only when supplied."""

    payload: dict[str, Any] = {
        "seed": 1,
        "max_ticks": 200,
        "mechs": [
            mech_payload("mech.red.01", "player.red", position=(5, 5), side="red"),
            mech_payload("mech.blue.01", "player.blue", position=(35, 35), side="blue"),
        ],
        "arena": arena_payload(),
    }
    if incentive_dump is not None:
        payload["utility_incentive"] = incentive_dump
    return payload


__all__ = [
    "INCENTIVE_ARENA_ID",
    "MATCH_ID",
    "VP_THRESHOLD",
    "arena_payload",
    "card_catalog",
    "card_runtime_snapshot",
    "match_started_payload",
    "mech_payload",
    "pilot_observation",
    "programming_observation",
]
