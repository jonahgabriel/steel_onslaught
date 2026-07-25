# SO-SCEN-OBJ — Objectives-Toggle Control Arm (ASYM geometry held, objectives OFF), 2026-07-25

**Verdict: OBJECTIVES-ATTRIBUTABLE per the literal pre-registered criterion (`f_obj_pooled = 1.7530 >= 0.65`) — but the criterion's parenthetical gloss "geometry <=35%" is FALSIFIED by the measurement, and that failure is the actual finding.** The pre-registration assumed the two components share the sign of the total drift. They do not. Removing objectives while holding the ASYM geometry byte-identical drove utility keep-rate **down far past** the SYM_NOOBJ reference — red 0.055249 → **0.017588**, blue 0.165746 → **0.087940**, both *below* the symmetric-arena baseline. The geometry component therefore carries the **opposite** sign (`d_geom_red = -0.014268`, `d_geom_blue = -0.035329`): objectives suppress-when-removed, geometry partially offsets, and the two axes **partially cancel**. The confounded ASYM_OBJ→SYM_NOOBJ drift the program has been quoting is a *residual of two opposing effects*, not a small single effect.

Concretely: the single-axis objectives toggle is **larger and statistically cleaner** than the two-axis contrast it was built to explain. Objectives contrast (this arm vs ASYM_OBJ) is significant for both seats — red z=-2.80, p=0.0051; blue z=-3.24, p=0.0012. Geometry contrast (this arm vs SYM_NOOBJ) reaches significance for neither — red p=0.157; blue p=0.071. The original confounded baseline pair is only marginal — red p=0.063, blue p=0.055. See the clustering caveat in §7 before weighting any of these p-values.

The decomposition identity `d_obj + d_geom == d_total` holds **exactly** for both seats (verified in exact rational arithmetic, not floating point), confirming the computation is correct — the out-of-range fraction is a real property of the data, not an arithmetic error.

`play_terminal_fraction = 29/30 = 0.9667` (29 elimination, 1 abort — codebase default gate >=0.95, PASS). Blue won **29/29** decided matches; red 0/29. `objective_scored` events: **0**, confirming the toggle landed at runtime and not merely in the contract.

**Ledger:** `.onex_state/steel_onslaught/ugate_scenobj_asym_noobj_battery_r3` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-SCEN-OBJ worktree.

**Change under test:** exactly one axis, both files additive (new, not modifications):
1. `contracts_data/arenas/foundry_60_asym_v1_noobj.yaml` — geometry copy of `contracts_data/arenas/foundry_60_asym_v1.yaml` with the 3-entry `objectives:` block and `vp_threshold: 15` removed, nothing else changed (§3).
2. `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_noobj_qwen.yaml` — the ASYM utility overlay with `contracts.arena_id` repointed and `.onex_state` path stems renamed (cosmetic only; §3b).

**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030 — matched to both baselines. Loadouts `llm_qwen35_berserker.yaml` / `qwen35/sniper_ironclad.yaml`, stock and unmodified, no dose multiplier.

**Baselines bridged:** ASYM_OBJ (`ugate_surfacing_fix_battery`, arena `foundry_60_asym_v1`, n=30 seeds 5001–5030) and SYM_NOOBJ (`ugate_qwen35_symmetric_battery`, arena `foundry_60`, n=30 seeds 5001–5030).

All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl`. The baseline constants were likewise recomputed from the two baselines' own raw ledgers at pre-registration time, not copied from their evidence docs (§8 records a discrepancy this surfaced).

---

## 0. Pre-declared hypothesis and criterion (quoted verbatim from the overlay header, committed before any battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_noobj_qwen.yaml`, commit `3b0ac4a3263b688f3d077a605ddc59053c7706ae`:

> FIXED REFERENCE CONSTANTS. Independently recomputed from the two merged n=30
> baselines (both seeds 5001-5030) at pre-registration time, from their raw
> events.sqlite3 ledgers, using the established method (dealt = utility-partition
> card count summed over each seat's hand_dealt events; programmed =
> plan_committed register slots whose card_id matches card.utility.*):
>
>   ASYM_OBJ   (ledger ugate_surfacing_fix_battery):
>       red  = 20/362 = 0.055249      blue = 60/362 = 0.165746
>   SYM_NOOBJ  (ledger ugate_qwen35_symmetric_battery):
>       red  = 23/722 = 0.031856      blue = 89/722 = 0.123269
>
>   d_total_red  = 0.055249 - 0.031856 = 0.023393   (42.34% of ASYM_OBJ_red)
>   d_total_blue = 0.165746 - 0.123269 = 0.042477   (25.63% of ASYM_OBJ_blue)
>   d_total_red + d_total_blue = 0.065870
>
> DECOMPOSITION, per seat:
>   d_obj_seat  = ASYM_OBJ_seat   - ASYM_NOOBJ_seat   (objectives effect, geometry fixed)
>   d_geom_seat = ASYM_NOOBJ_seat - SYM_NOOBJ_seat    (geometry effect, no-objectives fixed)
>
> PRIMARY STATISTIC:
>   f_obj_pooled = (d_obj_red + d_obj_blue) / 0.065870
>
> DECISION (disjunctive, exactly one criterion, no illustrative bands):
>   f_obj_pooled >= 0.65          => OBJECTIVES-ATTRIBUTABLE
>                                    (objectives toggle alone explains >=65% of
>                                    the total drift; geometry <=35%)
>   f_obj_pooled <= 0.35          => GEOMETRY-ATTRIBUTABLE
>                                    (objectives toggle explains <=35%;
>                                    geometry >=65%)
>   0.35 < f_obj_pooled < 0.65    => BOTH-CONTRIBUTE; report both components and
>                                    do NOT force a single-cause verdict.
>
> SIGN-REVERSAL ESCAPE. If d_obj_red or d_obj_blue carries the opposite sign
> from its own d_total (i.e. ASYM_NOOBJ_seat > ASYM_OBJ_seat - removing
> objectives INCREASED that seat's keep-rate), that seat is reported
> QUALITATIVELY as a sign reversal. A negative or >1 fraction is NOT folded into
> the 0-1 scale.

**Pre-registration timeline held.** Commit `3b0ac4a` at `2026-07-25T16:59:10Z`; the earliest `match_started` in *any* run of this arm — including the two discarded runs — is `2026-07-25T17:00:01Z` (r1). The scored run's first event is `2026-07-25T17:39:16Z`. The criterion, the fixed constants, and the contamination gate were all fixed before a single match was played.

### 0a. Where the pre-registration proved inadequate (stated against myself)

The criterion is written as a fraction on a 0–1 scale, which **presupposes** `d_obj` and `d_geom` both carry the sign of `d_total` — i.e. that the two axes push the same way and merely divide the total between them. The measurement violates that presupposition: `d_obj` overshoots `d_total` and `d_geom` is negative on both seats.

The pre-registered SIGN-REVERSAL escape covers only the case where **`d_obj`** reverses. It does not name the case that actually occurred, where `d_obj` keeps the expected sign and **`d_geom`** reverses. So the literal decision rule fires (`1.7530 >= 0.65` ⇒ OBJECTIVES-ATTRIBUTABLE) while the interpretation printed alongside it ("geometry <=35%") is false.

This document reports the label the pre-registered rule produces **and** states plainly that its gloss does not hold, rather than silently re-scoping the criterion after seeing the data. The directional claim the label carries — *objectives dominate; the objectives axis alone more than accounts for the observed drift* — is supported. The partition claim — *geometry takes the remaining ≤35%* — is refuted; geometry's contribution is **negative** (−75.3% pooled).

---

## Method

- **Keep-rate**, unchanged from `docs/evidence/2026-07-23-scenario-variation-qwen35-symmetric.md`: `dealt` = utility-partition card count summed over each seat's `hand_dealt` events; `programmed` = `plan_committed` register slots whose `card_id` matches `card.utility.*`; keep-rate = programmed / dealt. Recomputed directly from `events.sqlite3`.
- **Decomposition** computed in exact rational arithmetic (Python `Fraction`) so the identity check is a genuine equality test, not a float tolerance.
- **Win rate** = wins ÷ `elimination`-class terminals (aborts excluded); the all-30 basis is also reported.
- **Baseline constants** recomputed from the baselines' own raw ledgers, not read from their published docs.

---

## 1. Contamination gate

The pre-registered gate: exactly 30 `match_started` rows, 30 distinct `match_id`s, seeds 5001–5030 each exactly once.

| Check | Value | Required | Pass |
|---|---:|---|---|
| `match_started` rows | 30 | 30 | yes |
| distinct `match_started` `match_id` | 30 | 30 | yes |
| distinct `match_ended` `match_id` | 30 | 30 | yes |
| `battery_raw.jsonl` rows | 30 | 30 | yes |
| seed range | 5001–5030 | 5001–5030 | yes |
| every seed exactly once | true | true | yes |
| duplicate / gap seeds | 0 / 0 | 0 / 0 | yes |

### 1a. Two earlier runs failed this gate and were discarded UNSCORED

This is disclosed in full because a silently re-rolled battery is indistinguishable from optional stopping.

| Run | State root | `match_started` rows | completed matches | Skipped seeds | Disposition |
|---|---|---:|---:|---|---|
| r1 | `ugate_scenobj_asym_noobj_battery_r1_DISCARDED_gate_fail` | 30 | 28 | 5016, 5020 (`LlmTransportError`) | discarded, **never scored** |
| r2 | `ugate_scenobj_asym_noobj_battery_r2` | 30 | 29 | 5010 (`LlmTransportError`) | discarded, **never scored** |
| r3 | `ugate_scenobj_asym_noobj_battery_r3` | 30 | 30 | none | **scored** |

Discipline applied, and its limits:

- **The discarded runs were checked against the gate only.** No keep-rate, decomposition, or win-rate figure was computed for r1 or r2 at any point — the selection rule ("first run that passes the pre-registered gate") is blind to the quantity under test, so it cannot bias the estimate. r1's ledger is retained on disk (with its stdout log) for audit; r2's likewise.
- **The re-roll budget was bounded and declared before the re-rolls ran** (up to 4 further attempts, then report the arm as gate-failed using the run with fewest skipped seeds). r3 passed on the first of those attempts, so the fallback never engaged.
- **Honest residual:** the gate text I pre-registered is ambiguous, and I resolved the ambiguity *against* myself after seeing it fire. "Exactly 30 `match_started` rows" is literally TRUE for r1 and r2 — a seed that dies mid-match still emits `match_started`. Reading the gate literally would have passed both. I treated them as failures because the gate's *intent* is 30 complete, uncontaminated matches, and a match that died mid-play leaves truncated `hand_dealt`/`plan_committed` events in the ledger that corrupt the keep-rate denominators. A future arm should pre-register the gate against **completed** matches (`battery_raw.jsonl` row count) rather than `match_started` rows.

### 1b. Root cause of the discarded runs (not filed as "transient")

`LlmTransportError: LLM transport request failed` is raised at `src/steel_onslaught/llm/client_http.py:153` from `httpx.RequestError` — a **connection-level** failure, not an HTTP status. It is not a provider 429 and not a timeout (those map to `LlmCompletionBoundaryError`).

Probe run against the live endpoint with a long-lived `httpx.Client(trust_env=False)` — the same construction the battery uses at `src/steel_onslaught/match/composition.py:1479` — issued 69 consecutive completions at 2s spacing with **69/69 clean**, so the endpoint is not rejecting or reaping connections under sustained reuse. Combined with the observed failures being scattered across the battery window rather than clustered (r1 failed at matches 16 and 20; r2 at match 10), the signature is a **low-rate sporadic drop on the network path**, on the order of 0.5% per request across ~400 requests per battery. That yields ≈1–2 lost seeds per 30-match battery, matching what r1 and r2 produced.

This is a known, recurring class in this program, not a novelty: the battery driver's own per-seed skip handling was added on 2026-07-24 precisely because "a single such error propagated out of the loop and killed the whole battery process: the V-IMG vision arm lost 29 of 30 seeds to one 429" (`scripts/run_ogate_objectives_battery.py`). Program precedent (P1 n=29, P3 n=28, P4 n=29) is to report the achieved n rather than re-roll; this arm re-rolled instead because its pre-registered gate demanded exactly 30 and a decomposition against two n=30 baselines is cleaner at equal n. **Nothing in the engine, overlay, or loadouts was changed to obtain the clean run** — r3 used byte-identical inputs to r1 and r2.

---

## 2. Terminal health and win rate

| Metric | ASYM_NOOBJ (this arm) | ASYM_OBJ | SYM_NOOBJ |
|---|---|---|---|
| `match_started` / `match_ended` | 30 / 30 | 30 / 30 | 30 / 30 |
| Terminal-class mix | elimination 29, abort 1 | elimination 29, abort 1 | elimination 30 |
| `play_terminal_fraction` | **0.9667** (PASS, >=0.95) | 0.9667 | 1.0 |
| Winner distribution | blue 29, red 0 | blue 29, red 0 | blue 30, red 0 |
| **Decided-match red win rate** | **0/29 = 0.0000** | 0/29 = 0.0000 | 0/30 = 0.0000 |
| `mech_destroyed` | `mech.red.01` × 29 | `mech.red.01` × 29 | `mech.red.01` × 30 |
| `objective_scored` events | **0** | 2 | 0 |
| VP-threshold terminals | 0 | **0** | 0 |

The abort is seed 5008, `end_reason=provider_semantic_failure`, `failed_completions=3`, `is_draw=true` — an LLM semantic-exhaustion terminal, the same class the ASYM_OBJ baseline also carries exactly one of. `failed_completions` distribution across the 30 matches: 0 → 11, 1 → 16, 2 → 2, 3 → 1.

**Red is winless in all three corners.** Neither axis moves win rate; both move keep-rate. Win rate is not informative here and no claim is made from it.

**Objectives were present but almost never captured.** ASYM_OBJ produced only **2** `objective_scored` events across 30 matches and **zero** VP terminals — every match still ended by elimination. This matters for §6.

---

## 3. Single-axis proof — geometry held exactly constant

### 3a. Arena contract

`git diff HEAD -- contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml` returns **empty** — zero baseline files modified.

Parsed field-by-field comparison of `foundry_60_asym_v1_noobj` against `foundry_60_asym_v1`:

| Field | Status |
|---|---|
| `size` (60) | identical |
| `spawn_a` ({x:4, y:30}) | identical |
| `spawn_b` ({x:52, y:30}) | identical |
| `obstacles` (`[]`) | identical |
| `rects` (all 22 entries) | identical |
| `obstacle_cells` (derived terrain) | identical |
| `sudden_death_start_tick` (120) | identical |
| `sudden_death_damage_base` (8) | identical |
| `kind`, `schema_version` | identical |
| `objectives` | **3 entries → `()`** (the toggle) |
| `vp_threshold` | **15 → `None`** (the toggle) |
| `arena_id`, `display_name` | renamed (identity, not geometry) |

This is not a prose assertion — `tests/contracts/test_scenobj_noobj_overlay.py::test_noobj_arena_geometry_is_identical_to_asym_v1` asserts every row of that table in CI, so a future edit that moves a rect or a spawn fails the build rather than silently invalidating this decomposition.

Both removed keys default to `()` / `None` in `ModelSOArenaSpec`, which is exactly the objective-less shape `foundry_60` already has, so the toggle is purely **subtractive** and introduces zero new design decisions. The additive direction — placing objective cells onto `foundry_60`'s symmetric scatter — was rejected: cell placement there is an undesigned free choice with no precedent, i.e. a new design decision smuggled into a control.

### 3b. Overlay

Parsed-field diff against `tactical_split_overdeal_utility_asym_v1_qwen.yaml` yields exactly **7** differing leaves:

- `contracts.arena_id`: `foundry_60_asym_v1` → `foundry_60_asym_v1_noobj` — **the only functional change**;
- 6 `.onex_state/...` path stems (`event_ledger.path`, `leaderboard.path`, three `learning_artifacts` roots, `evaluation_storage.root`) — **cosmetic only**: `_lane_overlay()` in `scripts/run_ogate_objectives_battery.py` rewrites every durable path from `--state-root` before the run, so these strings never reach the runtime. They are renamed to avoid the stale-path hygiene issue the SYM overlay's own evidence doc flagged as a follow-up.

Everything the match runtime consumes is byte-equal: provider binding, retry (`max_attempts=1`), timeout, deck policy, over-deal quotas (4 movement + 4 weapon + 2 utility, 5 registers), `utility_handler_pack`, pilot registry, balance rule pack. Asserted in CI by `test_noobj_overlay_inherits_asym_provider_and_retry_verbatim` and `test_noobj_overlay_only_differs_from_asym_by_arena_binding`.

### 3c. Runtime confirmation

`objective_scored` event count on this arm: **0**. The toggle is proven at the ledger, not just in the contract.

---

## 4. Keep-rate — the measurement

Independently recomputed from `events.sqlite3`. `battery_summary.json` does not publish keep-rate fields, so the cross-check is against the raw ledger only (stated rather than claimed as an agreement that was not available).

| Corner | Seat | programmed | dealt | keep-rate | all-card keep |
|---|---|---:|---:|---:|---:|
| ASYM_OBJ | player.red | 20 | 362 | 0.055249 | 0.5000 |
| ASYM_OBJ | player.blue | 60 | 362 | 0.165746 | 0.5000 |
| SYM_NOOBJ | player.red | 23 | 722 | 0.031856 | 0.5000 |
| SYM_NOOBJ | player.blue | 89 | 722 | 0.123269 | 0.5000 |
| **ASYM_NOOBJ (this arm)** | **player.red** | **7** | **398** | **0.017588** | 0.5000 |
| **ASYM_NOOBJ (this arm)** | **player.blue** | **35** | **398** | **0.087940** | 0.5000 |

95% Wilson CI on this arm: red **[0.008545, 0.035854]**, blue **[0.063910, 0.119848]**.

All-card keep is **exactly 0.5000** in all three corners (5 registers programmed of 10 dealt) — utility-specific deprioritization is not a dealing artifact in any corner, reproducing the SYM doc's sanity check.

**This arm has the lowest keep-rate of all three corners on both seats** — below SYM_NOOBJ, which the program had been treating as the low end.

**Sub-chance deprioritization and the blue>red ordering both persist**, and the ordering *strengthens* monotonically as objectives are removed:

| Corner | red | blue | blue/red |
|---|---:|---:|---:|
| ASYM_OBJ | 0.055249 | 0.165746 | 3.00× |
| SYM_NOOBJ | 0.031856 | 0.123269 | 3.87× |
| **ASYM_NOOBJ** | **0.017588** | **0.087940** | **5.00×** |

---

## 5. Decomposition

`d_obj_seat = ASYM_OBJ_seat − ASYM_NOOBJ_seat` (objectives effect, geometry fixed); `d_geom_seat = ASYM_NOOBJ_seat − SYM_NOOBJ_seat` (geometry effect, no-objectives fixed).

| Seat | ASYM_OBJ | ASYM_NOOBJ | SYM_NOOBJ | d_obj | d_geom | d_total | identity holds |
|---|---:|---:|---:|---:|---:|---:|---|
| red | 0.055249 | 0.017588 | 0.031856 | **+0.037661** | **−0.014268** | +0.023393 | **exact** |
| blue | 0.165746 | 0.087940 | 0.123269 | **+0.077806** | **−0.035329** | +0.042477 | **exact** |

Arithmetic shown:

```
red:   d_obj  = 0.055249 - 0.017588 = +0.037661
       d_geom = 0.017588 - 0.031856 = -0.014268
       sum    = +0.037661 - 0.014268 = +0.023393  == d_total_red   (exact)
blue:  d_obj  = 0.165746 - 0.087940 = +0.077806
       d_geom = 0.087940 - 0.123269 = -0.035329
       sum    = +0.077806 - 0.035329 = +0.042477  == d_total_blue  (exact)
```

The identity is true by algebra for any measured value; it is verified here in exact rational arithmetic purely as a **computation-correctness check**, and it passes — so the out-of-range fractions below are a property of the data, not a bug.

Attribution fractions:

```
f_obj_red    = +0.037661 / 0.023393 = +1.6099      f_geom_red    = -0.6099
f_obj_blue   = +0.077806 / 0.042477 = +1.8317      f_geom_blue   = -0.8317
f_obj_pooled = (0.037661 + 0.077806) / 0.065870
             = 0.115467 / 0.065870  = +1.7530      f_geom_pooled = -0.7530
```

**Decision per the literal pre-registered rule:** `f_obj_pooled = 1.7530 >= 0.65` ⇒ **OBJECTIVES-ATTRIBUTABLE**.

**What the number actually means, stated precisely:** the objectives axis alone accounts for **175%** of the observed ASYM_OBJ→SYM_NOOBJ drift, and the geometry axis contributes **−75%** — it pushes keep-rate back *up*, cancelling part of the objectives effect. Both seats agree in sign and are close in magnitude (red 1.61, blue 1.83), so this is not one seat dragging a pooled statistic; the split between seats is modest and does not itself constitute a separate finding.

**No SIGN-REVERSAL escape is invoked** — that clause is scoped to `d_obj` reversing, and `d_obj` is positive on both seats as expected. The reversal is in `d_geom`, which the pre-registration did not contemplate (§0a).

### 5a. Sensitivity to the abort

Recomputing with the single aborted match (seed 5008) excluded: red 7/390 = 0.017949, blue 35/390 = 0.089744, **`f_obj_pooled = 1.7201`**. The verdict and every qualitative claim are unchanged. This is a post-hoc robustness check, not a redefinition of the pre-registered primary statistic.

---

## 6. Match length, and what it says about the confound

| Metric | ASYM_NOOBJ (this arm) | ASYM_OBJ | SYM_NOOBJ |
|---|---:|---:|---:|
| min ticks | 11 | 13 | 30 |
| median ticks | **28.0** | 29 | 58 |
| mean ticks | **30.30** | 28.67 | 57.23 |
| max ticks | 56 | 73 | 86 |
| rounds / match | **6.63** | 6.03 | 12.03 |
| utility cards dealt / seat | 398 | 362 | 722 |
| `utility_deploy_intent` | 36 (smoke 23, chaff 12, flares 1); blue 30 / red 6 | 72 (smoke 46, chaff 20, flares 6); blue 54 / red 18 | 101 (smoke 73, chaff 22, flares 6); blue 81 / red 20 |

Sorted durations (n=30): 11, 12, 16, 16, 21, 21, 22, 23, 23, 23, 24, 26, 26, 27, 27, 29, 29, 31, 36, 36, 36, 36, 37, 38, 40, 41, 41, 51, 54, 56.

The SYM doc flagged match length as "a confound on absolute magnitude" — SYM matches ran ~2× longer than ASYM. **This arm resolves which axis owns that confound: geometry.** With objectives removed but ASYM geometry held, match length stays with ASYM_OBJ (median 28 vs 29, 6.63 vs 6.03 rounds), nowhere near SYM_NOOBJ's 58 / 12.03. Objectives do not drive match length; terrain and spawn separation do.

That resolution matters because the length confound and the keep-rate effect **point in opposite directions here**: this arm runs ASYM-short yet posts the *lowest* keep-rate of the three corners. Whatever suppresses utility programming on this arm is not "more rounds diluting the denominator."

### 6a. A mechanism note, flagged as inference

ASYM_OBJ produced only **2** `objective_scored` events in 30 matches and zero VP terminals — objectives were present in the contract and essentially never captured in play. Yet their *removal* is the larger of the two effects on utility keep-rate. The reading this suggests is that objectives act on card selection through the **stated goal in the pilot's decision context**, not through realized objective capture: a mech with somewhere to go programs utility (smoke/chaff to cover an approach) at ~3–5× the rate of one whose only available goal is to shoot. This arm did not test that mechanism and **does not demonstrate it** — it is an inference consistent with the numbers, and isolating it needs a separate arm (e.g. objectives present in the observation space but non-scoring).

---

## 7. Statistical comparisons

Two-proportion z-tests on keep-rate:

| Comparison | p1 | p2 | z | p | Significant at α=0.05 |
|---|---:|---:|---:|---:|---|
| **Objectives axis** — ASYM_NOOBJ red vs ASYM_OBJ red | 0.017588 | 0.055249 | −2.801 | **0.0051** | **Yes** |
| **Objectives axis** — ASYM_NOOBJ blue vs ASYM_OBJ blue | 0.087940 | 0.165746 | −3.239 | **0.0012** | **Yes** |
| **Geometry axis** — ASYM_NOOBJ red vs SYM_NOOBJ red | 0.017588 | 0.031856 | −1.415 | 0.157 | No |
| **Geometry axis** — ASYM_NOOBJ blue vs SYM_NOOBJ blue | 0.087940 | 0.123269 | −1.803 | 0.071 | No |
| Confounded baseline pair — ASYM_OBJ red vs SYM_NOOBJ red | 0.055249 | 0.031856 | +1.861 | 0.063 | No |
| Confounded baseline pair — ASYM_OBJ blue vs SYM_NOOBJ blue | 0.165746 | 0.123269 | +1.916 | 0.055 | No |

The single-axis objectives contrast is the **only** comparison in this table that clears significance, and it does so on both seats — while the confounded two-axis contrast the program has been quoting clears on neither. That is the expected consequence of two partially-cancelling components: decomposing the contrast made the real effect visible.

**Clustering caveat — read before weighting any p-value above.** These are card-level proportions (denominator 362–722 register slots), but observations are **clustered within matches**: each match contributes ~6–12 rounds × 2 utility cards per seat, and a pilot's disposition toward utility is correlated within a match. Effective n is therefore materially smaller than the nominal denominator and **these p-values are anti-conservative**. They should be read as a rank ordering of effect strength (objectives ≫ geometry), not as calibrated evidence. A match-level analysis (per-match keep-rate, n=30, cluster-robust) is the correct follow-up; it is not performed here.

Consistent with program history, adjacent-arm comparisons at n=30 rarely reach significance, and no claim here rests on a single comparison.

---

## 8. Arithmetic correction flagged, not silently applied

`docs/steel_onslaught/LEARNINGS.md` (entry "Utility deprioritization is SCENARIO-ROBUST") states the ASYM_OBJ→SYM_NOOBJ magnitude drop as "~35–42% lower" for both seats. Recomputing from the raw ledgers at pre-registration time:

| Seat | ASYM_OBJ | SYM_NOOBJ | relative drop | inside "~35–42%"? |
|---|---:|---:|---:|---|
| red | 0.055249 | 0.031856 | **42.34%** | yes |
| blue | 0.165746 | 0.123269 | **25.63%** | **no** |

Red is inside the stated band; **blue is not** (25.6% < 35%). The mean of the two, 33.99%, also sits below the band. The band appears to have been generalized from the red figure to both seats. The same discrepancy is reproduced in `docs/evidence/2026-07-23-scenario-variation-qwen35-symmetric.md` § Findings item 3.

This arm used the **exact recomputed fractions** as its fixed constants, never the rounded range. Per the register's append-only maintenance contract, the closed LEARNINGS entry is **not edited here**; a future session should append a correcting entry citing this document. This is exactly the class of unverified-arithmetic error the pre-registration method rules exist to catch, and it was caught only because the constants were recomputed rather than copied.

---

## 9. Limitations

- **Uncontrolled standoff (OMN-15119 disclosure class).** Blue's loadout `contracts_data/loadouts/qwen35/sniper_ironclad.yaml` (stock, unmodified) carries `weapon.siege.artillery_mortar` (range 50) and `weapon.heavy.harpoon_gun` (range 30). Red's `contracts_data/loadouts/llm_qwen35_berserker.yaml` carries `weapon.light.machine_gun` (range 12) and `weapon.light.shrapnel_thrower` (range 8). **Blue therefore holds an uncontrolled ~18–38 cell range advantage over red in this arm.** This arm inherits that asymmetry unchanged and deliberately: both baselines it bridges (ASYM_OBJ, SYM_NOOBJ) carry the identical loadout pairing, so the standoff is constant across all three corners and cannot generate the drift being decomposed. It is disclosed verbatim so no reader assumes it was controlled for. It plausibly explains red's 0/29 winless record in every corner, and it means all keep-rate figures here describe a permanently-losing red seat and a permanently-winning blue seat.
- **The pre-registered criterion's 0–1 framing was inadequate for the data** (§0a). The label fired; its gloss did not hold. A future decomposition arm should pre-register a rule that admits opposite-signed components, and should scope the sign-reversal escape to *either* component rather than `d_obj` alone.
- **Two runs were discarded before the scored run** (§1a). Selection was blind to the measured quantity and the budget was bounded and declared in advance, but the arm is nonetheless the third battery executed, not the first.
- **Card-level p-values are anti-conservative** due to within-match clustering (§7). The significance ordering is trustworthy; the exact p-values are not.
- **`n=30` per corner.** The decomposition rests on a single new datapoint against two fixed baselines. It does not carry a confidence interval on `f_obj_pooled` — propagating uncertainty from three independent batteries through a ratio whose denominator is a small difference of two noisy estimates would produce an extremely wide interval. **The point estimate `f_obj_pooled = 1.7530` should not be read as precise**; the robust claims are its sign and that it exceeds 1.
- **Denominators are unequal across corners** (398 vs 362 vs 722), a direct consequence of differing match lengths (§6). Keep-rate is a rate so this does not bias it, but it does mean the three corners carry different precision.
- **Single model, single seat pairing.** Live Qwen3.6-35B-A3B on both seats. Nothing here establishes that the objectives effect generalizes across models or archetypes.
- **The fourth corner (SYM_WITH_OBJ) was not built,** by design: objective-cell placement on `foundry_60`'s symmetric scatter is an undesigned free choice. The 2×2 identity makes the third corner sufficient for the decomposition, but a genuine interaction term between geometry and objectives cannot be estimated without it — this arm assumes additivity, and additivity is untestable with three corners.
- **One abort** (seed 5008, `provider_semantic_failure`). Sensitivity check in §5a shows it does not move the verdict.

---

## 10. Citations (all relative paths)

Artifacts produced by this arm:
- `contracts_data/arenas/foundry_60_asym_v1_noobj.yaml`
- `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_noobj_qwen.yaml`
- `tests/contracts/test_scenobj_noobj_overlay.py`
- `tests/contracts/test_arena.py` (one-line catalog-set addition)
- `.onex_state/steel_onslaught/ugate_scenobj_asym_noobj_battery_r3/` — scored ledger
- `.onex_state/steel_onslaught/ugate_scenobj_asym_noobj_battery_r1_DISCARDED_gate_fail/`, `.onex_state/steel_onslaught/ugate_scenobj_asym_noobj_battery_r2/` — discarded, unscored, retained for audit

Baselines and prior work:
- `docs/evidence/2026-07-23-scenario-variation-qwen35-symmetric.md` — the confounded contrast; its § "Verdict and caveats" names this exact follow-up
- `contracts_data/arenas/foundry_60_asym_v1.yaml`, `contracts_data/arenas/foundry_60.yaml`
- `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml`, `contracts_data/overlays/tactical_split_overdeal_utility_sym_v1_qwen.yaml`
- `contracts_data/loadouts/llm_qwen35_berserker.yaml`, `contracts_data/loadouts/qwen35/sniper_ironclad.yaml`
- ASYM_OBJ ledger `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree)
- SYM_NOOBJ ledger `.onex_state/steel_onslaught/ugate_qwen35_symmetric_battery/events.sqlite3` (SO-SCENARIO-SYM2 worktree)

Code cited:
- `scripts/run_ogate_objectives_battery.py` (`_lane_overlay`, per-seed skip handling)
- `src/steel_onslaught/llm/client_http.py` (transport error classification)
- `src/steel_onslaught/match/composition.py` (root-owned httpx client)
- `src/steel_onslaught/events/envelope.py` (`match_started`, `hand_dealt`, `plan_committed`)

Pending correction (flagged, not applied): `docs/steel_onslaught/LEARNINGS.md`, "Utility deprioritization is SCENARIO-ROBUST" — see §8.

Pre-registration commit: `3b0ac4a3263b688f3d077a605ddc59053c7706ae` at `2026-07-25T16:59:10Z`, preceding the earliest `match_started` of any run of this arm (`2026-07-25T17:00:01Z`).

No secrets, keys, or absolute paths included.
