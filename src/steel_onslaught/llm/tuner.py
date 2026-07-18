"""The LLM tuner — proposes candidate ParamDicts for the learning loop.

Given an archetype, parent params, bounds, and a context arm, the tuner:
  1. Assembles the arm's context (context_arms.py).
  2. Renders a prompt asking the LLM to propose N improved parameter sets.
  3. Makes one LLM call (batch — not per-candidate).
  4. Parses proposals → snaps each numeric to the bounds lattice, validates
     categoricals, dedupes (against parent + within batch).
  5. Returns [(params, selection_reason), ...] for ``run_learning_loop(EXTERNAL)``.

All LLM I/O happens HERE, at the CLI effect boundary, before the pure loop runs.
The loop receives a plain list — no lazy I/O inside it (adversarial verdict C3).
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol

from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import BoundsDict
from steel_onslaught.llm.context_arms import ContextArm, assemble_arm_context
from steel_onslaught.llm.effect import consume_llm_completion
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOLlmEvidenceContext,
    ProtocolLlmClient,
    ProtocolLlmClientFactory,
)

_LOG = logging.getLogger(__name__)


class _LlmTunerResponseError(ValueError):
    """A tuner response failed the tuner's private semantic contract."""


_PROPOSAL_PROMPT = """

You are tuning the parameters of a heuristic pilot for a steampunk mech combat
game. Propose {n} DISTINCT improved parameter sets as a JSON array. Each set
must be a JSON object with the parameter names and values shown above. Values
must be within the declared bounds. Return ONLY the JSON array, no prose.

JSON shape: [{{"param_name": value, ...}}, ...]
"""


@dataclass(frozen=True)
class ModelSOTunerGeneration:
    candidates: tuple[tuple[ParamDict, str], ...]
    generator_id: str
    usage: LlmUsage
    context_manifest_hash: str


class ProtocolTunerGenerator(Protocol):
    def generate(
        self,
        *,
        provider_id: str,
        arm: ContextArm,
        archetype: str,
        parent_params: ParamDict,
        bounds: BoundsDict,
        n_proposals: int,
        evidence_context: ModelSOLlmEvidenceContext,
        **arm_kwargs: Any,
    ) -> ModelSOTunerGeneration: ...


class LlmTunerGenerator:
    """Root-created generator selecting a prebuilt client by explicit provider id."""

    def __init__(self, client_factory: ProtocolLlmClientFactory) -> None:
        self._client_factory = client_factory

    def generate(
        self,
        *,
        provider_id: str,
        arm: ContextArm,
        archetype: str,
        parent_params: ParamDict,
        bounds: BoundsDict,
        n_proposals: int,
        evidence_context: ModelSOLlmEvidenceContext,
        **arm_kwargs: Any,
    ) -> ModelSOTunerGeneration:
        context = assemble_arm_context(
            arm,
            archetype=archetype,
            parent_params=parent_params,
            bounds=bounds,
            **arm_kwargs,
        )
        candidates, generator_id, usage = tune_with_usage(
            client=self._client_factory.client_for(provider_id),
            provider_id=provider_id,
            arm=arm,
            archetype=archetype,
            parent_params=parent_params,
            bounds=bounds,
            n_proposals=n_proposals,
            evidence_context=evidence_context,
            **arm_kwargs,
        )
        return ModelSOTunerGeneration(
            candidates=tuple(candidates),
            generator_id=generator_id,
            usage=usage,
            context_manifest_hash=context.context_manifest_hash,
        )


def _snap_to_lattice(value: float, bound: Any) -> float | int | None:
    """Snap a numeric value to the nearest lattice point within bounds.

    Returns None if the value is outside the bound's range.
    """
    from steel_onslaught.learning.protocols import ModelSONumericBound

    if not isinstance(bound, ModelSONumericBound):
        return None  # categorical — handled separately
    if not math.isfinite(value):
        return None
    clamped = max(bound.minimum, min(bound.maximum, value))
    # Find the nearest lattice point: minimum + k * step
    if bound.step == 0:
        return clamped
    k = round((clamped - bound.minimum) / bound.step)
    snapped = bound.minimum + k * bound.step
    return max(bound.minimum, min(bound.maximum, snapped))


def _validate_categorical(value: Any, bound: Any) -> str | None:
    """Return the value if it's a valid categorical choice, else None."""
    from steel_onslaught.learning.protocols import ModelSOCategoricalBound

    if not isinstance(bound, ModelSOCategoricalBound):
        return None
    if value in bound.choices:
        return str(value)
    return None


def tune(
    *,
    client: ProtocolLlmClient,
    provider_id: str,
    arm: ContextArm,
    archetype: str,
    parent_params: ParamDict,
    bounds: BoundsDict,
    n_proposals: int,
    evidence_context: ModelSOLlmEvidenceContext,
    **arm_kwargs: Any,
) -> tuple[list[tuple[ParamDict, str]], str]:
    """Propose candidate parameter sets via one LLM call.

    Returns (candidates, generator_id) where candidates is a list of
    (ParamDict, selection_reason) tuples ready for ``run_learning_loop``.

    Thin wrapper over :func:`tune_with_usage` for callers that do not need the
    per-call token/cost accounting (e.g. ``so learn``).
    """
    candidates, generator_id, _usage = tune_with_usage(
        client=client,
        provider_id=provider_id,
        arm=arm,
        archetype=archetype,
        parent_params=parent_params,
        bounds=bounds,
        n_proposals=n_proposals,
        evidence_context=evidence_context,
        **arm_kwargs,
    )
    return candidates, generator_id


def tune_with_usage(
    *,
    client: ProtocolLlmClient,
    provider_id: str,
    arm: ContextArm,
    archetype: str,
    parent_params: ParamDict,
    bounds: BoundsDict,
    n_proposals: int,
    evidence_context: ModelSOLlmEvidenceContext,
    **arm_kwargs: Any,
) -> tuple[list[tuple[ParamDict, str]], str, LlmUsage]:
    """Propose candidate parameter sets via one LLM call, returning usage.

    Returns (candidates, generator_id, usage). ``usage`` is the token/cost
    accounting of the single ``complete()`` call — the source of truth for the
    experiment harness's ``cost_per_promotion`` metric. On any failure (LLM
    error, unparseable JSON) the candidate list is empty and usage is whatever
    was accounted (zero on a failed call) — honest, not a crash.
    """
    ctx = assemble_arm_context(
        arm, archetype=archetype, parent_params=parent_params, bounds=bounds, **arm_kwargs
    )
    prompt = ctx.prompt_addendum + _PROPOSAL_PROMPT.format(n=n_proposals)
    model = provider_id
    usage = LlmUsage(prompt_tokens=0, completion_tokens=0, cost_usd=None)

    request = ModelSOLlmCompletionRequest(
        system_prompt=("You are an expert game-balance tuner. Propose parameter improvements."),
        user_prompt=prompt,
        persona="tuner",
        temperature=0.0,
        json_mode=True,
        evidence_context=evidence_context,
    )

    def accept(response: LlmResponse) -> list[tuple[ParamDict, str]]:
        nonlocal model, usage
        model = response.model
        usage = response.usage
        try:
            decoded: object = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            raise _LlmTunerResponseError("unparseable tuner JSON") from None
        if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
            raise _LlmTunerResponseError("tuner response must be an array of objects")
        proposals_raw = decoded

        seen_hashes: set[str] = set()
        from steel_onslaught.contracts.lineage import spec_hash

        seen_hashes.add(spec_hash(archetype, parent_params))
        candidates: list[tuple[ParamDict, str]] = []

        for raw in proposals_raw:
            if set(raw) - set(bounds):
                raise _LlmTunerResponseError("tuner proposal contains unknown parameters")
            snapped: dict[str, Any] = {}
            snapped_any = False
            for name, bound in bounds.items():
                if name not in raw:
                    snapped[name] = parent_params.get(name)
                    continue
                value = raw[name]
                from steel_onslaught.learning.protocols import (
                    ModelSOCategoricalBound,
                    ModelSONumericBound,
                )

                if isinstance(bound, ModelSONumericBound):
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int | float)
                        or not math.isfinite(value)
                    ):
                        raise _LlmTunerResponseError("tuner numeric proposal is not finite")
                    snapped_val = _snap_to_lattice(float(value), bound)
                    if snapped_val is None:
                        raise _LlmTunerResponseError("tuner numeric proposal is invalid")
                    snapped[name] = snapped_val
                    snapped_any = True
                elif isinstance(bound, ModelSOCategoricalBound):
                    validated = _validate_categorical(value, bound)
                    if validated is None:
                        raise _LlmTunerResponseError("tuner categorical proposal is invalid")
                    snapped[name] = validated
                    snapped_any = True
                else:
                    raise _LlmTunerResponseError("tuner bound contract is unsupported")

            if not snapped_any:
                continue
            candidate_hash = spec_hash(archetype, snapped)
            if candidate_hash in seen_hashes:
                continue
            seen_hashes.add(candidate_hash)
            candidates.append((snapped, "llm_proposal:snapped"))
        return candidates

    try:
        candidates = consume_llm_completion(
            client=client,
            request=request,
            consumer=accept,
        )
    except Exception as exc:
        _LOG.warning("LLM tuner call failed (%s)", type(exc).__name__)
        return [], f"llm.{model}@{arm.value}", usage

    generator_id = f"llm.{model}@{arm.value}"
    return candidates, generator_id, usage


__all__ = [
    "LlmTunerGenerator",
    "ModelSOTunerGeneration",
    "ProtocolTunerGenerator",
    "tune",
    "tune_with_usage",
]
