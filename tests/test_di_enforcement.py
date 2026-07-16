"""Static guardrails for the Slice-1 composition boundary."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).parents[1] / "src" / "steel_onslaught"
_ROOT = _SRC / "match" / "composition.py"
_ADAPTERS = {
    _SRC / "bus" / "in_process.py",
    _SRC / "ledger" / "sqlite_ledger.py",
    _SRC / "projections" / "leaderboard" / "handler.py",
}
_CONCRETE_NAMES = {
    "InProcessEventBus",
    "SQLiteLedger",
    "ModelSOSQLiteLedgerConfig",
    "LeaderboardHandler",
    "ModelSOSQLiteLeaderboardConfig",
}
_EFFECT_NAMES = {"datetime.now", "uuid4", "ulid.new"}


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    target: ast.expr = node.func
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


@pytest.mark.unit
def test_concrete_adapters_are_constructed_only_at_composition_root() -> None:
    violations: list[str] = []
    allowed = _ADAPTERS | {_ROOT}
    for path in sorted(_SRC.rglob("*.py")):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in _CONCRETE_NAMES:
                violations.append(f"{path.relative_to(_SRC)}:{node.lineno}")

    assert violations == []


@pytest.mark.unit
def test_clock_and_identity_effects_are_confined_to_composition_root() -> None:
    violations: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if path == _ROOT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in _EFFECT_NAMES:
                violations.append(f"{path.relative_to(_SRC)}:{node.lineno}:{_call_name(node)}")

    assert violations == []


@pytest.mark.unit
def test_cli_requires_explicit_overlay() -> None:
    for filename in ("main.py", "balance.py", "learn.py", "serve.py"):
        source = (_SRC / "cli" / filename).read_text(encoding="utf-8")
        assert '"--overlay"' in source, filename
