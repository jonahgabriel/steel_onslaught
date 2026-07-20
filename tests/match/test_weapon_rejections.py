"""Live telemetry for weapon-fire validation rejections."""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    ModelSOPosition,
    SOPilotAction,
    SOPilotReasonCode,
)
from tests.runtime import match_runner

_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")


class _FirePilot:
    def __init__(self, *, target_mech_id: str | None = None) -> None:
        self._target_mech_id = target_mech_id

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        del observation
        params: dict[str, str] = {"weapon_id": "weapon.light.machine_gun"}
        if self._target_mech_id is not None:
            params["target_mech_id"] = self._target_mech_id
        return ModelSOPilotDecision(
            action=SOPilotAction.FIRE_WEAPON,
            action_params=params,
            reason_code=SOPilotReasonCode.TARGET_IN_RANGE,
            confidence=1.0,
            considered_actions=(
                ModelSOConsideredAction(action=SOPilotAction.FIRE_WEAPON, score=1.0),
            ),
        )


class _RemainPilot:
    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        del observation
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            action_params={},
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0),),
        )


def _run_one_rejection(
    *, arena: ModelSOArenaSpec, target_mech_id: str | None = None
) -> list[ModelSOEventEnvelope]:
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    loadout = load_loadout(_LOADOUT)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.test.weapon-rejection",
        seed=7,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=2,
        arena_override=arena,
        pilots_override={
            "mech.a.01": _FirePilot(target_mech_id=target_mech_id),
            "mech.b.01": _RemainPilot(),
        },
    )
    runner.run()
    return events


def _far_arena() -> ModelSOArenaSpec:
    return ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="weapon_rejection_far",
        display_name="Weapon rejection far arena",
        size=20,
        spawn_a=ModelSOPosition(x=1, y=1),
        spawn_b=ModelSOPosition(x=18, y=18),
        obstacles=(),
        rects=(),
    )


@pytest.mark.integration
def test_out_of_range_weapon_fire_emits_typed_rejection_with_causation() -> None:
    events = _run_one_rejection(arena=_far_arena())

    rejected = [event for event in events if event.event_type is SOEventType.WEAPON_FIRE_REJECTED]
    intents = [event for event in events if event.event_type is SOEventType.WEAPON_FIRE_INTENT]
    assert len(rejected) == 1
    assert len(intents) == 1
    assert rejected[0].payload == {
        "weapon_id": "weapon.light.machine_gun",
        "target_id": "mech.b.01",
        "reason": "target_out_of_range",
    }
    assert rejected[0].causation_id == intents[0].envelope.message_id
    assert not any(event.event_type is SOEventType.WEAPON_FIRED for event in events)


@pytest.mark.integration
def test_unknown_target_weapon_fire_emits_explicit_rejection() -> None:
    events = _run_one_rejection(
        arena=_far_arena(),
        target_mech_id="mech.missing.01",
    )

    rejected = [event for event in events if event.event_type is SOEventType.WEAPON_FIRE_REJECTED]
    assert len(rejected) == 1
    assert rejected[0].payload == {
        "weapon_id": "weapon.light.machine_gun",
        "target_id": "mech.missing.01",
        "reason": "target_not_found",
    }
