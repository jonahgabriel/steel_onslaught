from __future__ import annotations

from collections.abc import Mapping, Sequence

from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.learning.protocols import ModelSOSeedOutcome


class FakeEvaluator:
    """Deterministic, table-driven EvaluatorProtocol double.

    Outcomes are scripted per seed at construction. Unscripted seeds raise
    KeyError (fail fast — no silent defaults). Parameters are accepted but
    ignored: the double scripts outcomes; it does not simulate matches.
    """

    def __init__(self, script: Mapping[int, ModelSOSeedOutcome]) -> None:
        for seed, outcome in script.items():
            if outcome.seed != seed:
                raise ValueError(f"script key {seed} != outcome.seed {outcome.seed}")
        self._script = dict(script)

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        missing = [s for s in seeds if s not in self._script]
        if missing:
            raise KeyError(f"unscripted seeds: {missing}")
        return [self._script[s] for s in seeds]
