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

from steel_onslaught.contracts.card import ModelSOCard, SOCardCategory
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import (
    CardProgrammingRuleHandler,
    ModelSOCardRuleCatalogProjection,
    ModelSOCardRuleHandlerDescriptor,
    ModelSOCardRuleHandlerMetadata,
    ModelSOCardRulePackProvenance,
    ModelSOProgrammingObservation,
)


class CardProgrammingRuleError(ValueError):
    """A rule registry or plugin violated its explicit typed boundary."""


def _descriptor(
    *,
    handler_id: str,
    version: str,
    implementation: str,
    display_name: str,
    description: str,
) -> ModelSOCardRuleHandlerDescriptor:
    """Build one handler's identity plus its operator-facing description.

    The implementation digest is derived from the fully qualified class name
    and version so a rename or a version bump is a different identity, while
    editing the human description can never change match provenance.
    """

    return ModelSOCardRuleHandlerDescriptor(
        metadata=ModelSOCardRuleHandlerMetadata(
            handler_id=handler_id,
            version=version,
            implementation_sha256=hashlib.sha256(
                f"{implementation}:{version}".encode()
            ).hexdigest(),
        ),
        display_name=display_name,
        description=description,
    )


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

    def catalog(self, handler_ids: Sequence[str] = ()) -> ModelSOCardRuleCatalogProjection:
        """Enumerate every installed rule with its human description.

        This is the discovery surface an operator (CLI or browser) reads to
        decide what to turn on.  ``select`` remains the only *authority*: the
        selection is still validated and fails closed on an unknown id.  A
        handler that ships no descriptor is a packaging bug and is rejected
        here rather than silently rendered as a blank row.
        """

        descriptors: list[ModelSOCardRuleHandlerDescriptor] = []
        for handler in self.handlers:
            descriptor = getattr(handler, "descriptor", None)
            if not isinstance(descriptor, ModelSOCardRuleHandlerDescriptor):
                raise CardProgrammingRuleError(
                    f"card rule handler {handler.metadata.handler_id!r} does not expose a typed "
                    "ModelSOCardRuleHandlerDescriptor"
                )
            if descriptor.metadata != handler.metadata:
                raise CardProgrammingRuleError(
                    f"card rule handler {handler.metadata.handler_id!r} descriptor metadata "
                    "differs from its provenance metadata"
                )
            descriptors.append(descriptor)
        selected = tuple(handler.metadata.handler_id for handler in self.select(handler_ids))
        return ModelSOCardRuleCatalogProjection(
            pack_id=self.pack_id,
            available=tuple(descriptors),
            enabled_handler_ids=selected,
        )

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

    descriptor: ModelSOCardRuleHandlerDescriptor = _descriptor(
        handler_id="prefer_attack_cards",
        version="v1.0.0",
        implementation="steel_onslaught.cards.rules.PreferAttackCardsRuleHandler",
        display_name="Fire-dense programming",
        description=(
            "Replace non-attack registers with unused attack cards from the dealt hand, "
            "so a round trends toward shooting instead of maneuvering. No-op when the "
            "hand holds no unused attack card."
        ),
    )
    metadata: ModelSOCardRuleHandlerMetadata = descriptor.metadata

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
            # A rule adjusts the plan; it never changes who authored it.
            plan_source=proposed_plan.plan_source,
        )


class EnsureMovementCardRuleHandler:
    """Guarantee every programmed round retains one movement card.

    An LLM card programmer is free to choose a coherent plan, and a perfectly
    valid response can fill every register with attack/vent cards.  That makes
    a match collapse into a stationary exchange even when the dealt hand holds
    flank and reposition options.  This opt-in rule preserves the programmer's
    plan whenever it already moves; otherwise it replaces only the last
    register with the highest-priority unused movement card in the hand.

    The transform is pure, deterministic, and bounded to the immutable hand
    snapshot.  It does not alter card definitions or movement physics.
    """

    descriptor: ModelSOCardRuleHandlerDescriptor = _descriptor(
        handler_id="ensure_movement_card",
        version="v1.0.0",
        implementation="steel_onslaught.cards.rules.EnsureMovementCardRuleHandler",
        display_name="Movement variety",
        description=(
            "Guarantee at least one movement card per round: if the proposed plan has none, "
            "swap the last register for the highest-priority unused movement card in the "
            "hand. No-op when the plan already moves or the hand has no movement card."
        ),
    )
    metadata: ModelSOCardRuleHandlerMetadata = descriptor.metadata

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
        return _restamp(proposed_plan, registers, self.metadata.handler_id)


class CloseTheGapRuleHandler:
    """Forbid retreating while the enemy is outside every weapon's reach.

    Long-range standoff is a legitimate doctrine, but a plan that backs away
    while already out of range cannot produce a shot for either side, which is
    the stalemate shape a large arena makes easy.  When the latest sensor
    reading puts the enemy beyond this mech's longest weapon range, this rule
    swaps ``away_from_enemy`` movement registers for available
    ``toward_enemy`` movement cards from the same hand.

    The band is read from the immutable observation (weapon ranges and the
    newest sensor reading), never from card names, a provider, or reducer
    state, so the rule needs no extra injected policy contract to be
    discoverable and selectable.  If the hand cannot supply enough approach
    cards, the registers it cannot legally repair are left untouched rather
    than aborting a live match on a hand-composition accident.
    """

    descriptor: ModelSOCardRuleHandlerDescriptor = _descriptor(
        handler_id="close_the_gap",
        version="v1.0.0",
        implementation="steel_onslaught.cards.rules.CloseTheGapRuleHandler",
        display_name="No retreat out of range",
        description=(
            "While the newest sensor reading puts the enemy beyond this mech's longest "
            "weapon range, swap away-from-enemy movement registers for available "
            "toward-enemy cards. No-op in range, without sensor contact, or without a "
            "legal approach card."
        ),
    )
    metadata: ModelSOCardRuleHandlerMetadata = descriptor.metadata

    @staticmethod
    def _latest_enemy_distance(observation: ModelSOProgrammingObservation) -> float | None:
        readings = observation.pilot_observation.enemy_observations
        if not readings:
            return None
        newest = max(readings, key=lambda reading: (reading.tick, reading.enemy_mech_id))
        return newest.distance_estimate

    @staticmethod
    def _longest_weapon_range(observation: ModelSOProgrammingObservation) -> int | None:
        weapons = observation.pilot_observation.weapons
        if not weapons:
            return None
        return max(weapon.range for weapon in weapons)

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload:
        distance = self._latest_enemy_distance(observation)
        reach = self._longest_weapon_range(observation)
        if distance is None or reach is None or distance <= float(reach):
            return proposed_plan

        hand_cards = {card.id: card for card in observation.hand_cards}

        def _direction(card_id: str) -> str | None:
            card = hand_cards[card_id]
            if card.category is not SOCardCategory.MOVEMENT:
                return None
            return card.effect.direction

        retreat_indices = [
            position
            for position, register in enumerate(proposed_plan.registers)
            if _direction(register.card_id) == "away_from_enemy"
        ]
        if not retreat_indices:
            return proposed_plan

        remaining: Counter[str] = Counter(str(card_id) for card_id in observation.hand)
        remaining.subtract(str(register.card_id) for register in proposed_plan.registers)
        approach_ids: list[str] = []
        for card in sorted(hand_cards.values(), key=lambda item: (-item.priority, str(item.id))):
            if card.category is not SOCardCategory.MOVEMENT:
                continue
            if card.effect.direction != "toward_enemy":
                continue
            approach_ids.extend([str(card.id)] * max(0, remaining[str(card.id)]))
        if not approach_ids:
            return proposed_plan

        replacements = dict(zip(retreat_indices, approach_ids, strict=False))
        registers = tuple(
            ModelSOPlanRegister(
                register_index=register.register_index,
                card_id=replacements.get(position, register.card_id),
            )
            for position, register in enumerate(proposed_plan.registers)
        )
        if registers == proposed_plan.registers:
            return proposed_plan
        return _restamp(proposed_plan, registers, self.metadata.handler_id)


class OverpressureCooldownRuleHandler:
    """c11 Overpressure Cooldown — a heat-lockout resource on the shared pool.

    This is the allowlisted, plan-time half of the c11 balance fix. It folds the
    proposed round's fire/vent registers over the pilot's *own* event-sourced
    heat pool (``boiler.heat_current``) and, whenever the next admissible shot
    would cross the boiler's overpressure ceiling (``boiler.heat_capacity``),
    EXCHANGES that attack register with a later vent register in the same round
    (a multiset-preserving permutation, never a substitution): the vent moves
    earlier to cool this tick and the shot is deferred to the vent's slot, where
    it is re-gated. If the dealt round holds no spendable vent the shot fires and
    the dormant redline backstop remains. The effect is simultaneously a sniper
    RATE-tax (fewer shells per approach) and a brawler APPROACH-tool (the
    forced-vent register is a non-firing window to close distance).

    It is intentionally NOT a hidden core-sim conditional: it is a pure
    transform of a typed plan against the immutable programming observation,
    identical for the LLM programmer and the deterministic priority planner, and
    revalidated against the dealt hand by ``program_for_seat``. The runtime heat
    economy (WEAPON_FIRED adds ``heat_generated``, MATCH_TICK vents
    ``heat_vent_rate``) is the source of truth; this handler only decides which
    registers are allowed to fire, so replay stays exact from the committed plan.

    Projection model (paced cadence: one register resolves per tick):
      - Cooldowns are seeded from ``weapons[slot].cooldown_remaining_ticks`` and
        decremented one tick per register, so an attack the weapon cannot yet
        fire is never counted as heat and never swapped (it would resolve as a
        no-op regardless — addressing the "don't overcount the effect" review).
      - Each register-tick vents ``heat_vent_rate`` first, then a firing register
        adds ``heat_generated`` — mirroring the runtime tick order (vent on
        MATCH_TICK, then WEAPON_FIRED during the card round).
      - A fired weapon is modeled as unavailable for the remainder of the round
        (base cooldowns are not surfaced in the observation; artillery/harpoon
        cooldowns exceed a 5-register round, so this round-granularity is exact
        for the c11 loadouts and conservative otherwise).
    """

    descriptor: ModelSOCardRuleHandlerDescriptor = _descriptor(
        handler_id="overpressure_cooldown",
        version="v1.0.0",
        implementation="steel_onslaught.cards.rules.OverpressureCooldownRuleHandler",
        display_name="Overpressure cooldown (heat lockout)",
        description=(
            "Fold the round's shots over the boiler heat pool; when the next shot would "
            "cross heat_capacity, force an emergency vent (or a non-attack card) instead. "
            "A sniper rate-tax and the brawler's approach window. No-op when no shot overheats."
        ),
    )
    metadata: ModelSOCardRuleHandlerMetadata = descriptor.metadata

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload:
        boiler = observation.pilot_observation.boiler
        weapons = observation.pilot_observation.weapons
        capacity = boiler.heat_capacity
        vent_rate = boiler.heat_vent_rate
        hand_cards = {card.id: card for card in observation.hand_cards}

        # The result is a PERMUTATION of the proposed round's cards across the
        # same register slots — never a substitution with an unused card. The
        # deterministic priority planner consumes the whole hand (no card is
        # left over to swap in), so a heat-blocked attack is EXCHANGED with a
        # later non-attack register (a vent, preferred): the vent moves earlier
        # to cool, the shot is deferred to the later slot (and re-gated there).
        # Multiset-preserving, so ``_validate_plan`` accepts it.
        result_ids = [str(register.card_id) for register in proposed_plan.registers]

        cooldown: dict[int, int] = {
            slot: max(0, weapon.cooldown_remaining_ticks) for slot, weapon in enumerate(weapons)
        }
        locked_for_round = len(proposed_plan.registers) + 1

        projected = boiler.heat_current
        changed = False

        for position in range(len(result_ids)):
            # One tick elapses per register in the paced cadence.
            for cd_slot in cooldown:
                cooldown[cd_slot] = max(cooldown[cd_slot] - 1, 0)
            card = hand_cards[result_ids[position]]
            slot = card.effect.weapon_slot if card.category is SOCardCategory.ATTACK else None
            if slot is None or slot < 0 or slot >= len(weapons):
                # Non-attack, or an unfielded hardpoint: one tick passes, cool.
                projected = max(projected - vent_rate, 0)
                continue
            if cooldown[slot] > 0:
                # Cooldown-rejected at runtime: fires nothing, no heat, so it is
                # not a real overheat and must not be swapped or counted.
                projected = max(projected - vent_rate, 0)
                continue
            heat_after_vent = max(projected - vent_rate, 0)
            heat_generated = weapons[slot].heat_generated
            if heat_after_vent + heat_generated >= capacity:
                other = self._later_vent(hand_cards, result_ids, position + 1)
                if other is not None:
                    # Exchange the overheating shot with a later VENT register:
                    # the vent moves earlier to cool this tick, the shot is
                    # deferred to the vent's old slot and re-gated there.
                    # Movement/mode registers are deliberately left in place so
                    # the lockout is a "vent instead of shoot" resource, not a
                    # repositioning side effect.
                    result_ids[position], result_ids[other] = (
                        result_ids[other],
                        result_ids[position],
                    )
                    changed = True
                    projected = heat_after_vent
                    continue
                # No vent card left to spend this round: the shot fires rather
                # than abort a live round on a hand-composition accident. Heat
                # crossing the ceiling without a vent to spend is exactly when
                # the dormant redline backstop remains available.
                projected = min(heat_after_vent + heat_generated, capacity)
                cooldown[slot] = locked_for_round
                continue
            projected = heat_after_vent + heat_generated
            cooldown[slot] = locked_for_round

        if not changed:
            return proposed_plan
        registers = tuple(
            ModelSOPlanRegister(register_index=register.register_index, card_id=card_id)
            for register, card_id in zip(proposed_plan.registers, result_ids, strict=True)
        )
        return _restamp(proposed_plan, registers, self.metadata.handler_id)

    @staticmethod
    def _later_vent(
        hand_cards: Mapping[str, ModelSOCard],
        result_ids: list[str],
        start: int,
    ) -> int | None:
        """Index of the first later register holding a vent card, if any."""

        for index in range(start, len(result_ids)):
            if hand_cards[result_ids[index]].category is SOCardCategory.VENT:
                return index
        return None


def _restamp(
    proposed_plan: ModelSOPlanCommittedPayload,
    registers: tuple[ModelSOPlanRegister, ...],
    handler_id: str,
) -> ModelSOPlanCommittedPayload:
    """Rebuild a plan with an appended rule note, preserving authorship."""

    rule_note = f"rule:{handler_id}"
    rationale = proposed_plan.rationale
    rationale = rule_note if not rationale else f"{rationale}; {rule_note}"
    return ModelSOPlanCommittedPayload(
        seat=proposed_plan.seat,
        registers=registers,
        rationale=rationale,
        confidence=proposed_plan.confidence,
        # A rule adjusts the plan; it never changes who authored it.
        plan_source=proposed_plan.plan_source,
    )


def default_rule_registry() -> CardProgrammingRuleRegistry:
    """Build the application allowlist without enabling any rule by default.

    Installation is not activation: every handler here is discoverable through
    ``catalog()`` but stays inert until an overlay (or the ``so tune`` writer)
    names it in ``balance_rule_pack.handler_ids``.
    """

    return CardProgrammingRuleRegistry(
        pack_id="rules.card_programming_v1",
        handlers=(
            PreferAttackCardsRuleHandler(),
            EnsureMovementCardRuleHandler(),
            CloseTheGapRuleHandler(),
            OverpressureCooldownRuleHandler(),
        ),
    )


__all__ = [
    "CardProgrammingRuleError",
    "CardProgrammingRuleRegistry",
    "CloseTheGapRuleHandler",
    "EnsureMovementCardRuleHandler",
    "OverpressureCooldownRuleHandler",
    "PreferAttackCardsRuleHandler",
    "default_rule_registry",
]
