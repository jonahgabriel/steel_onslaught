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
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from steel_onslaught.contracts.application import ModelSODelegationProviderBinding
from steel_onslaught.llm.client_delegation import (
    _TACTICAL_RESPONSE_CONTRACT,
    LlmBusDelegationClient,
    ProtocolDelegationCliRunner,
    SubprocessDelegationCliRunner,
)
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
) -> LlmBusDelegationClient:
    return LlmBusDelegationClient(
        config=config or _config(tmp_path),
        new_correlation_id=uuid4,
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


def test_programming_path_completion_omits_the_tactical_response_contract_omn15522(
    tmp_path: Path,
) -> None:
    """OMN-15522 RED-FIRST regression.

    Card-mode programming completions (``LLMProgrammingPilot``) opt out of
    the tactical-decision contract via
    ``wants_tactical_response_contract=False`` -- their response is a
    whole-round register plan, not a single tactical decision, and
    forwarding the tactical schema made the platform's delegation quality
    gate reject a correct programming response as ``SCHEMA_VIOLATION``
    (OMN-15482 comment 14468f08, OMN-15488 canary). Must FAIL against the
    unfixed client, which forwarded ``_TACTICAL_RESPONSE_CONTRACT``
    unconditionally regardless of what the request asked for.
    """
    captured: dict[str, object] = {}

    def _stdout(argv: tuple[str, ...]) -> str:
        input_path = Path(argv[argv.index("--input") + 1])
        captured.update(json.loads(input_path.read_text(encoding="utf-8")))
        return _skill_result_json(correlation_id=str(captured["correlation_id"]))

    client = _client(runner=_RecordingRunner(_stdout), tmp_path=tmp_path)
    client.complete(_request(wants_tactical_response_contract=False))

    assert "response_contract" not in captured, (
        "programming-path completion must not carry a wire-level response "
        "contract -- response-shape validation for a register plan is owned "
        "by steel's own programming parser + bounded reprompt loop, not the "
        "per-tick tactical-decision schema"
    )


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
