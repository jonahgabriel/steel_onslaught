"""Tests for canonical fire opportunity metrics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.metrics import (
    ModelSOWeaponOpportunityMetric,
    project_weapon_opportunity_metrics,
)

pytestmark = pytest.mark.unit

_MATCH_ID = "match.metrics.001"
_SUBJECT_A = ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red")


def _event(
    event_type: SOEventType,
    payload: dict[str, Any],
    *,
    subject: ModelSOEventSubject = _SUBJECT_A,
    tick: int,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=_MATCH_ID,
        tick=tick,
        sequence_in_tick=0,
        producer_node="node.test.metrics",
        subject=subject,
        event_type=event_type,
        payload=payload,
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=UUID(int=1),
            causation_id=None,
            entity_id=_MATCH_ID,
            emitted_at=datetime(2026, 7, 20, tzinfo=UTC),
        ),
    )


def test_project_weapon_opportunity_metrics_counts_intent_legality_fires_and_hits() -> None:
    events = (
        _event(
            SOEventType.WEAPON_FIRE_INTENT,
            {"weapon_id": "module.weapon.machine_gun", "target_mech_id": "mech.blue.01"},
            tick=1,
        ),
        _event(
            SOEventType.WEAPON_FIRE_INTENT,
            {"weapon_id": "module.weapon.machine_gun", "target_mech_id": "mech.blue.01"},
            tick=2,
        ),
        _event(
            SOEventType.WEAPON_FIRE_INTENT,
            {"weapon_id": "module.weapon.machine_gun", "target_mech_id": "mech.blue.01"},
            tick=3,
        ),
        _event(
            SOEventType.WEAPON_FIRE_REJECTED,
            {
                "weapon_id": "module.weapon.machine_gun",
                "target_id": "mech.blue.01",
                "reason": "target_out_of_range",
            },
            tick=3,
        ),
        _event(
            SOEventType.WEAPON_FIRED,
            {
                "weapon_id": "module.weapon.machine_gun",
                "target_id": "mech.blue.01",
                "hit_probability": 0.8,
                "pressure_cost": 5,
                "heat_generated": 2,
            },
            tick=1,
        ),
        _event(
            SOEventType.WEAPON_FIRED,
            {
                "weapon_id": "module.weapon.machine_gun",
                "target_id": "mech.blue.01",
                "hit_probability": 0.4,
                "pressure_cost": 5,
                "heat_generated": 2,
            },
            tick=2,
        ),
        _event(
            SOEventType.HIT_RESOLVED,
            {
                "attacker_id": "mech.red.01",
                "defender_id": "mech.blue.01",
                "result": {"hit": True, "damage_after_armor": 7},
            },
            tick=1,
        ),
    )

    result = project_weapon_opportunity_metrics(events)

    assert result == (
        ModelSOWeaponOpportunityMetric(
            mech_id="mech.red.01",
            player_id="player.red",
            intent_count=3,
            legal_intent_count=2,
            fired_count=2,
            hit_count=1,
            damage_dealt=7,
        ),
    )
    assert result[0].legal_fire_ratio == pytest.approx(2 / 3)
    assert result[0].hit_ratio == pytest.approx(1 / 2)


def test_weapon_metric_rejects_non_monotonic_counts() -> None:
    with pytest.raises(ValueError, match="fired_count cannot exceed"):
        ModelSOWeaponOpportunityMetric(
            mech_id="mech.red.01",
            player_id="player.red",
            intent_count=1,
            legal_intent_count=1,
            fired_count=2,
            hit_count=0,
            damage_dealt=0,
        )


def test_metric_projection_validates_closed_event_payloads() -> None:
    event = _event(
        SOEventType.WEAPON_FIRE_INTENT,
        {
            "weapon_id": "module.weapon.machine_gun",
            "target_mech_id": "mech.blue.01",
            "unknown": True,
        },
        tick=1,
    )
    with pytest.raises(ValueError, match="unknown"):
        project_weapon_opportunity_metrics((event,))
