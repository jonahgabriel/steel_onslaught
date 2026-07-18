"""Source-level purity gates for the register reducer."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from steel_onslaught.cards import registers

pytestmark = pytest.mark.unit

_SOURCE_PATH = Path(inspect.getsourcefile(registers) or "")


def _tree() -> ast.Module:
    return ast.parse(_SOURCE_PATH.read_text(encoding="utf-8"))


def test_reducer_imports_only_pure_contract_and_action_modules() -> None:
    tree = _tree()
    forbidden = {
        "asyncio",
        "aiohttp",
        "datetime",
        "httpx",
        "psycopg",
        "random",
        "requests",
        "sqlite3",
        "time",
        "uuid",
        "yaml",
    }
    imports = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for _ in [node]
    }
    imports.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert imports.isdisjoint(forbidden)
    assert not any(
        isinstance(node, ast.Name) and node.id in {"make_event", "EventBus", "open"}
        for node in ast.walk(tree)
    )


def test_reducer_has_no_clock_random_identity_or_file_io_calls() -> None:
    forbidden: list[str] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "open",
                "uuid4",
                "uuid1",
                "ulid",
            }:
                forbidden.append(node.func.id)
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {"now", "sleep"}:
                    forbidden.append(node.func.attr)
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                    "random",
                    "time",
                }:
                    forbidden.append(f"{node.func.value.id}.{node.func.attr}")
    assert not forbidden, f"non-deterministic or I/O calls found: {forbidden}"
