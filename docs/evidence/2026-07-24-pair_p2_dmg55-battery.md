# Pair-Sweep Arm P2 (mortar_r30 × red-dmg×5.5) Battery — Independent Verification (2026-07-24)

**Verdict:** **DIRECTIONAL.** Decided-match red (brawler) win rate is **5/29 = 0.1724** (all-30 basis: **5/30 = 0.1667**) — inside the `0.10–0.35` DIRECTIONAL band, 95% Wilson CI **[0.076, 0.345]** (decided-29 basis). The historical ×5.5-alone single-lever dose is confirmed to have landed correctly at both the contract layer (exact ×5.5, direct diff) and the engine layer (deterministic per-hit raw-damage reconstruction, zero variance, ratios 5.57×–6.00× accounting for `int()` truncation on both baseline and variant). Pairing it with the merged mortar_r30 approach fix produces the strongest result in the pair-sweep so far: a clear jump above both single-lever nulls (v1 anchor 0/30, arm-1-alone 0/30) and above the historical ×5.5-alone rate itself (~5%, 1/43, prior lethal-approach regime) — but the point estimate (16.7–17.2%) is still well short of the 0.35 COMPETITIVE threshold, and the Wilson CI upper bound (0.345) sits just under that line, not across it.

**Ledger:** `.onex_state/steel_onslaught/pair_p2_dmg55` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-PAIR worktree.
**Change under test:** PR #170 (merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0`) — two levers, exactly two:
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`, first merged under PR #159) — swaps only `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_r30` (range 50 → 30), every other module/field identical.
2. Red loadout `loadout.llm.qwen35_berserker_dmg55` (`contracts_data/loadouts/llm_qwen35_berserker_dmg55.yaml`) — swaps both berserker weapons for damage-×5.5 variants (`machine_gun_dmg55`: damage 8 → 44; `shrapnel_thrower_dmg55`: damage 12 → 66), every other weapon field identical.
Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p2_dmg55_qwen.yaml` is the same U-GATE/O-GATE combined shape as the v1 overlay, isolated `.onex_state` paths only. Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true` (1/1 both players, all 30 matches), `o_gate_pass=true` on the full 30-row recompute (the on-disk `battery_summary.json` incorrectly reads `o_gate_pass: false` because it reflects only the resumed n=16 second-invocation slice — see §0).
**Baselines:** v1 anchor 0/30 median 31 ticks; arm-1 (mortar_r30 alone) 0/30 median 28 ticks; recut-v2 0/30 median 33 ticks; pair P1 (mortar_r30 + red-dmg×3) 1/29 = 0.0345, FAILED; historical single-lever ×5.5-alone ~5% (1/43, prior lethal-approach regime).
- All figures below are independently recomputed by an adversarial verifier directly from `events.sqlite3` and `battery_raw.jsonl` — not copied from the runner's or implementer's report — with an explicit contract-level and engine-level check of whether the intended ×5.5 damage dose actually landed.

---

## 0. Raw-file provenance (battery ran in two invocations)

The battery was interrupted once: the first invocation completed seeds 5001–5014 before dying at seed 5015 with a genuine `LlmTransportError` (`steel_onslaught/llm/client_http.py:148`, `retryable=True`) — confirmed from the crash traceback in the first-attempt log and from `events.sqlite3`: `match_started`=31 distinct match_ids vs `match_ended`=30, the one orphan (`match.01KYAMQGMCFBR6CH58H5E79MX7`) tracing to a partial run that reached tick 6 (`hand_dealt`/`plan_committed` at tick 1, zero `hit_resolved` events, terminating on `llm_completion_failed` at tick 6) and is **not** one of the 30 rows in `battery_raw.jsonl`. It contributes zero hit/damage/keep-rate data to any figure below (verified by re-running every aggregate with and without the match_id filter — identical results).

The second invocation resumed with `--seed-base 5014 --n 16` against the same `--state-root`, in append mode (no `--fresh`), covering seeds 5015–5030 (16 rows) with no `--seed-base`/`--n` overlap against the first invocation's 5001–5014 (14 rows). `battery_raw.jsonl` contains exactly 30 rows, seeds 5001–5030, each present exactly once (`SELECT DISTINCT seed` = 30 unique values) — confirmed no duplication or gap from the two-invocation provenance. **`battery_summary.json` on disk is stale**: the second invocation's summary write overwrote the file with `"n": 16"` (the resumed slice only), not the merged 30. Every metric in this document is recomputed from the full 30-row `battery_raw.jsonl` + `events.sqlite3`, not from that file.

---

## Method

- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded from the denominator); all-30 basis also reported for comparability with prior single-lever docs.
- **Dose verification, two layers:**
  1. **Contract layer** — `git diff` of the new weapon/loadout files against their un-modified baselines, confirming the only field changed is `damage` (×5.5) and the only module swap is the two weapon IDs.
  2. **Engine layer** — reconstructed `damage_raw` per hit by pairing each `hit_resolved` event with the `armor_absorbed` event at `sequence_in_tick + 1` in the same `(match_id, tick)` (`damage_raw = damage_after_armor + absorbed_amount`, per `steel_onslaught.reducers.damage.compute_armor_reduction`'s invariant `effective = damage_raw − absorbed`), cross-checked against `damage_raw = int(weapon.damage × target_class_effectiveness[target.chassis_class])` from `match/runner.py`. Pairing verified zero-mismatch across all 93 red-caused hits (11 ticks in the battery have 2 hits in the same tick from both weapons firing; the triple `hit_resolved → armor_absorbed → damage_applied` is confirmed to always occupy 3 consecutive `sequence_in_tick` values even in that case).
- **Damage-after-armor caveat:** this arena's armor model (`compute_armor_reduction`) is a **degrading, capped-fraction pool**, not a flat subtraction: `absorbed = min(armor_value_remaining, ceil(damage_raw × mitigation_cap))` (`mitigation_cap=0.75` for `standard`-type weapons — both `machine_gun`/`shrapnel_thrower` are `damage_type: standard`), and armor degrades per hit (no mid-match regen observed in this pairing). Because absorption scales with `damage_raw` up to the 75% cap (subject to the remaining pool), a ×5.5 raw-damage dose does **not** mechanically imply ×5.5 damage-after-armor — a larger raw hit also gets a larger *absolute* absorption whenever the pool isn't exhausted, compressing the effective multiplier below the raw-damage multiplier. This is the same mechanism documented in the P1 (×3) verification doc. The raw-damage reconstruction above is the correct dose-landed proof; damage-after-armor is reported alongside for context only, not as a pass/fail test.
- **Utility keep-rate per seat** = utility cards programmed into a register (`plan_committed.registers[].card_id` matching `card.utility.%`) ÷ utility cards dealt (`hand_dealt.card_ids` matching `card.utility.%`), same method as the 2026-07-23/07-24 baseline docs and the P1 doc. Filtered to the 30 valid `match_id`s (excludes the orphan crashed match).

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` events (raw, incl. crashed first-attempt seed 5015) | 31 |
| `match_ended` events (= decided/aborted matches in the final 30) | 30 |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5024) |
| play_terminal_fraction | **0.9667** (gate: ≥0.9 task threshold and ≥0.95 codebase default `--gate-threshold` — PASS on both) |
| Winner distribution | player.blue 24, player.red 5, draw 1 (the abort) |
| **Decided-match red win rate (aborts excluded)** | **5/29 = 0.1724** |
| **All-match red win rate (aborts included, denominator 30)** | **5/30 = 0.1667** |
| 95% Wilson CI, decided-29 basis | **[0.0760, 0.3455]** |
| 95% Wilson CI, all-30 basis | [0.0734, 0.3356] |
| Replay validity | 1/1 both players, all 30 matches |

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once) and cross-checked against `events.sqlite3` (`SELECT COUNT(DISTINCT match_id) FROM events WHERE event_type='match_ended'` = 30). Matches the runner's raw tally exactly, per-seed, with zero discrepancy: red wins are seeds 5003, 5007, 5009, 5023, 5027 (all `elimination`/`last_mech_standing`); seed 5024 is the sole abort (`provider_semantic_failure`, red seat, `malformed_json`, 3 consecutive failed plan attempts before the plan-attempt budget was exhausted — confirmed via `llm_completion_failed` grouped by `match_id`: `match.01KYAN0MV165F9Q7785GDFWR2D` has exactly 3 failures and is the only match with a non-`elimination` terminal class among the 30).

The point estimate (16.7–17.2%) sits solidly inside the `0.10–0.35` DIRECTIONAL band, well clear of both edges. This is a materially different outcome from P1 (×3 dose, same approach-fix pairing): P1 scored 1/29 (FAILED, `<0.10`), P2 scores 5/29 — a 5× jump in win count for a 1.83× larger raw-damage multiplier, consistent with a dose-response relationship rather than a flat/noisy signal (though n=30 per arm is not enough to fit a real dose-response curve, only to note the direction is right).

## 2. Match length

| Metric | P2 (mortar_r30 + dmg×5.5) | v1 anchor | arm-1 alone | recut-v2 | P1 (dmg×3) |
|---|---:|---:|---:|---:|---:|
| min ticks | 1 (abort) / 18 (elimination) | — | 14 | — | 1 (abort) / 13 |
| median ticks | **30** | 31 | 28 | 33 | 31 |
| mean ticks | 30.1 (all 30, incl. the 1-tick abort) / 31.1 (elimination-only, n=29) | — | 27.7 | — | 31.4 / 32.4 |
| max ticks | 50 | — | 44 | — | 61 |

Median (30) sits between arm-1-alone (28) and the v1/P1 anchors (31), essentially flat relative to the family of prior batteries on this overlay shape — the added lethality dose did not systematically shorten or lengthen matches. The longest match (50 ticks, seed 5027) is one of the five red wins, not a general pattern (the other four red wins run 32–38 ticks, inside the normal distribution).

## 3. Dose verification (raw weapon damage)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `contracts_data/weapons/machine_gun.yaml` → `machine_gun_dmg55.yaml` | `damage: 8` | `damage: 44` | `damage` only (range/pressure_cost/heat/cooldown/accuracy_curve/target_class_effectiveness/damage_type/compatibility byte-identical) |
| `contracts_data/weapons/shrapnel_thrower.yaml` → `shrapnel_thrower_dmg55.yaml` | `damage: 12` | `damage: 66` | `damage` only, same identical-field guarantee |
| `contracts_data/loadouts/llm_qwen35_berserker.yaml` → `llm_qwen35_berserker_dmg55.yaml` | `weapons: [machine_gun, shrapnel_thrower]` | `weapons: [machine_gun_dmg55, shrapnel_thrower_dmg55]` | weapon-slot module IDs only; chassis/boiler/pilot/sensors/cooling/armor/gizmos/budgets byte-identical |

Confirmed via direct file read of each pair — exactly ×5.50 on both weapons at the contract layer, zero other fields touched. `match_started` runtime snapshot for seed 5001 independently confirms the wiring landed: `mech.red.01.loadout_id = "loadout.llm.qwen35_berserker_dmg55"`, `weapon_cooldowns` keys `weapon.light.machine_gun_dmg55` / `weapon.light.shrapnel_thrower_dmg55` (red, `chassis_class=light`, hp=60/armor=6); `mech.blue.01.loadout_id = "loadout.llm.qwen35_sniper_ironclad_mortar_r30"` (blue, `chassis_class=heavy`, hp=160/armor=16) — matches the program's stated forensic baseline (60HP red / 160HP+16-armor blue) exactly.

### 3b. Engine layer (reconstructed from live event data)

Blue's `chassis_class` is `heavy`, which sets `target_class_effectiveness.heavy` = 0.7 (machine gun) / 0.6 (shrapnel thrower) — unchanged by this arm (only `damage` was edited). Reconstructed `damage_raw` per hit via `hit_resolved` + `armor_absorbed` pairing (Method), cross-checked against `int(weapon.damage × 0.7-or-0.6)`:

| Weapon | Baseline raw (P1 doc: int(8×0.7)=5 / int(12×0.6)=7) | P2 raw observed | Ratio |
|---|---:|---:|---:|
| `machine_gun_dmg55` | 5 | **30** (64/93 red hits, 100% consistent, `int(44×0.7)=30`) | 6.00× |
| `shrapnel_thrower_dmg55` | 7 | **39** (29/93 red hits, 100% consistent, `int(66×0.6)=39`) | 5.57× |

Both weapons land at exactly one raw-damage value each across all 93 red-on-blue hits in the battery (zero variance) — the dose is deterministic and confirmed at the engine layer, 5.57×–6.00×, both bracketing the intended 5.5×. Same as the P1 doc's finding for ×3, the sub/super-exact-5.5× spread is an `int()` truncation artifact, not dose drift: `int(44×0.7)=30` vs `5.5×5=27.5`→truncation on the *baseline* side too, not the variant; `int(66×0.6)=39` vs `5.5×7=38.5` (39 is the correctly-rounded observed value, near-exact). Hit-count-weighted total raw damage ratio: `(64×30 + 29×39) / (64×5 + 29×7) = 3051 / 523 = 5.83×` — solidly bracketing 5.5×.

### 3c. Damage-after-armor (context, not a dose-landed test — see Method)

| | P2 red→blue | Historical baseline (context, cited) |
|---|---:|---:|
| Mean damage-after-armor per hit | **26.68** (n=93 hits) | 5.98 |
| Median | 28 | — |
| Ratio to baseline | 4.46× | — |

As documented in Method, this sub-5.5× ratio is expected, not anomalous: the armor model absorbs up to 75% of `damage_raw` (capped by the remaining armor pool), so a larger raw hit also gets a larger *absolute* absorption whenever the pool isn't already exhausted, compressing the effective multiplier below the raw-damage multiplier. The per-hit distribution confirms this mechanism directly — `machine_gun_dmg55` hits (raw=30) span `damage_after_armor` 14 (armor pool intact, near-full 75%-of-30≈23-capped-at-16-remaining-armor absorption: 23/64 hits) up to 29 (armor pool nearly depleted, ~1 point absorbed: 18/64 hits); `shrapnel_thrower_dmg55` hits (raw=39) cluster overwhelmingly at 38 (armor already fully depleted from an earlier hit, minimal absorption: 21/29 hits).

**Conclusion: the dose landed exactly as designed.** The contract diff and the deterministic raw-damage reconstruction both independently confirm ×5.5 (bracketed 5.57×–6.00×, hit-weighted 5.83×); the damage-after-armor figure diverges from a naive ×5.5 expectation for the same mechanically-verified, non-anomalous reason documented in the P1 doc — this is **not** a vacuous or mis-applied-dose result.

## 4. Hits-to-kill

| | P2 | Historical baseline (context, cited) | P1 (×3, context) |
|---|---:|---:|---:|
| Blue kills red — mean hits (24 kills) | **2.67** (median 3, range 2–3) | ~2.04 | 2.75 |
| Red kills blue — mean hits (5 kills) | **6.40** (median 6, range 6–7) | ~26.74 | 12 (n=1) |

`mech_destroyed` event counts corroborate the win tally exactly: blue destroyed in 5 matches (= the 5 red wins), red destroyed in 24 matches (= the 24 blue wins), 5+24=29 = all elimination terminals, zero unexplained destructions. Red's kill speed against blue improved sharply and consistently across all 5 wins (6–7 hits, tight range) versus the historical ~26.74 — a ~4.2× reduction, closely tracking the 4.46× damage-after-armor multiplier from §3c (26.74/4.46 ≈ 6.0, matching the observed mean of 6.40). Blue's kill speed against red is essentially unchanged from baseline (2.67 vs 2.04, both seats' weapons on blue's side untouched by this arm) — the small increase is within normal n=24 sampling noise, not a lever effect.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate | P1 (×3, context) |
|---|---:|---:|---:|---:|
| red (brawler) | 378 | 12 | **0.0317** | 0.043 |
| blue (sniper) | 378 | 42 | **0.1111** | 0.079 |
| all-card sanity, both seats | 945/1890 (each seat) | 945/1890 (each seat) | 0.5000 (mechanical, confirms 5-of-10 register structure held) | 0.500 |

Both seats show low utility pickup (3–11%), consistent with the program's recurring finding that utility cards lose out to weapon/movement cards under this deal/program ratio — not a new effect of this arm, and roughly the same order of magnitude as the P1 battery on the same overlay shape.

## 6. Completion health

| Metric | Value (filtered to the 30 valid matches) |
|---|---|
| `llm_completion_requested` | 397 |
| `llm_completion_resolved` | 379 |
| `llm_completion_failed` | 18 |
| `finish_reason` distribution | `stop`: 379/379 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 378/378 (zero fallback/heuristic plans) |
| Matches with ≥1 failed completion | 13/30 |
| Max single-match failures | 3 (seed 5024 — the abort; also seed 5027, recovered) |
| Matches reaching an unrecovered abort | 1/30 (seed 5024) |
| Retries at the battery-runner level (transport failure) | 1 (seed 5015 first attempt, `LlmTransportError`, resumed clean — see §0) |

397 requested − 379 resolved = 18, matching `llm_completion_failed` exactly. All but one match's within-match retries were recovered (`finish_reason=stop`, `plan_source=llm` on all 378 final plans); seed 5024 hit 3 consecutive `malformed_json` failures on the red seat and exhausted its plan-attempt budget, consistent with `play_terminal_fraction=0.9667` and the single non-elimination terminal.

## 7. Merge / additivity verification

- PR #170 merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (`gh pr view 170`: state MERGED, mergedAt 2026-07-24T17:32:38Z, base `main`, title "feat: pair-sweep arms — mortar_r30 x lethality dose-response (red dmg x3, x5.5; blue armor 8)").
- 4/4 CI checks green (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: SUCCESS`).
- `git diff 7cb8634 255f2306 -- contracts_data/weapons/machine_gun.yaml contracts_data/weapons/shrapnel_thrower.yaml contracts_data/weapons/artillery_mortar.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/chassis/heavy_ironclad_mk1.yaml` returns **empty** (`7cb8634` = the commit immediately preceding the pair-sweep PR on `main`) — every baseline file this arm depends on is byte-identical pre/post-merge. 13 files changed in the PR overall, all additive (P1/P2/P3 weapon/loadout/armor/overlay variants + `tests/contracts/test_pair_sweep_arms.py`), zero deletions.

---

## Verdict

**DIRECTIONAL.** Decided-match red win rate is 0.1724 (5/29), all-30 basis 0.1667 (5/30) — inside the `0.10–0.35` DIRECTIONAL band, Wilson 95% CI [0.076, 0.345] not crossing into COMPETITIVE. `play_terminal_fraction=0.9667` clears the trust gate on both the task-stated ≥0.9 threshold and the codebase's own ≥0.95 default. The intended ×5.5 raw-damage dose is verified to have landed exactly as designed at both the contract layer (direct diff, exact ×5.5 on the `damage` field) and the engine layer (deterministic per-hit raw-damage reconstruction, zero variance across 93 hits, 5.57×–6.00× bracketing 5.5× once `int()` truncation is accounted for, hit-weighted 5.83×) — **this is not a vacuous or mis-applied-dose result.** The damage-after-armor figure (26.68, 4.46× baseline) undershoots a naive ×5.5 expectation for the same mechanically-verified, non-anomalous reason documented in the P1 doc: the degrading-pool, capped-fraction armor model compresses the effective multiplier. Pairing the approach fix (mortar_r30) with the historical ×5.5 dose produced 5 red wins in thirty matches — a clear step up from P1's ×3 dose (1/29), from both single-lever nulls (v1 anchor 0/30, arm-1-alone 0/30), and from the historical ×5.5-alone rate itself (~5%, 1/43) — consistent with the pairing hypothesis that the approach fix and the lethality dose compound rather than substitute. Red's kill speed against blue dropped sharply and consistently (6.40 mean hits vs historical ~26.74, tight 6–7 range across all 5 wins), internally consistent with the measured damage multiplier (26.74/4.46 ≈ 6.0 ≈ observed 6.40). Blue's kill speed against red is essentially unchanged (2.67 vs historical 2.04), as expected since this arm does not touch blue's weapons.

**Implication for the pair-sweep:** P2 is the strongest single arm in this program to date — the first result inside the DIRECTIONAL band rather than FAILED — but still falls well short of COMPETITIVE (0.35–0.65). P3 (blue armor 16→8, lethality via mitigation rather than red damage, zero red-side buffs) remains the third leg of the decisive-experiment design and is the deciding comparison for whether an armor-side lethality dose, combined with the same approach fix, matches or exceeds P2's damage-side result.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p2_dmg55/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `damage_applied`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against the stale partial `battery_summary.json` (n=16 only — see §0) and the crashed first-attempt / resume scratchpad logs.
- Contract diffs: `contracts_data/weapons/{machine_gun,shrapnel_thrower}.yaml` vs `*_dmg55.yaml`; `contracts_data/loadouts/llm_qwen35_berserker.yaml` vs `llm_qwen35_berserker_dmg55.yaml`; `contracts_data/loadouts/qwen35/sniper_ironclad.yaml` vs `sniper_ironclad_mortar_r30.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction model, `_MITIGATION_CAP[STANDARD]=0.75`).
- Merge commit: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`).
- Pair P1 (×3) reference doc: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md` (PR #177).
- Ledger: `docs/tracking/ROLLING_WORK_LEDGER.md` (2026-07-24 SO-PAIR P2 entry).
- No secrets, keys, or absolute paths included.
