"""LLM client routing completions through the ONEX platform delegation chain.

``LlmBusDelegationClient`` implements :class:`~steel_onslaught.llm.schemas.
ProtocolLlmClient` by shelling out to the platform's ``onex`` CLI rather than
speaking HTTP directly to a provider (contrast with
:class:`~steel_onslaught.llm.client_http.OpenAICompatibleClient`). The
completion is dispatched through ``node_delegate_skill_orchestrator`` -- the
platform's def-B CONTRACT+NODE+HANDLER delegation entry point -- instead of a
raw Kafka client, per the steel-node-dispatch integration plan
(``omni_home/docs/plans/2026-07-26-steel-node-dispatch-integration-plan.md``
§2 step 2; the plan explicitly rejects the pre-canon-shape-ratchet raw-Kafka
probe design from ``docs/plans/2026-07-02-kafka-delegation-lane-probe.md``).

Invocation mechanism (load-bearing seam decision, OMN-15157/OMN-15159 PR
body): three options were evaluated in the plan's stated preference order.

1. **Direct import of omnimarket's wire model + dispatch port** -- rejected.
   ``omnimarket`` hard-depends on ``omnibase-infra``, ``aiokafka``,
   ``confluent-kafka``, ``asyncpg``, ``fastapi``, ``uvicorn`` (its
   ``pyproject.toml`` ``dependencies``, not ``optional-dependencies`` --
   importing any one submodule pulls the whole graph). Steel's own
   ``pyproject.toml`` deliberately excludes ``omnibase-infra`` ("Infra is
   intentionally excluded from this engine") and pins only
   ``omnibase-core``/``omnibase-spi``. Adding ``omnimarket`` as a runtime
   dependency would violate that boundary for a personal
   architecture-legibility demo repo.
2. **Subprocess to the platform CLI** -- CHOSEN, with a refinement. The task
   framing suggested ``onex delegate``, but that subcommand hardcodes
   ``source="claude-code"`` (``omnibase_infra/cli/cli_delegate.py``,
   ``DELEGATE_SOURCE`` constant, no ``--source`` flag) -- unusable here,
   since OMN-15158 widened ``ModelDelegateSkillRequest.source`` specifically
   so this client could declare ``"external-client"`` instead of
   misattributing itself as the Claude Code CLI. This client instead shells
   out to the generic ``onex node node_delegate_skill_orchestrator --input
   <payload.json> --output receipt`` entry point
   (``omnibase_infra/cli/cli_node.py``), building the
   ``ModelDelegateSkillRequest``-shaped payload itself so ``source`` can be
   set correctly. stdout is one ``ModelSkillResult[ModelDelegateSkillResponse]``
   JSON (OMN-13094 receipt mode) -- a parseable typed result, per the task's
   own bar for this option.
3. **A minimal mirrored wire DTO** -- explicitly NOT done as a full duplicate
   Pydantic model of ``ModelSkillResult``/``ModelDelegateSkillResponse``
   (that would be the one-canonical-model-per-shape violation option (c)
   warns about). Response parsing instead reads only the specific fields
   this client needs via narrow, fail-loud dict access
   (:func:`_parse_skill_result`) -- no shadow model of the platform's wire
   contract is declared here.

**Formerly discovered gap, closed by OMN-15170:** at the time this client was
built, the ``backend_id`` pin OMN-15156 threaded through
``LocalDelegationDispatchPort.dispatch()`` was NOT reachable from the
consumer-facing ``ModelDelegateSkillRequest`` wire model this client
constructs (no ``backend_id`` field on the model, and
``HandlerDelegateSkill.handle()`` never read one from ``metadata`` either).
OMN-15180 closed that gap on the omnimarket side (wire field +
handler/port/resolver threading, ``routing_tiers.yaml`` local-tier
same-tier-fallback proof). OMN-15170 closed the remaining half on this side:
``complete()`` below now forwards ``config.backend_id`` into the payload --
previously captured on the binding for documentation only and never
actually sent. Live routing determinism to ``local-coder-mlx`` is proven by
OMN-15170's driver test (``tests/live/``), not by this module's own
(hermetic, fake-runner) unit tests.

**Contract-declared response validation (OMN-15193):** ``ModelDelegateSkillRequest``
gained an optional ``response_contract`` field (a JSON Schema) that, when
set, makes the platform's delegation quality gate validate the response
structurally against it instead of running the generic task-class keyword
heuristics. ``complete()`` below always forwards
``_TACTICAL_RESPONSE_CONTRACT`` -- the closed tactical-decision shape derived
from this repo's own ``_ModelSOLlmPilotResponse`` decision-parsing contract
(``steel_onslaught.llm.pilot``) -- since this client has exactly one response
shape and no request variant should fall back to the keyword heuristics
(which previously false-positived on a legitimate ``rationale`` containing
"i cannot" as coherent prose).

**Completion-shaping fidelity, closed by OMN-15482.** Three of the gaps
previously listed here were the reason an overlay could not be migrated from
``kind: openai_compatible`` to ``kind: onex_delegation`` without silently
changing behaviour, and they are now closed end to end. The consumer-facing
wire model gained ``system_prompt``, ``temperature`` and ``response_format``
(OMN-15482, omnimarket side), threaded through ``HandlerDelegateSkill`` ->
``LocalDelegationDispatchPort`` -> ``ModelLlmDelegationCallRequest`` onto the
outbound chat-completions payload. ``complete()`` below therefore forwards:

- ``system_prompt`` as its own wire field, NOT concatenated onto the user
  prompt, so the backend receives two distinct chat roles exactly as
  :class:`~steel_onslaught.llm.client_http.OpenAICompatibleClient` sends them.
- ``temperature`` verbatim. Six pilot specs configure a real value (5 x 0.7,
  1 x 0.2); those were previously discarded, so a migrated overlay silently
  sampled at the delegation default instead.
- ``json_mode`` as the wire parameter ``response_format={"type":
  "json_object"}``. The former appended "respond with a single JSON object
  only" prompt sentence is DELETED, not kept as a fallback -- an alternate
  path that silently changes the prompt text is exactly what made the two
  clients non-equivalent, and leaving it in place would keep the migration
  unprovable.

The differential test ``tests/llm/test_client_delegation_fidelity_omn15482.py``
pins the equivalence for all three fields by driving BOTH clients with one
identical :class:`ModelSOLlmCompletionRequest` and comparing the two wire
requests field by field, so "behaviour-preserving" is a tested claim.

**Cross-repo version requirement (read before deploying this client).**
``ModelDelegateSkillRequest`` is ``extra="forbid"``, so the three fields above
require the OMN-15482 omnimarket change to be present in whichever
``omnibase_infra`` venv :class:`SubprocessDelegationCliRunner` invokes. Against
an OLDER omnimarket the CLI rejects the payload at request validation and this
client raises :class:`LlmTransportError` -- loud and immediate, never a silent
drop, which is the intended failure mode. The two halves must nonetheless land
together; the seam is pinned from both sides (``tests/llm/
test_client_delegation_fidelity_omn15482.py::
test_payload_key_set_is_pinned_for_the_cross_repo_seam`` here, and
``test_steel_payload_validates_against_the_wire_model`` in omnimarket).

**Known, deliberate fidelity gaps that REMAIN open** (the consumer-facing
delegation wire model still has no equivalent field):

- ``persona`` and ``evidence_context`` have no wire counterpart and are not
  forwarded -- but note that ``OpenAICompatibleClient`` does not forward them
  either (verified: neither name appears in ``client_http.py``), so this is
  NOT a differential gap between the two clients and does not affect
  migration equivalence. ``persona`` carries only the persona ID; the
  persona's actual text is ``system_prompt``, which IS forwarded now.
  ``evidence_context`` is match/tick correlation telemetry, not prompt
  content. Carrying either as a first-class wire field would be
  display-salience-arm-specific design work, out of this client's scope
  (ticket 8R, P3).
- ``image_attachment`` is unsupported; a request that sets one raises
  ``ValueError`` immediately rather than silently dropping the image.
  Supporting images end to end is separate, larger work (OMN-15482 explicitly
  scopes it out); the four vision overlays stay on ``openai_compatible``.
- ``ModelSOOpenAIRetryPolicy`` (the per-overlay ``retry`` block every
  ``openai_compatible`` binding declares) has no counterpart on
  ``ModelSODelegationProviderBinding`` -- retries belong to the delegation
  node's own escalation ladder. Whether per-overlay retry config needs an
  equivalent is an open design question, not a fidelity bug.
- The delegation wire response carries no provider-level ``finish_reason``;
  :func:`_parse_skill_result` reports ``"stop"``, the only value implied by a
  domain status of ``completed`` on this surface today.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Protocol, runtime_checkable
from uuid import UUID

from steel_onslaught.contracts.application import ModelSODelegationProviderBinding
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmResponse,
    LlmTransportError,
    LlmUsage,
    ModelSOLlmCompletionRequest,
)

# Additional wall-clock allowance on top of the binding's own
# ``timeout_seconds`` before the subprocess call itself is abandoned -- gives
# the delegation node's own internal timeout (which fires first) the chance
# to return a typed ``status: "timeout"`` result rather than the subprocess
# boundary racing it.
_SUBPROCESS_TIMEOUT_GRACE_SECONDS = 30.0

# OMN-15482: the wire parameter ``json_mode`` maps to, byte-identical to what
# ``OpenAICompatibleClient`` puts on its own wire body via
# ``ModelSOOpenAIResponseFormat(type="json_object")``. This REPLACES the former
# ``_JSON_MODE_INSTRUCTION`` prompt sentence, which is deleted rather than kept
# as a fallback: an alternate path that silently rewrites the prompt is exactly
# what made the two clients non-equivalent.
_JSON_OBJECT_RESPONSE_FORMAT: dict[str, object] = {"type": "json_object"}

# OMN-15170/OMN-15193: the closed tactical-decision response shape this client
# always expects back, declared as a JSON Schema and forwarded verbatim on
# every request via ``ModelDelegateSkillRequest.response_contract`` (landed on
# the omnimarket side by OMN-15193, PR #1908). Derived field-for-field from
# this repo's own decision-parsing contract --
# ``steel_onslaught.llm.pilot._ModelSOLlmPilotResponse`` (the closed,
# ``extra="forbid"``, ``strict=True`` Pydantic boundary the pilot validates
# every LLM response against) -- so the schema never declares anything looser
# than what this client already requires downstream:
#   - ``action``: ``StrictStr`` with ``min_length=1`` -> ``{"type": "string",
#     "minLength": 1}``.
#   - ``action_params``: ``FrozenJSONMapping`` (a JSON object) -> ``{"type":
#     "object"}``; its per-action inner shape is validated separately by
#     ``_parse_response`` against the matched intent-payload model, not by
#     this contract.
#   - ``confidence``: ``StrictFloat`` with ``ge=0.0, le=1.0`` -> ``{"type":
#     "number", "minimum": 0.0, "maximum": 1.0}``.
#   - ``rationale``: ``StrictStr`` with ``min_length=1`` -> ``{"type":
#     "string", "minLength": 1}``.
# ``additionalProperties: false`` mirrors the Pydantic model's
# ``extra="forbid"``: this is a closed shape, not an open one. Declaring this
# schema on the wire makes the platform's delegation quality gate
# (``handler_quality_gate.py``) validate structurally against it instead of
# running its generic task-class keyword heuristics (``sub_tasks_verified``
# substring matching, ``no_refusal`` phrase matching) -- which is what closes
# the false-positive class where a legitimate ``rationale`` containing "i
# cannot" as coherent prose (not a refusal) previously tripped the
# ``no_refusal`` heuristic.
_TACTICAL_RESPONSE_CONTRACT: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "minLength": 1},
        "action_params": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "rationale": {"type": "string", "minLength": 1},
    },
    "required": ["action", "action_params", "confidence", "rationale"],
    "additionalProperties": False,
}


@runtime_checkable
class ProtocolDelegationCliRunner(Protocol):
    """Injectable seam: executes the delegation CLI subprocess.

    Production code uses :class:`SubprocessDelegationCliRunner`. Unit tests
    inject a fake that returns a canned ``ModelSkillResult`` JSON string (or
    raises) without ever spawning a process -- this is the documented seam
    ``LlmBusDelegationClient``'s tests fake instead of exercising the real
    subprocess boundary.
    """

    def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> str:
        """Execute ``argv`` and return raw stdout text, or raise on failure."""
        ...


class SubprocessDelegationCliRunner:
    """Production adapter: ``uv run --project <omnibase_infra> onex node ...``."""

    def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> str:
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise LlmCompletionBoundaryError("timeout", retryable=True) from None
        except OSError as exc:
            raise LlmTransportError(
                f"failed to launch onex delegation CLI: {exc}", retryable=False
            ) from None
        if completed.returncode != 0:
            raise LlmTransportError(
                f"onex delegation CLI exited {completed.returncode}: {completed.stderr[-2000:]}",
                retryable=False,
                # OMN-15240: the message above stays capped at the last 2000
                # chars (unchanged, existing behavior) -- these three fields
                # carry the FULL, unsliced diagnostic context (exact argv,
                # exit code, complete stderr) so a persisted record never
                # loses it to a downstream display-truncation budget.
                argv=argv,
                exit_code=completed.returncode,
                stderr=completed.stderr,
            )
        return completed.stdout


def _reject_unsupported(request: ModelSOLlmCompletionRequest) -> None:
    """Fail loud on the one request shape this client genuinely cannot carry.

    ``image_attachment`` remains out of scope (OMN-15482 scopes it out
    explicitly); raising is correct behaviour, and is deliberately NOT softened
    into a silent drop. Everything else on ``ModelSOLlmCompletionRequest`` that
    ``OpenAICompatibleClient`` puts on the wire is now forwarded -- see the
    module docstring.
    """
    if request.image_attachment is not None:
        raise ValueError(
            "LlmBusDelegationClient does not support image_attachment requests "
            "-- the consumer-facing delegation wire model has no image field"
        )


def _require_str(payload: dict[str, object], key: str, *, where: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise LlmTransportError(
            f"onex delegation CLI result missing/invalid string field {where}.{key!r}: {value!r}",
            retryable=False,
        )
    return value


def _require_dict(payload: dict[str, object], key: str, *, where: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise LlmTransportError(
            f"onex delegation CLI result missing/invalid object field {where}.{key!r}: {value!r}",
            retryable=False,
        )
    return value


def _require_int(payload: dict[str, object], key: str, *, where: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise LlmTransportError(
            f"onex delegation CLI result missing/invalid int field {where}.{key!r}: {value!r}",
            retryable=False,
        )
    return value


def _optional_float(payload: dict[str, object], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LlmTransportError(
            f"onex delegation CLI result field {key!r} is not numeric: {value!r}",
            retryable=False,
        )
    return float(value)


# Envelope-level statuses that mean "the workflow ran and produced a result"
# (``EnumSkillResultStatus.is_success_like``, mirrored here without importing
# the enum -- see the module docstring option (3) rationale: no shadow model,
# but a shadow of a 3-member closed string set kept minimal and local is a
# deliberately narrower, more defensible choice than importing the enum from
# omnibase_core purely to compare three literal strings).
_ENVELOPE_SUCCESS_LIKE = frozenset({"success", "partial", "dry_run"})


def _parse_skill_result(
    stdout: str,
    *,
    expected_model: str,
    expected_correlation_id: UUID,
) -> LlmResponse:
    """Parse the one ``ModelSkillResult[ModelDelegateSkillResponse]`` JSON line.

    Fail-loud on any shape deviation -- a missing/mistyped field is a
    ``LlmTransportError``, never a silently-defaulted value. Only the exact
    fields this client needs are read (see the module docstring's option (3)
    rationale for why this is deliberately not a full mirrored model).
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LlmTransportError(
            f"onex delegation CLI stdout was not valid JSON: {exc}", retryable=False
        ) from None
    if not isinstance(envelope, dict):
        raise LlmTransportError(
            "onex delegation CLI stdout JSON was not an object", retryable=False
        )

    envelope_status = _require_str(envelope, "status", where="envelope")
    if envelope_status not in _ENVELOPE_SUCCESS_LIKE:
        raise LlmTransportError(
            f"onex delegation dispatch did not complete (envelope status={envelope_status!r})",
            retryable=envelope_status == "error",
        )

    result = _require_dict(envelope, "result", where="envelope")
    result_correlation_id = _require_str(result, "correlation_id", where="result")
    if result_correlation_id != str(expected_correlation_id):
        raise LlmTransportError(
            "onex delegation CLI result correlation_id "
            f"{result_correlation_id!r} does not match the minted request "
            f"correlation_id {expected_correlation_id!s}",
            retryable=False,
        )

    domain_status = _require_str(result, "status", where="result")
    if domain_status == "timeout":
        raise LlmCompletionBoundaryError("timeout", retryable=True)
    if domain_status != "completed":
        error_message = result.get("error_message")
        raise LlmTransportError(
            f"delegation domain status={domain_status!r}: "
            f"{error_message if isinstance(error_message, str) else '(no error_message)'}",
            retryable=False,
        )

    served_model = _require_str(result, "model_name", where="result")
    if served_model != expected_model:
        raise LlmTransportError(
            f"delegation served model {served_model!r} does not match the "
            f"configured binding model {expected_model!r}",
            retryable=False,
        )

    response_text = _require_str(result, "response", where="result")
    metrics = _require_dict(result, "metrics", where="result")
    usage = LlmUsage(
        prompt_tokens=_require_int(metrics, "input_tokens", where="result.metrics"),
        completion_tokens=_require_int(metrics, "output_tokens", where="result.metrics"),
        cost_usd=_optional_float(metrics, "cost_usd"),
    )
    return LlmResponse(
        text=response_text,
        usage=usage,
        model=served_model,
        # The delegation wire response carries no provider-level finish_reason
        # (see the module docstring); "stop" is the only value implied by a
        # domain status of "completed" on this surface today.
        finish_reason="stop",
    )


class LlmBusDelegationClient:
    """``ProtocolLlmClient`` routed through the ONEX platform delegation chain.

    See the module docstring for the invocation-mechanism decision, the
    OMN-15180 routing gap, and the deliberate fidelity gaps against
    ``ModelSOLlmCompletionRequest``.
    """

    def __init__(
        self,
        *,
        config: ModelSODelegationProviderBinding,
        new_correlation_id: Callable[[], UUID],
        runner: ProtocolDelegationCliRunner | None = None,
        event_bus: str = "inmemory",
    ) -> None:
        """Construct the client.

        ``config.omnibase_infra_path``/``config.state_root`` are the ONLY
        source of those two paths -- both are explicit overlay data on the
        binding itself (see ``ModelSODelegationProviderBinding``'s
        docstring), never re-derived here.

        ``new_correlation_id`` is an injected capability, never a direct
        ``uuid.uuid4()`` call inside this module: this codebase's
        DI-confinement gate (``tests/test_di_enforcement.py``) confines every
        effectful/nondeterministic construction -- including UUID minting --
        to ``match/composition.py``. The composition root passes
        ``SystemIdentityProvider().new_correlation_id`` (the same identity
        capability already used for event correlation ids elsewhere in the
        match pipeline); tests inject a deterministic fake.

        ``event_bus`` pins the delegation dispatch to the in-memory backend
        by default -- this client does not attempt to route through a live
        Kafka broker. Bus-forwarding steel's own match/battery lifecycle
        events onto Kafka is a SEPARATE, unrelated mechanism (plan §3 P2,
        the ``kafka_forwarder`` subscriber) from how the delegation NODE
        itself dispatches internally; conflating the two would entangle this
        P0 ticket with P2's bus-reachability concerns. Pass
        ``event_bus="kafka"`` explicitly only once a caller has verified
        Kafka reachability for its own use case.
        """
        self._config = config
        self._new_correlation_id = new_correlation_id
        self._runner = runner if runner is not None else SubprocessDelegationCliRunner()
        self._event_bus = event_bus

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        _reject_unsupported(request)
        correlation_id = self._new_correlation_id()
        payload: dict[str, object] = {
            # OMN-15482: the USER prompt only. The system prompt travels in its
            # own wire field below, so the backend receives two distinct chat
            # roles -- previously these were concatenated into one flat string,
            # which is the fidelity gap that made an overlay migration off
            # OpenAICompatibleClient non-behaviour-preserving.
            "prompt": request.user_prompt,
            "system_prompt": request.system_prompt,
            # OMN-15482: forwarded verbatim. Six pilot specs configure a real
            # temperature (5 x 0.7, 1 x 0.2) that this client previously
            # discarded entirely.
            "temperature": request.temperature,
            "task_type": self._config.task_type,
            "source": self._config.source,
            "correlation_id": str(correlation_id),
            # OMN-15170: OMN-15180 landed the wire-path this binding's
            # docstring named as a precondition (ModelDelegateSkillRequest
            # gained a `backend_id` field, threaded through
            # HandlerDelegateSkill.handle() -> dispatch_port.dispatch() ->
            # resolve_delegation_backend(task_type, backend_id=...) on the
            # bus-less LocalDelegationDispatchPort). `backend_id` is a
            # required (non-empty) field on ModelSODelegationProviderBinding,
            # so it is always forwarded -- this closes the gap the binding's
            # docstring documented ("declaring the intended backend_id here
            # ... leaves the field ready the moment the wire path opens").
            "backend_id": self._config.backend_id,
            # OMN-15193: always declare the closed tactical-decision response
            # schema (see ``_TACTICAL_RESPONSE_CONTRACT`` above) so the
            # platform's delegation quality gate validates structurally
            # against it instead of the generic task-class keyword
            # heuristics. Unconditional -- this client has exactly one
            # response shape (the pilot's tactical decision), so there is no
            # request variant that should omit it.
            "response_contract": _TACTICAL_RESPONSE_CONTRACT,
        }
        # OMN-15482: json_mode as a WIRE PARAMETER, matching
        # ``OpenAICompatibleClient``'s ``response_format`` field exactly. The
        # key is omitted entirely when json_mode is False, mirroring that
        # client's ``exclude_none`` wire body -- so the two are equivalent in
        # both polarities, not just the True case.
        if request.json_mode:
            payload["response_format"] = dict(_JSON_OBJECT_RESPONSE_FORMAT)
        if self._config.max_tokens is not None:
            payload["max_tokens"] = self._config.max_tokens

        tmp_dir = self._config.state_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        payload_path = tmp_dir / f"delegate-input-{correlation_id}.json"
        payload_path.write_text(json.dumps(payload), encoding="utf-8")

        argv = (
            "uv",
            "run",
            "--project",
            str(self._config.omnibase_infra_path),
            "onex",
            "node",
            "node_delegate_skill_orchestrator",
            "--input",
            str(payload_path),
            "--output",
            "receipt",
            "--state-root",
            str(self._config.state_root),
            "--timeout",
            str(int(self._config.timeout_seconds)),
            "--backend",
            f"event_bus={self._event_bus}",
        )
        stdout = self._runner.run(
            argv,
            timeout_seconds=self._config.timeout_seconds + _SUBPROCESS_TIMEOUT_GRACE_SECONDS,
        )
        return _parse_skill_result(
            stdout,
            expected_model=self._config.model,
            expected_correlation_id=correlation_id,
        )


__all__ = [
    "LlmBusDelegationClient",
    "ProtocolDelegationCliRunner",
    "SubprocessDelegationCliRunner",
]
