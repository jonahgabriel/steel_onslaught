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

from steel_onslaught.llm import client_delegation
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


# --- Residual sweep: the two latent divergences the PR #239 post-merge
# verifier recorded on OMN-15522 (comment ``43af2956``) --------------------
#
# The fixture-bridge tests above are scoped, by their own docstring, to the
# structural fixture shapes ``tests/llm/test_llm_programming.py`` already
# exercises. Two divergence classes escape that scope entirely because no
# fixture in those sets carries an explicit JSON ``null`` or a non-integral
# JSON number:
#
# 1. ``spatial_read: null`` -- schema TIGHTER than parser. The dangerous
#    direction: a value the parser accepts that the wire schema rejects is
#    a ``SCHEMA_VIOLATION`` at the platform's delegation quality gate, i.e.
#    the exact abort class OMN-15522 exists to close. Latent only because
#    no shipped ``onex_delegation`` overlay sets ``spatial_representation``
#    today (so ``spatial_read_required`` is always False); an R2 /
#    ``grid_scaffold`` seat migrating to the delegation transport makes it
#    live.
# 2. ``register_index: 1.0`` -- schema LOOSER than parser. Benign
#    direction (steel's own parser + bounded reprompt absorb it, which is
#    the pre-OMN-15522 behavior), but it falsifies the "never looser"
#    claim the constant's own comment block made, and JSON Schema has no
#    keyword that can express it away. It is therefore DECLARED in source
#    rather than silently tolerated -- see
#    ``client_delegation._PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES``.
#
# ``_EDGE_FIXTURES`` below is the mechanism, not the two named regressions:
# it sweeps every field of the contract against null / wrong-type /
# boundary / non-integral-number inputs and asserts the ONLY parser-vs-
# schema disagreements are the ones source explicitly declares. Adding a
# new divergence (by editing either the schema or the parser) fails this
# test until someone names it in the source constant.


def _register(**overrides: object) -> dict[str, object]:
    return _base_fixture(
        registers=[{"register_index": 0, "card_id": "card.test.advance", **overrides}]
    )


_EDGE_FIXTURES: dict[str, dict[str, object]] = {
    # spatial_read (optional R2 scaffold field)
    "spatial_read_explicit_null": _base_fixture(spatial_read=None),
    "spatial_read_empty_string": _base_fixture(spatial_read=""),
    "spatial_read_wrong_type": _base_fixture(spatial_read=123),
    # registers[].register_index
    "register_index_integral_float": _register(register_index=1.0),
    "register_index_fractional_float": _register(register_index=1.5),
    "register_index_bool": _register(register_index=True),
    "register_index_negative": _register(register_index=-1),
    "register_index_string": _register(register_index="0"),
    "register_index_null": _register(register_index=None),
    # registers[].card_id
    "card_id_empty_string": _register(card_id=""),
    "card_id_null": _register(card_id=None),
    # registers[] closedness
    "register_extra_field": _register(weight=1),
    # confidence
    "confidence_integer": _base_fixture(confidence=1),
    "confidence_bool": _base_fixture(confidence=True),
    "confidence_string": _base_fixture(confidence="0.8"),
    "confidence_above_range": _base_fixture(confidence=1.5),
    "confidence_null": _base_fixture(confidence=None),
    # rationale
    "rationale_empty_string": _base_fixture(rationale=""),
    "rationale_null": _base_fixture(rationale=None),
    # registers container
    "registers_empty_array": _base_fixture(registers=[]),
    "registers_null": _base_fixture(registers=None),
    "registers_object": _base_fixture(
        registers={"register_index": 0, "card_id": "card.test.advance"}
    ),
}


def test_edge_matrix_has_no_undeclared_parser_schema_divergence() -> None:
    """Sweep every contract field for null / wrong-type / boundary /
    non-integral-number inputs and assert the parser and the wire schema
    agree everywhere EXCEPT the divergences source explicitly declares.

    This is the standing mechanism for both OMN-15522 residuals: a future
    edit to either ``_PROGRAMMING_RESPONSE_CONTRACT`` or
    ``_ModelSOLlmProgrammingResponse`` that opens a new gap fails here
    until it is named in
    ``client_delegation._PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES``.
    """
    # Read the allowlist off the source module (not a test-local copy) so
    # the declaration lives with the schema it qualifies.
    declared = sorted(client_delegation._PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES)

    observed = sorted(
        name
        for name, payload in _EDGE_FIXTURES.items()
        if _parser_accepts(payload) != _schema_accepts(payload)
    )

    assert observed == declared, (
        "parser-vs-wire-schema divergence set changed: observed "
        f"{observed!r}, source declares {declared!r}. A divergence in the "
        "schema-TIGHTER-than-parser direction is a SCHEMA_VIOLATION abort "
        "source at the platform quality gate and must be FIXED, not "
        "declared."
    )


def test_explicit_null_spatial_read_is_accepted_by_both_seams() -> None:
    """OMN-15522 residual 1 (RED before the fix).

    ``_ModelSOLlmProgrammingResponse.spatial_read`` is ``StrictStr | None``,
    and ``programming.py`` deliberately logs-never-raises when a
    ``grid_scaffold`` seat omits it -- "a scaffold field must never become
    a new abort source". A model that answers the R2 scaffold prompt with
    an explicit ``"spatial_read": null`` must therefore survive the wire
    schema too; before the fix the schema declared a bare
    ``{"type": "string", "minLength": 1}`` and rejected it, which the
    platform gate reports as ``SCHEMA_VIOLATION`` through all 3 retries.
    """
    payload = _base_fixture(spatial_read=None)

    assert _parser_accepts(payload), "parser must accept an explicit null spatial_read"
    assert _schema_accepts(payload), (
        "wire schema rejected an explicit null spatial_read the parser "
        "accepts -- schema is TIGHTER than the parser, which is a live "
        "SCHEMA_VIOLATION abort source for an R2/grid_scaffold seat"
    )


def test_spatial_read_schema_still_rejects_empty_and_wrong_typed_values() -> None:
    """The residual-1 fix widens ``spatial_read`` to accept null ONLY --
    an empty string (parser: ``min_length=1``) and a non-string, non-null
    value must still be rejected by both seams."""
    for payload in (_base_fixture(spatial_read=""), _base_fixture(spatial_read=123)):
        assert not _parser_accepts(payload)
        assert not _schema_accepts(payload)


def test_known_divergence_register_index_integral_float_is_declared_in_source() -> None:
    """OMN-15522 residual 2 (RED before the fix).

    JSON Schema's ``"type": "integer"`` matches any number with a zero
    fractional part, so ``register_index: 1.0`` validates on the wire while
    the parser's ``StrictInt`` rejects it. ``multipleOf: 1`` does NOT close
    this (``1.0 % 1 == 0``), and no other keyword expresses "integer token,
    not integral float" -- so the looseness is unfixable on the wire and is
    DECLARED in source instead of being contradicted by a "never looser"
    docstring claim.
    """
    payload = _register(register_index=1.0)

    assert not _parser_accepts(payload), "parser StrictInt must reject 1.0"
    assert _schema_accepts(payload), (
        "wire schema unexpectedly rejects register_index 1.0 -- if this "
        "became fixable, drop it from _PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES"
    )
    assert (
        "register_index_integral_float" in client_delegation._PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES
    )


def test_declared_divergences_are_real_and_named_after_edge_fixtures() -> None:
    """Guard the declaration itself: every name in the source constant must
    correspond to a real ``_EDGE_FIXTURES`` case that actually diverges, so
    the allowlist cannot rot into a blanket suppression."""
    for name in client_delegation._PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES:
        assert name in _EDGE_FIXTURES, f"declared divergence {name!r} has no edge fixture"
        payload = _EDGE_FIXTURES[name]
        assert _parser_accepts(payload) != _schema_accepts(payload), (
            f"declared divergence {name!r} no longer diverges -- remove it "
            "from _PROGRAMMING_CONTRACT_KNOWN_DIVERGENCES"
        )


def test_contracts_are_valid_schemas_under_the_gate_s_own_validator_resolution() -> None:
    """Seam check against the CONSUMER's actual validation path.

    ``handler_quality_gate._schema_violation_reasons`` (omnimarket,
    ``node_delegation_quality_gate_reducer``) does not use
    ``jsonschema.validate``: it resolves ``jsonschema.validators.
    validator_for(response_contract)`` (latest supported draft when the
    contract declares no ``$schema`` -- neither of ours does), calls
    ``validator_cls.check_schema(...)``, and iterates errors. Its own
    docstring states that an invalid caller-authored schema raises
    ``SchemaError`` and "must surface loudly" -- i.e. a malformed contract
    is a hard failure on the platform side, not a silent pass.

    Residual 1's fix introduces the first ``anyOf`` in either contract, so
    this pins that (a) both contracts still ``check_schema`` clean under
    the validator class the gate itself would pick, and (b) the null
    ``spatial_read`` case produces ZERO errors through that exact
    ``iter_errors`` path -- not merely through this module's
    ``jsonschema.validate`` helper.
    """
    for contract in (
        client_delegation._TACTICAL_RESPONSE_CONTRACT,
        _PROGRAMMING_RESPONSE_CONTRACT,
    ):
        validator_cls = jsonschema.validators.validator_for(contract)
        validator_cls.check_schema(contract)

    validator_cls = jsonschema.validators.validator_for(_PROGRAMMING_RESPONSE_CONTRACT)
    validator = validator_cls(_PROGRAMMING_RESPONSE_CONTRACT)

    assert list(validator.iter_errors(_base_fixture(spatial_read=None))) == []
    assert list(validator.iter_errors(_base_fixture(spatial_read="clear sightline"))) == []
    assert list(validator.iter_errors(_base_fixture())) == []
    assert list(validator.iter_errors(_base_fixture(spatial_read=""))) != []
