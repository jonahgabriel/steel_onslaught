"""Canonical event-payload samples for the TS type-parity contract — Task 31.

Emits one sample :class:`ModelSOEventEnvelope` per :class:`SOEventType` to
``frontend/src/__tests__/fixtures/<event_type>.json``.  The vitest suite
``frontend/src/__tests__/types_parity.test.ts`` parses each fixture through
the hand-written TS types in ``frontend/src/types.ts`` — any field added or
renamed in a Python event payload breaks that test until the TS type is
updated.

Regenerate whenever an event schema changes:

    uv run python -m tests.fixtures.event_samples

Payload shapes mirror the actual emitters:
  - MATCH_STARTED / VICTORY_DECLARED / MATCH_ENDED — lifecycle reducer models
  - MATCH_SCORED / HIT_RESOLVED — scoring reducer models
  - BOILER_* / HEAT_REDLINE_* — boiler + failure-cascade reducers
  - MODE_TRANSITION_* — mode reducer
  - SENSOR_OBSERVATION / PILOT_DECISION_MADE / *_INTENT — sensor + pilot tick
  - MOVEMENT_RESOLVED / MECH_SPAWNED — movement reducer payload contracts
  - WEAPON_FIRED / DAMAGE_APPLIED / MECH_DESTROYED / PILOT_KILLED — weapon,
    damage, and failure-cascade reducers
  - ARMOR_ABSORBED / PILOT_INJURED — declared in the design but not yet
    emitted by any reducer; samples carry the design-documented minimal shape
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid5

from steel_onslaught.contracts.arena import ModelSOCurrentLiveArenaSnapshot
from steel_onslaught.contracts.boiler import ModelSOBoilerState
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.runtime import (
    ModelSORuntimeStatusPayload,
    SORuntimeMode,
    SORuntimeStatus,
)
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    ModelSORegisterResolvedPayload,
    SOPlanSource,
    SORegisterOutcome,
)
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    make_event,
)
from steel_onslaught.match.state import ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.scoring import (
    ModelSOMatchScoredPayload,
    ModelSOPlayerScore,
    ModelSOScoredWinner,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = _REPO_ROOT / "frontend" / "src" / "__tests__" / "fixtures"

_MATCH_ID = "match.fixture.0001"
_EMITTED_AT = "2026-04-30T00:00:00+00:00"
_EMITTED_AT_DT = datetime(2026, 4, 30, tzinfo=UTC)
_PRODUCER = "node.fixture_emitter"
_SUBJECT_A = ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a")
_SUBJECT_B = ModelSOEventSubject(mech_id="mech.b.01", player_id="player.b")

# Deterministic ONEX workflow correlation id, shared across every fixture
# event (uuid5 from a fixed namespace + the fixture match id — stable across
# runs so the checked-in JSON fixtures don't churn).
_CORRELATION_ID: UUID = uuid5(UUID(int=0), _MATCH_ID)

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32 (ULID)


def _event_id(event_type: SOEventType) -> str:
    """Deterministic 26-char ULID-shaped id, unique per event type."""
    stem = "".join(c for c in event_type.value.upper() if c in _ULID_ALPHABET)
    return (f"01{stem}" + "0" * 26)[:26]


def _message_id(event_type: SOEventType) -> UUID:
    """Deterministic ONEX message UUID, unique per event type (uuid5)."""
    return uuid5(_CORRELATION_ID, event_type.value)


def _mech_state(
    *,
    mech_id: str,
    player_id: str,
    side: Literal["red", "blue"],
    x: int,
    y: int,
    facing: int,
) -> ModelSOMechRuntimeState:
    boiler = ModelSOBoilerState(
        match_id=_MATCH_ID,
        mech_id=mech_id,
        tick=0,
        pressure_current=45,
        pressure_maximum=90,
        regeneration_per_tick=5,
        heat_current=0,
        heat_redline_threshold=70,
        heat_rupture_threshold=100,
        heat_vent_rate=8,
        status_redline=False,
        status_rupture_warning=False,
        status_disabled=False,
        status_ruptured=False,
        modifier_heat_weapon_pressure=1.0,
        modifier_venting_penalty=0.0,
        modifier_mode_switch_heat_delta=0,
    )
    return ModelSOMechRuntimeState(
        mech_id=mech_id,
        player_id=player_id,
        side=side,
        loadout_id="loadout.fixture.alpha",
        pilot_id="pilot.aggressive",
        chassis_id="chassis.light_scout_mk1",
        chassis_class="light",
        sensor_ids=("module.sensor.short_range_scanner",),
        gizmo_ids=("module.gizmo.targeting_assist",),
        base_speed=3,
        position=ModelSOPosition(x=x, y=y),
        facing=facing,
        speed=3,
        hp=100,
        hp_max=100,
        armor_value=10,
        armor_max=10,
        current_mode=ModeId.RECON,
        weapon_cooldowns={"module.weapon.machine_gun": 0},
        boiler=boiler,
    )


def _card_event_payloads() -> dict[SOEventType, dict[str, Any]]:
    """Build card-event fixtures from the strict Python payload models.

    The card system is intentionally unbound in this slice: these samples use
    explicit contract ids and do not load a default deck or publish events.
    """

    cards = (
        "card.movement.advance",
        "card.attack.fire_primary",
        "card.vent.emergency_vent",
    )
    hand_dealt = ModelSOHandDealtPayload(
        seat="a",
        deck_id="deck.fixture.standard",
        card_ids=cards,
        hand_size=len(cards),
        deck_remaining=21,
        reshuffled=False,
    )
    plan_committed = ModelSOPlanCommittedPayload(
        seat="a",
        registers=tuple(
            ModelSOPlanRegister(register_index=index, card_id=card_id)
            for index, card_id in enumerate(cards)
        ),
        rationale="Advance, fire, then vent.",
        confidence=0.8,
        # A live match is LLM-driven, so the canonical wire sample is an
        # LLM-authored plan.
        plan_source=SOPlanSource.LLM,
    )
    register_resolved = ModelSORegisterResolvedPayload(
        seat="a",
        register_index=0,
        card_id=cards[0],
        action="move",
        outcome=SORegisterOutcome.RESOLVED,
        priority=400,
        priority_rank=0,
        fill_reason=None,
    )
    cards_discarded = ModelSOCardsDiscardedPayload(
        seat="a",
        card_ids=(cards[0],),
        reason="played",
    )
    return {
        SOEventType.HAND_DEALT: hand_dealt.model_dump(mode="json"),
        SOEventType.PLAN_COMMITTED: plan_committed.model_dump(mode="json"),
        SOEventType.REGISTER_RESOLVED: register_resolved.model_dump(mode="json"),
        SOEventType.CARDS_DISCARDED: cards_discarded.model_dump(mode="json"),
    }


def _sample_payloads() -> dict[SOEventType, dict[str, Any]]:
    """One canonical payload per event type, in declaration order."""
    mech_a = _mech_state(mech_id="mech.a.01", player_id="player.a", side="red", x=5, y=5, facing=90)
    mech_b = _mech_state(
        mech_id="mech.b.01", player_id="player.b", side="blue", x=35, y=35, facing=270
    )
    scored = ModelSOMatchScoredPayload(
        match_id=_MATCH_ID,
        winner=ModelSOScoredWinner(player_id="player.a", mech_id="mech.a.01"),
        scores={
            "player.a": ModelSOPlayerScore(
                victory=1,
                damage_dealt=120,
                damage_efficiency=1.5,
                pressure_efficiency=0.8,
                overload_penalty=0,
                replay_validity=1,
                final_score=220,
            ),
            "player.b": ModelSOPlayerScore(
                victory=0,
                damage_dealt=60,
                damage_efficiency=0.75,
                pressure_efficiency=0.6,
                overload_penalty=10,
                replay_validity=1,
                final_score=95,
            ),
        },
        winner_player_id="player.a",
        winner_loadout_id="loadout.fixture.alpha",
        winner_score=220,
        loser_player_id="player.b",
        loser_score=95,
        duration_ticks=42,
        scored_at=_EMITTED_AT,
        is_draw=False,
    )
    return {
        SOEventType.MATCH_STARTED: {
            "seed": 12345,
            "max_ticks": 200,
            "mechs": [mech_a.model_dump(mode="json"), mech_b.model_dump(mode="json")],
            "arena": ModelSOCurrentLiveArenaSnapshot(
                schema_version="0.1.0",
                kind="steel_onslaught.arena_snapshot",
                arena_id="open_field",
                size=40,
                spawn_a=mech_a.position,
                spawn_b=mech_b.position,
                obstacles=(),
                sudden_death_start_tick=None,
                sudden_death_damage_base=8,
            ).model_dump(mode="json"),
        },
        SOEventType.RUNTIME_STATUS_CHANGED: ModelSORuntimeStatusPayload(
            status=SORuntimeStatus.RUNNING,
            mode=SORuntimeMode.ONE_GAME,
            revision=1,
            owner_id="runtime_owner.browser",
            match_index=0,
            last_command_id=UUID("11111111-1111-4111-8111-111111111111"),
        ).model_dump(mode="json"),
        SOEventType.MATCH_TICK: {},
        SOEventType.MECH_SPAWNED: {"position": {"x": 5, "y": 5}, "facing": 90},
        SOEventType.SENSOR_OBSERVATION: {
            "enemy_mech_id": "mech.b.01",
            "distance_estimate": 12.4,
            "confidence": 0.85,
            "heat_estimate": 55.0,
            "mode_estimate": "assault",
        },
        SOEventType.PILOT_DECISION_MADE: {
            "action": "fire_weapon",
            "action_params": {"weapon_id": "module.weapon.machine_gun"},
            "reason_code": "target_in_range",
            "confidence": 0.9,
            "considered_actions": [
                {"action": "fire_weapon", "score": 0.9},
                {"action": "move", "score": 0.4},
            ],
            "rationale": None,
        },
        SOEventType.LLM_COMPLETION_REQUESTED: {
            "provider_id": "stub",
            "persona_id": "berserker",
            "system_prompt_length": 128,
            "user_prompt_length": 512,
        },
        SOEventType.LLM_COMPLETION_RESOLVED: {
            "provider_id": "stub",
            "model": "stub",
            "finish_reason": "stop",
            "prompt_tokens": 64,
            "completion_tokens": 24,
            "response_length": 96,
            "cost_usd": 0.0,
        },
        SOEventType.LLM_COMPLETION_FAILED: {
            "provider_id": "primary",
            "reason_code": "invalid_response",
            "semantic_failure_code": "malformed_json",
            "model": "served-model",
            "finish_reason": "stop",
            "prompt_tokens": 64,
            "completion_tokens": 24,
            "cost_usd": None,
        },
        SOEventType.MOVE_INTENT: {"direction": "toward_enemy", "speed": "full"},
        SOEventType.WEAPON_FIRE_INTENT: {"weapon_id": "module.weapon.machine_gun"},
        SOEventType.MODE_SWITCH_INTENT: {"target_mode": "assault"},
        SOEventType.VENT_INTENT: {},
        SOEventType.MOVEMENT_RESOLVED: {
            "from": {"x": 5, "y": 5},
            "to": {"x": 7, "y": 6},
            "ticks_consumed": 1,
            "pressure_consumed": 2,
        },
        SOEventType.BOILER_UPDATED: {
            "pressure_before": 45,
            "pressure_after": 50,
            "heat_before": 20,
            "heat_after": 12,
        },
        SOEventType.HEAT_REDLINE_ENTERED: {"heat": 72, "redline_threshold": 70},
        SOEventType.HEAT_REDLINE_EXITED: {"heat": 64, "redline_threshold": 70},
        SOEventType.BOILER_OVERLOADED: {
            "heat": 78,
            "redline_threshold": 70,
            "redline_consecutive_ticks": 3,
            "accuracy_penalty_next_fire": 0.25,
            "mode_switch_disabled_until": 14,
        },
        SOEventType.BOILER_RUPTURED: {
            "cause": "heat_threshold",
            "heat": 100,
            "rupture_threshold": 100,
            "direct_damage": 40,
            "area_damage": 15,
            "area_radius_cells": 3,
        },
        SOEventType.MODE_TRANSITION_STARTED: {
            "from_mode": "recon",
            "to_mode": "assault",
            "costs": {"pressure": 10, "heat": 5, "transition_ticks": 2},
            "sensor_dropout_ticks": 1,
            "evasion_penalty": 0.2,
        },
        SOEventType.MODE_TRANSITION_COMPLETED: {
            "from_mode": "recon",
            "new_mode": "assault",
            "mode_lock_until": 12,
        },
        SOEventType.WEAPON_FIRE_REJECTED: {
            "weapon_id": "module.weapon.machine_gun",
            "target_id": "mech.b.01",
            "reason": "target_out_of_range",
        },
        SOEventType.WEAPON_FIRED: {
            "weapon_id": "module.weapon.machine_gun",
            "target_id": "mech.b.01",
            "hit_probability": 0.65,
            "pressure_cost": 4,
            "heat_generated": 6,
        },
        SOEventType.HIT_RESOLVED: {
            "attacker_id": "mech.a.01",
            "defender_id": "mech.b.01",
            "result": {"hit": True, "damage_after_armor": 8},
        },
        SOEventType.ARMOR_ABSORBED: {
            "target_id": "mech.b.01",
            "absorbed_amount": 4,
            "armor_after": 6,
        },
        SOEventType.DAMAGE_APPLIED: {
            "target_id": "mech.b.01",
            "damage": 8,
            "cause": "weapon_hit",
            "hp_after": 92,
            "source_mech_id": "mech.a.01",
            "radius_cells": 0,
        },
        SOEventType.PILOT_INJURED: {"mech_id": "mech.b.01"},
        SOEventType.PILOT_KILLED: {
            "mech_id": "mech.b.01",
            "survival_probability": 0.7,
            "roll": 0.95,
            "safety_gizmos_equipped": 1,
        },
        SOEventType.MECH_DESTROYED: {
            "cause": "boiler_rupture",
            "source_mech_id": "mech.a.01",
        },
        SOEventType.VICTORY_DECLARED: {
            "winner_player_id": "player.a",
            "reason": "last_mech_standing",
        },
        SOEventType.MATCH_ENDED: {"reason": "last_mech_standing", "winner_id": "player.a"},
        SOEventType.MATCH_SCORED: scored.model_dump(mode="json"),
        **_card_event_payloads(),
    }


def build_sample_envelopes() -> dict[SOEventType, ModelSOEventEnvelope]:
    """One deterministic envelope per event type."""
    envelopes: dict[SOEventType, ModelSOEventEnvelope] = {}
    for event_type, payload in _sample_payloads().items():
        subject = _SUBJECT_B if event_type in _DEFENDER_SUBJECT_EVENTS else _SUBJECT_A
        envelopes[event_type] = make_event(
            event_id=_event_id(event_type),
            message_id=_message_id(event_type),
            emitted_at=_EMITTED_AT_DT,
            match_id=_MATCH_ID,
            correlation_id=_CORRELATION_ID,
            tick=0 if event_type is SOEventType.MATCH_STARTED else 7,
            sequence_in_tick=0,
            producer_node=_PRODUCER,
            subject=subject,
            event_type=event_type,
            payload=payload,
        )
    return envelopes


_DEFENDER_SUBJECT_EVENTS = frozenset(
    {
        SOEventType.DAMAGE_APPLIED,
        SOEventType.PILOT_INJURED,
        SOEventType.PILOT_KILLED,
        SOEventType.MECH_DESTROYED,
    }
)


def emit_fixtures(out_dir: Path | None = None) -> list[Path]:
    """Write one ``<event_type>.json`` per event type; return written paths."""
    target = FIXTURES_DIR if out_dir is None else out_dir
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for event_type, envelope in build_sample_envelopes().items():
        path = target / f"{event_type.value}.json"
        path.write_text(envelope.model_dump_json(indent=2) + "\n")
        written.append(path)
    return sorted(written)


if __name__ == "__main__":
    for fixture_path in emit_fixtures():
        print(fixture_path.relative_to(_REPO_ROOT))
