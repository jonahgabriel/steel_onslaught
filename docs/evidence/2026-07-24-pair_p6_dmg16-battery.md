# Pair-Sweep Arm P6 (mortar_r30 × red-dmg×16) Battery — H1 vs H2 Discriminating Test (2026-07-24)

**Verdict:** **H2 (kill-speed-parity ceiling) is better supported than H1 (continued linearity), though neither pre-registered prediction lands exactly and n=30 does not prove either.** Decided-match red (brawler) win rate is **17/30 = 0.5667**, 95% Wilson CI **[0.3920, 0.7262]** — the sixth point on the dose-response curve (×1 0%, ×3 3.4%, ×5.5 17.2%, ×8 27.6%, ×11 43.3%, ×16 **56.7%**). The marginal rate on this step is **2.67 pp/unit**, down sharply from ×11's 5.25 pp/unit — deceleration, not continued acceleration or steady linear climb. `play_terminal_fraction=1.0` (30/30 elimination, zero aborts), `all_replay_valid=true`. A two-proportion z-test against P5 (pooled p=0.500, SE=0.129) gives **z=1.03, p=0.302** — not statistically significant.

**The pre-registered discriminating evidence:** H1 predicted ~65–70% by extrapolating the ~4–5.5 pp/unit marginal rate; H2 predicted an asymptote near ~50% because red's kill speed had already hit exact parity with blue's (~3 hits, matching blue's own ~2–3) at ×11. **Observed 56.7% sits 10.8pp below H1's midpoint (67.5%) and only 6.7pp above H2's ~50%** — numerically closer to H2. The hits-to-kill data corroborates the H2 mechanism directly, and more strongly than pre-registered: red's mean hits-to-kill **dropped to 2.18** (median 2, n=17) — **below** blue's own 2.62 (median 3, n=13). Red has not merely reached parity with blue's kill speed; it has **overtaken** it, yet win rate rose only 13.3pp (43.3%→56.7%), not sharply toward a red-dominant regime. This is consistent with a ceiling mechanism operating on something beyond raw hit-count parity — plausibly approach/exposure-time or blue's range advantage still costing red actions before it can capitalize on its now-superior kill speed — but this document does not claim to have identified that finer mechanism; it reports the hit-count crossing as a fact and leaves the deeper cause as an open question.

**Ledger:** `.onex_state/steel_onslaught/pair_p6_dmg16` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-COMP-P5 worktree (`steel_onslaught_p6`).
**Change under test:** two levers, exactly two, both additive contract files (new, not modifications):
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` — unmodified, held constant across every pair-sweep arm including this one.
2. Red loadout `loadout.llm.qwen35_berserker_dmg16` (`contracts_data/loadouts/llm_qwen35_berserker_dmg16.yaml`) — swaps both berserker weapons for damage-×16 variants (`machine_gun_dmg16`: damage 8 → 128; `shrapnel_thrower_dmg16`: damage 12 → 192), every other weapon field identical (confirmed via full-field diff, §3a).

Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p6_dmg16_qwen.yaml` is byte-identical to the merged P5 overlay except for the red loadout id, the dose-curve/hypothesis comment block, and isolated `.onex_state` ledger paths. Arena (`foundry_60_asym_v1`) untouched. A one-line addition to `tests/contracts/test_pilot_registry.py`'s `_PINNED_LOADOUT_PILOT_IDS` map pins the new loadout's provenance (`test_all_shipped_loadouts_have_exact_registered_provenance` requires every shipped loadout YAML to have an exact pinned entry — this bit the P5 PR on first push; fixed proactively here before running the battery).
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, per-seed isolated invocation (one process per seed, shared append-mode state root, `--fresh` only on seed 5001, up to 2 attempts per seed on a 420s timeout). Two seeds (5018, 5026) hit a transient `LlmTransportError` on attempt 1 and succeeded on attempt 2 — the raw file has exactly 30 rows, seeds 5001–5030, zero duplicates, zero gaps.
**Baselines:** v1 anchor 0/30; P1 (×3) 1/29 = 0.0345 FAILED; P2 (×5.5) 5/29 = 0.1724 DIRECTIONAL; P3 (armor-8) 0/28 = 0.0000 FAILED (dead lever); P4 (×8) 8/29 = 0.2759 DIRECTIONAL; P5 (×11) 13/30 = 0.4333 COMPETITIVE (point estimate).
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl` — not copied from `battery_summary.json` or stdout.

---

## 0. Pre-registered predictions (written before reading results)

Committed in this overlay's own header comment before the battery ran, per operator instruction, following P5's own finding that the armor-saturation hypothesis was falsified:

- **Engine-layer dose prediction** (blue `chassis_class=heavy`): `machine_gun_dmg16` raw = `int(128 × 0.7) = 89`; `shrapnel_thrower_dmg16` raw = `int(192 × 0.6) = 115`. **Both matched the reconstructed engine-layer data exactly, zero variance** (§3b).
- **H1 (continued ~linear marginal rate):** the five-point marginal-rate series (1.72, 5.52, 4.14, 5.25 pp/unit across ×1→×3→×5.5→×8→×11) settles at roughly 4–5.5 pp/unit after the initial ramp; ×16 is +5 dose-units over ×11 (43.3%), so ~5pp/unit predicts **roughly 65–70%**.
- **H2 (kill-speed-parity ceiling):** at ×11, red's kill speed against blue hit exactly 3 hits with zero variance across all 13 wins — close to blue's own long-standing ~2–3 hits against red. Once both seats need a comparable number of hits, the match becomes a first-strike/initiative race, and additional red lethality cannot buy much beyond winning that race — predicting an outcome asymptote **near ~50%**.
- Neither prediction was favored going in; ×16 was chosen specifically because it is far enough past ×11 to separate the two.

---

## Method

Identical to the P1–P5 method:
- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded); all-30 basis also reported. Zero aborts this battery, so both bases are identical.
- **Dose verification, two layers:** contract-layer diff (only `damage` changed) and engine-layer reconstruction (`hit_resolved` paired with `armor_absorbed` at `sequence_in_tick + 1` in the same `(match_id, tick)`; `damage_raw = damage_after_armor + absorbed_amount`; weapon attribution from the closest preceding `weapon_fired` targeting the same defender in the same tick).

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | elimination 30/30, zero aborts |
| `play_terminal_fraction` | **1.0** (task gate ≥0.9 — PASS; codebase default ≥0.95 — also PASS) |
| Winner distribution | player.red 17, player.blue 13 |
| **Decided-match red win rate** | **17/30 = 0.5667** |
| **All-match red win rate** | **17/30 = 0.5667** (identical — zero aborts) |
| 95% Wilson CI | **[0.3920, 0.7262]** |
| Replay validity | 1/1 both players, all 30 matches |

Independently recomputed from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once, zero duplicates, zero gaps) and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id)` = 30 for both `match_started` and `match_ended`). **Red wins: seeds 5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5010, 5017, 5018, 5019, 5020, 5023, 5024, 5026, 5029** (17 seeds, all `elimination`/`last_mech_standing`, corroborated by `mech_destroyed` on `mech.blue.01` × 17).

This is the highest point estimate in the program to date — the first arm where red wins a majority of decided matches. Per the program's point-estimate classification convention this is comfortably COMPETITIVE (`>=0.35`).

### 1a. Statistical comparisons

| Comparison | z | p | Significant at α=0.05? |
|---|---:|---:|---|
| P6 (17/30) vs P5 (13/30) | 1.03 | 0.302 | No |
| P6 (17/30) vs P4 (8/29) | 2.26 | 0.024 | **Yes** (P6 vs. the ×8 baseline, two dose-steps back, does clear conventional significance — the only pairwise comparison in the whole program to do so) |

The step-to-step comparison (P6 vs its immediate predecessor P5) is not significant, consistent with every other adjacent-arm comparison in this program (P5 vs P4 was also n.s., p=0.207; composition vs P4 was n.s., p=0.312). The non-adjacent P6-vs-P4 comparison, spanning two dose steps, is the first pairwise comparison in the program to clear p<0.05 — a useful data point on the overall trend even though no single step is individually decisive.

## 2. Match length

| Metric | P6 (×16) | P5 (×11) | P4 (×8) | P2 (×5.5) | P1 (×3) |
|---|---:|---:|---:|---:|---:|
| min ticks | 15 | 14 | 14 (elim) | 18 | 13 |
| median ticks | **23.0** | 23.0 | 24 | 30 | 31 |
| mean ticks | **23.3** | 24.43 | 24.86 (elim-only) | 30.1 | 31.4 |
| max ticks | 40 | 39 | 38 | 50 | 61 |

Match length is essentially flat against P5 (median identical at 23.0, mean marginally lower) — the monotonic shortening trend from P1→P2→P4→P5 (31→30→24→23) has plateaued rather than continuing to shrink at P6. This is a second piece of evidence (alongside the marginal win-rate deceleration) that something is capping further gains at this dose level, independent of the win-rate statistic itself.

## 3. Dose verification (raw weapon damage)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `machine_gun.yaml` → `machine_gun_dmg16.yaml` | `damage: 8` | `damage: 128` | `damage` only (full-field diff over every other key confirms zero other change) |
| `shrapnel_thrower.yaml` → `shrapnel_thrower_dmg16.yaml` | `damage: 12` | `damage: 192` | `damage` only, same identical-field guarantee |

`git diff HEAD` against `machine_gun.yaml`, `shrapnel_thrower.yaml`, `llm_qwen35_berserker.yaml`, `sniper_ironclad_mortar_r30.yaml`, and `foundry_60_asym_v1.yaml` (every baseline this arm depends on) returns **empty** — zero existing files modified.

`match_started` runtime snapshot for seed 5001 confirms wiring: `mech.red.01.loadout_id = "loadout.llm.qwen35_berserker_dmg16"` (light, `hp_max=60`, `armor_max=6`); `mech.blue.01.loadout_id = "loadout.llm.qwen35_sniper_ironclad_mortar_r30"` (heavy, `hp_max=160`, `armor_max=16`).

### 3b. Engine layer — dose landed exactly as pre-registered

| Weapon | Baseline raw | P6 raw observed | Pre-registered prediction (§0) | Match? |
|---|---:|---:|---|---|
| `machine_gun_dmg16` | 5 (int(8×0.7)) | **89** (33/43 red hits, zero variance) | int(128×0.7)=89 | **exact match** |
| `shrapnel_thrower_dmg16` | 7 (int(12×0.6)) | **115** (10/43 red hits, zero variance) | int(192×0.6)=115 | **exact match** |

All 95 `hit_resolved` events in the battery (43 red-caused, 52 blue-caused) paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches, zero unattributed weapon IDs on the red side.

### 3c. Armor saturation — mechanism continues to hold at ×16

| | P6 (×16) | P5 (×11) | P4 (×8) |
|---|---:|---:|---:|
| `armor_after == 0` on red hits | **43/43 = 100%** | 57/57 = 100% | 68/68 = 100% |
| Mean damage-after-armor per hit | **84.93** | 58.04 | 40.57 |
| Median | 83 | 57 | 41 |

The same mechanism the P5 doc traced (corrected from the P4 doc's original, falsified saturation hypothesis) continues to hold: `absorbed_amount` is bounded by the fixed, small armor pool (16, regenerating per-tick), never by the mitigation-cap fraction of `damage_raw` (already irrelevantly large at every dose from ×8 upward). Predicted increase in mean damage-after-armor from raw-damage growth alone (hit-weighted, using P6's 33/10 machine-gun/shrapnel split): `(33×28 + 10×36)/43 ≈ 29.86` (raw increases: machine gun 61→89 = +28; shrapnel 79→115 = +36); **observed increase is 84.93 − 58.04 = 26.89** — within noise of the prediction, confirming the mechanism holds at this third consecutive dose step.

## 4. Hits-to-kill — the sharpest single finding in this document

| | P6 (×16) | P5 (×11) | P4 (×8) | P2 (×5.5) |
|---|---:|---:|---:|---:|
| **Red kills blue — mean hits (17 kills)** | **2.18** (median 2, `{2:14, 3:3}`) | 3.00 (median 3, zero variance, all 13 at exactly 3) | 4.13 (n=8) | 6.40 |
| Blue kills red — mean hits (13 kills) | **2.62** (median 3, `{2:5, 3:8}`) | 2.59 (17 kills) | 2.38 (21 kills) | 2.67 |

At ×11, red's kill speed hit exact parity with blue's long-standing ~2–3 hit range (P5 doc). **At ×16, red's kill speed has overtaken blue's** — 2.18 mean hits vs blue's 2.62 — the first time in the entire program that red's hits-to-kill is *lower* than blue's. This directly corroborates the H2 kill-speed-convergence mechanism, and more strongly than the pre-registered prediction anticipated: the prediction was that red would reach parity and the win-rate gain would then plateau; the data shows red has gone *past* parity, yet the win-rate gain (43.3%→56.7%, +13.3pp) is modest relative to how large the hit-count crossing is. This is consistent with, but not fully explained by, a pure hit-count-parity ceiling — some other factor (approach/exposure time, blue's range advantage letting it land early hits before red is even in range, or simple match-to-match variance in who gets the first effective shot) likely still caps red's win rate even after its kill speed advantage. This document reports the crossing as an established fact from the ledger; it does not claim to have isolated the residual capping mechanism. `mech_destroyed` counts corroborate the win tally exactly: blue destroyed in 17 matches (= the 17 red wins), red destroyed in 13 matches (= the 13 blue wins), 17+13=30, zero unexplained destructions.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate | P5 (×11) |
|---|---:|---:|---:|---:|
| red (brawler) | 302 | 9 | **0.0298** | 0.0348 |
| blue (sniper) | 302 | 31 | **0.1026** | 0.1076 |
| all-card sanity, both seats | 755/1510 (each seat) | — | 0.5000 (mechanical) | 0.500 |

Both seats' utility keep-rates stay flat against P5 — no new effect from the higher dose.

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 325 |
| `llm_completion_resolved` | 302 |
| `llm_completion_failed` | 23 |
| `finish_reason` distribution | `stop`: 302/302 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 302/302 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **0/30** |

325 requested − 302 resolved = 23, matching `llm_completion_failed` exactly, zero gap between resolved and `plan_committed`. Every in-match completion failure was recovered by retry; the two seed-level transport failures (seeds 5018, 5026, §header) were recovered by the per-seed isolation harness at the process level.

---

## 7. Merge / additivity verification

- PR #170 merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0` — confirmed an ancestor of this branch's HEAD via `git merge-base --is-ancestor`.
- `git diff HEAD` against every baseline file this arm depends on (machine_gun, shrapnel_thrower, berserker loadout, mortar_r30 loadout, arena) returns **empty**.
- The 5 files this arm touches: 4 new additive contract files (`machine_gun_dmg16.yaml`, `shrapnel_thrower_dmg16.yaml`, `llm_qwen35_berserker_dmg16.yaml`, `tactical_split_overdeal_utility_asym_pair_p6_dmg16_qwen.yaml`) plus one pinned-provenance test entry (`tests/contracts/test_pilot_registry.py`, additive dict entry, same pattern as dmg3/dmg55/dmg8/dmg11) — no existing loadout/weapon/overlay/arena file is modified.

---

## 8. Dose-response placement

| Dose | Arm | Decided-basis win rate | Classification |
|---|---|---:|---|
| ×1 | v1 anchor | 0/30 = 0.0000 | (null) |
| ×3 | P1 | 1/29 = 0.0345 | FAILED |
| ×5.5 | P2 | 5/29 = 0.1724 | DIRECTIONAL |
| ×8 | P4 | 8/29 = 0.2759 | DIRECTIONAL |
| ×11 | P5 | 13/30 = 0.4333 | COMPETITIVE (point estimate) |
| ×16 | **P6 (this arm)** | **17/30 = 0.5667** | **COMPETITIVE (point estimate)** |

| Step | Δdose | Δ win rate (pp) | Marginal rate (pp/dose-unit) |
|---|---:|---:|---:|
| ×1 → ×3 | 2.0 | +3.45 | 1.72 |
| ×3 → ×5.5 | 2.5 | +13.79 | 5.52 |
| ×5.5 → ×8 | 2.5 | +10.34 | 4.14 |
| ×8 → ×11 | 3.0 | +15.74 | 5.25 |
| ×11 → ×16 | 5.0 | +13.33 | **2.67 — down again** |

Six points now show a marginal-rate series of 1.72 → 5.52 → 4.14 → 5.25 → 2.67 — not monotonic in either direction, and this is the third time in six points that the program's dose-curve-shape characterization would need revision if forced to fit one ("accelerating" fit the first two steps; "saturating" fit the third; "roughly linear" fit through the fourth; this fifth step breaks all three). Per the methodological lesson this session's own LEARNINGS append already records: shape claims from adjacent points at n=30/arm are unreliable, and this document does not fit or name a shape for the six-point series.

---

## Verdict

**H2 (kill-speed-parity ceiling) is better supported than H1 (continued linearity), but neither is proven and n=30 leaves real uncertainty.**

- **Win rate:** 17/30 = 0.5667, Wilson CI [0.3920, 0.7262] — the highest point estimate in the program, the first majority-win arm, comfortably inside COMPETITIVE by the program's point-estimate convention. Not statistically separated from P5 (z=1.03, p=0.302), though it does clear significance against the earlier P4 baseline two arms back (z=2.26, p=0.024) — the only pairwise comparison in the program to do so.
- **Marginal rate decelerated sharply** (5.25 → 2.67 pp/unit), the third deceleration in six points — inconsistent with H1's continued-linearity extrapolation, which predicted the rate would hold near 5pp/unit.
- **Match length plateaued** (median 23.0, flat vs P5) rather than continuing to shorten — a second independent signal (alongside the marginal-rate deceleration) that something is capping further gains.
- **Hits-to-kill crossed:** red's mean hits-to-kill (2.18) is now *below* blue's (2.62) — the first time in the program red has overtaken blue's kill speed, not merely matched it. This directly corroborates the kill-speed-convergence mechanism H2 is built on, and shows it operating even more strongly than the pre-registered hypothesis anticipated. That the win-rate gain (+13.3pp) is nonetheless modest relative to this crossing suggests a residual capping factor beyond simple hit-count parity (plausibly approach/exposure time or blue's range advantage) that this document identifies as an open question, not a solved one.
- **Dose verification** (contract diff + engine-layer reconstruction) confirms ×16 landed exactly as pre-registered, with zero variance, at both layers; armor saturation (43/43, 100%) and the damage-after-armor tracking-raw-damage mechanism (observed +26.89 vs a raw-weighted prediction of +29.86) both replicate the corrected P5 mechanism for a third consecutive dose step.

**Honest statement on what this arm does and does not settle:** the observed win rate (56.7%) sits between the two pre-registered predictions, numerically closer to H2's ~50% than to H1's 65–70%, and the marginal-rate deceleration plus flat match length both point the same direction as H2. But the hits-to-kill crossing is a genuinely new phenomenon this document does not fully explain, and the win-rate CI [0.392, 0.726] is wide enough that a true rate anywhere from "roughly even" to "solidly favors red" remains statistically plausible at n=30. This is reported as **H2 better supported, not confirmed** — a fully legitimate outcome given the pre-registration explicitly allowed for "cannot distinguish" as an acceptable answer, and this document goes one step further than that only because the hits-to-kill crossing gives a genuine (if incomplete) mechanistic reason to lean toward H2 rather than treating the two hypotheses as equally live.

---

## Limitations

- **Uncontrolled range-30 standoff (`harpoon_gun`), now identified.** §Verdict above flags "blue's range advantage" as a plausible residual capping factor without naming it precisely. It is now named: `artillery_mortar` was cut to range 30 (the approach-fix lever), but `harpoon_gun` stayed at range 30, uncapped, through this arm and every other arm in the P1–P7 sweep. Blue therefore retained an ~18–22 cell standoff advantage against red's longest weapon (`machine_gun`, range 12) that this arm's design did not control for. Found post hoc during the SO-RANGECAP design pass (PR #197); does not change any figure reported above. See OMN-15119.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p6_dmg16/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `weapon_fired`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Contract diffs: `contracts_data/weapons/{machine_gun,shrapnel_thrower}.yaml` vs `*_dmg16.yaml`; `contracts_data/loadouts/llm_qwen35_berserker.yaml` vs `llm_qwen35_berserker_dmg16.yaml`.
- Pinned provenance test: `tests/contracts/test_pilot_registry.py::_PINNED_LOADOUT_PILOT_IDS`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction, per-tick-regenerating model).
- Merge commit: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`), confirmed ancestor of this branch.
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md`, `-pair_p2_dmg55-battery.md`, `-pair_p3_armor8-battery.md`, `-pair_p4_dmg8-battery.md`, `-pair_p5_dmg11-battery.md`, `-composition-p4dmg8-covadv-r1-battery.md`.
- Prior hypothesis corrected/refined by this document: `docs/evidence/2026-07-24-pair_p5_dmg11-battery.md` (H1/H2 pre-registration).
- No secrets, keys, or absolute paths included.
