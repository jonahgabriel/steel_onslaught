# SO-UTIL-THRESH Arm (vp-ladder payout-threshold confound, `vp_per_deploy` fixed at 6) Battery — 2026-07-26

**Verdict:** **H_INTERIOR is supported.** Pooled (red+blue) utility keep-rate at `vp_per_deploy: 6` with the bounty-driven early-termination confound relieved (`vp_threshold` raised 15 → 48) is **117/684 = 0.171053** (95% Wilson `[0.1447, 0.2011]`). The pre-registered bar — the vp4 rung's own published pooled keep-rate — required **≥ 0.211656**. Observed falls short by **0.040603**. Relieving the payout-threshold confound did **not** recover the vp6 dose ladder's dip: the discharged reading (0.171053) is statistically indistinguishable from the ORIGINAL vp6 baseline it was meant to interrogate (91/484 = 0.188017; z = −0.747, p = 0.4554) and from the vp2 rung (115/684 = 0.168129; z = 0.144, p = 0.8854), and it is *further* below the vp4 bar than the original vp6 baseline was (0.040603 short here vs 0.023639 short at baseline). The SO-UTIL-VP6 "response stops and turns over" finding (#209) survives its most direct mechanical challenge.

**What the manipulation did, verified at the engine layer.** Raising `vp_threshold` from 15 to 48 while holding `vp_per_deploy: 6` fixed fully discharged the mechanical truncation channel it targeted: **zero of 30 matches (0%) ended on `vp_threshold`**, versus 12/30 (40%) at the vp6 baseline and matching the vp2 rung's own near-zero rate (1/30) — the explicit design target. The maximum VP any seat scored in any of the 30 matches was 30, well under the new 48 threshold; every match that ended, ended on `elimination` (29/30) or `abort` (1/30). `play_terminal_fraction` rose to **0.9667** (O-GATE pass), versus the vp6 baseline's 0.7667 (O-GATE fail). The manipulation worked exactly as designed — and the pooled keep-rate still did not recover.

**One disclosed complication, reported rather than smoothed over.** The pre-registration's confound (1) predicted that relieving truncation could pull the pooled rate DOWN (via exposing lower-rate late rounds), based on the vp6 baseline's OWN within-match drift (there, rounds 1–3 read *higher* than rounds 4+). In THIS arm the within-match drift runs the opposite direction — rounds 1–3 read **lower** (54/356 = 0.151685) than rounds 4+ (63/328 = 0.192073; z = −1.401, p = 0.1611, not significant) — so the specific mechanism named in the pre-registration is not what is happening here. The small net drop from the vp6 baseline (0.188017 → 0.171053) is not explained by that channel and is not itself significant. What is robust regardless: **the reading stayed below the vp4 bar in both directions of round-index drift**, which is what the scored criterion asks.

**Ledger:** `.onex_state/steel_onslaught/util_incentive_vp6_vpthresh48` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-UTIL-THRESH worktree.

**Change under test:** exactly ONE experimental lever versus the SO-UTIL-VP6 (rung 3) overlay — `contracts.arena_id` `foundry_60_asym_v1` → `foundry_60_asym_v1_vpthresh48` (a sibling arena identical in every field except `vp_threshold` 15 → 48). `vp_per_deploy` stays 6, UNCHANGED. Below `schema_version`, the two overlay bodies differ in exactly **eight lines** (verified by direct diff): six isolated state-root paths, the `contracts.arena_id` value, and the one inline comment restating the new `vp_threshold` in prose. Arena geometry (spawns, obstacles, rects, sudden-death parameters, objective cells and their `vp_per_round`), loadouts, decks, weapons, personas, prompt code, handler pack, provider binding and `retry.max_attempts: 1` are byte-identical to every rung in this family. The mechanism (`src/steel_onslaught/contracts/incentive.py`, the `MatchStateFold` payout, `MATCH_STARTED` stamping) is unchanged since `c6d0d9c`.

**Engine-layer confirmation of the arm's configuration** (read from the ledger, not from the overlay file): all 30 `match_started` events carry `arena.arena_id = foundry_60_asym_v1_vpthresh48`, `arena.vp_threshold = 48`, and `utility_incentive = {"kind": "utility_deploy_vp_bounty", "schema_version": "0.1.0", "vp_per_deploy": 6}`. The `weapon_fired` breakdown carries only stock, un-suffixed weapon ids — `weapon.siege.artillery_mortar` 108, `weapon.light.machine_gun` 87, `weapon.heavy.harpoon_gun` 55, `weapon.light.shrapnel_thrower` 40 (290 total). Zero dose-ladder or range-cap variant ids appear.

**Arena / deal:** `foundry_60_asym_v1_vpthresh48` (new sibling of `foundry_60_asym_v1`; single field change `vp_threshold: 15 → 48`), over-deal 10 (4 movement + 4 weapon + 2 utility), program 5, utility handler pack `utility.resolution.v1` complete.
**Model:** live Qwen3.6-35B-A3B, both seats, keyless. n = 30, seeds 5001–5030, `--fresh`. `battery_raw.jsonl` holds exactly 30 rows; seeds 5001–5030 each present exactly once; zero duplicates, zero gaps; `events.sqlite3` shows exactly **30** `match_started` and **30** `match_ended`.

**Baselines (recomputed from their own ledgers by the §Method pairing, not copied from published docs):**
- **Scored bar — vp4 rung** (`util_incentive_vp4`, SO-UTIL-VP4 worktree): pooled 138/652 = 0.211656 — reproduces the published figure exactly.
- **The arm this design interrogates — vp6 baseline** (`util_incentive_vp6`, SO-UTIL-VP6 worktree): pooled 91/484 = 0.188017 — reproduces the published figure exactly.
- **Reported reference — vp2 rung** (`util_incentive_vp2`, SO-UTIL-REWARD worktree): pooled 115/684 = 0.168129 — reproduces the published figure exactly.
- **Single-lever comparator — surfacing-fix re-measure** (incentive OFF, post-#139 prompt code): pooled 80/724 = 0.110497 (published figure, not re-derived in this arm's recompute run).

---

## 0. Pre-registered hypothesis and criterion (committed and pushed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp6_vpthresh48_qwen.yaml`.

| Event | Commit | Author timestamp |
|---|---|---|
| Pre-registration — hypotheses + the ONE formal criterion + discard rule | **`cf44b91`** | **2026-07-25T18:47:33−07:00** (2026-07-26T01:47:33Z) |
| **First `match_started` of the scored run** | — | **2026-07-26T01:48:34.253864Z** |

The pre-registration precedes the first `match_started` of the scored run by **1 minute 1 second** — a thin but positive and mechanically verified margin (`scripts/check_preregistration_timing.py`, exit 0; see §7 Method gates). The branch was cut from `origin/main` at `d49831b2` and has not been rebased since, so the commit's author and committer timestamps agree (`2026-07-25T18:47:33−07:00` both) and no pre-rebase alias column is needed.

> **H_ARTIFACT** — the vp6 dip below vp4 was a payout-threshold-truncation artifact. Relieving the truncation (raising `vp_threshold` so `deploys-to-threshold` matches the vp2 rung's own tier, at the same `vp_per_deploy`) lets the pooled keep-rate recover to at least vp4's published level.
>
> **H_INTERIOR** — the vp6 dip is a true interior optimum in incentive strength. Relieving the truncation does not lift the pooled keep-rate back to vp4's level; the model's drafting response genuinely peaked at vp4 and declined by vp6, independent of match-length truncation.
>
> **FORMAL CRITERION — the ONLY criterion this arm is scored against.**
> Quantity: POOLED (red + blue) utility keep-rate, n = 30, seeds 5001-5030, U-GATE paired `hand_dealt`/`plan_committed` method (identical definition every rung in this program has used).
> ```
>   bar = vp4 rung's own pooled utility keep-rate = 138 / 652 = 0.211656
> ```
> DECISION: pooled utility keep-rate >= 0.211656 supports H_ARTIFACT. pooled utility keep-rate < 0.211656 supports H_INTERIOR.

**A point comparison, deliberately not a CI-scaled one.** Every prior rung in this ladder scored a *new dose* against a Wilson-CI-width-derived bar (`bar = A + steps * W`) because the ladder was asking whether the price response kept climbing. This arm asks a different, binary question at a fixed dose — does relieving one specific mechanical confound move the measured rate back to a previously observed level — and the operator's 2026-07-25 handoff directive named that level explicitly ("keep-rate recovering to at least vp4's level implies artifact; staying down implies true interior optimum"). Three alternative readings were named in the pre-registration and explicitly rejected as the criterion: a CI-scaled bar, a two-proportion significance test against vp4, and a comparison against this arm's own vp6-baseline reading. Those three are reported below as secondaries (§1c), never in place of the scored point comparison.

---

## Method

Keep-rate is defined exactly as every sibling arm in this program defines it. For each seat, every `hand_dealt` is paired with the `plan_committed` that follows it for the same `(match_id, seat)` in ledger order (`tick`, `sequence_in_tick`); keep-rate = (utility cards appearing in `plan_committed.registers[].card_id`) ÷ (utility cards appearing in `hand_dealt.card_ids`). Unpaired hands are excluded from **both** numerator and denominator. **Unpaired hands in this arm: 0** (342 paired rounds total across both seats).

Recompute tool: `scripts/analyze_util_thresh_keeprate.py` (new this arm, committed alongside this document), which reads only `battery_raw.jsonl` + `events.sqlite3` — never `battery_summary.json` or driver stdout.

**Method-fidelity check.** The recompute code reproduces the published figures of all three ladder baselines exactly before being pointed at this arm's ledger: vp2 115/684 = 0.168129 (Wilson `[0.1420, 0.1980]`), vp4 138/652 = 0.211656, vp6 91/484 = 0.188017 (Wilson `[0.1557, 0.2252]`) — all recomputed from their own ledgers in the SO-UTIL-REWARD/SO-UTIL-VP4/SO-UTIL-VP6 worktrees, not copied from any document. All-card control on this arm's own ledger returns **0.500000 exactly** (1,710/3,420), the same mechanical invariant every rung in this family has produced.

Statistics: two-proportion z-tests for arm-vs-baseline comparisons; one-proportion z against the fixed 0.50 floor; 95% Wilson intervals throughout.

---

## 1. PRIMARY — the scored criterion

| Quantity | Value |
|---|---|
| Pooled utility kept / dealt | **117 / 684** |
| **Pooled utility keep-rate (the SCORED quantity)** | **0.171053** |
| 95% Wilson CI | **[0.1447, 0.2011]** (width 0.0564) |
| Pre-registered bar (vp4 rung's own pooled rate) | 0.211656 |
| **Meets bar?** | **NO — short by 0.040603** |
| Cards needed to reach the bar (same 684 denominator) | 145 kept (observed 117) — **28 more** |
| All-card keep-rate (mechanical control) | **0.500000 exactly** (1,710 / 3,420) |
| Standing reference — one-proportion z vs the 0.50 floor | **−17.21** |
| Standing reference — distance below chance | **2.92×** |

**Scoring.** 0.171053 < 0.211656 → **H_INTERIOR**. That is the pre-registered rule applied mechanically.

### 1a. Per seat (secondary, pre-declared, not scored)

| Seat | Kept / dealt | Keep-rate | 95% Wilson |
|---|---:|---:|---|
| red (brawler) | 43 / 342 | **0.125731** | [0.0947, 0.1651] |
| blue (sniper) | 74 / 342 | **0.216374** | [0.1760, 0.2630] |

Both seats read *below* their vp6-baseline figures (red 0.161157 → 0.125731; blue 0.214876 → 0.216374 — blue essentially flat, red down). Red, the most utility-averse seat throughout this program, is the seat that moved.

### 1b. Comparisons against baselines and the vp6 dose-response context (secondary, pre-declared, not scored)

| Comparison | Baseline rate | This arm | z | p (two-sided) | Significant at α=0.05? |
|---|---:|---:|---:|---:|---|
| **Pooled vs vp6 baseline (the arm this design interrogates)** | 91/484 = 0.188017 | 0.171053 | **−0.747** | **0.4554** | No |
| **Pooled vs vp4 bar (unscored significance reading)** | 138/652 = 0.211656 | 0.171053 | **−1.888** | **0.0591** | No (borderline) |
| **Pooled vs vp2 rung** | 115/684 = 0.168129 | 0.171053 | **0.144** | **0.8854** | No |
| **Pooled vs surfacing-fix comparator (incentive OFF, published figure)** | 80/724 = 0.110497 | 0.171053 | **3.274** | **0.0011** | **Yes** |

**Every one of the three alternative readings named-and-rejected in §0 agrees with the scored verdict.** A CI-scaled bar (as the ladder itself used) would also fail here — this arm's 95% CI `[0.1447, 0.2011]` does not reach 0.211656. A significance test against vp4 is borderline (p = 0.0591, just short of α = 0.05) but does not support recovery. A comparison against this arm's own vp6-baseline reading shows no significant *movement at all* (p = 0.4554) — i.e. discharging the confound left the reading statistically where the original vp6 battery found it, indistinguishable from both vp6 and vp2. **The lever itself is not dead**: 1.55× the incentive-OFF comparator at high significance (p = 0.0011), the same qualitative finding every rung in this ladder has reported.

**Four-point-plus-one context** (vp0 → vp2 → vp4 → vp6-baseline → this discharged reading, all pooled keep-rate): 0.110497 → 0.168129 → 0.211656 → 0.188017 → **0.171053**. Discharging the payout-threshold confound at vp6 landed the reading *between* the vp2 and vp6-baseline points, not up near vp4 — consistent with the ladder's own shape (rise then turn over) rather than with a confound that was suppressing a true vp4-or-higher plateau.

---

## 2. Secondary — the manipulation's mechanical effect (pre-declared, verifies the design worked)

| Metric | This arm (threshold relieved) | vp6 baseline | vp4 rung | vp2 rung |
|---|---:|---:|---:|---:|
| `vp_threshold` (arena) | **48** | 15 | 15 | 15 |
| `vp_threshold` terminals | **0 / 30 (0%)** | 12/30 (40%) | 14/30 (47%) | 1/30 (3%) |
| Terminal-class mix | `elimination` 29, `abort` 1 | `vp_threshold` 12, `elimination` 11, `abort` 7 | `elimination` 16, `vp_threshold` 14 | `elimination` 28, `vp_threshold` 1, `abort` 1 |
| `play_terminal_fraction` | **0.9667 — O-GATE PASS** | 0.7667 — O-GATE FAIL | 1.0000 | 0.9667 |
| Max VP any seat, any match | **30** (well under the 48 threshold) | 30 (at the 15 threshold, repeatedly) | — | — |
| Median match length (ticks) | **25.0** | 18.0 | 25.0 | 28.5 |
| Winners | blue 29, draw 1, **red 0** | blue 20, red 3, draw 7 | blue 28, red 2 | blue 29, none 1 |

**The manipulation discharged the targeted mechanism cleanly.** Zero matches ended on the bounty (down from 40% at baseline), matching the vp2 rung's own near-zero rate — the explicit design target (`ceil(48/6) = 8 = ceil(15/2)`). Median match length recovered to 25.0 ticks, identical to the vp4 rung's own median and well above the truncated vp6 baseline's 18.0. `play_terminal_fraction` cleared the O-GATE (0.9667 vs a 0.95 threshold), where the vp6 baseline failed it (0.7667, driven by six client-timeout aborts absent here — this run had exactly one abort, a different failure class, see §4).

**Red's win rate collapsed to zero.** Red went 0/30 → 2/30 → 3/30 across the priced ladder (vp2 → vp4 → vp6-baseline), all three vp6-baseline wins bought with deploys rather than won in a firefight. With the bounty-purchase win path closed off (0/30 `vp_threshold` terminals here), red has no path to a decisive win against blue's unchanged standoff configuration (confound 3, §6) and reads 0/30. This is not read as a balance result — see §6 — but it is the clearest illustration that the manipulation removed the win path it targeted.

---

## 3. Secondary — the round-index check (confound 1, pre-declared)

The pre-registration flagged that if the vp6 baseline's own late-round-is-lower drift were real, relieving truncation should pull the pooled rate DOWN, not toward the vp4 bar — and disclosed that this would cut *against* H_ARTIFACT rather than for it. This is the check that tests it directly, on this arm's own ledger.

| Window | Kept / dealt | Rate |
|---|---:|---:|
| Round 1 | 16 / 120 | 0.1333 |
| Round 2 | 19 / 120 | 0.1583 |
| Round 3 | 19 / 116 | 0.1638 |
| Round 4 | 23 / 112 | 0.2054 |
| Round 5 | 16 / 92 | 0.1739 |
| Round 6 | 10 / 56 | 0.1786 |
| Round 7 | 6 / 40 | 0.1500 |
| Round 8 | 8 / 24 | 0.3333 |
| Round 9 | 0 / 4 | 0.0000 |
| **Rounds 1–2 only** (truncation-immune window, same definition every rung uses) | **35 / 240** | **0.145833** |
| **Rounds 1–3 vs rounds 4+** | 54/356 = 0.151685 vs 63/328 = 0.192073 | z = −1.401, p = 0.1611 |

**The direction is the OPPOSITE of the vp6 baseline's own check** (there: rounds 1–3 = 0.209877 > rounds 4+ = 0.143750, z = +1.752; here: rounds 1–3 = 0.151685 < rounds 4+ = 0.192073, z = −1.401). Neither is individually significant. This means the specific causal channel the pre-registration named — "truncation removed low-rate late rounds, so relieving it should pull the estimate down toward those late rounds" — is not the mechanism operating in this arm; if anything, exposing more late rounds here would pull the estimate *up*, since late rounds read higher. **The scored verdict does not depend on this being resolved**: the rounds-1–2 truncation-immune reading (0.145833) is, if anything, *further* below the vp4 bar than the full-battery reading, so no plausible reading of this table moves the arm above the bar. It is reported as an honest complication of the pre-registered causal story, not as a rescue or a threat to the verdict.

---

## 4. Secondary — utility deployment, VP composition, completion health

| Metric | This arm | vp6 baseline | vp4 rung | vp2 rung |
|---|---:|---:|---:|---:|
| `utility_deploy_intent` events | 101 | 84 | 119 | 102 |
| `utility_deployed` (resolved) events | **101** | 84 | 119 | 102 |
| by seat | blue 64, red 37 | blue 50, red 34 | blue 77, red 42 | blue 73, red 29 |
| by kind | smoke 66, chaff 26, flares 9 | smoke 53, chaff 25, flares 6 | smoke 72, chaff 35, flares 12 | smoke 61, chaff 25, flares 16 |
| Programmed-to-resolved conversion (deployed ÷ pooled utility "kept", §1) | **101 / 117 = 86.3%** | 84/91 = 92.3% | 119/138 = 86.2% | 102/115 = 88.7% |
| VP composition | bounty 606 (100%), objective 0 | bounty 504 (98.8%), objective 6 | — | — |
| `llm_completion_requested` / `resolved` / `failed` | 349 / 343 / 6 | 259 / 244 / 15 | — | — |
| `llm_completion_failed` breakdown | 5 `invalid_response`, 1 `timeout` | 9 `invalid_response`, 6 `timeout` | — | — |
| `plan_committed` | 342 | 242 | — | — |
| Aborted matches | **1 / 30** | 7 / 30 | 0 / 30 | 1 / 30 |

**`utility_deploy_intent` and `utility_deployed` are equal in every rung of this family, including this arm (101 = 101)** — an engine-internal invariant (once a register's resolution fires an intent, it always resolves) unrelated to the "programmed-to-resolved conversion" figure, which instead measures deployed events against the pooled utility cards the model *kept in its plan* (§1's "kept" numerator, 117 here) — the gap between the two (117 programmed vs 101 deployed, 16 cards) is plan-committed utility that never reached its register's resolution tick before the match ended. This arm's conversion (86.3%) sits almost exactly at the vp4 rung's own figure (86.2%), both below vp2 (88.7%) and vp6-baseline (92.3%) — consistent with this arm's longer, more contested matches (median 25 ticks, more rounds played) leaving more late-programmed utility unresolved at the terminal tick, not with a data error. **Zero objective VP was scored** (100% of VP is bounty VP) — no `objective_scored` events fired in any of the 30 matches, so the objective-VP-shortcut disclosure the vp6 pre-registration required is vacuously satisfied (no match could take a shortcut that never existed here).

One match (seed 5002) aborted after a genuine `llm_completion_failed` chain (not the client-timeout class that dominated the vp6 baseline's aborts) — see the raw row for `match.01KYE1TWP5QJ9VGADSGNTPN1HY`, terminal_class `abort`, `end_reason: aborted`.

---

## 5. Secondary — replay validity, contamination gate

`all_replay_valid: true` across all 30 matches (both players, every match). `scripts/check_contamination_gate.py --state-root .onex_state/steel_onslaught/util_incentive_vp6_vpthresh48 --n 30 --seed-base 5000` reports 30 distinct rows for seeds 5001–5030, zero duplicates, zero gaps, zero out-of-range seeds, zero orphaned `match_started` rows, and the ledger's `match_ended` set is bijective with `battery_raw.jsonl`'s `match_id` set. Exit 0.

---

## 6. Verdict

**H_INTERIOR is supported.** Discharging the payout-threshold confound — the one mechanical channel by which a higher bounty price could truncate the match and mechanically depress the measured keep-rate — did not recover the vp6 dose ladder's dip. The discharged reading (117/684 = 0.171053) is:

- **Short of the pre-registered vp4 bar** (0.211656) by 0.040603, a larger shortfall in absolute terms than the original vp6 baseline's own miss (0.023639).
- **Statistically indistinguishable from the vp6 baseline it re-examines** (z = −0.747, p = 0.4554) — discharging the confound moved the point estimate down slightly, not up toward vp4, and the move is not significant either way.
- **Statistically indistinguishable from the vp2 rung** (z = 0.144, p = 0.8854).
- **Still significantly above the incentive-OFF comparator** (z = 3.274, p = 0.0011, 1.55×) — the lever is real; it is the *dose response past vp4* that does not survive discharging this confound, exactly the finding #209 reported before this arm existed.

**The manipulation itself worked as designed** (§2): `vp_threshold` terminals dropped from 40% to 0%, matching the vp2 rung's own near-zero rate, median match length recovered to the vp4 rung's own median, and the O-GATE passed where the untreated vp6 baseline failed it. This was not a weak or partial manipulation that left the confound half-discharged — it fully removed the mechanical channel named in the mission, and the keep-rate still did not recover.

**What this arm adds to the SO-UTIL-VP6 finding.** #209 reported an inverted-U and flagged, but could not discharge, the payout-threshold-truncation explanation. This arm removes that explanation by direct experimental manipulation rather than post-hoc round-capping: the vp6 dip is not an artifact of the bounty ending matches early. Whatever is producing the plateau/turnover at `vp_per_deploy: 6`, it is not "the match didn't run long enough for the model to keep drafting utility" — matches here ran to a natural elimination-governed length (median 25.0 ticks, matching vp4) and the rate still sat below vp4's level.

**What this arm does NOT settle.** The reversed round-index drift (§3) is an honest complication: the specific causal story named in the pre-registered confound (1) — truncation artificially inflates the baseline reading by excluding lower-rate late rounds — is not what this arm's own within-match pattern shows (here late rounds read *higher*, not lower). The verdict does not depend on resolving this, because the rounds-1–2 truncation-immune reading is, if anything, further below the bar than the pooled figure. But a reader should not conclude this arm identifies *why* vp6 turns over — only that payout-threshold truncation specifically is not the explanation.

---

## 7. Method gates (mandatory, PR #207)

Both run against this arm's scored lane before this document was written.

```
$ uv run python scripts/check_preregistration_timing.py \
    --state-root .onex_state/steel_onslaught/util_incentive_vp6_vpthresh48 \
    --overlay contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp6_vpthresh48_qwen.yaml
Pre-registration commit:    cf44b91a57d42276c5d5de44e361f64e4c4c9314
  author timestamp:         2026-07-25T18:47:33-07:00   (load-bearing)
First match_started:        2026-07-26T01:48:34.253864+00:00
Gap (match_started - author date): 0:01:01.253864
OK: pre-registration commit's author timestamp precedes the first match_started.
Exit: 0

$ uv run python scripts/check_contamination_gate.py \
    --state-root .onex_state/steel_onslaught/util_incentive_vp6_vpthresh48 \
    --n 30 --seed-base 5000
battery_raw.jsonl rows:       30
Distinct seeds:               30
Duplicate seeds / Missing seeds / Out-of-range seeds / Duplicate match_id: 0 / 0 / 0 / 0
Ledger match_ended vs battery_raw match_id sets bijective: yes
OK: battery_raw.jsonl holds exactly the 30 expected COMPLETED rows.
Exit: 0
```

Both gates pass honestly against the scored lane; neither was re-run or reinterpreted.

---

## 8. Limitations

- **The pre-registration margin is thin (1 minute 1 second).** Every prior rung in this family disclosed a margin of many minutes; this arm's is the tightest on record. The gap is mechanically verified positive by `check_preregistration_timing.py` reading the commit's AUTHOR timestamp (unaffected by the absence of any rebase here — author and committer timestamps agree, branch cut from `origin/main` at `d49831b2` and never rebased) against the ledger's own `emitted_at`. It is disclosed rather than rounded away.
- **This arm changes TWO things relative to the vp6 baseline simultaneously from the pooled-keep-rate reader's perspective, even though only one is an experimental lever.** `vp_threshold` is the single experimental change (arena_id), but raising it necessarily also changes which matches survive to be sampled (fewer bounty-truncated matches, more elimination-governed matches) — this is not a confound in the sense of an uncontrolled second lever (it is the mechanism the manipulation is designed to test), but it does mean the two arms' underlying match populations differ in ways beyond keep-rate alone (§2), and any reader treating this as a clean two-armed RCT on a fixed population should read §2's terminal-class table first.
- **The blue standoff configuration this family inherits (the P1–P7 harpoon framing error, OMN-15119 class) applies to this arm unchanged.** Blue carries `weapon.siege.artillery_mortar` (range 50) and `weapon.heavy.harpoon_gun` (range 30) against red's range-12 machine gun and range-8 shrapnel thrower. Red's 0/30 win rate in this arm must be read against this uncontested standoff envelope, not as evidence about the utility-incentive lever.
- **The round-index drift direction reversed relative to the vp6 baseline (§3)**, and this arm does not explain why. It does not threaten the scored verdict (the truncation-immune rounds-1–2 window reads even further below the bar than the pooled figure), but it means the specific causal story in the pre-registration's confound (1) is not confirmed here — only that its concrete alternative (recovery to the vp4 bar) did not occur.
- **One model, one arena family, one arm.** `foundry_60_asym_v1_vpthresh48`, Qwen3.6-35B-A3B on both seats. This arm does not test whether a payout-threshold confound exists in any other overlay in this program; it tests it once, at the single price point (`vp_per_deploy: 6`) where the original ladder's inverted-U was sharpest.
- **`vp_threshold: 48` is itself an untested design point**, not derived from any independent principle beyond matching the vp2 rung's own deploys-to-threshold tier. A still-higher threshold could in principle expose a different regime; this arm does not claim to have found the threshold at which the confound is "maximally" relieved, only a threshold that fully removed the targeted mechanical channel (0/30 `vp_threshold` terminals, §2).
- **Objective scoring is silent in this arm** (0 awards across 30 matches, vs 2–8 in the priced siblings) — plausibly because longer, elimination-governed matches leave less opportunity for a slow-building objective-control strategy before one side is destroyed. Reported, not scored, and not modeled further here.
- **Win rate and VP composition are not balance results** (100% of scored VP is bounty VP; red 0/30). Same disclaimer every sibling rung in this family carries.

---

## Citations (all relative paths)

- Recomputed metrics, this arm: `.onex_state/steel_onslaught/util_incentive_vp6_vpthresh48/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `utility_deploy_intent`, `utility_deployed`, `objective_scored`, `victory_declared`, `weapon_fired`, `llm_completion_requested`/`resolved`/`failed`) and `battery_raw.jsonl` (30 rows, seeds 5001–5030); driver summary `battery_summary.json` (gitignored local-machine artifact, same as every sibling lane in this program).
- Recompute tool (new this arm): `scripts/analyze_util_thresh_keeprate.py`.
- Pre-registration: overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp6_vpthresh48_qwen.yaml`, commit `cf44b91a57d42276c5d5de44e361f64e4c4c9314` (authored 2026-07-25T18:47:33−07:00), pushed before the first `match_started` at 2026-07-26T01:48:34.253864Z (margin 1 min 1 s). Branch `jonah/so-util-thresh-payout-threshold` cut from `origin/main` at `d49831b2`; never rebased.
- New arena: `contracts_data/arenas/foundry_60_asym_v1_vpthresh48.yaml` (single field change vs `foundry_60_asym_v1.yaml`: `vp_threshold: 15 → 48`).
- Discharged arm: `docs/evidence/2026-07-25-util_incentive_vp6-battery.md`, ledger `.onex_state/steel_onslaught/util_incentive_vp6/events.sqlite3` (SO-UTIL-VP6 worktree), independently recomputed here.
- Scored bar (vp4 rung): `docs/evidence/2026-07-25-util_incentive_vp4-battery.md`, ledger `.onex_state/steel_onslaught/util_incentive_vp4/events.sqlite3` (SO-UTIL-VP4 worktree), independently recomputed here.
- Reported reference (vp2 rung): `docs/evidence/2026-07-25-util_incentive_vp2-battery.md`, ledger `.onex_state/steel_onslaught/util_incentive_vp2/events.sqlite3` (SO-UTIL-REWARD worktree), independently recomputed here.
- Single-lever comparator: `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md` (published figure only, not re-derived by this arm's recompute run).
- Mechanism under test (unchanged this arm): `src/steel_onslaught/contracts/incentive.py`, `src/steel_onslaught/match/fold.py` (`_on_utility_deployed` payout, `_on_match_started` stamping), `src/steel_onslaught/llm/programming.py`, merged `c6d0d9c`. Mechanism tests: `tests/match/test_utility_incentive.py`.
- Arena contract, `vp_threshold` field: `src/steel_onslaught/contracts/arena.py` (`ModelSOArenaSpec.vp_threshold`, `StrictInt | None`, `gt=0`, no upper bound).
- Method gates (PR #207): `scripts/check_preregistration_timing.py`, `scripts/check_contamination_gate.py`; both run against this arm's lane in §7, exit 0.
- Battery driver: `scripts/run_ogate_objectives_battery.py` (non-zero exit on any skipped seed as of #204; this run had zero skips).
- No secrets, keys, or absolute paths included.
