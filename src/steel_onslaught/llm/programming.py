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
into a different LLM or decide-only pilot.  An explicit ``fallback`` policy
may opt into the deterministic priority planner for callers that choose that
tradeoff deliberately.
"""

from __future__ import annotations

import json
import logging
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

from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.llm.effect import LlmSemanticError, consume_llm_completion
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmResponse,
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

Use every free register exactly once, in ascending register_index order. Use
each physical card at most once and only card ids from ``legal_hand``. The
ONLY legal card IDs are the ``legal_hand`` entries: do not copy ids from the
deck description or persona instructions. Duplicate an id only up to its
``available_copies`` count. Before emitting, check every register against that
allowlist and replace any unavailable tactic with an available card. Never
assign a card to a locked register. Do not add fields, prose, markdown, or
comments. Keep rationale to twelve words or fewer. Emit the JSON object as the
first character of the response and stop immediately after its closing brace.
""".strip()


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
    return {
        "id": dumped["id"],
        "category": dumped["category"],
        "priority": dumped["priority"],
        "heat_cost": dumped["heat_cost"],
        "effect": dumped["effect"],
    }


def _serialize_programming_observation(observation: ModelSOProgrammingObservation) -> str:
    """Build a compact, deterministic prompt from one typed observation."""

    deck = observation.deck
    free_indices = tuple(observation.free_indices)
    locked_indices = tuple(
        index for index in range(deck.register_count) if index not in free_indices
    )
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
            "register_count": deck.register_count,
            "locked_indices": locked_indices,
            "free_indices": free_indices,
        },
        # The full deck is intentionally not repeated here.  It is a tempting
        # source of otherwise-valid-looking ids for providers that must choose
        # only from this round's dealt hand.  The hand definitions below carry
        # all card semantics needed for planning; ``legal_hand`` is the closed
        # multiset boundary used by the parser.
        "deck": {
            "deck_id": deck.id,
            "display_name": deck.display_name,
            "hand_size": deck.hand_size,
            "register_count": deck.register_count,
        },
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
    "rationale under twelve words. No reasoning, prose, markdown, or extra keys."
)


class LLMProgrammingPilot:
    """A whole-round ``ProgrammingPilot`` backed by an injected LLM client."""

    def __init__(
        self,
        *,
        client: ProtocolLlmClient,
        persona: Persona,
        failure_policy: LlmProgrammingFailurePolicy = "raise",
        correlation_id: UUID | None = None,
    ) -> None:
        if failure_policy not in ("raise", "fallback"):
            raise ValueError(f"unknown LLM programming failure policy: {failure_policy!r}")
        self._client = client
        self._persona = persona
        self._failure_policy = failure_policy
        self._correlation_id = correlation_id

    def program(self, observation: ModelSOProgrammingObservation) -> ModelSOPlanCommittedPayload:
        """Request, parse, and strictly validate one complete register plan."""

        request = ModelSOLlmCompletionRequest(
            system_prompt=f"{self._persona.system_prompt}\n\n{_PROGRAMMING_INSTRUCTIONS}",
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
        try:
            return consume_llm_completion(
                client=self._client,
                request=request,
                consumer=lambda response: self._parse_response(response, observation),
            )
        except LlmSemanticError as exc:
            if self._failure_policy == "fallback":
                return program_for_seat(None, observation)
            if exc.code != "malformed_json":
                raise
            # Some reasoning providers occasionally spend the full response
            # budget before emitting the requested object.  A single compact
            # semantic repair remains on the same injected provider and uses
            # the same evidence context; it never changes provider or falls
            # back to a deterministic pilot.
            repair_request = request.model_copy(
                update={
                    "system_prompt": _PROGRAMMING_REPAIR_INSTRUCTIONS,
                    "user_prompt": _serialize_repair_observation(observation),
                    "temperature": 0.0,
                    "persona": f"{self._persona.persona_id}.repair",
                }
            )
            try:
                return consume_llm_completion(
                    client=self._client,
                    request=repair_request,
                    consumer=lambda response: self._parse_response(response, observation),
                )
            except LlmCompletionBoundaryError:
                raise
            except Exception:
                pass
            raise exc
        except LlmCompletionBoundaryError:
            # Provider length/timeout boundaries are terminal live-match
            # failures. Never convert them into a deterministic card plan.
            raise
        except Exception as exc:
            _LOG.warning("LLM programming call failed (%s)", type(exc).__name__)
            if self._failure_policy == "fallback":
                # This fallback is explicit and deterministic. It never calls
                # a decide-only pilot or another provider.
                return program_for_seat(None, observation)
            raise

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
                # complete JSON object in a short markdown/thought prefix.
                # Strip only that wrapper; the inner object remains subject to
                # the closed response model and the canonical plan validator.
                text = response.text.strip()
                start = text.find("{")
                end = text.rfind("}")
                if start < 0 or end <= start:
                    raise
                parsed = _ModelSOLlmProgrammingResponse.model_validate_json(text[start : end + 1])
        except (ValidationError, ValueError, TypeError):
            raise LlmSemanticError("malformed_json") from None

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
            )
            # Run the candidate through the canonical boundary here so an
            # observed completion is resolved only after hand/register checks.
            return program_for_seat(_ValueProgrammer(plan), observation)
        except (ProgrammingPilotError, TypeError, ValueError):
            raise LlmSemanticError("invalid_action_parameters") from None


__all__ = [
    "LLMProgrammingPilot",
    "LlmProgrammingFailurePolicy",
]
