"""AST guardrails for the Slice-1 composition boundary."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).parents[1] / "src" / "steel_onslaught"
_ROOT = _SRC / "match" / "composition.py"
_CONCRETE_NAMES = {
    "InProcessEventBus",
    "SQLiteLedger",
    "ModelSOSQLiteLedgerConfig",
    "LeaderboardHandler",
    "ModelSOSQLiteLeaderboardConfig",
    "YamlFilesystemLearningArtifactStore",
    "ModelSOFilesystemLearningArtifactsConfig",
}


class _CallScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: dict[str, str] = {}
        self.calls: list[tuple[int, str]] = []

    def resolve(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return self.symbols.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            return f"{base}.{node.attr}" if base is not None else None
        if (
            isinstance(node, ast.Call)
            and self.resolve(node.func) in {"getattr", "builtins.getattr"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            base = self.resolve(node.args[0])
            return f"{base}.{node.args[1].value}" if base is not None else None
        return None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.symbols[alias.asname or alias.name.split(".")[0]] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self.symbols[alias.asname or alias.name] = f"{module}.{alias.name}".lstrip(".")

    def visit_Assign(self, node: ast.Assign) -> None:
        resolved = self.resolve(node.value)
        if resolved is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.symbols[target.id] = resolved
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            resolved = self.resolve(node.value)
            if resolved is not None:
                self.symbols[node.target.id] = resolved
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved = self.resolve(node.func)
        if resolved is not None:
            self.calls.append((node.lineno, resolved))
        self.generic_visit(node)


def _forbidden_kind(resolved: str) -> str | None:
    tail = resolved.rsplit(".", 1)[-1]
    if tail in _CONCRETE_NAMES:
        return tail
    if resolved.endswith(".datetime.now") or resolved == "datetime.now":
        return "datetime.now"
    if resolved.endswith(".uuid4") or resolved == "uuid4":
        return "uuid4"
    if resolved.endswith(".ulid.new") or resolved == "ulid.new":
        return "ulid.new"
    return None


def _violations(source: str, *, allowed: frozenset[str] = frozenset()) -> list[str]:
    scanner = _CallScanner()
    scanner.visit(ast.parse(source))
    return [
        f"{line}:{kind}"
        for line, resolved in scanner.calls
        if (kind := _forbidden_kind(resolved)) is not None and kind not in allowed
    ]


@pytest.mark.unit
def test_effectful_construction_is_confined_to_exact_root_calls() -> None:
    violations: list[str] = []
    root_allowed = frozenset(_CONCRETE_NAMES | {"datetime.now", "uuid4", "ulid.new"})
    for path in sorted(_SRC.rglob("*.py")):
        allowed = root_allowed if path == _ROOT else frozenset()
        for violation in _violations(path.read_text(encoding="utf-8"), allowed=allowed):
            violations.append(f"{path.relative_to(_SRC)}:{violation}")
    assert violations == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\nSQLiteLedger(cfg)",
        ("import steel_onslaught.ledger.sqlite_ledger as ledger\nledger.SQLiteLedger(cfg)"),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "ctor = SQLiteLedger\nctor(cfg)"
        ),
        (
            "import steel_onslaught.ledger.sqlite_ledger as ledger\n"
            "getattr(ledger, 'SQLiteLedger')(cfg)"
        ),
        "from datetime import datetime as dt\ndt.now()",
        "import uuid as ids\nmaker = ids.uuid4\nmaker()",
        "import ulid as identity\ngetattr(identity, 'new')()",
    ],
)
def test_guard_detects_alias_and_getattr_evasions(source: str) -> None:
    assert _violations(source), source


@pytest.mark.unit
def test_cli_requires_explicit_overlay_and_has_no_package_path_defaults() -> None:
    violations: list[str] = []
    for filename in ("main.py", "balance.py", "learn.py", "serve.py"):
        source = (_SRC / "cli" / filename).read_text(encoding="utf-8")
        if '"--overlay"' not in source:
            violations.append(f"{filename}: missing --overlay")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"parent", "parents"}:
                violations.append(f"{filename}:{node.lineno}: package path traversal")
    assert violations == []
