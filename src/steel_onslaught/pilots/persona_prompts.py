"""Human-editable pilot prompts with durable, replayable provenance.

A seat's persona doctrine is the single largest decision input a live match
has that is *not* code: it is authored YAML that becomes the LLM system
prompt.  Making it operator-editable is only safe if the edit is impossible
to hide, so this module pairs two things that must ship together:

* :class:`ModelSOPersonaPromptOverride` — the closed, typed edit an
  application overlay may declare for one persona id.  It replaces the
  authored doctrine (and optionally the sampling temperature) at composition
  time; nothing else about the persona can be redefined.
* :class:`ModelSOMatchPromptProvenance` — the content-addressed record of the
  *effective* prompt every persona flew with, including the full prompt text
  and its digest, plus whether it came from the authored contract or an
  operator override.

The runner writes that provenance into ``MATCH_STARTED`` exactly like the
card rule-pack provenance, and replay compares it, so an edited prompt cannot
escape the evidence and silently diverge a replay.

This module is pure: no filesystem, network, provider, or clock authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr, model_validator

from steel_onslaught.llm.personas import Persona

_PERSONA_ID_PATTERN = r"^[a-z][a-z0-9_.-]*$"


class PersonaPromptOverrideError(ValueError):
    """An operator prompt edit did not satisfy the typed override boundary."""


class _ClosedPromptModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def prompt_sha256(prompt_text: str) -> str:
    """Return the canonical digest of one effective system prompt."""

    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


class ModelSOPersonaPromptOverride(_ClosedPromptModel):
    """One operator-authored replacement for a persona's doctrine.

    ``doctrine`` is the human-editable body.  The loader-appended output
    contract (the JSON action shape) is deliberately *not* overridable: an
    operator may change how a mech thinks, never the wire shape the runner
    parses.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.persona_prompt_override"] = (
        "steel_onslaught.persona_prompt_override"
    )
    persona_id: StrictStr = Field(min_length=1, max_length=96, pattern=_PERSONA_ID_PATTERN)
    doctrine: StrictStr = Field(min_length=1, max_length=8000)
    temperature: StrictFloat | None = Field(default=None, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def _doctrine_is_meaningful(self) -> ModelSOPersonaPromptOverride:
        if not self.doctrine.strip():
            raise ValueError("persona prompt override doctrine must not be blank")
        return self


class ModelSOEffectivePromptProvenance(_ClosedPromptModel):
    """The prompt one persona flew with, identified by an un-forgeable hash.

    ``prompt_sha256`` is the always-present *binding hash* recorded in the
    event ledger; it is what a match records and replay compares.
    ``prompt_text`` is optional and deliberately absent from the browser-facing
    event stream: a raw system prompt must never be broadcast (the
    sanitization gate forbids it), so the runtime/ledger form carries only the
    hash, while an operator inspection surface (``so prompts show --full``, the
    workbench) reads the full text back from the overlay.  When the text *is*
    present it must match the hash, so an inspection projection cannot show a
    prompt that differs from the one the hash binds.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.effective_prompt"] = "steel_onslaught.effective_prompt"
    persona_id: StrictStr = Field(min_length=1, max_length=96, pattern=_PERSONA_ID_PATTERN)
    display_name: StrictStr = Field(min_length=1, max_length=96)
    source: Literal["contract", "operator_override"]
    temperature: StrictFloat = Field(ge=0.0, le=2.0)
    prompt_sha256: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    prompt_text: StrictStr | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def _digest_matches_text(self) -> ModelSOEffectivePromptProvenance:
        if self.prompt_text is not None and prompt_sha256(self.prompt_text) != self.prompt_sha256:
            raise ValueError("effective prompt digest does not match its recorded text")
        return self


class ModelSOMatchPromptProvenance(_ClosedPromptModel):
    """Content-addressed identity of every effective prompt in one match."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.match_prompt_provenance"] = (
        "steel_onslaught.match_prompt_provenance"
    )
    prompts: tuple[ModelSOEffectivePromptProvenance, ...] = ()
    # Digest of the code-owned instruction block appended to a card
    # programming prompt.  It is not operator-editable, but it *is* part of
    # the decision input, so a code change to it is visible in the ledger.
    programming_instructions_sha256: StrictStr = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    content_sha256: StrictStr = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _prompts_are_canonical(self) -> ModelSOMatchPromptProvenance:
        persona_ids = [prompt.persona_id for prompt in self.prompts]
        if len(persona_ids) != len(set(persona_ids)):
            raise ValueError("match prompt provenance must not repeat a persona id")
        if persona_ids != sorted(persona_ids):
            raise ValueError("match prompt provenance must be in ascending persona id order")
        expected = _provenance_digest(self.prompts, self.programming_instructions_sha256)
        if expected != self.content_sha256:
            raise ValueError("match prompt provenance content digest does not match its prompts")
        return self

    def require(self, persona_id: str) -> ModelSOEffectivePromptProvenance:
        """Resolve one recorded effective prompt or fail closed."""

        for prompt in self.prompts:
            if prompt.persona_id == persona_id:
                return prompt
        raise PersonaPromptOverrideError(f"no effective prompt recorded for persona {persona_id!r}")


def _provenance_digest(
    prompts: tuple[ModelSOEffectivePromptProvenance, ...],
    programming_instructions_sha256: str,
) -> str:
    payload = {
        "programming_instructions_sha256": programming_instructions_sha256,
        "prompts": [prompt.model_dump(mode="json") for prompt in prompts],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_prompt_overrides(
    personas: Mapping[str, Persona],
    overrides: Iterable[ModelSOPersonaPromptOverride] = (),
) -> tuple[dict[str, Persona], frozenset[str]]:
    """Return the effective persona mapping and the overridden persona ids.

    An override for an unknown persona id fails closed: silently ignoring it
    would let an operator believe a mech is flying an edited prompt when it is
    not.  The loader-appended output contract is preserved verbatim by
    substituting only the doctrine prefix of the existing system prompt.
    """

    effective = dict(personas)
    overridden: set[str] = set()
    for override in overrides:
        if not isinstance(override, ModelSOPersonaPromptOverride):
            raise PersonaPromptOverrideError(
                "persona prompt overrides must be ModelSOPersonaPromptOverride"
            )
        if override.persona_id in overridden:
            raise PersonaPromptOverrideError(
                f"duplicate persona prompt override for {override.persona_id!r}"
            )
        base = effective.get(override.persona_id)
        if base is None:
            raise PersonaPromptOverrideError(
                f"persona prompt override targets unknown persona {override.persona_id!r}"
            )
        effective[override.persona_id] = Persona(
            persona_id=base.persona_id,
            display_name=base.display_name,
            system_prompt=_substitute_doctrine(base.system_prompt, override.doctrine),
            temperature=base.temperature if override.temperature is None else override.temperature,
        )
        overridden.add(override.persona_id)
    return effective, frozenset(overridden)


def _substitute_doctrine(system_prompt: str, doctrine: str) -> str:
    """Replace the doctrine body while preserving the appended output contract.

    ``load_persona`` builds ``doctrine + _JSON_INSTRUCTION``.  The instruction
    block starts at the first blank-line boundary it introduces, so splitting
    on that exact separator restores it byte-for-byte.  When no separator is
    present (a persona built directly rather than loaded) the whole prompt is
    the doctrine.
    """

    separator = "\n\nRespond with ONLY a JSON object"
    _head, found, tail = system_prompt.partition(separator)
    if not found:
        return doctrine
    return f"{doctrine}{separator}{tail}"


def build_match_prompt_provenance(
    personas: Mapping[str, Persona],
    *,
    overridden_persona_ids: frozenset[str] = frozenset(),
    programming_instructions_sha256: str,
    include_text: bool = True,
) -> ModelSOMatchPromptProvenance:
    """Record every effective prompt in one deterministic, closed projection.

    ``include_text`` is ``False`` for the runtime/ledger form written into
    MATCH_STARTED and broadcast to the browser: only the binding hash travels,
    keeping the sanitization guarantee that raw prompts never leave the server.
    An operator inspection projection passes ``True`` to reconstruct the exact
    text from the overlay.  The two forms have distinct ``content_sha256``
    values, so the runner and its replay-validity check must use the same form
    (both use the redacted one).
    """

    prompts = tuple(
        ModelSOEffectivePromptProvenance(
            persona_id=persona.persona_id,
            display_name=persona.display_name,
            source=(
                "operator_override" if persona.persona_id in overridden_persona_ids else "contract"
            ),
            temperature=float(persona.temperature),
            prompt_sha256=prompt_sha256(persona.system_prompt),
            prompt_text=persona.system_prompt if include_text else None,
        )
        for _persona_id, persona in sorted(personas.items())
    )
    return ModelSOMatchPromptProvenance(
        prompts=prompts,
        programming_instructions_sha256=programming_instructions_sha256,
        content_sha256=_provenance_digest(prompts, programming_instructions_sha256),
    )


__all__ = [
    "ModelSOEffectivePromptProvenance",
    "ModelSOMatchPromptProvenance",
    "ModelSOPersonaPromptOverride",
    "PersonaPromptOverrideError",
    "apply_prompt_overrides",
    "build_match_prompt_provenance",
    "prompt_sha256",
]
