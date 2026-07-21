"""Pure card-round event specifications for a later envelope adapter.

``CardRunnerAdapter`` deliberately returns value-only output.  This module
adds the next, still-pure seam: it turns those values into typed event
specifications without constructing envelopes, allocating message ids, or
publishing on a bus.  A later composition root owns envelope construction and
publication after resolving this explicit UUID chain.

The builder keeps the adapter's authored ``value_id`` out of UUID handling.
The caller supplies an explicit root causation UUID and one explicit child
message UUID for every emitted specification.  Parent links therefore remain
UUID-to-UUID metadata even though a later envelope adapter owns publication.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.contracts.card import CardId
from steel_onslaught.contracts.mode import ModelSOModeSwitchIntentPayload
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
)
from steel_onslaught.events.envelope import ModelSOEventSubject, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMoveIntentPayload,
    ModelSOWeaponFireIntentPayload,
)
from steel_onslaught.match.card_adapter import (
    ModelSOCardIntentProjection,
    ModelSOCardRoundEmission,
    ModelSOCardRoundValue,
)
from steel_onslaught.pilots.schemas import SOPilotAction


class CardRoundEventSpecError(ValueError):
    """Card-round values cannot be converted into a safe event specification."""


class _ClosedCardEventSpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


CardRoundSpecStage = Literal[
    "HAND_DEALT",
    "PLAN_COMMITTED",
    "REGISTER_RESOLVED",
    "INTENT",
    "CARDS_DISCARDED",
]

CardRoundLifecyclePayload = (
    ModelSOHandDealtPayload
    | ModelSOPlanCommittedPayload
    | ModelSORegisterResolvedPayload
    | ModelSOCardsDiscardedPayload
)
CardRoundIntentPayload = (
    ModelSOEmptyPayload
    | ModelSOMoveIntentPayload
    | ModelSOWeaponFireIntentPayload
    | ModelSOModeSwitchIntentPayload
)
CardRoundSpecPayload = CardRoundLifecyclePayload | CardRoundIntentPayload


class ModelSOCardRoundParentLink(_ClosedCardEventSpecModel):
    """Explicit UUID root and parent metadata for a later envelope adapter."""

    root_causation_id: UUID
    parent_message_id: UUID | None = None


class ModelSOCardRoundEventSpec(_ClosedCardEventSpecModel):
    """One canonical event intent with a deterministic logical parent link.

    ``sequence_index`` is local to this pure specification batch.  It is not
    an envelope's ``sequence_in_tick``; the event bus remains the ordering
    authority when a later adapter publishes the resulting envelopes.
    """

    sequence_index: StrictInt = Field(ge=0)
    message_id: UUID
    causation_id: UUID
    stage: CardRoundSpecStage
    event_type: SOEventType
    seat: StrictStr = Field(min_length=1)
    subject: ModelSOEventSubject
    payload: CardRoundSpecPayload
    parent: ModelSOCardRoundParentLink
    source_ordinal: StrictInt = Field(ge=0)
    register_index: StrictInt | None = Field(default=None, ge=0)
    card_id: CardId | None = None
    action: SOPilotAction | None = None

    @model_validator(mode="after")
    def _validate_spec_shape(self) -> Self:
        if (
            self.causation_id != self.parent.root_causation_id
            and self.parent.parent_message_id is None
        ):
            raise CardRoundEventSpecError("non-root card specs require an explicit parent UUID")
        if (
            self.parent.parent_message_id is not None
            and self.causation_id != self.parent.parent_message_id
        ):
            raise CardRoundEventSpecError("card causation_id must equal its parent_message_id")
        expected_lifecycle = {
            "HAND_DEALT": SOEventType.HAND_DEALT,
            "PLAN_COMMITTED": SOEventType.PLAN_COMMITTED,
            "REGISTER_RESOLVED": SOEventType.REGISTER_RESOLVED,
            "CARDS_DISCARDED": SOEventType.CARDS_DISCARDED,
        }
        if self.stage in expected_lifecycle:
            if self.event_type is not expected_lifecycle[self.stage]:
                raise CardRoundEventSpecError(
                    f"{self.stage} must map to {expected_lifecycle[self.stage].value}"
                )
            if self.action is not None:
                raise CardRoundEventSpecError("lifecycle specs cannot carry an intent action")
        elif self.stage == "INTENT":
            if self.event_type not in {
                SOEventType.MOVE_INTENT,
                SOEventType.WEAPON_FIRE_INTENT,
                SOEventType.MODE_SWITCH_INTENT,
                SOEventType.VENT_INTENT,
            }:
                raise CardRoundEventSpecError("INTENT specs require a canonical intent event type")
            if self.action is None:
                raise CardRoundEventSpecError("INTENT specs require the projected pilot action")
            if self.register_index is None:
                raise CardRoundEventSpecError("INTENT specs require a register_index")
        else:  # pragma: no cover - Literal validation normally catches this first.
            raise CardRoundEventSpecError(f"unsupported card event stage {self.stage!r}")
        return self


_LIFECYCLE_EVENT_TYPES: dict[str, SOEventType] = {
    "HAND_DEALT": SOEventType.HAND_DEALT,
    "PLAN_COMMITTED": SOEventType.PLAN_COMMITTED,
    "REGISTER_RESOLVED": SOEventType.REGISTER_RESOLVED,
    "CARDS_DISCARDED": SOEventType.CARDS_DISCARDED,
}


@dataclass(frozen=True, slots=True)
class CardRoundEventSpecBuilder:
    """Convert one value-only card emission into pure event specifications.

    The caller owns the root/child UUID chain and seat-to-subject projection.
    This class never constructs envelopes, creates UUIDs, touches a bus, or
    mutates card/deck state.  Those operations belong to the later runtime
    adapter.
    """

    root_causation_id: UUID
    seat_subjects: Mapping[str, ModelSOEventSubject]

    def __post_init__(self) -> None:
        if not isinstance(self.root_causation_id, UUID):
            raise TypeError("root_causation_id must be a UUID")
        if not isinstance(self.seat_subjects, Mapping):
            raise TypeError("seat_subjects must be a mapping")
        subjects = dict(self.seat_subjects)
        if any(not isinstance(seat, str) or not seat for seat in subjects):
            raise CardRoundEventSpecError("seat_subjects keys must be non-empty strings")
        if any(not isinstance(subject, ModelSOEventSubject) for subject in subjects.values()):
            raise TypeError("seat_subjects values must be ModelSOEventSubject")
        subject_keys = tuple((subject.mech_id, subject.player_id) for subject in subjects.values())
        if len(subject_keys) != len(set(subject_keys)):
            raise CardRoundEventSpecError(
                "seat_subjects must not map multiple seats to one subject"
            )
        object.__setattr__(self, "seat_subjects", MappingProxyType(subjects))

    def build(
        self,
        emission: ModelSOCardRoundEmission,
        *,
        message_ids: Sequence[UUID],
    ) -> tuple[ModelSOCardRoundEventSpec, ...]:
        """Build lifecycle and intent specs in deterministic causal order."""

        if not isinstance(emission, ModelSOCardRoundEmission):
            raise TypeError("emission must be ModelSOCardRoundEmission")
        if emission.suppressed_reason is not None:
            if emission.values or emission.actions:
                raise CardRoundEventSpecError("suppressed emission cannot contain event values")
            if message_ids:
                raise CardRoundEventSpecError("suppressed emission cannot consume message UUIDs")
            return ()
        if not emission.registers_enabled:
            raise CardRoundEventSpecError(
                "an unsuppressed card emission must have registers_enabled=true"
            )
        if not emission.values:
            raise CardRoundEventSpecError("enabled card emission must contain card event values")

        values = tuple(emission.values)
        self._validate_values(values)
        actions = self._index_actions(emission.actions)
        active_action_count = len(actions)
        expected_message_count = len(values) + active_action_count
        ids = tuple(message_ids)
        if len(ids) != expected_message_count:
            raise CardRoundEventSpecError(
                f"message_ids must contain exactly {expected_message_count} UUIDs; got {len(ids)}"
            )
        if len(set(ids)) != len(ids) or self.root_causation_id in ids:
            raise CardRoundEventSpecError("message_ids must be unique and distinct from root UUID")
        specs: list[ModelSOCardRoundEventSpec] = []
        register_specs: dict[tuple[str, int], int] = {}
        previous_lifecycle_message_id: UUID | None = None

        for value in values:
            event_type = _LIFECYCLE_EVENT_TYPES.get(value.stage)
            if event_type is None:
                raise CardRoundEventSpecError(f"unsupported card event stage {value.stage!r}")
            subject = self._subject_for(value.seat)
            sequence_index = len(specs)
            causation_id = (
                self.root_causation_id
                if previous_lifecycle_message_id is None
                else previous_lifecycle_message_id
            )
            specs.append(
                ModelSOCardRoundEventSpec(
                    sequence_index=sequence_index,
                    message_id=ids[sequence_index],
                    causation_id=causation_id,
                    stage=value.stage,
                    event_type=event_type,
                    seat=value.seat,
                    subject=subject,
                    payload=value.payload,
                    parent=ModelSOCardRoundParentLink(
                        root_causation_id=self.root_causation_id,
                        parent_message_id=previous_lifecycle_message_id,
                    ),
                    source_ordinal=value.ordinal,
                )
            )
            previous_lifecycle_message_id = ids[sequence_index]
            if value.stage == "REGISTER_RESOLVED":
                register = value.payload
                if not isinstance(register, ModelSORegisterResolvedPayload):
                    raise CardRoundEventSpecError(
                        "REGISTER_RESOLVED value must carry ModelSORegisterResolvedPayload"
                    )
                register_key = (register.seat, register.register_index)
                if register_key in register_specs:
                    raise CardRoundEventSpecError("duplicate REGISTER_RESOLVED seat/register pair")
                register_specs[register_key] = sequence_index
                projection = actions.pop(register_key, None)
                if projection is None:
                    continue
                self._append_intent_spec(
                    specs,
                    projection,
                    value.ordinal,
                    register_specs[register_key],
                    ids,
                )

        if actions:
            raise CardRoundEventSpecError(
                f"card intent projection has no matching REGISTER_RESOLVED row: {sorted(actions)}"
            )
        return tuple(specs)

    def _validate_values(self, values: tuple[ModelSOCardRoundValue, ...]) -> None:
        seen_ordinals: set[int] = set()
        seen_by_stage_seat: set[tuple[str, str]] = set()
        previous_stage = -1
        phase_order = {stage: index for index, stage in enumerate(_LIFECYCLE_EVENT_TYPES)}
        for value in values:
            if value.ordinal in seen_ordinals:
                raise CardRoundEventSpecError("card event values must have unique ordinals")
            seen_ordinals.add(value.ordinal)
            stage_order = phase_order.get(value.stage)
            if stage_order is None:
                raise CardRoundEventSpecError(f"unsupported card event stage {value.stage!r}")
            if stage_order < previous_stage:
                raise CardRoundEventSpecError("card event values are out of lifecycle phase order")
            previous_stage = stage_order
            if value.stage in {"HAND_DEALT", "PLAN_COMMITTED", "CARDS_DISCARDED"}:
                key = (value.stage, value.seat)
                if key in seen_by_stage_seat:
                    raise CardRoundEventSpecError(
                        f"duplicate {value.stage} value for seat {value.seat!r}"
                    )
                seen_by_stage_seat.add(key)
            self._subject_for(value.seat)

    @staticmethod
    def _index_actions(
        actions: tuple[ModelSOCardIntentProjection, ...],
    ) -> dict[tuple[str, int], ModelSOCardIntentProjection]:
        indexed: dict[tuple[str, int], ModelSOCardIntentProjection] = {}
        for projection in actions:
            key = (projection.seat, projection.register_index)
            if key in indexed:
                raise CardRoundEventSpecError(
                    "duplicate card intent projection for seat/register pair"
                )
            if projection.outcome.value == "auto_remain":
                if projection.event_type is not None or projection.payload is not None:
                    raise CardRoundEventSpecError("AUTO_REMAIN projection cannot become an intent")
                continue
            if projection.unavailable_reason is not None:
                # A resolved-but-unfieldable card (e.g. an attack naming a
                # hardpoint the mech does not carry) keeps its
                # REGISTER_RESOLVED row and produces no intent.
                if projection.event_type is not None or projection.payload is not None:
                    raise CardRoundEventSpecError(
                        "unavailable card projection cannot become an intent"
                    )
                continue
            if projection.event_type is None or projection.payload is None:
                raise CardRoundEventSpecError(
                    "resolved card projection requires event type and payload"
                )
            indexed[key] = projection
        return indexed

    def _append_intent_spec(
        self,
        specs: list[ModelSOCardRoundEventSpec],
        projection: ModelSOCardIntentProjection,
        source_ordinal: int,
        parent_sequence: int,
        message_ids: Sequence[UUID],
    ) -> None:
        assert projection.event_type is not None
        assert projection.payload is not None
        if projection.event_type not in {
            SOEventType.MOVE_INTENT,
            SOEventType.WEAPON_FIRE_INTENT,
            SOEventType.MODE_SWITCH_INTENT,
            SOEventType.VENT_INTENT,
        }:
            raise CardRoundEventSpecError(
                f"unsupported projected intent event type {projection.event_type!r}"
            )
        specs.append(
            ModelSOCardRoundEventSpec(
                sequence_index=len(specs),
                message_id=message_ids[len(specs)],
                causation_id=specs[parent_sequence].message_id,
                stage="INTENT",
                event_type=projection.event_type,
                seat=projection.seat,
                subject=self._subject_for(projection.seat),
                payload=projection.payload,
                parent=ModelSOCardRoundParentLink(
                    root_causation_id=self.root_causation_id,
                    parent_message_id=specs[parent_sequence].message_id,
                ),
                source_ordinal=source_ordinal,
                register_index=projection.register_index,
                card_id=projection.card_id,
                action=projection.action,
            )
        )

    def _subject_for(self, seat: str) -> ModelSOEventSubject:
        try:
            return self.seat_subjects[seat]
        except KeyError as exc:
            raise CardRoundEventSpecError(
                f"missing subject mapping for card seat {seat!r}"
            ) from exc


def build_card_round_event_specs(
    emission: ModelSOCardRoundEmission,
    *,
    root_causation_id: UUID,
    seat_subjects: Mapping[str, ModelSOEventSubject],
    message_ids: Sequence[UUID],
) -> tuple[ModelSOCardRoundEventSpec, ...]:
    """Functional convenience wrapper around :class:`CardRoundEventSpecBuilder`."""

    return CardRoundEventSpecBuilder(
        root_causation_id=root_causation_id,
        seat_subjects=seat_subjects,
    ).build(emission, message_ids=message_ids)


__all__ = [
    "CardRoundEventSpecBuilder",
    "CardRoundEventSpecError",
    "ModelSOCardRoundEventSpec",
    "ModelSOCardRoundParentLink",
    "build_card_round_event_specs",
]
