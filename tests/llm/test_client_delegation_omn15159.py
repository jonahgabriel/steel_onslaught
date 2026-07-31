"""Hermetic tests for ``LlmBusDelegationClient`` (OMN-15159).

The documented seam this client's tests fake is ``ProtocolDelegationCliRunner``
-- no subprocess is ever spawned. The real subprocess boundary
(:class:`~steel_onslaught.llm.client_delegation.SubprocessDelegationCliRunner`)
is exercised only by OMN-15170's live driver test against a real onex CLI
call, per the task's explicit scope: this file proves the client's argv
construction, payload shape, and response parsing/validation logic, not a
live delegation routing outcome.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from steel_onslaught.contracts.application import ModelSODelegationProviderBinding
from steel_onslaught.llm.client_delegation import (
    _PROGRAMMING_RESPONSE_CONTRACT,
    _TACTICAL_RESPONSE_CONTRACT,
    LlmBusDelegationClient,
    ProtocolDelegationCliRunner,
    SubprocessDelegationCliRunner,
)
from steel_onslaught.llm.effect import LlmSemanticError
from steel_onslaught.llm.schemas import (
    LlmCompletionBoundaryError,
    LlmTransportError,
    ModelSOLlmCompletionRequest,
    ModelSOLlmImageAttachment,
)

pytestmark = pytest.mark.unit


def _config(tmp_path: Path, **overrides: object) -> ModelSODelegationProviderBinding:
    raw: dict[str, object] = {
        "kind": "onex_delegation",
        "provider_id": "onex-local-coder-mlx",
        "backend_id": "local-coder-mlx",
        "task_type": "agent_delegation",
        "source": "external-client",
        "model": "mlx-community/Qwen3.6-35B-A3B-8bit",
        "timeout_seconds": 300.0,
        "omnibase_infra_path": tmp_path / "omnibase_infra",
        "state_root": tmp_path / "state",
    }
    raw.update(overrides)
    return ModelSODelegationProviderBinding.model_validate(raw)


def _request(
    *,
    json_mode: bool = True,
    image: bool = False,
    wants_tactical_response_contract: bool = True,
) -> ModelSOLlmCompletionRequest:
    return ModelSOLlmCompletionRequest(
        system_prompt="you are a mech pilot",
        user_prompt="what do you do",
        persona="berserker",
        temperature=0.4,
        json_mode=json_mode,
        evidence_context=None,
        image_attachment=(
            ModelSOLlmImageAttachment(png_bytes=b"\x89PNG", sha256_hex="0" * 64) if image else None
        ),
        wants_tactical_response_contract=wants_tactical_response_contract,
    )


def _skill_result_json(
    *,
    correlation_id: str,
    envelope_status: str = "success",
    domain_status: str = "completed",
    model_name: str = "mlx-community/Qwen3.6-35B-A3B-8bit",
    response_text: str = '{"action": "remain"}',
    error_message: str = "",
    input_tokens: int = 12,
    output_tokens: int = 34,
    cost_usd: float | None = 0.0,
) -> str:
    metrics: dict[str, object] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if cost_usd is not None:
        metrics["cost_usd"] = cost_usd
    return json.dumps(
        {
            "skill_name": "delegate",
            "node_name": "node_delegate_skill_orchestrator",
            "status": envelope_status,
            "correlation_id": correlation_id,
            "run_id": correlation_id,
            "exit_code": 0,
            "duration_ms": 500,
            "result": {
                "status": domain_status,
                "correlation_id": correlation_id,
                "task_type": "agent_delegation",
                "provider": "http://stickybeatz-studio:8401/v1/chat/completions",
                "model_name": model_name,
                "response": response_text,
                "error_message": error_message,
                "metrics": metrics,
            },
            "result_model": "omnimarket.models.delegation.wire.model_delegate_skill_response."
            "ModelDelegateSkillResponse",
        }
    )


class _RecordingRunner:
    """Fake ``ProtocolDelegationCliRunner`` that records argv and returns canned stdout."""

    def __init__(self, stdout_factory: object) -> None:
        self._stdout_factory = stdout_factory
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> str:
        self.calls.append((argv, timeout_seconds))
        if callable(self._stdout_factory):
            return self._stdout_factory(argv)  # type: ignore[no-any-return]
        return self._stdout_factory  # type: ignore[return-value]


def _client(
    *,
    runner: ProtocolDelegationCliRunner,
    config: ModelSODelegationProviderBinding | None = None,
    tmp_path: Path,
    new_correlation_id: Callable[[], UUID] = uuid4,
) -> LlmBusDelegationClient:
    return LlmBusDelegationClient(
        config=config or _config(tmp_path),
        new_correlation_id=new_correlation_id,
        runner=runner,
    )


def test_satisfies_protocol_llm_client_shape(tmp_path: Path) -> None:
    from steel_onslaught.llm.schemas import ProtocolLlmClient

    assert isinstance(_client(runner=_RecordingRunner(""), tmp_path=tmp_path), ProtocolLlmClient)


def test_argv_targets_the_generic_onex_node_entrypoint_not_the_delegate_subcommand(
    tmp_path: Path,
) -> None:
    """The client must NOT use ``onex delegate`` (hardcodes source=claude-code)."""
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(correlation_id=_correlation_from_argv(argv))
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    client.complete(_request())

    assert len(runner.calls) == 1
    argv, timeout_seconds = runner.calls[0]
    assert argv[:2] == ("uv", "run")
    assert "--project" in argv
    assert str(tmp_path / "omnibase_infra") in argv
    assert "node" in argv
    assert "node_delegate_skill_orchestrator" in argv
    assert "delegate" not in argv  # never the source-hardcoding subcommand wrapper
    assert "--output" in argv
    assert argv[argv.index("--output") + 1] == "receipt"
    assert "--backend" in argv
    assert argv[argv.index("--backend") + 1] == "event_bus=inmemory"
    assert timeout_seconds > 300.0  # grace window added on top of timeout_seconds


def _correlation_from_argv(argv: tuple[str, ...]) -> str:
    input_path = Path(argv[argv.index("--input") + 1])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return str(payload["correlation_id"])


def test_payload_carries_source_external_client_and_configured_task_type(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request())

    assert captured["source"] == "external-client"
    assert captured["task_type"] == "agent_delegation"
    # A fresh correlation_id is minted per call and is a real UUID.
    UUID(str(captured["correlation_id"]))


def test_payload_forwards_configured_backend_id_omn15170(tmp_path: Path) -> None:
    """OMN-15170: ``backend_id`` must reach the wire payload verbatim.

    Regression for the gap this client's own module docstring previously
    documented as deferred: ``ModelSODelegationProviderBinding.backend_id``
    was captured for "documentation/provenance" only and never forwarded --
    OMN-15180 landed the wire-model + handler support this needed, and this
    client must actually use it or the pin is dead on arrival despite being
    reachable end-to-end.
    """
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request())

    assert captured["backend_id"] == "local-coder-mlx"


def test_payload_declares_the_tactical_response_contract_schema_omn15193(
    tmp_path: Path,
) -> None:
    """OMN-15193: the client always declares its closed tactical-decision
    response schema on the wire via ``response_contract``, so the platform's
    delegation quality gate validates structurally instead of running the
    task-class keyword heuristics (which false-positived on a legitimate
    ``rationale`` substring like "i cannot").

    The declared schema must be present, exact, and derived from -- never
    looser than -- this repo's own decision-parsing contract
    (``steel_onslaught.llm.pilot._ModelSOLlmPilotResponse``): ``action`` and
    ``rationale`` are non-empty strings, ``action_params`` is a JSON object,
    ``confidence`` is a number bounded to ``[0.0, 1.0]``, all four fields are
    required, and no additional properties are allowed (mirroring the
    Pydantic model's ``extra="forbid"``).
    """
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request())

    assert "response_contract" in captured
    assert captured["response_contract"] == _TACTICAL_RESPONSE_CONTRACT
    assert captured["response_contract"] == {
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


def test_decide_path_default_still_carries_the_tactical_response_contract_byte_identical(
    tmp_path: Path,
) -> None:
    """OMN-15522 companion: the plain decide() path (default request, no
    caller opt-out) forwards the exact same ``response_contract`` value as
    before this fix -- the display-salience arm's proven delegation
    configuration must be provably unchanged.
    """
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    # No wants_tactical_response_contract override -- exercises the default,
    # exactly as LLMPilot._build_request constructs its request.
    client.complete(_request(wants_tactical_response_contract=True))

    assert captured["response_contract"] == _TACTICAL_RESPONSE_CONTRACT


def test_programming_path_completion_carries_the_programming_response_contract_omn15522(
    tmp_path: Path,
) -> None:
    """OMN-15522 round 4 RED-FIRST regression (AMENDMENT 2).

    Card-mode programming completions (``LLMProgrammingPilot``) opt out of
    the tactical-decision contract via
    ``wants_tactical_response_contract=False`` -- their response is a
    whole-round register plan, not a single tactical decision, and
    forwarding the tactical schema made the platform's delegation quality
    gate reject a correct programming response as ``SCHEMA_VIOLATION``
    (OMN-15482 comment 14468f08, OMN-15488 canary). Round 3 fixed this by
    OMITTING the wire contract on this path; the OMN-15488 attempt-3 canary
    (comment bd30cc1b) proved that was insufficient live -- with no
    caller-supplied contract, the platform validates against its own
    DEFAULT schema set, which also rejects the registers shape. This
    assertion must therefore FAIL against the round-3 client (which omits
    ``response_contract`` on this path) and PASS only once the client sends
    ``_PROGRAMMING_RESPONSE_CONTRACT`` instead.
    """
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request(wants_tactical_response_contract=False))

    assert "response_contract" in captured, (
        "programming-path completion must carry a wire-level response "
        "contract -- omitting one leaves the platform to validate against "
        "its own default schema set, which rejects the registers shape "
        "(OMN-15488 attempt-3 canary)"
    )
    assert captured["response_contract"] == _PROGRAMMING_RESPONSE_CONTRACT
    assert captured["response_contract"] != _TACTICAL_RESPONSE_CONTRACT


def test_payload_composes_system_and_user_prompt_with_json_mode_instruction(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request(json_mode=True))

    prompt = str(captured["prompt"])
    assert "you are a mech pilot" in prompt
    assert "what do you do" in prompt
    assert "JSON object only" in prompt


def test_json_mode_false_omits_the_json_instruction(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request(json_mode=False))

    assert "JSON object only" not in str(captured["prompt"])


def test_max_tokens_included_only_when_configured(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(
        runner=_RecordingRunner(_stdout),
        config=_config(tmp_path, max_tokens=2048),
        tmp_path=tmp_path,
    )
    client.complete(_request())
    assert captured["max_tokens"] == 2048

    captured.clear()
    client_no_max = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client_no_max.complete(_request())
    assert "max_tokens" not in captured


def test_image_attachment_request_raises_immediately_without_a_subprocess_call(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner("")
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(ValueError, match="image_attachment"):
        client.complete(_request(image=True))

    assert runner.calls == []


def test_successful_completion_parses_text_usage_model_and_finish_reason(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(
            correlation_id=_correlation_from_argv(argv),
            response_text='{"action": "fire_weapon"}',
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0025,
        )
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    response = client.complete(_request())

    assert response.text == '{"action": "fire_weapon"}'
    assert response.model == "mlx-community/Qwen3.6-35B-A3B-8bit"
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 100
    assert response.usage.completion_tokens == 50
    assert response.usage.cost_usd == 0.0025


def test_cost_usd_absent_from_metrics_maps_to_none(tmp_path: Path) -> None:
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(correlation_id=_correlation_from_argv(argv), cost_usd=None)
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    response = client.complete(_request())
    assert response.usage.cost_usd is None


def test_envelope_status_not_success_like_raises_transport_error(tmp_path: Path) -> None:
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(
            correlation_id=_correlation_from_argv(argv), envelope_status="error"
        )
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmTransportError, match="envelope status"):
        client.complete(_request())


def test_domain_status_timeout_raises_completion_boundary_error(tmp_path: Path) -> None:
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(
            correlation_id=_correlation_from_argv(argv), domain_status="timeout"
        )
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmCompletionBoundaryError) as exc_info:
        client.complete(_request())
    assert exc_info.value.reason_code == "timeout"


def test_domain_status_failed_raises_transport_error_with_error_message(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(
            correlation_id=_correlation_from_argv(argv),
            domain_status="failed",
            error_message="no healthy backend",
        )
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmTransportError, match="no healthy backend"):
        client.complete(_request())


def test_mismatched_correlation_id_raises_transport_error(tmp_path: Path) -> None:
    """Defense-in-depth: a stale/foreign result must never be silently accepted."""
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(correlation_id="00000000-0000-0000-0000-000000000000")
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmTransportError, match="correlation_id"):
        client.complete(_request())


def test_mismatched_served_model_raises_transport_error(tmp_path: Path) -> None:
    """Plan §4a: the served model must match the configured binding verbatim."""
    runner = _RecordingRunner(
        lambda argv: _skill_result_json(
            correlation_id=_correlation_from_argv(argv),
            model_name="some-other-model",
        )
    )
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmTransportError, match="does not match"):
        client.complete(_request())


def test_malformed_json_stdout_raises_transport_error(tmp_path: Path) -> None:
    runner = _RecordingRunner("not json at all")
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmTransportError, match="not valid JSON"):
        client.complete(_request())


def test_missing_result_field_raises_transport_error(tmp_path: Path) -> None:
    runner = _RecordingRunner(json.dumps({"status": "success"}))
    client = _client(runner=runner, tmp_path=tmp_path)

    with pytest.raises(LlmTransportError, match=re.escape("envelope.'result'")):
        client.complete(_request())


def test_missing_metrics_field_raises_transport_error(tmp_path: Path) -> None:
    def _stdout(argv: tuple[str, ...]) -> str:
        correlation_id = _correlation_from_argv(argv)
        return json.dumps(
            {
                "status": "success",
                "result": {
                    "status": "completed",
                    "correlation_id": correlation_id,
                    "model_name": "mlx-community/Qwen3.6-35B-A3B-8bit",
                    "response": "ok",
                },
            }
        )

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    with pytest.raises(LlmTransportError, match=re.escape("result.'metrics'")):
        client.complete(_request())


def test_payload_written_under_the_caller_supplied_state_root(tmp_path: Path) -> None:
    """The client never hardcodes a scratch location -- it honors the
    injected ``state_root`` (mirrors the platform's own onex delegate
    ``_write_payload`` convention: ``<state_root>/tmp/``), so the caller
    (``build_llm_dependencies``) fully controls where scratch payloads land.
    """
    captured_paths: list[Path] = []

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured_paths.append(input_path)
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        return _skill_result_json(correlation_id=str(payload["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request())

    assert len(captured_paths) == 1
    assert captured_paths[0].is_relative_to(tmp_path / "state")


# --- OMN-15240: SubprocessDelegationCliRunner -- full stderr/exit_code/argv ---
#
# Unlike every other test in this module (which fakes ProtocolDelegationCliRunner
# so no subprocess is ever spawned -- see the module docstring), these tests
# exercise the REAL subprocess boundary (SubprocessDelegationCliRunner) with a
# throwaway ``python3 -c`` child process. This is the exact seam that masked
# the OMN-15240 acceptance-battery failures: a benign ~190-char uv
# VIRTUAL_ENV warning at the FRONT of stderr ate a downstream 240-char
# console-truncation budget, hiding the real error that followed it. The
# fix is verified here at the layer that must never lose the tail: the
# raised LlmTransportError's own attributes, not the truncated message text.


def _python_argv(script: str) -> tuple[str, ...]:
    return (sys.executable, "-c", script)


def test_nonzero_exit_attaches_full_argv_exit_code_and_stderr() -> None:
    """A non-zero CLI exit must attach the exact argv, exit code, and the
    COMPLETE (unsliced) stderr onto the raised LlmTransportError -- not just
    bake a truncated preview into the message string. This is what lets a
    caller (e.g. a battery driver's skip record) persist the full diagnostic
    text regardless of its own display-layer truncation.
    """
    tail_marker = "REAL_ERROR_TAIL_MARKER_qqzz9182"
    # A long benign preamble (mimics the uv VIRTUAL_ENV warning that, in
    # production, sits at the very front of stderr) followed by the real
    # error at the tail -- long enough in total that a naive head-truncation
    # (e.g. [:240]) would never reach the marker.
    script = (
        "import sys\n"
        f"sys.stderr.write('warning: ' + ('x' * 300) + '\\n')\n"
        f"sys.stderr.write('filler ' * 50 + '\\n')\n"
        f"sys.stderr.write('Error: {tail_marker}\\n')\n"
        "sys.exit(1)\n"
    )
    argv = _python_argv(script)
    runner = SubprocessDelegationCliRunner()

    with pytest.raises(LlmTransportError) as excinfo:
        runner.run(argv, timeout_seconds=30.0)

    exc = excinfo.value
    assert exc.exit_code == 1
    assert exc.argv == argv
    assert exc.stderr is not None
    assert tail_marker in exc.stderr
    # The truncated console-style preview a caller might derive from this
    # exception must NOT reliably contain the tail marker -- proving the
    # marker's survival depends on reading the structured `.stderr` field,
    # not the flattened message string sliced to a short preview.
    preview = " ".join(f"{type(exc).__name__}: {exc}".split())[:240]
    assert tail_marker not in preview


def test_zero_exit_returns_stdout_without_raising() -> None:
    """Control case: a clean exit never raises, full stop."""
    runner = SubprocessDelegationCliRunner()
    argv = _python_argv("print('ok')")

    stdout = runner.run(argv, timeout_seconds=30.0)

    assert stdout.strip() == "ok"


# --- OMN-15535: SubprocessDelegationCliRunner -- stdout tail on CLI failure --
#
# OMN-15240 fixed stderr truncation but never touched stdout. In
# ``--output receipt`` mode the CLI prints its actual diagnostic (the
# ModelSkillResult JSON, including the delegation quality gate's
# SCHEMA_VIOLATION detail) to STDOUT on a non-zero exit -- which
# ``SubprocessDelegationCliRunner.run()`` never read at all, silently
# dropping the one durable diagnostic surface for a receipt-mode failure
# (OMN-15488 comment bd30cc1b).


def test_nonzero_exit_attaches_full_stdout_alongside_stderr_omn15535() -> None:
    """A non-zero CLI exit with nonempty stdout must attach the COMPLETE
    (unsliced) stdout onto the raised ``LlmTransportError`` -- not just
    stderr -- so a caller can recover the receipt-mode diagnostic without
    reading files off disk (the exact recovery path the OMN-15488
    attempt-3 canary was forced into)."""
    stdout_marker = "STDOUT_RECEIPT_DIAGNOSTIC_MARKER_ab12cd34"
    script = (
        "import sys\n"
        f'sys.stdout.write(\'{{"status": "error", "result": {{"error_message": '
        f'"SCHEMA_VIOLATION: {stdout_marker}"}}}}\\n\')\n'
        "sys.stderr.write('onex CLI: quality gate rejected the response\\n')\n"
        "sys.exit(1)\n"
    )
    argv = _python_argv(script)
    runner = SubprocessDelegationCliRunner()

    with pytest.raises(LlmTransportError) as excinfo:
        runner.run(argv, timeout_seconds=30.0)

    exc = excinfo.value
    assert exc.exit_code == 1
    assert exc.stdout is not None
    assert stdout_marker in exc.stdout
    # The stderr behavior OMN-15240 proved must be unchanged.
    assert exc.stderr is not None
    assert "quality gate rejected" in exc.stderr
    # The bounded tail also reaches the message string itself.
    assert stdout_marker in str(exc)


def test_nonzero_exit_stdout_tail_survives_a_downstream_truncation_budget_omn15535() -> None:
    """Same class of proof as OMN-15240's stderr test: the marker's survival
    must depend on reading the structured ``.stdout`` field, and a long
    benign prefix before the real diagnostic must not defeat a naive
    head-truncation read of that field."""
    tail_marker = "REAL_DIAGNOSTIC_STDOUT_TAIL_MARKER_zz77qq"
    script = (
        "import sys\n"
        f"sys.stdout.write('warning: ' + ('x' * 300) + '\\n')\n"
        f"sys.stdout.write('filler ' * 50 + '\\n')\n"
        f"sys.stdout.write('SCHEMA_VIOLATION: {tail_marker}\\n')\n"
        "sys.exit(1)\n"
    )
    argv = _python_argv(script)
    runner = SubprocessDelegationCliRunner()

    with pytest.raises(LlmTransportError) as excinfo:
        runner.run(argv, timeout_seconds=30.0)

    exc = excinfo.value
    assert exc.stdout is not None
    assert tail_marker in exc.stdout


def test_nonzero_exit_with_empty_stdout_omits_the_stdout_message_suffix_omn15535() -> None:
    """A stderr-only failure (empty stdout) keeps its existing message shape
    -- no dangling ``| stdout: `` suffix -- and ``exc.stdout`` reflects the
    real empty string rather than a synthesized placeholder."""
    script = "import sys\nsys.stderr.write('plain stderr failure\\n')\nsys.exit(1)\n"
    argv = _python_argv(script)
    runner = SubprocessDelegationCliRunner()

    with pytest.raises(LlmTransportError) as excinfo:
        runner.run(argv, timeout_seconds=30.0)

    exc = excinfo.value
    assert exc.stdout == ""
    assert "| stdout:" not in str(exc)
    assert "plain stderr failure" in str(exc)


# --- OMN-15566: quality-gate rejections are semantic, not transport ---
#
# The 2026-07-30 OMN-15488 battery crashed at baseline seed 4028: the
# delegation node's platform-side quality gate rejected a completion as
# syntactically malformed JSON after exhausting its own 3 internal retries,
# `SubprocessDelegationCliRunner.run()` saw only "onex CLI exited 1" and
# raised `LlmTransportError`, and that transport-classified exception is
# INVISIBLE to card mode's bounded reprompt loop (`llm/programming.py`,
# `except LlmSemanticError`) and the plain decide() path's equivalent
# (`llm/pilot.py`, same catch, OMN-15239) -- so it propagated straight out
# of the match and killed the whole battery process. `LlmBusDelegationClient
# .complete()` must reclassify a quality-gate REJECTION (MALFORMED /
# SCHEMA_VIOLATION response classes) as `LlmSemanticError` so the existing,
# already-proven bounded reprompt recovers it -- exactly as the HTTP binding
# already does for the same failure class (steel #128, 2026-07-22 battery:
# 2 recovered via reprompt, 0 aborts).


_QUALITY_GATE_FIXTURE_CORRELATION_ID = "738867fd-3db1-40b1-9854-4f269ae50fcd"


def _receipt_stdout_with_quality_gate_failure(
    *,
    reasons: list[str],
    correlation_id: str = _QUALITY_GATE_FIXTURE_CORRELATION_ID,
    error: str = "",
) -> str:
    """A CLI stdout receipt shaped like ``ModelSkillResult[ModelReceiptRuntimeSummary]``
    on a non-zero, quality-gate-rejected exit (``receipt_mode.py``'s failure
    branch: ``result.terminal_payload`` mirrors the runtime's persisted
    ``workflow_result.json`` verbatim, including ``quality_gates_failed`` --
    this is the exact shape recovered from the real OMN-15488 crash's own
    persisted receipt, correlation ``738867fd-3db1-40b1-9854-4f269ae50fcd``
    by default).

    ``correlation_id``/``error`` are overridable (OMN-15566 r5b) so callers
    can build the STALE-receipt scenario the r5 adversarial verifier proved
    reachable: a receipt whose top-level ``correlation_id`` does not match
    THIS invocation's own id and/or whose ``result.error`` is non-empty (a
    genuine crash) must never classify as semantic even when
    ``quality_gates_failed`` is present.
    """
    return json.dumps(
        {
            "skill_name": "delegate",
            "node_name": "node_delegate_skill_orchestrator",
            "status": "error",
            "correlation_id": correlation_id,
            "run_id": correlation_id,
            "exit_code": 1,
            "duration_ms": 133380,
            "result": {
                "workflow_result": "failed",
                "exit_code": 1,
                "workflow": "/omnibase_infra/.venv/.../node_delegate_skill_orchestrator/"
                "contract.yaml",
                "terminal_payload": {
                    "status": "failed",
                    "correlation_id": correlation_id,
                    "quality_gate_passed": False,
                    "quality_gates_failed": reasons,
                    "error_message": "",
                },
                "handler_result": None,
                "error": error,
                "capture_log": "17:36:43 INFO omnibase_core.runtime.runtime_local — result=failed",
            },
            "result_model": "omnibase_infra.cli.model_receipt_runtime_summary."
            "ModelReceiptRuntimeSummary",
        }
    )


class _RaisingRunner:
    """Fake ``ProtocolDelegationCliRunner`` whose ``run()`` raises unconditionally."""

    def __init__(self, error: LlmTransportError) -> None:
        self._error = error

    def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> str:
        raise self._error


def _fixture_correlation_client(
    *, runner: ProtocolDelegationCliRunner, tmp_path: Path
) -> LlmBusDelegationClient:
    """A client pinned to mint ``_QUALITY_GATE_FIXTURE_CORRELATION_ID`` --
    OMN-15566 r5b's invocation-binding fix requires the receipt's
    top-level ``correlation_id`` to match THIS invocation's own id, so the
    fixed-``_RaisingRunner`` tests (whose stdout is built BEFORE ``complete()``
    mints a correlation id) must pin the client to the same fixed id the
    fixture stdout already carries -- a real ``uuid4()`` mint would almost
    never match it.
    """
    return _client(
        runner=runner,
        tmp_path=tmp_path,
        new_correlation_id=lambda: UUID(_QUALITY_GATE_FIXTURE_CORRELATION_ID),
    )


def test_malformed_quality_gate_rejection_surfaces_as_semantic_malformed_json(
    tmp_path: Path,
) -> None:
    """RED on pre-fix main: a delegation-node MALFORMED rejection must raise
    ``LlmSemanticError(code="malformed_json")`` -- the type card mode's and
    the plain decide() path's bounded reprompt loops both catch -- not the
    ``LlmTransportError`` the runner itself raised. This is the exact class
    that killed the OMN-15488 battery at seed 4028.
    """
    stdout = _receipt_stdout_with_quality_gate_failure(
        reasons=["MALFORMED: response is not valid JSON: Expecting ':' delimiter"]
    )
    transport_error = LlmTransportError(
        "onex delegation CLI exited 1: (quality gate rejection)",
        retryable=False,
        argv=("uv", "run", "onex", "node", "node_delegate_skill_orchestrator"),
        exit_code=1,
        stderr="",
        stdout=stdout,
    )
    client = _fixture_correlation_client(runner=_RaisingRunner(transport_error), tmp_path=tmp_path)

    with pytest.raises(LlmSemanticError) as excinfo:
        client.complete(_request(wants_tactical_response_contract=False))

    exc = excinfo.value
    assert exc.code == "malformed_json"
    assert exc.detail is not None
    assert "MALFORMED" in exc.detail
    assert "Expecting ':' delimiter" in exc.detail


def test_schema_violation_quality_gate_rejection_surfaces_as_semantic_invalid_action_parameters(
    tmp_path: Path,
) -> None:
    """RED on pre-fix main: a SCHEMA_VIOLATION rejection (valid JSON, wrong
    shape -- the OMN-15488 attempt-3 canary's failure class) must also
    reclassify as a semantic error, not a transport error."""
    stdout = _receipt_stdout_with_quality_gate_failure(
        reasons=["SCHEMA_VIOLATION: <root>: {...} is not valid under any of the given schemas"]
    )
    transport_error = LlmTransportError(
        "onex delegation CLI exited 1: (quality gate rejection)",
        retryable=False,
        argv=("uv", "run", "onex", "node", "node_delegate_skill_orchestrator"),
        exit_code=1,
        stderr="",
        stdout=stdout,
    )
    client = _fixture_correlation_client(runner=_RaisingRunner(transport_error), tmp_path=tmp_path)

    with pytest.raises(LlmSemanticError) as excinfo:
        client.complete(_request(wants_tactical_response_contract=False))

    exc = excinfo.value
    assert exc.code == "invalid_action_parameters"
    assert exc.detail is not None
    assert "SCHEMA_VIOLATION" in exc.detail


def test_stale_receipt_with_mismatched_correlation_and_crash_error_stays_transport_error(
    tmp_path: Path,
) -> None:
    """RED on pre-fix head (59ba1c17) -- the r5 adversarial verifier's exact
    finding 1: ``workflow_result.json`` is a SHARED per-provider file,
    rewritten by every completion against the same binding, including on
    the CLI's own crash path. Without binding the classification to THIS
    invocation, a STALE prior completion's ``quality_gates_failed`` payload
    (a DIFFERENT ``correlation_id``) plus a genuine crash on THIS invocation
    (non-empty ``result.error``) misclassified as
    ``LlmSemanticError("malformed_json")`` instead of staying
    ``LlmTransportError``. This receipt intentionally carries BOTH signals of
    genuineness at once (mismatched correlation id AND a non-empty crash
    error) so the fix's binding guard is proven on the exact adversarial
    shape, not a simplified stand-in.
    """
    this_invocation_id = UUID("11111111-1111-1111-1111-111111111111")
    stale_correlation_id = "00000000-0000-0000-0000-0000000000aa"
    stdout = _receipt_stdout_with_quality_gate_failure(
        reasons=["MALFORMED: response is not valid JSON: Expecting ':' delimiter"],
        correlation_id=stale_correlation_id,
        error="Traceback (most recent call last):\n  ...\nRuntimeError: boom",
    )
    transport_error = LlmTransportError(
        "onex delegation CLI exited 1: (genuine crash)",
        retryable=False,
        argv=("uv", "run", "onex", "node", "node_delegate_skill_orchestrator"),
        exit_code=1,
        stderr="",
        stdout=stdout,
    )
    client = _client(
        runner=_RaisingRunner(transport_error),
        tmp_path=tmp_path,
        new_correlation_id=lambda: this_invocation_id,
    )

    with pytest.raises(LlmTransportError) as excinfo:
        client.complete(_request(wants_tactical_response_contract=False))

    assert excinfo.value is transport_error


def test_stale_receipt_with_matching_correlation_but_crash_error_stays_transport_error(
    tmp_path: Path,
) -> None:
    """Second half of finding 1's fix: even when the correlation id happens
    to match THIS invocation, a non-empty ``result.error`` means the runtime
    raised before producing a terminal result -- a genuine crash -- and must
    never be reclassified as semantic."""
    stdout = _receipt_stdout_with_quality_gate_failure(
        reasons=["MALFORMED: response is not valid JSON: Expecting ':' delimiter"],
        error="Traceback (most recent call last):\n  ...\nRuntimeError: boom",
    )
    transport_error = LlmTransportError(
        "onex delegation CLI exited 1: (genuine crash)",
        retryable=False,
        argv=("uv", "run", "onex", "node", "node_delegate_skill_orchestrator"),
        exit_code=1,
        stderr="",
        stdout=stdout,
    )
    client = _fixture_correlation_client(runner=_RaisingRunner(transport_error), tmp_path=tmp_path)

    with pytest.raises(LlmTransportError) as excinfo:
        client.complete(_request(wants_tactical_response_contract=False))

    assert excinfo.value is transport_error


def test_genuine_transport_failure_still_raises_llm_transport_error(tmp_path: Path) -> None:
    """Control case: a non-zero exit that is NOT a quality-gate rejection
    (no ``quality_gates_failed`` content reachable in stdout -- a real CLI
    crash/launch failure/environment error) must keep raising
    ``LlmTransportError`` unchanged. This is the negative half of the fix:
    reclassification must not swallow genuine transport failures."""
    transport_error = LlmTransportError(
        "onex delegation CLI exited 1: connection refused",
        retryable=False,
        argv=("uv", "run", "onex", "node", "node_delegate_skill_orchestrator"),
        exit_code=1,
        stderr="ConnectionRefusedError: [Errno 61] Connection refused",
        stdout="",
    )
    client = _client(runner=_RaisingRunner(transport_error), tmp_path=tmp_path)

    with pytest.raises(LlmTransportError) as excinfo:
        client.complete(_request())

    assert excinfo.value is transport_error


def test_nonzero_exit_with_unparsable_stdout_still_raises_llm_transport_error(
    tmp_path: Path,
) -> None:
    """A non-zero exit whose stdout is not the expected JSON receipt shape
    (e.g. a launch failure that never reached receipt-mode output) must not
    be silently swallowed by the classifier -- it re-raises the original
    ``LlmTransportError`` unchanged rather than raising nothing or crashing
    on the malformed stdout itself."""
    transport_error = LlmTransportError(
        "failed to launch onex delegation CLI: [Errno 2] No such file or directory",
        retryable=False,
    )
    client = _client(runner=_RaisingRunner(transport_error), tmp_path=tmp_path)

    with pytest.raises(LlmTransportError) as excinfo:
        client.complete(_request())

    assert excinfo.value is transport_error
