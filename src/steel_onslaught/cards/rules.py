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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from steel_onslaught.contracts.card import SOCardCategory
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import (
    CardProgrammingRuleHandler,
    ModelSOCardRuleHandlerMetadata,
    ModelSOCardRulePackProvenance,
    ModelSOProgrammingObservation,
)


class CardProgrammingRuleError(ValueError):
    """A rule registry or plugin violated its explicit typed boundary."""


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


class EnsureMovementCardRuleHandler:
    """Ensure each programmed round retains one movement card.

    LLM card programmers are free to choose a coherent plan, but a perfectly
    valid response can fill every register with mode/attack cards.  That
    makes a match collapse into a stationary exchange even when the selected
    deck contains flank and reposition options.  This opt-in rule preserves
    the programmer's plan whenever it already contains movement; otherwise
    it replaces only the lowest-priority register with the highest-priority
    unused movement card from the dealt hand.

    The transform is pure, deterministic, and bounded to the immutable hand
    snapshot.  It does not alter card definitions or movement physics.
    """

    metadata: ModelSOCardRuleHandlerMetadata = ModelSOCardRuleHandlerMetadata(
        handler_id="ensure_movement_card",
        version="v1.0.0",
        implementation_sha256=hashlib.sha256(
            b"steel_onslaught.cards.rules.EnsureMovementCardRuleHandler:v1.0.0"
        ).hexdigest(),
    )

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload:
        hand_cards = {card.id: card for card in observation.hand_cards}
        if any(
            hand_cards[register.card_id].category is SOCardCategory.MOVEMENT
            for register in proposed_plan.registers
        ):
            return proposed_plan

        used = {register.card_id for register in proposed_plan.registers}
        movement_cards = sorted(
            (
                card
                for card in hand_cards.values()
                if card.category is SOCardCategory.MOVEMENT and card.id not in used
            ),
            key=lambda card: (-card.priority, str(card.id)),
        )
        if not movement_cards or not proposed_plan.registers:
            return proposed_plan

        replacement_index = len(proposed_plan.registers) - 1
        replacement_id = movement_cards[0].id
        registers = tuple(
            ModelSOPlanRegister(
                register_index=register.register_index,
                card_id=replacement_id if index == replacement_index else register.card_id,
            )
            for index, register in enumerate(proposed_plan.registers)
        )
        rule_note = f"rule:{self.metadata.handler_id}"
        rationale = proposed_plan.rationale
        rationale = rule_note if not rationale else f"{rationale}; {rule_note}"
        return ModelSOPlanCommittedPayload(
            seat=proposed_plan.seat,
            registers=registers,
            rationale=rationale,
            confidence=proposed_plan.confidence,
        )


def default_rule_registry() -> CardProgrammingRuleRegistry:
    """Build the application allowlist without enabling any rule by default."""

    return CardProgrammingRuleRegistry(
        pack_id="rules.card_programming_v1",
        handlers=(PreferAttackCardsRuleHandler(), EnsureMovementCardRuleHandler()),
    )


__all__ = [
    "CardProgrammingRuleError",
    "CardProgrammingRuleRegistry",
    "EnsureMovementCardRuleHandler",
    "PreferAttackCardsRuleHandler",
    "default_rule_registry",
]
