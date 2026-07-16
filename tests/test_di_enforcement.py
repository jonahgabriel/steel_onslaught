"""AST guardrails for the Slice-1 composition boundary."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
_OWNED_CLASS_DEFINITIONS: dict[Path, frozenset[str]] = {
    Path("bus/in_process.py"): frozenset({"InProcessEventBus"}),
    Path("contracts/pilot_registry.py"): frozenset({"PilotSpecRegistry"}),
    Path("events/factory.py"): frozenset({"EventFactory"}),
    Path("learning/filesystem_artifacts.py"): frozenset(
        {
            "ModelSOFilesystemLearningArtifactsConfig",
            "YamlFilesystemLearningArtifactStore",
        }
    ),
    Path("ledger/sqlite_ledger.py"): frozenset({"ModelSOSQLiteLedgerConfig", "SQLiteLedger"}),
    Path("match/composition.py"): frozenset({"SystemClock", "SystemIdentityProvider"}),
    Path("match/fold.py"): frozenset({"MatchContractCatalog"}),
    Path("pilots/aggressive.py"): frozenset({"AggressivePilot"}),
    Path("pilots/defensive.py"): frozenset({"DefensivePilot"}),
    Path("pilots/predictive.py"): frozenset({"PredictivePilot"}),
    Path("projections/leaderboard/handler.py"): frozenset(
        {"LeaderboardHandler", "ModelSOSQLiteLeaderboardConfig"}
    ),
}

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


_UNRESOLVED = object()


@dataclass
class _Scope:
    kind: Literal["module", "class", "function", "lambda"]
    symbols: dict[str, str | object]
    local_names: frozenset[str] = frozenset()
    global_names: frozenset[str] = frozenset()
    nonlocal_names: frozenset[str] = frozenset()


class _LocalBindingCollector(ast.NodeVisitor):
    """Collect bindings governed by Python's function-wide local-name rule."""

    def __init__(self) -> None:
        self.local_names: set[str] = set()
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()

    def visit_Global(self, node: ast.Global) -> None:
        self.global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocal_names.update(node.names)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.local_names.add(node.id)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self.local_names.add(node.name)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.local_names.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.local_names.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.local_names.add(node.name)
        self._visit_definition_expressions(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.local_names.add(node.name)
        self._visit_definition_expressions(node)

    def _visit_definition_expressions(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.local_names.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Lambda parameters and body belong to the lambda's own scope.
        return

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        values: list[ast.expr],
    ) -> None:
        # Comprehension iteration targets belong to the comprehension's implicit
        # scope, while assignment expressions in its values bind outside it.
        for generator in generators:
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        for value in values:
            self.visit(value)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, [node.key, node.value])

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name is not None:
            self.local_names.add(node.name)
        if node.pattern is not None:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name is not None:
            self.local_names.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest is not None:
            self.local_names.add(node.rest)
        self.generic_visit(node)

    def finish(self) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        directives = self.global_names | self.nonlocal_names
        return (
            frozenset(self.local_names - directives),
            frozenset(self.global_names),
            frozenset(self.nonlocal_names),
        )


def _parameter_names(arguments: ast.arguments) -> set[str]:
    names = {
        argument.arg
        for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    }
    if arguments.vararg is not None:
        names.add(arguments.vararg.arg)
    if arguments.kwarg is not None:
        names.add(arguments.kwarg.arg)
    return names


def _function_scope(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> _Scope:
    collector = _LocalBindingCollector()
    for statement in node.body:
        collector.visit(statement)
    local_names, global_names, nonlocal_names = collector.finish()
    local_names = frozenset(set(local_names) | _parameter_names(node.args))
    return _Scope(
        kind="function",
        symbols={name: _UNRESOLVED for name in local_names},
        local_names=local_names,
        global_names=global_names,
        nonlocal_names=nonlocal_names,
    )


def _lambda_scope(node: ast.Lambda) -> _Scope:
    collector = _LocalBindingCollector()
    collector.visit(node.body)
    local_names, global_names, nonlocal_names = collector.finish()
    local_names = frozenset(set(local_names) | _parameter_names(node.args))
    return _Scope(
        kind="lambda",
        symbols={name: _UNRESOLVED for name in local_names},
        local_names=local_names,
        global_names=global_names,
        nonlocal_names=nonlocal_names,
    )


class _ReferenceScanner(ast.NodeVisitor):
    def __init__(self, *, owned_class_definitions: frozenset[str]) -> None:
        self._scopes = [_Scope(kind="module", symbols={})]
        self._owned_class_definitions = owned_class_definitions
        self.usages: list[_Usage] = []
        self._classes: list[str] = []
        self._functions: list[str] = []
        self._lambda_depth = 0

    @property
    def function(self) -> str:
        pieces = [*self._classes, *self._functions]
        return ".".join(pieces) if pieces else "<module>"

    @property
    def _scope(self) -> _Scope:
        return self._scopes[-1]

    def _scope_value(self, scope: _Scope, name: str) -> str | None:
        value = scope.symbols.get(name, _UNRESOLVED)
        return value if isinstance(value, str) else None

    def _resolve_nonlocal(self, name: str, start: int) -> str | None:
        for scope in reversed(self._scopes[:start]):
            if scope.kind in {"function", "lambda"} and name in scope.local_names:
                return self._scope_value(scope, name)
        return None

    def _resolve_name(self, name: str) -> str | None:
        current_index = len(self._scopes) - 1
        current = self._scope
        if current.kind in {"function", "lambda"}:
            if name in current.global_names:
                return self._scope_value(self._scopes[0], name) or name
            if name in current.nonlocal_names:
                return self._resolve_nonlocal(name, current_index)

        skip_class_scopes = current.kind in {"function", "lambda"}
        for index in range(current_index, -1, -1):
            scope = self._scopes[index]
            if scope.kind == "class" and skip_class_scopes:
                continue
            if scope.kind in {"function", "lambda"} and name in scope.local_names:
                return self._scope_value(scope, name)
            if name in scope.symbols:
                return self._scope_value(scope, name)
            if scope.kind in {"function", "lambda"}:
                skip_class_scopes = True
        return name

    def _binding_scope(self, name: str) -> _Scope:
        current = self._scope
        if current.kind not in {"function", "lambda"}:
            return current
        if name in current.global_names:
            return self._scopes[0]
        if name in current.nonlocal_names:
            for scope in reversed(self._scopes[:-1]):
                if scope.kind in {"function", "lambda"} and name in scope.local_names:
                    return scope
        return current

    def _bind(self, name: str, resolved: str | None) -> None:
        self._binding_scope(name).symbols[name] = resolved or _UNRESOLVED

    def resolve(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
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
            self._bind(alias.asname or alias.name.split(".")[0], alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self._bind(
                alias.asname or alias.name,
                f"{module}.{alias.name}".lstrip("."),
            )

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
        is_owned_definition = (
            self._scope.kind == "module" and node.name in self._owned_class_definitions
        )
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._classes.append(node.name)
        self._scopes.append(_Scope(kind="class", symbols={}))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()
        self._classes.pop()
        self._bind(node.name, node.name if is_owned_definition else None)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        self._functions.append(node.name)
        self._scopes.append(_function_scope(node))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()
        self._functions.pop()
        self._bind(node.name, None)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        self._lambda_depth += 1
        self._scopes.append(_lambda_scope(node))
        self.visit(node.body)
        self._scopes.pop()
        self._lambda_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        resolved = self.resolve(node.value)
        self.visit(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._bind(target.id, resolved)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            resolved = self.resolve(node.value)
            self.visit(node.value)
            if isinstance(node.target, ast.Name):
                self._bind(node.target.id, resolved)
        elif isinstance(node.target, ast.Name):
            self._bind(node.target.id, None)

    def visit_Name(self, node: ast.Name) -> None:
        if not isinstance(node.ctx, ast.Load):
            return
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


def _usages(
    source: str,
    *,
    owned_class_definitions: frozenset[str] = frozenset(),
) -> list[_Usage]:
    scanner = _ReferenceScanner(owned_class_definitions=owned_class_definitions)
    scanner.visit(ast.parse(source))
    return scanner.usages


def _violations(source: str) -> list[str]:
    return [f"{usage.line}:{usage.kind}" for usage in _usages(source)]


def _budget_mismatch(
    observed: Counter[tuple[str, str]],
    approved: Counter[tuple[str, str]],
) -> str | None:
    if observed == approved:
        return None
    return f"approved-call mismatch: {observed} != {approved}"


@pytest.mark.unit
def test_effectful_construction_is_confined_to_exact_root_calls() -> None:
    violations: list[str] = []
    observed: Counter[tuple[str, str]] = Counter()
    for path in sorted(_SRC.rglob("*.py")):
        relative_path = path.relative_to(_SRC)
        for usage in _usages(
            path.read_text(encoding="utf-8"),
            owned_class_definitions=_OWNED_CLASS_DEFINITIONS.get(relative_path, frozenset()),
        ):
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
    if mismatch := _budget_mismatch(observed, _APPROVED_CALLS):
        violations.append(mismatch)
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
def test_function_local_shadow_does_not_mutate_module_resolution() -> None:
    source = (
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
        "def harmless_earlier_function():\n"
        "    SQLiteLedger = harmless\n"
        "    return SQLiteLedger(cfg)\n"
        "def forbidden_later_function():\n"
        "    return SQLiteLedger(cfg)\n"
    )

    assert _violations(source) == ["6:SQLiteLedger"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def invoke(SQLiteLedger):\n"
            "    return SQLiteLedger(cfg)\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def invoke():\n"
            "    SQLiteLedger = harmless\n"
            "    return SQLiteLedger(cfg)\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "invoke = lambda SQLiteLedger: SQLiteLedger(cfg)\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def outer():\n"
            "    SQLiteLedger = harmless\n"
            "    def inner():\n"
            "        nonlocal SQLiteLedger\n"
            "        return SQLiteLedger(cfg)\n"
            "    return inner\n"
        ),
    ],
)
def test_guard_honors_harmless_lexical_shadows(source: str) -> None:
    assert _violations(source) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    pass\n"
            "SQLiteLedger()\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def invoke():\n"
            "    class SQLiteLedger:\n"
            "        pass\n"
            "    return SQLiteLedger()\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class Namespace:\n"
            "    class SQLiteLedger:\n"
            "        pass\n"
            "    instance = SQLiteLedger()\n"
        ),
    ],
)
def test_guard_honors_harmless_class_definition_shadows(source: str) -> None:
    assert _violations(source) == []


@pytest.mark.unit
def test_owned_forbidden_class_definition_retains_constructor_identity() -> None:
    source = (
        "class SystemClock:\n"
        "    pass\n"
        "def build_runtime_dependencies():\n"
        "    return SystemClock()\n"
    )

    assert _usages(
        source,
        owned_class_definitions=frozenset({"SystemClock"}),
    ) == [
        _Usage(
            line=4,
            kind="SystemClock",
            function="build_runtime_dependencies",
            direct_call=True,
            in_lambda=False,
        )
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "source, expected_line",
    [
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def outer():\n"
            "    def inner():\n"
            "        return SQLiteLedger(cfg)\n"
            "    return inner\n",
            4,
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "def invoke():\n"
            "    global SQLiteLedger\n"
            "    return SQLiteLedger(cfg)\n",
            4,
        ),
    ],
)
def test_guard_resolves_nested_closure_and_global_names(source: str, expected_line: int) -> None:
    assert _violations(source) == [f"{expected_line}:SQLiteLedger"]


@pytest.mark.unit
def test_approved_root_call_budget_rejects_an_extra_call() -> None:
    source = (
        "from steel_onslaught.match.composition import SystemClock\n"
        "def build_runtime_dependencies():\n"
        "    SystemClock()\n"
        "    SystemClock()\n"
    )
    key = ("build_runtime_dependencies", "SystemClock")
    observed = Counter(
        (usage.function, usage.kind)
        for usage in _usages(source)
        if usage.direct_call and not usage.in_lambda
    )

    assert observed == Counter({key: 2})
    assert _budget_mismatch(observed, Counter({key: 1})) is not None


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
