# Pair-Sweep Arm P7 (mortar_r30 × red-dmg×24) Battery — H1 vs H2 Discriminating Test, Second Round (2026-07-25)

**Verdict:** **H2 (kill-speed-parity ceiling, confirmed and holding) is supported; H1 (re-acceleration) is falsified by both of its own named triggers.** Decided-match red (brawler) win rate is **21/30 = 0.7000**, 95% Wilson CI **[0.5212, 0.8334]** — the seventh point on the dose-response curve (×1 0%, ×3 3.4%, ×5.5 17.2%, ×8 27.6%, ×11 43.3%, ×16 56.7%, ×24 **70.0%**). The marginal rate on this step is **1.67 pp/unit**, down further from ×16's already-decelerated 2.67 pp/unit — continued deceleration, not re-acceleration. Match length stayed essentially flat (median 24.5 vs P6's 23.0, +1.5 ticks — no drop). `play_terminal_fraction=1.0` (30/30 elimination, zero aborts), `all_replay_valid=true`. A two-proportion z-test against P6 (pooled p=0.633, SE=0.124) gives **z=1.07, p=0.284** — not statistically significant, the expected shape for this program's adjacent-arm comparisons at n=30 (this is the seventh consecutive arm for which the adjacent-step comparison fails to reach significance). The two-steps-back comparison against P5 (13/30) does clear significance (z=2.08, p=0.037), and the three-steps-back comparison against P4 (8/29) is highly significant (z=3.26, p=0.0011) — consistent with a real, monotonic upward trend across the whole curve even though no single adjacent step is individually decisive.

**This document is a second, further discriminating test of the same H1/H2 pair P6 built** (per the overlay's own header comment, committed before the battery ran): P6 found ×16 scored 17/30 = 56.7% with a marginal rate of only 2.67 pp/unit (down sharply from ×11's 5.25 pp/unit) and match length plateaued (median 23.0, flat vs ×11), while red's hits-to-kill (mean 2.18) had already overtaken blue's (mean 2.62) — consistent with H2 but leaving a residual, unidentified capping mechanism as an open question. **Both of H1's named falsification triggers are false at ×24:** the marginal rate did not re-accelerate past 2.67 pp/unit (it fell further, to 1.67), and match length did not drop (it rose slightly, 23.0→24.5). Both of H2's named criteria hold: deceleration continued, and length stayed flat. Red's kill-speed advantage over blue widened further (§4) — all 21 red wins this arm took **exactly 2 hits, zero variance** — while win rate rose only 13.3pp, the same disproportion P6 flagged. The residual capping mechanism P6 could not identify remains unidentified here; this document does not claim to have found it either.

**Ledger:** `.onex_state/steel_onslaught/pair_p7_dmg24` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-DOSE24 worktree.
**Change under test:** two levers, exactly two, both additive contract files (new, not modifications):
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` — unmodified, held constant across every pair-sweep arm including this one (P1–P7).
2. Red loadout `loadout.llm.qwen35_berserker_dmg24` (`contracts_data/loadouts/llm_qwen35_berserker_dmg24.yaml`) — swaps both berserker weapons for damage-×24 variants (`machine_gun_dmg24`: damage 8 → 192; `shrapnel_thrower_dmg24`: damage 12 → 288), every other weapon field identical (confirmed via full-field diff, §3a).

Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p7_dmg24_qwen.yaml` is byte-identical to the merged P6 overlay except for the red loadout id, the dose-curve/hypothesis comment block, and isolated `.onex_state` ledger paths. Arena (`foundry_60_asym_v1`) untouched. A one-line addition to `tests/contracts/test_pilot_registry.py`'s `_PINNED_LOADOUT_PILOT_IDS` map pins the new loadout's provenance, matching the dmg3/dmg55/dmg8/dmg11/dmg16 pattern.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, matched to every prior pair-sweep arm. `battery_raw.jsonl` holds exactly 30 rows, seeds 5001–5030 present exactly once each, zero duplicates, zero gaps — **n=30 as pre-declared, no truncation, no optional stopping.**
**Baselines:** v1 anchor 0/30; P1 (×3) 1/29 = 0.0345 FAILED; P2 (×5.5) 5/29 = 0.1724 DIRECTIONAL; P3 (armor-8) 0/28 = 0.0000 FAILED (dead lever); P4 (×8) 8/29 = 0.2759 DIRECTIONAL; P5 (×11) 13/30 = 0.4333 COMPETITIVE (point estimate); P6 (×16) 17/30 = 0.5667 COMPETITIVE (point estimate).
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl` — not copied from `battery_summary.json` or stdout, though `battery_summary.json` is cross-checked and agrees exactly.

---

## 0. Pre-declared hypothesis (quoted verbatim from the overlay header, committed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p7_dmg24_qwen.yaml`:

> **H1** (ceiling continues to erode toward re-acceleration or the deceleration trend itself was noise): win rate re-accelerates past the 2.67pp/unit rate observed at x16, or match length starts dropping again after the x11->x16 plateau. Either signal would mean the "residual capping mechanism" P6 flagged as unexplained is NOT the whole story — raw lethality still has room to buy wins.
>
> **H2** (kill-speed-parity ceiling, confirmed and holding): win rate continues to decelerate at or below the 2.67pp/unit marginal rate set at x16 (i.e. lands at roughly 56.7-63% or lower), AND match length stays flat (~23 ticks) rather than dropping. This would further support the ceiling hypothesis and argue the residual, unexplained capping mechanism (not raw damage) is the binding constraint on win rate at this point in the curve.

The overlay explicitly states this arm "does NOT pre-favor either hypothesis" and that "n=30 cannot distinguish them" is a fully acceptable answer. Both predictions were written and committed (overlay header, commit `ea160e2b6d2b6c3e1f06ca562b6766385c1d3cfc`) before the battery ran.

---

## Method

Identical to the P1–P6 method:
- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded); all-30 basis also reported. Zero aborts this battery, so both bases are identical.
- **Dose verification, two layers:** contract-layer diff (only `damage` changed) and engine-layer reconstruction (`hit_resolved` paired with `armor_absorbed` at `sequence_in_tick + 1` in the same `(match_id, tick)`; `damage_raw = damage_after_armor + absorbed_amount`; weapon attribution from the closest preceding `weapon_fired` targeting the same defender in the same tick).

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | elimination 30/30, zero aborts |
| `play_terminal_fraction` | **1.0** (task gate ≥0.9 — PASS; codebase default ≥0.95 — also PASS) |
| Winner distribution | player.red 21, player.blue 9 |
| **Decided-match red win rate** | **21/30 = 0.7000** |
| **All-match red win rate** | **21/30 = 0.7000** (identical — zero aborts) |
| 95% Wilson CI | **[0.5212, 0.8334]** |
| Replay validity | 1/1 both players, all 30 matches |
| `failed_completions` distribution | 0 → 15 matches, 1 → 13 matches, 2 → 2 matches (sum = 17, matches §6 exactly) |

Independently recomputed from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once, zero duplicates, zero gaps) and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id)` = 30 for both `match_started` and `match_ended`, `mech_destroyed` on `mech.blue.01` × 21 / `mech.red.01` × 9). **Red wins: seeds 5001, 5002, 5004, 5005, 5006, 5007, 5008, 5009, 5013, 5014, 5019, 5020, 5021, 5023, 5024, 5025, 5026, 5027, 5028, 5029, 5030** (21 seeds).

`failed_completions` is LLM completion retry noise, not a match-failure signal — every one of the 30 matches still terminated validly (`terminal_class=elimination`, `end_reason=last_mech_standing`, `replay_validity` clean for both players) regardless of how many retries a given match needed.

This is the highest point estimate in the program to date. Per the program's point-estimate classification convention this is comfortably COMPETITIVE (`>=0.35`).

### 1a. Statistical comparisons

| Comparison | z | p | Significant at α=0.05? |
|---|---:|---:|---|
| P7 (21/30) vs P6 (17/30) — adjacent step | 1.07 | 0.284 | No |
| P7 (21/30) vs P5 (13/30) — two steps back | 2.08 | 0.037 | **Yes** |
| P7 (21/30) vs P4 (8/29) — three steps back | 3.26 | 0.0011 | **Yes** |

The adjacent-step comparison (P7 vs its immediate predecessor P6) is not significant — consistent with every adjacent-arm comparison in this program to date (P6 vs P5 was n.s. p=0.302; P5 vs P4 was n.s. p=0.21; composition vs P4 was n.s. p=0.312). **This program has never once produced a significant adjacent-arm comparison at n=30, and this arm does not break that pattern — a non-significant adjacent-step result here is the expected shape, not a defect, and should not be over-read as evidence against a real underlying trend.** The non-adjacent comparisons (two and three dose-steps back) do clear conventional significance, as they did for P6 (P6 vs P4 was the first non-adjacent comparison in the program to reach p<0.05); this is a second, independent instance of the same pattern — no single step is decisive, but the cumulative climb across steps is statistically separable from earlier points on the curve.

## 2. Match length

| Metric | P7 (×24) | P6 (×16) | P5 (×11) | P4 (×8) | P2 (×5.5) | P1 (×3) |
|---|---:|---:|---:|---:|---:|---:|
| min ticks | 13 | 15 | 14 | 14 (elim) | 18 | 13 |
| median ticks | **24.5** | 23.0 | 23.0 | 24 | 30 | 31 |
| mean ticks | **24.67** | 23.3 | 24.43 | 24.86 (elim-only) | 30.1 | 31.4 |
| max ticks | 34 | 40 | 39 | 38 | 50 | 61 |

Sorted durations (n=30): 13, 16, 17, 18, 19, 20, 21, 21, 21, 22, 22, 23, 23, 24, 24, 25, 25, 25, 27, 27, 28, 28, 29, 29, 30, 31, 32, 32, 34, 34.

Match length is essentially flat against P6 — median rose marginally (23.0 → 24.5, +1.5 ticks), mean rose marginally (23.3 → 24.67) — a small increase, not the drop H1 would predict. The P1→P2→P4→P5→P6 monotonic-shortening-then-plateau trend does not resume shortening at P7; if anything this arm sits a hair above P6 and P5, still well below P1/P2/P4. This is the second dose step in a row (after P6) where match length has not moved in the direction raw lethality escalation would predict if it were still buying wins the way it did at P1→P5 — a second independent signal, alongside the marginal-rate deceleration (§8), that something continues to cap further gains at this dose level.

## 3. Dose verification (raw weapon damage)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `machine_gun.yaml` → `machine_gun_dmg24.yaml` | `damage: 8` | `damage: 192` | `damage` only (full-field diff over every other key confirms zero other change) |
| `shrapnel_thrower.yaml` → `shrapnel_thrower_dmg24.yaml` | `damage: 12` | `damage: 288` | `damage` only, same identical-field guarantee |

`git diff HEAD` against `machine_gun.yaml`, `shrapnel_thrower.yaml`, `llm_qwen35_berserker.yaml`, `sniper_ironclad_mortar_r30.yaml`, and `foundry_60_asym_v1.yaml` (every baseline this arm depends on) returns **empty** — zero existing files modified.

`llm_qwen35_berserker_dmg24.yaml` swaps only the weapon-slot module IDs (`weapons: [weapon.light.machine_gun_dmg24, weapon.light.shrapnel_thrower_dmg24]`); every other field (chassis, boiler, pilot, sensors, cooling, armor, gizmos, budgets) is byte-identical to the baseline berserker loadout.

### 3b. Engine layer — dose landed exactly as pre-registered

| Weapon | Baseline raw | P7 raw observed | Pre-registered prediction (overlay header) | Match? |
|---|---:|---:|---|---|
| `machine_gun_dmg24` | 5 (int(8×0.7)) | **134** (30/45 red hits, zero variance) | int(192×0.7)=134 | **exact match** |
| `shrapnel_thrower_dmg24` | 7 (int(12×0.6)) | **172** (15/45 red hits, zero variance) | int(288×0.6)=172 | **exact match** |

All 91 `hit_resolved` events in the battery (45 red-caused, 46 blue-caused) paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches, zero unattributed weapon IDs on the red side.

### 3c. Armor saturation — mechanism continues to hold at ×24

| | P7 (×24) | P6 (×16) | P5 (×11) |
|---|---:|---:|---:|
| `armor_after == 0` on red hits | **45/45 = 100%** | 43/43 = 100% | 57/57 = 100% |
| Mean damage-after-armor per hit | **136.67** | 84.93 | 58.04 |
| Median | 131 | 83 | 57 |

The same mechanism the P5 doc identified and P6 replicated continues to hold at a fourth consecutive dose step: `absorbed_amount` is bounded by the fixed, small armor pool (16, regenerating per-tick), never by the mitigation-cap fraction of `damage_raw` (already irrelevantly large at every dose from ×8 upward). Predicted increase in mean damage-after-armor from raw-damage growth alone (hit-weighted, using P7's 30/15 machine-gun/shrapnel split, raw-damage deltas ×16→×24: machine gun 89→134 = +45; shrapnel 115→172 = +57): `(30×45 + 15×57)/45 = 49.0`; **observed increase is 136.67 − 84.93 = 51.73** — within noise of the prediction, confirming the mechanism holds at this fourth consecutive dose step.

## 4. Hits-to-kill — the sharpest single finding in this document

| | P7 (×24) | P6 (×16) | P5 (×11) |
|---|---:|---:|---:|
| **Red kills blue — mean hits (21 kills)** | **2.00** (median 2, **zero variance — every single one of the 21 kills took exactly 2 hits**) | 2.18 (median 2, `{2:14, 3:3}`) | 3.00 (median 3, zero variance, all 13 at exactly 3) |
| Blue kills red — mean hits (9 kills) | **2.67** (median 3, `{2:3, 3:6}`) | 2.62 (median 3, `{2:5, 3:8}`) | 2.59 (17 kills) |

At ×16, red's kill speed had already overtaken blue's (2.18 vs 2.62). **At ×24, red's kill speed has widened that gap further and dropped to a hard floor: every single red kill this arm took exactly 2 hits, zero variance.** This is the natural floor for a kill-count statistic bounded below by "not zero" — red cannot kill blue faster than 2 hits given the engine's mechanics, and it now does so every single time. Blue's own kill speed against red is essentially unchanged (2.62 → 2.67, well within noise). **Despite this widened, now-floored kill-speed advantage, win rate rose only 13.3pp (56.7%→70.0%)** — the same disproportion P6 identified between hit-count dominance and win-rate gain, replicated and intensified at this fourth dose step. This is the strongest single piece of evidence in this document for a residual capping mechanism beyond raw hit-count parity: red's kill speed genuinely cannot go faster, yet blue still wins 30% of matches. `mech_destroyed` counts corroborate the win tally exactly: blue destroyed in 21 matches (= the 21 red wins), red destroyed in 9 matches (= the 9 blue wins), 21+9=30, zero unexplained destructions.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate | P6 (×16) |
|---|---:|---:|---:|---:|
| red (brawler) | 320 | 13 | **0.0406** | 0.0298 |
| blue (sniper) | 320 | 33 | **0.1031** | 0.1026 |
| all-card sanity, both seats | 800/1600 (each seat) | — | 0.5000 (mechanical, confirms 5-of-10 register structure held) | 0.500 |

Both seats' utility keep-rates stay in the same low range as every prior arm — a small uptick for red (0.030→0.041) sits within the noise this statistic has shown across arms; no new systematic effect from the higher dose.

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 337 |
| `llm_completion_resolved` | 320 |
| `llm_completion_failed` | 17 |
| `finish_reason` distribution | `stop`: 320/320 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 320/320 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **0/30** |

337 requested − 320 resolved = 17, matching `llm_completion_failed` exactly, zero gap between resolved and `plan_committed`. Every in-match completion failure was recovered by retry; no match in this battery reached an unrecovered abort.

---

## 7. Merge / additivity verification

- PR #170 (P1/P2/P3 framework, `main` commit `255f23062d1ddb845faf3e2765bad6ba4e0521f0`) and PR #191 (P6, `main` commit `93aaa43d1fd5fb713a6cc3ceb157a3ea5f3aca97`) both confirmed ancestors of this branch's HEAD via `git merge-base --is-ancestor`.
- `git diff HEAD` against every baseline file this arm depends on (`machine_gun.yaml`, `shrapnel_thrower.yaml`, `llm_qwen35_berserker.yaml`, `sniper_ironclad_mortar_r30.yaml`, `foundry_60_asym_v1.yaml`) returns **empty** — zero existing files modified.
- The 5 files this arm's commit touches: 3 new additive contract files (`machine_gun_dmg24.yaml`, `shrapnel_thrower_dmg24.yaml`, `llm_qwen35_berserker_dmg24.yaml`), 1 new additive overlay (`tactical_split_overdeal_utility_asym_pair_p7_dmg24_qwen.yaml`), plus one pinned-provenance test entry (`tests/contracts/test_pilot_registry.py`, additive dict entry, same pattern as dmg3/dmg55/dmg8/dmg11/dmg16) — no existing loadout/weapon/overlay/arena file is modified.

---

## 8. Dose-response placement

| Dose | Arm | Decided-basis win rate | Classification |
|---|---|---:|---|
| ×1 | v1 anchor | 0/30 = 0.0000 | (null) |
| ×3 | P1 | 1/29 = 0.0345 | FAILED |
| ×5.5 | P2 | 5/29 = 0.1724 | DIRECTIONAL |
| ×8 | P4 | 8/29 = 0.2759 | DIRECTIONAL |
| ×11 | P5 | 13/30 = 0.4333 | COMPETITIVE (point estimate) |
| ×16 | P6 | 17/30 = 0.5667 | COMPETITIVE (point estimate) |
| ×24 | **P7 (this arm)** | **21/30 = 0.7000** | **COMPETITIVE (point estimate)** |

| Step | Δdose | Δ win rate (pp) | Marginal rate (pp/dose-unit) |
|---|---:|---:|---:|
| ×1 → ×3 | 2.0 | +3.45 | 1.72 |
| ×3 → ×5.5 | 2.5 | +13.79 | 5.52 |
| ×5.5 → ×8 | 2.5 | +10.34 | 4.14 |
| ×8 → ×11 | 3.0 | +15.74 | 5.25 |
| ×11 → ×16 | 5.0 | +13.33 | 2.67 |
| ×16 → ×24 | 8.0 | +13.33 | **1.67 — down again** |

Seven points now show a marginal-rate series of 1.72 → 5.52 → 4.14 → 5.25 → 2.67 → 1.67 — the third consecutive deceleration (P5→P6→P7 marginal rates: 5.25 → 2.67 → 1.67), the clearest run of monotonic deceleration yet seen in this series. Per the methodological lesson this program's own record already carries: shape claims from adjacent points at n=30/arm are unreliable in isolation, but three consecutive decelerating steps is a stronger signal than any single step alone, and this document reports that pattern as the most notable feature of the updated curve without asserting a specific functional form for the full seven-point series.

---

## Verdict

**H2 (kill-speed-parity ceiling, confirmed and holding) is supported; H1 is falsified by both of its own named triggers, though n=30 per arm still leaves real uncertainty in the underlying rate.**

- **Win rate:** 21/30 = 0.7000, Wilson CI [0.5212, 0.8334] — the highest point estimate in the program, comfortably inside COMPETITIVE by the program's point-estimate convention. Not statistically separated from P6 (z=1.07, p=0.284) — the expected shape given this program has never once produced a significant adjacent-arm comparison at n=30. It does clear significance against P5, two steps back (z=2.08, p=0.037), and against P4, three steps back (z=3.26, p=0.0011).
- **H1's first trigger (re-acceleration past 2.67 pp/unit) is false:** the marginal rate fell further, to 1.67 pp/unit — the third consecutive deceleration in the series.
- **H1's second trigger (match length dropping again) is false:** match length rose slightly (median 23.0 → 24.5), not dropped.
- **H2's criteria both hold:** deceleration continued below the 2.67 pp/unit threshold, and match length stayed flat (small rise, not a drop).
- **Hits-to-kill:** red's kill speed dropped to a hard floor — every one of 21 kills took exactly 2 hits, zero variance — widening its already-established advantage over blue (mean 2.67, essentially unchanged from P6's 2.62). Win rate rose only 13.3pp despite this widened, floored advantage — the same disproportion P6 flagged between raw kill-speed dominance and win-rate gain, replicated and intensified. This remains the strongest evidence for an unidentified residual capping mechanism (plausibly approach/exposure time or blue's range advantage); this document does not claim to have isolated it.
- **Dose verification** (contract diff + engine-layer reconstruction) confirms ×24 landed exactly as pre-registered, with zero variance, at both layers; armor saturation (45/45, 100%) and the damage-after-armor tracking-raw-damage mechanism (observed +51.73 vs a raw-weighted prediction of +49.0) both replicate the corrected P5 mechanism for a fourth consecutive dose step.

**One internal inconsistency in the pre-registered hypothesis text itself, flagged rather than resolved silently:** H2's own illustrative percentage range ("lands at roughly 56.7-63% or lower") is arithmetically inconsistent with its own formal, disjunctive criterion. A marginal rate literally at 2.67 pp/unit sustained over the 8 dose-units from ×16 to ×24 would project to 56.7 + (2.67×8) ≈ 78%, not 63% — the 56.7–63% illustrative band implies a much lower marginal rate (~0.8 pp/unit) than the criterion's own stated 2.67 pp/unit ceiling. The observed 70.0% satisfies the formal criterion (marginal rate below 2.67 pp/unit — it is 1.67 — and no match-length drop) but falls outside the hypothesis's own illustrative percentage band. This document reports the raw number and the mismatch rather than picking whichever framing reads cleaner; the formal, falsifiable criterion is what is scored, not the illustrative aside.

**Honest statement on what this arm does and does not settle:** the marginal-rate deceleration is now a three-step trend (5.25 → 2.67 → 1.67), the strongest such run in the program, and match length has not resumed shortening for two arms running. Combined with the hits-to-kill floor, the directional case for H2 is stronger here than it was at P6. But the Wilson CI [0.521, 0.833] is still wide at n=30, the adjacent-step z-test is (as always in this program) non-significant, and this document does not claim the true underlying rate or ceiling is pinned down — only that, on the specific falsifiable criteria the overlay pre-declared, H1's two named triggers are both false and H2's two named criteria both hold.

---

## 9. Limitations

- **n=30 adjacent-arm power.** As in every prior arm, a single adjacent-step comparison at n=30 per arm does not have the power to distinguish rates in the 55–70% range with high confidence (P7 vs P6: z=1.07, p=0.284). This is pre-declared, expected, and not treated here as evidence against a real trend — the non-adjacent comparisons (§1a) carry more of the statistical weight for the overall climb.
- **Hypothesis-text internal inconsistency.** H2's illustrative percentage band (56.7–63%) does not match its own formal marginal-rate criterion's implied ceiling (~78% at a sustained 2.67 pp/unit) — flagged above in the Verdict, not resolved by cherry-picking an interpretation. The formal criterion, not the illustrative band, is what this document scores.
- **Unlinked run.log.** Prior arms in this program (e.g. P5, P6) cited a per-seed harness invocation log to state which seeds needed a retry at the process level (distinct from in-match `llm_completion_failed` retries). No such run.log exists under `.onex_state/steel_onslaught/pair_p7_dmg24/` or elsewhere in this worktree for this arm — only `battery_raw.jsonl`, `battery_summary.json`, `events.sqlite3`, and `leaderboard.sqlite3` are present. This document therefore reports `failed_completions` (in-match LLM retry counts, §1/§6, all captured in `battery_raw.jsonl` and `events.sqlite3`) but cannot make the P5/P6-style claim about seed-level harness-attempt counts one way or the other — that provenance is simply absent, not verified-clean.
- **No re-run to chase a different number.** n=30, seeds 5001–5030, was pre-declared before this battery ran and is reported as-is; the battery completed all 30 seeds with zero aborts, so there is no truncation to disclose.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p7_dmg24/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `weapon_fired`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `utility_deployed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Contract diffs: `contracts_data/weapons/{machine_gun,shrapnel_thrower}.yaml` vs `*_dmg24.yaml`; `contracts_data/loadouts/llm_qwen35_berserker.yaml` vs `llm_qwen35_berserker_dmg24.yaml`.
- Pinned provenance test: `tests/contracts/test_pilot_registry.py::_PINNED_LOADOUT_PILOT_IDS`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction, per-tick-regenerating model).
- Merge commits: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`, P1/P2/P3 framework); `93aaa43d1fd5fb713a6cc3ceb157a3ea5f3aca97` (PR #191, `main`, P6) — both confirmed ancestors of this branch.
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md`, `-pair_p2_dmg55-battery.md`, `-pair_p3_armor8-battery.md`, `-pair_p4_dmg8-battery.md`, `-pair_p5_dmg11-battery.md`, `-pair_p6_dmg16-battery.md`.
- Pre-declared hypothesis extended by this document: `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md` (H1/H2 re-declaration for ×24, quoted verbatim in §0 above from the overlay header).
- No secrets, keys, or absolute paths included.
