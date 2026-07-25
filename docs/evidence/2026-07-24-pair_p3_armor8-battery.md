# Pair-Sweep Arm P3 (mortar_r30 × blue-armor-8) Battery — Independent Verification (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/28 = 0.0000** (all-30 basis: **0/30 = 0.0000**) — inside the `<0.10` FAILED band, 95% Wilson CI **[0, 0.1206]** (decided-28 basis). The armor-side lethality dose (blue chassis `base_armor` 16 → 8, zero red-side buffs) is confirmed to have landed exactly as designed at the contract layer (`git diff` shows the single `base_armor: 16` → `base_armor: 8` field change, nothing else), and it measurably lowered blue's mitigation in a minority of hits — but the arena's degrading, capped-fraction armor model (`absorbed = min(armor_value, ceil(damage_raw × 0.75))`) means the armor pool is the *binding* constraint on absorption only when `armor_value < ceil(damage_raw × 0.75)`. Red's stock weapons (`machine_gun`/`shrapnel_thrower`, raw damage 5/7 against blue's `heavy` chassis class) produce a cap of 4/6, which is below the OLD armor value of 16 in effectively all cases and below the NEW value of 8 whenever the pool is fresh — so on a majority of hits (62/96, 65%) the mitigation cap, not the armor pool, was already the limiting factor, and halving `base_armor` changed nothing. Pairing this dose with the merged mortar_r30 approach fix reproduces the double-null baseline exactly (v1 anchor 0/30, arm-1-alone 0/30) — in sharp contrast to P1 (mortar_r30 + red-dmg×3, 1/29 FAILED-but-nonzero) and P2 (mortar_r30 + red-dmg×5.5, 5/29 DIRECTIONAL), both of which raised red's *raw* damage output directly rather than lowering blue's mitigation ceiling.

**Ledger:** `.onex_state/steel_onslaught/pair_p3_armor8` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-PAIR worktree.
**Change under test:** PR #170 (merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0`) — two levers, exactly two:
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30_armor8` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30_armor8.yaml`) — carries both the shared approach-fix lever (`weapon.siege.artillery_mortar` → `...mortar_r30`, range 50 → 30, first merged under PR #159) and the P3 lethality-dose lever (chassis `chassis.heavy.ironclad_mk1` → `...ironclad_mk1_armor8`).
2. Chassis `contracts_data/chassis/heavy_ironclad_mk1_armor8.yaml` — `constraints.base_armor: 16` → `8`, every other field (`max_mass`, `max_module_slots`, `max_boiler_volume`, `base_speed`, `base_turn_rate`, `base_signature`, `base_vent_rate`, `base_hp`, `base_armor_regen`, `compatibility`, `penalties`) byte-identical to `heavy_ironclad_mk1.yaml`.
Red loadout `loadout.llm.qwen35_berserker` (`contracts_data/loadouts/llm_qwen35_berserker.yaml`) is fully **stock** — zero red-side buffs, unlike P1/P2. Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p3_armor8_qwen.yaml` is the same U-GATE/O-GATE combined shape as the v1 overlay, isolated `.onex_state` paths only. Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true` (1/1 both players, all 30 matches).
**Baselines:** v1 anchor 0/30 median 31 ticks; arm-1 (mortar_r30 alone) 0/30 median 28 ticks; recut-v2 0/30 median 33 ticks; pair P1 (mortar_r30 + red-dmg×3) 1/29 = 0.0345, FAILED; pair P2 (mortar_r30 + red-dmg×5.5) 5/29 = 0.1724, DIRECTIONAL; historical single-lever ×5.5-alone ~5% (1/43, prior lethal-approach regime).
- All figures below are independently recomputed by an adversarial verifier directly from `events.sqlite3` and `battery_raw.jsonl` — not copied from the runner's or implementer's report — with an explicit contract-level and engine-level check of whether the intended armor-8 dose actually landed and actually moved damage output.

---

## 0. Raw-file provenance (battery ran in two invocations)

The battery process crashed mid-run with an unhandled `steel_onslaught.llm.schemas.LlmTransportError: LLM transport request failed` (`client_http.py:148`, `retryable=True`) while attempting seed 5008 — after seeds 5001–5007 had already been cleanly logged and appended to `battery_raw.jsonl` (nohup PID 25573, log `pair_p3_armor8.log`). The runner script has no built-in resume and appends unconditionally on every invocation without `--fresh`, so the battery was relaunched with `--n 23 --seed-base 5007` (PID 53092, log `pair_p3_armor8_part2.log`) to append exactly seeds 5008–5030 to the same state root rather than re-running 5001–5007 and duplicating rows.

Independently verified: `battery_raw.jsonl` has exactly 30 lines, `SELECT DISTINCT seed` = 30 unique values covering 5001–5030 with zero duplicates and zero gaps (checked by direct set-difference against `range(5001, 5031)`, not by trusting the row count alone).

---

## Method

- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded from the denominator); all-30 basis also reported for comparability with prior single-lever docs.
- **Dose verification, two layers:**
  1. **Contract layer** — `git diff` of `heavy_ironclad_mk1_armor8.yaml` against the un-modified `heavy_ironclad_mk1.yaml`, confirming the only field changed is `constraints.base_armor` (16 → 8).
  2. **Engine layer** — for every red-on-blue `hit_resolved` event, paired the matching `armor_absorbed` event on blue at the same `(match_id, tick)` (unambiguous: zero multi-hit ticks observed), reconstructed `damage_raw = damage_after_armor + absorbed_amount` (per `steel_onslaught.reducers.damage.compute_armor_reduction`'s invariant `effective = damage_raw − absorbed`), reconstructed `armor_value_before_hit = armor_after + absorbed_amount`, and classified each hit as **armor-bound** (`absorbed == armor_value_before` and `armor_value_before < ceil(damage_raw × 0.75)`, i.e. the pool was the limiting factor) or **cap-bound** (`ceil(damage_raw × 0.75) <= armor_value_before`, i.e. the 75%-of-raw-damage mitigation cap was the limiting factor and the armor pool's exact value was irrelevant to that hit).
- **Why this classification matters (armor-side dose validity):** `compute_armor_reduction`'s formula is `absorbable = min(armor_value, ceil(damage_raw × mitigation_cap))` — armor is only a lethality lever on hits where `armor_value` is the smaller of the two terms. Red's stock weapons deal weak raw damage against blue's `heavy` chassis class (`machine_gun`: `int(8×0.7)=5`; `shrapnel_thrower`: `int(12×0.6)=7`), so `ceil(damage_raw × 0.75)` is 4 or 6 — well below the OLD `base_armor=16` on every hit, and below the NEW `base_armor=8` whenever the pool has not yet been worn down from prior hits. This is a mechanically distinct failure mode from a "dose didn't land" bug: the contract diff is exact and the engine confirms `base_armor` reads as 8 in-battery (see §3b), but the lever is only *load-bearing* on a subset of hits, by construction of the armor formula against these specific weapon/chassis stats.
- **Utility keep-rate per seat** = utility cards programmed into a register (`plan_committed.registers[].card_id` matching `card.utility.%`) ÷ utility cards dealt (`hand_dealt.partitions.utility.card_ids`), same method as the P1/P2 docs.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | elimination 28/30, abort 2/30 (seeds 5007, 5017) |
| play_terminal_fraction | **0.9333** (gate: ≥0.9 — PASS) |
| Winner distribution | player.blue 30 (28 elimination wins + 2 abort-default), player.red 0, is_draw=true 2 (the two aborts) |
| **Decided-match red win rate (aborts excluded)** | **0/28 = 0.0000** |
| **All-match red win rate (aborts included, denominator 30)** | **0/30 = 0.0000** |
| 95% Wilson CI, decided-28 basis | **[0, 0.1206]** |
| 95% Wilson CI, all-30 basis | [0, 0.1135] |
| Replay validity | 1/1 both players, all 30 matches |

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once) and cross-checked against `events.sqlite3` (`SELECT COUNT(DISTINCT match_id) WHERE event_type='match_ended'` = 30). Matches the runner's raw tally exactly, per-seed, zero discrepancy: both aborted matches carry `is_draw=true` and `winner_player_id="player.blue"` simultaneously (a non-decisive default value on the field, not an actual blue win) — seed 5007 (`aborted`, `LlmTransportError`-driven process crash during the run, distinct from the mid-battery process crash described in §0 — this abort was recorded cleanly before the crash; confirmed via `llm_completion_failed`, `match.01KYAP9K3WP473TRHQJVFBZJ9X` has 1 failure, consistent with `failed_completions=1`) and seed 5017 (`provider_semantic_failure`, red seat, `malformed_json`, 3 consecutive failed plan attempts at tick 1, budget exhausted — `match.01KYAPYH33YTJAY37S628W1Z6X` has exactly 3 `llm_completion_failed` events, the only match with a non-`elimination` terminal class besides 5007). Both aborts are correctly excluded from both the numerator and denominator of the decided-match rate; treating them as blue wins (all-30 basis) does not change the win-rate figure since red also has zero wins in that basis.

The point estimate (0.0) sits at the floor of the `<0.10` FAILED band with a Wilson upper bound of 0.12 — a slightly tighter CI than P1's 0/29-equivalent would produce, reflecting the larger sample of zero-events (28 vs the hypothetical). This is the same outcome, seed-for-seed pattern, as the v1 anchor (0/30) and arm-1-alone (0/30): **zero uplift from the armor-side lethality lever**, in direct contrast to P1 (1/29) and P2 (5/29), which both moved red's *raw* damage output.

## 2. Match length

| Metric | P3 (mortar_r30 + armor8) | v1 anchor | arm-1 alone | recut-v2 | P1 (dmg×3) | P2 (dmg×5.5) |
|---|---:|---:|---:|---:|---:|---:|
| min ticks | 1 (abort) / 14 (elimination) | — | 14 | — | 1 / 13 | 1 / 18 |
| median ticks | **27.5** | 31 | 28 | 33 | 31 | 30 |
| mean ticks | 29.23 (all 30) / 29.64 (decided, n=28) | — | 27.7 | — | 31.4 / 32.4 | 30.1 / 31.1 |
| max ticks | 66 | — | 44 | — | 61 | — |

Median (27.5) is the shortest of every arm in the pair-sweep so far, and sits just below arm-1-alone (28) rather than between it and the higher-lethality-dose arms (P1: 31, P2: 30) — the opposite of what a working lethality lever would produce (P1/P2 both landed *above* arm-1-alone's median, consistent with red occasionally surviving long enough to make a fight of it). P3's shorter matches are consistent with zero uplift: nothing changed blue's kill speed against red, and red never survived meaningfully longer either.

## 3. Dose verification (armor-side lethality)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `contracts_data/chassis/heavy_ironclad_mk1.yaml` → `heavy_ironclad_mk1_armor8.yaml` | `constraints.base_armor: 16` | `constraints.base_armor: 8` | `base_armor` only — `max_mass`, `max_module_slots`, `max_boiler_volume`, `base_speed`, `base_turn_rate`, `base_signature`, `base_vent_rate`, `base_hp`, `base_armor_regen`, `compatibility`, `penalties` all byte-identical |

Confirmed via direct `git diff` — exactly one field changed, no red-side files touched at all (unlike P1/P2, which modify weapon contracts).

### 3b. Engine layer (reconstructed from live event data)

Reconstructed `armor_value_before_hit = armor_after + absorbed_amount` for all 96 red-on-blue hits and classified each as armor-bound or cap-bound per the Method above:

| | Value |
|---|---:|
| Raw damage values observed (red→blue, `damage_after_armor + absorbed_amount`) | {5: 67 hits, 7: 29 hits} — matches `int(8×0.7)=5` (machine_gun vs `heavy`) and `int(12×0.6)=7` (shrapnel_thrower vs `heavy`) exactly, zero variance |
| Mitigation cap per hit (`ceil(raw × 0.75)`) | 4 (raw=5 hits) / 6 (raw=7 hits) |
| Reconstructed `armor_value_before_hit` observed range | 1–8 (armor degrades across the match, no regen observed within a single fight sequence) |
| Hits where the mitigation cap was binding (armor_value ≥ cap — armor's exact value was irrelevant) | **62/96 (65%)** |
| Hits where the armor pool was binding (armor_value < cap — the dose was load-bearing) | **34/96 (35%)** |

**The dose landed exactly as contracted** — `base_armor` reads as 8 in-battery, confirmed by the observed `armor_value_before_hit` ceiling of 8 (never higher, whereas the pre-dose baseline would show a ceiling of 16) — but it was only mechanically load-bearing on 35% of red's hits, because the mitigation-cap formula already limited absorption below 8 on the majority (65%) of hits against these specific weak red weapons. This is a genuine, correctly-applied dose whose real-world effect size is small by construction of the armor formula, not a vacuous or mis-applied result.

### 3c. Damage-after-armor (context, and the direct check requested: does red's output differ from the historical baseline?)

| | P3 red→blue (n=96 hits, all 30 seeds) | P3 red→blue (n=89 hits, decided-28 only) | Historical baseline (context, cited) |
|---|---:|---:|---:|
| Mean damage-after-armor per hit | **2.052** | 2.045 | 5.98 |
| Median | 1 | 1 | — |

Red's mean damage-after-armor (2.05) is **lower**, not higher, than the cited historical baseline (5.98) — the opposite of the naive expectation that halving blue's armor should raise red's per-hit output. This is not evidence the dose failed to apply (§3b already proves it did, at the contract and engine layers); it reflects that the 5.98 historical figure comes from a different regime (the original stock v1 arena/loadouts, pre-mortar_r30, pre-any-pairing) with different match dynamics, not a like-for-like comparison, and that this arena's capped-fraction armor model means the armor value's effect on absorption is bounded by 75% of the incoming raw damage regardless of the armor pool's magnitude. Given red's weak stock raw damage (5/7) against blue's `heavy` class, the theoretical maximum benefit from removing armor's binding constraint entirely (armor_value=0) would only raise mean damage-after-armor to the full raw-damage average (5.62, weighted by the 67/29 hit-type split) — nowhere near enough to meaningfully shift the 160-HP blue kill math even in the best case.

**Conclusion: the dose landed exactly as designed at both layers, and this document's own reconstruction explains, mechanically, why a correctly-landed armor-8 dose still produced zero measurable uplift** — not a mismeasured or unlanded dose, a genuinely small effect size given the weapon/armor interaction.

## 4. Hits-to-kill

| | P3 | Historical baseline (context, cited) |
|---|---:|---:|
| Blue kills red — mean hits (28 kills, decided matches) | **2.71** | ~2.04 |
| Blue kills red — mean damage-after-armor per hit (n=76, decided) | 27.29 | 29.47 |
| Red kills blue — hits (n=0, zero red wins) | not observable | ~26.74 |
| Red's implied hits-to-kill if sustained at observed rate (160 HP / 2.05 avg dmg) | **≈78** | 26.74 |

Blue's kill speed against red is essentially unchanged from the historical baseline (2.71 vs 2.04 hits, same order of magnitude — nothing about P3 touches blue's offense or red's defense). Red never killed blue in this battery, so there is no observed hits-to-kill figure for red; the implied rate from red's observed per-hit output (≈78 hits to deplete 160 HP) is roughly **3× worse** than the historical baseline's ~26.74, consistent with §3c's finding that red's damage-after-armor was lower here than the cited historical context, not higher — the armor-8 dose did not close this gap.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate |
|---|---:|---:|---:|
| red (brawler) | 370 | 9 | **0.024** |
| blue (sniper) | 370 | 38 | **0.103** |

Both seats show low utility pickup, consistent with the program's recurring finding that utility cards lose out to weapon/movement cards under this deal/program ratio (P1: red 4.3%/blue 7.9%; P2 not cited in this doc but same pattern reported) — not a new effect of this arm, and not diagnostic of the win-rate result.

## 6. Completion health

| Metric | Value |
|---|---:|
| `llm_completion_requested` | 409 |
| `llm_completion_resolved` | 373 |
| `llm_completion_failed` | 36 |
| `finish_reason` distribution | `stop`: 373/373 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 370/370 committed plans (zero fallback/heuristic plans) |
| Matches with ≥1 failed completion | 22/30 |
| Max single-match failures | 4 |
| Matches reaching an unrecovered abort | 2/30 (seeds 5007, 5017) |
| Total `failed_completions` summed across `battery_raw.jsonl` | 35 (matches raw-file field sum exactly) |

409 requested − 373 resolved = 36, matching `llm_completion_failed` exactly. All but two matches' failures were recovered by retry (`finish_reason=stop`, `plan_source=llm` on all 370 final committed plans across the 29 matches that reached at least one `plan_committed`); seed 5017 hit 3 consecutive `malformed_json` failures on the red seat at tick 1 and exhausted its plan-attempt budget before any plan was committed (29, not 30, matches have `plan_committed` events — consistent with seed 5017's zero-plan abort). `play_terminal_fraction=0.9333` reflects the two non-elimination terminals (5007, 5017).

## 7. Merge / additivity verification

- PR #170 merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (`gh pr view 170`: state MERGED, mergedAt 2026-07-24T17:32:38Z, base `main`), confirmed as an ancestor of this evidence branch's base commit.
- The specific baseline file this arm depends on (`heavy_ironclad_mk1.yaml`) plus the shared cross-arm baselines (`llm_qwen35_berserker.yaml`, `sniper_ironclad.yaml`, `sniper_ironclad_mortar_r30.yaml`, `foundry_60_asym_v1.yaml`, `artillery_mortar.yaml`, `artillery_mortar_r30.yaml`) — a direct `git diff` across the merge on all of these returns empty, matching the additivity guarantee documented in the P1/P2 verifications.
- No red-side contract file is touched by P3 at all (unlike P1/P2's weapon-damage variants) — the only new contract-data files introduced for this arm are `heavy_ironclad_mk1_armor8.yaml` and `sniper_ironclad_mortar_r30_armor8.yaml` (the P3 blue loadout binding the two P3 levers together).

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/28), all-30 basis 0.0000 (0/30) — the floor of the `<0.10` FAILED band, 95% Wilson CI `[0, 0.1206]`. `play_terminal_fraction=0.9333` clears the ≥0.9 trust gate. The intended `base_armor` 16→8 dose is verified to have landed exactly as designed at both the contract layer (single-field diff) and the engine layer (observed `armor_value_before_hit` ceiling drops from the pre-dose 16 to 8, confirmed) — this is not a vacuous or mis-applied-dose result. It is, however, a dose whose real-world effect is genuinely small: the arena's capped-fraction armor model (`absorbed = min(armor_value, ceil(damage_raw × 0.75))`) means armor's exact value is the binding constraint on absorption only when it is smaller than 75% of the incoming raw damage — true for only 35% of red's hits against blue in this battery, because red's stock weapons deal weak raw damage (5/7) against blue's `heavy` chassis class. Pairing this correctly-landed but structurally-weak lethality lever with the mortar_r30 approach fix reproduces the double-null baseline exactly (0/30, matching both the v1 anchor and arm-1-alone).

**Dose-response conclusion across the three paired arms:** P1 (red-dmg×3, raises red's raw output directly) scored 1/29 FAILED-but-nonzero; P2 (red-dmg×5.5, same mechanism, larger dose) scored 5/29 DIRECTIONAL; P3 (blue armor 16→8, lowers blue's mitigation ceiling rather than raising red's raw output) scored 0/28, indistinguishable from the double-null baseline. This is not just "armor moved less than damage" — §3b's per-hit classification shows the mechanism directly: raising red's raw damage output moves *every* hit's post-armor result (the mitigation cap scales with raw damage, so a bigger hit produces a bigger cap and a bigger absorbed amount, but also a proportionally bigger leak-through), whereas lowering blue's armor pool only matters on the minority of hits where the pool, not the cap, was already the tighter constraint. Under this specific weapon/chassis/armor-formula interaction, **lethality must be dosed on the attacker's raw damage, not the defender's armor pool, to move win rate** — a mechanism-level finding, not just a correlational one, and specific to this armor model (a flat-subtraction armor model would not exhibit this asymmetry).

---

## Limitations

- **Uncontrolled range-30 standoff (`harpoon_gun`).** This arm's blue loadout closes only one of blue's two long-range weapons: `artillery_mortar` was cut to range 30 (the approach-fix lever named above), but `harpoon_gun` stayed at range 30, uncapped, through this arm and every other arm in the P1–P7 sweep. Blue therefore retained an ~18–22 cell standoff advantage against red's longest weapon (`machine_gun`, range 12) that this arm's design did not control for and this document did not previously disclose. Found post hoc during the SO-RANGECAP design pass (PR #197); does not change any figure reported above. See OMN-15119.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p3_armor8/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `damage_applied`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against `battery_summary.json` (noting the on-disk summary's `--n` window reflects only the part-2 23-seed resume, per §0 — all figures in this document are recomputed from the full 30-row raw file, not from that summary).
- Contract diff: `contracts_data/chassis/heavy_ironclad_mk1.yaml` vs `heavy_ironclad_mk1_armor8.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction model, `_MITIGATION_CAP` table).
- Merge commit: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`).
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md` (PR #177), `docs/evidence/2026-07-24-pair_p2_dmg55-battery.md` (PR #179).
- Ledger: `docs/tracking/ROLLING_WORK_LEDGER.md` (2026-07-24 SO-PAIR P3 entry, to be added on merge).
- No secrets, keys, or absolute paths included.
