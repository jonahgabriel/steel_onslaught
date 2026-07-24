# Pair-Sweep Arm P5 (mortar_r30 × red-dmg×11) Battery — Saturation Hypothesis Test (2026-07-24)

**Verdict:** **The point estimate crosses into the `>=0.35` COMPETITIVE band — the P4 doc's saturation hypothesis is FALSIFIED, not supported.** Decided-match red (brawler) win rate is **13/30 = 0.4333** (zero aborts, so the all-30 basis is identical), 95% Wilson CI **[0.2738, 0.6080]**. This is the fifth point on the dose-response curve (×1 0%, ×3 3.4%, ×5.5 17.2%, ×8 27.6%, ×11 **43.3%**) and is a **substantial jump**, not a plateau: +15.7pp over P4's own 27.6%, the largest single-step gain since ×3→×5.5. By the program's own point-estimate classification convention this arm is **COMPETITIVE** — the first arm in the entire program to cross that threshold. A two-proportion z-test against P4 (pooled p=0.362, SE=0.127) gives **z=1.26, p=0.21** — **not statistically significant** at conventional thresholds, so this is reported as a strong directional result, not a statistically proven jump; the CIs of P4 [0.147, 0.457] and P5 [0.274, 0.608] overlap substantially. `play_terminal_fraction=1.0` (30/30 elimination, zero aborts), `all_replay_valid=true` (1/1 both players, all 30 matches) — the cleanest trust-gate result of any pair-sweep arm to date.

**This document was pre-registered to test, not chase, a hypothesis** (per the dispatch instruction and this overlay's own header comment, committed before the battery ran): the P4 doc's leading (explicitly-hypothesis-only) mechanism was that blue's armor pool, already saturated (`armor_after==0` on all 68/68 red hits at ×8), would make further raw-damage escalation buy diminishing marginal win-rate return. **The engine-layer data below shows why that prediction did not hold**, and the explanation is mechanistic, not speculative: `armor_after==0` on every hit does not mean armor stops mattering — it means the *absorbed amount* on each hit is capped by whatever armor has regenerated since the last hit (bounded above by `armor_max=16`, a small, fixed ceiling), not by the 75% mitigation-cap fraction of `damage_raw` (which was already irrelevantly large at ×8 and is more so at ×11). Once the *cap* stops binding, `damage_after_armor = damage_raw − absorbed_amount` moves almost 1:1 with `damage_raw`, because the subtracted term is bounded by a small fixed number, not by a fraction of the growing dose. **"Saturated" was the wrong word for what P4 observed — the pool was overwhelmed, but overwhelmed does not imply insensitive to further dose.**

**Ledger:** `.onex_state/steel_onslaught/pair_p5_dmg11` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-COMP-P5 worktree.
**Change under test:** two levers, exactly two, both additive contract files (new, not modifications):
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` — unmodified, held constant across every pair-sweep arm including this one.
2. Red loadout `loadout.llm.qwen35_berserker_dmg11` (`contracts_data/loadouts/llm_qwen35_berserker_dmg11.yaml`) — swaps both berserker weapons for damage-×11 variants (`machine_gun_dmg11`: damage 8 → 88; `shrapnel_thrower_dmg11`: damage 12 → 132), every other weapon field identical (confirmed via full-field diff, §3a).

Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p5_dmg11_qwen.yaml` is byte-identical to the merged P4 overlay except for the red loadout id, the dose-curve comment block, and isolated `.onex_state` ledger paths. Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, per-seed isolated invocation (one process per seed, shared append-mode state root, `--fresh` only on seed 5001, up to 2 attempts per seed on a 420s timeout). **Every one of the 30 seeds succeeded on attempt 1 — zero retries needed** (unlike the composition-arm battery run immediately before this one on the same endpoint, which needed 2 retries; no evidence of endpoint degradation across the two sequential batteries).
**Baselines:** v1 anchor 0/30; P1 (×3) 1/29 = 0.0345 FAILED; P2 (×5.5) 5/29 = 0.1724 DIRECTIONAL; P3 (armor-8) 0/28 = 0.0000 FAILED (dead lever); P4 (×8) 8/29 = 0.2759 DIRECTIONAL.
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl` — not copied from `battery_summary.json` or stdout.

---

## 0. Pre-registered prediction (written before reading results, per dispatch instruction)

Committed in this overlay's own header comment before the battery ran: blue is `chassis_class=heavy`, so `target_class_effectiveness.heavy` = 0.7 (machine gun) / 0.6 (shrapnel thrower) applies, giving a predicted engine-layer `damage_raw`:

- `machine_gun_dmg11`: `int(88 × 0.7) = 61`
- `shrapnel_thrower_dmg11`: `int(132 × 0.6) = 79`

**Both predictions matched the reconstructed engine-layer data exactly, zero variance** (§3b). The win-rate prediction was deliberately *not* pre-registered as a number — per the dispatch instruction, this arm is a test of the P4 saturation hypothesis, not an attempt to hit a calibrated target: "if ×11 lands near or below ×8's 27.6%, the saturation hypothesis is supported; if it jumps substantially, the hypothesis is wrong." **It jumped substantially (27.6% → 43.3%, +15.7pp) — the hypothesis is not supported by this result.**

---

## Method

Identical to the P1–P4 method:
- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded); all-30 basis also reported. Zero aborts this battery, so both bases are identical.
- **Dose verification, two layers:** contract-layer diff (only `damage` changed) and engine-layer reconstruction (`hit_resolved` paired with `armor_absorbed` at `sequence_in_tick + 1` in the same `(match_id, tick)`; `damage_raw = damage_after_armor + absorbed_amount`; weapon attribution from the closest preceding `weapon_fired` targeting the same defender in the same tick).
- **Armor mechanic** (`src/steel_onslaught/reducers/damage.py::compute_armor_reduction`): a **degrading, capped-fraction, per-tick-regenerating pool**. `absorbable = min(armor_value_remaining, ceil(damage_raw × mitigation_cap))`, `mitigation_cap=0.75` for `standard`-type weapons (both weapons here). Critically — per the module's own docstring — **"regeneration is per-tick in the fold, toward armor_max"**: armor is not a one-shot resource: it regenerates between hits, so the *timing* of hits relative to the regen cadence determines how much armor is available to absorb any given hit, independent of `damage_raw`.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 (zero orphans — every seed succeeded on attempt 1, no retries) |
| Terminal-class mix | elimination 30/30, zero aborts |
| `play_terminal_fraction` | **1.0** (task gate ≥0.9 — PASS; codebase default ≥0.95 — also PASS) |
| Winner distribution | player.red 13, player.blue 17 |
| **Decided-match red win rate (aborts excluded)** | **13/30 = 0.4333** |
| **All-match red win rate** | **13/30 = 0.4333** (identical — zero aborts) |
| 95% Wilson CI | **[0.2738, 0.6080]** |
| Replay validity | 1/1 both players, all 30 matches |

Independently recomputed from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once, zero duplicates, zero gaps) and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id)` = 30 for both `match_started` and `match_ended`). **Red wins: seeds 5003, 5006, 5009, 5011, 5013, 5014, 5016, 5020, 5023, 5024, 5025, 5026, 5027** (13 seeds, all `elimination`/`last_mech_standing`, corroborated by `mech_destroyed` on `mech.blue.01` × 13).

By the program's own verdict-band convention (`<0.10` FAILED, `0.10–0.35` DIRECTIONAL, `>=0.35` COMPETITIVE), the **point estimate (0.4333) falls inside the COMPETITIVE band** — the first arm in this entire program to do so by point estimate, not merely by CI-overlap (P4's own CI touched but did not center on COMPETITIVE). The Wilson CI's lower bound (0.2738) still sits inside DIRECTIONAL territory, so this is not proof the *true* rate is COMPETITIVE — but the point-estimate classification, applied with the same convention used for every prior arm in this program, calls this one COMPETITIVE.

### 1a. Matched-seed comparison against P4

Both P4 and this arm ran the identical seed set (5001–5030) on the identical arena/blue-loadout pairing, differing only in red's dose. P4's own doc reports its red-win seeds as **5001, 5007, 5014, 5016, 5020, 5025, 5029, 5030** (8 seeds).

| | Count | Seeds |
|---|---:|---|
| Red won in **both** P4 and P5 | 4 | 5014, 5016, 5020, 5025 |
| Red won in P4, **lost** in P5 | 4 | 5001, 5007, 5029, 5030 |
| Red **won** in P5, lost in P4 | 9 | 5003, 5006, 5009, 5011, 5013, 5023, 5024, 5026, 5027 |
| Blue won in both | 13 | (remainder) |

Nine seeds flipped from blue-favorable to red-favorable going P4→P5, against only four flipping the other way — a 9:4 split in the direction the dose hypothesis predicts, not the saturation hypothesis. This is **not a controlled paired test** (the underlying process is stochastic LLM decision-making plus engine RNG per match, not a deterministic replay with only the dose changed — a seed does not force an identical match trajectory across arms once weapon behavior differs), so it is reported as a corroborating directional signal, not a formal significance test. It is consistent with, and does not contradict, the raw count difference (13 − 8 = 5 = 9 − 4).

## 2. Match length

| Metric | P5 (×11) | P4 (×8) | P2 (×5.5) | P1 (×3) |
|---|---:|---:|---:|---:|
| min ticks | 14 | 14 (elim) | 18 | 13 |
| median ticks | **23.0** | 24 | 30 | 31 |
| mean ticks | **24.43** | 24.86 (elim-only) | 30.1 | 31.4 |
| max ticks | 39 | 38 | 50 | 61 |

P5's match length continues the monotonic shortening trend the P4 doc identified (P1: 31 → P2: 30 → P4: 24 → **P5: 23**) — the shortest median of any arm in the pair-sweep program, marginally below even P4. This is consistent with a still-more-lethal dose compressing matches further, in the same direction P4 already established, not a reversal.

## 3. Dose verification (raw weapon damage)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `machine_gun.yaml` → `machine_gun_dmg11.yaml` | `damage: 8` | `damage: 88` | `damage` only (full-field diff over every other key — `weapon_class`, `range`, `pressure_cost`, `heat_generated`, `cooldown_ticks`, `accuracy_curve`, `target_class_effectiveness`, `damage_type`, `compatibility` — confirms zero other change) |
| `shrapnel_thrower.yaml` → `shrapnel_thrower_dmg11.yaml` | `damage: 12` | `damage: 132` | `damage` only, same identical-field guarantee |
| `llm_qwen35_berserker.yaml` → `llm_qwen35_berserker_dmg11.yaml` | `weapons: [machine_gun, shrapnel_thrower]` | `weapons: [machine_gun_dmg11, shrapnel_thrower_dmg11]` | weapon-slot module IDs only; full-field diff over every other key confirms byte-identical chassis/boiler/pilot/sensors/cooling/armor/gizmos/budgets |

`git diff HEAD` against `machine_gun.yaml`, `shrapnel_thrower.yaml`, `llm_qwen35_berserker.yaml`, `sniper_ironclad_mortar_r30.yaml`, `sniper_ironclad.yaml`, `foundry_60_asym_v1.yaml`, and `heavy_ironclad_mk1.yaml` (every baseline this arm depends on) returns **empty** — this arm modifies zero existing files, exactly as P1–P4 did.

`match_started` runtime snapshot for seed 5001 confirms wiring: `mech.red.01.loadout_id = "loadout.llm.qwen35_berserker_dmg11"` (light, `hp_max=60`, `armor_max=6`); `mech.blue.01.loadout_id = "loadout.llm.qwen35_sniper_ironclad_mortar_r30"` (heavy, `hp_max=160`, `armor_max=16`) — matches P1–P4's wiring confirmation exactly.

### 3b. Engine layer — dose landed exactly as pre-registered

| Weapon | Baseline raw (int(8×0.7)=5 / int(12×0.6)=7) | P5 raw observed | Pre-registered prediction (§0) | Match? |
|---|---:|---:|---|---|
| `machine_gun_dmg11` | 5 | **61** (39/57 red hits, zero variance) | int(88×0.7)=61 | **exact match** |
| `shrapnel_thrower_dmg11` | 7 | **79** (18/57 red hits, zero variance) | int(132×0.6)=79 | **exact match** |

All 117 `hit_resolved` events in the battery (57 red-caused, 60 blue-caused) paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches, zero unattributed weapon IDs on the red side. Both weapons land at exactly one raw-damage value each across every red-on-blue hit (zero variance) — the dose is deterministic and matches the pre-registered prediction to the integer.

### 3c. Armor saturation — `armor_after==0` replicates P4, but this is where the hypothesis breaks

| | P5 (×11) | P4 (×8) |
|---|---:|---:|
| `armor_after == 0` on red hits | **57/57 = 100%** | 68/68 = 100% |
| Mean damage-after-armor per hit | **58.04** | 40.57 |
| Median | 57 | 41 |
| Ratio P5/P4 | **1.430×** | — |

The `armor_after==0` fraction is identical (100% both arms) — this is the number the P4 doc's hypothesis leaned on, and by itself it looks like confirmation of saturation. **It is not.** The `absorbed_amount` distribution for this arm's 57 red hits (`Counter`: `16`×24, `1`×13, `4`×5, `2`×4, `5`×4, `6`×3, `8`×2, `3`×1, `11`×1) shows absorption is bounded **above by 16 (`armor_max`)**, never by the 75% mitigation cap (`ceil(61×0.75)=46` and `ceil(79×0.75)=60`, both far above 16) — exactly as the P4 doc itself documented for ×8. The mechanistic error in the prior hypothesis: **`armor_after==0` tells you the pool was overwhelmed on that hit, but says nothing about whether a larger dose would still have produced more post-armor damage.** Since `absorbed_amount = min(armor_remaining_at_that_moment, cap)` and `cap` is irrelevantly large at both ×8 and ×11, `absorbed_amount` depends only on how much armor had regenerated since the previous hit (bounded above by 16) — a quantity **independent of `damage_raw`**. Therefore `damage_after_armor = damage_raw − absorbed_amount` moves almost 1:1 with increases in `damage_raw`, not with diminishing returns: the raw-damage increase from ×8 to ×11 (44→61 machine gun, +17; 57→79 shrapnel, +22) predicts a hit-count-weighted mean increase of `(39×17 + 18×22)/57 ≈ 18.6`; the **observed** increase in mean damage-after-armor is `58.04 − 40.57 = 17.47`` — within noise of the raw-damage-driven prediction, and nowhere close to the near-zero increase a genuinely saturating (diminishing-returns) mechanism would predict.

**Conclusion: the P4 doc's leading hypothesis conflated "the mitigation cap stopped binding" (true, and correctly observed at ×8) with "further dose has no further effect" (false, and now directly falsified by this arm's own engine-layer data).** Once the cap stops binding, the *fixed, small* armor-pool ceiling (16, regenerating slowly, never able to fully offset a single high-damage hit) means additional raw damage converts almost entirely into additional effective damage — the opposite of saturation. This is a genuine correction to the prior program record, grounded in the same mechanistic derivation the P4 doc itself started (armor model internals) but carried one step further than that document took it.

## 4. Hits-to-kill

| | P5 (×11) | P4 (×8) | P2 (×5.5) | P1 (×3) |
|---|---:|---:|---:|---:|
| Blue kills red — mean hits (17 kills) | **2.59** (median 3, `{2:7, 3:10}`) | 2.38 (21 kills) | 2.67 | 2.75 |
| Red kills blue — mean hits (13 kills) | **3.00** (median 3, **zero variance — every single kill took exactly 3 hits**) | 4.13 (8 kills) | 6.40 | 12 (n=1) |

Red's kill speed against blue continues its dose-response trend (12 → 6.40 → 4.13 → **3.00** mean hits across P1→P2→P4→P5) — the most dramatic figure in this table is the **zero variance**: all 13 of P5's red wins killed blue in *exactly* 3 hits, no exceptions. At a mean damage-after-armor of 58.04/hit against blue's `hp_max=160`, three hits average ≈174 — comfortably lethal, while two hits average ≈116, short of 160 in the typical case (consistent with zero 2-hit kills observed). This mechanically corroborates §3c's finding: the *absolute* magnitude of damage-after-armor at this dose is now large enough relative to blue's fixed HP pool that red's kill sequence has become nearly deterministic, a direct, verifiable consequence of raw damage continuing to translate into effective damage well past the point the armor mitigation cap stopped binding. `mech_destroyed` counts corroborate the win tally exactly: blue destroyed in 13 matches (= the 13 red wins), red destroyed in 17 matches (= the 17 blue wins), 13+17=30, zero unexplained destructions.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate | P4 (×8) |
|---|---:|---:|---:|---:|
| red (brawler) | 316 | 11 | **0.0348** | 0.0290 |
| blue (sniper) | 316 | 34 | **0.1076** | 0.1161 |
| all-card sanity, both seats | 790/1580 (each seat) | — | 0.5000 (mechanical, confirms 5-of-10 register structure held) | 0.500 |

Both seats' utility keep-rates stay in the same low range as every prior arm — no new effect from the higher dose.

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 330 |
| `llm_completion_resolved` | 316 |
| `llm_completion_failed` | 14 |
| `finish_reason` distribution | `stop`: 316/316 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 316/316 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **0/30** |

330 requested − 316 resolved = 14, matching `llm_completion_failed` exactly, zero gap between resolved and `plan_committed` — every in-match completion failure was recovered by retry, and (per the header note) every one of the 30 seed-level process invocations succeeded on the first attempt with no transport-level retry needed at the harness level — the cleanest process-level run of the two batteries in this session.

---

## 7. Merge / additivity verification

- PR #170 merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0` — confirmed an ancestor of this branch's HEAD via `git merge-base --is-ancestor 255f2306... HEAD` (exit 0).
- `git diff HEAD -- contracts_data/weapons/machine_gun.yaml contracts_data/weapons/shrapnel_thrower.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/chassis/heavy_ironclad_mk1.yaml` returns **empty** — every baseline file this arm depends on is byte-identical to its merged version.
- The 4 files this arm adds (`machine_gun_dmg11.yaml`, `shrapnel_thrower_dmg11.yaml`, `llm_qwen35_berserker_dmg11.yaml`, `tactical_split_overdeal_utility_asym_pair_p5_dmg11_qwen.yaml`) are all new, additive files — no existing file is modified.

---

## 8. Dose-response placement

| Dose | Arm | Decided-basis win rate | All-30 basis | Classification |
|---|---|---:|---:|---|
| ×1 | v1 anchor | 0/30 = 0.0000 | 0/30 = 0.0000 | (null) |
| ×3 | P1 | 1/29 = 0.0345 | 1/30 = 0.0333 | FAILED |
| ×5.5 | P2 | 5/29 = 0.1724 | 5/30 = 0.1667 | DIRECTIONAL |
| ×8 | P4 | 8/29 = 0.2759 | 8/30 = 0.2667 | DIRECTIONAL |
| ×11 | **P5 (this arm)** | **13/30 = 0.4333** | **13/30 = 0.4333** | **COMPETITIVE (point estimate)** |

| Step | Δdose | Δ win rate (decided basis, pp) | Marginal rate (pp/dose-unit) |
|---|---:|---:|---:|
| ×1 → ×3 | 2.0 | +3.45 | 1.72 |
| ×3 → ×5.5 | 2.5 | +13.79 | 5.52 |
| ×5.5 → ×8 | 2.5 | +10.34 | 4.14 |
| ×8 → ×11 | 3.0 | **+15.74** | **5.25** |

The marginal rate **rose again** on this step (4.14 → 5.25 pp/unit), reversing the deceleration P4 reported and landing close to the ×3→×5.5 step's own rate (5.52). Five points is still not enough to fit a specific functional form, but the shape is no longer consistent with simple saturation — it looks more like continued, roughly steady marginal returns once the armor mitigation cap stops binding (§3c), which for this arena/loadout pairing happened somewhere around ×5.5–×8.

---

## Verdict

**COMPETITIVE by point estimate (0.4333), the first arm in this program to cross the 0.35 threshold that way** — Wilson 95% CI [0.2738, 0.6080] (decided-30 basis, identical to all-30 since zero aborts). `play_terminal_fraction=1.0`, `all_replay_valid=true` — the cleanest trust-gate result of any pair-sweep arm. The intended ×11 raw-damage dose landed exactly as pre-registered at both layers: contract diff shows only `damage` changed (×11.00 exactly on both weapons), and engine-layer reconstruction matches the pre-registered prediction to the integer with zero variance across 57 hits (61 machine-gun, 79 shrapnel).

**The P4 doc's saturation hypothesis is falsified by this result, and the mechanism is now understood, not merely observed as a null.** `armor_after==0` on 100% of hits replicates at both ×8 and ×11 — but this fact does not mean further dose stops mattering. The armor model's `absorbed_amount` is capped by a small, slowly-regenerating pool (`armor_max=16`), not by the mitigation-cap fraction of `damage_raw` once that fraction is already irrelevantly large — so `damage_after_armor` continues to track `damage_raw` closely (§3c's observed +17.47 mean increase closely tracks the +18.6 raw-damage-weighted prediction). Kill speed corroborates this at the whole-match level: red's mean hits-to-kill dropped to exactly 3.00 with **zero variance** across all 13 wins (§4) — a direct, mechanically-explained consequence, not a fluke.

**Statistical caution, stated plainly:** the win-rate jump from P4 (27.6%) to P5 (43.3%) is **not statistically significant** by a two-proportion z-test (z=1.26, p=0.21) — n=30 per arm does not have the power to distinguish these two rates with confidence, and the Wilson CIs overlap substantially. The matched-seed comparison (§1a, 9 flips toward red vs. 4 away) is directionally corroborating but is not a formal significance test given the stochastic (not deterministic-replay) nature of the underlying matches. **The classification called here (COMPETITIVE) follows the same point-estimate convention used for every prior arm in this program** — it is the correct application of that convention, not a claim that the *true* underlying rate is proven to exceed 0.35.

**Implication for the program:** the damage axis is **not spent** — contrary to the P4 doc's own forward-looking note ("further escalation on this same lever ... is the lowest-information next experiment"), this arm shows the axis still has room and the marginal rate did not continue decelerating. Whether a sixth point would continue climbing, plateau, or reverse is now genuinely unknown and would be informative; this document does not extrapolate to a specific further multiplier.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p5_dmg11/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `weapon_fired`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Contract diffs: `contracts_data/weapons/{machine_gun,shrapnel_thrower}.yaml` vs `*_dmg11.yaml`; `contracts_data/loadouts/llm_qwen35_berserker.yaml` vs `llm_qwen35_berserker_dmg11.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction, per-tick-regenerating model; `_MITIGATION_CAP[STANDARD]=0.75`).
- Merge commit: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`), confirmed ancestor of this branch.
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md`, `-pair_p2_dmg55-battery.md`, `-pair_p3_armor8-battery.md`, `-pair_p4_dmg8-battery.md` (PR #184), `-composition-p4dmg8-covadv-r1-battery.md` (this session's companion arm).
- Prior claim corrected by this document: `docs/evidence/2026-07-24-pair_p4_dmg8-battery.md` §0 ("further escalation on this same lever ... is the lowest-information next experiment").
- No secrets, keys, or absolute paths included.
