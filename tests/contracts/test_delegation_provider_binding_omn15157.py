"""Contract tests for ``ModelSODelegationProviderBinding`` (OMN-15157).

Covers the discriminated-union membership, closed-set validation
(``extra="forbid"``, closed ``task_type``/``source`` Literals), and that the
existing ``LlmProviderBinding`` members (``stub``/``openai_compatible``) are
untouched by the new third member -- the golden-stability requirement (no
delegation binding configured -> byte-identical existing behavior).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from steel_onslaught.contracts.application import (
    LlmProviderBinding,
    ModelSODelegationProviderBinding,
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOStubLlmProviderBinding,
)

pytestmark = pytest.mark.unit

_UNION_ADAPTER: TypeAdapter[Any] = TypeAdapter(LlmProviderBinding)


def _raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "kind": "onex_delegation",
        "provider_id": "onex-local-coder-mlx",
        "backend_id": "local-coder-mlx",
        "task_type": "agent_delegation",
        "source": "external-client",
        "model": "mlx-community/Qwen3.6-35B-A3B-8bit",
        "timeout_seconds": 300.0,
        "omnibase_infra_path": "/fixture/omni_home/omnibase_infra",
        "state_root": "/fixture/state_root",
    }
    raw.update(overrides)
    return raw


def test_valid_binding_round_trips_through_the_discriminated_union() -> None:
    binding = _UNION_ADAPTER.validate_python(_raw())

    assert isinstance(binding, ModelSODelegationProviderBinding)
    assert binding.kind == "onex_delegation"
    assert binding.provider_id == "onex-local-coder-mlx"
    assert binding.backend_id == "local-coder-mlx"
    assert binding.task_type == "agent_delegation"
    assert binding.source == "external-client"
    assert binding.model == "mlx-community/Qwen3.6-35B-A3B-8bit"
    assert binding.max_tokens is None


def test_source_defaults_to_external_client_and_rejects_other_values() -> None:
    binding = ModelSODelegationProviderBinding.model_validate(
        {k: v for k, v in _raw().items() if k != "source"}
    )
    assert binding.source == "external-client"

    with pytest.raises(ValidationError, match="source"):
        ModelSODelegationProviderBinding.model_validate(_raw(source="claude-code"))
    with pytest.raises(ValidationError, match="source"):
        ModelSODelegationProviderBinding.model_validate(_raw(source="codex"))


def test_task_type_is_a_closed_literal_matching_the_omnimarket_wire_set() -> None:
    """Pins the 13-member closed set (OMN-15158) this binding must never widen."""
    expected_task_types = (
        "test",
        "document",
        "research",
        "code_generation",
        "code_review",
        "refactor",
        "reasoning",
        "complex_reasoning",
        "planning",
        "review",
        "summarization",
        "agent_delegation",
        "escalation",
    )
    for task_type in expected_task_types:
        binding = ModelSODelegationProviderBinding.model_validate(_raw(task_type=task_type))
        assert binding.task_type == task_type

    with pytest.raises(ValidationError, match="task_type"):
        ModelSODelegationProviderBinding.model_validate(_raw(task_type="not_a_real_task_type"))


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelSODelegationProviderBinding.model_validate(_raw(unexpected_field="nope"))


def test_binding_is_frozen() -> None:
    binding = ModelSODelegationProviderBinding.model_validate(_raw())
    with pytest.raises(ValidationError):
        binding.provider_id = "changed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", ""),
        ("backend_id", ""),
        ("model", ""),
        ("timeout_seconds", 0.0),
        ("timeout_seconds", -1.0),
        ("timeout_seconds", 900.001),
        ("max_tokens", 0),
        ("max_tokens", 200001),
    ],
)
def test_rejects_out_of_bounds_values(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        ModelSODelegationProviderBinding.model_validate(_raw(**{field: value}))


def test_max_tokens_is_optional_and_positive_when_present() -> None:
    binding = ModelSODelegationProviderBinding.model_validate(_raw(max_tokens=4096))
    assert binding.max_tokens == 4096


def test_existing_union_members_are_unaffected_by_the_new_kind() -> None:
    """Golden-stability: stub/openai_compatible members parse exactly as before."""
    stub = _UNION_ADAPTER.validate_python({"kind": "stub", "provider_id": "p", "model": "m"})
    assert isinstance(stub, ModelSOStubLlmProviderBinding)

    http = _UNION_ADAPTER.validate_python(
        {
            "kind": "openai_compatible",
            "provider_id": "p",
            "endpoint_url": "https://provider.test/v1/chat/completions",
            "model": "m",
            "secret_ref": None,
            "timeout_seconds": 30.0,
            "max_tokens": None,
            "retry": {
                "max_attempts": 1,
                "initial_backoff_seconds": 0.1,
                "backoff_multiplier": 2.0,
            },
        }
    )
    assert isinstance(http, ModelSOOpenAICompatibleProviderBinding)


def test_unknown_kind_is_rejected_by_the_closed_union() -> None:
    with pytest.raises(ValidationError):
        _UNION_ADAPTER.validate_python(_raw(kind="not_a_real_kind"))
