"""Human-editable persona prompts: override algebra, provenance, replay drift.

The operator ask is that a mech's prompt be editable *and* that the edit be
recorded so replay cannot silently diverge.  These tests prove both: an
override replaces the doctrine while preserving the fixed output contract, the
effective prompt is content-addressed and self-validating, and a replay whose
recorded prompt differs from the recomposed prompt fails closed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    CURRENT_CONSUMED_PAYLOAD_MODELS,
    ModelSOMatchStartedPayload,
)
from steel_onslaught.learning.post_match import project_match_learning_evidence
from steel_onslaught.llm.personas import Persona
from steel_onslaught.pilots.persona_prompts import (
    ModelSOEffectivePromptProvenance,
    ModelSOMatchPromptProvenance,
    ModelSOPersonaPromptOverride,
    PersonaPromptOverrideError,
    apply_prompt_overrides,
    build_match_prompt_provenance,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.fixtures.event_samples import build_sample_envelopes
from tests.runtime import runtime_dependencies

pytestmark = pytest.mark.unit

_INSTRUCTION = '\n\nRespond with ONLY a JSON object, no prose, of shape:\n{"action": "remain"}'
_INSTR_SHA = "e" * 64


def _persona(persona_id: str, doctrine: str, temperature: float = 0.7) -> Persona:
    return Persona(
        persona_id=persona_id,
        display_name=persona_id.title(),
        system_prompt=f"{doctrine}{_INSTRUCTION}",
        temperature=temperature,
    )


def _personas() -> dict[str, Persona]:
    return {
        "berserker": _persona("berserker", "You are a RECKLESS BERSERKER."),
        "sniper": _persona("sniper", "You are a PATIENT SNIPER.", temperature=0.5),
    }


def test_override_replaces_doctrine_but_preserves_output_contract() -> None:
    personas = _personas()
    override = ModelSOPersonaPromptOverride(
        persona_id="berserker",
        doctrine="CHARGE and never stop firing.",
        temperature=0.2,
    )
    effective, overridden = apply_prompt_overrides(personas, (override,))

    assert overridden == frozenset({"berserker"})
    prompt = effective["berserker"].system_prompt
    assert prompt.startswith("CHARGE and never stop firing.")
    # The fixed JSON output contract survives verbatim.
    assert prompt.endswith(_INSTRUCTION)
    assert "RECKLESS BERSERKER" not in prompt
    assert effective["berserker"].temperature == 0.2
    # Untouched persona is unchanged.
    assert effective["sniper"] == personas["sniper"]


def test_override_temperature_is_optional() -> None:
    effective, _ = apply_prompt_overrides(
        _personas(),
        (ModelSOPersonaPromptOverride(persona_id="sniper", doctrine="Wait for the perfect shot."),),
    )
    assert effective["sniper"].temperature == 0.5  # inherited from the contract


def test_unknown_persona_override_fails_closed() -> None:
    with pytest.raises(PersonaPromptOverrideError, match="unknown persona"):
        apply_prompt_overrides(
            _personas(),
            (ModelSOPersonaPromptOverride(persona_id="ghost", doctrine="x"),),
        )


def test_duplicate_override_fails_closed() -> None:
    with pytest.raises(PersonaPromptOverrideError, match="duplicate"):
        apply_prompt_overrides(
            _personas(),
            (
                ModelSOPersonaPromptOverride(persona_id="sniper", doctrine="a"),
                ModelSOPersonaPromptOverride(persona_id="sniper", doctrine="b"),
            ),
        )


def test_provenance_marks_source_and_is_content_addressed() -> None:
    effective, overridden = apply_prompt_overrides(
        _personas(),
        (ModelSOPersonaPromptOverride(persona_id="berserker", doctrine="CHARGE."),),
    )
    provenance = build_match_prompt_provenance(
        effective,
        overridden_persona_ids=overridden,
        programming_instructions_sha256=_INSTR_SHA,
    )
    # Ascending persona order and correct source attribution.
    assert [p.persona_id for p in provenance.prompts] == ["berserker", "sniper"]
    assert provenance.require("berserker").source == "operator_override"
    assert provenance.require("sniper").source == "contract"
    # Recomputing from the same personas is byte-identical (deterministic).
    again = build_match_prompt_provenance(
        effective,
        overridden_persona_ids=overridden,
        programming_instructions_sha256=_INSTR_SHA,
    )
    assert again == provenance
    # A single edited doctrine changes the content digest.
    edited_effective, edited_overridden = apply_prompt_overrides(
        _personas(),
        (ModelSOPersonaPromptOverride(persona_id="berserker", doctrine="DIFFERENT."),),
    )
    edited = build_match_prompt_provenance(
        edited_effective,
        overridden_persona_ids=edited_overridden,
        programming_instructions_sha256=_INSTR_SHA,
    )
    assert edited.content_sha256 != provenance.content_sha256


def test_effective_prompt_digest_is_self_validating() -> None:
    with pytest.raises(ValidationError, match="digest does not match"):
        ModelSOEffectivePromptProvenance(
            persona_id="berserker",
            display_name="Berserker",
            source="contract",
            temperature=0.7,
            prompt_sha256="0" * 64,  # wrong digest for the text below
            prompt_text="You are a RECKLESS BERSERKER.",
        )


def _match_prompt_provenance(doctrine: str) -> ModelSOMatchPromptProvenance:
    text = f"{doctrine}{_INSTRUCTION}"
    return build_match_prompt_provenance(
        {"berserker": Persona("berserker", "Berserker", text, 0.2)},
        overridden_persona_ids=frozenset({"berserker"}),
        programming_instructions_sha256=_INSTR_SHA,
    )


class _MemoryLedger:
    def __init__(self, events: list[ModelSOEventEnvelope]) -> None:
        self.events = events

    def append(self, event: ModelSOEventEnvelope) -> None:
        self.events.append(event)

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return (event for event in self.events if event.match_id == match_id)

    def read_after(self, match_id: str, after_tick: int) -> Iterator[ModelSOEventEnvelope]:
        return (
            event for event in self.events if event.match_id == match_id and event.tick > after_tick
        )


def _started_with_prompt(provenance: ModelSOMatchPromptProvenance) -> ModelSOEventEnvelope:
    started = build_sample_envelopes()[SOEventType.MATCH_STARTED]
    return started.model_copy(
        update={
            "payload": {
                **started.payload,
                "prompt_provenance": provenance.model_dump(mode="json"),
            }
        }
    )


def test_prompt_provenance_is_retained_in_start_and_learning_evidence() -> None:
    provenance = _match_prompt_provenance("CHARGE.")
    started = _started_with_prompt(provenance)
    assert started.payload["prompt_provenance"] == provenance.model_dump(mode="json")

    stream = [
        started if event_type is SOEventType.MATCH_STARTED else build_sample_envelopes()[event_type]
        for event_type in CURRENT_CONSUMED_PAYLOAD_MODELS
    ]
    evidence = project_match_learning_evidence(stream)
    assert evidence.prompt_provenance == provenance


def test_replay_detects_edited_prompt_drift() -> None:
    started = _started_with_prompt(_match_prompt_provenance("CHARGE."))
    runtime = runtime_dependencies()
    replay = ReplayEngine(
        _MemoryLedger([started]),
        started.match_id,
        catalog=runtime.catalog,
        event_factory=runtime.event_factory,
        prompt_provenance=_match_prompt_provenance("A COMPLETELY DIFFERENT DOCTRINE."),
    )
    with pytest.raises(ValueError, match="effective prompt provenance does not match"):
        replay.reconstruct_at_tick(0)


def test_replay_without_expected_prompt_accepts_self_consistent_recorded_value() -> None:
    # A bare state-reconstruction replay supplies no expected prompt. The
    # recorded value must still be self-validating: MATCH_STARTED payload
    # validation recomputes the effective-prompt digest, so a tampered prompt
    # text is rejected at parse time even without an external expectation,
    # while a self-consistent one validates.
    provenance = _match_prompt_provenance("CHARGE.")
    started = _started_with_prompt(provenance)
    reparsed = ModelSOMatchStartedPayload.model_validate(started.payload)
    assert reparsed.prompt_provenance == provenance
    tampered = provenance.model_dump(mode="json")
    tampered["prompts"][0]["prompt_text"] = "SILENTLY CHANGED DOCTRINE."
    with pytest.raises(ValidationError, match="digest does not match"):
        ModelSOMatchStartedPayload.model_validate(
            {**started.payload, "prompt_provenance": tampered}
        )
