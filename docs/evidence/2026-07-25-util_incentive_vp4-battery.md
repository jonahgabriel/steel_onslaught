# SO-UTIL-VP4 Arm (utility VP bounty dose ladder, rung 2, `vp_per_deploy: 4`) Battery — 2026-07-25

**Verdict:** **H_SATURATE is supported; the pre-registered formal criterion is NOT met — but by 9 cards, and the bar sits inside this arm's own confidence interval.** Pooled (red+blue) utility keep-rate is **138/652 = 0.211656** (95% Wilson `[0.1820, 0.2447]`). The pre-registered bar required **≥ 0.2242**. Observed falls short by **0.012544** — nine more programmed utility cards out of the same 652 dealt would have met it. Scored against the one criterion the pre-registration named, the dose response is **sub-linear**: doubling the price from 2 to 4 delivered **0.777 W** of lift where a linear response required 1.000 W.

That is the scored answer, and the honest reading is narrower than the verdict label. The bar **0.2242 lies inside the arm's 95% Wilson interval** `[0.1820, 0.2447]`. Unlike the vp2 rung — which missed its bar by 6.5× its own CI width and could not be rescued by any sampling story — this rung's miss is **well within sampling noise at n=30**. The pre-registration anticipated exactly this and pre-committed to saying so: *"n=30 CANNOT DISTINGUISH THEM" IS AN ACCEPTABLE ANSWER.* The scored verdict is H_SATURATE because that is the rule the arm committed to; the evidential strength behind it is weak, and this document does not claim otherwise.

**What the rung does establish, at a strength the criterion does not bound:** the response **kept moving**. Keep-rate rose 0.168129 → 0.211656, **1.26× the vp2 rung** (z = 2.030, p = 0.042), and **1.92× the single-lever comparator** (z = 5.131, p = 2.9e-07). The second doubling delivered **75.5%** of the increment the first one did — decelerating, not flat, and not saturated. The lever is still working at vp4; it is simply not working *linearly*.

**Ledger:** `.onex_state/steel_onslaught/util_incentive_vp4` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`, `experiments/`) in the SO-UTIL-VP4 worktree.

**Change under test:** exactly ONE experimental lever versus the SO-UTIL-REWARD (vp2) overlay — `contracts.utility_incentive.vp_per_deploy` 2 → 4. Below `schema_version`, the two overlay bodies differ in exactly **eight lines**: six isolated state-root paths, the `vp_per_deploy` value, and the one inline comment restating that value in prose. Arena, loadouts, decks, weapons, personas, prompt code, handler pack, provider binding and `retry.max_attempts: 1` are byte-identical. The mechanism itself (`src/steel_onslaught/contracts/incentive.py`, the `MatchStateFold` payout, `MATCH_STARTED` stamping, the in-register prompt fields) is unchanged since `c6d0d9c`.

**Dose and range configuration (held at the UNSCALED baseline, stated explicitly):**
- **Red DOSE: unscaled.** `loadout.llm.qwen35_berserker` → `weapon.light.machine_gun` (damage 8, range 12) and `weapon.light.shrapnel_thrower` (damage 12, range 8). No P1–P7 dose-ladder variant referenced.
- **Blue RANGE: uncut.** `loadout.llm.qwen35_sniper_ironclad` → `weapon.siege.artillery_mortar` (range 50, damage 45) and `weapon.heavy.harpoon_gun` (range 30, damage 28). No `_r30`/`_r15` variant referenced.
- **Engine-layer confirmation:** the ledger's `weapon_fired` breakdown carries only stock, un-suffixed weapon ids — `weapon.siege.artillery_mortar` 96, `weapon.light.machine_gun` 71, `weapon.heavy.harpoon_gun` 41, `weapon.light.shrapnel_thrower` 32 (240 total). Zero ladder-variant ids appear.

**Arena / deal:** `foundry_60_asym_v1`, `vp_threshold: 15`, over-deal 10 (4 movement + 4 weapon + 2 utility), program 5, utility handler pack `utility.resolution.v1` complete.
**Model:** live Qwen3.6-35B-A3B, both seats, keyless. n = 30, seeds 5001–5030, `--fresh`. `battery_raw.jsonl` holds exactly 30 rows; seeds 5001–5030 each present exactly once; zero duplicates, zero gaps; `events.sqlite3` shows exactly **30** `match_started` and **30** `match_ended`.

**Baselines (recomputed from their own ledgers by the §Method pairing, not copied from published docs):**
- **Scored anchor — vp2 rung** (`util_incentive_vp2`): pooled 115/684 = 0.168129, Wilson `[0.141973, 0.197992]`; red 34/342 = 0.099415; blue 81/342 = 0.236842. Recompute reproduces the published `docs/evidence/2026-07-25-util_incentive_vp2-battery.md` figures digit for digit, including its all-card control at 0.500000 exact.
- **Single-lever comparator — surfacing-fix re-measure** (incentive OFF, post-#139 prompt code): pooled 80/724 = 0.110497; red 20/362 = 0.055249; blue 60/362 = 0.165746.
- **U-GATE original** (incentive OFF, pre-#139): pooled 30/812 = 0.036946.

---

## 0. Pre-registered hypothesis and criterion (committed and pushed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp4_qwen.yaml`.

| Event | Commit | Author timestamp (UTC) |
|---|---|---|
| Pre-registration — hypotheses + the ONE formal criterion + discard rule | **`716eac2`** | **2026-07-25T18:53:22Z** |
| **First `match_started` of the scored run** | — | **2026-07-25T18:53:49.605581Z** |

The pre-registration precedes the first `match_started` by **27.6 seconds**, and the push to `origin/jonah/so-util-vp4-dose-ladder` completed inside that window — commit, push, and battery launch were three consecutive operations with no other work between them. The margin is thin in wall-clock terms but the ordering is unambiguous and independently checkable from two sources that cannot be back-dated together: the commit's author timestamp on the remote, and the ledger's own `emitted_at`. **The branch was created from and rebased onto `origin/main` (`626e32f`) BEFORE the pre-registration commit was authored, and has not been rebased since** — so `716eac2` is the originally-pushed object, its SHA is not rewritten, and no pre-rebase alias column is needed. (Two arms earlier in this program had their pre-registration SHAs rewritten by post-battery rebases; ordering the rebase first is the fix.)

> **H_DOSE** — the response to price is (at least) linear over this range. Doubling the bounty from 2 to 4 lifts pooled utility keep-rate by at least as much as the vp0 → vp2 segment lifted it, measured on the CI-width scale.
>
> **H_SATURATE** — the response to price is SUB-LINEAR. The lift is real at vp2 and is already flattening by vp4.
>
> **FORMAL CRITERION — the ONLY criterion this arm is scored against.**
> Quantity: POOLED (red + blue) utility keep-rate, n = 30, seeds 5001-5030, U-GATE paired `hand_dealt`/`plan_committed` method.
> ```
>   A   = vp2 pooled utility keep-rate   = 115 / 684 = 0.168129
>   W   = vp2 pooled 95% Wilson CI width = 0.1980 - 0.1420 = 0.0560
>   steps above the vp2 rung = (4 - 2) / 2 = 1
>   bar = A + 1 * W = 0.168129 + 0.056000 = 0.224129
>       -> rounded UP to 4 dp = 0.2242
> ```
> DECISION: pooled utility keep-rate >= 0.2242 supports H_DOSE. pooled utility keep-rate < 0.2242 supports H_SATURATE.

**Bar checkability.** Both inputs were read off the published vp2 evidence document before this battery ran, so the bar was verifiable in advance. It is also stable under rounding: carrying A and W at full precision (0.16812865 + 0.05601897 = 0.22414762) rounds up to the same **0.2242**.

**The 0.5331 chance bar is a standing reference, not this arm's criterion** — pre-declared as such. It is reported in §1 (distance, one-proportion z) and nothing in this document scores against it.

---

## Method

Keep-rate is defined exactly as the U-GATE arm defined it. For each seat, every `hand_dealt` is paired with the `plan_committed` that follows it for the same `(match_id, seat)` in ledger order; keep-rate = (utility cards appearing in `plan_committed.registers[].card_id`) ÷ (utility cards appearing in `hand_dealt.card_ids`). Unpaired hands are excluded from **both** numerator and denominator. **Unpaired hands in this arm: 0** (163 paired rounds per seat, 326 total).

This is *programmed*, not *deployed*. Both are reported (§4).

Statistics: two-proportion z-tests for arm-vs-baseline comparisons; one-proportion z against the fixed 0.50 floor; 95% Wilson intervals throughout.

**Method-fidelity check.** The recompute code used here reproduces the vp2 arm's published figures exactly — pooled 115/684 = 0.168129, Wilson `[0.1420, 0.1980]`, red 34/342, blue 81/342, all-card 0.500000 exact — before being pointed at this arm's ledger. The measurement is the program's existing one, not a new one tuned for this rung.

---

## 1. PRIMARY — the scored criterion

| Quantity | Value |
|---|---|
| Pooled utility kept / dealt | **138 / 652** |
| **Pooled utility keep-rate (the SCORED quantity)** | **0.211656** |
| 95% Wilson CI | **[0.1820, 0.2447]** (width 0.0626) |
| Pre-registered bar | 0.2242 |
| **Meets bar?** | **NO — short by 0.012544** |
| Cards needed to reach the bar (same 652 denominator) | 147 programmed (observed 138) — **9 more** |
| **Is the bar inside the arm's own 95% CI?** | **YES** — 0.1820 ≤ 0.2242 ≤ 0.2447 |
| Realised lift on the CI-width scale | **0.777 W** (linear required 1.000 W) |
| All-card keep-rate (mechanical control) | **0.500000 exactly** (1,630 / 3,260) |
| Standing reference — one-proportion z vs the 0.50 floor | **−14.73** |
| Standing reference — distance below chance | **2.36×** (short of 0.5331 by 0.3214) |

**Scoring.** 0.211656 < 0.2242 → **H_SATURATE**. That is the pre-registered rule applied mechanically.

**Strength of that scoring, stated plainly.** The miss is 0.0125 — **0.20× the arm's own CI width**, and the bar lies inside the interval. The vp2 rung missed its bar by 6.5× its CI width; this one misses by a fifth of it. A repeat battery at n=30 could land either side of this bar. H_SATURATE is the scored verdict and the honest confidence in it is low. What the data *does* support at strength is that the response is **not linear and not zero** — see §1b.

### 1a. Per seat (secondary, pre-declared, not scored)

| Seat | Kept / dealt | Keep-rate | 95% Wilson | vs vp2 | z | p | Below chance by |
|---|---:|---:|---|---:|---:|---:|---:|
| red (brawler) | 49 / 326 | **0.150307** | [0.1156, 0.1932] | **1.51×** | 1.993 | **0.0462** | 3.33× |
| blue (sniper) | 89 / 326 | **0.273006** | [0.2275, 0.3238] | 1.15× | 1.073 | 0.2834 | 1.83× |

**The second doubling landed almost entirely on red.** Red — the seat that has been the most utility-averse in every arm of this family — moved 1.51× and is the only seat whose vp2→vp4 move reaches significance. Blue, already the higher seat at vp2, moved 1.15× and did not. Read against §1b this is the more informative secondary in the arm: the aggregate deceleration is substantially a *blue* deceleration, and red was still responding to price at this rung. Neither seat's interval comes within 0.17 of the 0.50 floor.

### 1b. Dose-response across the ladder (secondary, pre-declared, not scored)

| Rung | `vp_per_deploy` | Pooled keep-rate | Increment | Increment in W |
|---|---:|---:|---:|---:|
| comparator (incentive OFF) | 0 | 80/724 = 0.110497 | — | — |
| rung 1 | 2 | 115/684 = 0.168129 | +0.057632 | **1.029 W** |
| **rung 2 (this arm)** | **4** | **138/652 = 0.211656** | **+0.043527** | **0.777 W** |

The second doubling delivered **75.5%** of the first segment's increment. The curve is **rising and decelerating** — the shape H_SATURATE names, at a magnitude the criterion's threshold does not cleanly separate from linear at n=30. Cumulatively the two rungs have closed **26.0%** of the distance from the comparator baseline to chance (vp2 alone closed 14.8%).

### 1c. Comparisons against baselines (secondary, pre-declared, not scored)

| Comparison | Baseline rate | This arm | Multiple | z | p (two-sided) | Significant at α=0.05? |
|---|---:|---:|---:|---:|---:|---|
| **Pooled vs vp2 rung (the one-lever dose comparison)** | 115/684 = 0.168129 | 0.211656 | **1.26×** | **2.030** | **0.0424** | **Yes** |
| **Pooled vs surfacing-fix comparator (incentive OFF)** | 80/724 = 0.110497 | 0.211656 | **1.92×** | **5.131** | **2.9e-07** | **Yes** |
| red vs surfacing-fix | 20/362 = 0.055249 | 0.150307 | 2.72× | 4.145 | 3.4e-05 | Yes |
| blue vs surfacing-fix | 60/362 = 0.165746 | 0.273006 | 1.65× | 3.410 | 0.0006 | Yes |
| Pooled vs U-GATE original (pre-#139 prompt code — **not** a clean single-lever comparison) | 30/812 = 0.036946 | 0.211656 | 5.73× | 10.424 | <1e-24 | Yes |

The vp2→vp4 step is itself significant (p = 0.042) even though it did not clear the pre-registered slope. **"Criterion not met" and "no further effect" are different claims, and only the first is supported here** — exactly the confound (5) the pre-registration named.

### 1d. This arm against the program

| Measure | Previous program maximum (all 22 prior arms) | This arm | New maximum? |
|---|---|---:|---|
| Pooled utility keep-rate | 0.168129 (vp2 rung) | **0.211656** | **Yes** |
| red-seat keep-rate | 0.099415 (vp2 rung) | **0.150307** | **Yes** |
| blue-seat keep-rate | 0.236842 (vp2 rung) | **0.273006** | **Yes** |

Every prior arm, including the vp2 rung that set all three records two hours earlier, is strictly below this arm on all three measures.

---

## 2. Secondary — truncation-immunity checks (confound 2, pre-declared)

The bounty ends matches early, so the pre-registration required proof that truncation shortens *exposure* and not the *rate*.

**Round-capped keep-rate, rounds 1–2 only** — the pre-declared truncation-immune secondary. Every seat-match in this arm reaches round 2, so this window is unaffected by any early termination.

| Window | This arm | vp2 reference | Multiple | z | p |
|---|---:|---:|---:|---:|---:|
| Rounds 1–2 only | **54 / 240 = 0.225000** `[0.1767, 0.2819]` | 40 / 232 = 0.172414 | 1.30× | 1.430 | 0.153 |
| Full battery | 138 / 652 = 0.211656 | 115 / 684 = 0.168129 | 1.26× | 2.030 | 0.042 |

**Seat-matches failing to reach round 2: 0 of 60.** The truncation-immune window reproduces the full-battery multiple (1.30× vs 1.26×) — the effect is not an artefact of which rounds survived truncation. Note the round-capped window is the *higher* reading (0.2250 — above the bar), which is why it is reported and not scored: it was pre-declared as a robustness check, and promoting it now would be precisely the post-hoc rescue the pre-registration forbids.

**Stationarity in round index:**

| Window | Kept / dealt | Rate |
|---|---:|---:|
| Rounds 1–3 | 75 / 356 | 0.210674 |
| Rounds 4+ | 63 / 296 | 0.212838 |

Two-proportion z = **−0.067**, p = 0.946 — no drift whatsoever. (At vp2 the same check gave z = 0.855, p ≈ 0.39.) Stationarity is *stronger* at this rung than at the last, so the pre-registered worry — that a higher dose might change endgame drafting near the VP line in a way the vp2 ledger could not show — did not materialise.

**Per-round-index keep-rate:**

| Round | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| kept/dealt | 26/120 | 28/120 | 21/116 | 17/112 | 23/96 | 14/56 | 5/20 | 4/12 |
| rate | 0.2167 | 0.2333 | 0.1810 | 0.1518 | 0.2396 | 0.2500 | 0.2500 | 0.3333 |
| cumulative | 0.2167 | 0.2250 | 0.2107 | 0.1966 | 0.2039 | 0.2081 | 0.2094 | 0.2117 |

---

## 3. Secondary — terminal mix, win rate, VP composition (pre-declared, NOT scored)

| Metric | This arm (vp4) | vp2 rung | Surfacing-fix (OFF) |
|---|---|---|---|
| `match_started` / `match_ended` | 30 / 30 | 30 / 30 | 30 / 30 |
| Terminal-class mix | `elimination` 16, **`vp_threshold` 14**, `abort` 0 | `elimination` 28, `vp_threshold` 1, `abort` 1 | `elimination` 29, `abort` 1 |
| `play_terminal_fraction` | **1.0000** (task gate ≥0.9 PASS; codebase default ≥0.95 PASS) | 0.9667 | 0.9667 |
| Winner distribution | blue 28, **red 2** | blue 29, none 1 | blue 30 |
| **Red (brawler) all-match win rate** | **2/30 = 0.0667** | 0/30 | 0/30 |
| Replay validity | 1/1 both players, all 30 matches | 1/1 all 30 | — |
| Aborts | **0/30** | 1/30 | 1/30 |

**`vp_threshold` terminals rose 1 → 14 of 30 (47%).** Against the pre-registered projections (8/30 at the observed vp2 deploy rate, 12/30 at the bar-implied rate) the realised 14/30 is slightly above the upper projection, consistent with the realised deploy uplift.

**Red won 2 matches — the first red wins ever recorded in this arm family** (vp2 0/30, surfacing-fix 0/30, U-GATE 0/30). Both (seeds 5006, 5021) were `vp_threshold` victories on 4 resolved deploys, i.e. red won *by buying the bounty*, not by winning a firefight. **This is not a balance result** (§confound 4) — it is the bounty becoming a cheaper win condition than beating the standoff.

**Confound (1) disclosure — the per-match `vp_threshold` path.** The pre-registration required disclosing every match that reached the line via the 3-deploy + ≥3-objective-VP shortcut rather than the structural 4-deploy path. **Zero matches took the shortcut.** All 14 `vp_threshold` terminals were won on exactly **4 resolved deploys (16 VP)**; the single match with any objective VP on the winning side (seed 5022, blue, 4 deploys + 1 objective VP = 17) still needed all four deploys. Objective awards remained rare (8 across 30 matches; red 3, blue 5).

### VP composition (the win-rate confound, quantified)

| Source | VP | Share of all VP |
|---|---:|---:|
| Utility-deploy bounty (119 deploys × 4) | **476** | **98.3%** |
| Objective control (8 awards × 1) | 8 | 1.7% |
| **Total across all 30 matches** | **484** | 100% |

Bounty VP by seat: blue 308, red 168. Objective VP by seat: blue 5, red 3. **98.3% of every victory point scored in this arm is bounty VP** (vp2: 97.6%) — as pre-declared, the share rose. Any win-rate or VP reading from this arm measures the bounty, not the seats.

---

## 4. Secondary — utility deployment (resolution layer)

| Metric | This arm (vp4) | vp2 rung | Surfacing-fix (OFF) |
|---|---:|---:|---:|
| `utility_deploy_intent` | 119 | 102 | — |
| `utility_deployed` (resolved) | **119** | 102 | 72 |
| by seat | blue 77, red 42 | blue 73, red 29 | blue 54, red 18 |
| by kind | smoke 72 (blue 47 / red 25), chaff 35 (blue 21 / red 14), flares 12 (blue 9 / red 3) | smoke 61, chaff 25, flares 16 | smoke 46, chaff 20, flares 6 |
| Matches with ≥1 deploy | 29/30 | 28/30 | — |
| Deploys per match (matches with ≥1) | 1–7, median 4 | 1–10, median 3 | — |
| **Programmed-to-resolved conversion** | **119 / 138 = 86.2%** | 102 / 115 = 88.7% | — |

Every deploy intent resolved (119/119), so the 19-card shortfall is upstream of the resolver — programmed utility that never reached resolution because the match ended, the mech died, or heat locked. Note the **median deploys per match rose 3 → 4 while the maximum fell 10 → 7**: at vp4 the fourth deploy ends the match, so the long tail is truncated by construction. Red's deploys rose 29 → 42 (1.45×), tracking red's keep-rate move in §1a.

---

## 5. Secondary — match length and completion health

| Metric | This arm (vp4) | vp2 rung | Surfacing-fix (OFF) |
|---|---:|---:|---:|
| min ticks | 8 | 1 (the abort) | 13 |
| median ticks | **25.0** | 28.5 | 29.0 |
| mean ticks | **26.13** | 27.2 | 28.67 |
| max ticks | **40** | 59 | 73 |

Sorted durations (n=30): 8, 14, 18, 19, 19, 21, 22, 23, 23, 23, 23, 23, 24, 24, 24, 26, 27, 27, 28, 28, 30, 31, 31, 31, 31, 34, 36, 38, 38, 40.

**Matches got shorter and the tail compressed** (max 59 → 40). This is the expected mechanical consequence of a 4-deploy win condition, not a strategic finding.

| Completion metric | Value |
|---|---|
| `llm_completion_requested` | 334 |
| `llm_completion_resolved` | 326 |
| `llm_completion_failed` | 8 (`reason_code: invalid_response`, `semantic_failure_code: invalid_action_parameters`) |
| `finish_reason` distribution | `stop`: 326/326 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 326/326 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **0/30** |

334 requested − 326 resolved = 8, matching `llm_completion_failed` exactly, with zero gap between resolved and `plan_committed`. Failure rate is *lower* than both baselines (vp2: 14; surfacing-fix: 18) and this is the first battery in the family with **zero aborts**.

---

## 6. Verdict

**H_SATURATE is supported by the pre-registered rule; the evidence behind that verdict is weak, and this document does not launder it into a strong one.** Pooled utility keep-rate at `vp_per_deploy: 4` is 0.211656 against a bar of 0.2242 — short by 0.012544, which is nine programmed cards out of 652, and **the bar sits inside the arm's own 95% Wilson interval**. The pre-registration named this outcome in advance: *"n=30 CANNOT DISTINGUISH THEM" IS AN ACCEPTABLE ANSWER.* This is that case. The criterion was applied mechanically and it returned H_SATURATE; a replicate at n=30 could plausibly return H_DOSE.

**What the battery does establish at strength:**

- **The lever kept working.** 1.26× the vp2 rung (z = 2.030, p = 0.042) and 1.92× the incentive-OFF comparator (z = 5.131, p = 2.9e-07). "Criterion not met" is not "no further effect."
- **The curve is rising and decelerating.** The second doubling delivered 0.777 W where linear required 1.000 W — 75.5% of the first segment's increment. Two rungs have closed 26.0% of the distance from baseline to chance.
- **The deceleration is mostly blue's.** Red moved 1.51× (p = 0.046) and blue 1.15× (p = 0.283). The seat with the strongest utility aversion was still buying at this price; the seat already near the top of the family's range was not.
- **New program maxima on all three keep-rate measures**, beating the vp2 rung that set them.
- **Structural side-effects are large and were correctly projected.** `vp_threshold` terminals 1 → 14 of 30; red's first-ever wins in this family (2/30), both bought with four deploys rather than won in a firefight; bounty VP share 97.6% → 98.3%.

**The design implication, stated precisely.** The vp2 rung showed the drafting bias is *price-sensitive but heavily discounted*. This rung sharpens that: the discount is **not** a one-time step that saturates immediately — the model keeps re-pricing as the price rises — but it deepens with dose, and it deepens fastest in the seat that had already responded most. Extrapolating the realised vp2→vp4 slope, chance would not be reached until `vp_per_deploy` ≈ 17, well past the point where a single deploy wins the match outright. **No price on this ladder can reach the chance floor without destroying the arena it is measured in.** That is a stronger and more useful statement than either hypothesis label.

**What this arm does NOT settle.** Whether the true response over 2→4 is linear or sub-linear: this battery cannot separate them at n=30, and the bar falling inside the CI is the direct evidence of that. The pre-registered rung 3 (`vp_per_deploy: 6`, deploys-to-threshold 3, projected 12/30 terminals at N ≈ 532 and CI width 1.14× W) is the discriminating measurement — a third point makes the curve's shape identifiable in a way two points plus a threshold cannot. Nothing here is a balance result (§3).

---

## 7. Limitations

- **The scored verdict is a near-miss and must not be cited as a clean negative.** The bar (0.2242) lies inside this arm's 95% Wilson interval `[0.1820, 0.2447]`; the miss is 0.20× the arm's own CI width. Any downstream summary that reports "H_SATURATE" without reporting that the bar is inside the interval is misrepresenting this battery. Contrast the vp2 rung, whose miss was 6.5× its CI width and genuinely decisive.
- **The round-capped secondary (0.2250) is above the bar and is NOT a rescue.** It was pre-declared as a truncation-robustness check, reported and never scored. It is quoted in §2 as designed; promoting it to the criterion after the fact is exactly what the pre-registration's secondary-observable declaration exists to prevent.
- **The blue standoff configuration this family inherits (the P1–P7 harpoon framing error, OMN-15119 class) applies to this arm unchanged.** Blue carries `weapon.siege.artillery_mortar` at range 50 and `weapon.heavy.harpoon_gun` at range 30 against red's range-12 machine gun and range-8 shrapnel thrower. Blue holds an uncontested standoff envelope; every win-rate and terminal figure in §3 must be read against it. The configuration is held at baseline deliberately — it is what makes the keep-rate comparison single-lever — and is not corrected here.
- **The bounty counts toward `vp_threshold`, and at this rung that confound is materially larger than at the last.** Deploys-to-threshold = ceil(15/4) = 4, so 14 of 30 matches (47%) ended on the bounty rather than on play, versus 1 of 30 at vp2. Red's 2 wins are bounty purchases, not combat outcomes. 98.3% of all VP was bounty VP. **Win rate in this arm is not a balance result and must not be cited as one.**
- **The pre-declared small-N risk did not materialise, but the denominator did shrink.** N = 652 versus vp2's 684. The pre-registration flagged that a projected N of 532–616 would fall below 620 — the smallest pooled utility-dealt count in any prior clean n=30 arm — and required disclosure if so; the realised 652 exceeds 620, so that specific risk is retired. Realised Wilson width 0.0626 = **1.12× W**, inside the projected 1.05–1.14× band. The bar is a fixed rate, so N could never have moved it, only widened this arm's CI — which is precisely the mechanism by which the bar ended up inside the interval.
- **Truncation was verified not to bias the rate, at this rung.** Stationarity is stronger here than at vp2 (z = −0.067, p = 0.946 vs z = 0.855, p ≈ 0.39), all 60 seat-matches reached round 2, and the truncation-immune window reproduces the full-battery multiple. This verification does not automatically extend to rung 3, where deploys-to-threshold falls to 3 and truncation bites harder; it must be re-run there.
- **Comparator choice is load-bearing.** The scored anchor is the vp2 rung (0.168129), a contemporaneous battery on the same tree — this is the cleanest adjacent comparison the program has produced. The surfacing-fix comparator (0.110497) is 2 days old and predates engine changes since 2026-07-23; the U-GATE original (0.036946) additionally predates the #139 prompt-surfacing fix and is reported for lineage only. The 1.26× (vs vp2) and 1.92× (vs surfacing-fix) figures are the defensible ones; 5.73× is not this arm's effect.
- **Keep-rate measures programming, not resolution.** 86.2% of programmed utility cards resolved into a deploy (§4). A reader comparing this document's keep-rate to a sibling arm's `utility_deployed`-based proxy is comparing two different quantities.
- **The per-rung dose comparison is a between-battery comparison, not a within-match one.** vp2 and vp4 are separate n=30 batteries on the same seeds and the same tree, run ~2 hours apart. Seeds are shared, which controls arena/deal variation, but LLM sampling is not held fixed across them.
- **One price step, one model, one arena.** `vp_per_deploy: 4`, Qwen3.6-35B-A3B on both seats, `foundry_60_asym_v1`. The sub-chance keep-rate replicated across qwen35, deepseek, gemma and glm, but only qwen35 has been priced at any rung.
- **The extrapolated "chance needs vp ≈ 17" figure is an extrapolation, not a measurement.** It projects the realised vp2→vp4 slope linearly past a region where the same battery just showed the slope is decelerating, so it is a *lower* bound on the required price at best, and it is stated only to make the point that the ladder's usable range is bounded by arena degeneracy.
- **No re-run to chase a different number.** n=30, seeds 5001–5030, was pre-declared. The first run completed 30/30 (`skipped_seeds: []`, driver exit 0) and is the scored run under the pre-registered discard rule, evaluated before any keep-rate was computed. **Zero runs were discarded for this arm.**

---

## Citations (all relative paths)

- Recomputed metrics, this arm: `.onex_state/steel_onslaught/util_incentive_vp4/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `utility_deploy_intent`, `utility_deployed`, `objective_scored`, `victory_declared`, `weapon_fired`, `llm_completion_requested`/`resolved`/`failed`) and `battery_raw.jsonl` (30 rows, seeds 5001–5030); driver output `battery_summary.json`.
- Pre-registration: overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp4_qwen.yaml`, commit `716eac2` (authored 2026-07-25T18:53:22Z), pushed before the first `match_started` at 2026-07-25T18:53:49.605581Z (margin 27.6 s). Branch cut and rebased onto `main` before the pre-registration was authored; SHA not rewritten.
- Scored anchor (rung 1): `docs/evidence/2026-07-25-util_incentive_vp2-battery.md`, ledger `.onex_state/steel_onslaught/util_incentive_vp2/events.sqlite3` (SO-UTIL-REWARD worktree), independently recomputed here.
- Single-lever comparator: `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`, ledger `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree).
- Lineage baseline: `docs/evidence/2026-07-23-ugate-asym-utility-battery.md`, ledger `.onex_state/steel_onslaught/ugate_asym_utility_battery/events.sqlite3` (SO-UGATE-ASYM worktree).
- Mechanism under test (unchanged this arm): `src/steel_onslaught/contracts/incentive.py`, `src/steel_onslaught/match/fold.py` (`_on_utility_deployed` payout, `_on_match_started` stamping), `src/steel_onslaught/llm/programming.py` (`legal_hand[].deploy_vp_bounty`, `incentives` block), merged `c6d0d9c`. Mechanism tests: `tests/match/test_utility_incentive.py`.
- Battery driver: `scripts/run_ogate_objectives_battery.py` (non-zero exit on any skipped seed as of #204, which is what makes the discard rule exit-code checkable).
- Prompt-steering negative this ladder is contrasted against: `docs/evidence/2026-07-24-prompt_guidance_v2-battery.md`, `docs/evidence/2026-07-24-prompt_surfacing_v2-battery.md`.
- No secrets, keys, or absolute paths included.
