# SO-RANGECAP Arm (blue mortar range 30 → 15, red dose held at ×16) Battery — Residual-Capping-Mechanism Isolation (2026-07-25)

**Verdict:** **H_NULL is supported; the pre-registered formal criterion is NOT met — blue's mortar-range halving does not, on its own, close the residual capping gap P6/P7 flagged.** Red (brawler) win count is **21** (out of 30 seeds; 29 decided/elimination-class matches, 1 abort). Decided-match red win rate is **21/29 = 0.7241** (Wilson 95% CI **[0.5428, 0.8530]**); all-match basis (n=30, abort included in denominator, not counted as a win) is **21/30 = 0.7000** (Wilson 95% CI **[0.5212, 0.8334]**). The pre-registered threshold required **≥22 wins** (equivalently, win rate ≥ 22/30 = 0.7333). Observed win count (21) falls **one win short** of the threshold under every reading of the criterion — literal win-count (21 < 22), all-basis proportion (0.7000 < 0.7333), and decided-basis proportion (0.7241 < 0.7333, the closest of the three, missing by 0.92pp). Against the P6 baseline (17/30 = 0.5667), the point-estimate gain is **+13.33pp (all-basis) to +15.75pp (decided-basis)** — the decided-basis gain is numerically almost exactly equal to the pre-registered target magnitude (+15.74pp) but the criterion was written and scored as an integer win-count threshold, which this arm misses by exactly one match. A two-proportion z-test against P6 is **not significant** on either basis (all-basis z=1.07, p=0.284; decided-basis z=1.26, p=0.207) — consistent with this program's unbroken record of non-significant adjacent/near-baseline comparisons at n=30.

**Engine-layer confirmation that the manipulation landed as intended:** blue's mortar fired 31 times this arm (vs 68 times in the P6 baseline with mortar_r30) despite MORE total fire attempts against it (152 vs 120, fired+rejected) — a `target_out_of_range` rejection rate of 121/152 = 79.6% for the mortar this arm, vs 52/120 = 43.3% in P6. Blue's mortar usage was cut by more than half in absolute count. The manipulation is real and large at the engine layer; it is the win-rate effect size relative to the pre-registered bar that came up one match short.

**Ledger:** `.onex_state/steel_onslaught/rangecap_r15_dmg16` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-RANGECAP worktree.
**Change under test:** ONE lever, additive contract files only:
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r15` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r15.yaml`) — swaps only the mortar weapon module (`weapon.siege.artillery_mortar_r30` → `weapon.siege.artillery_mortar_r15`, range 30 → 15). Every other loadout field (chassis, boiler, pilot, sensors, cooling, armor, gizmos, budgets, `harpoon_gun`) byte-identical to the P6/P1-P7 `mortar_r30` loadout.
2. `contracts_data/weapons/artillery_mortar_r15.yaml` — one field changed from `artillery_mortar_r30.yaml`: `range: 30 → 15`. `accuracy_curve`, `damage`, `cooldown_ticks`, `heat_generated`, `pressure_cost`, `target_class_effectiveness`, `damage_type`, `compatibility` all byte-identical (confirmed by full diff, §3).
3. Red loadout `loadout.llm.qwen35_berserker_dmg16` — **UNCHANGED from P6**, the baseline this arm compares against. Red's dose is held constant; this arm isolates range alone.

Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_rangecap_r15_dmg16_qwen.yaml` is byte-identical to the merged P6 overlay except for the blue loadout id, the pre-registration comment block, and isolated `.onex_state` ledger paths. Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030 (matched to P6), `--fresh` on first launch only. `battery_raw.jsonl` holds exactly 30 rows, seeds 5001–5030 present exactly once each, zero duplicates, zero gaps.
**Baseline:** P6 (mortar_r30 × dmg16, `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md`) — 17/30 = 0.56667 decided-match red win rate, zero aborts.
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl`, cross-checked against `battery_summary.json` (agrees exactly on `winners`, `n`, `terminal_classes`, `play_terminal_fraction`).

---

## 0. Pre-registered hypothesis (quoted verbatim from the overlay header, committed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_rangecap_r15_dmg16_qwen.yaml`:

> **H_RANGE** (blue's range advantage IS a -- or the -- residual capping mechanism P6/P7 flagged as unexplained): cutting blue's mortar standoff range in half (30->15), at fixed dose, raises red's win rate by at least as much as the single largest dose-driven marginal gain observed anywhere in the P1-P7 program (+15.74pp, the x8->x11 step, per docs/evidence/2026-07-25-pair_p7_dmg24-battery.md Sec8).
>
> **FORMAL CRITERION (the ONLY criterion this arm is scored against):** decided-match red win rate >= 22/30 (0.56667 + 0.1574 = 0.72407; 30 x 0.72407 = 21.72, so 22/30 = 0.73333 is the smallest integer win count at or above the threshold -- 21/30 = 0.70000 falls short of it). Win rate >= 22/30 supports H_RANGE. Win rate <= 21/30 supports H_NULL (range is NOT the -- or not the sole -- residual capping mechanism; the cap lies elsewhere, e.g. approach/exposure-time dynamics net of range, or something this arm does not isolate) -- this is an equally real, publishable finding, not a failed run.

The overlay explicitly states this arm "does NOT pre-favor either hypothesis" and that "n=30 cannot distinguish them" is a fully acceptable answer.

---

## Method

Identical to the P1–P7 method:
- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded); all-30 basis also reported.
- **Dose/lever verification, two layers:** contract-layer diff (only `range` changed) and engine-layer reconstruction (`hit_resolved` paired with `armor_absorbed` at `sequence_in_tick + 1` in the same `(match_id, tick)`; weapon attribution from the closest preceding `weapon_fired` targeting the same defender in the same tick; `weapon_fired`/`weapon_fire_rejected` counts by weapon_id and reason).

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | `elimination` 29/30, `abort` 1/30 (seed 5007, `provider_semantic_failure`, `is_draw=true`, no winner) |
| `play_terminal_fraction` | **0.9667** (task gate ≥0.9 — PASS; codebase default ≥0.95 — PASS) |
| Winner distribution | player.red 21, player.blue 8, no winner (abort) 1 |
| **Decided-match red win rate** (elimination-only denominator, per Method) | **21/29 = 0.7241** |
| **All-match red win rate** (n=30, abort in denominator, not a win) | **21/30 = 0.7000** |
| 95% Wilson CI, decided basis | **[0.5428, 0.8530]** |
| 95% Wilson CI, all basis | **[0.5212, 0.8334]** |
| Replay validity | 1/1 both players, all 30 matches (including the abort) |
| `failed_completions` distribution | 0 → 12 matches, 1 → 13 matches, 2 → 3 matches, 4 → 1 match, 5 → 1 match (sum = 28, matches §6 exactly) |

Independently recomputed from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once, zero duplicates, zero gaps) and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id)` = 30 for both `match_started` and `match_ended`; `mech_destroyed` on `mech.blue.01` × 21 / `mech.red.01` × 8, sum 29 = the 29 decided matches).

**Non-elimination / abort count: 1** — seed 5007 (`provider_semantic_failure`, malformed JSON completion), `is_draw=true` in the raw row (an artifact of the abort path setting the draw flag, not a genuine tied match — no `victory_kind`, no `winner_player_id`, `total_awards=0`). This is the only abort in the battery; every other arm compared here (P6, P7) had zero aborts.

### 1a. Statistical comparison vs P6 baseline (two-proportion z-test)

| Comparison | Basis | z | p | Significant at α=0.05? |
|---|---|---:|---:|---|
| SO-RANGECAP (21/29) vs P6 (17/30) | decided | 1.263 | 0.207 | No |
| SO-RANGECAP (21/30) vs P6 (17/30) | all-match | 1.072 | 0.284 | No |

Not significant on either basis — consistent with this program's unbroken record of non-significant adjacent/near-baseline comparisons at n=30 (no adjacent-arm comparison in the P1–P7 program has ever reached significance; this arm, though a lever-swap rather than a dose step, replicates the same pattern against its nearest baseline).

### 1b. Formal-criterion scoring — the pre-registered decision

The criterion text fixes the threshold as an **integer win count (≥22)**, derived via an arithmetic pass that assumed a zero-abort denominator of 30 (true of every prior arm in this family, including P6). This arm produced one abort, which the pre-registered text did not anticipate. Scored three ways, all agree:

| Reading | Value | vs threshold | Result |
|---|---:|---|---|
| Literal win count | 21 wins | need ≥22 | **falls short by 1** |
| All-match proportion (n=30 denominator, as the criterion's own arithmetic used) | 0.7000 | need ≥0.7333 | **falls short** |
| Decided-match proportion (Method's own definition, n=29 denominator) | 0.7241 | need ≥0.7333 | **falls short** (closest reading — misses by 0.92pp) |

All three readings agree on the same side of the pre-registered line: **H_NULL is supported**, not H_RANGE. The margin is narrow — one match — but the criterion was stated as a single bright-line threshold precisely to avoid post-hoc interpretation, and this arm does not clear it under any of the three ways to read "decided-match win rate" given the unanticipated abort.

## 2. Match length

| Metric | This arm (r15) | P6 (r30, baseline) |
|---|---:|---:|
| min ticks | 12 | 15 |
| median ticks | **26.0** | 23.0 |
| mean ticks | **26.4** | 23.3 |
| max ticks | 34 | 40 |

Sorted durations (n=30): 12, 17, 19, 22, 23, 24, 24, 24, 24, 25, 25, 25, 25, 25, 26, 26, 26, 27, 28, 28, 29, 30, 30, 30, 32, 32, 33, 33, 34, 34.

Match length rose (median 23.0 → 26.0, +3 ticks; mean 23.3 → 26.4, +3.1 ticks) rather than shortening. This runs counter to the naive expectation that shrinking blue's engagement envelope would let red close and end matches faster — if anything matches took longer, plausibly because blue's mortar (now range-15) becomes usable later in the approach and blue is forced to rely more on `harpoon_gun` (also range 30, unchanged) and repositioning before either weapon connects, extending the early no-damage phase. This document does not claim to have isolated that mechanism; it reports the direction as a fact against expectation.

## 3. Range-lever verification (contract + engine layers)

### 3a. Contract layer

`git diff HEAD` against every baseline file this arm depends on (`artillery_mortar_r30.yaml`, `sniper_ironclad_mortar_r30.yaml`, `sniper_ironclad.yaml`, `llm_qwen35_berserker_dmg16.yaml`, `foundry_60_asym_v1.yaml`) returns **empty** — zero existing files modified. `diff contracts_data/weapons/artillery_mortar_r30.yaml contracts_data/weapons/artillery_mortar_r15.yaml` shows exactly one field changed outside comments: `range: 30` → `range: 15`. `diff` on the two loadout files shows exactly one module-id swap (`weapon.siege.artillery_mortar_r30` → `weapon.siege.artillery_mortar_r15`), all other fields identical.

### 3b. Engine layer — the lever fired as intended

| Weapon | Fired | Rejected (`target_out_of_range`) | Total attempts | Fire rate |
|---|---:|---:|---:|---:|
| `artillery_mortar_r15` (this arm) | **31** | **121** | 152 | **20.4%** |
| `artillery_mortar_r30` (P6 baseline) | 68 | 52 | 120 | 56.7% |

Blue's mortar shot count dropped from 68 (P6) to 31 (this arm), a 54.4% reduction, despite MORE total fire attempts against the range check (152 vs 120) — confirming the range cut materially restricted the weapon's usable window at the engine layer, not merely on paper. `weapon_fired` totals this arm: `machine_gun_dmg16` 54, `harpoon_gun` 53, `artillery_mortar_r15` 31, `shrapnel_thrower_dmg16` 20 (475 total `weapon_fire_rejected` events, breakdown: `machine_gun_dmg16`/out-of-range 167, `shrapnel_thrower_dmg16`/out-of-range 121, `artillery_mortar_r15`/out-of-range 121, `harpoon_gun`/out-of-range 24, `harpoon_gun`/cooldown 20, `artillery_mortar_r15`/cooldown 14, `shrapnel_thrower_dmg16`/cooldown 8).

### 3c. Red's dose (dmg16) landed unchanged from P6 — confirms this arm isolates range alone

| Weapon | P6 raw (baseline) | This arm raw observed | Match? |
|---|---:|---:|---|
| `machine_gun_dmg16` | 89 | **89** (35/49 red hits, zero variance) | **exact match** |
| `shrapnel_thrower_dmg16` | 115 | **115** (14/49 red hits, zero variance) | **exact match** |

All 92 `hit_resolved` (hit=true) events paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches (49 red-caused, 43 blue-caused). Red's raw per-hit damage is byte-identical to P6, confirming red's dose was not touched by this arm — any win-rate delta is attributable to blue's range change alone, not a confound from red's own loadout.

### 3d. Armor saturation — mechanism continues to hold

| | This arm | P6 baseline |
|---|---:|---:|
| `armor_after == 0` on red hits | **49/49 = 100%** | 43/43 = 100% |
| Mean damage-after-armor per hit | **86.76** | 84.93 |
| Median | 86 | 83 |

Consistent with every prior arm in this family — `absorbed_amount` is bounded by the fixed, small armor pool, never by the mitigation-cap fraction of raw damage. Mean/median damage-after-armor essentially unchanged from P6 (as expected — red's dose is unchanged).

## 4. Hits-to-kill

| | This arm | P6 baseline |
|---|---:|---:|
| **Red kills blue — mean hits (21 kills)** | **2.048** (median 2, `{2:20, 3:1}` — near-zero variance, not the exact-2 floor seen in P7's dmg24 arm) | 2.18 (median 2, `{2:14, 3:3}`) |
| **Blue kills red — mean hits (8 kills)** | **2.75** (median 3, `{2:2, 3:6}`) | 2.62 (median 3, `{2:5, 3:8}`) |

Red's kill speed remains faster than blue's, essentially unchanged from P6 (2.048 vs 2.18) — expected, since red's dose is byte-identical to P6. Blue's own kill speed against red is slightly slower than P6 (2.75 vs 2.62), consistent with blue losing some of its early-mortar engagement window and needing to rely more on `harpoon_gun`/closer-range fire. `mech_destroyed` counts corroborate the win tally exactly: blue destroyed in 21 matches (= the 21 red wins), red destroyed in 8 matches (= the 8 blue wins), 21+8=29 decided matches, zero unexplained destructions, 1 abort with no destruction event on either side.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility, `utility_deployed`) | Keep-rate | P6 (r30 baseline) |
|---|---:|---:|---:|---:|
| red (brawler) | 334 | 12 | **0.0359** | 0.0298 |
| blue (sniper) | 334 | 22 | **0.0659** | 0.1026 |
| all-card sanity, both seats | 835/1670 (each seat: 167 `plan_committed` × 5-card register / 167 `hand_dealt` × 10-card hand) | — | 0.5000 (mechanical, confirms 5-of-10 register structure held) | 0.500 |

Blue's utility keep-rate dropped from P6's 0.1026 to 0.0659 — directionally consistent with blue spending more of its limited register slots on movement/positioning to compensate for the shrunk mortar window, though this document does not claim to have isolated that as the mechanism (n=30 is not powered to separate this from noise). Red's keep-rate is essentially flat (0.0298 → 0.0359).

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 362 |
| `llm_completion_resolved` | 334 |
| `llm_completion_failed` | 28 |
| `finish_reason` distribution | `stop`: 334/334 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 334/334 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **1/30** (seed 5007) |

362 requested − 334 resolved = 28, matching `llm_completion_failed` exactly, zero gap between resolved and `plan_committed`. Seed 5007's abort (`provider_semantic_failure`) was an in-match completion failure that was NOT recovered — this is the one match in the battery that did not reach a clean `elimination` terminal. `failed_completions` sums to 28 across all 30 rows including the aborted one (which itself carries 5 failed_completions before terminating).

---

## 7. Merge / additivity verification

- Branch `exp/so-rangecap-r15-dmg24` off `origin/main` @ `38dd334` (P6, PR #191, and the P1–P3 framework PR #170 are both ancestors, confirmed by prior pre-registration commit).
- `git diff HEAD` against every baseline file this arm depends on (`artillery_mortar_r30.yaml`, `sniper_ironclad_mortar_r30.yaml`, `sniper_ironclad.yaml`, `llm_qwen35_berserker_dmg16.yaml`, `foundry_60_asym_v1.yaml`) returns **empty** — zero existing files modified.
- The 3 files this arm's commit touches: 2 new additive contract files (`artillery_mortar_r15.yaml`, `sniper_ironclad_mortar_r15.yaml`), 1 new additive overlay (`tactical_split_overdeal_utility_asym_rangecap_r15_dmg16_qwen.yaml`) — no existing loadout/weapon/overlay/arena file modified. No provenance-test pin was needed (the new blue loadout lives under `contracts_data/loadouts/qwen35/`, outside `test_pilot_registry.py`'s non-recursive top-level glob, matching `sniper_ironclad_mortar_r30.yaml`'s own unpinned status).

---

## Verdict

**H_NULL is supported — the pre-registered formal criterion is not met.** Blue's mortar-range halving (30→15), at fixed red dose, raised red's decided-match win rate from P6's 56.67% to 72.41% (+15.75pp) — numerically almost exactly the pre-registered target magnitude (+15.74pp) — but the criterion was pre-declared as an integer win-count threshold (≥22 wins out of 30) that this arm misses by exactly one match (21 wins). Scored three ways (literal win count, all-match proportion, decided-match proportion), all three land on the H_NULL side of the line; the decided-match proportion is the closest, missing by 0.92pp.

- **The manipulation is real and large at the engine layer** (§3b): blue's mortar fire rate dropped from 56.7% (P6) to 20.4% (this arm) of attempts, a 54.4% reduction in shots actually fired, confirming the range cut materially restricted blue's engagement envelope as designed.
- **The win-rate effect is directionally large but statistically inseparable from P6 at n=30** (z=1.07–1.26, p=0.207–0.284 depending on basis) — consistent with this program's unbroken record of non-significant adjacent/near-baseline comparisons.
- **Range is at most a partial contributor to the residual capping mechanism, not the whole story.** A range cut alone, isolated from dose, produces a directionally strong but pre-registration-insufficient gain. Whatever remains uncapped by range alone (harpoon_gun unchanged at range 30, approach/exposure-time dynamics, or first-strike variance) is still live as an open question — exactly the "equally real, publishable finding" the pre-registration anticipated for the H_NULL outcome.
- **This arm does not settle whether range is A contributor** — the directional gain (+13.3 to +15.75pp depending on basis) is the largest single-lever gain seen in this program outside the dose-response sweep itself, and sits almost exactly at the pre-registered magnitude bar. It simply does not clear the specific bright-line integer threshold the pre-registration set, by one match.
- **One abort (seed 5007) introduced a denominator ambiguity the pre-registration did not anticipate** (assumed zero aborts, matching P6's history). All three readings of "decided-match win rate" resolve to the same side of the line, so the ambiguity does not change the verdict here, but it is a real gap in the pre-registration's own arithmetic, flagged rather than silently resolved (§1b).

**Honest statement on what this arm does and does not settle:** the point estimate (70–72%) is high and the engine-layer confirmation that the lever fired is unambiguous, but n=30 leaves a wide Wilson CI (roughly [0.52, 0.85] depending on basis) that comfortably contains both "range alone clears the bar" and "range alone falls well short of it." The pre-registered bright-line criterion is the only thing this document scores against, and by that criterion the answer is no — by a single match, on the closest reading. Whether a larger n would flip the verdict is not something this document can answer without running the exact re-roll the house rules prohibit.

---

## 8. Limitations

- **n=30 power, narrow miss.** The observed win count (21) is one match away from the pre-registered threshold (22). A single-match margin at n=30 is well within normal sampling variance; this document reports the miss as pre-registered and does not treat it as a strong disconfirmation of H_RANGE, only as the pre-declared decision rule's actual output.
- **Unanticipated abort creates a denominator ambiguity.** The pre-registration's arithmetic assumed a zero-abort n=30 denominator (true for P6, the baseline). This arm had one abort, so "decided-match win rate" (Method's own definition, denominator 29) and the criterion's own literal "X/30" arithmetic are two different quantities. Both are reported (§1a, §1b); both land on the same side of the threshold here, so the ambiguity is disclosed but does not change the verdict.
- **Non-adjacent-to-dose-curve comparison.** This arm is a lever-swap against the P6 baseline, not a step in the P1–P7 dose-response sweep; it is not placed in that sweep's dose-response table and should not be read as a dose-response data point.
- **Match-length increase is reported, not explained.** §2's finding (median +3 ticks vs P6) runs counter to a naive prediction and is reported as a fact; no mechanism is claimed or verified for it.
- **No re-run to chase a different number.** n=30, seeds 5001–5030, was pre-declared before this battery ran and is reported as-is (including the one abort); the battery completed all 30 seeds, so there is no truncation to disclose.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/rangecap_r15_dmg16/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `weapon_fired`, `weapon_fire_rejected`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `utility_deployed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Contract diffs: `contracts_data/weapons/artillery_mortar_r30.yaml` vs `artillery_mortar_r15.yaml`; `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml` vs `sniper_ironclad_mortar_r15.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`); accuracy curve: `src/steel_onslaught/reducers/weapons.py` (`interpolate_accuracy`).
- Baseline arm evidence: `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md` (P6, 17/30 = 0.5667, the comparison baseline this arm is scored against).
- Sibling arm evidence, program context: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md` through `-pair_p6_dmg16-battery.md`, `docs/evidence/2026-07-25-pair_p7_dmg24-battery.md` (marginal-rate table, source of the +15.74pp threshold magnitude).
- Pre-registration: overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_rangecap_r15_dmg16_qwen.yaml`, commit `235ba46`.
- No secrets, keys, or absolute paths included.
