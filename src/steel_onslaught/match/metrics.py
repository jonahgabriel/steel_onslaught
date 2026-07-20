"""Pure combat-opportunity metrics projected from canonical event streams."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    CURRENT_CONSUMED_PAYLOAD_MODELS,
    ModelSOHitResolvedPayload,
    ModelSOWeaponFiredPayload,
    ModelSOWeaponFireRejectedPayload,
)


class ModelSOWeaponOpportunityMetric(BaseModel):
    """Per-seat fire opportunity counts derived from typed events.

    ``legal_intent_count`` counts fire intents that were not rejected.  A
    ``weapon_fired`` event is the canonical acceptance marker, and a hit is
    counted only from ``HIT_RESOLVED.result.hit``.  The ordering constraints
    prevent a report from silently claiming more legal fires or hits than the
    event stream contains.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.weapon_opportunity_metric"] = (
        "steel_onslaught.weapon_opportunity_metric"
    )
    mech_id: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    intent_count: StrictInt = Field(ge=0)
    legal_intent_count: StrictInt = Field(ge=0)
    fired_count: StrictInt = Field(ge=0)
    hit_count: StrictInt = Field(ge=0)
    damage_dealt: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _counts_are_monotonic(self) -> ModelSOWeaponOpportunityMetric:
        if self.legal_intent_count > self.intent_count:
            raise ValueError("legal_intent_count cannot exceed intent_count")
        if self.fired_count > self.legal_intent_count:
            raise ValueError("fired_count cannot exceed legal_intent_count")
        if self.hit_count > self.fired_count:
            raise ValueError("hit_count cannot exceed fired_count")
        return self

    @property
    def legal_fire_ratio(self) -> float:
        """Fraction of fire intents accepted by the weapon resolver."""

        return self.legal_intent_count / self.intent_count if self.intent_count else 0.0

    @property
    def hit_ratio(self) -> float:
        """Fraction of accepted fires that produced a hit."""

        return self.hit_count / self.fired_count if self.fired_count else 0.0


@dataclass
class _MutableWeaponMetric:
    player_id: str
    intent_count: int = 0
    rejected_count: int = 0
    fired_count: int = 0
    hit_count: int = 0
    damage_dealt: int = 0


def project_weapon_opportunity_metrics(
    events: Iterable[ModelSOEventEnvelope],
) -> tuple[ModelSOWeaponOpportunityMetric, ...]:
    """Project fire intents, legality, shots, and hits by canonical mech.

    The projector has no runner or provider dependency.  It validates each
    consumed payload before counting it and returns stable mech-id order so a
    report is replayable and safe to compare across matches.
    """

    stream = tuple(events)
    player_by_mech: dict[str, str] = {}
    for event in stream:
        mech_id = event.subject.mech_id
        player_id = event.subject.player_id
        if mech_id in {"", "*"} or player_id in {"", "*"}:
            continue
        previous = player_by_mech.setdefault(mech_id, player_id)
        if previous != player_id:
            raise ValueError(f"mech {mech_id!r} is associated with multiple player ids")

    metrics: dict[str, _MutableWeaponMetric] = {}
    for event in stream:
        if event.event_type not in {
            SOEventType.WEAPON_FIRE_INTENT,
            SOEventType.WEAPON_FIRE_REJECTED,
            SOEventType.WEAPON_FIRED,
            SOEventType.HIT_RESOLVED,
        }:
            continue

        if event.event_type is SOEventType.HIT_RESOLVED:
            payload = CURRENT_CONSUMED_PAYLOAD_MODELS[event.event_type].model_validate(
                event.payload
            )
            if not isinstance(payload, ModelSOHitResolvedPayload):
                raise TypeError("HIT_RESOLVED payload authority returned the wrong model")
            mech_id = payload.attacker_id
        else:
            mech_id = event.subject.mech_id

        if mech_id in {"", "*"}:
            raise ValueError(f"weapon opportunity event has no concrete attacker: {mech_id!r}")
        mapped_player_id = player_by_mech.get(mech_id)
        if mapped_player_id is None:
            raise ValueError(f"weapon opportunity event has no player mapping for {mech_id!r}")
        item = metrics.setdefault(mech_id, _MutableWeaponMetric(mapped_player_id))

        if event.event_type is SOEventType.WEAPON_FIRE_INTENT:
            CURRENT_CONSUMED_PAYLOAD_MODELS[event.event_type].model_validate(event.payload)
            item.intent_count += 1
        elif event.event_type is SOEventType.WEAPON_FIRE_REJECTED:
            payload = CURRENT_CONSUMED_PAYLOAD_MODELS[event.event_type].model_validate(
                event.payload
            )
            if not isinstance(payload, ModelSOWeaponFireRejectedPayload):
                raise TypeError("WEAPON_FIRE_REJECTED payload authority returned the wrong model")
            item.rejected_count += 1
        elif event.event_type is SOEventType.WEAPON_FIRED:
            payload = CURRENT_CONSUMED_PAYLOAD_MODELS[event.event_type].model_validate(
                event.payload
            )
            if not isinstance(payload, ModelSOWeaponFiredPayload):
                raise TypeError("WEAPON_FIRED payload authority returned the wrong model")
            item.fired_count += 1
        else:
            payload = CURRENT_CONSUMED_PAYLOAD_MODELS[event.event_type].model_validate(
                event.payload
            )
            if not isinstance(payload, ModelSOHitResolvedPayload):
                raise TypeError("HIT_RESOLVED payload authority returned the wrong model")
            if payload.result.hit:
                item.hit_count += 1
                item.damage_dealt += payload.result.damage_after_armor

    result: list[ModelSOWeaponOpportunityMetric] = []
    for mech_id, item in sorted(metrics.items()):
        legal_count = item.intent_count - item.rejected_count
        if legal_count < 0:
            raise ValueError(f"weapon fire rejection count exceeds intents for mech {mech_id!r}")
        result.append(
            ModelSOWeaponOpportunityMetric(
                mech_id=mech_id,
                player_id=item.player_id,
                intent_count=item.intent_count,
                legal_intent_count=legal_count,
                fired_count=item.fired_count,
                hit_count=item.hit_count,
                damage_dealt=item.damage_dealt,
            )
        )
    return tuple(result)


__all__ = ["ModelSOWeaponOpportunityMetric", "project_weapon_opportunity_metrics"]
