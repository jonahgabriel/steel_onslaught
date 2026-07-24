# Pair-Sweep Arm P4 (mortar_r30 × red-dmg×8) Battery — Independent Verification (2026-07-24)

**Verdict:** **DIRECTIONAL.** Decided-match red (brawler) win rate is **8/29 = 0.2759** (all-30 basis: **8/30 = 0.2667**) — inside the `0.10–0.35` DIRECTIONAL band, 95% Wilson CI **[0.1470, 0.4572]** (decided-29 basis) / **[0.1418, 0.4445]** (all-30 basis). This is the fourth and strongest point on the dose-response curve (x1 0%, x3 3.4%, x5.5 17.2%, x8 27.6%), still well short of the 0.35 COMPETITIVE threshold on point estimate but the first arm whose Wilson upper bound (0.4572) visibly crosses above 0.35 — a wider overlap into COMPETITIVE territory than P2 exhibited (P2's upper bound, 0.345, stayed just under the line). The intended ×8 raw-damage dose is confirmed to have landed exactly as predicted at both the contract layer (exact ×8 on the `damage` field, direct diff) and the engine layer (deterministic per-hit raw-damage reconstruction, zero variance across all 68 red-caused hits, observed ratios 8.14×–8.80× matching the pre-registered engine-layer prediction to the hit).

**This document corrects a prior program claim.** The merged P2 evidence doc and the session handoff (`docs/handoffs/2026-07-24-brawler-competitiveness-session.md`, §7: "P1/P2 dose-response is monotonic and accelerating, not linear") characterized the first three points as accelerating. This fourth point falsifies the *accelerating* half of that claim: the marginal win-rate gain per unit of additional dose rose from 1.72 pp/unit (×1→×3) to 5.52 pp/unit (×3→×5.5), then **fell** to 4.14 pp/unit (×5.5→×8). Monotonic still holds (win rate keeps climbing in absolute terms); accelerating does not — the shape through four points is rise-then-inflect-then-slow, i.e. saturating, not accelerating. Full arithmetic and a candidate (hypothesis-only) mechanism are in §0 below; see also §8.

**Ledger:** `.onex_state/steel_onslaught/pair_p4_dmg8` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-PAIR-P4 worktree.
**Change under test:** two levers, exactly two, both additive contract files (uncommitted at battery time, committed alongside this document):
1. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`, merged under PR #159/#170, unmodified by this arm) — the shared approach-fix lever, held constant across P1/P2/P3/P4.
2. Red loadout `loadout.llm.qwen35_berserker_dmg8` (`contracts_data/loadouts/llm_qwen35_berserker_dmg8.yaml`) — swaps both berserker weapons for damage-×8 variants (`machine_gun_dmg8`: damage 8 → 64; `shrapnel_thrower_dmg8`: damage 12 → 96), every other weapon field identical to the un-modified baselines.
Overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p4_dmg8_qwen.yaml` is byte-identical to the merged P2 overlay except for the red loadout id, the dose-curve comment block, and isolated `.onex_state` ledger paths (verified by direct diff — see §3a). Arena (`foundry_60_asym_v1`) untouched.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, single-invocation-per-seed battery (no resume/segmentation — see §0b), `all_replay_valid=true` (1/1 both players, all 30 matches).
**Baselines:** v1 anchor 0/30 median 31 ticks; arm-1 (mortar_r30 alone) 0/30 median 28 ticks; recut-v2 0/30 median 33 ticks; pair P1 (mortar_r30 + red-dmg×3) 1/29 = 0.0345, FAILED; pair P2 (mortar_r30 + red-dmg×5.5) 5/29 = 0.1724, DIRECTIONAL; pair P3 (mortar_r30 + blue-armor-8) 0/28 = 0.0000, FAILED; historical single-lever ×5.5-alone ~5% (1/43, prior lethal-approach regime).
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl` — not copied from `battery_summary.json` or the runner's stdout — with an explicit contract-level and engine-level check of whether the intended ×8 damage dose actually landed.

---

## 0. Correction to the prior "monotonic and accelerating" claim (read this first)

The P2 evidence doc (`docs/evidence/2026-07-24-pair_p2_dmg55-battery.md`) and the session handoff (`docs/handoffs/2026-07-24-brawler-competitiveness-session.md`, §7, "P1/P2 dose-response is monotonic and accelerating, not linear") both describe the three-point curve available at the time (×1→×3→×5.5) as accelerating, citing "a 1.83× larger dose produced a ~5× jump in win count." That characterization was a reasonable read of three points, but three points cannot distinguish an accelerating curve from a saturating (rise-then-inflect-then-slow) one — both look identical over the first two intervals. This document's fourth point resolves the ambiguity:

| Step | Δdose | Δ win rate (decided basis, pp) | Marginal rate (pp / dose-unit) |
|---|---:|---:|---:|
| ×1 → ×3 | 2.0 | +3.45 | 1.72 |
| ×3 → ×5.5 | 2.5 | +13.79 | 5.52 |
| ×5.5 → ×8 | 2.5 | +10.34 | **4.14 — down, not up** |

The marginal rate rose across the first two intervals (1.72 → 5.52 pp/unit, consistent with "accelerating") and then **fell** on this third interval (5.52 → 4.14 pp/unit). **Monotonic still holds** — win rate keeps climbing in absolute terms at every step (0% → 3.45% → 17.24% → 27.59%) — but **accelerating does not survive this fourth point**. The correct description of the shape through four points is a curve that rises, inflects, and is now decelerating — consistent with saturation, not with continued acceleration. This is a correction to the prior docs' record, not a silent supersession: the prior characterization is left as written in those documents (this program does not retroactively edit closed/merged evidence docs), and this document is the record of what changed.

**Candidate mechanism (hypothesis, not proven):** §3c below documents that blue's armor pool is fully saturated (`armor_after == 0`) on **all 68 of 68** red-caused hits at this dose — a strictly larger fraction than P2 showed at ×5.5, where the P2 doc's own published per-hit breakdown reports only a majority saturating (23/64 `machine_gun_dmg55` hits landed at full 16-point absorption, the other 18/64 at a depleted-pool absorption of ~1). Once the armor pool saturates on (near-)every hit, additional raw damage no longer buys additional *effective* damage-after-armor at the same marginal rate — it increasingly converts into overkill on the last hit of a kill sequence rather than shortening the number of hits required. This is a mechanically coherent and quantitatively clean candidate explanation for why the marginal win-rate gain per dose-unit would fall as saturation approaches 100%. **It is not proven by this document.** Three dose points, one battery per point (n=30 matches each), is not enough to establish this as the demonstrated cause of the deceleration — it is the most plausible mechanism consistent with the measured armor-saturation numbers, and no more than that.

**Forward-looking note (inference, not a result — no plateau value is stated):** if lethality dosing on the raw-damage axis is approaching saturation against blue's fixed 16-point armor pool, further escalation on this same lever (e.g. ×11, ×16) is the *lowest*-information next experiment: the saturation hypothesis predicts diminishing marginal returns, and — if the hypothesis holds — a plateau that may sit below the 0.35 COMPETITIVE band. This document does not have enough points to fit a curve or name a plateau value, and does not attempt to. A lever other than raw red damage (P3 already showed the armor-pool-size lever alone is a null, 0/28) may be more informative than a fifth point on this axis.

---

## 0b. Raw-file provenance (single-invocation battery, no resume)

Unlike the P2 and P3 batteries (both of which crashed mid-run on a `LlmTransportError` and required a resumed second invocation), P4 was run as **30 independent per-seed process invocations** against a shared, append-mode state root (`run_p4.sh`, seeds 5001–5030 in a `for` loop, `--n 1` per seed, up to 2 attempts per seed with a 420s timeout, `--fresh` only on the very first seed). This design means a transport failure on any single seed kills only that seed's process, not the whole 30-seed run — a deliberate hardening after the P2/P3 crash-and-resume pattern. In practice, **every one of the 30 seeds succeeded on attempt 1**; no seed required a retry (confirmed directly from the driver log: exactly 30 `### seed=NNNN attempt=1` blocks, zero `attempt=2` blocks, zero `FAILED rc=` lines).

Independently verified: `battery_raw.jsonl` has exactly 30 lines, `seed` values are 5001–5030 with **zero duplicates and zero gaps** (`len(set(seeds))==30`, `min=5001`, `max=5030`). Cross-checked against `events.sqlite3`: `SELECT COUNT(DISTINCT match_id) FROM events WHERE event_type='match_started'` = 30 and same for `match_ended` = 30, and the set of `match_id`s in `battery_raw.jsonl` is exactly equal to the set of `match_id`s with a `match_started` event (no orphans, no missing rows). `battery_summary.json` on disk reflects the same single, complete 30-row run (no stale-partial-slice risk this time, since there was no resume) — this document's figures are still independently recomputed from the raw file and event log, not read from that summary, per program convention.

---

## Method

- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded from the denominator); all-30 basis also reported for comparability with prior arms.
- **Dose verification, two layers:**
  1. **Contract layer** — direct diff of the new weapon/loadout files against their un-modified baselines, confirming the only field changed is `damage` (×8) and the only module swap is the two weapon IDs.
  2. **Engine layer** — reconstructed `damage_raw` per hit by pairing each `hit_resolved` event (`{"attacker_id","defender_id","result":{"hit","damage_after_armor"}}`) with the `armor_absorbed` event (`{"target_id","absorbed_amount","armor_after"}`) at `sequence_in_tick + 1` in the same `(match_id, tick)` (`damage_raw = damage_after_armor + absorbed_amount`, per `steel_onslaught.reducers.damage.compute_armor_reduction`'s invariant `effective = damage_raw − absorbed`). Weapon attribution comes from the closest preceding `weapon_fired` event (`{"weapon_id","target_id","hit_probability",...}`) targeting the same defender in the same `(match_id, tick)` — `hit_resolved` carries no `weapon_id` itself. Pairing verified zero-mismatch across all 126 `hit_resolved` events in the battery (68 red-caused, 58 blue-caused); zero unattributed red hits.
- **Damage-after-armor caveat:** this arena's armor model (`compute_armor_reduction`) is a **degrading, capped-fraction pool**, not a flat subtraction: `absorbed = min(armor_value_remaining, ceil(damage_raw × mitigation_cap))` (`mitigation_cap=0.75` for `standard`-type weapons — both `machine_gun`/`shrapnel_thrower` are `damage_type: standard`). Because absorption is capped by whichever of the two terms is smaller, a ×8 raw-damage dose does **not** mechanically imply ×8 damage-after-armor. The raw-damage reconstruction above is the correct dose-landed proof; damage-after-armor is reported alongside for context only, never as a pass/fail test (same convention as the P1/P2/P3 docs).
- **Utility keep-rate per seat** = utility cards programmed into a register (`plan_committed.registers[].card_id` matching `card.utility.%`) ÷ utility cards dealt (`hand_dealt.card_ids` matching `card.utility.%`), same method as the P1/P2/P3 docs. Filtered to the 30 valid `match_id`s (there are no orphan/crashed matches to exclude in this battery — see §0b).

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5028) |
| play_terminal_fraction | **0.9667** (task gate ≥0.9 — PASS; codebase default `--gate-threshold=0.95` — **also PASS**) |
| Winner distribution | player.blue 21, player.red 8, draw 1 (the abort) |
| **Decided-match red win rate (aborts excluded)** | **8/29 = 0.2759** |
| **All-match red win rate (aborts included, denominator 30)** | **8/30 = 0.2667** |
| 95% Wilson CI, decided-29 basis | **[0.1470, 0.4572]** |
| 95% Wilson CI, all-30 basis | [0.1418, 0.4445] |
| Replay validity | 1/1 both players, all 30 matches |

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once) and cross-checked against `events.sqlite3` (`SELECT COUNT(DISTINCT match_id) FROM events WHERE event_type='match_ended'` = 30). Matches the runner's raw per-seed tally exactly (cross-checked against the independent third source — the driver script's own stdout log — seed-for-seed, zero discrepancy): **red wins are seeds 5001, 5007, 5014, 5016, 5020, 5025, 5029, 5030** (all `elimination`/`last_mech_standing`); **seed 5028 is the sole abort** (`provider_semantic_failure`, red seat, tick 1: `invalid_action_parameters` then two consecutive `malformed_json` failures, 3 total, exhausting the plan-attempt budget before any plan was committed for that match — confirmed via direct event-log inspection of `match.01KYAT1XPK61H653M0YBKR2B88`, which has exactly 3 `llm_completion_failed` events and zero `plan_committed` events, the only match in the battery with zero committed plans). The `battery_raw.jsonl` row for this match records `winner_player_id: "player.blue"` with `is_draw: true` simultaneously — a non-decisive default value on that field, not an actual blue win; it is correctly excluded from both the numerator and denominator of the decided-match rate.

The point estimate (26.7–27.6%) sits well inside the `0.10–0.35` DIRECTIONAL band — the highest of the four dose-response points and the first to approach (though not cross) the midpoint of the band. Unlike P2 (whose Wilson upper bound, 0.345, stayed just under the 0.35 COMPETITIVE line), **this arm's decided-basis Wilson upper bound (0.4572) crosses above 0.35** — at n=29 with 8 wins, the data cannot rule out a "true" rate as high as ~46%. This is a straightforward consequence of a larger win count on the same sample size (wider absolute CI at higher phat), not evidence that the true rate is COMPETITIVE; the classification is called against the point estimate (26.7–27.6%, DIRECTIONAL), matching the convention used for every other arm in this program, but the CI overlap is flagged here explicitly since it is materially wider than P2's.

## 2. Match length

| Metric | P4 (mortar_r30 + dmg×8) | v1 anchor | arm-1 alone | recut-v2 | P1 (dmg×3) | P2 (dmg×5.5) | P3 (armor8) |
|---|---:|---:|---:|---:|---:|---:|---:|
| min ticks | 1 (abort) / 14 (elimination) | — | 14 | — | 1 / 13 | 1 / 18 | 1 / 14 |
| median ticks | **24** | 31 | 28 | 33 | 31 | 30 | 27.5 |
| mean ticks | 24.07 (all 30, incl. the 1-tick abort) / 24.86 (elimination-only, n=29) | — | 27.7 | — | 31.4 / 32.4 | 30.1 / 31.1 | 29.23 / 29.64 |
| max ticks | 38 | — | 44 | — | 61 | 50 | 66 |

P4's median (24 ticks) is the **shortest of every arm in the pair-sweep program to date**, below even P3's armor-lever arm (27.5) despite P3 scoring 0/30. This is the first arm where match length shortens *monotonically* with dose relative to the mid-dose arms (P1: 31, P2: 30, P4: 24) — consistent with a working raw-damage lethality lever compressing the match regardless of which side ultimately wins: at ×8 raw damage, fights end faster because both sides' exchanges are more lethal, not only red's specific wins. The max (38 ticks) is also the lowest ceiling of any arm in the program (all priors exceeded 44).

## 3. Dose verification (raw weapon damage)

### 3a. Contract layer

| File | Baseline | Variant | Only field changed |
|---|---|---|---|
| `contracts_data/weapons/machine_gun.yaml` → `machine_gun_dmg8.yaml` | `damage: 8` | `damage: 64` | `damage` only (`weapon_class`, `range`, `pressure_cost`, `heat_generated`, `cooldown_ticks`, `accuracy_curve`, `target_class_effectiveness`, `damage_type`, `compatibility` byte-identical, confirmed via full-file read of both) |
| `contracts_data/weapons/shrapnel_thrower.yaml` → `shrapnel_thrower_dmg8.yaml` | `damage: 12` | `damage: 96` | `damage` only, same identical-field guarantee |
| `contracts_data/loadouts/llm_qwen35_berserker.yaml` → `llm_qwen35_berserker_dmg8.yaml` | `weapons: [machine_gun, shrapnel_thrower]` | `weapons: [machine_gun_dmg8, shrapnel_thrower_dmg8]` | weapon-slot module IDs only; `chassis_id`/`boiler_id`/`pilot_id`/sensors/cooling/armor/gizmos/budgets byte-identical (confirmed budgets are unaffected — weapon contracts carry no mass field, `_module_budgets` hardcodes `mass=0` for weapons) |

Confirmed via direct file read of each pair — exactly ×8.00 on both weapons at the contract layer, zero other fields touched. The overlay diff against the merged P2 overlay (`git diff` of the two files) shows only: the red-loadout id string, an added dose-curve narrative comment block, and the isolated `.onex_state/steel_onslaught/pair_p4_dmg8/...` ledger paths — no arena, budget, or U-GATE/O-GATE gating logic changed.

`match_started` runtime snapshot for seed 5001 independently confirms the wiring landed: `mech.red.01.loadout_id = "loadout.llm.qwen35_berserker_dmg8"` (red, `chassis_class=light`, `hp_max=60`, `armor_max=6`); `mech.blue.01.loadout_id = "loadout.llm.qwen35_sniper_ironclad_mortar_r30"` (blue, `chassis_class=heavy`, `hp_max=160`, `armor_max=16`) — matches the program's stated forensic baseline exactly and is identical to the P1/P2 wiring confirmation.

### 3b. Engine layer (reconstructed from live event data)

Blue's `chassis_class` is `heavy`, which sets `target_class_effectiveness.heavy` = 0.7 (machine gun) / 0.6 (shrapnel thrower) — unchanged by this arm (only `damage` was edited). Reconstructed `damage_raw` per hit via `hit_resolved` + `armor_absorbed` pairing (Method), weapon-attributed via the preceding `weapon_fired` event, cross-checked against `int(weapon.damage × 0.7-or-0.6)` and against the pre-registered engine-layer prediction written into the contract file's own comments (§ change-under-test above):

| Weapon | Baseline raw (int(8×0.7)=5 / int(12×0.6)=7) | P4 raw observed | Ratio | Pre-registered prediction |
|---|---:|---:|---:|---|
| `machine_gun_dmg8` | 5 | **44** (47/68 red hits, 100% consistent, zero variance) | 8.80× | int(64×0.7)=44, 8.80× — **exact match** |
| `shrapnel_thrower_dmg8` | 7 | **57** (21/68 red hits, 100% consistent, zero variance) | 8.14× | int(96×0.6)=57, 8.14× — **exact match** |

Both weapons land at exactly one raw-damage value each across all 68 red-on-blue hits in the battery (zero variance) — the dose is deterministic and confirmed at the engine layer, matching the pre-registered prediction to the hit. Hit-count-weighted total raw damage ratio: `(47×44 + 21×57) / (47×5 + 21×7) = 3265 / 382 = 8.5471×` — bracketed between the two per-weapon ratios (8.14×–8.80×) and closely tracking the nominal ×8 dose once `int()` truncation on the baseline side (which inflates the ratio above nominal, the same artifact documented in every prior arm) is accounted for. All 126 `hit_resolved` events in the battery (68 red, 58 blue) paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches, zero unattributed weapon IDs on the red side.

### 3c. Damage-after-armor (context, not a dose-landed test — see Method)

| | P4 red→blue | Historical baseline (inherited, unverified — see caveat below) |
|---|---:|---:|
| Mean damage-after-armor per hit (n=68) | **40.57** | 5.98 |
| Median | 41 | — |
| Ratio to baseline | 6.78× | — |

Per-weapon breakdown: `machine_gun_dmg8` (raw=44) hits show `damage_after_armor` n=47, mean=36.00, median=40, range 28–43; `shrapnel_thrower_dmg8` (raw=57) hits show n=21, mean=50.81, median=54, range 41–56.

**A notable saturation effect distinguishes this arm from P1/P2:** reconstructing `armor_value_before_hit = armor_after + absorbed_amount` for all 68 red hits shows `armor_after == 0` on **every single hit, with zero exceptions**. This is because the mitigation cap at this dose (`ceil(44×0.75)=33` for machine gun, `ceil(57×0.75)=43` for shrapnel thrower) vastly exceeds blue's entire `armor_max` (16) — so absorption is bounded by whatever armor remains (never by the 75% cap) on every hit, and every red hit fully exhausts the pool regardless of its state going in. This is the same mechanism P2 exhibited on only a majority of hits (per the P2 doc's own published breakdown: 23/64 `machine_gun_dmg55` hits landed at full-pool absorption of 16, the other 18/64 at a depleted-pool absorption of ~1) — at ×8 the saturation is now total. Practically, this means damage-after-armor at this dose level has become a *less* dose-sensitive proxy than at lower doses: raising raw damage further would not increase damage-after-armor further in aggregate, since the constraint has shifted entirely onto "how much armor happens to be left," not "how much the weapon deals." As documented in Method and in every prior arm's doc, this sub-8× ratio (6.78×) is expected under this armor model and is not evidence the dose failed — §3a/§3b already prove it landed exactly as designed.

**The historical baseline figure (5.98) inherited into this table is itself flagged as unverified.** As noted in the task brief for this session, no primary source or independent re-derivation of this figure exists in any merged evidence doc in this repository; it is repeated here, as in the P1/P2/P3 docs, as **inherited-and-unverified context**, not an established fact.

**Conclusion: the dose landed exactly as designed and exactly as pre-registered.** The contract diff, the deterministic raw-damage reconstruction (zero variance, exact match to the pre-registered prediction), and the hit-weighted aggregate ratio (8.55×) all independently confirm ×8; the damage-after-armor figure's sub-8× ratio (6.78×) is explained by full armor-pool saturation on every hit, a mechanically verified and expected consequence of this arena's capped-fraction armor model at this dose level — not a vacuous or mis-applied-dose result.

## 4. Hits-to-kill

| | P4 | Historical baseline (inherited, unverified) | P1 (×3) | P2 (×5.5) |
|---|---:|---:|---:|---:|
| Blue kills red — mean hits (21 kills) | **2.38** (median 2, range 2–3, `{2:13, 3:8}`) | ~2.04 | 2.75 | 2.67 |
| Red kills blue — mean hits (8 kills) | **4.13** (median 4, range 4–5, `{4:7, 5:1}`) | ~26.74 | 12 (n=1) | 6.40 |

`mech_destroyed` event counts corroborate the win tally exactly: blue destroyed in 8 matches (= the 8 red wins, `subject.mech_id="mech.blue.01"`), red destroyed in 21 matches (= the 21 blue wins, `subject.mech_id="mech.red.01"`), 8+21=29 = all elimination terminals, zero unexplained destructions, zero mechs destroyed in the abort match. Red's kill speed against blue continues the trend from P1→P2→P4 (12 → 6.40 → 4.13 mean hits), each dose step further reducing the hits red needs to finish blue — consistent with the raw-damage-per-hit increases documented in §3b/§3c (higher raw damage and higher damage-after-armor both directly shorten the kill sequence). Blue's kill speed against red is essentially unchanged across every arm in this program (2.04 historical → 2.75 → 2.67 → 2.38, all within the same small-integer range) — expected, since none of these arms touch blue's weapons or red's HP/armor.

## 5. Utility keep-rate per seat

| Seat | Dealt (utility) | Programmed (utility) | Keep-rate | P1 (×3) | P2 (×5.5) |
|---|---:|---:|---:|---:|---:|
| red (brawler) | 310 | 9 | **0.0290** | 0.043 | 0.032 |
| blue (sniper) | 310 | 36 | **0.1161** | 0.079 | 0.111 |
| all-card sanity, both seats | 775/1550 (each seat) | 775/1550 (each seat) | 0.5000 (mechanical, confirms 5-of-10 register structure held) | 0.500 | 0.500 |

Both seats show low utility pickup (2.9–11.6%), consistent with the program's recurring finding that utility cards lose out to weapon/movement cards under this deal/program ratio — not a new effect of this arm, and in the same order of magnitude as every prior arm on this overlay shape.

## 6. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 335 |
| `llm_completion_resolved` | 311 |
| `llm_completion_failed` | 24 |
| `finish_reason` distribution | `stop`: 311/311 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 310/310 committed plans (zero fallback/heuristic plans) |
| Matches with ≥1 failed completion | 19/30 |
| Max single-match failures | 3 (seed 5028 — the abort) |
| Matches reaching an unrecovered abort | 1/30 (seed 5028) |
| `failed_completions` summed across `battery_raw.jsonl` | 24 (matches the event-table count exactly) |

335 requested − 311 resolved = 24, matching `llm_completion_failed` exactly. There is a 1-event gap between `llm_completion_resolved` (311) and `plan_committed` (310), fully explained by the abort match: in `match.01KYAT1XPK61H653M0YBKR2B88` (seed 5028), blue's tick-1 completion resolved successfully (`llm_completion_resolved`), but the match aborted (red's 3 consecutive failures) before a `plan_committed` event was ever emitted for either seat — confirmed by direct inspection of that match's full event sequence, which shows the resolved blue completion followed immediately by red's three failures and `match_ended`, with no `plan_committed` event anywhere in the match. All other 29 matches' completions were fully recovered by retry where needed (`finish_reason=stop`, `plan_source=llm` on all 310 final committed plans), consistent with `play_terminal_fraction=0.9667` and the single non-elimination terminal.

## 7. Merge / additivity verification

- PR #170 merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (`gh pr view 170`: state MERGED, mergedAt 2026-07-24T17:32:38Z, base `main`) — confirmed as an ancestor of this branch's HEAD via `git merge-base --is-ancestor 255f2306... HEAD` (exit 0).
- `git diff 255f2306~1 255f2306 -- contracts_data/weapons/machine_gun.yaml contracts_data/weapons/shrapnel_thrower.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/chassis/heavy_ironclad_mk1.yaml` returns **empty** — every baseline file this arm depends on is byte-identical pre/post-merge.
- The 4 files this arm adds (`machine_gun_dmg8.yaml`, `shrapnel_thrower_dmg8.yaml`, `llm_qwen35_berserker_dmg8.yaml`, `tactical_split_overdeal_utility_asym_pair_p4_dmg8_qwen.yaml`) are all new, additive files — no existing file is modified by this arm.

---

## 8. Dose-response placement

| Dose | Arm | Decided-basis win rate | All-30 basis | Classification |
|---|---|---:|---:|---|
| ×1 | v1 anchor / arm-1-alone | 0/30 = 0.0000 | 0/30 = 0.0000 | (null) |
| ×3 | P1 | 1/29 = 0.0345 | 1/30 = 0.0333 | FAILED |
| ×5.5 | P2 | 5/29 = 0.1724 | 5/30 = 0.1667 | DIRECTIONAL |
| ×8 | **P4 (this arm)** | **8/29 = 0.2759** | **8/30 = 0.2667** | **DIRECTIONAL** |

The point estimate continues to climb monotonically across all four points and remains inside the DIRECTIONAL band, short of the 0.35 COMPETITIVE threshold. **The per-unit-dose marginal increment does not continue to accelerate on this step — see §0 above for the full arithmetic (1.72 → 5.52 → 4.14 pp/unit across the three steps) and the correction this document makes to the prior "monotonic and accelerating" characterization.** Four points, n=30 per arm, is not enough to fit a dose-response curve of any functional form; no calibrated "predicted competitive multiplier" is offered here.

The Wilson CI widening (P2 upper bound 0.345, just under COMPETITIVE; P4 upper bound 0.4572, well into COMPETITIVE territory) is a sample-size artifact of a larger win count at the same n=29/30, not a claim that the true rate is COMPETITIVE — the point-estimate classification (DIRECTIONAL) is what this document calls, consistent with every prior arm's convention.

---

## Verdict

**DIRECTIONAL.** Decided-match red win rate is 0.2759 (8/29), all-30 basis 0.2667 (8/30) — inside the `0.10–0.35` DIRECTIONAL band, Wilson 95% CI [0.1470, 0.4572] (decided) / [0.1418, 0.4445] (all-30) — the decided-basis upper bound crosses above 0.35, a materially wider overlap into COMPETITIVE territory than any prior arm, though the point-estimate classification remains DIRECTIONAL per program convention. `play_terminal_fraction=0.9667` clears the trust gate on both the task-stated ≥0.9 threshold and the codebase's own ≥0.95 default. The intended ×8 raw-damage dose is verified to have landed exactly as designed and exactly as pre-registered at both the contract layer (direct diff, exact ×8 on the `damage` field) and the engine layer (deterministic per-hit raw-damage reconstruction, zero variance across 68 hits, 8.14×–8.80× bracketing 8× once `int()` truncation is accounted for, hit-weighted 8.55×) — this is not a vacuous or mis-applied-dose result. The damage-after-armor figure (40.57, 6.78× the inherited-and-unverified historical baseline) undershoots a naive ×8 expectation because blue's armor pool is now fully saturated on every single red hit (armor_after=0, zero exceptions) — a mechanically verified extension of the same effect P2 showed on a majority (not all) of its hits. Red's kill speed against blue continues to drop with each dose step (12 → 6.40 → 4.13 mean hits across P1/P2/P4); blue's kill speed against red is essentially unchanged throughout the program.

**The correction this document makes to the prior program record (§0):** the P2 doc and the session handoff (§7) characterized the first three dose-response points as "monotonic and accelerating." This document's fourth point falsifies the accelerating half: the marginal win-rate gain per dose-unit rose 1.72 → 5.52 pp/unit across the first two steps, then **fell** to 4.14 pp/unit on this step. Monotonic holds; accelerating does not — the shape is rise-then-inflect-then-slow (saturating), not accelerating. The full armor-saturation pool (`armor_after == 0` on all 68 hits, vs only a majority at P2's dose) is offered as the **leading hypothesis** for the mechanism, explicitly not proven at n=30/arm across three dose points. No calibrated extrapolation to a competitive-crossing dose is offered, and further raw-damage-only escalation (×11, ×16) is flagged as the lowest-information next experiment on this specific lever if the saturation hypothesis holds — without naming a predicted plateau value.

**Implication for the pair-sweep:** P4 is the strongest single arm in this program to date by point estimate, and the first to show Wilson-CI overlap with the COMPETITIVE band — but it is not itself a COMPETITIVE result, and the marginal-rate deceleration is a genuine finding that argues against assuming further dose increases will cross 0.35 at a similar or faster rate than the ×3→×5.5 step suggested. Four points (n=30 each) establish direction only; a fifth point, or a fundamentally different lever (as P3's armor-side null already demonstrated), would be needed to further resolve whether raw-damage dosing alone can cross into COMPETITIVE territory.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/pair_p4_dmg8/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `damage_applied`, `weapon_fired`, `mech_destroyed`, `hand_dealt`, `plan_committed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Contract diffs: `contracts_data/weapons/{machine_gun,shrapnel_thrower}.yaml` vs `*_dmg8.yaml`; `contracts_data/loadouts/llm_qwen35_berserker.yaml` vs `llm_qwen35_berserker_dmg8.yaml`; overlay diff vs `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p2_dmg55_qwen.yaml`.
- Armor mechanic: `src/steel_onslaught/reducers/damage.py` (`compute_armor_reduction`, degrading-pool capped-fraction model, `_MITIGATION_CAP[STANDARD]=0.75`).
- Merge commit: `255f23062d1ddb845faf3e2765bad6ba4e0521f0` (PR #170, `main`).
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p1_dmg3-battery.md` (PR #177), `docs/evidence/2026-07-24-pair_p2_dmg55-battery.md` (PR #179), `docs/evidence/2026-07-24-pair_p3_armor8-battery.md` (PR #181).
- Prior claim corrected by §0: `docs/handoffs/2026-07-24-brawler-competitiveness-session.md` §7 ("P1/P2 dose-response is monotonic and accelerating, not linear").
- No secrets, keys, or absolute paths included.
