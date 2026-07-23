"""Deterministic policy-guidance rendering + prompt-composition contracts.

L-GATE-2's consumption seam: the guidance block must be a pure function of
the policy (auditable via the seat's ``MATCH_STARTED`` policy provenance),
and its ABSENCE must leave the programming prompt byte-identical to the
pre-policy composition — a match without a live-learning policy is unchanged
(``PROGRAMMING_INSTRUCTIONS_SHA256`` does not rotate).
"""

from __future__ import annotations

import pytest

from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.policy_guidance import render_policy_guidance
from steel_onslaught.llm.programming import (
    _PROGRAMMING_INSTRUCTIONS,
    programming_system_prompt,
)

pytestmark = pytest.mark.unit


def _policy(
    parameters: ParamDict,
    *,
    policy_id: str = "policy.aggressive.genesis",
    generation: int = 0,
) -> ModelSOLiveLearningPolicy:
    return ModelSOLiveLearningPolicy(
        policy_id=policy_id,
        archetype="aggressive",
        parameters=parameters,
        spec_hash=spec_hash("aggressive", parameters),
        generation=generation,
    )


def _persona() -> Persona:
    return Persona(
        persona_id="persona.test.guidance",
        display_name="Guidance Test",
        system_prompt="You are a test pilot.",
        temperature=0.2,
    )


def test_rendering_is_deterministic_byte_for_byte() -> None:
    first = render_policy_guidance(_policy({"aggression": 1.25}))
    second = render_policy_guidance(_policy({"aggression": 1.25}))

    assert first == second
    assert first.startswith("POLICY GUIDANCE")


def test_rendering_changes_when_a_parameter_changes() -> None:
    genesis = render_policy_guidance(_policy({"aggression": 1.0}))
    promoted = render_policy_guidance(
        _policy(
            {"aggression": 1.25},
            policy_id="policy.aggressive.abcdef0123456789",
            generation=0,
        )
    )

    assert genesis != promoted
    assert '"aggression":1.0' in genesis
    assert '"aggression":1.25' in promoted


def test_rendering_pins_policy_identity_and_generation() -> None:
    block = render_policy_guidance(_policy({"aggression": 1.0}))

    assert "policy_id=policy.aggressive.genesis generation=0" in block


def test_known_parameter_gains_selection_semantics_and_unknown_does_not() -> None:
    known = render_policy_guidance(_policy({"aggression": 2.0}))
    unknown = render_policy_guidance(_policy({"mystery_bias": 2.0}))

    assert "prefer weapon and attack cards" in known
    assert "prefer weapon and attack cards" not in unknown
    assert '"mystery_bias":2.0' in unknown


def test_prompt_without_guidance_is_byte_identical_to_pre_policy_composition() -> None:
    persona = _persona()

    composed = programming_system_prompt(persona)

    assert composed == f"{persona.system_prompt}\n\n{_PROGRAMMING_INSTRUCTIONS}"


def test_prompt_with_guidance_appends_the_block_after_the_wire_contract() -> None:
    persona = _persona()
    block = render_policy_guidance(_policy({"aggression": 1.25}))

    composed = programming_system_prompt(persona, policy_guidance=block)

    assert composed == f"{persona.system_prompt}\n\n{_PROGRAMMING_INSTRUCTIONS}\n\n{block}"
    assert composed.index(_PROGRAMMING_INSTRUCTIONS) < composed.index("POLICY GUIDANCE")


def test_blank_guidance_is_rejected_rather_than_silently_dropped() -> None:
    with pytest.raises(ValueError, match="omitted"):
        programming_system_prompt(_persona(), policy_guidance="   ")
