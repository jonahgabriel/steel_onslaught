# Steel Onslaught Learning Loop — Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Routing: ticket-pipeline (single-repo, sequential — every task binds to the previous task's seam). Linear: NOT required (personal repo, local mode if launched).

> **HARD GATE — implementation starts only after the tunable-pilots branch lands on `main`.** Every task below imports types and machinery the tunable-pilots plan (`2026-06-10-tunable-pilots-mvp-plan.md`) creates: `ModelSOPilotSpec` + the archetype parameter models (its Task 1), loadout `pilot_spec_path` resolution via `PilotSpecRegistry` (its Task 5), and the `so balance` round-robin match-running harness (its Task 6 — the evaluator's binding target). That plan is being executed in a parallel workflow RIGHT NOW; treat its task specifications as the interface contract. Verify before starting: `src/steel_onslaught/contracts/pilot.py`, `src/steel_onslaught/contracts/pilot_registry.py`, and `src/steel_onslaught/cli/balance.py` all exist on `main`, and `uv run pytest tests/ -v` is green. **This PLAN document has no code dependency — it can merge immediately; only execution is gated.**

**Design authority:** `docs/plans/2026-06-10-learning-loop-design-addendum.md` (§4 evaluation, §5 gate, §6 lineage, §8 Phase 2 scope) over `docs/plans/2026-04-30-steel-onslaught-design.md` §18/§19/§23. The loop's semantics are normative in the addendum; this plan does not restate rationales. The Phase 1 plan (`2026-06-10-learning-loop-phase1-plan.md`) shipped the pure core this plan binds: `EvaluatorProtocol`, `SpecLike`, `FakeEvaluator`, `stats.py` (sign test + Wilson CI + `paired_comparison`), `search.py` (grid / hill-climb neighbors / seeded restart), `promotion.py` (`evaluate_promotion` gate), `contracts/lineage.py` (record + canonical hashing) — all merged in `1683fe3` (PR #4).

**Goal:** Bind the Phase 1 seams to the real game: a `DuelEvaluator` satisfying `EvaluatorProtocol` by running deterministic, seeded, side-swapped duels through the balance-harness match machinery; a `SpecLike` adapter over `ModelSOPilotSpec` with bounds derived from the parameter models (single source); the loop driver composing search → evaluate → stats → gate → record; lineage YAML persistence under `contracts_data/lineage/`; and the `so learn` CLI — with the determinism chain (identical seeds ⇒ identical win matrix ⇒ identical search trajectory ⇒ identical lineage record) and the applicable §23 anti-exploit checks proven end-to-end.

**Tech stack:** unchanged from the MVP plan (Python 3.13, uv, ruff, mypy --strict, pytest with unit/integration/slow markers, Pydantic v2, PyYAML, SQLite, Click). Phase 1's stdlib+pydantic-only restriction is lifted: Phase 2 is the binding layer and may import the game engine, PyYAML, and Click.

**Explicitly OUT of scope (Phase 3, deferred — do not smuggle any of it in):** the LLM tuner and every `llm_*` context arm of addendum §3.3, Gemini/cloud/local model routing, `attempts_to_promotion`/`cost_per_promotion` cross-arm experiments, and the `node_context_roi_compute` row-schema export of addendum §8 Phase 3. The only candidate generators in Phase 2 are the deterministic §3.2 strategies. `ModelSOLearnResult.evaluations_consumed` (Task 4) is recorded so Phase 3 has its baseline-arm floor, but no arm machinery ships here.

**Architectural Decisions (FIXED for this plan):**

1. **Read-then-bind to the landed harness.** The tunable-pilots branch is in flight; its plan pins observable behavior (deterministic round-robin duels against temp ledgers, `max_ticks` cap, MVP Task 18 draw semantics), not internal helper names. Task 2 Step 0 reads the merged Task-6 code and binds to its match-running machinery. If that machinery landed CLI-private, extract a shared helper in the same commit rather than duplicating match-invocation logic — extraction, not reimplementation.
2. **Side-swapped pairs, conservative aggregation.** Each evaluation seed = two duels with sides swapped (candidate fields red then blue; the opponent mirror-swaps). Per-seed outcome: candidate wins both duels → `CANDIDATE`; parent wins both → `PARENT`; **every other combination (split, either draw, double draw) → `DRAW`**. This pins the case addendum §4.1 left implicit (win+draw is a draw). Corollary used as a bias test: candidate params == parent params must aggregate to `DRAW` on every seed.
3. **Bounds from the parameter models; lattice steps declared once.** `BoundsDict` is derived from `ModelSO{Aggressive,Defensive,Predictive}PilotParams` field metadata (`ge`/`le`) and StrEnum choices — never retyped from the addendum tables. The tunable-pilots bounds define ranges, not steps; the search lattice step is a Phase 2 decision declared exactly once: **int parameters step 1, float parameters step 0.05** (`FLOAT_STEPS` table in the adapter, completeness-tested against `model_fields`).
4. **The determinism chain is the acceptance bar.** Identical `(master_seed, parent, strategy, budget, thresholds)` ⇒ identical seed batteries ⇒ identical per-seed duel outcomes (win matrix) ⇒ identical candidate sequence and trajectory ⇒ identical lineage record. Wall-clock enters exactly once, at persistence (`recorded_at`, injected — never `datetime.now()` defaults), and is excluded from record identity.
5. **Holdout is sacred (§23.1).** Search and holdout batteries are derived together from the master seed, disjoint by construction, both recorded in evidence. The holdout battery is consumed by exactly one evaluator call — the final gate evaluation — and never by any search step. The Phase 1 gate already raises on overlap; Task 4 additionally proves non-consumption via the evaluator call log.
6. **No live-match mutation, no schema changes (§4.5, §19).** Learning runs offline: duels execute against temp ledgers in a caller-provided workdir; the only repository write surface is `contracts_data/lineage/`. No new `SOEventType` members, no payload changes, no edits to any shipped loadout/pilot YAML. Promoted specs enter play only by being fielded in new matches — nothing in this plan auto-fields anything.
7. **Rejections are evidence; absence of a candidate is not.** The gate is called for the best direction-positive candidate even when it will fail (the rejection record is §19 evidence). If no evaluated candidate beat the parent at all, no gate call happens and `record is None` — the trajectory itself is the evidence. Never gate a candidate that lost just to manufacture a record.

---

## Known Types Inventory

> Consumed from merged code: `EvaluatorProtocol`, `SpecLike`, `BoundsDict`, `ModelSONumericBound`, `ModelSOCategoricalBound`, `ModelSOSeedOutcome`, `SOSeedWinner`, `ModelSOPairedComparison` (`learning/protocols.py`); `FakeEvaluator` (`learning/fake_evaluator.py`); `exact_binomial_sign_test`, `wilson_interval`, `paired_comparison` (`learning/stats.py`); `lattice_values`, `iter_grid`, `hill_climb_neighbors`, `random_restart` (`learning/search.py`); `ModelSOPromotionThresholds`, `param_distance`, `evaluate_promotion` (`learning/promotion.py`); `spec_hash`, `meta_hash`, `ModelSOLineageRecord` + sub-models, `ParamDict` (`contracts/lineage.py`); `run_match` (`match/runner.py`); `ReplayEngine` (`replay/engine.py`); `SQLiteLedger` (`ledger/sqlite_ledger.py`); the Click group (`cli/main.py`).
>
> Consumed from the tunable-pilots branch once landed: `ModelSOPilotSpec`, `ModelSOPilotLineage`, `ModelSO{Aggressive,Defensive,Predictive}PilotParams`, `SOWeaponPreference` (`contracts/pilot.py`); `PilotSpecRegistry` + loadout `pilot_spec_path` (`contracts/pilot_registry.py`, `contracts/loadout.py`); the `so balance` match-running machinery (`cli/balance.py`, its Task 6).
>
> Net-new types introduced by this plan: `FLOAT_STEPS`, `bounds_for_archetype`, `params_from_spec`, `spec_from_params`, `PilotSpecView` (Task 1, `learning/spec_adapter.py`); `DuelEvaluator`, `aggregate_pair` (Task 2, `learning/duel_evaluator.py`); `ModelSOPersistedLineageRecord`, `write_lineage_record`, `load_lineage_records` (Task 3, `learning/lineage_store.py`); `SOSearchStrategy` (StrEnum), `ModelSOLearnConfig`, `ModelSOTrajectoryEntry`, `ModelSOLearnResult`, `derive_seed_batteries`, `run_learning_loop` (Task 4, `learning/loop.py`); `learn_command` (Task 5, `cli/learn.py`).
>
> R7 Type Duplication: no prior `DuelEvaluator`/`Learn*`/`lineage_store` art exists on `main` (verified against the merged tree at `1683fe3`); the only `EvaluatorProtocol` implementation today is `FakeEvaluator`, which stays untouched as the unit-test double.

## Runtime State Inventory

> New on-disk state: lineage records as YAML under `contracts_data/lineage/<archetype>/<spec_hash>/<record_digest>.yaml` (Task 3), and per-evaluation temp SQLite ledgers under a caller-provided workdir (Task 2 — retained for the gate evaluation as replay evidence, disposable for search evaluations). No new SQLite tables in the match ledger schema, no migrations, no topics, no consumer groups, no event types.

---

## Task 1: `SpecLike` adapter over `ModelSOPilotSpec` — bounds from one source

**Files:**
- Create: `src/steel_onslaught/learning/spec_adapter.py`
- Create: `tests/learning/test_spec_adapter.py`

**API (signatures normative; bodies are the implementer's):**

```python
FLOAT_STEPS: dict[str, float]
"""Search-lattice step per float-typed tunable field, declared exactly once.
Phase 2 decision (Architectural Decision #3): every float parameter steps 0.05;
int parameters always step 1 and need no entry. Keyed by field name; the
completeness test pins this table against the parameter models."""

def bounds_for_archetype(archetype: str) -> BoundsDict:
    """Derive the search BoundsDict for an archetype from its ModelSO*PilotParams
    model_fields metadata: numeric fields -> ModelSONumericBound(minimum=ge,
    maximum=le, step=1 for int / FLOAT_STEPS[name] for float); StrEnum fields ->
    ModelSOCategoricalBound(choices=enum values in declaration order).
    Unknown archetype raises ValueError. NEVER retypes the addendum bounds tables.
    """

def params_from_spec(spec: ModelSOPilotSpec) -> ParamDict:
    """spec.parameters via model_dump(mode="json") shaped to ParamDict: ints stay
    int, floats stay float, enums become their str values — the exact JSON-native
    types Phase 1's spec_hash identity contract requires (its int-vs-float test)."""

def spec_from_params(
    *, archetype: str, params: ParamDict, spec_id: str, parent_id: str | None, display_name: str
) -> ModelSOPilotSpec:
    """Inverse construction; ValidationError propagates (bounds are the contract
    gate — an out-of-bounds candidate is a generator bug, fail fast)."""

class PilotSpecView:
    """SpecLike over a ModelSOPilotSpec: archetype/parameters/bounds properties,
    parameters via params_from_spec, bounds via bounds_for_archetype."""
    def __init__(self, spec: ModelSOPilotSpec) -> None: ...
```

**Invariants asserted by tests (Step 1):**

- `bounds_for_archetype("aggressive")` reproduces the constraints carried by `ModelSOAggressivePilotParams` itself — asserted by comparing against `model_fields` metadata programmatically, NOT against retyped literals; one spot-pin per archetype guards against silent constraint drift (e.g. aggressive `vent_at_heat_margin` → `ModelSONumericBound(minimum=2, maximum=20, step=1)`; predictive `lock_confidence_floor` → `(0.3, 0.95, 0.05)`; aggressive `weapon_preference` → choices `("highest_damage", "lowest_heat")`).
- `FLOAT_STEPS` completeness both directions: every float-typed field across the three parameter models has an entry; every entry names a float-typed field (drift in either direction fails).
- Every numeric bound's `minimum`/`maximum` lie on its own step lattice (`lattice_values(bound)` contains both) — otherwise hill-climb starts are off-lattice by construction.
- `params_from_spec` on each landed template spec yields native types: `type(v) is int` for int fields, `is float` for float fields, `is str` for the enum — and `spec_hash(archetype, params)` is stable across two calls.
- Round-trip identity: `spec_from_params(params_from_spec(spec), ...)` reproduces equal `parameters` for all three templates; `params_from_spec(spec_from_params(p))` == `p` for an in-bounds synthetic `ParamDict`.
- `spec_from_params` with an out-of-bounds value (`vent_at_heat_margin: 1`) or a wrong-archetype field set raises `ValidationError`.
- `PilotSpecView` structurally satisfies `SpecLike` (assign to a variable annotated `SpecLike`; mypy --strict enforces) and its `.bounds` values all validate as Phase 1 bound models.
- Template-spec lattices are searchable: `random_restart(bounds_for_archetype(a), seed)` and `hill_climb_neighbors(params_from_spec(template), bounds, 1)` both succeed for all three archetypes (proves the adapter's lattice and the landed template values are mutually on-lattice).

**Step 1: Write the failing tests** — `tests/learning/test_spec_adapter.py`, `@pytest.mark.unit`. Expected failure: `ModuleNotFoundError` on `steel_onslaught.learning.spec_adapter`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_spec_adapter.py -v`.

**Step 3: Implement** — introspect `model_fields` for `ge`/`le` constraints and annotation types; map StrEnum annotations to categorical bounds.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, `uv run ruff format src/ tests/ && uv run ruff check --fix src/ tests/`, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/spec_adapter.py tests/learning/test_spec_adapter.py
git commit -m "feat(learning): SpecLike adapter over ModelSOPilotSpec — bounds derived from parameter models, lattice steps declared once"
```

---

## Task 2: `DuelEvaluator` — real duels behind `EvaluatorProtocol`

**Files:**
- Create: `src/steel_onslaught/learning/duel_evaluator.py`
- Create: `tests/learning/test_duel_evaluator.py`
- Possibly modify (extraction only, Architectural Decision #1): the balance harness's match-invocation helper to be importable

**Step 0 (characterization, before any change):** read the landed tunable-pilots Task 5/6 code and write down, in a comment block at the top of `duel_evaluator.py`: (a) how a spec-fielded duel is launched (loadout `pilot_spec_path` → `PilotSpecRegistry.resolve` → pilot construction inside `run_match`), (b) which helper the balance harness uses to run one seeded pairing against a temp ledger, and (c) the registry's rule that path-resolved specs require a non-null `lineage.parent`. The evaluator binds to exactly those mechanisms.

**API (signatures normative):**

```python
def aggregate_pair(first: SOSeedWinner, second: SOSeedWinner) -> SOSeedWinner:
    """Pure pair aggregation per Architectural Decision #2: CANDIDATE+CANDIDATE
    -> CANDIDATE, PARENT+PARENT -> PARENT, all 7 other combinations -> DRAW.
    Inputs are already side-normalized (each duel's winner mapped to
    candidate/parent/draw by the caller)."""

class DuelEvaluator:
    """EvaluatorProtocol implementation that runs real deterministic duels.

    Per seed: two duels with sides swapped, candidate and parent fielding the
    SAME base loadout (chassis, boiler, modules — only pilot parameters differ).
    candidate_overloads / parent_overloads = count of BOILER_OVERLOADED ledger
    events for that side's mech, summed over the seed's two duels.
    """

    def __init__(
        self,
        *,
        archetype: str,
        base_loadout: Path,          # a shipped loadout YAML; its pilot is replaced
        workdir: Path,               # ALL ledgers/specs/loadouts materialize under here
        max_ticks: int,
        contracts_data_dir: Path | None = None,
    ) -> None: ...

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]: ...
```

**Spec materialization (pinned):** per `evaluate` call the evaluator writes, under `workdir`, two pilot spec YAMLs and two derived loadout YAMLs. The parent spec gets `lineage.parent` = the archetype's template id (`pilot.template.<archetype>` — path-resolved specs must have a non-null parent); the candidate spec gets `lineage.parent` = the parent spec's id. Derived loadouts copy the base loadout byte-for-byte except `id`, `pilot_id` (set to the materialized spec id) and `pilot_spec_path`. Spec ids embed the spec hash (e.g. `pilot.learn.cand_<first 12 hash chars>`) so ledger subjects are attributable and re-materialization is idempotent.

**Invariants asserted by tests (Step 1):**

- `aggregate_pair` full 9-case table (unit, exhaustive over `SOSeedWinner × SOSeedWinner`): exactly `(CANDIDATE, CANDIDATE) -> CANDIDATE` and `(PARENT, PARENT) -> PARENT`; the other 7 are `DRAW`.
- `DuelEvaluator` structurally satisfies `EvaluatorProtocol` (mypy-enforced assignment).
- **Determinism (integration, slow):** `evaluate(c, p, seeds)` called twice with the same 2-seed battery returns equal `ModelSOSeedOutcome` lists — identical winners AND identical overload counts (this is "identical seeds ⇒ identical win matrix" at the single-pairing level).
- **Self-pairing bias check (integration, slow):** `evaluate(p, p, seeds)` with candidate == parent params aggregates every seed to `DRAW` (the two duels of a seed are the same match with labels swapped — side-swap cancellation proven, not assumed).
- **Side swap actually happens (integration):** for one seed, the two duel ledgers show the candidate's materialized `pilot_id` on the red side in one duel and the blue side in the other (query `pilot_decision_made` subjects).
- Outcomes return in the given seed order; duplicate seeds in the input raise `ValueError`.
- **No writes outside `workdir` (§4.5 / Decision #6):** snapshot `contracts_data/` file list + hashes before and after an `evaluate`; assert unchanged. No implicit ledger directory is created (the MVP/Task-6 invariant, re-asserted here).
- An invalid base loadout (budget violation) propagates `run_match`'s validation error — no silent catch.
- Off-template parent params produce a valid materialized spec (parent chain to template id) — asserted by loading the materialized YAML through `ModelSOPilotSpec.model_validate`.

**Step 1: Write the failing tests** — `tests/learning/test_duel_evaluator.py`; pure helpers `@pytest.mark.unit`, real-duel tests `@pytest.mark.integration @pytest.mark.slow` with a small `max_ticks` and ≤2 seeds (keep CI under control). Expected failure: `ModuleNotFoundError`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_duel_evaluator.py -v`.

**Step 3: Implement** — bind per Step 0; reuse (or extract, never duplicate) the balance harness's match invocation.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, ruff format + check, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/duel_evaluator.py tests/learning/test_duel_evaluator.py
git commit -m "feat(learning): DuelEvaluator — side-swapped deterministic duels behind EvaluatorProtocol via the balance harness"
```

---

## Task 3: Lineage persistence — YAML store under `contracts_data/lineage/`

**Files:**
- Create: `src/steel_onslaught/learning/lineage_store.py`
- Create: `tests/learning/test_lineage_store.py`

**API (signatures normative):**

```python
class ModelSOPersistedLineageRecord(BaseModel):
    """Persistence envelope: the pure record plus wall-clock attribution added
    AT PERSISTENCE TIME (addendum §6 deviation note) — recorded_at is a required
    field with NO default; the clock is injected by the caller."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    record: ModelSOLineageRecord
    recorded_at: datetime  # timezone-aware required (validator); never defaulted

def record_digest(record: ModelSOLineageRecord) -> str:
    """SHA-256 over the canonical JSON (sort_keys, compact separators) of the
    INNER record only — recorded_at is excluded from identity (Decision #4)."""

def write_lineage_record(
    record: ModelSOLineageRecord, *, root: Path, recorded_at: datetime
) -> Path:
    """Write YAML to root/<archetype>/<spec_hash>/<record_digest>.yaml.
    First write wins: if the path exists, leave the file untouched and return
    the existing path (idempotent re-runs; identical inner record => identical
    path regardless of clock)."""

def load_lineage_records(root: Path) -> list[ModelSOPersistedLineageRecord]:
    """Load every record under root, sorted by (archetype, spec_hash, digest)
    — a deterministic order, no mtime reliance. Unparseable files raise."""
```

**Invariants asserted by tests (Step 1):**

- Round-trip lossless: write → load reproduces an equal `ModelSOPersistedLineageRecord` (frozen-model equality), for a promoted AND a rejected record (rejections persist too — Decision #7).
- Path scheme is exactly `root/<archetype>/<spec_hash>/<record_digest>.yaml`; `spec_hash` in the path equals `record.spec_hash`.
- `record_digest` is invariant under `recorded_at` changes and changes when any inner field changes (flip one performance field → new digest).
- First-write-wins: writing the same inner record twice with different `recorded_at` returns the same path and leaves the first file's bytes unchanged.
- A naive (timezone-unaware) `recorded_at` raises `ValidationError`.
- `load_lineage_records` ordering is deterministic across two calls and independent of write order.
- Source-scan test (MVP Task 23 pattern): `lineage_store.py` contains no `datetime.now`, no `datetime.utcnow`, no default for `recorded_at`.
- YAML loads via `yaml.safe_load` (no arbitrary-object tags).

**Step 1: Write the failing tests** — `tests/learning/test_lineage_store.py`, `@pytest.mark.unit` (tmp_path roots; no real `contracts_data/` writes in unit tests). Expected failure: `ModuleNotFoundError`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_lineage_store.py -v`.

**Step 3: Implement.**

**Step 4: Verify pass** — full suite (no `-k`), mypy, ruff, pre-commit.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/lineage_store.py tests/learning/test_lineage_store.py
git commit -m "feat(learning): lineage YAML store — spec-hash-keyed records, clock injected at persistence, first-write-wins"
```

---

## Task 4: Loop driver — search → evaluate → stats → gate → record

**Files:**
- Create: `src/steel_onslaught/learning/loop.py`
- Create: `tests/learning/test_loop.py`

This is the composition Phase 1 deliberately deferred (its Architectural Decision #4). `loop.py` is the ONLY module that imports `search.py`, `stats.py`, AND `promotion.py` together.

**API (signatures normative):**

```python
class SOSearchStrategy(StrEnum):
    GRID = "grid"
    HILL_CLIMB = "hill_climb"
    RANDOM_RESTART = "random_restart"

class ModelSOLearnConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy: SOSearchStrategy
    master_seed: int
    n_search_seeds: int = Field(ge=1)
    n_holdout_seeds: int = Field(ge=1)
    max_evaluations: int = Field(ge=2)        # >= 1 search evaluation + the gate evaluation
    step_schedule: tuple[int, ...] = (4, 2, 1)  # hill-climb coarse -> fine multipliers
    n_restarts: int = Field(default=8, ge=1)    # random_restart draws
    thresholds: ModelSOPromotionThresholds = ModelSOPromotionThresholds()

class ModelSOTrajectoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    index: int = Field(ge=0)                  # evaluation order, 0-based
    generator: ModelSOLineageGenerator        # generator_id + selection_reason (addendum §7)
    candidate_params: ParamDict
    candidate_hash: str                       # spec_hash(archetype, candidate_params)
    comparison: ModelSOPairedComparison       # vs the comparison baseline at that step

class ModelSOLearnResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    config: ModelSOLearnConfig
    archetype: str
    parent_params: ParamDict
    search_seeds: tuple[int, ...]
    holdout_seeds: tuple[int, ...]
    trajectory: tuple[ModelSOTrajectoryEntry, ...]
    evaluations_consumed: int = Field(ge=0)   # Phase 3's baseline-arm floor (attempts metric)
    record: ModelSOLineageRecord | None       # None when no candidate beat the parent (Decision #7)

def derive_seed_batteries(
    master_seed: int, n_search: int, n_holdout: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """rng = random.Random(master_seed); draw distinct ints from
    range(1, 2**31) until n_search + n_holdout unique values exist; first
    n_search are the search battery, the rest the holdout battery. Disjoint by
    construction, deterministic forever, no wall-clock."""

def run_learning_loop(
    *,
    archetype: str,
    parent_params: ParamDict,
    bounds: BoundsDict,
    evaluator: EvaluatorProtocol,
    opponent_spec_hashes: Sequence[str],
    config: ModelSOLearnConfig,
) -> ModelSOLearnResult: ...
```

**Loop semantics (pinned — each bullet is a test):**

- **Batteries:** `derive_seed_batteries(config.master_seed, ...)` once, up front. Every search-phase `evaluator.evaluate` call uses exactly the search battery; the holdout battery is used by exactly one call (the gate's), after the search terminates (Decision #5).
- **Grid:** enumerate `iter_grid(bounds)` in its canonical order, skipping the parent's own point; evaluate each vs `parent_params` until the budget leaves exactly one evaluation for the gate. Best = lowest p among direction-positive candidates (`candidate_wins > parent_wins`); ties broken by higher `candidate_win_rate`, then lexicographically smaller `candidate_hash`.
- **Hill-climb:** current ← parent. For each multiplier in `step_schedule` (coarse → fine): propose `hill_climb_neighbors(current, bounds, m)`, evaluate each vs **current** (budget permitting); move to the best neighbor that is direction-positive AND significant (`p ≤ thresholds.p_value_max`) under the same tie-break; repeat at this multiplier until no neighbor qualifies, then refine. After the schedule, if current ≠ parent, run ONE explicit current-vs-original-parent evaluation on the search battery — the gate's `search_comparison` is always candidate-vs-the-lineage-parent, never vs an intermediate (design §19 "run vs parent").
- **Random restart:** `random_restart(bounds, seed)` for `seed in range(config.master_seed, config.master_seed + n_restarts)`, dedupe identical draws and the parent's point, evaluate each vs `parent_params` (budget permitting), select as grid does.
- **Gate:** for the selected candidate, evaluate on the holdout battery, then `evaluate_promotion(...)` with the candidate's vs-parent search comparison, both outcome sets, `opponent_spec_hashes`, the trajectory entry's `generator`, and `config.thresholds`. Promoted or rejected, the record lands in the result. No direction-positive candidate ⇒ no gate call, `record is None`.
- **Provenance (addendum §7):** every trajectory entry carries `generator_id` ∈ {`search.grid`, `search.hill_climb`, `search.random_restart`} and a concrete `selection_reason` (`grid_enumeration`, `hill_climb_neighbor:<param><+/-><k>@x<multiplier>`, `random_restart:<seed>`).
- **Budget:** `evaluations_consumed` counts every `evaluator.evaluate` call including the gate's holdout call; the loop NEVER exceeds `config.max_evaluations` (asserted via a counting evaluator wrapper).

**Invariants asserted by tests (Step 1) — all unit, all via `FakeEvaluator`/scripted doubles wrapped in a call recorder:**

- `derive_seed_batteries` is deterministic (two calls equal), disjoint, correct sizes, and stable under interleaved global-`random` usage.
- **Trajectory determinism:** identical `(config, parent_params, bounds, scripted evaluator)` ⇒ two `run_learning_loop` calls return EQUAL `ModelSOLearnResult` models (full frozen-model equality — this is "identical win matrix ⇒ identical search trajectory" at the unit level).
- Holdout non-consumption: the call recorder shows holdout seeds in exactly one call, which is the last; every other call's seeds == the search battery.
- Hill-climb moves only on significant direction-positive neighbors: a script where the best neighbor has p > 0.05 produces no move at that multiplier; the final explicit candidate-vs-original-parent evaluation happens whenever current ≠ parent (asserted via the recorder).
- Grid/restart selection rule: scripts with (a) two direction-positive candidates with distinct p, (b) equal p but distinct win rates, (c) fully tied — assert lowest-p, then win-rate, then hash tie-break.
- Budget exhaustion mid-search still reserves the gate evaluation; `max_evaluations=2` with one candidate works end-to-end; the loop never exceeds the budget.
- All-losers script ⇒ `record is None`, non-empty trajectory, no holdout call (Decision #7).
- A rejected-by-gate script (e.g. direction-positive but trivial-clone distance) still yields a full rejection `ModelSOLineageRecord` in the result.
- Loop purity source-scan: `loop.py` imports no `time`/`datetime`, no global `random` calls (only `derive_seed_batteries`'s seeded `random.Random`), no I/O modules (`pathlib` allowed nowhere — persistence is the CLI's job).

**Step 1: Write the failing tests** — `tests/learning/test_loop.py`, `@pytest.mark.unit`. Expected failure: `ModuleNotFoundError`.

**Step 2: Verify failure** — `uv run pytest tests/learning/test_loop.py -v`.

**Step 3: Implement.**

**Step 4: Verify pass** — full suite (no `-k`), mypy, ruff, pre-commit.

**Step 5: Commit**

```bash
git add src/steel_onslaught/learning/loop.py tests/learning/test_loop.py
git commit -m "feat(learning): loop driver — bounded search over the spec lattice composed with stats and the promotion gate"
```

---

## Task 5: `so learn` CLI

**Files:**
- Create: `src/steel_onslaught/cli/learn.py`
- Modify: `src/steel_onslaught/cli/main.py` (one line: `main.add_command(learn_command)`)
- Create: `tests/cli/test_learn.py`

**Behavior (flags per addendum §8 Phase 2, concretized):**

```
so learn --archetype {aggressive|defensive|predictive}
         --parent PATH            # pilot spec YAML; archetype must match
         --strategy {grid|hill_climb|random_restart}
         --seeds N --holdout M    # battery sizes (derive_seed_batteries)
         --budget K               # max_evaluations
         --master-seed S
         --base-loadout PATH      # the loadout both sides field (Task 2)
         --max-ticks T
         --lineage-root PATH      # default contracts_data/lineage
         --workdir PATH           # evaluation scratch + retained gate ledgers
```

Composition (thin — `learn_command` parses, then calls one testable function `_run_learn(...) -> tuple[ModelSOLearnResult, Path | None]`): load the parent spec → `PilotSpecView` (Task 1) → `DuelEvaluator` (Task 2) → `run_learning_loop` (Task 4) → if a record exists, `write_lineage_record` with `recorded_at=datetime.now(UTC)` taken HERE, at the effect boundary — the only wall-clock read in the whole feature → print a summary: strategy, evaluations consumed, candidate hash, verdict, rejection reasons, p-value / decisive n / CI (no-overclaim format, addendum §4.3), and the record path. `opponent_spec_hashes` for the gate = the parent's spec hash (the Phase 2 meta is the parent pairing; pool-wide metas arrive with populations, Phase 3+).

**Exit codes:** 0 on any completed run — promoted, rejected, AND no-candidate (`record is None`) are all successful loop executions; rejection is evidence, not error. Non-zero only on harness errors (bad flags, archetype mismatch, missing files, gate `ValueError`s).

**Invariants asserted by tests (Step 1):**

- `--seeds 0`, `--holdout 0`, `--budget 1`, unknown `--strategy`, and a `--parent` whose archetype ≠ `--archetype` each exit non-zero with a usage/validation error (CliRunner).
- A completed rejected run exits 0 and prints every rejection reason; the summary line always carries p-value, effect size, CI, and decisive n (never a bare "better" — §4.3).
- The record path printed exists and loads via `load_lineage_records`; its `evidence` seed batteries equal the result's batteries.
- `recorded_at` in the persisted envelope is timezone-aware UTC.
- Source-scan: `learn.py` is the only module under `src/steel_onslaught/learning/`+`cli/learn.py` matching `datetime.now` (single wall-clock boundary, Decision #4).
- Smoke e2e (`@pytest.mark.integration @pytest.mark.slow`): `so learn --strategy hill_climb --seeds 2 --holdout 2 --budget 4 --max-ticks <small>` against a shipped loadout completes with exit 0 and writes either nothing (no candidate) or a loadable record — outcome-agnostic, mechanics-asserting.

**Step 1: Write the failing tests** — `tests/cli/test_learn.py`. Expected failure: no `learn` command registered.

**Step 2: Verify failure** — `uv run pytest tests/cli/test_learn.py -v`.

**Step 3: Implement.**

**Step 4: Verify pass** — full suite (no `-k`), mypy, ruff, pre-commit.

**Step 5: Commit**

```bash
git add src/steel_onslaught/cli/learn.py src/steel_onslaught/cli/main.py tests/cli/test_learn.py
git commit -m "feat(cli): so learn — bounded pilot-spec search with promotion gate, hidden-seed holdout, and lineage records"
```

---

## Task 6: End-to-end determinism chain + §23 anti-exploit proof

**Files:**
- Create: `tests/integration/test_learn_e2e.py`

One integration file proving the claims the unit tests can only prove piecewise, on REAL duels (`@pytest.mark.integration @pytest.mark.slow`, tiny batteries: 2 search seeds, 2 holdout seeds, budget ≤ 6, small `max_ticks`).

**Invariants asserted by tests (Step 1):**

- **The determinism chain (Decision #4), whole and unbroken:** run `run_learning_loop` with a `DuelEvaluator` twice from identical inputs (same master seed, parent template, strategy `hill_climb`, fixed injected `recorded_at`). Assert, in order: (1) identical seed batteries; (2) identical per-candidate outcome lists from the evaluator — the win matrix; (3) identical trajectories (full model equality); (4) identical `ModelSOLearnResult`; (5) when a record was written, byte-identical persisted YAML. Identical seeds ⇒ identical win matrix ⇒ identical search trajectory ⇒ identical record, proven on the real engine.
- **§23.1 holdout integrity on real duels:** the persisted record's `evidence.search_seeds` and `evidence.holdout_seeds` are disjoint and equal the derived batteries; mutating the harness to overlap them (direct gate call with a shared seed) raises `ValueError`, never a verdict.
- **§23 draw-farming guard live:** a synthetic pairing scripted/configured to exceed the draw-rate cap (e.g. thresholds with `max_draw_rate` set below the observed real draw rate of a self-pairing run) produces a `DRAW_RATE_EXCEEDED` rejection record — the cap fires on real-duel draw rates, not just unit vectors.
- **§23 trivial-clone guard live:** gating the parent against itself (distance 0.0) yields `TRIVIAL_CLONE` (plus `WRONG_DIRECTION` — all-draws on self-pairing per Task 2's bias invariant means no direction win), as a single multi-reason record.
- **Replay determinism (§23.1 list):** pick one retained gate-evaluation ledger; `ReplayEngine` replay of it equals the live fold result (reuse the PoL replay-validity machinery — the §21 check applied to learning evidence).
- **No live-match mutation (§4.5 / Decision #6):** snapshot `contracts_data/` before the e2e run; after it, the ONLY additions are under `contracts_data/lineage/` (when the test points `--lineage-root` there via tmp redirection, assert zero additions instead); no shipped YAML's bytes changed; `SOEventType`'s member set equals the pinned pre-plan literal set (no schema drift).
- **PoL untouched:** `tests/integration/test_proof_of_life.py` has no diff on this branch (`git diff --stat` against the merge base).

**Step 1: Write the failing tests** — `tests/integration/test_learn_e2e.py`. Expected failure: imports resolve but the chain has never been composed; before Tasks 2/4/5 land it fails at import — this task executes LAST.

**Step 2: Verify failure** — `uv run pytest tests/integration/test_learn_e2e.py -v`.

**Step 3: Implement** — test-only work; any product bug it finds is fixed in the owning module with its own regression test.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), `uv run mypy src/ tests/`, ruff format + check, `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add tests/integration/test_learn_e2e.py
git commit -m "test(learning): e2e determinism chain + section-23 anti-exploit proof for the phase-2 loop"
```

---

## Adversarial Self-Check

- **R1 Count Integrity:** 6 tasks stated, 6 `## Task N:` headings, sequential (each binds the previous task's seam; no parallel claim is made).
- **R2 Acceptance Criteria:** every task lists concrete invariants asserted by named tests; no "should work" language. The two genuinely unpinnable facts — the landed Task-6 harness's internal helper shape and the landed template constants — are handled by read-then-bind steps (Task 2 Step 0, Task 1's model-introspection tests) rather than invented.
- **R3 Scope:** zero source/test changes ship with THIS plan document; the dependency gate is explicit and verifiable (`contracts/pilot.py`, `contracts/pilot_registry.py`, `cli/balance.py` on `main`). Phase 3 exclusions are enumerated, not implied.
- **R4 Integration Traps:** every consumed type names its creating file and plan; the win+draw aggregation case, the hill-climb final re-basing vs the lineage parent, the parent-of-parent template chaining for path-resolved specs, and the recorded_at identity exclusion are pinned here precisely because they are the seams where two correct implementations would otherwise diverge.
- **R6 Verification Soundness:** determinism is proven by double-execution equality on the real engine, not by inspection; side-swap cancellation is proven by the self-pairing all-draws invariant; the gate's summary-vs-outcomes cross-check (Phase 1) plus the call-recorder holdout proof prevent gamed inputs; wall-clock is confined to one greppable boundary.
- **R7 Type Duplication:** Known Types Inventory above; the only prior `EvaluatorProtocol` implementation is `FakeEvaluator`, retained as the test double, never modified.
- **R8 Runtime State Grounding:** new state is exactly the lineage YAML tree and workdir ledgers (inventory above); no schema, topic, or event-type changes anywhere.
- **R9/R10:** the end-to-end proof (Task 6) exercises the full chain — spec YAML → adapter → real duels → ledgers → stats → gate → persisted lineage record → replay check — with field-level assertions; no rendered-output claims are made because no UI work is in scope.

---

## Phase 3 Routing

```yaml
routing: ticket-pipeline
linear_required: false
auto_launch: false
notes: |
  Personal repo (jonahgabriel/steel_onslaught). HARD GATE: do not execute until
  the tunable-pilots branch (2026-06-10-tunable-pilots-mvp-plan.md, Tasks 1-6
  including the so-balance harness) is fully merged to main — verify
  src/steel_onslaught/contracts/pilot.py, contracts/pilot_registry.py, and
  cli/balance.py exist on main and the full suite is green before Task 1.
  Tasks 1-6 sequential. The LLM tuner / context arms / Gemini / ROI row export
  are Phase 3 and excluded. Worktree convention: per-task branches under
  $OMNI_HOME/omni_worktrees/learning-phase2-task-N/steel_onslaught/.
```
