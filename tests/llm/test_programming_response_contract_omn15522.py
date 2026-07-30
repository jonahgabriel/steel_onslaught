"""Fixture-bridge test: ``_PROGRAMMING_RESPONSE_CONTRACT`` vs the real parser.

OMN-15522 (round 4 / AMENDMENT 2): ``_PROGRAMMING_RESPONSE_CONTRACT``
(``steel_onslaught.llm.client_delegation``) is a JSON Schema handed to the
platform's delegation quality gate over the wire. The single authority for
"what shape is accepted" is this repo's own closed Pydantic parsing contract,
``steel_onslaught.llm.programming._ModelSOLlmProgrammingResponse`` -- the
model ``_parse_response`` validates every raw completion against before any
deeper (observation-dependent) semantic check runs.

This module proves the JSON Schema is neither LOOSER nor TIGHTER than that
parser at the STRUCTURAL level, using the exact fixture shapes
``tests/llm/test_llm_programming.py`` already exercises:

* fixtures the parser accepts structurally (``model_validate`` raises
  nothing) must also validate against the schema;
* at least one fixture the parser rejects structurally
  (``extra="forbidden"`` -- the closed model's ``extra="forbid"`` boundary)
  must also fail schema validation (``additionalProperties: false``).

Deliberately OUT of scope here: the deeper semantic checks
``program_for_seat`` performs (free-register coverage, legal-hand
membership, available-copies clamping). Those depend on the runtime
observation (free indices, dealt hand), which a static response-body JSON
Schema cannot express -- exactly the same scoping ``_TACTICAL_RESPONSE_CONTRACT``
's own module docstring states for ``action_params``' inner shape. A
fixture that is structurally valid but semantically rejected by
``program_for_seat`` (missing register, duplicate register_index, unknown
card id, over-copied card) is therefore expected to be ACCEPTED by both the
parser (structurally) and the schema here -- see ``_STRUCTURALLY_VALID_BUT_SEMANTICALLY_REJECTED``.
"""

from __future__ import annotations

import json

import jsonschema  # type: ignore[import-untyped]
import pytest
from pydantic import ValidationError

from steel_onslaught.llm.client_delegation import _PROGRAMMING_RESPONSE_CONTRACT
from steel_onslaught.llm.programming import _ModelSOLlmProgrammingResponse

pytestmark = pytest.mark.unit


def _base_registers() -> list[dict[str, object]]:
    return [
        {"register_index": 0, "card_id": "card.test.advance"},
        {"register_index": 2, "card_id": "card.test.vent"},
    ]


def _base_fixture(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "registers": _base_registers(),
        "confidence": 0.8,
        "rationale": "advance, then vent if heat rises",
    }
    value.update(overrides)
    return value


# --- Fixtures the parser accepts STRUCTURALLY (mirrors the positive-path and
# semantically-rejected-but-structurally-valid cases already exercised in
# tests/llm/test_llm_programming.py) -----------------------------------------

_STRUCTURALLY_VALID_FIXTURES: dict[str, dict[str, object]] = {
    "base": _base_fixture(),
    "dealt_multiplicity": _base_fixture(
        registers=[
            {"register_index": 0, "card_id": "card.test.advance"},
            {"register_index": 1, "card_id": "card.test.advance"},
            {"register_index": 2, "card_id": "card.test.vent"},
        ]
    ),
    "spatial_read_present": _base_fixture(
        confidence=0.9,
        rationale="vent then advance",
        spatial_read="clear line of sight, no cover nearby",
    ),
    # The exact live blue-mirror-seat response from the OMN-15488 attempt-3
    # canary (comment bd30cc1b) -- the response this whole fix exists to
    # let through the wire uncontested.
    "attempt3_canary_response": {
        "registers": [
            {"register_index": 0, "card_id": "card.special.mode_assault"},
            {"register_index": 1, "card_id": "card.attack.fire_primary"},
            {"register_index": 2, "card_id": "card.attack.fire_secondary"},
            {"register_index": 3, "card_id": "card.movement.advance"},
            {"register_index": 4, "card_id": "card.movement.flank_left"},
        ],
        "confidence": 0.95,
        "rationale": (
            "Maximize aggression by switching to assault and firing all "
            "weapons while closing distance."
        ),
    },
    # Structurally valid but semantically rejected by program_for_seat --
    # see the module docstring for why the STATIC schema cannot and must
    # not attempt to catch these (they depend on the runtime observation).
    "single_register_undercount": _base_fixture(
        registers=[{"register_index": 0, "card_id": "card.test.advance"}]
    ),
    "duplicate_register_index": _base_fixture(
        registers=[
            {"register_index": 0, "card_id": "card.test.advance"},
            {"register_index": 0, "card_id": "card.test.vent"},
        ]
    ),
    "unknown_card_id": _base_fixture(
        registers=[
            {"register_index": 0, "card_id": "card.test.unknown"},
            {"register_index": 2, "card_id": "card.test.vent"},
        ]
    ),
    "over_copy": _base_fixture(
        registers=[
            {"register_index": 0, "card_id": "card.test.advance"},
            {"register_index": 2, "card_id": "card.test.advance"},
        ]
    ),
}

# --- Fixtures the parser rejects STRUCTURALLY (the closed model's own
# extra="forbid"/type boundary -- not a semantic/observation-dependent
# rejection) -------------------------------------------------------------

_STRUCTURALLY_INVALID_FIXTURES: dict[str, dict[str, object]] = {
    "extra_field_forbidden": _base_fixture(extra="forbidden"),
    "wrong_type_confidence": _base_fixture(confidence="high"),
    "missing_rationale": {"registers": _base_registers(), "confidence": 0.8},
}


def _parser_accepts(payload: dict[str, object]) -> bool:
    """Mirror the real parsing path (``_parse_response`` calls
    ``model_validate_json(response.text)`` on the raw provider text, never
    ``model_validate`` on an already-Python dict) -- under this model's
    ``strict=True`` config the two are NOT equivalent: ``model_validate``
    on a plain ``dict`` rejects a Python ``list`` for the ``tuple[...]``
    ``registers`` field (strict mode does not coerce list->tuple), while
    ``model_validate_json`` parses the JSON array directly into the tuple
    type without that intermediate check. Serializing through JSON first
    reproduces the actual wire path byte-for-byte."""
    try:
        _ModelSOLlmProgrammingResponse.model_validate_json(json.dumps(payload))
    except ValidationError:
        return False
    return True


def _schema_accepts(payload: dict[str, object]) -> bool:
    try:
        jsonschema.validate(instance=payload, schema=_PROGRAMMING_RESPONSE_CONTRACT)
    except jsonschema.exceptions.ValidationError:
        return False
    return True


@pytest.mark.parametrize("name", sorted(_STRUCTURALLY_VALID_FIXTURES))
def test_parser_accepted_fixture_validates_against_the_wire_schema(name: str) -> None:
    """Every fixture the parser accepts structurally must also validate
    against ``_PROGRAMMING_RESPONSE_CONTRACT`` -- the schema must not be
    TIGHTER than the parser (never rejecting something the parser allows
    through to its own, observation-dependent semantic checks)."""
    payload = _STRUCTURALLY_VALID_FIXTURES[name]

    assert _parser_accepts(payload), (
        f"fixture harness bug: {name!r} is not parser-structurally-valid"
    )
    assert _schema_accepts(payload), (
        f"schema rejected a parser-accepted fixture {name!r} -- "
        "_PROGRAMMING_RESPONSE_CONTRACT is tighter than the parser"
    )


@pytest.mark.parametrize("name", sorted(_STRUCTURALLY_INVALID_FIXTURES))
def test_parser_rejected_fixture_fails_the_wire_schema(name: str) -> None:
    """Every fixture the parser rejects structurally must also fail
    ``_PROGRAMMING_RESPONSE_CONTRACT`` validation -- the schema must not be
    LOOSER than the parser (accepting something the closed Pydantic model's
    own ``extra="forbid"``/type boundary would reject)."""
    payload = _STRUCTURALLY_INVALID_FIXTURES[name]

    assert not _parser_accepts(payload), (
        f"fixture harness bug: {name!r} is parser-structurally-valid"
    )
    assert not _schema_accepts(payload), (
        f"schema accepted a parser-rejected fixture {name!r} -- "
        "_PROGRAMMING_RESPONSE_CONTRACT is looser than the parser"
    )


def test_extra_field_forbidden_fixture_fails_both_the_parser_and_the_schema() -> None:
    """Named regression for the specific case the ticket calls out: at
    least one parser-rejected fixture (the extra-field case, the same
    shape used by ``test_default_failure_policy_exhausts_bounded_retries_on_invalid_plans``
    in ``tests/llm/test_llm_programming.py``) must fail schema validation
    precisely because of ``additionalProperties: false``."""
    payload = _base_fixture(extra="forbidden")

    with pytest.raises(ValidationError):
        _ModelSOLlmProgrammingResponse.model_validate_json(json.dumps(payload))

    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=payload, schema=_PROGRAMMING_RESPONSE_CONTRACT)


def test_not_json_fixture_is_rejected_by_both_seams() -> None:
    """The remaining parametrize-list fixture from
    ``test_llm_programming.py`` ("not json") is not a JSON object at all --
    both the parser (via ``model_validate_json``) and any JSON Schema
    validation over its parsed form must reject it."""
    raw = "not json"

    with pytest.raises(ValidationError):
        _ModelSOLlmProgrammingResponse.model_validate_json(raw)

    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


def test_schema_is_the_closed_registers_confidence_rationale_shape() -> None:
    """Structural sanity pin on the schema's own declared shape -- the
    required/optional split the fixture-bridge tests above hold it to."""
    assert _PROGRAMMING_RESPONSE_CONTRACT["type"] == "object"
    assert _PROGRAMMING_RESPONSE_CONTRACT["required"] == ["registers", "confidence", "rationale"]
    assert _PROGRAMMING_RESPONSE_CONTRACT["additionalProperties"] is False
    properties = _PROGRAMMING_RESPONSE_CONTRACT["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"registers", "confidence", "rationale", "spatial_read"}
