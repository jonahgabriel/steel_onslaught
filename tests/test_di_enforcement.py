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
_FORBIDDEN_SYMBOLS = {
    "builtins.__import__": "__import__",
    "builtins.globals": "globals",
    "builtins.vars": "vars",
    "datetime.datetime.now": "datetime.now",
    "httpx.Client": "httpx.Client",
    "importlib.import_module": "importlib.import_module",
    "os.environ": "os.environ",
    "os.getenv": "os.getenv",
    "steel_onslaught.bus.in_process.InProcessEventBus": "InProcessEventBus",
    "steel_onslaught.contracts.pilot_registry.PilotSpecRegistry": "PilotSpecRegistry",
    "steel_onslaught.events.factory.EventFactory": "EventFactory",
    "steel_onslaught.learning.filesystem_artifacts.ModelSOFilesystemLearningArtifactsConfig": (
        "ModelSOFilesystemLearningArtifactsConfig"
    ),
    "steel_onslaught.learning.filesystem_artifacts.YamlFilesystemLearningArtifactStore": (
        "YamlFilesystemLearningArtifactStore"
    ),
    "steel_onslaught.ledger.sqlite_ledger.ModelSOSQLiteLedgerConfig": ("ModelSOSQLiteLedgerConfig"),
    "steel_onslaught.ledger.sqlite_ledger.SQLiteLedger": "SQLiteLedger",
    "steel_onslaught.match.composition.SystemClock": "SystemClock",
    "steel_onslaught.match.composition.SystemIdentityProvider": "SystemIdentityProvider",
    "steel_onslaught.match.fold.MatchContractCatalog": "MatchContractCatalog",
    "steel_onslaught.match.evaluation_storage.SQLiteEvaluationStorageAllocator": (
        "SQLiteEvaluationStorageAllocator"
    ),
    "steel_onslaught.match.composition.ApplicationPilotFactory": "ApplicationPilotFactory",
    "steel_onslaught.llm.adaptation.OpponentAwareClient": "OpponentAwareClient",
    "steel_onslaught.llm.client_http.HttpxJsonTransport": "HttpxJsonTransport",
    "steel_onslaught.llm.client_http.NoSecretResolver": "NoSecretResolver",
    "steel_onslaught.llm.client_http.OpenAICompatibleClient": "OpenAICompatibleClient",
    "steel_onslaught.llm.client_http.StaticLlmClientFactory": "StaticLlmClientFactory",
    "steel_onslaught.llm.client_http.SystemSleeper": "SystemSleeper",
    "steel_onslaught.llm.effect.LedgerLlmCompletionObserver": ("LedgerLlmCompletionObserver"),
    "steel_onslaught.llm.effect.ObservedLlmClient": "ObservedLlmClient",
    "steel_onslaught.llm.personas.PersonaRegistry.load": "PersonaRegistry.load",
    "steel_onslaught.llm.pilot.LLMPilot": "LLMPilot",
    "steel_onslaught.llm.stub.StubLlmClient": "StubLlmClient",
    "steel_onslaught.llm.tuner.LlmTunerGenerator": "LlmTunerGenerator",
    "steel_onslaught.pilots.aggressive.AggressivePilot": "AggressivePilot",
    "steel_onslaught.pilots.defensive.DefensivePilot": "DefensivePilot",
    "steel_onslaught.pilots.predictive.PredictivePilot": "PredictivePilot",
    "steel_onslaught.projections.leaderboard.handler.LeaderboardHandler": ("LeaderboardHandler"),
    "steel_onslaught.projections.leaderboard.handler.ModelSOSQLiteLeaderboardConfig": (
        "ModelSOSQLiteLeaderboardConfig"
    ),
    "ulid.new": "ulid.new",
    "uuid.uuid4": "uuid4",
}

# Exact direct-call budget. Constructor references, lambdas, wrappers, and
# calls in any other function/file are forbidden even inside composition.py.
_APPROVED_CALLS = Counter(
    {
        ("SystemClock.now", "datetime.datetime.now"): 1,
        ("SystemIdentityProvider.new_match_id", "ulid.new"): 1,
        ("SystemIdentityProvider.new_correlation_id", "uuid.uuid4"): 1,
        ("SystemIdentityProvider.new_event_id", "ulid.new"): 1,
        ("SystemIdentityProvider.new_message_id", "uuid.uuid4"): 1,
        (
            "load_match_contract_catalog",
            "steel_onslaught.match.fold.MatchContractCatalog",
        ): 1,
        (
            "load_pilot_registry",
            "steel_onslaught.contracts.pilot_registry.PilotSpecRegistry",
        ): 1,
        (
            "ApplicationPilotFactory.from_spec",
            "steel_onslaught.pilots.aggressive.AggressivePilot",
        ): 1,
        (
            "ApplicationPilotFactory.from_spec",
            "steel_onslaught.pilots.defensive.DefensivePilot",
        ): 1,
        (
            "ApplicationPilotFactory.from_spec",
            "steel_onslaught.pilots.predictive.PredictivePilot",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.match.composition.SystemClock",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.match.composition.SystemIdentityProvider",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.events.factory.EventFactory",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.bus.in_process.InProcessEventBus",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.ledger.sqlite_ledger.ModelSOSQLiteLedgerConfig",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.ledger.sqlite_ledger.SQLiteLedger",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.projections.leaderboard.handler.ModelSOSQLiteLeaderboardConfig",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.projections.leaderboard.handler.LeaderboardHandler",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.learning.filesystem_artifacts.ModelSOFilesystemLearningArtifactsConfig",
        ): 1,
        (
            "build_runtime_dependencies",
            "steel_onslaught.learning.filesystem_artifacts.YamlFilesystemLearningArtifactStore",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.match.composition.SystemClock",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.match.composition.SystemIdentityProvider",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.events.factory.EventFactory",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.llm.effect.LedgerLlmCompletionObserver",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.llm.client_http.StaticLlmClientFactory",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.llm.effect.ObservedLlmClient",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.llm.tuner.LlmTunerGenerator",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.learning.filesystem_artifacts.ModelSOFilesystemLearningArtifactsConfig",
        ): 1,
        (
            "build_learning_dependencies",
            "steel_onslaught.learning.filesystem_artifacts.YamlFilesystemLearningArtifactStore",
        ): 1,
        (
            "build_evaluation_storage_allocator",
            "steel_onslaught.match.evaluation_storage.SQLiteEvaluationStorageAllocator",
        ): 1,
        (
            "ApplicationPilotFactory.with_observer",
            "steel_onslaught.match.composition.ApplicationPilotFactory",
        ): 1,
        (
            "ApplicationPilotFactory.llm_pilot",
            "steel_onslaught.llm.effect.ObservedLlmClient",
        ): 1,
        (
            "ApplicationPilotFactory.llm_pilot",
            "steel_onslaught.llm.adaptation.OpponentAwareClient",
        ): 1,
        (
            "ApplicationPilotFactory.llm_pilot",
            "steel_onslaught.llm.pilot.LLMPilot",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.client_http.NoSecretResolver",
        ): 1,
        ("build_llm_dependencies", "httpx.Client"): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.client_http.HttpxJsonTransport",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.client_http.SystemSleeper",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.stub.StubLlmClient",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.client_http.OpenAICompatibleClient",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.client_http.StaticLlmClientFactory",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.personas.PersonaRegistry.load",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.match.composition.ApplicationPilotFactory",
        ): 1,
        (
            "build_llm_dependencies",
            "steel_onslaught.llm.tuner.LlmTunerGenerator",
        ): 1,
        (
            "build_pilot_duel_executor_with_dependencies.execute",
            "steel_onslaught.llm.effect.LedgerLlmCompletionObserver",
        ): 1,
        (
            "assemble_match_with_dependencies",
            "steel_onslaught.llm.effect.LedgerLlmCompletionObserver",
        ): 1,
    }
)


@dataclass(frozen=True)
class _Usage:
    line: int
    symbol: str
    function: str
    direct_call: bool
    in_lambda: bool

    @property
    def kind(self) -> str:
        return _FORBIDDEN_SYMBOLS[self.symbol]


_Provenance = frozenset[str]
_UNRESOLVED: _Provenance = frozenset()


@dataclass
class _Scope:
    kind: Literal["module", "class", "function", "lambda", "comprehension"]
    symbols: dict[str, _Provenance]
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
    def __init__(self, *, module_name: str, postponed_annotations: bool) -> None:
        self._module_name = module_name
        self._postponed_annotations = postponed_annotations
        self._scopes = [
            _Scope(
                kind="module",
                symbols={
                    "__import__": frozenset({"builtins.__import__"}),
                    "getattr": frozenset({"builtins.getattr"}),
                    "globals": frozenset({"builtins.globals"}),
                    "vars": frozenset({"builtins.vars"}),
                },
            )
        ]
        self.usages: list[_Usage] = []
        self._classes: list[str] = []
        self._functions: list[str] = []
        self._deferred_class_bindings: list[tuple[_Scope, str, _Provenance]] = []
        self._lambda_depth = 0

    @property
    def function(self) -> str:
        pieces = [*self._classes, *self._functions]
        return ".".join(pieces) if pieces else "<module>"

    @property
    def _scope(self) -> _Scope:
        return self._scopes[-1]

    def _resolve_nonlocal(self, name: str, start: int) -> _Provenance:
        for scope in reversed(self._scopes[:start]):
            if scope.kind in {"function", "lambda"} and name in scope.local_names:
                return scope.symbols.get(name, _UNRESOLVED)
        return _UNRESOLVED

    def _resolve_name(self, name: str) -> _Provenance:
        current_index = len(self._scopes) - 1
        current = self._scope
        if current.kind in {"function", "lambda"}:
            if name in current.global_names:
                return current.symbols.get(name, self._scopes[0].symbols.get(name, _UNRESOLVED))
            if name in current.nonlocal_names:
                return current.symbols.get(name, self._resolve_nonlocal(name, current_index))

        function_like = {"function", "lambda", "comprehension"}
        skip_class_scopes = current.kind in function_like
        for index in range(current_index, -1, -1):
            scope = self._scopes[index]
            if scope.kind == "class" and skip_class_scopes:
                continue
            if scope.kind in function_like and name in scope.local_names:
                return scope.symbols.get(name, _UNRESOLVED)
            if name in scope.symbols:
                return scope.symbols[name]
            if scope.kind in function_like:
                skip_class_scopes = True
        return _UNRESOLVED

    def _bind(self, name: str, resolved: _Provenance) -> None:
        # Global/nonlocal assignments get a function-analysis-local override.
        # Visiting a function definition must never mutate enclosing scan state.
        self._scope.symbols[name] = resolved

    def resolve(self, node: ast.expr) -> _Provenance:
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        if isinstance(node, ast.Attribute):
            return frozenset(f"{base}.{node.attr}" for base in self.resolve(node.value))
        if isinstance(node, ast.IfExp):
            return self.resolve(node.body) | self.resolve(node.orelse)
        if isinstance(node, ast.BoolOp):
            return frozenset().union(*(self.resolve(value) for value in node.values))
        if isinstance(node, ast.NamedExpr):
            return self.resolve(node.value)
        if (
            isinstance(node, ast.Call)
            and "builtins.getattr" in self.resolve(node.func)
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            return frozenset(f"{base}.{node.args[1].value}" for base in self.resolve(node.args[0]))
        return _UNRESOLVED

    def _import_module(self, node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""
        package = self._module_name.rpartition(".")[0]
        pieces = package.split(".") if package else []
        keep = max(0, len(pieces) - (node.level - 1))
        prefix = ".".join(pieces[:keep])
        return ".".join(part for part in (prefix, node.module or "") if part)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname is not None:
                self._bind(alias.asname, frozenset({alias.name}))
            else:
                root = alias.name.split(".", 1)[0]
                self._bind(root, frozenset({root}))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = self._import_module(node)
        for alias in node.names:
            if alias.name == "*":
                continue
            symbol = ".".join(part for part in (module, alias.name) if part)
            self._bind(alias.asname or alias.name, frozenset({symbol}))

    def _record(self, node: ast.expr, resolved: _Provenance, *, direct_call: bool) -> bool:
        forbidden = sorted(resolved & _FORBIDDEN_SYMBOLS.keys())
        for symbol in forbidden:
            self.usages.append(
                _Usage(
                    line=node.lineno,
                    symbol=symbol,
                    function=self.function,
                    direct_call=direct_call,
                    in_lambda=self._lambda_depth > 0,
                )
            )
        return bool(forbidden)

    def _visit_annotation(self, node: ast.expr | None) -> None:
        if node is not None and not self._postponed_annotations:
            self.visit(node)

    def _visit_arguments(self, arguments: ast.arguments) -> None:
        for argument in [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        ]:
            self._visit_annotation(argument.annotation)
        if arguments.vararg is not None:
            self._visit_annotation(arguments.vararg.annotation)
        if arguments.kwarg is not None:
            self._visit_annotation(arguments.kwarg.annotation)
        for default in [*arguments.defaults, *arguments.kw_defaults]:
            if default is not None:
                self.visit(default)

    def _apply_deferred_class_bindings(
        self,
    ) -> list[tuple[_Scope, str, bool, _Provenance]]:
        saved: list[tuple[_Scope, str, bool, _Provenance]] = []
        for scope, name, resolved in self._deferred_class_bindings:
            saved.append((scope, name, name in scope.symbols, scope.symbols.get(name, _UNRESOLVED)))
            scope.symbols[name] = resolved
        return saved

    @staticmethod
    def _restore_deferred_class_bindings(
        saved: list[tuple[_Scope, str, bool, _Provenance]],
    ) -> None:
        for scope, name, existed, resolved in reversed(saved):
            if existed:
                scope.symbols[name] = resolved
            else:
                scope.symbols.pop(name, None)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        symbol = f"{self._module_name}.{node.name}"
        owned = self._scope.kind == "module" and symbol in _FORBIDDEN_SYMBOLS
        resolved = frozenset({symbol}) if owned else _UNRESOLVED
        outer_scope = self._scope
        self._classes.append(node.name)
        self._scopes.append(_Scope(kind="class", symbols={}))
        self._deferred_class_bindings.append((outer_scope, node.name, resolved))
        for statement in node.body:
            self.visit(statement)
        self._deferred_class_bindings.pop()
        self._scopes.pop()
        self._classes.pop()
        self._bind(node.name, resolved)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_arguments(node.args)
        self._visit_annotation(node.returns)
        self._bind(node.name, _UNRESOLVED)
        self._functions.append(node.name)
        saved = self._apply_deferred_class_bindings()
        self._scopes.append(_function_scope(node))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()
        self._restore_deferred_class_bindings(saved)
        self._functions.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_arguments(node.args)
        self._lambda_depth += 1
        saved = self._apply_deferred_class_bindings()
        self._scopes.append(_lambda_scope(node))
        self.visit(node.body)
        self._scopes.pop()
        self._restore_deferred_class_bindings(saved)
        self._lambda_depth -= 1

    def _bind_target(self, target: ast.expr, resolved: _Provenance) -> None:
        if isinstance(target, ast.Name):
            self._bind(target.id, resolved)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind_target(element, _UNRESOLVED)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value, _UNRESOLVED)
        else:
            self.visit(target)

    def visit_Assign(self, node: ast.Assign) -> None:
        resolved = self.resolve(node.value)
        self.visit(node.value)
        for target in node.targets:
            self._bind_target(target, resolved)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            resolved = self.resolve(node.value)
            self.visit(node.value)
            self._bind_target(node.target, resolved)
        elif not isinstance(node.target, ast.Name):
            self.visit(node.target)
        self._visit_annotation(node.annotation)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            self._record(node.target, self.resolve(node.target), direct_call=False)
            self._bind(node.target.id, _UNRESOLVED)
        else:
            self.visit(node.target)
        self.visit(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._bind_target(target, _UNRESOLVED)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        resolved = self.resolve(node.value)
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            for scope in reversed(self._scopes):
                if scope.kind != "comprehension":
                    scope.symbols[node.target.id] = resolved
                    break

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record(node, self.resolve(node), direct_call=False)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if not self._record(node, self.resolve(node), direct_call=False):
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved_func = self.resolve(node.func)
        if not self._record(node.func, resolved_func, direct_call=True):
            resolved_value = self.resolve(node)
            if not self._record(node, resolved_value, direct_call=False):
                self.visit(node.func)
        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def _snapshot(self) -> dict[str, _Provenance]:
        return dict(self._scope.symbols)

    def _restore(self, symbols: dict[str, _Provenance]) -> None:
        self._scope.symbols = dict(symbols)

    @staticmethod
    def _merge(*states: dict[str, _Provenance]) -> dict[str, _Provenance]:
        names = set().union(*(state.keys() for state in states))
        return {
            name: frozenset().union(*(state.get(name, _UNRESOLVED) for state in states))
            for name in names
        }

    def _visit_statements(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self.visit(statement)

    def _visit_statements_with_states(
        self, statements: list[ast.stmt]
    ) -> list[dict[str, _Provenance]]:
        states = [self._snapshot()]
        for statement in statements:
            self.visit(statement)
            states.append(self._snapshot())
        return states

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        base = self._snapshot()
        self._visit_statements(node.body)
        body = self._snapshot()
        self._restore(base)
        self._visit_statements(node.orelse)
        orelse = self._snapshot()
        self._restore(self._merge(body, orelse))

    def _visit_try(self, node: ast.Try | ast.TryStar) -> None:
        base = self._snapshot()
        try_states = self._visit_statements_with_states(node.body)
        body = self._snapshot()
        self._visit_statements(node.orelse)
        paths = [self._snapshot()]
        for handler in node.handlers:
            self._restore(self._merge(base, body, *try_states))
            if handler.type is not None:
                self.visit(handler.type)
            if handler.name is not None:
                self._bind(handler.name, _UNRESOLVED)
            self._visit_statements(handler.body)
            paths.append(self._snapshot())
        self._restore(self._merge(*paths))
        self._visit_statements(node.finalbody)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._visit_try(node)

    def _bind_pattern(self, pattern: ast.pattern) -> None:
        for item in ast.walk(pattern):
            if isinstance(item, (ast.MatchAs, ast.MatchStar)) and item.name is not None:
                self._bind(item.name, _UNRESOLVED)
            elif isinstance(item, ast.MatchMapping) and item.rest is not None:
                self._bind(item.rest, _UNRESOLVED)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        base = self._snapshot()
        paths = [base]
        for case in node.cases:
            self._restore(base)
            self.visit(case.pattern)
            self._bind_pattern(case.pattern)
            if case.guard is not None:
                self.visit(case.guard)
            self._visit_statements(case.body)
            paths.append(self._snapshot())
        self._restore(self._merge(*paths))

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        base = self._snapshot()
        self._bind_target(node.target, _UNRESOLVED)
        body_states = self._visit_statements_with_states(node.body)
        body = self._snapshot()
        body_may = self._merge(base, body, *body_states)
        self._restore(body_may)
        self._visit_statements(node.orelse)
        self._restore(self._merge(body_may, self._snapshot()))

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit_For(node)

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        base = self._snapshot()
        body_states = self._visit_statements_with_states(node.body)
        body = self._snapshot()
        body_may = self._merge(base, body, *body_states)
        self._restore(body_may)
        self._visit_statements(node.orelse)
        self._restore(self._merge(body_may, self._snapshot()))

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        values: list[ast.expr],
        *,
        deferred_body: bool = False,
    ) -> None:
        first, *remaining = generators
        self.visit(first.iter)
        saved = self._apply_deferred_class_bindings() if deferred_body else []
        local_names = frozenset(
            item.id
            for generator in generators
            for item in ast.walk(generator.target)
            if isinstance(item, ast.Name)
        )
        self._scopes.append(
            _Scope(
                kind="comprehension",
                symbols={name: _UNRESOLVED for name in local_names},
                local_names=local_names,
            )
        )
        self._bind_target(first.target, _UNRESOLVED)
        for condition in first.ifs:
            self.visit(condition)
        for generator in remaining:
            self.visit(generator.iter)
            self._bind_target(generator.target, _UNRESOLVED)
            for condition in generator.ifs:
                self.visit(condition)
        for value in values:
            self.visit(value)
        self._scopes.pop()
        self._restore_deferred_class_bindings(saved)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, [node.elt], deferred_body=True)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, [node.key, node.value])


def _usages(
    source: str,
    *,
    module_name: str = "fixture",
) -> list[_Usage]:
    tree = ast.parse(source)
    postponed_annotations = any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and any(alias.name == "annotations" for alias in statement.names)
        for statement in tree.body
    )
    scanner = _ReferenceScanner(
        module_name=module_name,
        postponed_annotations=postponed_annotations,
    )
    scanner.visit(tree)
    return scanner.usages


def _violations(source: str) -> list[str]:
    return [f"{usage.line}:{usage.kind}" for usage in _usages(source)]


def _module_name(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(["steel_onslaught", *parts])


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
            module_name=_module_name(relative_path),
        ):
            key = (usage.function, usage.symbol)
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
        (
            "from steel_onslaught.match.evaluation_storage import "
            "SQLiteEvaluationStorageAllocator\n"
            "SQLiteEvaluationStorageAllocator(binding)"
        ),
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
        "import os\nos.getenv('LLM_API_KEY')",
        "from os import environ as environment\nvalue = environment['LLM_API_KEY']",
        "from os import getenv as read_env\nresolver = read_env\nresolver('LLM_API_KEY')",
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
        "__import__('steel_onslaught.ledger.sqlite_ledger').SQLiteLedger(cfg)",
        "import importlib\nimportlib.import_module('steel_onslaught.ledger.sqlite_ledger')",
        "globals()['SQLiteLedger'](cfg)",
        "vars(module)['SQLiteLedger'](cfg)",
    ],
)
def test_guard_detects_alias_getattr_and_higher_order_evasions(source: str) -> None:
    assert _violations(source), source


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        (
            "import steel_onslaught.ledger.sqlite_ledger\n"
            "steel_onslaught.ledger.sqlite_ledger.SQLiteLedger(cfg)\n"
        ),
        ("from steel_onslaught.ledger import sqlite_ledger\nsqlite_ledger.SQLiteLedger(cfg)\n"),
    ],
)
def test_guard_preserves_full_canonical_import_provenance(source: str) -> None:
    assert _violations(source) == ["2:SQLiteLedger"]


@pytest.mark.unit
def test_guard_resolves_relative_import_provenance() -> None:
    source = "from .ledger.sqlite_ledger import SQLiteLedger as factory\nfactory(cfg)\n"

    usages = _usages(source, module_name="steel_onslaught.fixture")
    assert [f"{usage.line}:{usage.kind}" for usage in usages] == ["2:SQLiteLedger"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        "from counterfeit import SQLiteLedger\nSQLiteLedger(cfg)\n",
        "import counterfeit.sqlite_ledger as ledger\nledger.SQLiteLedger(cfg)\n",
        "import counterfeit.sqlite_ledger as ledger\ngetattr(ledger, 'SQLiteLedger')(cfg)\n",
        "from counterfeit import uuid4\nuuid4()\n",
        "from counterfeit import datetime\ndatetime.now()\n",
        "import counterfeit.ulid as identity\nidentity.new()\n",
    ],
)
def test_wrong_module_homonyms_are_neither_forbidden_nor_approved(source: str) -> None:
    assert _violations(source) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "source, expected_line",
    [
        (
            "if enabled:\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "else:\n"
            "    factory = harmless\n"
            "factory(cfg)\n",
            5,
        ),
        (
            "try:\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "except Exception:\n"
            "    factory = harmless\n"
            "factory(cfg)\n",
            5,
        ),
        (
            "factory = harmless\n"
            "try:\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "    risky()\n"
            "    factory = harmless\n"
            "except Exception:\n"
            "    pass\n"
            "factory(cfg)\n",
            8,
        ),
        (
            "match value:\n"
            "    case 1:\n"
            "        from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "    case _:\n"
            "        factory = harmless\n"
            "factory(cfg)\n",
            6,
        ),
        (
            "factory = harmless\n"
            "for item in items:\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "factory(cfg)\n",
            4,
        ),
        (
            "factory = harmless\n"
            "while enabled:\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "factory(cfg)\n",
            4,
        ),
        (
            "factory = harmless\n"
            "for item in items:\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "    if stop:\n"
            "        break\n"
            "    factory = harmless\n"
            "factory(cfg)\n",
            7,
        ),
    ],
)
def test_module_control_flow_joins_may_provenance(source: str, expected_line: int) -> None:
    assert _violations(source) == [f"{expected_line}:SQLiteLedger"]


@pytest.mark.unit
def test_unconditional_module_rebinding_clears_branch_may_provenance() -> None:
    source = (
        "if enabled:\n"
        "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
        "factory = harmless\n"
        "factory(cfg)\n"
    )

    assert _violations(source) == []


@pytest.mark.unit
def test_comprehension_scope_shadows_iteration_parameters() -> None:
    source = (
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
        "instances = [SQLiteLedger() for SQLiteLedger in factories]\n"
    )

    assert _violations(source) == []


@pytest.mark.unit
def test_comprehension_closure_preserves_canonical_provenance() -> None:
    source = (
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
        "instances = [SQLiteLedger(config) for config in configs]\n"
    )

    assert _violations(source) == ["2:SQLiteLedger"]


@pytest.mark.unit
def test_evaluated_annotations_are_scanned_in_the_enclosing_scope() -> None:
    source = (
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
        "def invoke(SQLiteLedger: SQLiteLedger()):\n"
        "    return SQLiteLedger(cfg)\n"
    )

    assert _violations(source) == ["2:SQLiteLedger"]


@pytest.mark.unit
def test_postponed_annotations_are_not_runtime_constructor_references() -> None:
    source = (
        "from __future__ import annotations\n"
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
        "def invoke(SQLiteLedger: SQLiteLedger()):\n"
        "    return SQLiteLedger(cfg)\n"
    )

    assert _violations(source) == []


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
def test_function_global_override_does_not_mutate_module_scan_state() -> None:
    source = (
        "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
        "def harmless_earlier_function():\n"
        "    global SQLiteLedger\n"
        "    SQLiteLedger = harmless\n"
        "    return SQLiteLedger(cfg)\n"
        "def forbidden_later_function():\n"
        "    return SQLiteLedger(cfg)\n"
    )

    assert _violations(source) == ["7:SQLiteLedger"]


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
@pytest.mark.parametrize(
    "source, expected_line",
    [
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    instance = SQLiteLedger(cfg)\n",
            3,
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    def build(factory=SQLiteLedger(cfg)):\n"
            "        return factory\n",
            3,
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    stream = (item for item in SQLiteLedger(cfg))\n",
            3,
        ),
    ],
)
def test_class_body_evaluation_sees_the_preexisting_outer_binding(
    source: str, expected_line: int
) -> None:
    assert _violations(source) == [f"{expected_line}:SQLiteLedger"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    def build():\n"
            "        return SQLiteLedger(cfg)\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    build = lambda: SQLiteLedger(cfg)\n"
        ),
        (
            "from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger\n"
            "class SQLiteLedger:\n"
            "    stream = (SQLiteLedger(cfg) for cfg in configs)\n"
        ),
    ],
)
def test_class_method_and_lambda_closures_see_the_final_class_binding(
    source: str,
) -> None:
    assert _violations(source) == []


@pytest.mark.unit
def test_owned_class_method_closure_retains_canonical_identity() -> None:
    source = (
        "class SystemClock:\n    @classmethod\n    def build(cls):\n        return SystemClock()\n"
    )

    assert [
        usage.symbol
        for usage in _usages(
            source,
            module_name="steel_onslaught.match.composition",
        )
    ] == ["steel_onslaught.match.composition.SystemClock"]


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
        module_name="steel_onslaught.match.composition",
    ) == [
        _Usage(
            line=4,
            symbol="steel_onslaught.match.composition.SystemClock",
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
        (
            "def outer():\n"
            "    from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger as factory\n"
            "    def inner():\n"
            "        nonlocal factory\n"
            "        return factory(cfg)\n"
            "    return inner\n",
            5,
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
    key = (
        "build_runtime_dependencies",
        "steel_onslaught.match.composition.SystemClock",
    )
    observed = Counter(
        (usage.function, usage.symbol)
        for usage in _usages(source)
        if usage.direct_call and not usage.in_lambda
    )

    assert observed == Counter({key: 2})
    assert _budget_mismatch(observed, Counter({key: 1})) is not None


@pytest.mark.unit
def test_wrong_module_homonym_cannot_satisfy_an_approved_budget() -> None:
    source = (
        "from counterfeit import SystemClock\n"
        "def build_runtime_dependencies():\n"
        "    return SystemClock()\n"
    )
    expected = Counter(
        {
            (
                "build_runtime_dependencies",
                "steel_onslaught.match.composition.SystemClock",
            ): 1
        }
    )
    observed = Counter(
        (usage.function, usage.symbol)
        for usage in _usages(source)
        if usage.direct_call and not usage.in_lambda
    )

    assert observed == Counter()
    assert _budget_mismatch(observed, expected) is not None


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


@pytest.mark.unit
def test_duel_executor_routes_both_stores_through_injected_atomic_claim() -> None:
    source = _ROOT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_duel_executor_with_dependencies"
    )
    execute = next(
        node
        for node in factory.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute"
    )

    claim_assignments = [
        node
        for node in execute.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "claim" for target in node.targets)
    ]
    assert len(claim_assignments) == 1
    assert ast.unparse(claim_assignments[0].value) == "evaluation_storage.claim(storage)"

    binding_updates: dict[str, ast.Dict] = {}
    for node in execute.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {
            "ledger_binding",
            "leaderboard_binding",
        }:
            continue
        assert isinstance(node.value, ast.Call)
        update = next(keyword.value for keyword in node.value.keywords if keyword.arg == "update")
        assert isinstance(update, ast.Dict)
        binding_updates[target.id] = update

    assert set(binding_updates) == {"ledger_binding", "leaderboard_binding"}
    for update in binding_updates.values():
        path_values = [
            value
            for key, value in zip(update.keys, update.values, strict=True)
            if isinstance(key, ast.Constant) and key.value == "path"
        ]
        assert len(path_values) == 1
        assert ast.unparse(path_values[0]) == "claim.path"

    forbidden_inner_calls = {
        node.func.attr
        for node in ast.walk(execute)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"exists", "mkdir", "open"}
    }
    assert forbidden_inner_calls == set()
    assert (
        sum(
            1
            for node in ast.walk(execute)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_runtime_dependencies"
        )
        == 1
    )
