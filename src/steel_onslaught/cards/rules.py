"""Pure, allowlisted card-programming rule plugins.

The card runner owns dealing and reduction; this module owns neither.  A rule
plugin only transforms a typed proposed plan against an immutable programming
observation.  The composition root selects an ordered registry entry and
passes it to :func:`program_for_seat`, so experiments can change policy
without changing the canonical reducer or movement physics.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from steel_onslaught.contracts.card import SOCardCategory
from steel_onslaught.contracts.range_policy import ModelSOPreferredRangePolicy
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import (
    CardProgrammingRuleHandler,
    ModelSOCardRuleHandlerMetadata,
    ModelSOCardRulePackProvenance,
    ModelSOProgrammingObservation,
)


class CardProgrammingRuleError(ValueError):
    """A rule registry or plugin violated its explicit typed boundary."""


class PreferredRangePolicyError(CardProgrammingRuleError):
    """A plan violates an injected preferred-range policy."""


def _pack_digest(pack_id: str, handlers: tuple[ModelSOCardRuleHandlerMetadata, ...]) -> str:
    payload = {
        "pack_id": pack_id,
        "handlers": [handler.model_dump(mode="json") for handler in handlers],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CardProgrammingRuleRegistry:
    """An immutable allowlist of rule implementations.

    ``select`` is the only supported lookup path.  Unknown, duplicate, or
    empty selections fail closed before a match can start.  The ordered
    selection is also content-addressed for match provenance.
    """

    pack_id: str
    handlers: tuple[CardProgrammingRuleHandler, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.pack_id, str) or not self.pack_id:
            raise CardProgrammingRuleError("rule pack id must be a non-empty string")
        by_id: dict[str, CardProgrammingRuleHandler] = {}
        for handler in self.handlers:
            if not isinstance(handler, CardProgrammingRuleHandler):
                raise CardProgrammingRuleError(
                    "rule registry entries must expose typed metadata and callable apply"
                )
            metadata = handler.metadata
            if not isinstance(metadata, ModelSOCardRuleHandlerMetadata):
                raise CardProgrammingRuleError("rule handler metadata is not the closed contract")
            if metadata.handler_id in by_id:
                raise CardProgrammingRuleError(
                    f"duplicate card rule handler id {metadata.handler_id!r}"
                )
            by_id[metadata.handler_id] = handler
        object.__setattr__(self, "handlers", tuple(self.handlers))
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    # The private map is set once in ``__post_init__``; it is deliberately not
    # part of the constructor or serialized contract.
    _by_id: Mapping[str, CardProgrammingRuleHandler] = field(
        default_factory=lambda: MappingProxyType({}),
        init=False,
        repr=False,
        compare=False,
    )

    def select(self, handler_ids: Sequence[str] = ()) -> tuple[CardProgrammingRuleHandler, ...]:
        """Resolve an ordered allowlisted selection, rejecting unknown ids."""

        selected: list[CardProgrammingRuleHandler] = []
        seen: set[str] = set()
        for handler_id in handler_ids:
            if not isinstance(handler_id, str) or not handler_id:
                raise CardProgrammingRuleError("selected card rule ids must be non-empty strings")
            if handler_id in seen:
                raise CardProgrammingRuleError(f"duplicate selected card rule id {handler_id!r}")
            seen.add(handler_id)
            try:
                selected.append(self._by_id[handler_id])
            except KeyError as exc:
                raise CardProgrammingRuleError(
                    f"card rule handler {handler_id!r} is not registered in pack {self.pack_id!r}"
                ) from exc
        return tuple(selected)

    def provenance(self, handler_ids: Sequence[str] = ()) -> ModelSOCardRulePackProvenance:
        """Return the content-addressed identity of a selected rule pack."""

        selected = self.select(handler_ids)
        metadata = tuple(handler.metadata for handler in selected)
        return ModelSOCardRulePackProvenance(
            pack_id=self.pack_id,
            handlers=metadata,
            content_sha256=_pack_digest(self.pack_id, metadata),
        )


class PreferAttackCardsRuleHandler:
    """Replace lower-priority proposed cards with unused attack cards.

    This is intentionally an opt-in policy plugin.  It is useful for a
    fire-dense experiment, but does not alter card definitions, register
    economics, or the canonical reducer.  If the dealt hand has no unused
    attack card, the proposal is returned unchanged.
    """

    metadata: ModelSOCardRuleHandlerMetadata = ModelSOCardRuleHandlerMetadata(
        handler_id="prefer_attack_cards",
        version="v1.0.0",
        implementation_sha256=hashlib.sha256(
            b"steel_onslaught.cards.rules.PreferAttackCardsRuleHandler:v1.0.0"
        ).hexdigest(),
    )

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload:
        hand_cards = {card.id: card for card in observation.hand_cards}
        used = {register.card_id for register in proposed_plan.registers}
        attack_ids = sorted(
            (
                card.id
                for card in hand_cards.values()
                if card.category is SOCardCategory.ATTACK and card.id not in used
            ),
            key=str,
        )
        if not attack_ids:
            return proposed_plan

        replacement_index = 0
        registers: list[ModelSOPlanRegister] = []
        for register in proposed_plan.registers:
            card = hand_cards[register.card_id]
            if card.category is not SOCardCategory.ATTACK and replacement_index < len(attack_ids):
                card_id = attack_ids[replacement_index]
                replacement_index += 1
            else:
                card_id = register.card_id
            registers.append(
                ModelSOPlanRegister(register_index=register.register_index, card_id=card_id)
            )
        rationale = proposed_plan.rationale
        rule_note = f"rule:{self.metadata.handler_id}"
        rationale = rule_note if not rationale else f"{rationale}; {rule_note}"
        return ModelSOPlanCommittedPayload(
            seat=proposed_plan.seat,
            registers=tuple(registers),
            rationale=rationale,
            confidence=proposed_plan.confidence,
        )


class PreferredRangeRuleHandler:
    """Repair forbidden retreat cards when an archetype is outside range.

    This is a pure, allowlisted plan transform.  It does not infer range from
    card names, call a provider, or mutate reducer state: the immutable pilot
    observation supplies the latest enemy distance and the injected policy
    supplies the archetype and preferred band.  A Berserker outside its band
    therefore cannot silently turn ``movement.reposition`` into a retreat;
    the handler swaps each away card for an available approach card, or fails
    closed when no legal replacement exists.
    """

    metadata: ModelSOCardRuleHandlerMetadata = ModelSOCardRuleHandlerMetadata(
        handler_id="preferred_range_guard",
        version="v1.0.0",
        implementation_sha256=hashlib.sha256(
            b"steel_onslaught.cards.rules.PreferredRangeRuleHandler:v1.0.0"
        ).hexdigest(),
    )

    def __init__(self, policy: ModelSOPreferredRangePolicy) -> None:
        if not isinstance(policy, ModelSOPreferredRangePolicy):
            raise TypeError("preferred range handler requires the typed range policy contract")
        self._policy = policy

    @staticmethod
    def _enemy_distance(observation: ModelSOProgrammingObservation) -> float | None:
        readings = observation.pilot_observation.enemy_observations
        if not readings:
            return None
        return max(
            readings,
            key=lambda reading: (reading.tick, reading.enemy_mech_id),
        ).distance_estimate

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload:
        policy = self._policy
        distance = self._enemy_distance(observation)
        if (
            distance is None
            or distance <= policy.preferred_max
            or not policy.forbid_away_outside_range
            or policy.outside_range_direction == "away_from_enemy"
        ):
            return proposed_plan

        hand_cards = {card.id: card for card in observation.hand_cards}
        retreat_registers = tuple(
            register
            for register in proposed_plan.registers
            if hand_cards[register.card_id].category is SOCardCategory.MOVEMENT
            and hand_cards[register.card_id].effect.direction == "away_from_enemy"
        )
        if not retreat_registers:
            return proposed_plan

        used_counts: Counter[str] = Counter(
            str(register.card_id) for register in proposed_plan.registers
        )
        available_counts = Counter(str(card_id) for card_id in observation.hand)
        available_counts.subtract(used_counts)
        replacement_cards = sorted(
            (
                card
                for card in hand_cards.values()
                if card.category is SOCardCategory.MOVEMENT
                and card.effect.direction == policy.outside_range_direction
                for _ in range(max(0, available_counts[str(card.id)]))
            ),
            key=lambda card: (-card.priority, str(card.id)),
        )
        if len(replacement_cards) < len(retreat_registers):
            raise PreferredRangePolicyError(
                f"{policy.policy_id} forbids away movement for {policy.archetype} outside "
                f"preferred range {policy.preferred_max}, but the hand has only "
                f"{len(replacement_cards)} legal approach card(s) for "
                f"{len(retreat_registers)} retreat register(s)"
            )

        replacement_by_index = {
            register.register_index: card.id
            for register, card in zip(retreat_registers, replacement_cards, strict=True)
        }
        registers = tuple(
            ModelSOPlanRegister(
                register_index=register.register_index,
                card_id=replacement_by_index.get(register.register_index, register.card_id),
            )
            for register in proposed_plan.registers
        )
        rule_note = f"range_policy:{policy.policy_id}:approach"
        rationale = proposed_plan.rationale
        rationale = rule_note if not rationale else f"{rationale}; {rule_note}"
        return ModelSOPlanCommittedPayload(
            seat=proposed_plan.seat,
            registers=registers,
            rationale=rationale,
            confidence=proposed_plan.confidence,
        )


def default_rule_registry(
    *, preferred_range_policy: ModelSOPreferredRangePolicy | None = None
) -> CardProgrammingRuleRegistry:
    """Build the application allowlist with explicitly injected policy seams.

    The existing attack preference remains the only handler in the no-argument
    registry.  A composition root that selects a preferred-range contract must
    pass it explicitly; this prevents an ambient balance rule from changing
    matches that did not opt into the experiment.
    """

    handlers: list[CardProgrammingRuleHandler] = [PreferAttackCardsRuleHandler()]
    if preferred_range_policy is not None:
        handlers.append(PreferredRangeRuleHandler(preferred_range_policy))
    return CardProgrammingRuleRegistry(
        pack_id="rules.card_programming_v1",
        handlers=tuple(handlers),
    )


__all__ = [
    "CardProgrammingRuleError",
    "CardProgrammingRuleRegistry",
    "PreferAttackCardsRuleHandler",
    "PreferredRangePolicyError",
    "PreferredRangeRuleHandler",
    "default_rule_registry",
]
