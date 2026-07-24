# Pair-Sweep Arm P1 (mortar_r30 × red-dmg×3) Battery — Independent Verification (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **1/29 = 0.0345** (all-30 basis: **1/30 = 0.0333**) — inside the `<0.10` FAILED band, 95% Wilson CI **[0.0061, 0.1718]** on the all-30 basis. The dose lands correctly at the raw-weapon-damage layer (contract-verified exactly ×3, engine-reconstructed at ×3.0–3.2 after integer truncation), but pairing it with the merged mortar_r30 approach fix still produces only one red win in thirty matches — a small, non-zero improvement over both single-lever nulls (v1 anchor 0/30, arm-1-alone 0/30) but far short of competitive, and below the historical single-lever ×5.5-alone rate of ~5% (1/43, different regime).

**Ledger:** `.onex_state/steel_onslaught/pair_p1_dmg3` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-PAIR worktree.
**Change under test:** PR #170 (merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0`) — two levers, exactly two:
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`, first merged under PR #159) — swaps only `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_r30` (range 50 → 30), every other module/field identical.
2. Red loadout `loadout.llm.qwen35_berserker_dmg3` (`contracts_data/loadouts/llm_qwen35_berserker_dmg3.yaml`) — swaps both berserker weapons for damage-×3 variants (`machine_gun_dmg3`: damage 8 → 24; `shrapnel_thrower_dmg3`: damage 12 → 36), every other weapon field identical.
Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p1_dmg3_qwen.yaml` is the same U-GATE/O-GATE combined shape as the v1 overlay, isolated `.onex_state` paths only. Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baselines:** v1 anchor 0/30 median 31 ticks; arm-1 (mortar_r30 alone) 0/30 median 28 ticks; recut-v2 0/30 median 33 ticks; historical single-lever ×5.5-alone ~5% (1/43, prior lethal-approach regime).
- All figures below are independently recomputed by an adversarial verifier directly from `events.sqlite3` and `battery_raw.jsonl` — not copied from the runner's or implementer's report — with an explicit contract-level and engine-level check of whether the intended ×3 damage dose actually landed.

---

## Method

- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded from the denominator); all-30 basis also reported for comparability with prior single-lever docs.
- **Dose verification, two layers:**
  1. **Contract layer** — `git diff` of the new weapon/loadout files against their un-modified baselines, confirming the only field changed is `damage` (×3) and the only module swap is the two weapon IDs.
  2. **Engine layer** — reconstructed `damage_raw` per hit from paired `hit_resolved` + `armor_absorbed` events (`damage_raw = damage_after_armor + absorbed_amount`, since `steel_onslaught.reducers.damage.compute_armor_reduction` guarantees `effective = damage_raw − absorbed`), cross-checked against `damage_raw = int(weapon.damage × target_class_effectiveness[target.chassis_class])` from `match/runner.py`.
- **Damage-after-armor caveat:** this arena's armor model (`compute_armor_reduction`) is a **degrading, capped-fraction pool**, not a flat subtraction: `absorbed = min(armor_value_remaining, ceil(damage_raw × mitigation_cap))` (`mitigation_cap=0.75` for `standard`-type weapons), and armor regenerates per tick toward `armor_max`. Because absorption scales with `damage_raw` up to the 75% cap (subject to the remaining pool), tripling raw damage does **not** mechanically imply tripling damage-after-armor — a naive "post-armor damage should also read ~3×" expectation does not hold under this model and is not a valid pass/fail test for whether the dose landed. The raw-damage reconstruction above is the correct dose-landed proof; it is reported alongside the (necessarily sub-3×) damage-after-armor figure for context.
- **Utility keep-rate per seat** = utility cards programmed into a register (`plan_committed.registers[].card_id` matching `card.utility.%`) ÷ utility cards dealt (`hand_dealt.card_ids` matching `card.utility.%`), same method as the 2026-07-23/07-24 baseline docs.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5003) |
| play_terminal_fraction | **0.9667** (gate: ≥0.9 — PASS) |
| Winner distribution | player.blue 28, player.red 1, draw 1 (the abort) |
| **Decided-match red win rate (aborts excluded)** | **1/29 = 0.0345** |
| **All-match red win rate (aborts included, denominator 30)** | **1/30 = 0.0333** |
| 95% Wilson CI, all-30 basis | **[0.0061, 0.1718]** |
| 95% Wilson CI, decided-29 basis | [0.0061, 0.1718] (≈ same to 4dp) |
| Replay validity | 1/1 both players, all 30 matches |

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once) and cross-checked against `events.sqlite3` (`SELECT COUNT(DISTINCT match_id)` = 30, `match_ended` = 30). Matches the runner's raw tally exactly, per-seed, with zero discrepancy: seed 5028 is the sole red win (elimination, 61 ticks — the longest match in the battery), seed 5003 is the sole abort (`provider_semantic_failure`, blue seat, `invalid_action_parameters`, 3 consecutive failed completions before the plan-attempt budget was exhausted — confirmed via `llm_completion_failed` grouped by `match_id`: `match.01KYAK1MQBDZ3KCBDTCMAW9ETZ` has exactly 3 failures and is the only match with a non-`elimination` terminal class).

The point estimate (0.033–0.034) sits solidly in the `<0.10` FAILED band. The Wilson CI upper bound (0.172) technically overlaps the low end of the DIRECTIONAL band (0.10–0.35), which is an honest small-*n* caveat — at n=30 a single win cannot rule out a "true" rate as high as ~17% — but the classification called against the point estimate, matching the convention used for every other arm in this program, is FAILED.

## 2. Match length

| Metric | P1 (mortar_r30 + dmg×3) | v1 anchor | arm-1 alone | recut-v2 |
|---|---:|---:|---:|---:|
| min ticks | 1 (abort) / 13 (elimination) | — | 14 | — |
| median ticks | **31** | 31 | 28 | 33 |
| mean ticks | 31.4 (all 30, incl. the 1-tick abort) / 32.4 (elimination-only, n=29) | — | 27.7 | — |
| max ticks | 61 | — | 44 | — |

Median (31) lands between arm-1-alone (28) and the v1/recut-v2 anchors (31/33) — the added lethality dose did not systematically shorten matches relative to the approach-fix-alone arm, consistent with red still losing almost every match by the same mechanism (blue's mortar). The longest match in the battery (61 ticks, seed 5028) is also the one red win — the only case where red survived long enough, and hit hard enough, to turn the fight.

## 3. Dose verification (raw weapon damage)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `contracts_data/weapons/machine_gun.yaml` → `machine_gun_dmg3.yaml` | `damage: 8` | `damage: 24` | `damage` only (range/pressure_cost/heat/cooldown/accuracy_curve/target_class_effectiveness/damage_type/compatibility byte-identical) |
| `contracts_data/weapons/shrapnel_thrower.yaml` → `shrapnel_thrower_dmg3.yaml` | `damage: 12` | `damage: 36` | `damage` only, same identical-field guarantee |
| `contracts_data/loadouts/llm_qwen35_berserker.yaml` → `llm_qwen35_berserker_dmg3.yaml` | `weapons: [machine_gun, shrapnel_thrower]` | `weapons: [machine_gun_dmg3, shrapnel_thrower_dmg3]` | weapon-slot module IDs only; chassis/boiler/pilot/sensors/cooling/armor/gizmos/budgets byte-identical |

Confirmed via direct `git diff` of each pair — exactly ×3.00 on both weapons at the contract layer, zero other fields touched.

### 3b. Engine layer (reconstructed from live event data)

Blue's target `chassis_class` is `heavy` (confirmed from the `match_started` snapshot), which sets `target_class_effectiveness.heavy` = 0.7 (machine gun) / 0.6 (shrapnel thrower). Reconstructed `damage_raw = int(weapon.damage × 0.7-or-0.6)` per hit, cross-checked against `damage_after_armor + absorbed_amount` from the paired `hit_resolved`/`armor_absorbed` events:

| Weapon | Baseline raw (int(8×0.7)=5 / int(12×0.6)=7) | P1 raw observed | Ratio |
|---|---:|---:|---:|
| `machine_gun_dmg3` | 5 | **16** (71/101 red hits, 100% consistent) | 3.20× |
| `shrapnel_thrower_dmg3` | 7 | **21** (30/101 red hits, 100% consistent) | 3.00× |

Both weapons land at exactly one raw-damage value each across all 101 red-on-blue hits in the battery (zero variance) — the dose is deterministic and confirmed at the engine layer, ×3.0–3.2 (the sub-exact-3× reading on machine gun is `int()` truncation on both baseline and variant, not dose drift: `int(24×0.7)=16` vs `3×int(8×0.7)=15`, a rounding artifact, not a measurement failure).

### 3c. Damage-after-armor (context, not a dose-landed test — see Method)

| | P1 red→blue | Historical baseline (context, cited) |
|---|---:|---:|
| Mean damage-after-armor per hit | **11.27** (n=101 hits) | 5.98 |
| Median | 12 | — |
| Ratio to baseline | 1.88× | — |

As documented in Method, this sub-3× ratio is expected, not anomalous: the armor model absorbs up to 75% of `damage_raw` (capped by the remaining armor pool), so a larger raw hit also gets a larger *absolute* absorption whenever the pool isn't already exhausted, compressing the effective multiplier below the raw-damage multiplier. The bimodal per-hit distribution confirms this mechanism directly — `machine_gun_dmg3` hits cluster at `damage_after_armor=4` (armor pool intact, full 75% cap applied: 19/71 hits) and at `damage_after_armor=15` (armor pool nearly depleted, ~1 point of absorption: 15/71 hits), tracking blue's armor regeneration/depletion cycle rather than a fixed ratio.

**Conclusion: the dose landed exactly as designed.** The contract diff and the deterministic raw-damage reconstruction both independently confirm ×3; the damage-after-armor figure diverges from a naive ×3 expectation for a mechanically explained, verified reason, not because the dose failed to apply.

## 4. Hits-to-kill

| | P1 | Historical baseline (context, cited) |
|---|---:|---:|
| Blue kills red — mean hits (28 kills) | **2.75** | ~2.04 |
| Blue kills red — hit-count distribution | {2: 9, 3: 18, 4: 1} | — |
| Red kills blue — hits (n=1, seed 5028) | **12** | ~26.74 |

Blue's kill speed against red is essentially unchanged (2.75 vs 2.04 hits — same order of magnitude, blue's weapon and red's HP/armor were not touched by this arm). Red's one successful kill needed 12 hits versus the historical baseline's ~26.74 — a >2× reduction in hits-required, directionally consistent with the ×3 raw-damage dose, though this is a single observation (n=1) and cannot be treated as a stable rate.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate |
|---|---:|---:|---:|
| red (brawler) | 392 | 17 | **0.043** |
| blue (sniper) | 392 | 31 | **0.079** |
| all-card sanity, both seats | 1960 / 1960 | 980 / 980 | 0.500 (mechanical, confirms 5-of-10 register structure held) |

Both seats show low utility pickup (4–8%), consistent with the program's recurring finding that utility cards lose out to weapon/movement cards under this deal/program ratio — not a new effect of this arm.

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 419 |
| `llm_completion_resolved` | 392 |
| `llm_completion_failed` | 27 |
| `finish_reason` distribution | `stop`: 392/392 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 392/392 (zero fallback/heuristic plans) |
| Matches with ≥1 failed completion | 17/30 |
| Max single-match failures | 3 (seed 5003 — the abort; also seed matching `match.01KYAK7XTXS1Z31B8DQF191P11`, recovered) |
| Matches reaching an unrecovered abort | 1/30 (seed 5003) |

419 requested − 392 resolved = 27, matching `llm_completion_failed` exactly. All but one match's failures were recovered by retry (`finish_reason=stop`, `plan_source=llm` on all 392 final plans); seed 5003 hit 3 consecutive `invalid_action_parameters` failures on the blue seat and exhausted its plan-attempt budget, consistent with `play_terminal_fraction=0.9667` and the single non-elimination terminal.

## 7. Merge / additivity verification

- PR #170 merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (`gh pr view 170`: state MERGED, mergedAt 2026-07-24T17:32:38Z, base `main`).
- 4/4 CI checks green (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: success`).
- `git diff <pre-merge-parent> 255f230 --stat` shows **13 files changed, 1300 insertions(+), 0 deletions** — every changed file is either a new additive contract file (P1/P2/P3 weapon/loadout/armor/overlay variants) or a new test file; the two pilot-registry lines added (`llm_qwen35_berserker_dmg3.yaml`, `llm_qwen35_berserker_dmg55.yaml` pinned to `pilot.llm.qwen35`) are additive registrations, not edits to an existing entry. A direct `git diff` of the specific baseline files this arm depends on (`machine_gun.yaml`, `shrapnel_thrower.yaml`, `llm_qwen35_berserker.yaml`, `sniper_ironclad.yaml`, `sniper_ironclad_mortar_r30.yaml`, `foundry_60_asym_v1.yaml`, `artillery_mortar.yaml`, `artillery_mortar_r30.yaml`) across the merge returns **empty** — all byte-identical pre/post-merge.

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0345 (1/29), all-30 basis 0.0333 (1/30) — inside the `<0.10` FAILED band. `play_terminal_fraction=0.9667` clears the ≥0.9 trust gate. The intended ×3 raw-damage dose is verified to have landed exactly as designed at both the contract layer (direct diff) and the engine layer (deterministic per-hit raw-damage reconstruction, zero variance across 101 hits) — this is not a vacuous or mis-applied-dose result. Pairing the approach fix (mortar_r30) with a ×3 lethality dose produced exactly one red win in thirty matches (the longest match in the battery), a small qualitative change from the double-null baseline (v1 anchor 0/30, arm-1-alone 0/30) but not a competitive or even clearly directional shift, and below the historical single-lever ×5.5-alone rate (~5%, different regime, itself already a weak result). Blue's kill speed against red is essentially unchanged (2.75 vs historical 2.04 hits); red's one kill needed markedly fewer hits than the historical baseline (12 vs ~26.74) but this is a single data point. The damage-after-armor figure (11.27, 1.88× baseline) undershoots a naive ×3 expectation for a mechanically verified, non-anomalous reason — the degrading-pool, capped-fraction armor model compresses the effective multiplier — and should not be read as evidence the dose failed.

**Implication for the pair-sweep:** P1's ×3 dose, paired with the approach fix, is a FAILED result but not a null one — it is the first non-zero outcome in this program under the paired-approach-fix regime. P2 (×5.5, the historical dose, now paired) and P3 (blue armor 16→8, lethality via mitigation rather than red damage) remain the deciding comparisons for whether a larger or differently-targeted lethality dose, combined with the same approach fix, can cross into the DIRECTIONAL band.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p1_dmg3/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `damage_applied`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against `battery_summary.json`.
- Contract diffs: `contracts_data/weapons/{machine_gun,shrapnel_thrower}.yaml` vs `*_dmg3.yaml`; `contracts_data/loadouts/llm_qwen35_berserker.yaml` vs `llm_qwen35_berserker_dmg3.yaml`; `contracts_data/loadouts/qwen35/sniper_ironclad.yaml` vs `sniper_ironclad_mortar_r30.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction model); `src/steel_onslaught/match/runner.py:1436-1449` (`damage_raw = int(spec.damage * effectiveness)`, armor reduction call site).
- Merge commit: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`).
- Ledger: `docs/tracking/ROLLING_WORK_LEDGER.md` (2026-07-24 SO-PAIR P1 entry).
- No secrets, keys, or absolute paths included.
