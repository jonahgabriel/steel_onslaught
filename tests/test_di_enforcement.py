"""AST guardrails for the Slice-1 composition boundary."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

_SRC = Path(__file__).parents[1] / "src" / "steel_onslaught"
_ROOT = _SRC / "match" / "composition.py"
_FORBIDDEN_NAMES = {
    "AggressivePilot",
    "DefensivePilot",
    "EventFactory",
    "InProcessEventBus",
    "LeaderboardHandler",
    "MatchContractCatalog",
    "ModelSOFilesystemLearningArtifactsConfig",
    "ModelSOSQLiteLeaderboardConfig",
    "ModelSOSQLiteLedgerConfig",
    "PilotSpecRegistry",
    "PredictivePilot",
    "SQLiteLedger",
    "SystemClock",
    "SystemIdentityProvider",
    "YamlFilesystemLearningArtifactStore",
}
_EFFECT_NAMES = {"datetime.now", "ulid.new", "uuid4"}

# Exact direct-call budget. Constructor references, lambdas, wrappers, and
# calls in any other function/file are forbidden even inside composition.py.
_APPROVED_CALLS = Counter(
    {
        ("SystemClock.now", "datetime.now"): 1,
        ("SystemIdentityProvider.new_match_id", "ulid.new"): 1,
        ("SystemIdentityProvider.new_correlation_id", "uuid4"): 1,
        ("SystemIdentityProvider.new_event_id", "ulid.new"): 1,
        ("SystemIdentityProvider.new_message_id", "uuid4"): 1,
        ("load_match_contract_catalog", "MatchContractCatalog"): 1,
        ("load_pilot_registry", "PilotSpecRegistry"): 1,
        ("pilot_from_spec", "AggressivePilot"): 1,
        ("pilot_from_spec", "DefensivePilot"): 1,
        ("pilot_from_spec", "PredictivePilot"): 1,
        ("build_runtime_dependencies", "SystemClock"): 1,
        ("build_runtime_dependencies", "SystemIdentityProvider"): 1,
        ("build_runtime_dependencies", "EventFactory"): 1,
        ("build_runtime_dependencies", "InProcessEventBus"): 1,
        ("build_runtime_dependencies", "ModelSOSQLiteLedgerConfig"): 1,
        ("build_runtime_dependencies", "SQLiteLedger"): 1,
        ("build_runtime_dependencies", "ModelSOSQLiteLeaderboardConfig"): 1,
        ("build_runtime_dependencies", "LeaderboardHandler"): 1,
        ("build_learning_dependencies", "SystemClock"): 1,
        (
            "build_learning_dependencies",
            "ModelSOFilesystemLearningArtifactsConfig",
        ): 1,
        ("build_learning_dependencies", "YamlFilesystemLearningArtifactStore"): 1,
    }
)


@dataclass(frozen=True)
class _Usage:
    line: int
    kind: str
    function: str
    direct_call: bool
    in_lambda: bool


class _ReferenceScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: dict[str, str] = {}
        self.usages: list[_Usage] = []
        self._classes: list[str] = []
        self._functions: list[str] = []
        self._lambda_depth = 0

    @property
    def function(self) -> str:
        pieces = [*self._classes, *self._functions]
        return ".".join(pieces) if pieces else "<module>"

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

    def _record(self, node: ast.expr, resolved: str, *, direct_call: bool) -> None:
        kind = _forbidden_kind(resolved)
        if kind is not None:
            self.usages.append(
                _Usage(
                    line=node.lineno,
                    kind=kind,
                    function=self.function,
                    direct_call=direct_call,
                    in_lambda=self._lambda_depth > 0,
                )
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        self._classes.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self._classes.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        self._functions.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self._functions.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._lambda_depth += 1
        self.visit(node.body)
        self._lambda_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        resolved = self.resolve(node.value)
        if resolved is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.symbols[target.id] = resolved
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            resolved = self.resolve(node.value)
            if resolved is not None:
                self.symbols[node.target.id] = resolved
        if node.value is not None:
            self.visit(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        resolved = self.resolve(node)
        if resolved is not None:
            self._record(node, resolved, direct_call=False)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        resolved = self.resolve(node)
        if resolved is not None and _forbidden_kind(resolved) is not None:
            self._record(node, resolved, direct_call=False)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved_func = self.resolve(node.func)
        if resolved_func is not None and _forbidden_kind(resolved_func) is not None:
            self._record(node.func, resolved_func, direct_call=True)
        else:
            resolved_value = self.resolve(node)
            if resolved_value is not None and _forbidden_kind(resolved_value) is not None:
                self._record(node, resolved_value, direct_call=False)
            self.visit(node.func)
        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)


def _forbidden_kind(resolved: str) -> str | None:
    tail = resolved.rsplit(".", 1)[-1]
    if tail in _FORBIDDEN_NAMES:
        return tail
    if resolved.endswith(".datetime.now") or resolved == "datetime.now":
        return "datetime.now"
    if resolved.endswith(".uuid4") or resolved == "uuid4":
        return "uuid4"
    if resolved.endswith(".ulid.new") or resolved == "ulid.new":
        return "ulid.new"
    return None


def _usages(source: str) -> list[_Usage]:
    scanner = _ReferenceScanner()
    scanner.visit(ast.parse(source))
    return scanner.usages


def _violations(source: str) -> list[str]:
    return [f"{usage.line}:{usage.kind}" for usage in _usages(source)]


@pytest.mark.unit
def test_effectful_construction_is_confined_to_exact_root_calls() -> None:
    violations: list[str] = []
    observed: Counter[tuple[str, str]] = Counter()
    for path in sorted(_SRC.rglob("*.py")):
        for usage in _usages(path.read_text(encoding="utf-8")):
            key = (usage.function, usage.kind)
            if (
                path == _ROOT
                and usage.direct_call
                and not usage.in_lambda
                and key in _APPROVED_CALLS
            ):
                observed[key] += 1
            else:
                violations.append(
                    f"{path.relative_to(_SRC)}:{usage.line}:{usage.function}:{usage.kind}"
                )
    if observed != _APPROVED_CALLS:
        violations.append(f"approved-call mismatch: {observed} != {_APPROVED_CALLS}")
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
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def invoke(factory):\n    return factory(cfg)\n"
            "invoke(SQLiteLedger)"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "factory = lambda: SQLiteLedger(cfg)\nfactory()"
        ),
        (
            "from functools import partial\n"
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "factory = partial(SQLiteLedger, cfg)"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def register(*, factory):\n    pass\nregister(factory=SQLiteLedger)"
        ),
    ],
)
def test_guard_detects_alias_getattr_and_higher_order_evasions(source: str) -> None:
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
