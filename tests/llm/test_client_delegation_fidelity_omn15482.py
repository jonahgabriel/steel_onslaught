"""Differential wire-fidelity proof: HTTP client vs delegation client (OMN-15482).

OMN-15174 batch 1 established that migrating a steel overlay from
``kind: openai_compatible`` to ``kind: onex_delegation`` was NOT
behaviour-preserving, and could therefore migrate exactly one of 57 overlays.
Three measured deltas were the blocker:

1. ``temperature`` was dropped -- ``OpenAICompatibleClient`` forwards it on the
   wire, ``LlmBusDelegationClient`` built a payload that never mentioned it,
   while six pilot specs configure a real value (5 x 0.7, 1 x 0.2).
2. The system/user message split was collapsed -- ``_composed_prompt()``
   concatenated ``system_prompt + "\\n\\n" + user_prompt`` into one flat string
   where the HTTP client sends two distinct chat roles.
3. ``json_mode`` changed representation -- a wire parameter on the HTTP path,
   an appended prompt sentence on the delegation path.

This module is the AC4 deliverable: it drives BOTH real clients with ONE
identical :class:`ModelSOLlmCompletionRequest` and compares the two resulting
wire requests field by field, so "behaviour-preserving" is a tested claim
rather than an assertion in a docstring. Both sides capture at their real wire
boundary -- the ``ModelSOOpenAIChatRequest`` handed to the injected HTTP
transport, and the JSON payload file the delegation client hands to the ``onex``
CLI over ``--input``.

What this test does NOT claim: that the delegation NODE forwards these fields
onward to the provider. That is the omnimarket half of the seam
(``ModelDelegateSkillRequest`` -> ``HandlerDelegateSkill`` ->
``LocalDelegationDispatchPort`` -> outbound chat-completions payload), proven
there by ``omnimarket tests/unit/nodes/node_delegate_skill_orchestrator/
test_wire_completion_fidelity_omn15482.py``, and against the real
``local-coder-mlx`` backend by that repo's opt-in
``test_live_completion_fidelity_omn15482.py``. This file proves steel's own
half: that the two clients emit equivalent requests.

Cross-repo seam note (OMN-14208): the widened wire fields this client now
sends -- ``system_prompt``, ``temperature``, ``response_format`` -- require the
omnimarket-side ``ModelDelegateSkillRequest`` change to be present in whatever
``omnibase_infra`` venv the CLI resolves. ``ModelDelegateSkillRequest`` is
``extra="forbid"``, so against an OLDER omnimarket the delegation call fails
LOUDLY at request validation rather than silently dropping the fields. That is
the intended failure mode, but it does mean the two halves must land together;
the seam is pinned from the consuming side by that repo's
``test_steel_payload_validates_against_the_wire_model``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from steel_onslaught.contracts.application import (
    ModelSODelegationProviderBinding,
    ModelSOLlmRetryBinding,
    ModelSOOpenAICompatibleProviderBinding,
)
from steel_onslaught.llm.client_delegation import LlmBusDelegationClient
from steel_onslaught.llm.client_http import OpenAICompatibleClient
from steel_onslaught.llm.schemas import (
    ModelSOLlmCompletionRequest,
    ModelSOOpenAIChatRequest,
    ModelSOOpenAIChatResponse,
)

pytestmark = pytest.mark.unit

_MODEL = "mlx-community/Qwen3.6-35B-A3B-8bit"
_SYSTEM_PROMPT = "You are a mech pilot. Answer with one tactical decision."
_USER_PROMPT = "Enemy contact at grid 4,7 with heat 62. What do you do?"

_CORRELATION_ID = UUID("11111111-2222-3333-4444-555555555555")


# ---------------------------------------------------------------------------
# One request, driven through both clients
# ---------------------------------------------------------------------------


def _shared_request(
    *, json_mode: bool = True, temperature: float = 0.7
) -> ModelSOLlmCompletionRequest:
    """The single request object BOTH clients receive.

    Constructed once per test and passed to both, so no divergence can be
    smuggled in through subtly different inputs.
    """
    return ModelSOLlmCompletionRequest(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=_USER_PROMPT,
        persona="berserker",
        temperature=temperature,
        json_mode=json_mode,
        evidence_context=None,
    )


# --- HTTP side -------------------------------------------------------------


class _RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[ModelSOOpenAIChatRequest] = []

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        request: ModelSOOpenAIChatRequest,
        timeout_seconds: float,
    ) -> ModelSOOpenAIChatResponse:
        self.requests.append(request)
        return ModelSOOpenAIChatResponse.model_validate(
            {
                "id": "resp-1",
                "choices": (
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    },
                ),
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 5,
                    "total_tokens": 8,
                },
                "model": _MODEL,
            }
        )


class _NoSecrets:
    def resolve(self, reference: Any) -> str:  # pragma: no cover - never called
        raise AssertionError("this binding declares no secret_ref")


class _NoSleep:
    def sleep(self, seconds: float) -> None:  # pragma: no cover - no retries here
        raise AssertionError("no retry should occur in these tests")


def _http_wire_request(
    request: ModelSOLlmCompletionRequest, *, max_tokens: int | None
) -> ModelSOOpenAIChatRequest:
    transport = _RecordingTransport()
    client = OpenAICompatibleClient(
        config=ModelSOOpenAICompatibleProviderBinding(
            kind="openai_compatible",
            provider_id="primary",
            endpoint_url="http://stickybeatz-studio:8401/v1/chat/completions",
            model=_MODEL,
            secret_ref=None,
            timeout_seconds=300.0,
            max_tokens=max_tokens,
            retry=ModelSOLlmRetryBinding(
                max_attempts=1,
                initial_backoff_seconds=0.25,
                backoff_multiplier=2.0,
            ),
        ),
        transport=transport,
        secret_resolver=_NoSecrets(),
        sleeper=_NoSleep(),
    )
    client.complete(request)
    assert len(transport.requests) == 1
    return transport.requests[0]


# --- Delegation side -------------------------------------------------------


def _skill_result_json(correlation_id: str) -> str:
    return json.dumps(
        {
            "status": "success",
            "result": {
                "correlation_id": correlation_id,
                "status": "completed",
                "model_name": _MODEL,
                "response": "{}",
                "metrics": {"input_tokens": 3, "output_tokens": 5},
            },
        }
    )


class _RecordingRunner:
    """Captures the payload file the client hands to the onex CLI."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        self.payloads.append(payload)
        return _skill_result_json(str(payload["correlation_id"]))


def _delegation_wire_payload(
    request: ModelSOLlmCompletionRequest,
    tmp_path: Path,
    *,
    max_tokens: int | None,
) -> dict[str, Any]:
    runner = _RecordingRunner()
    client = LlmBusDelegationClient(
        config=ModelSODelegationProviderBinding.model_validate(
            {
                "kind": "onex_delegation",
                "provider_id": "onex-local-coder-mlx",
                "backend_id": "local-coder-mlx",
                "task_type": "agent_delegation",
                "source": "external-client",
                "model": _MODEL,
                "timeout_seconds": 300.0,
                "max_tokens": max_tokens,
                "omnibase_infra_path": tmp_path / "omnibase_infra",
                "state_root": tmp_path / "state",
            }
        ),
        new_correlation_id=lambda: _CORRELATION_ID,
        runner=runner,
    )
    client.complete(request)
    assert len(runner.payloads) == 1
    return runner.payloads[0]


# ---------------------------------------------------------------------------
# AC4: the differential assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("temperature", [0.0, 0.2, 0.7, 1.0, 2.0])
def test_temperature_is_equivalent_across_both_clients(tmp_path: Path, temperature: float) -> None:
    """AC1 at the wire boundary. Parameterised over the two values pilot specs
    actually configure (0.2, 0.7) plus the range endpoints, so the equality is
    a property of the mapping rather than of one lucky sample."""
    request = _shared_request(temperature=temperature)

    http = _http_wire_request(request, max_tokens=None)
    delegation = _delegation_wire_payload(request, tmp_path, max_tokens=None)

    assert http.temperature == temperature
    assert delegation["temperature"] == temperature
    assert delegation["temperature"] == http.temperature


def test_system_user_role_split_is_equivalent_across_both_clients(
    tmp_path: Path,
) -> None:
    """AC2 at the wire boundary. The HTTP client sends two roles; the delegation
    payload must carry the SAME two strings in two distinct fields, with the
    system text absent from the user field -- the concatenation that previously
    happened would put it there."""
    request = _shared_request()

    http = _http_wire_request(request, max_tokens=None)
    delegation = _delegation_wire_payload(request, tmp_path, max_tokens=None)

    http_system, http_user = http.messages
    assert http_system.role == "system"
    assert http_user.role == "user"

    assert delegation["system_prompt"] == http_system.content
    assert delegation["prompt"] == http_user.content
    # The specific regression: no concatenation, in either direction.
    assert _SYSTEM_PROMPT not in str(delegation["prompt"])
    assert _USER_PROMPT not in str(delegation["system_prompt"])


def test_json_mode_true_is_a_wire_parameter_on_both_clients(tmp_path: Path) -> None:
    """AC3 at the wire boundary: identical ``response_format`` structure, and
    the prompt text is untouched -- no appended JSON instruction sentence."""
    request = _shared_request(json_mode=True)

    http = _http_wire_request(request, max_tokens=None)
    delegation = _delegation_wire_payload(request, tmp_path, max_tokens=None)

    assert http.response_format is not None
    assert http.response_format.type == "json_object"
    assert delegation["response_format"] == {"type": "json_object"}
    assert delegation["response_format"] == http.response_format.model_dump()

    # The deleted fallback must not have come back by another name.
    assert delegation["prompt"] == _USER_PROMPT
    assert "JSON object only" not in str(delegation["prompt"])
    assert "JSON object only" not in str(delegation["system_prompt"])


def test_json_mode_false_omits_response_format_on_both_clients(
    tmp_path: Path,
) -> None:
    """Equivalence in BOTH polarities. The HTTP client leaves the field None
    (dropped by ``exclude_none`` on the wire body); the delegation payload must
    omit the key entirely rather than send an explicit null or a text mode."""
    request = _shared_request(json_mode=False)

    http = _http_wire_request(request, max_tokens=None)
    delegation = _delegation_wire_payload(request, tmp_path, max_tokens=None)

    assert http.response_format is None
    assert "response_format" not in delegation
    assert delegation["prompt"] == _USER_PROMPT


def test_full_differential_over_the_three_migrated_fields(tmp_path: Path) -> None:
    """The single combined assertion the ticket asks for: one identical steel
    request produces an EQUIVALENT wire request through both clients for every
    field in AC1-AC3, compared as one normalized structure rather than three
    separate spot checks that could each pass while the whole diverges."""
    request = _shared_request(json_mode=True, temperature=0.7)

    http = _http_wire_request(request, max_tokens=4096)
    delegation = _delegation_wire_payload(request, tmp_path, max_tokens=4096)

    http_system, http_user = http.messages
    http_normalized = {
        "system": http_system.content,
        "user": http_user.content,
        "temperature": http.temperature,
        "response_format": (
            None if http.response_format is None else http.response_format.model_dump()
        ),
        "max_tokens": http.max_tokens,
    }
    delegation_normalized = {
        "system": delegation["system_prompt"],
        "user": delegation["prompt"],
        "temperature": delegation["temperature"],
        "response_format": delegation.get("response_format"),
        "max_tokens": delegation.get("max_tokens"),
    }

    assert delegation_normalized == http_normalized


def test_image_attachment_still_fails_loud_on_the_delegation_path(
    tmp_path: Path,
) -> None:
    """Explicitly OUT of scope for OMN-15482 and deliberately still unequal:
    the HTTP client builds multi-part content for the four vision overlays, and
    the delegation client raises rather than dropping the image silently. This
    test pins that the gap-closing work above did NOT quietly soften the
    fail-loud boundary into a silent drop."""
    import hashlib

    from steel_onslaught.llm.schemas import ModelSOLlmImageAttachment

    png_bytes = b"\x89PNG\r\n\x1a\n"
    request = ModelSOLlmCompletionRequest(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=_USER_PROMPT,
        persona="berserker",
        temperature=0.7,
        json_mode=True,
        evidence_context=None,
        image_attachment=ModelSOLlmImageAttachment(
            png_bytes=png_bytes,
            sha256_hex=hashlib.sha256(png_bytes).hexdigest(),
        ),
    )

    with pytest.raises(ValueError, match="image_attachment"):
        _delegation_wire_payload(request, tmp_path, max_tokens=None)


def test_payload_key_set_is_pinned_for_the_cross_repo_seam(tmp_path: Path) -> None:
    """OMN-14208 seam pin, measured from the PRODUCING side.

    ``ModelDelegateSkillRequest`` is ``extra="forbid"``, so every key below must
    exist as a field on it. The consuming side asserts the mirror of this exact
    payload (omnimarket
    ``test_steel_payload_validates_against_the_wire_model``); pinning the key
    set here means adding a key on this side fails a steel test immediately
    rather than at runtime inside the onex CLI, in the other repo, days later.
    """
    request = _shared_request(json_mode=True)
    with_json_mode = set(_delegation_wire_payload(request, tmp_path, max_tokens=4096))
    without_json_mode = set(
        _delegation_wire_payload(_shared_request(json_mode=False), tmp_path, max_tokens=None)
    )

    assert with_json_mode == {
        "prompt",
        "system_prompt",
        "temperature",
        "task_type",
        "source",
        "correlation_id",
        "backend_id",
        "response_contract",
        "response_format",
        "max_tokens",
    }
    # The two conditional keys are the only difference between the shapes.
    assert with_json_mode - without_json_mode == {"response_format", "max_tokens"}
    assert without_json_mode - with_json_mode == set()


def test_correlation_id_is_minted_per_request_not_shared(tmp_path: Path) -> None:
    """Guard against the differential fixtures above accidentally pinning a
    constant correlation id into production behaviour: the client mints one per
    call from its injected capability."""
    runner = _RecordingRunner()
    minted: list[UUID] = []

    def _new_id() -> UUID:
        value = uuid4()
        minted.append(value)
        return value

    client = LlmBusDelegationClient(
        config=ModelSODelegationProviderBinding.model_validate(
            {
                "kind": "onex_delegation",
                "provider_id": "onex-local-coder-mlx",
                "backend_id": "local-coder-mlx",
                "task_type": "agent_delegation",
                "source": "external-client",
                "model": _MODEL,
                "timeout_seconds": 300.0,
                "omnibase_infra_path": tmp_path / "omnibase_infra",
                "state_root": tmp_path / "state",
            }
        ),
        new_correlation_id=_new_id,
        runner=runner,
    )
    client.complete(_shared_request())
    client.complete(_shared_request())

    assert len(minted) == 2
    assert minted[0] != minted[1]
    assert [p["correlation_id"] for p in runner.payloads] == [
        str(minted[0]),
        str(minted[1]),
    ]
