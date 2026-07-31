"""Seat-scoped card-programming rule driven by a deterministic pilot spec.

OMN-15489.  In card mode the runner resolves each seat's ``ModelSOPilotSpec``
into a decide-only pilot and then never consults it: ``_run_card_round``
programs registers from the overlay's ``card_catalog.programmers`` bindings
alone.  Every tunable parameter of the heuristic archetypes
(``vent_at_heat_margin``, ``idle_vent_heat_threshold``,
``mode_switch_pressure_floor``, ``mode_switch_heat_ceiling``,
``weapon_preference``) is consumed ONLY by ``pilots/*.decide()``, which is
reachable only through the non-card ``ReducerPilotTick`` branch.  A duel
battery that materializes a candidate and a parent spec and then flies them in
card mode therefore compares two causally identical systems: the promotion
verdict is a judgment about provider variance, not about the parameter.

This module closes that bypass on the EXISTING pure rule seam
(``pilots.programming.program_for_seat`` / ``CardProgrammingRuleHandler``)
rather than by inventing a second decision surface.  The seat's deterministic
policy is projected onto the round as an *action guarantee*: the pilot decides
from the same immutable ``ModelSOPilotObservation`` the non-card branch uses,
and the round is required to contain at least one card that expresses that
decision — its category, and for the two actions whose card carries a
discriminating effect field, the mode-switch target (``target_mode``) or the
chosen weapon's slot (``weapon_slot``).  Nothing else about the programmer's
plan is altered.  Matching on the effect fields rather than the category alone
is what keeps ``weapon_preference`` and the ``mode_switch_*`` pair causal;
category-only matching would leave three of the five aggressive lattice
parameters still inert.

Scope is deliberately narrow:

- Only archetypes with a deterministic, pure ``decide`` policy get a rule.
  ``llm`` seats return ``None`` — their decision surface *is* the programmer,
  their spec carries no search-lattice parameters, and calling an LLM pilot
  from this pure seam would give it provider authority it must never have
  (see ``pilots.programming``'s module docstring).
- The transform is pure, deterministic, and bounded to the dealt hand.  It
  reads no runner state, mutates nothing, and no-ops whenever the hand cannot
  legally satisfy the guarantee.
- It never relaxes a threshold, never rewrites a spec, and never touches the
  promotion statistics.  It only makes the spec *causal*.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from steel_onslaught.contracts.card import ModelSOCard, SOCardCategory
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.pilots.programming import (
    ModelSOCardRuleHandlerMetadata,
    ModelSOProgrammingObservation,
)
from steel_onslaught.pilots.schemas import ModelSOPilotDecision, PilotProtocol, SOPilotAction

RULE_HANDLER_ID = "pilot_policy_category_guard"
RULE_VERSION = "v1.0.0"
_IMPLEMENTATION = "steel_onslaught.cards.pilot_policy.PilotPolicyCategoryRule"

#: Archetypes whose ``decide`` is a pure deterministic function of the
#: observation and the spec parameters.  These are exactly the archetypes the
#: learning lattice (``learning.spec_adapter``) can search, which is why they
#: are the archetypes a duel gate can make a claim about.
DETERMINISTIC_ARCHETYPES: frozenset[str] = frozenset({"aggressive", "defensive", "predictive"})

#: Projection of a decide-only action onto the card category that expresses it.
#: Actions with no single-card analogue (``REMAIN``, ``ACTIVATE_MODULE``,
#: ``EMERGENCY_SHUTDOWN``, ``DISENGAGE``, ``DEPLOY_UTILITY``) are deliberately
#: absent: the rule no-ops rather than inventing a mapping.
_ACTION_CATEGORY: dict[SOPilotAction, SOCardCategory] = {
    SOPilotAction.VENT: SOCardCategory.VENT,
    SOPilotAction.FIRE_WEAPON: SOCardCategory.ATTACK,
    SOPilotAction.MOVE: SOCardCategory.MOVEMENT,
    SOPilotAction.SWITCH_MODE: SOCardCategory.SPECIAL,
}


def _spec_digest(spec: ModelSOPilotSpec) -> str:
    """Content-address this rule instance against the exact spec it enforces.

    Two seats running the same handler with different tunable parameters are
    NOT the same rule — that identity difference is precisely the thing the
    duel gate is supposed to be measuring, so it is part of the handler's
    provenance rather than hidden behind a shared class digest.
    """

    payload = {
        "implementation": _IMPLEMENTATION,
        "version": RULE_VERSION,
        "archetype": spec.archetype,
        "parameters": spec.parameters.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PilotPolicyCategoryRule:
    """Require the round to lead with the action the seat's pilot chose.

    ``apply`` runs the seat's deterministic pilot against the SAME
    ``ModelSOPilotObservation`` the non-card branch would have handed it, maps
    the resulting action onto a card, and then enforces two things and nothing
    else:

    1. **presence** — if no programmed register expresses that action and the
       dealt hand still holds a card that does, the lowest-priority register is
       swapped for the highest-priority such card;
    2. **precedence** — the register expressing that action is moved to the
       earliest index, because registers resolve in index order.

    Precedence is not cosmetic.  Every stock single deck has
    ``hand_size == register_count``, so the deterministic planner programs the
    WHOLE hand and the card *set* is forced; ordering is then the only decision
    that exists, and without (2) the seat spec would stay causally inert on any
    non-over-dealt deck.  Every other aspect of the programmer's plan is
    preserved.

    Determinism: the pilot is pure, the action map is fixed, replacement
    selection is a total order (``-priority``, then card id), the replaced
    register is the lowest-priority one (ties broken by the highest register
    index), and the precedence swap is positional.  Re-running the rule on its
    own output is a no-op.
    """

    def __init__(self, spec: ModelSOPilotSpec, *, pilot: PilotProtocol) -> None:
        if not isinstance(spec, ModelSOPilotSpec):
            raise TypeError("PilotPolicyCategoryRule requires a typed ModelSOPilotSpec")
        if spec.archetype not in DETERMINISTIC_ARCHETYPES:
            raise ValueError(
                f"PilotPolicyCategoryRule requires a deterministic archetype; "
                f"got {spec.archetype!r} (spec id: {spec.id!r})"
            )
        # The pilot is INJECTED, never constructed here: pilot construction is
        # a composition-root privilege (tests/test_di_enforcement.py), and the
        # root has already built this exact seat's pilot from this exact spec.
        self._spec = spec
        self._pilot = pilot
        self.metadata = ModelSOCardRuleHandlerMetadata(
            handler_id=RULE_HANDLER_ID,
            version=RULE_VERSION,
            implementation_sha256=_spec_digest(spec),
        )

    @property
    def spec(self) -> ModelSOPilotSpec:
        """Return the pilot spec whose parameters this rule enforces."""

        return self._spec

    def required_action(self, observation: ModelSOProgrammingObservation) -> ModelSOPilotDecision:
        """Return the seat policy's decision for this observation.

        Exposed so a caller (or a test) can read the causal decision itself
        rather than inferring it from a mutated plan.
        """

        return self._pilot.decide(observation.pilot_observation)

    @staticmethod
    def _weapon_slot_for(
        observation: ModelSOProgrammingObservation, weapon_id: object
    ) -> int | None:
        """Resolve the pilot's chosen weapon id to its register slot index.

        Slot indices address ``mech.weapon_cooldowns`` order, which is the same
        order ``build_pilot_observation`` renders ``weapons`` in — the card
        adapter resolves ``weapon_slot`` against exactly that tuple.  ``None``
        when the decision named no weapon or the id is unknown, in which case
        the rule falls back to category-only matching rather than guessing.
        """

        if not isinstance(weapon_id, str):
            return None
        for index, weapon in enumerate(observation.pilot_observation.weapons):
            if weapon.weapon_id == weapon_id:
                return index
        return None

    def _card_matches(
        self,
        card: ModelSOCard,
        *,
        required: SOCardCategory,
        decision: ModelSOPilotDecision,
        observation: ModelSOProgrammingObservation,
    ) -> bool:
        """Does this card express the exact action the seat's policy chose?

        Category alone would collapse ``weapon_preference`` (both preferences
        map to ATTACK) and the mode-switch target, leaving two of the five
        aggressive lattice parameters still causally inert.  The effect fields
        the card already carries make both distinguishable.
        """

        if card.category is not required:
            return False
        if required is SOCardCategory.SPECIAL:
            target = decision.action_params.get("target_mode")
            return target is None or str(card.effect.target_mode) == str(target)
        if required is SOCardCategory.ATTACK:
            slot = self._weapon_slot_for(observation, decision.action_params.get("weapon_id"))
            return slot is None or card.effect.weapon_slot == slot
        return True

    def apply(
        self,
        observation: ModelSOProgrammingObservation,
        proposed_plan: ModelSOPlanCommittedPayload,
    ) -> ModelSOPlanCommittedPayload:
        decision = self.required_action(observation)
        required = _ACTION_CATEGORY.get(decision.action)
        if required is None or not proposed_plan.registers:
            return proposed_plan

        hand_cards = {card.id: card for card in observation.hand_cards}

        def matches(card: ModelSOCard) -> bool:
            return self._card_matches(
                card, required=required, decision=decision, observation=observation
            )

        card_ids = [str(register.card_id) for register in proposed_plan.registers]
        present = [index for index, card_id in enumerate(card_ids) if matches(hand_cards[card_id])]

        if not present:
            remaining: Counter[str] = Counter(str(card_id) for card_id in observation.hand)
            remaining.subtract(card_ids)
            available = sorted(
                (
                    card
                    for card in hand_cards.values()
                    if matches(card) and remaining[str(card.id)] > 0
                ),
                key=lambda card: (-card.priority, str(card.id)),
            )
            if not available:
                # An over-dealt hand can simply lack the card this policy wants.
                # Refusing to act is correct: the rule may not invent a card,
                # and it must never rewrite a legal plan into something the seat
                # was not dealt.
                return proposed_plan
            # Give up the least valuable programmed register: lowest authored
            # priority, then the latest register index.  A total order keeps the
            # swap replayable.
            position = min(
                range(len(card_ids)),
                key=lambda index: (
                    hand_cards[card_ids[index]].priority,
                    -proposed_plan.registers[index].register_index,
                ),
            )
            card_ids[position] = str(available[0].id)
            present = [position]

        # Registers resolve in index order, so WHEN the chosen action happens is
        # itself a decision — and when the hand exactly fills the registers
        # (every stock single deck: hand_size == register_count) it is the ONLY
        # decision left, because the plan's card SET is forced.  Placing the
        # policy's action first is therefore what keeps the seat spec causal on
        # a non-over-dealt deck instead of only under split-deck over-deal.
        first = min(present)
        if first != 0:
            card_ids[0], card_ids[first] = card_ids[first], card_ids[0]

        if tuple(card_ids) == tuple(str(register.card_id) for register in proposed_plan.registers):
            return proposed_plan

        registers = tuple(
            ModelSOPlanRegister(register_index=register.register_index, card_id=card_ids[index])
            for index, register in enumerate(proposed_plan.registers)
        )
        rule_note = f"rule:{RULE_HANDLER_ID}:{required.value}"
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


def seat_policy_rule_for_spec(
    spec: ModelSOPilotSpec, *, pilot: PilotProtocol
) -> PilotPolicyCategoryRule | None:
    """Build the seat's policy rule, or ``None`` when the spec has no policy.

    ``None`` is returned for ``llm`` (and any future provider-backed)
    archetypes: those seats decide through their bound programmer, and this
    pure seam must never acquire provider authority.  An untyped ``spec`` is a
    hard error rather than a quiet ``None`` — silently dropping the seat's
    policy is precisely the vacuous-gate failure this module exists to close.
    """

    if not isinstance(spec, ModelSOPilotSpec):
        raise TypeError(
            "a card-mode seat must resolve to a typed ModelSOPilotSpec before its "
            f"policy can be bound; got {type(spec).__name__}"
        )
    if spec.archetype not in DETERMINISTIC_ARCHETYPES:
        return None
    return PilotPolicyCategoryRule(spec, pilot=pilot)


__all__ = [
    "DETERMINISTIC_ARCHETYPES",
    "RULE_HANDLER_ID",
    "RULE_VERSION",
    "PilotPolicyCategoryRule",
    "seat_policy_rule_for_spec",
]
