"""Static purity and inert-descriptor gates for the unbound dealer."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.cards.dealer import DealerCompute

_SOURCE_PATH = Path(inspect.getsourcefile(DealerCompute) or "")
_CONTRACT_PATH = _SOURCE_PATH.with_name("contract.yaml")


def _source() -> str:
    return _SOURCE_PATH.read_text(encoding="utf-8")


@pytest.mark.unit
def test_dealer_has_no_io_discovery_registry_or_runtime_authority() -> None:
    source = _source()
    forbidden = (
        "requests",
        "httpx",
        "aiohttp",
        "sqlite3",
        "yaml",
        "pathlib",
        "registry",
        "default_dir",
        "os.environ",
        "getenv",
    )
    assert not [token for token in forbidden if token in source.lower()]


@pytest.mark.unit
def test_dealer_has_no_file_clock_id_or_global_random_calls() -> None:
    forbidden: list[str] = []
    for node in ast.walk(ast.parse(_source())):
        if isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names if alias.name == "random")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"open", "uuid1", "uuid4", "ulid"}:
                forbidden.append(node.func.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id in {"random", "time", "datetime"}:
                forbidden.append(f"{owner.id}.{node.func.attr}")
    assert forbidden == []


@pytest.mark.unit
def test_public_api_exposes_only_immutable_scope_and_no_caller_rng() -> None:
    assert not hasattr(DealerCompute, "fisher_yates")
    assert not hasattr(DealerCompute, "open_deck")
    assert not hasattr(DealerCompute, "draw")
    for method_name in (
        "open_deck_for_seat",
        "deal_hand_for_seat",
        "spawn_deal_for_seat",
    ):
        signature = inspect.signature(getattr(DealerCompute, method_name))
        assert "scope" in signature.parameters
        assert "rng" not in signature.parameters
        assert "match_rng" not in signature.parameters
        assert "Random" not in str(signature)


@pytest.mark.unit
def test_dealer_instance_is_frozen_and_stateless() -> None:
    dealer = DealerCompute()
    assert dealer == DealerCompute()
    with pytest.raises((FrozenInstanceError, TypeError)):
        dealer.hidden_state = object()  # type: ignore[attr-defined]


@pytest.mark.unit
def test_descriptor_is_inert_and_has_an_empty_bus() -> None:
    raw: object = yaml.safe_load(_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    event_bus = raw["event_bus"]
    assert event_bus == {"subscribe_topics": [], "publish_topics": []}
    assert raw["node_type"] == "compute"
    assert raw["descriptor"]["purity"] == "pure"
