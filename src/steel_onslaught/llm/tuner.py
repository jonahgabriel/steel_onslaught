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
from typing import Any

from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import BoundsDict
from steel_onslaught.llm.context_arms import ContextArm, assemble_arm_context
from steel_onslaught.llm.schemas import ProtocolLlmClient

_LOG = logging.getLogger(__name__)

_PROPOSAL_PROMPT = """

You are tuning the parameters of a heuristic pilot for a steampunk mech combat
game. Propose {n} DISTINCT improved parameter sets as a JSON array. Each set
must be a JSON object with the parameter names and values shown above. Values
must be within the declared bounds. Return ONLY the JSON array, no prose.

JSON shape: [{{"param_name": value, ...}}, ...]
"""


def _snap_to_lattice(value: float, bound: Any) -> float | int | None:
    """Snap a numeric value to the nearest lattice point within bounds.

    Returns None if the value is outside the bound's range.
    """
    from steel_onslaught.learning.protocols import ModelSONumericBound

    if not isinstance(bound, ModelSONumericBound):
        return None  # categorical — handled separately
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
    arm: ContextArm,
    archetype: str,
    parent_params: ParamDict,
    bounds: BoundsDict,
    n_proposals: int,
    **arm_kwargs: Any,
) -> tuple[list[tuple[ParamDict, str]], str]:
    """Propose candidate parameter sets via one LLM call.

    Returns (candidates, generator_id) where candidates is a list of
    (ParamDict, selection_reason) tuples ready for ``run_learning_loop``.

    All proposals are snapped to the lattice, validated, and deduped before
    return. On any failure (LLM error, unparseable JSON), returns an empty list
    — the loop will then report "no candidate" (honest, not a crash).
    """
    ctx = assemble_arm_context(
        arm, archetype=archetype, parent_params=parent_params, bounds=bounds, **arm_kwargs
    )
    prompt = ctx.prompt_addendum + _PROPOSAL_PROMPT.format(n=n_proposals)
    model = "stub"

    try:
        response = client.complete(
            system_prompt="You are an expert game-balance tuner. Propose parameter improvements.",
            user_prompt=prompt,
            persona="tuner",
            json_mode=True,
        )
        model = response.model
    except Exception as exc:
        _LOG.warning("LLM tuner call failed: %s", exc)
        return [], f"llm.{model}@{arm.value}"

    # Parse the JSON array of proposals.
    try:
        proposals_raw: list[dict[str, Any]] = json.loads(response.text)
        if not isinstance(proposals_raw, list):
            proposals_raw = []
    except (json.JSONDecodeError, TypeError):
        _LOG.warning("LLM tuner returned unparseable JSON")
        return [], f"llm.{model}@{arm.value}"

    # Snap + validate + dedupe.
    seen_hashes: set[str] = set()
    from steel_onslaught.contracts.lineage import spec_hash

    seen_hashes.add(spec_hash(archetype, parent_params))  # never propose the parent itself
    candidates: list[tuple[ParamDict, str]] = []

    for raw in proposals_raw:
        if not isinstance(raw, dict):
            continue
        snapped: dict[str, Any] = {}
        snapped_any = False
        for name, bound in bounds.items():
            if name not in raw:
                snapped[name] = parent_params.get(name)  # inherit parent value
                continue
            value = raw[name]
            from steel_onslaught.learning.protocols import (
                ModelSOCategoricalBound,
                ModelSONumericBound,
            )

            if isinstance(bound, ModelSONumericBound):
                try:
                    snapped_val = _snap_to_lattice(float(value), bound)
                except (TypeError, ValueError):
                    snapped_val = None
                if snapped_val is not None:
                    snapped[name] = snapped_val
                    snapped_any = True
                else:
                    snapped[name] = parent_params.get(name)
            elif isinstance(bound, ModelSOCategoricalBound):
                validated = _validate_categorical(value, bound)
                if validated is not None:
                    snapped[name] = validated
                    snapped_any = True
                else:
                    snapped[name] = parent_params.get(name)
            else:
                snapped[name] = parent_params.get(name)

        if not snapped_any:
            continue  # proposal didn't change anything after snapping
        h = spec_hash(archetype, snapped)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        candidates.append((snapped, "llm_proposal:snapped"))

    generator_id = f"llm.{model}@{arm.value}"
    return candidates, generator_id


__all__ = ["tune"]
