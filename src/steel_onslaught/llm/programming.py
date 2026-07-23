"""LLM-backed whole-round card programming.

The ordinary :class:`~steel_onslaught.llm.pilot.LLMPilot` chooses one action
for one tick.  Card mode needs a different capability: a pilot must assign an
ordered set of cards to the free registers in one round.  This module keeps
that capability behind the existing ``ProgrammingPilot`` protocol and the
same ``ProtocolLlmClient``/``consume_llm_completion`` evidence seam used by
per-tick LLM decisions.

The provider output is never trusted as a plan.  It is parsed as a closed
Pydantic model, converted to the canonical plan payload, and passed through
``program_for_seat`` before being accepted.  The default failure policy is
``raise``: a failed or semantically invalid completion cannot silently turn
into a different LLM or decide-only pilot.

A live match is LLM-driven end to end, so the deterministic planner is not a
degraded mode this module may choose on its own.  Provider boundary failures
(length/timeout) and every unclassified exception are re-raised so the runner
can end and classify the match.  Only a *typed* ``LlmSemanticError`` on a seat
whose overlay explicitly selected ``fallback`` may take the deterministic
plan, and that plan is stamped ``plan_source=deterministic_fallback`` so the
substitution is durable in the ledger and detectable by replay.

Under the default ``raise`` policy a semantically invalid plan is not a silent
stall and not an immediate death: the *same* model is reprompted with the exact
rejection so it can self-correct, up to a small bounded number of attempts.
This is a bounded reprompt loop, not determinism — every attempt is a real
provider call with its own ``llm_completion_requested``/``llm_completion_failed``
evidence.  When the budget is exhausted the pilot raises
``LlmSemanticExhaustedError`` so the runner ends the match with a distinct
``provider_semantic_failure`` terminal instead of freezing with no terminal.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
)

from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SOPlanSource,
)
from steel_onslaught.llm.effect import LlmSemanticError, consume_llm_completion
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmResponse,
    LlmSemanticExhaustedError,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
    ProtocolLlmClient,
)
from steel_onslaught.pilots.programming import (
    ModelSOProgrammingObservation,
    ProgrammingPilotError,
    program_for_seat,
)

_LOG = logging.getLogger(__name__)

type LlmProgrammingFailurePolicy = Literal["raise", "fallback"]


class _ClosedProgrammingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class _ModelSOLlmProgrammingRegister(_ClosedProgrammingResponse):
    register_index: StrictInt = Field(ge=0)
    card_id: StrictStr = Field(min_length=1)


class _ModelSOLlmProgrammingResponse(_ClosedProgrammingResponse):
    """The only response shape accepted from a whole-round completion."""

    registers: tuple[_ModelSOLlmProgrammingRegister, ...]
    confidence: StrictFloat = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rationale: StrictStr = Field(min_length=1)


class _ValueProgrammer:
    """Tiny adapter used to run a parsed value through ``program_for_seat``."""

    def __init__(self, plan: ModelSOPlanCommittedPayload) -> None:
        self._plan = plan

    def program(self, _observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
        return self._plan


_PROGRAMMING_INSTRUCTIONS = """
This is whole-round card programming, not a per-tick action decision. Ignore
any per-tick action JSON shape from the persona prompt above. Return ONLY one
JSON object with this exact shape:
{"registers":[{"register_index":0,"card_id":"card.example.id"}],
"confidence":0.0,"rationale":"one short sentence"}

Your hand is OVER-DEALT: ``legal_hand`` may hold MORE cards than there are
free registers (see ``selection.hand_size`` vs ``selection.program_count``).
You CHOOSE which cards to program. Every card you do not assign to a free
register is discarded UNPLAYED, so place the strongest card in each register
and let the weakest ones go. Fill every free register exactly once, in
ascending register_index order. Use each physical card at most once and only
card ids from ``legal_hand``. The ONLY legal card IDs are the ``legal_hand``
entries: do not copy ids from the deck description or persona instructions.
Duplicate an id only up to its ``available_copies`` count: an id with
available_copies 1 may appear in at most ONE register, and persona doctrine
never overrides this multiset — when your preferred card runs out, fill the
remaining registers with other legal_hand cards. Before emitting, check every
register against that allowlist and replace any unavailable tactic with an
available card. Never assign a card to a locked register. Do not add fields,
prose, comments, markdown, or code fences. Do not think out loud, emit a
<think> block, or include any chain-of-thought: decide silently and
return only the JSON object. Keep rationale to twelve words or fewer. Emit
the JSON object as the first character of the response and stop immediately
after its closing brace.
""".strip()

# The card-programming instruction block is code-owned and deliberately NOT
# operator-editable: an operator may rewrite how a mech thinks (the persona
# doctrine), never the wire contract the runner parses.  Its digest is still
# part of the recorded decision inputs so a code change to it is visible in
# the ledger alongside the human-edited prompt.
PROGRAMMING_INSTRUCTIONS_SHA256 = hashlib.sha256(
    _PROGRAMMING_INSTRUCTIONS.encode("utf-8")
).hexdigest()


def programming_system_prompt(persona: Persona, *, policy_guidance: str | None = None) -> str:
    """Return the exact system prompt one whole-round programmer will send.

    ``policy_guidance`` is the optional, code-rendered live-learning policy
    block (see ``steel_onslaught.llm.policy_guidance``).  It composes AFTER
    the code-owned instruction block so the wire contract stays first-class,
    and its absence leaves the prompt byte-identical to the policy-free
    composition — a match without a live-learning policy is unchanged.
    """

    base = f"{persona.system_prompt}\n\n{_PROGRAMMING_INSTRUCTIONS}"
    if policy_guidance is None:
        return base
    if not policy_guidance.strip():
        raise ValueError("policy_guidance must be omitted (None) rather than blank")
    return f"{base}\n\n{policy_guidance}"


# Reasoning gateways (e.g. Qwen "thinking" models) may prefix the JSON object
# with a ``<think>...</think>`` chain-of-thought span.  That span routinely
# contains its own braces (the model drafting register JSON while reasoning),
# which defeats the first-'{'/last-'}' extraction below and surfaces as a
# ``malformed_json`` semantic failure — the sniper-specific abort driver, since
# the verbose sniper persona invites more chain-of-thought than the terse
# brawler.  The programming/repair instructions and the persona now forbid the
# span, but a reasoning model can still leak one, so we strip any *complete*
# ``<think>`` spans before extracting the object.  An unterminated span is left
# untouched: that is a truncated (``finish_reason=length``) completion, which is
# a distinct boundary terminal and must not be silently repaired here.
_REASONING_WRAPPER_PATTERN = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def _strip_reasoning_wrapper(text: str) -> str:
    """Remove complete ``<think>...</think>`` reasoning spans from provider text."""

    return _REASONING_WRAPPER_PATTERN.sub("", text).strip()


def _error_detail(exc: BaseException, *, limit: int = 240) -> str:
    """Return a bounded, single-line rejection detail for a repair prompt.

    The message comes from our own closed response model or the canonical plan
    validator (never raw provider text), so it is safe to echo back to the
    model.  It is collapsed to one line and truncated so a verbose
    ``ValidationError`` cannot blow up the repair prompt.
    """

    detail = " ".join(str(exc).split())
    if len(detail) > limit:
        detail = detail[: limit - 1] + "…"
    return detail


def _card_definition(card: object) -> dict[str, object]:
    """Return the small, canonical definition surface exposed to the model."""

    # ``card`` is a validated ModelSOCard from the immutable snapshot. Keeping
    # this helper typed as object prevents accidental coupling to provider
    # payloads while model_dump remains the canonical contract serialization.
    model_dump = getattr(card, "model_dump", None)
    if not callable(model_dump):
        raise TypeError("card definition must expose model_dump")
    dumped = model_dump(mode="json")
    if not isinstance(dumped, dict):
        raise TypeError("card definition model_dump must be a mapping")
    # ``priority`` is deliberately NOT serialized here.  It is an internal
    # simultaneous-resolution tiebreak (utility 280-300, movement 400, attack
    # 600), never a strategic strength ranking, but a model that sees a field
    # literally named "priority" next to "place the strongest card in each
    # register" reads utility (lowest priority) as "weakest, discard".  The
    # engine still owns priority for resolution ordering; the LLM-facing card
    # surface must not leak it as a value signal for ANY category.
    definition: dict[str, object] = {
        "id": dumped["id"],
        "category": dumped["category"],
        "heat_cost": dumped["heat_cost"],
        "effect": dumped["effect"],
    }
    # Optional human-readable tactical description: utility is the only category
    # whose payoff is not otherwise stated by its effect fields, so when a card
    # authors one, surface it so the model can weigh the card on its effect
    # rather than pattern-matching the id string.  Absent for movement/weapon/
    # vent cards, so their serialized definition stays byte-identical.
    description = dumped.get("description")
    if description is not None:
        definition["description"] = description
    return definition


def _serialize_programming_observation(observation: ModelSOProgrammingObservation) -> str:
    """Build a compact, deterministic prompt from one typed observation."""

    # A split-deck observation deliberately has no ``selected_deck_id``: the
    # movement and weapon partitions are the authority for that hand.  The
    # old serializer unconditionally accessed ``observation.deck`` here,
    # which raised before ``consume_llm_completion`` and made a live match
    # appear to freeze at tick one without emitting provider-request
    # telemetry.  Keep the single-deck prompt shape for existing callers, but
    # describe the explicit split boundary with a closed synthetic descriptor
    # assembled only from the typed observation fields.
    if len(observation.hand_deck_ids) > 1:
        if observation.register_count is None:
            raise ValueError("split programming observation requires register_count")
        register_count = observation.register_count
        deck_prompt = {
            "deck_id": "deck.split",
            "display_name": "Split movement and weapon decks",
            "hand_size": len(observation.hand),
            "register_count": register_count,
            "partition_deck_ids": list(observation.hand_deck_ids),
        }
    else:
        deck = observation.deck
        register_count = deck.register_count
        deck_prompt = {
            "deck_id": deck.id,
            "display_name": deck.display_name,
            "hand_size": deck.hand_size,
            "register_count": register_count,
        }
    free_indices = tuple(observation.free_indices)
    locked_indices = tuple(index for index in range(register_count) if index not in free_indices)
    hand_card_ids = tuple(str(card_id) for card_id in observation.hand)
    hand_counts = Counter(hand_card_ids)
    pilot = observation.pilot_observation
    legal_hand = [
        {
            "card_id": card_id,
            "available_copies": hand_counts[card_id],
            "definition": _card_definition(
                observation.card_runtime_snapshot.card_catalog.require(card_id)
            ),
        }
        for card_id in dict.fromkeys(hand_card_ids)
    ]
    prompt_value = {
        "protocol": "steel_onslaught.whole_round_programming.v1",
        "match": {
            "match_id": pilot.match_id,
            "mech_id": pilot.mech_id,
            "player_id": pilot.player_id,
            "seat": observation.seat,
            "tick": pilot.tick,
            "match_elapsed_ticks": pilot.match_elapsed_ticks,
        },
        "registers": {
            "register_count": register_count,
            "locked_indices": locked_indices,
            "free_indices": free_indices,
        },
        # Over-deal legibility: make the "deal more than you program" decision
        # explicit rather than leaving the provider to infer it from a
        # hand/register length mismatch.  ``discard_unprogrammed`` is exactly
        # how many dealt cards the pilot must let go this round.
        "selection": {
            "hand_size": len(hand_card_ids),
            "program_count": len(free_indices),
            "discard_unprogrammed": len(hand_card_ids) - len(free_indices),
            "over_dealt": len(hand_card_ids) > len(free_indices),
        },
        # The full deck is intentionally not repeated here.  It is a tempting
        # source of otherwise-valid-looking ids for providers that must choose
        # only from this round's dealt hand.  The hand definitions below carry
        # all card semantics needed for planning; ``legal_hand`` is the closed
        # multiset boundary used by the parser.
        "deck": deck_prompt,
        "legal_hand": legal_hand,
        "hand": [
            {
                "card_id": card.id,
                "definition": _card_definition(card),
            }
            for card in observation.hand_cards
        ],
        # This is the already-authorized pilot view: own state plus noisy,
        # possibly stale opponent sensor readings. No fold or hidden state is
        # added by this serializer. Keep the two views named explicitly so a
        # provider cannot confuse sensor evidence with authoritative state.
        "own_observation": {
            "boiler": pilot.boiler.model_dump(mode="json"),
            "weapons": [weapon.model_dump(mode="json") for weapon in pilot.weapons],
            "current_mode": pilot.current_mode,
            "mode_lock_expired": pilot.mode_lock_expired,
            "position": pilot.position.model_dump(mode="json"),
            "hp_percent": pilot.hp_percent,
            "under_sensor_lock": pilot.under_sensor_lock,
            "has_line_of_sight_to_enemy": pilot.has_line_of_sight_to_enemy,
            "blocked_directions": pilot.blocked_directions,
        },
        "opponent_observations": [
            reading.model_dump(mode="json") for reading in pilot.enemy_observations
        ],
    }
    # Objective-victory legibility (Phase 4).  Added ONLY when the arena
    # declares objectives, so objective-free prompts stay byte-identical.
    # Without this block the pilots literally cannot play toward VP: the
    # O-GATE battery would measure blindness, not objective play.  The block
    # is deterministic (views are pre-sorted by objective_id) and carries a
    # self-describing rule line so no code-owned instruction text changes.
    #
    # The rule line is the ONLY imperative text inside the user payload, and
    # the O-GATE battery measured what an unguarded imperative-in-data does:
    # 11/413 completions (~2.7 per 100, both seats; 0/840 without the block in
    # the #124 battery) answered the objective imperative with a tiny 31-41
    # token single-action plan instead of the whole-round register program,
    # rejected as ``invalid_action_parameters`` ("program must contain exactly
    # the observation free_indices in canonical order").  The rule therefore
    # subordinates itself to the wire contract explicitly: objectives change
    # WHICH cards are picked, never the response shape, and objective ids are
    # named as map data so they cannot leak into card_id/register values.
    if pilot.objectives and pilot.victory_points is not None:
        prompt_value["objectives"] = {
            "rule": (
                "Victory points win this match: hold an objective cell "
                "(stand within 1 cell of it, uncontested by the enemy) to "
                "score its vp_per_round each round; first side to reach "
                "vp_threshold WINS immediately. Contested cells score for "
                "nobody. Objectives change WHICH cards you pick, never the "
                "response shape: still fill EVERY free register exactly once "
                "with legal_hand card ids. Objective ids and cells are map "
                "data, never card ids or register values. Plan movement "
                "toward scoring or denying objectives with your full "
                "register program."
            ),
            "vp_threshold": pilot.victory_points.vp_threshold,
            "own_vp": pilot.victory_points.own_vp,
            "enemy_vp": pilot.victory_points.enemy_vp,
            "cells": [objective.model_dump(mode="json") for objective in pilot.objectives],
        }
    return json.dumps(prompt_value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _serialize_repair_observation(observation: ModelSOProgrammingObservation) -> str:
    """Build a deliberately tiny retry prompt after provider JSON drift."""

    return json.dumps(
        {
            "free_register_indices": list(observation.free_indices),
            "hand_card_ids": [str(card_id) for card_id in observation.hand],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_PROGRAMMING_REPAIR_INSTRUCTIONS = (
    "Return ONLY compact JSON with keys registers, confidence, rationale. "
    "Use each free register exactly once, use only hand_card_ids, and keep "
    "rationale under twelve words. No reasoning, prose, markdown, or extra "
    "keys. Do NOT think out loud, emit a <think> block or any chain-of-thought, "
    "or wrap the JSON in code fences."
)

# Additional same-model reprompts after the first rejected plan.  Two extra
# attempts (three total provider calls) is enough for a capable model to
# self-correct a strict-schema slip without letting a persistently broken
# provider spin the match.  A bounded reprompt loop is not determinism: every
# attempt is a real, separately-recorded provider completion.
_DEFAULT_SEMANTIC_RETRY_LIMIT = 2


class LLMProgrammingPilot:
    """A whole-round ``ProgrammingPilot`` backed by an injected LLM client."""

    def __init__(
        self,
        *,
        client: ProtocolLlmClient,
        persona: Persona,
        failure_policy: LlmProgrammingFailurePolicy = "raise",
        correlation_id: UUID | None = None,
        provider_id: str | None = None,
        semantic_retry_limit: int = _DEFAULT_SEMANTIC_RETRY_LIMIT,
        policy_guidance: str | None = None,
    ) -> None:
        if failure_policy not in ("raise", "fallback"):
            raise ValueError(f"unknown LLM programming failure policy: {failure_policy!r}")
        if semantic_retry_limit < 0:
            raise ValueError("semantic_retry_limit must not be negative")
        if policy_guidance is not None and not policy_guidance.strip():
            raise ValueError("policy_guidance must be omitted (None) rather than blank")
        self._client = client
        self._persona = persona
        self._failure_policy = failure_policy
        self._correlation_id = correlation_id
        self._provider_id = provider_id
        self._semantic_retry_limit = semantic_retry_limit
        self._policy_guidance = policy_guidance

    def system_prompt(self) -> str:
        """The exact system prompt this programmer sends (persona + wire
        contract + optional policy-guidance block)."""

        return programming_system_prompt(self._persona, policy_guidance=self._policy_guidance)

    def program(self, observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
        """Request, parse, and strictly validate one complete register plan."""

        request = self._build_request(observation)
        try:
            return consume_llm_completion(
                client=self._client,
                request=request,
                consumer=lambda response: self._parse_response(response, observation),
            )
        except LlmSemanticError as exc:
            if self._failure_policy == "fallback":
                return self._classified_fallback(observation, reason=exc.code)
            # A live match is LLM-only: never substitute a deterministic plan.
            # Reprompt the SAME model with the exact rejection so it can
            # self-correct, up to the bounded budget; on exhaustion raise a
            # classified terminal signal the runner converts into MATCH_ENDED.
            return self._reprompt_or_terminate(observation, request, first_error=exc)
        except LlmCompletionBoundaryError:
            # Provider length/timeout boundaries are terminal live-match
            # failures. Never convert them into a deterministic card plan.
            raise
        except Exception:
            # A live match is LLM-driven end to end. An unclassified provider,
            # transport, or programming failure is a match failure: it is
            # re-raised so the runner can classify and end the match, never
            # silently replaced by a deterministic plan behind a log line.
            # Only the typed ``LlmSemanticError`` path above may take the
            # explicitly opted-in recovery, and that plan is stamped
            # ``deterministic_fallback`` in the ledger.
            raise

    def _build_request(
        self, observation: ModelSOProgrammingObservation
    ) -> ModelSOLlmCompletionRequest:
        # ``programming_system_prompt`` composes the (possibly operator-edited)
        # persona doctrine with the code-owned JSON instruction block and the
        # optional live-learning policy-guidance block.  Using it here keeps
        # the human-editable/recorded effective prompt seam intact while the
        # bounded reprompt loop above owns semantic-stall recovery.
        return ModelSOLlmCompletionRequest(
            system_prompt=self.system_prompt(),
            user_prompt=_serialize_programming_observation(observation),
            persona=self._persona.persona_id,
            # Card programming is a typed planning protocol.  Keep the
            # provider's tactical variation in the selected cards and
            # observation, while a low sampling temperature prevents a
            # reasoning gateway from consuming the entire JSON budget.
            temperature=min(self._persona.temperature, 0.2),
            json_mode=True,
            evidence_context=ModelSOLlmEvidenceContext(
                match_id=observation.pilot_observation.match_id,
                mech_id=observation.pilot_observation.mech_id,
                player_id=observation.pilot_observation.player_id,
                tick=observation.pilot_observation.tick,
                correlation_id=self._correlation_id,
            ),
        )

    def _reprompt_or_terminate(
        self,
        observation: ModelSOProgrammingObservation,
        base_request: ModelSOLlmCompletionRequest,
        *,
        first_error: LlmSemanticError,
    ) -> ModelSOPlanCommittedPayload:
        """Reprompt the same model up to the bounded budget, then terminate.

        Each attempt is a real provider completion whose requested/failed
        evidence is durably observed.  A completion boundary (length/timeout)
        during a repair belongs to its own terminal path and is re-raised
        unchanged.  Any other repair-time failure is treated as a spent attempt
        so the match still reaches a durable terminal rather than freezing.
        """

        last_error = first_error
        for attempt in range(1, self._semantic_retry_limit + 1):
            repair_request = self._build_repair_request(
                base_request, observation, last_error, attempt=attempt
            )
            try:
                return consume_llm_completion(
                    client=self._client,
                    request=repair_request,
                    consumer=lambda response: self._parse_response(response, observation),
                )
            except LlmCompletionBoundaryError:
                raise
            except LlmSemanticError as exc:
                last_error = exc
            except Exception:
                # An unclassified repair-time provider/transport error is a
                # spent attempt, not a stall. Keep the last classified semantic
                # code and continue the bounded loop toward a durable terminal.
                _LOG.warning(
                    "live provider repair attempt %d raised an unclassified error "
                    "for seat %s (persona=%s)",
                    attempt,
                    observation.seat,
                    self._persona.persona_id,
                )
        total_attempts = self._semantic_retry_limit + 1
        _LOG.warning(
            "live provider exhausted %d plan attempt(s) for seat %s "
            "(persona=%s, provider=%s, last_code=%s)",
            total_attempts,
            observation.seat,
            self._persona.persona_id,
            self._provider_id,
            last_error.code,
        )
        raise LlmSemanticExhaustedError(
            seat=observation.seat,
            semantic_failure_code=last_error.code,
            attempts=total_attempts,
            provider_id=self._provider_id,
        )

    def _build_repair_request(
        self,
        base_request: ModelSOLlmCompletionRequest,
        observation: ModelSOProgrammingObservation,
        error: LlmSemanticError,
        *,
        attempt: int,
    ) -> ModelSOLlmCompletionRequest:
        """Build a same-model repair request annotated with the exact rejection.

        ``malformed_json`` keeps the compact repair shape (a reasoning gateway
        that spent its budget needs a *smaller* prompt, not a larger one).  A
        structurally-valid-but-illegal plan (unknown/unavailable card, invalid
        parameters) keeps the full observation — the model needs ``legal_hand``
        to pick an admissible card — and gains an explicit correction note.
        """

        correction = self._correction_note(error)
        persona = f"{self._persona.persona_id}.repair.{attempt}"
        if error.code == "malformed_json":
            return base_request.model_copy(
                update={
                    "system_prompt": f"{correction}\n\n{_PROGRAMMING_REPAIR_INSTRUCTIONS}",
                    "user_prompt": _serialize_repair_observation(observation),
                    "temperature": 0.0,
                    "persona": persona,
                }
            )
        return base_request.model_copy(
            update={
                "system_prompt": f"{correction}\n\n{base_request.system_prompt}",
                "temperature": 0.0,
                "persona": persona,
            }
        )

    @staticmethod
    def _correction_note(error: LlmSemanticError) -> str:
        note = f"Your previous plan was REJECTED by the strict rules engine (reason: {error.code})."
        if error.detail:
            note += f" Details: {error.detail}"
        return (
            note + " Return a corrected plan that uses ONLY card ids from legal_hand, "
            "fills every free register exactly once in ascending register_index order, "
            "never exceeds available_copies, never assigns a locked register, and adds "
            "no extra fields. Reply with the whole-round programming JSON object "
            "(keys registers, confidence, rationale) and NEVER the per-tick "
            "action/action_params shape."
        )

    def _classified_fallback(
        self,
        observation: ModelSOProgrammingObservation,
        *,
        reason: str,
    ) -> ModelSOPlanCommittedPayload:
        """Return the deterministic plan under an explicit, recorded policy.

        This is reachable only when the overlay opted a seat into ``fallback``
        and the provider produced a *classified* semantic failure. The plan is
        restamped from the planner's own ``deterministic_planner`` to
        ``deterministic_fallback`` — this seat *was* bound to a provider and
        lost it, which is the one case that is a genuine substitution — so it
        is durable in the ledger and detectable by replay rather than
        indistinguishable from a real provider decision or from a seat that
        was deterministic by design.
        """

        _LOG.warning(
            "LLM programming fell back to the deterministic planner (%s, persona=%s)",
            reason,
            self._persona.persona_id,
        )
        plan = program_for_seat(None, observation)
        return plan.model_copy(update={"plan_source": SOPlanSource.DETERMINISTIC_FALLBACK})

    def _parse_response(
        self,
        response: LlmResponse,
        observation: ModelSOProgrammingObservation,
    ) -> ModelSOPlanCommittedPayload:
        try:
            try:
                parsed = _ModelSOLlmProgrammingResponse.model_validate_json(response.text)
            except (ValidationError, ValueError, TypeError):
                # A few OpenAI-compatible reasoning gateways wrap an otherwise
                # complete JSON object in a markdown/thought prefix.  Strip any
                # complete <think> reasoning span first (it can carry its own
                # braces that would defeat the extraction), then take the outer
                # object.  The inner object remains subject to the closed
                # response model and the canonical plan validator.
                text = _strip_reasoning_wrapper(response.text)
                start = text.find("{")
                end = text.rfind("}")
                if start < 0 or end <= start:
                    raise
                parsed = _ModelSOLlmProgrammingResponse.model_validate_json(text[start : end + 1])
        except (ValidationError, ValueError, TypeError) as exc:
            raise LlmSemanticError("malformed_json", detail=_error_detail(exc)) from None

        try:
            plan = ModelSOPlanCommittedPayload(
                seat=observation.seat,
                registers=tuple(
                    ModelSOPlanRegister(
                        register_index=register.register_index,
                        card_id=register.card_id,
                    )
                    for register in parsed.registers
                ),
                rationale=parsed.rationale,
                confidence=parsed.confidence,
                plan_source=SOPlanSource.LLM,
            )
            # Run the candidate through the canonical boundary here so an
            # observed completion is resolved only after hand/register checks.
            return program_for_seat(_ValueProgrammer(plan), observation)
        except (ProgrammingPilotError, TypeError, ValueError) as exc:
            raise LlmSemanticError("invalid_action_parameters", detail=_error_detail(exc)) from None


__all__ = [
    "PROGRAMMING_INSTRUCTIONS_SHA256",
    "LLMProgrammingPilot",
    "LlmProgrammingFailurePolicy",
    "programming_system_prompt",
]
