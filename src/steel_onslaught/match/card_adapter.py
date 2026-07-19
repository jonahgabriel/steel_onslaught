"""Opt-in card-round producer for the live match composition seam.

The ordinary synchronous tick runner remains the authoritative lifecycle
driver.  This module is deliberately a smaller, value-only
adapter which a later composition root can call at a round boundary.  It does
not subscribe to an event bus, create envelopes, or inspect a match fold.

Card gameplay is therefore impossible unless the caller explicitly enables
``registers_enabled`` and injects the complete dependency graph.  Disabled
and terminal calls return an empty result, which makes the opt-in boundary
safe to compose next to the existing per-tick runner without changing its
default behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from steel_onslaught.cards.actions import (
    ModelSOCardActionParameters,
    ModelSOCardActionTranslation,
    ModelSOCardAttackParameters,
    ModelSOCardMovementParameters,
    ModelSOCardRotateParameters,
    ModelSOCardSpecialParameters,
    ModelSOCardVentParameters,
    compile_card_action,
)
from steel_onslaught.cards.dealer import DealerCompute, ModelSODealerScope, ModelSODeckState
from steel_onslaught.cards.registers import (
    ModelSOSeatResolutionContext,
    RegisterExecutionReducer,
    heat_locked_indices,
)
from steel_onslaught.cards.round import (
    CardRoundRuntime,
    ModelSOCardRoundDeal,
    ModelSOCardRoundSequence,
)
from steel_onslaught.cards.rules import CardProgrammingRuleRegistry
from steel_onslaught.contracts.card import CardId
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.mode import ModelSOModeSwitchIntentPayload
from steel_onslaught.events.card_payloads import (
    ModelSOCardsDiscardedPayload,
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
    SORegisterOutcome,
)
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.events.payloads import (
    ModelSOEmptyPayload,
    ModelSOMoveIntentPayload,
    ModelSOWeaponFireIntentPayload,
)
from steel_onslaught.pilots.programming import (
    ModelSOCardRulePackProvenance,
    ModelSOProgrammingObservation,
    ProgrammingPilot,
    program_for_seat,
)
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    SOMoveDirection,
    SOPilotAction,
)


class CardRunnerAdapterError(ValueError):
    """An explicitly enabled card adapter cannot produce a safe round."""


class _ClosedCardAdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelSOCardSeatRequest(_ClosedCardAdapterModel):
    """All per-seat inputs required at one deterministic programming boundary."""

    seat: StrictStr = Field(min_length=1)
    dealer_scope: ModelSODealerScope
    pilot_observation: ModelSOPilotObservation
    initiative: StrictInt = Field(ge=0)
    lock_depth: StrictInt = Field(default=0, ge=0)
    previous_plan: ModelSOPlanCommittedPayload | None = None
    weapon_ids: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def _scope_belongs_to_seat(self) -> Self:
        if self.dealer_scope.seat != self.seat:
            raise CardRunnerAdapterError(
                f"dealer scope seat {self.dealer_scope.seat!r} does not match request seat "
                f"{self.seat!r}"
            )
        if self.previous_plan is not None and self.previous_plan.seat != self.seat:
            raise CardRunnerAdapterError(
                f"previous plan seat {self.previous_plan.seat!r} does not match request seat "
                f"{self.seat!r}"
            )
        if len(set(self.weapon_ids)) != len(self.weapon_ids):
            raise CardRunnerAdapterError("weapon_ids must not contain duplicates")
        return self


class ModelSOCardIntentProjection(_ClosedCardAdapterModel):
    """A compiled card action in the existing intent vocabulary.

    ``payload`` is one of the existing intent payload models, not a loosely
    typed card dictionary.  ``None`` is reserved for explicit short-deck
    ``AUTO_REMAIN`` rows; those rows are retained in ``actions`` as telemetry
    but never become a gameplay intent.
    """

    seat: StrictStr = Field(min_length=1)
    register_index: StrictInt = Field(ge=0)
    card_id: CardId | None = None
    action: SOPilotAction
    translation: ModelSOCardActionTranslation | None = None
    event_type: SOEventType | None = None
    payload: (
        ModelSOEmptyPayload
        | ModelSOMoveIntentPayload
        | ModelSOWeaponFireIntentPayload
        | ModelSOModeSwitchIntentPayload
        | None
    ) = None
    outcome: SORegisterOutcome

    @model_validator(mode="after")
    def _projection_is_closed(self) -> Self:
        if self.outcome is SORegisterOutcome.AUTO_REMAIN:
            if self.card_id is not None or self.translation is not None:
                raise CardRunnerAdapterError("AUTO_REMAIN projections cannot name a card")
            if self.action is not SOPilotAction.REMAIN or self.event_type is not None:
                raise CardRunnerAdapterError("AUTO_REMAIN projections must remain inert")
            if self.payload is not None:
                raise CardRunnerAdapterError("AUTO_REMAIN projections cannot carry a payload")
            return self
        if self.card_id is None or self.translation is None:
            raise CardRunnerAdapterError("resolved card projections require card and translation")
        if self.event_type is None or self.payload is None:
            raise CardRunnerAdapterError("resolved card projections require an intent payload")
        if self.action is not self.translation.action:
            raise CardRunnerAdapterError("projection action differs from compiled translation")
        return self


CardRoundStage = Literal[
    "HAND_DEALT",
    "PLAN_COMMITTED",
    "REGISTER_RESOLVED",
    "CARDS_DISCARDED",
]


class ModelSOCardRoundValue(_ClosedCardAdapterModel):
    """One typed value with deterministic ordering and causation metadata."""

    stage: CardRoundStage
    ordinal: StrictInt = Field(ge=0)
    seat: StrictStr = Field(min_length=1)
    value_id: StrictStr = Field(min_length=1)
    caused_by: StrictStr = Field(min_length=1)
    payload: (
        ModelSOHandDealtPayload
        | ModelSOPlanCommittedPayload
        | ModelSORegisterResolvedPayload
        | ModelSOCardsDiscardedPayload
    )


class ModelSOCardRoundEmission(_ClosedCardAdapterModel):
    """Pure producer output; no bus publication is implied by this value."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.card_round_emission"] = "steel_onslaught.card_round_emission"
    registers_enabled: StrictBool
    round_index: StrictInt = Field(ge=0)
    tick: StrictInt = Field(ge=0)
    causation_id: StrictStr = Field(min_length=1)
    values: tuple[ModelSOCardRoundValue, ...] = ()
    actions: tuple[ModelSOCardIntentProjection, ...] = ()
    sequence: ModelSOCardRoundSequence | None = None
    deck_state: ModelSODeckState | None = None
    suppressed_reason: Literal["registers_disabled", "match_ended"] | None = None

    @model_validator(mode="after")
    def _empty_suppression_is_explicit(self) -> Self:
        suppressed = self.suppressed_reason is not None
        if suppressed:
            if (
                self.values
                or self.actions
                or self.sequence is not None
                or self.deck_state is not None
            ):
                raise CardRunnerAdapterError("suppressed card rounds must emit no card values")
            if self.registers_enabled and self.suppressed_reason == "registers_disabled":
                raise CardRunnerAdapterError("enabled card rounds cannot be disabled")
            return self
        if not self.registers_enabled:
            raise CardRunnerAdapterError("disabled card rounds require suppression metadata")
        if self.sequence is None or self.deck_state is None:
            raise CardRunnerAdapterError("enabled card rounds require sequence and deck state")
        return self


@dataclass(frozen=True, slots=True)
class CardRunnerAdapter:
    """Produce one opt-in card round from explicit immutable dependencies.

    This adapter intentionally has no lifecycle loop and no tick cap.  The
    caller supplies the current tick, round index, terminal boundary, and a
    causation key.  That leaves max-ticks/progress-gate authority with the
    existing lifecycle composition while making card
    rounds deterministic and independently testable.
    """

    registers_enabled: bool = False
    card_round_runtime: CardRoundRuntime | None = None
    dealer: DealerCompute | None = None
    reducer: RegisterExecutionReducer | None = None
    programmers: Mapping[str, ProgrammingPilot] | None = None
    rule_registry: CardProgrammingRuleRegistry | None = None
    rule_handler_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.registers_enabled, bool):
            raise TypeError("registers_enabled must be a bool")
        for name, value, expected in (
            ("card_round_runtime", self.card_round_runtime, CardRoundRuntime),
            ("dealer", self.dealer, DealerCompute),
            ("reducer", self.reducer, RegisterExecutionReducer),
        ):
            if value is not None and not isinstance(value, expected):
                raise TypeError(f"{name} must be {expected.__name__} when supplied")
        if self.programmers is not None:
            object.__setattr__(self, "programmers", MappingProxyType(dict(self.programmers)))
        if self.rule_registry is not None:
            if not isinstance(self.rule_registry, CardProgrammingRuleRegistry):
                raise TypeError("rule_registry must be CardProgrammingRuleRegistry when supplied")
            self.rule_registry.select(self.rule_handler_ids)
        elif self.rule_handler_ids:
            raise CardRunnerAdapterError(
                "rule_handler_ids require an explicit injected rule_registry"
            )
        if not self.registers_enabled:
            return
        if self.card_round_runtime is None or self.dealer is None or self.reducer is None:
            raise CardRunnerAdapterError(
                "registers_enabled requires explicit card_round_runtime, dealer, and reducer"
            )
        if self.card_round_runtime.dealer is not self.dealer:
            raise CardRunnerAdapterError("dealer must be the exact CardRoundRuntime dependency")
        if self.card_round_runtime.reducer is not self.reducer:
            raise CardRunnerAdapterError("reducer must be the exact CardRoundRuntime dependency")

    @property
    def snapshot(self) -> ModelSOCardRuntimeSnapshot | None:
        """Return the explicit snapshot, if this adapter is enabled."""

        return None if self.card_round_runtime is None else self.card_round_runtime.snapshot

    @property
    def rule_provenance(self) -> ModelSOCardRulePackProvenance | None:
        """Return selected rule-pack provenance for match-start telemetry."""

        if self.rule_registry is None:
            return None
        return self.rule_registry.provenance(self.rule_handler_ids)

    def produce(
        self,
        *,
        seats: tuple[ModelSOCardSeatRequest, ...],
        round_index: int,
        tick: int,
        causation_id: str,
        terminated: bool = False,
        starting_deck_state: ModelSODeckState | None = None,
    ) -> ModelSOCardRoundEmission:
        """Derive one deterministic four-stage round or an empty boundary result."""

        round_number = self._non_bool_int(round_index, "round_index", minimum=0)
        tick_number = self._non_bool_int(tick, "tick", minimum=0)
        if not isinstance(causation_id, str) or not causation_id:
            raise CardRunnerAdapterError("causation_id must be a non-empty string")
        if not self.registers_enabled:
            return ModelSOCardRoundEmission(
                registers_enabled=False,
                round_index=round_number,
                tick=tick_number,
                causation_id=causation_id,
                suppressed_reason="registers_disabled",
            )
        if terminated:
            return ModelSOCardRoundEmission(
                registers_enabled=True,
                round_index=round_number,
                tick=tick_number,
                causation_id=causation_id,
                suppressed_reason="match_ended",
            )
        if not seats:
            raise CardRunnerAdapterError("enabled card rounds require at least one seat")
        assert self.card_round_runtime is not None
        assert self.reducer is not None

        canonical_seats = tuple(sorted(seats, key=lambda request: request.seat))
        seat_ids = tuple(request.seat for request in canonical_seats)
        if len(seat_ids) != len(set(seat_ids)):
            raise CardRunnerAdapterError("card round seat ids must be unique")

        deals: list[ModelSOCardRoundDeal] = []
        current_state = starting_deck_state
        for request in canonical_seats:
            deal = self.card_round_runtime.deal(
                scope=request.dealer_scope,
                state=current_state,
            )
            deals.append(deal)
            # Keep a shared explicit deck state while preserving the pure
            # per-deal conservation proof: a hand becomes discard input for
            # the next seat, and the final state therefore accounts for every
            # dealt physical card exactly once.
            current_state = ModelSODeckState(
                draw_pile=deal.state.draw_pile,
                discard_pile=deal.state.discard_pile + deal.hand,
            )

        contexts: list[ModelSOSeatResolutionContext] = []
        plans: dict[str, ModelSOPlanCommittedPayload] = {}
        rule_handlers = (
            () if self.rule_registry is None else self.rule_registry.select(self.rule_handler_ids)
        )
        for request, deal in zip(canonical_seats, deals, strict=True):
            deck = self.card_round_runtime.snapshot.selected_deck
            locked = heat_locked_indices(request.lock_depth, deck.register_count)
            free_indices = tuple(
                index for index in range(deck.register_count) if index not in locked
            )
            observation = ModelSOProgrammingObservation(
                pilot_observation=request.pilot_observation,
                card_runtime_snapshot=self.card_round_runtime.snapshot,
                seat=request.seat,
                hand=deal.hand,
                free_indices=free_indices,
            )
            programmer = None if self.programmers is None else self.programmers.get(request.seat)
            plan = program_for_seat(programmer, observation, rule_handlers=rule_handlers)
            plans[request.seat] = plan
            contexts.append(
                ModelSOSeatResolutionContext(
                    seat=request.seat,
                    register_count=deck.register_count,
                    initiative=request.initiative,
                    lock_depth=request.lock_depth,
                    plan=plan,
                    previous_plan=request.previous_plan,
                )
            )

        sequence = self.card_round_runtime.sequence(
            deals=tuple(deals),
            contexts=tuple(contexts),
        )
        actions = tuple(
            self._compile_projection(row, canonical_seats, sequence)
            for row in sequence.register_resolved
        )
        values = self._value_records(
            sequence=sequence,
            causation_id=causation_id,
        )
        assert current_state is not None
        return ModelSOCardRoundEmission(
            registers_enabled=True,
            round_index=round_number,
            tick=tick_number,
            causation_id=causation_id,
            values=values,
            actions=actions,
            sequence=sequence,
            deck_state=current_state,
        )

    def _compile_projection(
        self,
        row: ModelSORegisterResolvedPayload,
        seats: tuple[ModelSOCardSeatRequest, ...],
        sequence: ModelSOCardRoundSequence,
    ) -> ModelSOCardIntentProjection:
        if row.outcome is SORegisterOutcome.AUTO_REMAIN:
            return ModelSOCardIntentProjection(
                seat=row.seat,
                register_index=row.register_index,
                action=SOPilotAction.REMAIN,
                outcome=row.outcome,
            )
        assert row.card_id is not None
        assert self.card_round_runtime is not None
        translation = compile_card_action(
            self.card_round_runtime.snapshot.card_catalog.require(row.card_id)
        )
        request = next(request for request in seats if request.seat == row.seat)
        event_type, payload = self._intent_for_translation(translation, request)
        return ModelSOCardIntentProjection(
            seat=row.seat,
            register_index=row.register_index,
            card_id=row.card_id,
            action=translation.action,
            translation=translation,
            event_type=event_type,
            payload=payload,
            outcome=row.outcome,
        )

    @staticmethod
    def _intent_for_translation(
        translation: ModelSOCardActionTranslation,
        request: ModelSOCardSeatRequest,
    ) -> tuple[
        SOEventType,
        ModelSOEmptyPayload
        | ModelSOMoveIntentPayload
        | ModelSOWeaponFireIntentPayload
        | ModelSOModeSwitchIntentPayload,
    ]:
        parameters: ModelSOCardActionParameters = translation.parameters
        if isinstance(parameters, ModelSOCardMovementParameters):
            direction = cast(
                SOMoveDirection,
                {
                    "away_from_enemy": "defensive",
                    "left": "flank_left",
                    "right": "flank_right",
                }.get(parameters.direction, parameters.direction),
            )
            return SOEventType.MOVE_INTENT, ModelSOMoveIntentPayload(
                direction=direction,
                speed=parameters.speed,
            )
        if isinstance(parameters, ModelSOCardRotateParameters):
            direction = "flank_left" if parameters.direction == "left" else "flank_right"
            return SOEventType.MOVE_INTENT, ModelSOMoveIntentPayload(direction=direction)
        if isinstance(parameters, ModelSOCardAttackParameters):
            if parameters.weapon_slot >= len(request.weapon_ids):
                raise CardRunnerAdapterError(
                    f"seat {request.seat!r} card weapon slot {parameters.weapon_slot} "
                    "is absent from injected weapon_ids"
                )
            return SOEventType.WEAPON_FIRE_INTENT, ModelSOWeaponFireIntentPayload(
                weapon_id=request.weapon_ids[parameters.weapon_slot],
                target_mech_id=None,
            )
        if isinstance(parameters, ModelSOCardVentParameters):
            return SOEventType.VENT_INTENT, ModelSOEmptyPayload()
        if isinstance(parameters, ModelSOCardSpecialParameters):
            return SOEventType.MODE_SWITCH_INTENT, ModelSOModeSwitchIntentPayload(
                target_mode=parameters.target_mode
            )
        raise CardRunnerAdapterError(f"unsupported card action parameters: {parameters!r}")

    @staticmethod
    def _value_records(
        *,
        sequence: ModelSOCardRoundSequence,
        causation_id: str,
    ) -> tuple[ModelSOCardRoundValue, ...]:
        values: list[ModelSOCardRoundValue] = []
        previous_by_seat: dict[str, str] = {}

        def append(
            stage: CardRoundStage,
            seat: str,
            payload: (
                ModelSOHandDealtPayload
                | ModelSOPlanCommittedPayload
                | ModelSORegisterResolvedPayload
                | ModelSOCardsDiscardedPayload
            ),
            ordinal: int,
        ) -> None:
            value_id = f"{causation_id}:{stage}:{ordinal}"
            caused_by = previous_by_seat.get(seat, causation_id)
            values.append(
                ModelSOCardRoundValue(
                    stage=stage,
                    ordinal=ordinal,
                    seat=seat,
                    value_id=value_id,
                    caused_by=caused_by,
                    payload=payload,
                )
            )
            previous_by_seat[seat] = value_id

        ordinal = 0
        for hand in sequence.hand_dealt:
            append("HAND_DEALT", hand.seat, hand, ordinal)
            ordinal += 1
        for plan in sequence.plan_committed:
            append("PLAN_COMMITTED", plan.seat, plan, ordinal)
            ordinal += 1
        for resolved in sequence.register_resolved:
            append("REGISTER_RESOLVED", resolved.seat, resolved, ordinal)
            ordinal += 1
        for discarded in sequence.cards_discarded:
            append("CARDS_DISCARDED", discarded.seat, discarded, ordinal)
            ordinal += 1
        return tuple(values)

    @staticmethod
    def _non_bool_int(value: int, name: str, *, minimum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise CardRunnerAdapterError(f"{name} must be an integer >= {minimum}")
        return value


__all__ = [
    "CardRunnerAdapter",
    "CardRunnerAdapterError",
    "ModelSOCardIntentProjection",
    "ModelSOCardRoundEmission",
    "ModelSOCardRoundValue",
    "ModelSOCardSeatRequest",
]
