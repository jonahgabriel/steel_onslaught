# Steel Onslaught Learning Loop — Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Routing: 4 parallel agents (tasks are file-disjoint by construction). Linear: NOT required (personal repo, local mode if launched).

> **Phase 1 is parallel-safe against the in-flight MVP build: NEW FILES ONLY** under `src/steel_onslaught/learning/` and `tests/learning/` plus `src/steel_onslaught/contracts/lineage.py`. Verified unclaimed: the MVP plan's 34 task file lists claim `contracts/{chassis,boiler,weapon,sensor,gizmo,mode,loadout,budget}.py` and nothing under `learning/`; the tunable-pilots plan's 6 tasks claim `contracts/{pilot,pilot_registry}.py` and nothing under `learning/`; the in-flight branch tree (`origin/jonah/steel-onslaught-mvp`, checked 2026-06-10 at its Task-12 head `d63486a`) contains no `learning/`, `lineage`, `stats`, `search`, or `promotion` files. Imports limited to stdlib + pydantic (tests additionally use pytest); all game-engine touchpoints behind Protocols. Branch: stacked off `jonah/steel-onslaught-mvp`; merges to `main` only after the MVP PR.

**Design authority:** `docs/plans/2026-06-10-learning-loop-design-addendum.md`. The loop's semantics (arms, statistics, gate rules, lineage/identity/decay) are normative there; this plan does not restate rationales.

**Goal:** Ship the pure-logic core of the §19 learning loop — seam protocols, lineage records with canonical spec hashing, exact-test statistics, deterministic bounded search, and the §18/§23.1 promotion gate — as four parallel, file-disjoint, fully-tested tasks with zero dependency on in-flight MVP code beyond the package skeleton.

**Tech stack:** unchanged from the MVP plan (Python 3.13, uv, ruff, mypy --strict, pytest with unit/integration/slow markers, Pydantic v2). No PyYAML, no SQLite, no Click in Phase 1 — runtime imports are stdlib + pydantic only.

**Architectural Decisions (FIXED for this plan):**

1. **Task 1 is the seam; its sources are inlined verbatim.** `learning/protocols.py`, `contracts/lineage.py`, and `learning/fake_evaluator.py` are small and specified in this plan as **exact code, not sketches**. Tasks 2–4 import only those Task-1 modules (plus their own); they never import each other. This is what makes 4-way parallelism real: every shared type is frozen in this document before any agent starts.
2. **Parallel execution protocol.** Each task owns a disjoint file set; no task creates or modifies a file owned by another. Tasks 2–4 need Task 1's files present to *run* tests: if executing in parallel before Task 1's commit lands, materialize the Task-1 files byte-identically from this plan in your working tree but **commit only your own task's files** (identical bytes merge cleanly; divergent bytes are a plan violation, not a merge problem to solve).
3. **Pure and deterministic.** No I/O, no wall-clock, no global random state, no `datetime`, no event emission anywhere in Phase 1. The only randomness is `random.Random(seed)` inside `random_restart`. No `@dataclass` (plain classes or frozen Pydantic models).
4. **The gate consumes precomputed inputs.** `evaluate_promotion` takes a `ModelSOPairedComparison` (Task 2's output type, defined in Task 1's protocols) plus raw outcomes — it cross-checks them for consistency but never calls `stats.py`. Composition of search → evaluate → stats → gate is the Phase 2 loop driver, not Phase 1.
5. **Fail-fast vs verdict.** Harness bugs (out-of-bounds candidate, overlapping search/holdout seeds, comparison/outcome mismatch, off-lattice hill-climb start) **raise**. Only §18/§23.1 minting-rule failures become `rejected` verdicts with reasons.
6. **Statistics are stdlib-exact.** `math.comb` for the sign test, closed-form Wilson interval. Known-value vectors are pinned from verified arithmetic, including the June 8 platform vector: 14/2/34 ties-excluded → two-sided exact p = 274/65536 = **0.004180908203125** (the published "p = 0.0042" is this value rounded; the arithmetic was re-verified for this plan).

---

## Known Types Inventory

> Net-new types introduced by this plan, all namespaced `ModelSO*` / `SO*`:
> `ParamValue`, `ParamDict`, `spec_hash`, `meta_hash`, `SOPromotionStatus`, `SOPromotionRejection`, `ModelSOLineageEvidence`, `ModelSOLineagePerformance`, `ModelSOLineageGenerator`, `ModelSOLineagePromotion`, `ModelSOLineageRecord` (Task 1, `contracts/lineage.py`); `ModelSONumericBound`, `ModelSOCategoricalBound`, `BoundsDict`, `SpecLike`, `SOSeedWinner`, `ModelSOSeedOutcome`, `ModelSOPairedComparison`, `EvaluatorProtocol` (Task 1, `learning/protocols.py`); `FakeEvaluator` (Task 1); `exact_binomial_sign_test`, `wilson_interval`, `paired_comparison` (Task 2); `lattice_values`, `iter_grid`, `hill_climb_neighbors`, `random_restart` (Task 3); `ModelSOPromotionThresholds`, `param_distance`, `evaluate_promotion` (Task 4).
>
> Consumed from the merged MVP skeleton: nothing except the installed package itself (`pyproject.toml`, `src/steel_onslaught/__init__.py`, `src/steel_onslaught/contracts/__init__.py` — all present on the stacked base branch). `ModelSOPilotSpec` (tunable-pilots Task 1) is deliberately NOT imported — Phase 1 sees pilot specs only through the `SpecLike`/`ParamDict` seam; the adapter is Phase 2.
>
> R7 Type Duplication: no prior `ModelSOLineage*`, stats, search, or promotion types exist on any branch (verified via `git ls-tree` of `origin/jonah/steel-onslaught-mvp` and both prior plans' file lists). `ModelSOLineageRecord` intentionally implements design §18.2, which no other task claims.

## Runtime State Inventory

> No SQLite tables, no migrations, no topics, no consumer groups, no events, no files written. Phase 1 is pure in-memory logic; lineage persistence (YAML under `contracts_data/lineage/`) is Phase 2.

---

## Task 1: Seam protocols + lineage record + canonical hashing + fake evaluator

**Files:**
- Create: `src/steel_onslaught/learning/__init__.py` (empty)
- Create: `src/steel_onslaught/learning/protocols.py`
- Create: `src/steel_onslaught/learning/fake_evaluator.py`
- Create: `src/steel_onslaught/contracts/lineage.py`
- Create: `tests/learning/__init__.py` (empty)
- Create: `tests/learning/test_protocols.py`
- Create: `tests/learning/test_lineage.py`

The three source modules are normative, byte-for-byte (docstrings may be lightly edited; signatures, field names, types, bounds, validators, and behavior may not):

**`src/steel_onslaught/contracts/lineage.py`:**

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ParamValue = int | float | str
ParamDict = dict[str, ParamValue]


def spec_hash(archetype: str, parameters: ParamDict) -> str:
    """Canonical content hash of a pilot spec's tunable identity.

    Identity = (archetype, parameters) serialized as canonical JSON
    (sorted keys, compact separators). A changed spec is a new identity;
    history does not transfer (design addendum section 6).
    """
    payload = {"archetype": archetype, "parameters": parameters}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def meta_hash(opponent_spec_hashes: Iterable[str]) -> str:
    """Hash of the opponent pool ('meta') a record's evidence covers."""
    blob = json.dumps(sorted(set(opponent_spec_hashes)), separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class SOPromotionStatus(StrEnum):
    PROMOTED = "promoted"
    REJECTED = "rejected"


class SOPromotionRejection(StrEnum):
    WRONG_DIRECTION = "wrong_direction"
    NOT_SIGNIFICANT = "not_significant"
    INSUFFICIENT_DECISIVE_N = "insufficient_decisive_n"
    OVERLOAD_REGRESSION = "overload_regression"
    DRAW_RATE_EXCEEDED = "draw_rate_exceeded"
    TRIVIAL_CLONE = "trivial_clone"
    HOLDOUT_REGRESSION = "holdout_regression"


class ModelSOLineageEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    search_seeds: tuple[int, ...] = Field(min_length=1)
    holdout_seeds: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _disjoint(self) -> ModelSOLineageEvidence:
        overlap = set(self.search_seeds) & set(self.holdout_seeds)
        if overlap:
            raise ValueError(f"holdout seeds overlap search seeds: {sorted(overlap)}")
        return self


class ModelSOLineagePerformance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    candidate_win_rate: float = Field(ge=0.0, le=1.0)  # decisive trials only
    win_rate_delta: float = Field(ge=-0.5, le=0.5)  # candidate_win_rate - 0.5
    overload_rate_delta: float  # candidate minus parent, per evaluated match
    draw_rate: float = Field(ge=0.0, le=1.0)  # draws / total search seeds
    p_value: float = Field(ge=0.0, le=1.0)
    decisive_n: int = Field(ge=0)


class ModelSOLineageGenerator(BaseModel):
    """Search-authority provenance (design addendum section 7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    generator_id: str = Field(min_length=1)  # e.g. "search.hill_climb"
    selection_reason: str = Field(min_length=1)
    cohort: str | None = None


class ModelSOLineagePromotion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: SOPromotionStatus
    rejection_reasons: tuple[SOPromotionRejection, ...] = ()

    @model_validator(mode="after")
    def _status_matches_reasons(self) -> ModelSOLineagePromotion:
        if self.status is SOPromotionStatus.PROMOTED and self.rejection_reasons:
            raise ValueError("promoted record cannot carry rejection reasons")
        if self.status is SOPromotionStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("rejected record must carry at least one reason")
        return self


class ModelSOLineageRecord(BaseModel):
    """Design section 18.2 lineage record + capsule-identity discipline.

    Deliberately carries no timestamp: the gate is pure; wall-clock
    attribution is added at persistence time (Phase 2), never defaulted
    inside the pure model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.lineage_record"] = "steel_onslaught.lineage_record"
    archetype: str = Field(min_length=1)
    parameters: ParamDict
    spec_hash: str = Field(min_length=64, max_length=64)
    parent_hash: str = Field(min_length=64, max_length=64)
    meta_hash: str = Field(min_length=64, max_length=64)
    evidence: ModelSOLineageEvidence
    performance: ModelSOLineagePerformance
    generator: ModelSOLineageGenerator
    promotion: ModelSOLineagePromotion

    @model_validator(mode="after")
    def _hash_consistent(self) -> ModelSOLineageRecord:
        expected = spec_hash(self.archetype, self.parameters)
        if self.spec_hash != expected:
            raise ValueError(
                "spec_hash does not match canonical hash of (archetype, parameters)"
            )
        return self
```

**`src/steel_onslaught/learning/protocols.py`:**

```python
from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from steel_onslaught.contracts.lineage import ParamDict


class ModelSONumericBound(BaseModel):
    """Inclusive numeric range quantized to a step lattice."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    minimum: float
    maximum: float
    step: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> ModelSONumericBound:
        if self.minimum > self.maximum:
            raise ValueError("minimum must be <= maximum")
        return self


class ModelSOCategoricalBound(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    choices: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> ModelSOCategoricalBound:
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("choices must be unique")
        return self


BoundsDict = dict[str, ModelSONumericBound | ModelSOCategoricalBound]


class SpecLike(Protocol):
    """Structural view of a tunable pilot spec (no game-engine import).

    Phase 2 supplies an adapter over ModelSOPilotSpec (parameters via
    model_dump, bounds derived from the parameter models' field
    constraints). Phase 1 codes only against this shape.
    """

    @property
    def archetype(self) -> str: ...

    @property
    def parameters(self) -> ParamDict: ...

    @property
    def bounds(self) -> BoundsDict: ...


class SOSeedWinner(StrEnum):
    CANDIDATE = "candidate"
    PARENT = "parent"
    DRAW = "draw"


class ModelSOSeedOutcome(BaseModel):
    """Outcome of one paired candidate-vs-parent trial on one seed."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    seed: int
    winner: SOSeedWinner
    candidate_overloads: int = Field(ge=0)
    parent_overloads: int = Field(ge=0)


class ModelSOPairedComparison(BaseModel):
    """Summary of a paired seed battery (produced by stats, consumed by the gate)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    n_seeds: int = Field(ge=0)
    candidate_wins: int = Field(ge=0)
    parent_wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    p_value: float = Field(ge=0.0, le=1.0)
    candidate_win_rate: float = Field(ge=0.0, le=1.0)  # decisive only; 0.5 if none
    ci_low: float = Field(ge=0.0, le=1.0)  # Wilson 95% on candidate_win_rate
    ci_high: float = Field(ge=0.0, le=1.0)
    effect_size: float = Field(ge=-0.5, le=0.5)  # candidate_win_rate - 0.5

    @model_validator(mode="after")
    def _consistent(self) -> ModelSOPairedComparison:
        if self.candidate_wins + self.parent_wins + self.draws != self.n_seeds:
            raise ValueError("wins + draws must equal n_seeds")
        if self.ci_low > self.ci_high:
            raise ValueError("ci_low must be <= ci_high")
        return self


class EvaluatorProtocol(Protocol):
    """Seam to the match engine. Phase 1 ships only FakeEvaluator; Phase 2
    binds the balance-harness machinery behind this exact signature."""

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        """One outcome per seed, in the given seed order."""
        ...
```

**`src/steel_onslaught/learning/fake_evaluator.py`:**

```python
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
```

**Invariants asserted by tests (Step 1):**

- `spec_hash` is deterministic and key-order-independent: hashing `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` (same archetype) yields the same 64-char lowercase hex digest.
- A changed spec is a new identity: changing any single parameter value, or the archetype, changes `spec_hash`.
- Int/float identity is value-distinct where JSON is: `{"x": 1}` and `{"x": 1.0}` serialize differently under `json.dumps` (`1` vs `1.0`) and therefore hash differently — asserted explicitly so nobody "fixes" it silently later (Phase 2's adapter must emit the exact types the spec models carry).
- `meta_hash` is order- and duplicate-insensitive: `["h1", "h2"]`, `["h2", "h1"]`, `["h1", "h2", "h1"]` all hash identically; adding a new opponent hash changes it.
- `ModelSOLineageEvidence` rejects overlapping search/holdout seeds and rejects empty seed tuples.
- `ModelSOLineagePromotion` rejects PROMOTED-with-reasons and REJECTED-without-reasons.
- `ModelSOLineageRecord` rejects a `spec_hash` that does not equal `spec_hash(archetype, parameters)`; accepts a fully-valid record and round-trips through `model_dump()` / `model_validate()` losslessly.
- `FakeEvaluator` returns scripted outcomes in seed order; raises `KeyError` on an unscripted seed; raises `ValueError` at construction when a script key disagrees with `outcome.seed`.
- `FakeEvaluator` structurally satisfies `EvaluatorProtocol` (assign to a variable annotated `EvaluatorProtocol`; mypy --strict is the enforcement).
- `ModelSOPairedComparison` rejects `candidate_wins + parent_wins + draws != n_seeds` and `ci_low > ci_high`.
- `ModelSONumericBound` rejects `minimum > maximum` and `step <= 0`; `ModelSOCategoricalBound` rejects duplicates and empties.

**Step 1: Write the failing tests** — all of the above in `tests/learning/test_lineage.py` + `tests/learning/test_protocols.py`, `@pytest.mark.unit`. Expected failure: `ModuleNotFoundError: No module named 'steel_onslaught.learning'`.

**Step 2: Verify failure** — `uv run pytest tests/learning/ -v`.

**Step 3: Implement** — the three modules exactly as printed above, plus the two empty `__init__.py` files.

**Step 4: Verify pass** — `uv run pytest tests/learning/ -v`, then `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, `uv run ruff format src/ tests/ && uv run ruff check --fix src/ tests/`, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/__init__.py src/steel_onslaught/learning/protocols.py src/steel_onslaught/learning/fake_evaluator.py src/steel_onslaught/contracts/lineage.py tests/learning/
git commit -m "feat(learning): seam protocols + lineage record + canonical spec hashing + fake evaluator"
```

---

## Task 2: Statistics — exact binomial sign test, Wilson CI, paired comparison

**Files:**
- Create: `src/steel_onslaught/learning/stats.py`
- Create: `tests/learning/test_stats.py`

**API (signatures normative; bodies are the implementer's):**

```python
def exact_binomial_sign_test(wins_a: int, wins_b: int) -> float:
    """Two-sided exact binomial sign test on tie-excluded paired wins.

    H0: P(a beats b) = 0.5. With n = wins_a + wins_b and k = max(wins_a,
    wins_b), returns min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2**n).
    n == 0 returns 1.0. Negative inputs raise ValueError. stdlib only.
    """

def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval on successes/n (default 95%). n == 0 returns
    (0.0, 1.0). successes > n or negative inputs raise ValueError.
    """

def paired_comparison(outcomes: Sequence[ModelSOSeedOutcome]) -> ModelSOPairedComparison:
    """Fold per-seed outcomes into the Task-1 summary model.

    candidate_win_rate is over decisive (non-draw) trials only; with zero
    decisive trials it is 0.5 with CI (0.0, 1.0) and p 1.0. Duplicate seeds
    raise ValueError.
    """
```

**Invariants asserted by tests (Step 1) — known-value vectors are pinned, not recomputed by the test:**

- **June 8 vector (verified arithmetic):** `exact_binomial_sign_test(14, 2) == 274 / 65536 == 0.004180908203125` (exact dyadic rational — assert with `abs tol 1e-15`). A comment in the test cites the source: the platform's 2026-06-08 context experiment reported this as "p = 0.0042" from 14 context-wins / 2 off-wins / 34 ties.
- **June 8 phase-2 vector:** `exact_binomial_sign_test(8, 0) == 0.0078125` exactly (reported as "p = 0.0078").
- Symmetry: `exact_binomial_sign_test(2, 14) == exact_binomial_sign_test(14, 2)`.
- Clamping: `exact_binomial_sign_test(1, 1) == 1.0` (raw two-sided value 1.5 clamps to 1.0); `exact_binomial_sign_test(0, 0) == 1.0`.
- Monotonicity spot-check: `exact_binomial_sign_test(10, 0) < exact_binomial_sign_test(9, 1) < exact_binomial_sign_test(6, 4)`.
- Negative input raises `ValueError`.
- `wilson_interval(14, 16)` ≈ `(0.6398, 0.9650)` within `5e-4` (verified closed-form arithmetic for z = 1.96).
- `wilson_interval(0, 10)` has `low == 0.0` exactly and `high` ≈ `0.2775` within `5e-4`; `wilson_interval(10, 10)` has `high == 1.0` within `1e-12` and is the mirror of `wilson_interval(0, 10)`.
- `wilson_interval(0, 0) == (0.0, 1.0)`; `wilson_interval(5, 3)` raises `ValueError`.
- `paired_comparison` on a 50-outcome battery of 14 candidate / 2 parent / 34 draws returns: `n_seeds == 50`, `candidate_wins == 14`, `parent_wins == 2`, `draws == 34`, `p_value == 0.004180908203125`, `candidate_win_rate == 0.875`, `effect_size == 0.375`, `(ci_low, ci_high)` ≈ `(0.6398, 0.9650)` within `5e-4`.
- `paired_comparison([])` returns `n_seeds == 0`, `p_value == 1.0`, `candidate_win_rate == 0.5`, `ci == (0.0, 1.0)`, `effect_size == 0.0`; an all-draws battery returns the same decisive statistics with `draws == n_seeds`.
- Two outcomes with the same `seed` raise `ValueError`.
- Purity static check: the source of `stats.py` imports nothing beyond `math`, `collections.abc`, and Task-1 modules (asserted by reading the module source in the test, mirroring the MVP Task 23 static-check pattern).

**Step 1: Write the failing tests** — `tests/learning/test_stats.py`, `@pytest.mark.unit`. Expected failure: `ModuleNotFoundError` / `ImportError` on `steel_onslaught.learning.stats`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_stats.py -v`.

**Step 3: Implement** — `stats.py` per the API block; `math.comb`, closed-form Wilson, no scipy, no numpy.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, ruff format + check, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/stats.py tests/learning/test_stats.py
git commit -m "feat(learning): exact binomial sign test + Wilson CI + paired comparison summary"
```

---

## Task 3: Deterministic bounded search strategies

**Files:**
- Create: `src/steel_onslaught/learning/search.py`
- Create: `tests/learning/test_search.py`

**API (signatures normative):**

```python
def lattice_values(bound: ModelSONumericBound) -> list[int | float]:
    """The quantized value lattice: minimum + k*step for k = 0, 1, ... while
    value <= maximum + 1e-9. Values rounded to 9 decimals. Emitted as int when
    minimum, maximum, and step are all integral; else float. Ascending order.
    """

def iter_grid(bounds: BoundsDict) -> Iterator[ParamDict]:
    """Full cartesian product over the lattice. Parameter names iterate in
    sorted order; numeric values ascending; categorical choices in declared
    order; the last-sorted name varies fastest. Deterministic, lazy.
    """

def hill_climb_neighbors(
    current: ParamDict, bounds: BoundsDict, step_multiplier: int = 1
) -> list[ParamDict]:
    """Single-parameter neighbors of `current`: for each numeric parameter
    (sorted name order), the lattice values `step_multiplier` indices below
    then above the current index (clamped to the lattice ends; dropped when
    clamping lands back on the current index); for each categorical
    parameter, every other choice in declared order. Each neighbor differs
    from `current` in exactly one parameter. Raises ValueError when
    `current`'s keys do not exactly match `bounds`' keys, when a numeric
    value is off-lattice (tolerance 1e-9), when a categorical value is not a
    declared choice, or when step_multiplier < 1.
    """

def random_restart(bounds: BoundsDict, seed: int) -> ParamDict:
    """Seeded full assignment on the lattice: rng = random.Random(seed); for
    each parameter in sorted name order, numeric -> rng.choice(lattice_values),
    categorical -> rng.choice(choices). No wall-clock, no global random state.
    """
```

**Test fixtures:** small synthetic bounds (e.g. one int parameter 2–6 step 2, one float parameter 0.3–0.5 step 0.1, one categorical with 2 choices) — never the full real archetype grids (the aggressive grid alone is ~10^7 points; tests must stay sub-second). One additional fixture mirrors a real tunable-pilots bound (`lock_confidence_floor` 0.3–0.95 step 0.05) to prove float-lattice integrity on real numbers.

**Invariants asserted by tests (Step 1):**

- **Determinism:** `random_restart(bounds, 42)` called twice returns equal dicts; the sequence `[random_restart(bounds, s) for s in range(10)]` is equal across two constructions; interleaving calls to the *global* `random` module between invocations does not change results (no hidden global-state dependence).
- **Bounds never violated:** every value emitted by all three strategies satisfies `minimum - 1e-9 <= v <= maximum + 1e-9` (numeric) or `v in choices` (categorical) — property-checked over the full grid of the small fixtures and over 200 random restarts.
- **Lattice integrity:** every numeric value emitted equals a `lattice_values` entry exactly (no off-lattice floats from accumulation error); `lattice_values(0.3–0.95 step 0.05)` has 14 entries, first `0.3`, last `0.95`, all distinct after 9-decimal rounding.
- **Int typing:** integral bounds emit `int` values (`type(v) is int`); float bounds emit `float`.
- `iter_grid` size equals the product of per-parameter lattice/choice sizes; first and last elements are pinned literals; output order is reproducible across calls.
- `hill_climb_neighbors` at an interior point with 2 numeric + 1 two-choice categorical yields exactly 5 neighbors, each differing from `current` in exactly one parameter; at a lattice boundary the out-of-range side is dropped (not clamped onto a duplicate); `step_multiplier=2` moves two lattice indices and clamps to the lattice end when overshooting (emitting the end value only if it differs from current).
- Off-lattice `current`, key mismatch with `bounds`, unknown categorical value, and `step_multiplier=0` each raise `ValueError`.
- **Purity static check:** the source of `search.py` contains no `import time`, no `datetime`, no `random.seed`, and no bare module-level `random.random`/`random.choice` calls — all randomness flows through `random.Random(seed)` instances (source-scan test, MVP Task 23 pattern).

**Step 1: Write the failing tests** — `tests/learning/test_search.py`, `@pytest.mark.unit`. Expected failure: `ModuleNotFoundError` on `steel_onslaught.learning.search`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_search.py -v`.

**Step 3: Implement** — index-based lattice arithmetic (compute `k`, emit `round(minimum + k * step, 9)`), `itertools.product` for the grid, `random.Random(seed)` for restarts.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, ruff format + check, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/search.py tests/learning/test_search.py
git commit -m "feat(learning): deterministic bounded search - grid, hill-climb neighbors, seeded random restart"
```

---

## Task 4: Promotion gate — design §18 minting rules + §23.1 holdout as code

**Files:**
- Create: `src/steel_onslaught/learning/promotion.py`
- Create: `tests/learning/test_promotion.py`

**API (signatures normative):**

```python
class ModelSOPromotionThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    p_value_max: float = Field(default=0.05, gt=0.0, le=1.0)
    min_decisive_n: int = Field(default=10, ge=1)  # n < 10 is exploratory (no-overclaim)
    max_overload_rate_increase: float = Field(default=0.05, ge=0.0)
    max_draw_rate: float = Field(default=0.5, ge=0.0, le=1.0)
    min_param_distance: float = Field(default=0.05, ge=0.0, le=1.0)

def param_distance(candidate: ParamDict, parent: ParamDict, bounds: BoundsDict) -> float:
    """Normalized L-infinity distance: per numeric parameter
    |c - p| / (maximum - minimum) (0.0 when maximum == minimum); per
    categorical parameter 0.0 if equal else 1.0; distance = max over
    parameters. Key sets of candidate, parent, and bounds must all match;
    mismatch raises ValueError.
    """

def evaluate_promotion(
    *,
    archetype: str,
    candidate_params: ParamDict,
    parent_params: ParamDict,
    bounds: BoundsDict,
    search_comparison: ModelSOPairedComparison,
    search_outcomes: Sequence[ModelSOSeedOutcome],
    holdout_outcomes: Sequence[ModelSOSeedOutcome],
    opponent_spec_hashes: Sequence[str],
    generator: ModelSOLineageGenerator,
    thresholds: ModelSOPromotionThresholds,
) -> ModelSOLineageRecord:
    """Apply every minting rule; emit a lineage record for EVERY verdict
    (rejections are evidence too). All failed rules are reported, not
    first-fail (MVP budget-validator style).
    """
```

**Gate semantics (each row is a test):**

| Rule (design §18 / §23.1) | Check | Rejection reason |
|---|---|---|
| improves a meaningful metric — direction | `search_comparison.candidate_wins > parent_wins` | `WRONG_DIRECTION` |
| improves a meaningful metric — significance | `search_comparison.p_value <= thresholds.p_value_max` | `NOT_SIGNIFICANT` |
| no-overclaim floor | `candidate_wins + parent_wins >= thresholds.min_decisive_n` | `INSUFFICIENT_DECISIVE_N` |
| doesn't regress — overload | overload-rate delta over search + holdout outcomes combined (`sum(candidate_overloads)/len` minus parent's) `<= max_overload_rate_increase` | `OVERLOAD_REGRESSION` |
| doesn't regress — draws | `search_comparison.draws / n_seeds <= max_draw_rate` (0-seed batteries cannot reach the gate — see fail-fast) | `DRAW_RATE_EXCEEDED` |
| isn't a trivial clone | `param_distance(candidate, parent, bounds) >= min_param_distance` | `TRIVIAL_CLONE` |
| hidden evaluation (§23.1) | candidate wins ≥ parent wins counted over `holdout_outcomes` | `HOLDOUT_REGRESSION` |
| has a clear lineage parent | structural: `parent_hash` is computed and recorded on every record | (cannot fail as a verdict; asserted on output) |
| replayable match evidence | structural: `evidence.search_seeds` / `holdout_seeds` are the outcome seed lists, in order | (asserted on output) |

**Fail-fast raises (`ValueError`, never verdicts — Architectural Decision #5):**

- candidate or parent parameters out of `bounds` (off-lattice values are allowed here — bounds are range checks at the gate; lattice discipline is the generator's job — but out-of-range or key-mismatched parameters raise);
- search and holdout outcome seed sets overlap, or either is empty;
- `search_outcomes` disagree with `search_comparison` (recomputed `candidate_wins`/`parent_wins`/`draws`/`n_seeds` must match exactly — guards against gamed or stale summary inputs);
- duplicate seeds within either outcome sequence.

**Invariants asserted by tests (Step 1):**

- **Happy path:** a **20-seed search battery of 14 candidate / 2 parent / 4 draws** (seeds 1–20, built as `ModelSOSeedOutcome` literals — same decisive 14/2 as the June 8 vector, so the same exact p-value, while keeping `draw_rate == 0.2` under the cap; `search_comparison` constructed with the Task-2-verified values `p_value=0.004180908203125`, `candidate_win_rate=0.875`, `ci=(0.6398, 0.9650)` to 4 dp, `effect_size=0.375`), a 10-seed holdout (seeds 101–110, candidate 3 / parent 1 / draws 6), distance ≥ threshold, no overload regression → `status == PROMOTED`, `rejection_reasons == ()`; `spec_hash == spec_hash(archetype, candidate_params)`; `parent_hash == spec_hash(archetype, parent_params)`; `meta_hash == meta_hash(opponent_spec_hashes)`; `evidence.search_seeds == (1, ..., 20)` and `evidence.holdout_seeds == (101, ..., 110)`; `performance` carries the comparison's p/rate/n plus computed `overload_rate_delta` and `draw_rate == 0.2`.
- Each rejection reason has a dedicated test that flips the minimum set of inputs from the happy path and asserts the targeted reason appears: direction (2/14 swap — p stays 0.00418, so the test proves direction is checked independently of significance → `WRONG_DIRECTION in reasons`), significance (6/4 decisive over 10 seeds → p = 0.7539… > 0.05, direction and n-floor pass → exactly `NOT_SIGNIFICANT`), `min_decisive_n` (9/0 decisive → p = 0.00390625 ≤ 0.05, i.e. significant, yet n = 9 < 10 → exactly `INSUFFICIENT_DECISIVE_N` — the no-overclaim floor rejects **despite** significance), overload (+0.10 delta → `OVERLOAD_REGRESSION`), draws (a 40-seed battery of 14/2/24, `draw_rate == 0.6` → exactly `DRAW_RATE_EXCEEDED`), clone (candidate == parent → `TRIVIAL_CLONE`, distance 0.0), holdout (candidate 1 / parent 3 on holdout → `HOLDOUT_REGRESSION`).
- **Multi-failure:** a candidate failing significance AND clone distance returns BOTH reasons in a single record (not first-fail).
- **Rejections emit records:** every rejection test asserts a full `ModelSOLineageRecord` with `status == REJECTED`, intact hashes, and intact evidence (rejections are §19 evidence).
- `param_distance`: identical params → 0.0; one int param moved 1 step across an 18-wide range → `1/18` within `1e-9`; categorical flip → 1.0 dominates (L∞); zero-width numeric bound contributes 0.0; key mismatch raises.
- Fail-fast: out-of-range candidate parameter raises; overlapping search/holdout seeds raise; a `search_comparison` whose `candidate_wins` disagrees with `search_outcomes` raises; duplicate seeds raise. None of these produce a `REJECTED` record.
- Thresholds model: defaults are exactly `(0.05, 10, 0.05, 0.5, 0.05)`; out-of-range threshold values are rejected by validation.
- The gate never imports `stats.py` or `search.py` (source-scan test — Architectural Decision #4: composition is Phase 2).

**Step 1: Write the failing tests** — `tests/learning/test_promotion.py`, `@pytest.mark.unit`. Expected failure: `ModuleNotFoundError` on `steel_onslaught.learning.promotion`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_promotion.py -v`.

**Step 3: Implement** — `promotion.py` per the API and semantics tables. Collect reasons in the table's order; build the record once at the end.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, ruff format + check, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/promotion.py tests/learning/test_promotion.py
git commit -m "feat(learning): promotion gate enforcing design-18 minting rules + hidden-seed holdout"
```

---

## Adversarial Self-Check

- **R1 Count Integrity:** 4 tasks stated, 4 `## Task N:` headings, designed for 4 parallel agents.
- **R2 Acceptance Criteria:** every task lists concrete invariants asserted by named tests with pinned known values; no "should work" language. The sign-test vectors were re-verified arithmetically for this plan (274/65536 = 0.004180908203125; 2/256 = 0.0078125; Wilson(14,16) ≈ (0.6398, 0.9650)) rather than copied on trust.
- **R3 Scope / file disjointness:** the four file sets are pairwise disjoint; Tasks 2–4 import Task 1's modules only, and Task 1's modules are inlined as exact code so no task waits on another to *write* code. Conflict check against the in-flight MVP build and the tunable-pilots plan performed against both plans' file lists and the live branch tree (header note).
- **R4 Integration Traps:** every consumed type names its creating file; the gate's input type (`ModelSOPairedComparison`) lives in Task 1 precisely so Tasks 2 and 4 stay independent; `SpecLike`/`EvaluatorProtocol` document their Phase 2 binders.
- **R6 Verification Soundness:** statistics are verified against externally-published platform numbers, not self-generated oracles; the gate's summary-vs-outcomes cross-check prevents trivially gamed inputs; purity is enforced by source-scan tests, not convention.
- **R7 Type Duplication:** Known Types Inventory; no `ModelSOLineage*`/stats/search/promotion prior art on any branch (verified by `git ls-tree`).
- **R8 Runtime State Grounding:** no runtime state of any kind (inventory above).
- **R9/R10:** not applicable by design — Phase 1 has no data flow past pure functions and no rendered output; the end-to-end proof (real evaluator → ledgers → lineage YAML) is Phase 2's gate, stated, not smuggled.

---

## Phase 3 Routing

```yaml
routing: parallel-dispatch
linear_required: false
auto_launch: false
notes: |
  Personal repo (jonahgabriel/steel_onslaught). Branch jonah/learning-loop-phase1
  stacks off jonah/steel-onslaught-mvp (needs the package skeleton +
  contracts/__init__.py, both already on that branch); it merges to main only
  AFTER the MVP PR merges. Tasks 1-4 are file-disjoint and parallel-safe;
  Task 1's sources are inlined verbatim in this plan so Tasks 2-4 never wait.
  Worktree convention: per-task branches under
  $OMNI_HOME/omni_worktrees/learning-loop-task-N/steel_onslaught/.
```
