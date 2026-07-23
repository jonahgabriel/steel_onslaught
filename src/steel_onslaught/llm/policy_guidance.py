"""Deterministic policy-guidance rendering for the programming prompt.

This is the first live consumer of ``ModelSOLiveLearningPolicy.parameters``
(design 2026-07-22 §4.5): policy parameters are *selection biases*, rendered
into the whole-round programming prompt as a code-owned guidance block exactly
parallel to the code-owned ``_PROGRAMMING_INSTRUCTIONS`` wire-contract block.

Determinism contract: the rendered block is a pure function of the policy
value — the same policy always renders to a byte-identical block, and any
parameter change (which necessarily changes ``spec_hash``) changes the block.
The block's provenance is therefore exactly the per-seat
``ModelSOSeatPolicyProvenance`` recorded in ``MATCH_STARTED``: policy_id +
spec_hash + generation pin the block bytes without hashing prompt text twice.

The block deliberately does NOT touch ``_PROGRAMMING_INSTRUCTIONS``:
``PROGRAMMING_INSTRUCTIONS_SHA256`` stays stable whether or not a policy is
in play, and a match without a live-learning policy composes a byte-identical
prompt to the pre-policy tree.
"""

from __future__ import annotations

import json

from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy

# Semantics for parameters the guidance knows how to translate into selection
# behavior.  A parameter without an entry still renders (in the canonical
# parameter line) but gains no extra interpretation sentence — the model sees
# the raw bias value either way.
_KNOWN_PARAMETER_SEMANTICS: dict[str, str] = {
    "aggression": (
        "aggression: scale of 0.0 (fully cautious) to 3.0 (maximally "
        "aggressive). Higher values mean: when selecting which over-dealt "
        "cards to program, prefer weapon and attack cards over movement and "
        "vent cards in proportion to this value. At high aggression, fill "
        "nearly every free register with legal attack cards; at low "
        "aggression, prefer repositioning and heat management."
    ),
}


def render_policy_guidance(policy: ModelSOLiveLearningPolicy) -> str:
    """Render one policy snapshot into its deterministic prompt block.

    Pure and total for any valid policy: sorted keys, canonical compact JSON,
    fixed template text.  Same policy -> byte-identical block.
    """

    parameters_json = json.dumps(
        {name: policy.parameters[name] for name in sorted(policy.parameters)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    lines = [
        "POLICY GUIDANCE (learned selection biases for this seat):",
        f"policy_id={policy.policy_id} generation={policy.generation}",
        f"parameters={parameters_json}",
        (
            "Apply each parameter as a bias on THIS round's card selection "
            "from legal_hand. These biases adjust which legal cards you "
            "prefer; they never override the register rules above."
        ),
    ]
    for name in sorted(policy.parameters):
        semantics = _KNOWN_PARAMETER_SEMANTICS.get(name)
        if semantics is not None:
            lines.append(semantics)
    return "\n".join(lines)


__all__ = ["render_policy_guidance"]
