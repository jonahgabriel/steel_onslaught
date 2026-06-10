# Steel Onslaught Contract-Tunable Pilots — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Routing: ticket-pipeline (single-repo, sequential). Linear: NOT required (personal repo, local mode if launched).

> **Depends on: 2026-04-30 MVP plan fully merged (branch `jonah/steel-onslaught-mvp`). Do not execute before.**
> Every task below imports types, files, and constants that the MVP plan (Tasks 14–17, 13, 27–34) creates. Executing against a partial MVP branch will fail at Step 1 of Task 1. Verify the dependency first: `git log main --oneline` must contain the MVP Task 34 commit (`feat(integration): end-to-end duel proof of life — …`) before starting.

**Design authority:** `docs/plans/2026-06-10-tunable-pilots-design-addendum.md`. All parameter names, template values, bounds, and bound rationales are normative there (§5); this plan does not restate rationales.

**Goal:** Replace the three hardcoded pilot heuristics with spec-driven interpreters of a new bounded, versioned, forkable contract kind `steel_onslaught.pilot`, with golden decision-parity against the MVP behavior, untouched Proof-of-Life results, and loadout-level resolution of tuned pilots.

**Tech stack:** unchanged from the MVP plan (Python 3.13, uv, ruff, mypy --strict, pytest with unit/integration/slow markers, Pydantic v2, PyYAML, SQLite).

**Architectural Decisions (FIXED for this plan):**

1. **Spec-driven, structure-frozen.** Each archetype's decision tree shape stays code-owned; only the constants it compares against come from `ModelSOPilotSpec.parameters`. No rule reordering, no new rules.
2. **Golden fixtures are frozen BEFORE refactoring.** For each archetype, Step 1 of its refactor task generates a JSON decisions fixture by running the *current hardcoded* pilot over a committed observation battery, and commits that fixture. The refactored spec-driven pilot is then asserted equal against the fixture — the fixture is the reference implementation, so no heuristic logic is ever duplicated into tests.
3. **Ledger identity is scoped by MVP Architectural Decisions #6/#7.** "Identical ledger" means identical canonical event sequence — `(tick, sequence_in_tick, event_type, producer_node, subject, payload)` in canonical order — excluding `event_id` (ULID, uniqueness-only) and `emitted_at` (metadata-only), exactly as the MVP's own determinism contract scopes them. CLI replay output remains byte-identical (MVP Task 28 invariant).
4. **No event schema or payload changes.** No new `SOEventType` members, no payload fields added/removed/reordered anywhere in this plan. (Spec audit embedding in `match_started` is explicitly deferred — addendum §10.)
5. **Loadout resolution order** (addendum §7): `pilot_spec_path` (player-supplied, non-null parent required) → `contracts_data/pilots/` registry by `pilot_id` → MVP archetype fallback constructed from the template spec. The fallback keeps PoL loadout YAMLs and tests byte-unchanged.
6. **Unpinned MVP constants are read, not invented.** Where the MVP plan left a constant unpinned (defensive `fire_confidence_floor` — bounded to (0.4, 0.8] by Task 16 invariants only), the template value is copied verbatim from the merged implementation at execution time, and the golden test locks it.

---

## Known Types Inventory

> Consumed from the merged MVP (all in `src/steel_onslaught/`): `ModelSOPilotObservation`, `ModelSOPilotDecision`, `PilotProtocol` (Task 14, `pilots/schemas.py`); the three hardcoded archetype pilots (Tasks 15–17, `pilots/{aggressive,defensive,predictive}.py`); `ModelSOLoadout` (Task 13, `contracts/loadout.py`); `SQLiteLedger` (Task 6), `ReplayEngine` (Task 27), `run_match` (Task 34 entrypoint), CLI group (Task 28, `cli/main.py`).
>
> Net-new types introduced by this plan, all namespaced `ModelSO*` / `steel_onslaught.pilot`: `ModelSOPilotSpec`, `ModelSOPilotLineage`, `ModelSOAggressivePilotParams`, `ModelSODefensivePilotParams`, `ModelSOPredictivePilotParams`, `SOWeaponPreference` (StrEnum), `PilotSpecRegistry` (loader, Task 5), `ModelSOBalanceMatrix` (Task 6, optional).
>
> R7 Type Duplication: the only adjacent prior art is the MVP's archetype classes themselves, which Tasks 2–4 refactor in place (same files) rather than duplicating. No `ModelSOPilot*Params` analogue exists in the MVP.

## Runtime State Inventory

> No new SQLite tables, no migrations, no topics, no consumer groups. Pilot specs are YAML contract files under `contracts_data/pilots/`, loaded at match start — the same pattern as every other `contracts_data/` kind. Task 6 (optional) writes its win-matrix to stdout/CSV, not to a database.

---

## Task 1: Pilot spec contract models + 3 template YAMLs

**Files:**
- Create: `src/steel_onslaught/contracts/pilot.py`
- Create: `contracts_data/pilots/template_aggressive.yaml`
- Create: `contracts_data/pilots/template_defensive.yaml`
- Create: `contracts_data/pilots/template_predictive.yaml`
- Create: `tests/contracts/test_pilot_spec.py`

**Models** (full field/bounds tables: addendum §4.1, §5.1–§5.3):

- `SOWeaponPreference(StrEnum)` — `HIGHEST_DAMAGE`, `LOWEST_HEAT`.
- `ModelSOPilotLineage` — `parent: str | None`, regex `^pilot\.[a-z0-9_]+\.[a-z0-9_]+$` when non-null.
- `ModelSOAggressivePilotParams` — `vent_at_heat_margin: int` (ge=2, le=20), `idle_vent_heat_threshold: int` (ge=40, le=96), `mode_switch_pressure_floor: int` (ge=0, le=60), `mode_switch_heat_ceiling: int` (ge=0, le=92), `weapon_preference: SOWeaponPreference`.
- `ModelSODefensivePilotParams` — `vent_headroom_below_redline: int` (ge=0, le=40), `fire_confidence_floor: float` (ge=0.4, le=0.95), `fire_heat_headroom: int` (ge=0, le=40), `disengage_hp_pct: int` (ge=0, le=60).
- `ModelSOPredictivePilotParams` — `lock_confidence_floor: float` (ge=0.3, le=0.95), `predicted_hit_floor: float` (ge=0.2, le=0.95), `preemptive_vent_headroom: int` (ge=0, le=30), `regen_pressure_floor: int` (ge=0, le=60).
- `ModelSOPilotSpec` — `schema_version: Literal["0.1.0"]`, `kind: Literal["steel_onslaught.pilot"]`, `id: str` (regex above), `display_name: str` (min_length=1), `archetype: Literal["aggressive", "defensive", "predictive"]`, `lineage: ModelSOPilotLineage`, `parameters: ModelSOAggressivePilotParams | ModelSODefensivePilotParams | ModelSOPredictivePilotParams`. Model validators: parameters class must match `archetype`; `lineage.parent != id`.

All models `ConfigDict(frozen=True, extra="forbid")`.

**Template YAML values** — exactly the MVP hardcoded constants (addendum §5 tables): aggressive `5 / 90 / 12 / 80 / highest_damage`; defensive `8 / <landed constant — read from the merged src/steel_onslaught/pilots/defensive.py in Step 3 and record it here in the YAML with a comment citing the source line> / 12 / 30`; predictive `0.65 / 0.55 / 5 / 30`. `lineage.parent: null` in all three.

**Invariants asserted by tests (Step 1):**

- All 3 template YAMLs load via `ModelSOPilotSpec.model_validate(yaml.safe_load(...))` without error, and round-trip through `model_dump` losslessly.
- `pilot.template.aggressive` has `vent_at_heat_margin == 5`, `idle_vent_heat_threshold == 90`, `mode_switch_pressure_floor == 12`, `mode_switch_heat_ceiling == 80`, `weapon_preference == SOWeaponPreference.HIGHEST_DAMAGE`.
- `pilot.template.predictive` has `lock_confidence_floor == 0.65` and `predicted_hit_floor == 0.55`.
- `pilot.template.defensive`'s `fire_confidence_floor` equals the module-level constant in the merged `pilots/defensive.py` (imported, not retyped — the test breaks if either side drifts).
- Out-of-bounds is rejected: `vent_at_heat_margin: 1`, `vent_at_heat_margin: 21`, `fire_confidence_floor: 0.3`, `lock_confidence_floor: 0.96` each raise `ValidationError`.
- Unknown archetype is rejected: `archetype: opportunistic` raises `ValidationError`.
- Mismatched parameters are rejected: `archetype: aggressive` with defensive parameter fields raises `ValidationError`.
- Self-parent is rejected: `id: pilot.x.y` with `lineage.parent: pilot.x.y` raises `ValidationError`.
- Unknown parameter fields are rejected (`extra="forbid"`): an aggressive spec with `vent_at_heat_margn: 5` (typo) raises `ValidationError`.
- Bad id shape is rejected: `id: pilot.UPPER.case` and `id: pilot.only_two` raise `ValidationError`.
- Null-parent census: every spec under `contracts_data/pilots/` with `lineage.parent == None` is one of the three `pilot.template.*` ids (repo-scan test; addendum §8).

**Step 1: Write the failing tests** — all of the above in `tests/contracts/test_pilot_spec.py`, `@pytest.mark.unit`. Expected failure: `ImportError: cannot import name 'ModelSOPilotSpec'`.

**Step 2: Verify failure** — `uv run pytest tests/contracts/test_pilot_spec.py -v`.

**Step 3: Implement** — `contracts/pilot.py` models per the tables above; write the three template YAMLs; read the landed defensive constant and pin it in `template_defensive.yaml` with a source-line comment.

**Step 4: Verify pass** — `uv run pytest tests/contracts/test_pilot_spec.py -v`, then `uv run mypy src/ tests/` and `uv run pytest tests/ -v` (full suite, no `-k`).

**Step 5: Commit**

```bash
git add src/steel_onslaught/contracts/pilot.py contracts_data/pilots/ tests/contracts/test_pilot_spec.py
git commit -m "feat(pilots): ModelSOPilotSpec + bounded archetype parameter models + canonical template specs"
```

---

## Task 2: Aggressive pilot refactor to spec-driven + golden parity

**Files:**
- Create: `tests/pilots/golden/observation_battery.py` (deterministic battery generator, shared by Tasks 2–4)
- Create: `tests/pilots/golden/aggressive_golden.json` (generated in Step 1, committed)
- Create: `tests/pilots/test_aggressive_golden.py`
- Modify: `src/steel_onslaught/pilots/aggressive.py`
- Modify: `tests/pilots/test_aggressive.py` (constructor now takes a spec; assertions unchanged)

**Observation battery (`observation_battery.py`):** a pure function returning a deterministic `list[ModelSOPilotObservation]` — the cartesian grid over pinned value lists chosen to cross every rule boundary in all three archetypes: heat ∈ {0, 40, 68, 72, 73, 79, 80, 88, 89, 90, 91, 92, 95, 96, 99}, pressure ∈ {0, 5, 11, 12, 13, 29, 30, 64, 90}, enemy distance ∈ {in-range, out-of-range, will-enter-range-next-tick}, lock confidence ∈ {0.3, 0.4, 0.5, 0.65, 0.7, 0.8}, predicted hit ∈ {0.5, 0.55, 0.6}, mode ∈ {recon, assault, evasion} × mode_lock {expired, held}, weapon readiness ∈ {none, one, two-equal-damage, two-unequal}, hp_percent ∈ {25, 30, 31, 100}, boiler ∈ the three shipped specs (their actual redline/rupture values). Grid size is a few thousand observations; generation must be import-order- and hash-seed-independent (no `set` iteration, no dict-order reliance).

**Step 1: Freeze the golden fixture BEFORE touching `aggressive.py`.** Add a generator entrypoint (`uv run python -m tests.pilots.golden.generate aggressive`) that instantiates the *current hardcoded* aggressive pilot, runs it over the battery, and writes `aggressive_golden.json`: a list of `{observation_index, decision: <ModelSOPilotDecision.model_dump()>}`. Commit the fixture. Then write `test_aggressive_golden.py`:

```python
@pytest.mark.unit
def test_template_spec_matches_hardcoded_golden() -> None:
    spec = load_pilot_spec("contracts_data/pilots/template_aggressive.yaml")
    pilot = AggressivePilot(spec=spec)
    battery = observation_battery()
    golden = json.loads(GOLDEN_PATH.read_text())
    assert len(golden) == len(battery)
    for entry in golden:
        obs = battery[entry["observation_index"]]
        expected = ModelSOPilotDecision.model_validate(entry["decision"])
        assert pilot.decide(obs) == expected
```

**Step 2: Verify failure** — `AggressivePilot` takes no `spec` kwarg yet: `TypeError`.

**Step 3: Implement** — refactor `AggressivePilot` to take `spec: ModelSOPilotSpec` (asserting `archetype == "aggressive"`) and read every constant from `spec.parameters`: rule 5 tolerance → `vent_at_heat_margin` (strict `>` semantics, addendum §5.1), rule 3 → `idle_vent_heat_threshold`, rule 2 → `mode_switch_pressure_floor` / `mode_switch_heat_ceiling`, rule 1 weapon sort → `weapon_preference` with the fixed lowest-id tiebreak. Delete the module-level literals. Anywhere else the MVP constructed `AggressivePilot()`, construct it from the template spec.

**Invariants asserted by tests:**

- Golden parity: the template-spec pilot reproduces the frozen hardcoded decision (full `ModelSOPilotDecision` equality, including `considered_actions` scores) for every battery observation.
- All pre-existing Task 15 invariant tests still pass with the spec-constructed pilot (fires at heat 92/rupture 100; vents at 96/100; switches to assault at pressure ≥ 12 ∧ heat ≤ 80; lowest-id tiebreak on equal damage).
- A tuned spec changes behavior where it should: with `vent_at_heat_margin: 2`, the pilot FIREs at heat 96/rupture 100 (where the template vents) and VENTs at 99.
- With `weapon_preference: lowest_heat` and two ready weapons of unequal `heat_generated`, the pilot fires the cooler one; with equal heat, the lowest-id one.
- `AggressivePilot(spec=<defensive spec>)` raises at construction.
- `grep`-style static check: no integer literals 90/12/80 remain as decision constants in `aggressive.py` (the constants live only in specs).

**Step 4: Verify pass** — golden test + full suite: `uv run pytest tests/ -v`; `uv run mypy src/ tests/`; `uv run pre-commit run --all-files`.

**Step 5: Commit**

```bash
git add src/steel_onslaught/pilots/aggressive.py tests/pilots/
git commit -m "refactor(pilots): aggressive archetype driven by pilot spec — golden parity with hardcoded constants"
```

---

## Task 3: Defensive pilot refactor to spec-driven + golden parity

**Files:**
- Create: `tests/pilots/golden/defensive_golden.json` (generated in Step 1, committed)
- Create: `tests/pilots/test_defensive_golden.py`
- Modify: `src/steel_onslaught/pilots/defensive.py`
- Modify: `tests/pilots/test_defensive.py`

**Step 1: Read the landed constant, then freeze the fixture.** First, read the actual `fire_confidence_floor` constant from the merged `defensive.py` and verify `template_defensive.yaml` (Task 1) carries it verbatim — if Task 1 recorded a different value, fix the template YAML *now and in the same commit cite the defensive.py source line*. Then generate `defensive_golden.json` from the current hardcoded pilot over the shared battery (same generator, `defensive` argument) and commit it. Write the golden test (same shape as Task 2).

**Step 2: Verify failure** — `TypeError` on `spec` kwarg.

**Step 3: Implement** — refactor `DefensivePilot` to read rule 1 → `vent_headroom_below_redline`, rule 3 confidence gate → `fire_confidence_floor`, rule 3 headroom (`redline_threshold − heat ≥ …`) → `fire_heat_headroom`, rule 4 → `disengage_hp_pct`. Rule 2 (evasion switch under sensor lock) has no tunable constant and is untouched.

**Invariants asserted by tests:**

- Golden parity over the full battery (as Task 2).
- Pre-existing Task 16 invariants pass spec-constructed: vents at heat 73/redline 80; disengages at hp 25; holds at confidence 0.4; fires at 0.8 only with headroom ≥ 12.
- Tuned spec changes behavior: with `disengage_hp_pct: 0`, the hp-25 observation no longer disengages; with `fire_confidence_floor: 0.95`, the confidence-0.8 observation no longer fires.
- `DefensivePilot(spec=<aggressive spec>)` raises at construction.
- The template YAML's `fire_confidence_floor` equals the constant the golden fixture was generated under (cross-checked via the fixture metadata header written by the generator).

**Step 4: Verify pass** — full suite, mypy, pre-commit (as Task 2).

**Step 5: Commit**

```bash
git add src/steel_onslaught/pilots/defensive.py contracts_data/pilots/template_defensive.yaml tests/pilots/
git commit -m "refactor(pilots): defensive archetype driven by pilot spec — golden parity with hardcoded constants"
```

---

## Task 4: Predictive pilot refactor to spec-driven + golden parity

**Files:**
- Create: `tests/pilots/golden/predictive_golden.json` (generated in Step 1, committed)
- Create: `tests/pilots/test_predictive_golden.py`
- Modify: `src/steel_onslaught/pilots/predictive.py`
- Modify: `tests/pilots/test_predictive.py`

**Step 1: Freeze the fixture** from the current hardcoded predictive pilot over the shared battery; commit; write the golden test (same shape as Task 2).

**Step 2: Verify failure** — `TypeError` on `spec` kwarg.

**Step 3: Implement** — refactor `PredictivePilot` to read rule 3 → `lock_confidence_floor` / `predicted_hit_floor`, rule 4 → `preemptive_vent_headroom`, rule 5 → `regen_pressure_floor`. The 3-observation linear extrapolation (rules 1–2) is structural and stays hardcoded (addendum §5.3, "Not tunable").

**Invariants asserted by tests:**

- Golden parity over the full battery (as Task 2).
- Pre-existing Task 17 invariants pass spec-constructed: holds at lock 0.5; fires at lock 0.7 + predicted hit 0.6; vents at heat ≥ redline − 5; extrapolation deterministic.
- Tuned spec changes behavior: with `lock_confidence_floor: 0.45`, the lock-0.5 observation now fires (predicted hit permitting); with `regen_pressure_floor: 0`, the pressure-29 no-threat observation no longer repositions.
- `PredictivePilot(spec=<aggressive spec>)` raises at construction.
- The extrapolation window is NOT spec-readable: `ModelSOPredictivePilotParams` has exactly the four fields listed in Task 1 (introspection test on `model_fields`).

**Step 4: Verify pass** — full suite, mypy, pre-commit.

**Step 5: Commit**

```bash
git add src/steel_onslaught/pilots/predictive.py tests/pilots/
git commit -m "refactor(pilots): predictive archetype driven by pilot spec — golden parity with hardcoded constants"
```

---

## Task 5: Loadout → spec resolution + tuned-duel end-to-end

**Files:**
- Create: `src/steel_onslaught/contracts/pilot_registry.py` (`PilotSpecRegistry`: scan `contracts_data/pilots/*.yaml`, key by spec id; `resolve(loadout) -> ModelSOPilotSpec` implementing the three-step order of Architectural Decision #5)
- Create: `contracts_data/loadouts/tuned_aggressive_hunter.yaml` (PoL blue loadout re-piloted with a tuned fork)
- Create: `contracts_data/pilots/tuned_aggressive_hot_v1.yaml` (`lineage.parent: pilot.template.aggressive`)
- Create: `tests/contracts/test_pilot_registry.py`
- Create: `tests/integration/test_tuned_duel.py`
- Modify: `src/steel_onslaught/contracts/loadout.py` (add `pilot_spec_path: str | None = None`)
- Modify: the match entrypoint's pilot construction (Task 34's `run_match` composition) to resolve via `PilotSpecRegistry`

**Step 0 (characterization, before any change):** the MVP plan does not pin *how* Task 34's entrypoint maps `pilot_id` → archetype class. Read the merged wiring first and write a characterization test asserting its current behavior for the four PoL loadouts; the registry's archetype fallback (resolution step 3) must reproduce it exactly.

**Step 1: Write the failing tests.**

Registry unit tests (`test_pilot_registry.py`, `@pytest.mark.unit`):

- Registry scans `contracts_data/pilots/` and resolves `pilot.template.aggressive` to the template spec.
- `pilot_spec_path` takes precedence; a path-loaded spec whose `id != loadout.pilot_id` raises `PilotResolutionError("spec_id_mismatch")`.
- A path-loaded spec with `lineage.parent: null` raises `PilotResolutionError("player_spec_requires_parent")` (addendum §7 rule 1 / §8).
- A `pilot_id` matching neither path nor registry falls back to archetype resolution against the characterization baseline (step 0).
- Loadouts without `pilot_spec_path` (all existing YAMLs) validate unchanged.

End-to-end (`test_tuned_duel.py`, `@pytest.mark.integration @pytest.mark.slow`):

```python
def test_tuned_pilot_diverges_explainably(tmp_path: Path) -> None:
    template_state = run_match(red=POL_RED, blue=POL_BLUE_TEMPLATE, seed=12345, ...)
    tuned_state = run_match(red=POL_RED, blue=POL_BLUE_TUNED, seed=12345, ...)
    t_events = canonical_rows(template_ledger)   # Decision #3 scoping: no event_id/emitted_at
    u_events = canonical_rows(tuned_ledger)
    div = first_divergence(t_events, u_events)
    assert div is not None, "tuned parameters must change the duel"
    assert t_events[:div] == u_events[:div]      # identical prefix
    assert t_events[div].event_type == "pilot_decision_made"
    assert t_events[div].subject.mech_id == BLUE_MECH_ID
    # the flip is exactly the tuned parameter's doing:
    assert explains_divergence(t_events[div], u_events[div], tuned_param_predicate)
```

**Invariants asserted by tests:**

- Resolution order is exactly Architectural Decision #5 (all five registry invariants above).
- The tuned duel diverges from the template duel; ledgers are identical up to the first divergence; the divergent event is a `pilot_decision_made` for the tuned mech; and the decision pair satisfies the tuned parameter's predicate (e.g. for `vent_at_heat_margin: 2`: template decision VENT, tuned decision FIRE_WEAPON, observation heat in `(rupture−5, rupture−2]`).
- **Both Proof-of-Life tests re-run UNCHANGED and green** (`uv run pytest tests/integration/test_proof_of_life.py -v` — file untouched by this plan; assert via `git diff --stat`).
- Budget validation output for a loadout is identical with and without a tuned pilot (pilot specs cost nothing on any axis — addendum §7).

**Step 2: Verify failure** — `PilotSpecRegistry` does not exist; e2e fails at import.

**Step 3: Implement.** Registry + resolution + entrypoint wiring. Then select the tuned parameter empirically: run the template duel for seed 12345, dump the blue (aggressive) mech's per-tick `(heat, pressure, decision)` trace, and pick the tuned value that provably flips at least one decision given that trace — primary candidate `vent_at_heat_margin: 2` (flips a VENT into a FIRE in the `(rupture−5, rupture−2]` heat window); if the trace shows blue's heat never enters that window, fall back to `mode_switch_pressure_floor` or `idle_vent_heat_threshold` and pick the value the trace proves divergent. Pin the chosen parameter, the divergence tick, and the trace citation in a comment in `test_tuned_duel.py`. If seed 12345's PoL outcome is a draw-free decisive victory (expected per MVP Task 34), keep it; the divergence assertion does not depend on who wins.

**Step 4: Verify pass** — `uv run pytest tests/ -v` (full suite, no `-k`), mypy, pre-commit; confirm the PoL file is untouched (`git diff --stat` shows no change to `tests/integration/test_proof_of_life.py`).

**Step 5: Commit**

```bash
git add src/steel_onslaught/contracts/pilot_registry.py src/steel_onslaught/contracts/loadout.py contracts_data/pilots/tuned_aggressive_hot_v1.yaml contracts_data/loadouts/tuned_aggressive_hunter.yaml tests/contracts/test_pilot_registry.py tests/integration/test_tuned_duel.py
git commit -m "feat(contracts,pilots): loadout pilot_id -> pilot spec resolution + tuned-duel e2e divergence proof"
```

---

## Task 6 (OPTIONAL, separable): `so balance` — round-robin win matrix

> Separable: Tasks 1–5 ship a complete feature without this. Execute only if capacity allows; skipping it does not block anything downstream.

**Rationale:** with deterministic heuristics and a tunable spec space, meta-collapse (one dominant pairing) is a real risk and currently unmeasurable. A round-robin matrix makes balance drift visible for free, using only machinery Tasks 1–5 and the MVP already provide.

**Files:**
- Create: `src/steel_onslaught/cli/balance.py` (registered on the Task 28 CLI group)
- Create: `src/steel_onslaught/projections/balance/matrix.py` (`ModelSOBalanceMatrix`: ordered pairings, per-pairing `{wins_a, wins_b, draws}`, `draw_rate`)
- Create: `tests/cli/test_balance.py`

**Behavior:** `so balance --seeds N [--csv PATH]` — enumerate all template loadout × template pilot pairings (every shipped non-proof loadout under `contracts_data/loadouts/`, re-piloted with each of the 3 template pilot specs), run every unordered pairing round-robin × N seeds (seeds `1..N`, deterministic), and emit a win-matrix table plus overall draw rate. Matches run with the standard `max_ticks` cap; draws count per MVP Task 18 semantics.

**Invariants asserted by tests:**

- Matrix shape: for L loadouts × 3 pilots = C combatant configs, the matrix has exactly C×(C−1)/2 pairing rows, and `wins_a + wins_b + draws == N` for every row.
- Determinism: two runs with `--seeds 3` produce byte-identical CSV output.
- The CLI never writes to any match ledger directory implicitly (matches run against temp ledgers).
- `--seeds 0` exits non-zero with a usage error.
- Test uses `--seeds 2` and a reduced loadout fixture set, marked `@pytest.mark.slow`.

**Step 1: Failing test** (CLI command absent). **Step 2: Verify failure.** **Step 3: Implement.** **Step 4: Full suite + mypy + pre-commit pass.**

**Step 5: Commit**

```bash
git add src/steel_onslaught/cli/balance.py src/steel_onslaught/projections/balance/ tests/cli/test_balance.py
git commit -m "feat(cli): so balance — deterministic round-robin win matrix over template pairings"
```

---

## Adversarial Self-Check

- **R1 Count Integrity:** 6 tasks stated, 6 `## Task N:` headings (Task 6 explicitly optional/separable).
- **R2 Acceptance Criteria:** every task lists concrete invariants asserted by named tests; no "should work" language. The two genuinely unpinnable facts (defensive `fire_confidence_floor`, Task 34 pilot-wiring mechanism) are handled by read-then-lock steps (Task 1/3 Step 1, Task 5 Step 0) rather than invented values.
- **R4 Integration Traps:** every consumed type names its MVP creating task (Known Types Inventory). The golden-fixture generator is created once (Task 2) and reused (Tasks 3–4).
- **R6 Verification Soundness:** golden parity uses frozen fixtures generated from the pre-refactor code — the strongest available oracle without duplicating heuristics into tests. Ledger identity is scoped to the MVP's own determinism contract (Decision #3), not overclaimed as raw byte equality of ULID-bearing rows.
- **R8 Runtime State Grounding:** no new runtime state (inventory above).
- **R9/R10:** Task 5's e2e proves the full chain (spec YAML → resolution → decisions → ledger divergence → PoL regression) with field-level assertions; no rendered-output claims are made because no UI work is in scope.

---

## Phase 3 Routing

```yaml
routing: ticket-pipeline
linear_required: false
auto_launch: false
notes: |
  Personal repo (jonahgabriel/steel_onslaught). HARD GATE: do not execute until the
  2026-04-30 MVP plan (branch jonah/steel-onslaught-mvp) is fully merged to main —
  verify the Task 34 proof-of-life commit is on main first. Tasks 1-5 sequential
  (each refactor depends on Task 1 models; Task 5 depends on Tasks 2-4). Task 6
  optional. Worktree convention: per-task branches under
  $OMNI_HOME/omni_worktrees/tunable-pilots-task-N/steel_onslaught/.
```
