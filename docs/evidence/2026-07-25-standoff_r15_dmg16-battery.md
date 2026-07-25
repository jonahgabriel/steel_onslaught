# SO-STANDOFF Arm (blue harpoon range 30 → 15, on top of rung 1's mortar 30 → 15, red dose held at ×16) Battery — Rung-2 Ladder Step (2026-07-25)

**Verdict:** **H_FLAT is supported; the pre-registered formal criterion is NOT met — cutting blue's harpoon range on top of the mortar cut does not reproduce a gain of matching magnitude to rung 1's own gain.** Red (brawler) all-match win count is **23/30 = 0.7667** (29 decided/elimination-class matches, 1 abort; decided-match win rate 23/29 = 0.7931). The pre-registered threshold required **≥25/30 (0.8333)** all-match wins to support H_MONOTONE. Observed win count (23) falls **2 wins short** of that threshold, so by the pre-registered bright line this reads as **H_FLAT**: removing the rest of blue's standoff advantage did not buy a further gain matching the first cut's own +4-win (13.33pp) magnitude. It is not literally zero further gain — 23 is 2 wins above rung 1's 21 (a further +6.67pp point estimate) — but under the pre-registered criterion that partial gain is explicitly scored as H_FLAT, not H_MONOTONE, since the hypothesis under test was specifically whether the second cut matches the first cut's magnitude. Neither the vs-rung-1 nor the vs-rung-0 comparison reaches significance at n=30 (z=0.584–0.614, p=0.539–0.559 vs rung 1; z=1.643–1.861, p=0.063–0.100 vs rung 0/P6) — consistent with this program's unbroken record of non-significant adjacent-arm comparisons.

**Engine-layer confirmation that the manipulation landed as intended:** blue's harpoon_gun fired 25 times this arm (vs 53 times in rung 1, where harpoon was unchanged at r30) despite the harpoon accounting for a similar share of fire attempts (77 total attempts both arms, fired+`target_out_of_range`-rejected) — harpoon's `target_out_of_range` rejection rate rose from 24/77 = 31.2% (rung 1) to 52/77 = 67.5% (this arm). Harpoon usage was cut by more than half in absolute count (53 → 25, −52.8%), the same order of magnitude as rung 1's own mortar-cut effect on the mortar (68 → 31 fired, P6 → rung 1). The manipulation is real and large at the engine layer; it did not translate into a matching further win-rate gain.

**Ledger:** `.onex_state/steel_onslaught/standoff_r15_dmg16` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-STANDOFF worktree.
**Change under test:** ONE lever versus rung 1 (two levers versus rung 0/P6, by design — see Limitations), additive contract files only:
1. `contracts_data/weapons/harpoon_gun_r15.yaml` — one field changed from `harpoon_gun.yaml`: `range: 30 → 15`. `accuracy_curve` and all other fields byte-identical (per the overlay's own accuracy-curve independence check, `interpolate_accuracy` keys on actual distance, never on declared `range`; `range` is a fire-eligibility gate only, `sensors.py:182`, `pilot_tick.py:144/195`).
2. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r15_harpoon_r15` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r15_harpoon_r15.yaml`) — carries rung 1's `weapon.siege.artillery_mortar_r15` unchanged and swaps `weapon.heavy.harpoon_gun → harpoon_gun_r15`. Every other loadout field byte-identical to rung 1's `sniper_ironclad_mortar_r15` loadout.
3. Red loadout `loadout.llm.qwen35_berserker_dmg16` — **UNCHANGED from P6/rung 1**, the baseline this arm's dose is held against.

Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_standoff_r15_dmg16_qwen.yaml` is byte-identical to the merged rung-1 overlay except for the blue loadout id, the pre-registration comment block, and isolated `.onex_state` ledger paths. Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030 (matched to P6 and rung 1), `--fresh` on first launch only. `battery_raw.jsonl` holds exactly 30 rows, seeds 5001–5030 present exactly once each, zero duplicates, zero gaps.
**Baselines:** rung 0 = P6 (mortar_r30 × harpoon_r30 × dmg16, `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md`) — 17/30 = 0.5667. Rung 1 = SO-RANGECAP (mortar_r15 × harpoon_r30 × dmg16, `docs/evidence/2026-07-25-rangecap_r15_dmg16-battery.md`, PR #197, merged `65a679a`) — 21/30 = 0.7000 all-match (21/29 = 0.7241 decided-match), 1 abort.
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl`, cross-checked against `battery_summary.json` (agrees exactly on `winners`, `n`, `terminal_classes`, `play_terminal_fraction`).

---

## 0. Pre-registered hypothesis (quoted verbatim from the overlay header, committed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_standoff_r15_dmg16_qwen.yaml`:

> **H_MONOTONE** (blue's range is a genuinely additive/roughly-linear driver of the residual capping mechanism -- collapsing the SECOND half of blue's standoff envelope, symmetric in kind to the first, buys a further gain of AT LEAST the same magnitude as the first half-cut's own observed gain): rung-2 (this arm) all-match red win count >= 25/30.
>
> ARITHMETIC (independently verified before commit): rung 0 -> rung 1 gain, all-match basis = 21/30 - 17/30 = 4/30 = 0.13333 (13.33pp), i.e. exactly 4 additional wins (17 -> 21). Matched-magnitude threshold = rung-1 win count + rung0->rung1 win-count gain = 21 + 4 = 25. 25/30 = 0.83333. H_MONOTONE requires this arm's all-match win count to reach or exceed 25/30.
>
> **H_FLAT** (the mortar cut alone carried the residual-capping-mechanism effect; the harpoon cut, though a real and equally large-in-kind manipulation at the engine layer, does not reproduce a comparable further gain -- "removing the rest of the advantage changed nothing" relative to rung 1, a fully real, publishable, first-class negative result per house rule): rung-2 all-match red win count <= 24/30.
>
> **FORMAL CRITERION (the ONLY criterion this arm is scored against, ALL-MATCH basis, n=30, chosen deliberately over decided-match basis to avoid rung 1's own flagged denominator ambiguity):** red win count (all-match, n=30 denominator, any abort counted as a non-win) >= 25 supports H_MONOTONE. Win count <= 24 supports H_FLAT.

The overlay explicitly states this arm "does NOT pre-favor either hypothesis" and that "n=30 cannot distinguish them" is a fully acceptable answer.

---

## Method

Identical to P1–P7 / SO-RANGECAP:
- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded); all-30 basis also reported (and is the PRIMARY, scored basis for this arm per the pre-registered criterion).
- **Dose/lever verification, two layers:** contract-layer diff (only `range` changed) and engine-layer reconstruction (`hit_resolved` paired with `armor_absorbed` at `sequence_in_tick + 1` in the same `(match_id, tick)`; weapon attribution from the closest preceding `weapon_fired` targeting the same defender in the same tick; `weapon_fired`/`weapon_fire_rejected` counts by weapon_id and reason).

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | `elimination` 29/30, `abort` 1/30 (seed 5011, `provider_semantic_failure`, malformed JSON completion, `is_draw=true`, no winner) |
| `play_terminal_fraction` | **0.9667** (task gate ≥0.9 — PASS; codebase default ≥0.95 — PASS) |
| Winner distribution | player.red 23, player.blue 6, no winner (abort) 1 |
| **All-match red win rate** (n=30, abort in denominator, not a win — the SCORED basis) | **23/30 = 0.7667** |
| **Decided-match red win rate** (elimination-only denominator, per Method) | **23/29 = 0.7931** |
| 95% Wilson CI, all basis | **[0.5907, 0.8821]** |
| 95% Wilson CI, decided basis | **[0.6161, 0.9015]** |
| Replay validity | 1/1 both players, all 30 matches (including the abort) |
| `failed_completions` distribution | 0 → 13 matches, 1 → 12 matches, 2 → 4 matches, 3 → 1 match (sum = 23, matches §6 exactly) |

Independently recomputed from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once, zero duplicates, zero gaps) and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id)` = 30 for both `match_started` and `match_ended`; `mech_destroyed` on `mech.blue.01` × 23 / `mech.red.01` × 6, sum 29 = the 29 decided matches).

**Non-elimination / abort count: 1** — seed 5011 (`provider_semantic_failure`, malformed JSON completion), `is_draw=true` in the raw row (an artifact of the abort path setting the draw flag, not a genuine tied match — no `victory_kind`, no `winner_player_id`, `total_awards=1` from a single objective award before the abort). This matches rung 1's own single-abort rate (1/30, same failure mode `provider_semantic_failure`) — not a storm, not a second-failure pattern.

### 1a. Statistical comparisons (two-proportion z-test)

| Comparison | Basis | z | p | Significant at α=0.05? |
|---|---|---:|---:|---|
| SO-STANDOFF (23/30) vs rung 1 (21/30) | all-match | 0.584 | 0.559 | No |
| SO-STANDOFF (23/29) vs rung 1 (21/29) | decided | 0.614 | 0.539 | No |
| SO-STANDOFF (23/30) vs rung 0/P6 (17/30) | all-match | 1.643 | 0.100 | No |
| SO-STANDOFF (23/29) vs rung 0/P6 (17/30) | decided | 1.861 | 0.063 | No |

Not significant on any comparison — consistent with this program's unbroken record of non-significant adjacent-arm comparisons at n=30. The vs-rung-0/P6 comparisons (two-axis, not scored) sit closest to conventional significance thresholds but still do not cross α=0.05.

### 1b. Formal-criterion scoring — the pre-registered decision

| Reading | Value | vs threshold | Result |
|---|---:|---|---|
| Literal win count (the ONLY scored reading) | 23 wins | need ≥25 | **falls short by 2** |
| All-match proportion (n=30 denominator, as the criterion's own arithmetic used) | 0.7667 | need ≥0.8333 | **falls short** |

**H_FLAT is supported.** 23 is inside the pre-registered "22–24 = some further gain, but short of matching the first cut's own magnitude" band the overlay header explicitly called out in advance as reading H_FLAT by design.

## 2. Match length

| Metric | This arm (rung 2, mortar_r15+harpoon_r15) | Rung 1 (mortar_r15+harpoon_r30) | Rung 0 / P6 (mortar_r30+harpoon_r30) |
|---|---:|---:|---:|
| min ticks | 11 | 12 | 15 |
| median ticks | **24.0** | 26.0 | 23.0 |
| mean ticks | **24.9** | 26.4 | 23.3 |
| max ticks | 43 | 34 | 40 |

Sorted durations (n=30): 11, 16, 16, 17, 17, 18, 19, 19, 20, 20, 22, 22, 23, 24, 24, 24, 24, 26, 27, 27, 28, 28, 29, 31, 32, 32, 33, 35, 40, 43.

Match length this arm (median 24.0, mean 24.9) sits between rung 0 (23.0/23.3) and rung 1 (26.0/26.4) — shorter than rung 1 despite blue's engagement envelope being MORE collapsed, not less. This runs counter to the direction rung 1 itself observed (rung 1 lengthened relative to P6). One plausible reading: with both long-range weapons cut, blue has less reason to hold at standoff at all and closes faster into `machine_gun_dmg16`/`shrapnel_thrower_dmg16` range, shortening the early no-damage phase rung 1 flagged as the likely driver of its own length increase — but this document does not claim to have isolated that mechanism; it reports the direction as a fact against the rung-1 pattern.

## 3. Range-lever verification (contract + engine layers)

### 3a. Contract layer

`git diff HEAD` against every baseline file this arm depends on (`harpoon_gun.yaml`, `sniper_ironclad_mortar_r15.yaml`, `sniper_ironclad.yaml`, `llm_qwen35_berserker_dmg16.yaml`, `foundry_60_asym_v1.yaml`) returns **empty** — zero existing files modified. `diff contracts_data/weapons/harpoon_gun.yaml contracts_data/weapons/harpoon_gun_r15.yaml` shows exactly one field changed outside comments: `range: 30` → `range: 15`. `diff` on the two loadout files shows exactly one module-id swap (`weapon.heavy.harpoon_gun` → `weapon.heavy.harpoon_gun_r15`), all other fields identical, including the already-swapped `weapon.siege.artillery_mortar_r15` carried forward from rung 1 unchanged.

### 3b. Engine layer — the lever fired as intended

Total-attempts methodology matches rung 1's own table (`fired` + `target_out_of_range`-rejected only; cooldown-rejections excluded from "total attempts" since they are not range-driven):

| Weapon | Arm | Fired | Rejected (`target_out_of_range`) | Total attempts | Fire rate |
|---|---|---:|---:|---:|---:|
| `harpoon_gun_r15` | This arm (rung 2) | **25** | **52** | 77 | **32.5%** |
| `harpoon_gun` (r30) | Rung 1 | 53 | 24 | 77 | 68.8% |
| `artillery_mortar_r15` | This arm (rung 2) | 37 | 117 | 154 | 24.0% |
| `artillery_mortar_r15` | Rung 1 | 31 | 121 | 152 | 20.4% |
| `artillery_mortar_r30` | Rung 0 / P6 | 68 | 52 | 120 | 56.7% |

Blue's harpoon shot count dropped from 53 (rung 1) to 25 (this arm), a **52.8% reduction**, on an identical total-attempt denominator (77 both arms — the range cut converted attempts from fired to rejected almost one-for-one, not from a change in how often blue tried to fire) — confirming the harpoon range cut materially restricted the weapon's usable window at the engine layer, matching the same order of magnitude as rung 1's own mortar-cut effect (68 → 31 fired, −54.4%, P6 → rung 1). Notably, this arm's mortar usage rose slightly versus rung 1 (31 → 37 fired) even though the mortar weapon file is byte-identical between the two arms — consistent with blue substituting toward its one remaining ranged option as harpoon's window shrinks further, though this document does not claim to have isolated that as a causal mechanism. Total blue `weapon_fired` count (mortar + harpoon only, blue's two weapons) fell from 84 (rung 1: 31 mortar + 53 harpoon) to 62 (this arm: 37 mortar + 25 harpoon), a 26.2% reduction, consistent with blue's overall engagement window shrinking once both long-range weapons are cut.

Full `weapon_fired` breakdown, this arm (both seats): `machine_gun_dmg16` (red) 78, `artillery_mortar_r15` (blue) 37, `harpoon_gun_r15` (blue) 25, `shrapnel_thrower_dmg16` (red) 22 (162 total). Full `weapon_fire_rejected` breakdown, this arm: `machine_gun_dmg16`/out-of-range 138, `shrapnel_thrower_dmg16`/out-of-range 116, `artillery_mortar_r15`/out-of-range 117, `harpoon_gun_r15`/out-of-range 52, `artillery_mortar_r15`/cooldown 18, `harpoon_gun_r15`/cooldown 7, `shrapnel_thrower_dmg16`/cooldown 5 (453 total).

### 3c. Red's dose (dmg16) landed unchanged from rung 1 — confirms this arm's only new lever is the harpoon cut

Raw (pre-armor) per-hit damage recovered by pairing `hit_resolved` with `armor_absorbed` at `sequence_in_tick + 1` and attributing the weapon via the closest preceding `weapon_fired` targeting the same defender in the same tick:

| Weapon | Rung 1 raw damage (constant) | This arm raw damage (constant) | Match? |
|---|---:|---:|---|
| `machine_gun_dmg16` | 89 (35/49 red hits, zero variance) | **89** (45/56 red hits, zero variance) | **exact match** |
| `shrapnel_thrower_dmg16` | 115 (14/49 red hits, zero variance) | **115** (11/56 red hits, zero variance) | **exact match** |

Both weapons' raw damage constants are byte-identical to rung 1 — zero variance within either arm, and identical values across arms. Red's per-hit raw damage was not touched by this arm; any win-rate delta is attributable to blue's harpoon-range change alone (relative to rung 1). As a methodology cross-check, blue's own weapon raw-damage constants are also byte-identical across the two arms where the weapon itself is unchanged: `artillery_mortar_r15` raw damage = 40 in both rung 1 and this arm; `harpoon_gun`/`harpoon_gun_r15` raw damage = 22 in both arms (confirming the range cut, as expected from the overlay's own accuracy-curve/damage independence check, altered only fire-eligibility, not damage magnitude).

### 3d. Armor saturation — mechanism continues to hold

| | This arm | Rung 1 |
|---|---:|---:|
| `armor_after == 0` on all hits | **93/93 = 100%** | (not independently re-verified this session; rung 1 doc reports 100% on its own 92 red+blue hits) |
| `armor_after == 0` on red hits | **56/56 = 100%** | 49/49 = 100% |
| Mean damage-after-armor per hit (red hits) | **84.82** | 86.76 |
| Median (red hits) | 84 | 86 |

Consistent with every prior arm in this family — `absorbed_amount` is bounded by the target's remaining armor pool (which varies match-to-match as it depletes), never by a fixed mitigation-cap fraction of raw damage; `armor_after` reaches 0 on every recorded hit in this arm. Mean/median damage-after-armor on red hits is essentially unchanged from rung 1 (84.82 vs 86.76), as expected since red's dose and raw weapon damage are unchanged.

## 4. Hits-to-kill

| | This arm (rung 2) | Rung 1 (given) | Rung 0 / P6 (given) |
|---|---:|---:|---:|
| **Red kills blue — mean hits** | **2.261** (23 kills, median 2, `{2:17, 3:6}`) | 2.048 | 2.18 |
| **Blue kills red — mean hits** | **2.333** (6 kills, median 2, `{2:4, 3:2}`) | 2.75 | 2.62 |

Red's kill speed (2.261) is slightly slower than rung 1's (2.048) but still faster than blue's own kill speed in this arm — consistent with red's dose being unchanged and driven by sampling noise at n=23/29 kills rather than a real dose shift (§3c confirms red's raw damage is byte-identical to rung 1). Blue's kill speed against red (2.333) is faster than rung 1's (2.75) and closer to P6's (2.62) — directionally consistent with blue landing more concentrated hits once forced into closer engagement ranges on both its long-range weapons, though n=6 blue kills is too small to draw a confident conclusion. `mech_destroyed` counts corroborate the win tally exactly: blue destroyed in 23 matches (= the 23 red wins), red destroyed in 6 matches (= the 6 blue wins), 23+6=29 decided matches, zero unexplained destructions, 1 abort with no destruction event on either side.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility, hand_dealt × 2) | Programmed (utility, `utility_deployed`) | Keep-rate | Rung 1 (given context, not independently recomputed this session) |
|---|---:|---:|---:|---|
| red (brawler) | 322 | 5 | **0.0155** | 0.0298 (P6) / not restated by rung 1 doc for direct comparison |
| blue (sniper) | 322 | 23 | **0.0714** | 0.0659 (rung 1) / 0.1026 (P6) |
| all-card sanity, both seats | 805/1610 (each seat: 161 `plan_committed` × 5-card register / 161 `hand_dealt` × 10-card hand) | — | 0.5000 (mechanical, confirms 5-of-10 register structure held) | 0.500 |

Blue's utility keep-rate (0.0714) sits between rung 1's (0.0659) and P6's (0.1026), continuing the same downward-then-partial-recovery pattern rung 1 flagged (blue spending more register slots on movement/positioning as its ranged options shrink) — not independently isolated as a mechanism here either (n=30 is not powered to separate this from noise). Red's keep-rate (0.0155) is lower than either baseline; not explained further in this document.

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 345 |
| `llm_completion_resolved` | 322 |
| `llm_completion_failed` | 23 |
| `finish_reason` distribution | `stop`: 322/322 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 322/322 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **1/30** (seed 5011) |

345 requested − 322 resolved = 23, matching `llm_completion_failed` exactly, zero gap between resolved and `plan_committed`. Seed 5011's abort (`provider_semantic_failure`) was an in-match completion failure that was NOT recovered — the one match in the battery that did not reach a clean `elimination` terminal, same failure class/rate as rung 1's single abort (1/30, `provider_semantic_failure`).

---

## 7. THE LADDER — win rate, CI, hits-to-kill, engine-layer usage

| Rung | Arm | Blue mortar | Blue harpoon | All-match win rate | Wilson 95% CI | Red hits-to-kill | Blue hits-to-kill | Mortar fire rate | Harpoon fire rate |
|---|---|---|---|---:|---|---:|---:|---:|---:|
| 0 | P6 | r30 | r30 | 17/30 = 0.5667 | (not recomputed this session) | 2.18 | 2.62 | 56.7% (68/120) | not independently re-verified this session (see §Limitations) |
| 1 | SO-RANGECAP | r15 | r30 | 21/30 = 0.7000 | [0.5212, 0.8334] | 2.048 | 2.75 | 20.4% (31/152) | 68.8% (53/77) |
| 2 | SO-STANDOFF | r15 | r15 | **23/30 = 0.7667** | **[0.5907, 0.8821]** | **2.261** | **2.333** | **24.0% (37/154)** | **32.5% (25/77)** |

**Win-rate gain is NOT monotone in matched magnitude.** Rung 0→1 gained +4 wins (13.33pp) from the mortar cut alone. Rung 1→2 gained only +2 wins (6.67pp) from the harpoon cut on top of it — half the first cut's magnitude, despite the harpoon cut being at least as large a manipulation at the engine layer (fire-rate collapse 68.8%→32.5%, a 36.3pp swing, versus the mortar's own 56.7%→20.4%, a 36.3pp swing on P6→rung1 — nearly identical engine-layer effect sizes). The point estimate is still directionally positive and the wide, overlapping Wilson CIs across all three rungs (rung 0's own CI is not recomputed here, but rung 1 [0.52, 0.83] and rung 2 [0.59, 0.88] overlap substantially) mean n=30 cannot rule out a smaller true additive effect for the second cut — but the pre-registered bright line asked specifically whether the second cut MATCHES the first cut's magnitude, and it does not.

What this implicates: **range collapse on blue's second long-range weapon is not simply additive with the first.** Two readings are both consistent with the data and this document does not adjudicate between them: (a) diminishing returns — once blue's primary standoff weapon (mortar, the higher-alpha siege weapon) is already cut, forcing the secondary weapon (harpoon) into the same box captures less incremental value because blue was already substituting into short-range weapons after rung 1; or (b) genuine ceiling — some other factor (approach/exposure-time dynamics, first-strike variance, or the fixed short-range weapon kit itself) caps how much win rate range alone can buy, independent of how many of blue's weapons are range-restricted. This arm's design (single-axis vs rung 1) cannot distinguish these two readings from each other; it only establishes that the SECOND cut does not reproduce the FIRST cut's magnitude.

---

## 8. Verdict

**H_FLAT is supported — the pre-registered formal criterion is not met.** Blue's harpoon-range halving (30→15), on top of rung 1's mortar cut and at fixed red dose, raised red's all-match win rate from rung 1's 70.00% to 76.67% (+6.67pp, +2 wins) — a real, directionally positive, engine-layer-confirmed effect, but the pre-registered criterion required at least +4 wins (matching rung 0→1's own magnitude) to score H_MONOTONE, and this arm produced only +2. Scored by the ONLY reading the pre-registration specified (literal all-match win count ≥25), this arm's 23 lands clearly on the H_FLAT side.

- **The manipulation is real and large at the engine layer** (§3b): blue's harpoon fire rate dropped from 68.8% (rung 1) to 32.5% (this arm) of attempts on an identical 77-attempt denominator — a 52.8% reduction in shots actually fired, confirming the range cut materially restricted blue's remaining engagement envelope as designed, at a comparable order of magnitude to rung 1's own mortar-cut effect.
- **The win-rate effect is directionally positive but roughly half the magnitude of the first cut, and statistically inseparable from rung 1 at n=30** (z=0.584–0.614, p=0.539–0.559) — consistent with this program's unbroken record of non-significant adjacent-arm comparisons.
- **Range is not simply an additive/linear driver of the residual capping mechanism across both of blue's long-range weapons.** "Removing the rest of the advantage" (harpoon, on top of mortar) did NOT change nothing — win rate still rose — but it changed markedly less than removing the first half did, which is the pre-registered bar this arm was built to test, not merely directional positivity.
- **This arm does not settle WHY the second cut underperforms the first** — diminishing-returns and genuine-ceiling readings (§7) are both consistent with the data at n=30; distinguishing them would need a design this arm was not built to provide (e.g., isolating the harpoon cut alone against rung 0, without the mortar cut also applied — a genuinely single-axis-vs-rung-0 arm, which this ladder does not include by design, see Limitations).

**Honest statement on what this arm does and does not settle:** the point estimate (76.67% all-match, 79.31% decided) is the highest of the three rungs and the engine-layer confirmation that the harpoon lever fired is unambiguous, but n=30 leaves wide, overlapping Wilson CIs across rungs 1 and 2 that cannot cleanly separate "a real but smaller additive effect" from "no additional true effect, this point estimate is sampling noise around rung 1's own rate." The pre-registered bright-line criterion is the only thing this document scores against, and by that criterion the answer is H_FLAT — by 2 matches, on the one basis the pre-registration specified.

---

## 9. Limitations

- **This arm is single-axis versus rung 1, but two-axis versus rung 0, by design.** The pre-registered comparison baseline is rung 1 (mortar_r15 × harpoon_r30), against which exactly one property changes (harpoon range 30→15) — the scored criterion, statistical tests in §1a/§3, and the "manipulation landed" claim in §3b are all valid single-axis comparisons. Versus rung 0/P6 (mortar_r30 × harpoon_r30), this arm changes BOTH weapons simultaneously; any win-rate delta reported against rung 0 in §7's ladder table reflects the combined effect of both cuts and is NOT attributable to the harpoon cut alone. This is by design (the ladder's rung structure), not an oversight, and is called out explicitly in the overlay's own pre-registration header.
- **n=30 power, 2-win miss.** The observed win count (23) is 2 matches away from the pre-registered threshold (25). At n=30 this is well within normal sampling variance around a range of plausible true effect sizes; this document reports the miss as pre-registered and does not treat it as strong disconfirmation of a genuine (if smaller) harpoon effect, only as the pre-declared decision rule's actual output.
- **One abort (seed 5011) matches rung 1's own abort rate/mode exactly** (`provider_semantic_failure`, 1/30) — the all-match basis (the pre-registered PRIMARY basis for this arm specifically) absorbs this cleanly without the denominator ambiguity rung 1 itself flagged; decided-match basis (23/29) is reported alongside for continuity but is not the scored quantity.
- **P6 (rung 0) win-rate Wilson CI and harpoon-specific engine-layer figures are not independently recomputed in this document.** P6's win rate (17/30) and mortar fire rate (68/120 = 56.7%) are taken from rung 1's own already-published, independently-verified evidence doc (`docs/evidence/2026-07-25-rangecap_r15_dmg16-battery.md`). A shared P6 ledger was available this session under a concurrent arm's worktree but showed 33 `match_started` events against a pre-registered n=30 (evidence of reuse/contamination across sessions) and was deliberately excluded rather than risk citing an unverified figure — no P6 harpoon-specific fire-rate number is reported anywhere in this document for that reason.
- **Match-length direction reverses rung 1's own pattern and is reported, not explained.** §2's finding (this arm's median/mean sit between rung 0 and rung 1, shorter than rung 1 despite a MORE collapsed blue envelope) runs counter to a naive extrapolation of rung 1's own length-increase finding; no mechanism is claimed or verified for it.
- **No re-run to chase a different number.** n=30, seeds 5001–5030, was pre-declared before this battery ran and is reported as-is (including the one abort); the battery completed all 30 seeds, so there is no truncation to disclose.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/standoff_r15_dmg16/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `weapon_fired`, `weapon_fire_rejected`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `utility_deployed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Contract diffs: `contracts_data/weapons/harpoon_gun.yaml` vs `harpoon_gun_r15.yaml`; `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r15.yaml` vs `sniper_ironclad_mortar_r15_harpoon_r15.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`); accuracy curve, fire-eligibility gate: `src/steel_onslaught/reducers/weapons.py` (`interpolate_accuracy`), `src/steel_onslaught/reducers/sensors.py:182`, `src/steel_onslaught/reducers/pilot_tick.py:144/195`.
- Rung 1 (comparison baseline, scored): `docs/evidence/2026-07-25-rangecap_r15_dmg16-battery.md` (SO-RANGECAP, 21/30 = 0.7000, PR #197, merged `65a679a`), independently re-verified against its own ledger at `.onex_state/steel_onslaught/rangecap_r15_dmg16/events.sqlite3` in the SO-RANGECAP worktree for the §3c/§7 cross-checks in this document.
- Rung 0 baseline arm evidence: `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md` (P6, 17/30 = 0.5667, ladder-completeness only, not independently recomputed this session — see Limitations).
- Sibling arm evidence, program context: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md` through `-pair_p6_dmg16-battery.md`, `docs/evidence/2026-07-25-pair_p7_dmg24-battery.md`.
- Pre-registration: overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_standoff_r15_dmg16_qwen.yaml`, commit `8e13b37`.
- No secrets, keys, or absolute paths included.
