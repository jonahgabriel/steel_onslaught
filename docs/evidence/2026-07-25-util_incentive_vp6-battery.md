# SO-UTIL-VP6 Arm (utility VP bounty dose ladder, rung 3, `vp_per_deploy: 6`) Battery — 2026-07-25

**Verdict:** **H_SATURATE is supported, decisively this time.** Pooled (red+blue) utility keep-rate is **91/484 = 0.188017** (95% Wilson `[0.1557, 0.2252]`). The pre-registered bar required **≥ 0.2802**. Observed falls short by **0.092183 — 1.33× this arm's own CI width**, and the bar sits **far outside** the interval. Rung 2 missed its bar by 0.20× its CI width with the bar *inside* the interval and said plainly that it could not separate linear from sub-linear at n=30. This rung can: the cumulative vp2 → vp6 span delivered **0.355 W** of the 2.000 W a linear response required.

**And the third point does what two points plus a threshold could not — it identifies the shape.** The curve did not merely decelerate; it **stopped and turned over**. Keep-rate went 0.110497 (vp0) → 0.168129 (vp2) → 0.211656 (vp4) → **0.188017 (vp6)**. The vp4 → vp6 step is **−0.023640 (−0.422 W)**. This rung is statistically **indistinguishable from vp4** (0.89×, z = −0.982, p = 0.326) *and* from vp2 (1.12×, z = 0.878, p = 0.380) — it sits between them and cannot be told apart from either. Of the three pre-declared ladder shapes this is **(c) no further response**: pricing past vp4 bought nothing. The lever is still real against the incentive-OFF comparator (1.70×, z = 3.787, p = 1.5e-04); it simply stopped responding to further price.

**One artefact must be read before any number above, and it is disclosed here rather than in a footnote.** Six of the thirty matches ended in an `abort` caused by a **45-second client-side LLM timeout** — a failure class that appears **zero times** in both prior rungs. `play_terminal_fraction` is **0.7667**, which **fails the O-GATE** (threshold 0.95; `o_gate_pass: false` in the driver summary). The pre-registered discard rule is exhaustive and permits exactly one discard reason — a skipped seed — and this run has **none** (`skipped_seeds: []`, 30/30 rows, driver exit 0). So this is the scored run and it is not re-run or re-scored. What the artefact does to the verdict is measurable and is reported in §2b: removing all seven aborted matches *raises* keep-rate to **81/400 = 0.202500**, which still misses the bar by 0.0777 (> 1× CI width) and is still indistinguishable from vp4 (z = −0.355, p = 0.723). **The artefact worked against this arm and the verdict survives removing it.** That is the reason it is reported as a limitation rather than treated as grounds to discard.

**Ledger:** `.onex_state/steel_onslaught/util_incentive_vp6` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `battery_run.log`, `evaluations/`, `experiments/`) in the SO-UTIL-VP6 worktree.

**Change under test:** exactly ONE experimental lever versus the SO-UTIL-REWARD (vp2) overlay — `contracts.utility_incentive.vp_per_deploy` 2 → 6. Below `schema_version`, the two overlay bodies differ in exactly **eight lines**: six isolated state-root paths, the `vp_per_deploy` value, and the one inline comment restating that value in prose (verified by direct diff of the two file bodies). Arena, loadouts, decks, weapons, personas, prompt code, handler pack, provider binding and `retry.max_attempts: 1` are byte-identical. The mechanism (`src/steel_onslaught/contracts/incentive.py`, the `MatchStateFold` payout, `MATCH_STARTED` stamping, the in-register prompt fields) is unchanged since `c6d0d9c`.

**Engine-layer confirmation of the arm's configuration** (read from the ledger, not from the overlay file): all 30 `match_started` events carry `utility_incentive = {"kind": "utility_deploy_vp_bounty", "schema_version": "0.1.0", "vp_per_deploy": 6}`, `arena_id = foundry_60_asym_v1`, `vp_threshold = 15`. The `weapon_fired` breakdown carries only stock, un-suffixed weapon ids — `weapon.siege.artillery_mortar` 64, `weapon.light.machine_gun` 32, `weapon.heavy.harpoon_gun` 30, `weapon.light.shrapnel_thrower` 16 (142 total). Zero dose-ladder or range-cap variant ids appear.

**Arena / deal:** `foundry_60_asym_v1`, `vp_threshold: 15`, over-deal 10 (4 movement + 4 weapon + 2 utility), program 5, utility handler pack `utility.resolution.v1` complete.
**Model:** live Qwen3.6-35B-A3B, both seats, keyless. n = 30, seeds 5001–5030, `--fresh`. `battery_raw.jsonl` holds exactly 30 rows; seeds 5001–5030 each present exactly once; zero duplicates, zero gaps; `events.sqlite3` shows exactly **30** `match_started` and **30** `match_ended`.

**Baselines (recomputed from their own ledgers by the §Method pairing, not copied from published docs):**
- **Scored anchor — vp2 rung** (`util_incentive_vp2`): pooled 115/684 = 0.168129, Wilson `[0.141973, 0.197992]`; red 34/342 = 0.099415; blue 81/342 = 0.236842.
- **Preceding rung — vp4** (`util_incentive_vp4`): pooled 138/652 = 0.211656, Wilson `[0.182037, 0.244653]`; red 49/326 = 0.150307; blue 89/326 = 0.273006; rounds 1–2 54/240.
- **Single-lever comparator — surfacing-fix re-measure** (incentive OFF, post-#139 prompt code): pooled 80/724 = 0.110497; red 20/362 = 0.055249; blue 60/362 = 0.165746.
- **U-GATE original** (incentive OFF, pre-#139): pooled 30/812 = 0.036946.

---

## 0. Pre-registered hypothesis and criterion (committed and pushed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp6_qwen.yaml`.

| Event | Commit | Author timestamp (UTC) |
|---|---|---|
| Pre-registration — hypotheses + the ONE formal criterion + discard rule | **`8816f24`** | **2026-07-25T19:26:27Z** |
| **First `match_started` of the scored run** | — | **2026-07-25T20:14:46.427769Z** |

The pre-registration precedes the first `match_started` of the scored run by **48 minutes 19 seconds**, and was pushed to `origin/jonah/so-util-vp6-dose-ladder` before any match in this arm was started. **The branch was cut from `main` at `8094e8f` (the vp4 merge) and has NOT been rebased since**, so `8816f24` is the originally-pushed object, its SHA is not rewritten, and no pre-rebase alias column is needed. The ordering is checkable from two sources that cannot be back-dated together: the commit's author timestamp on the remote, and the ledger's own `emitted_at`.

> **H_DOSE** — the response to price is (at least) linear across the full vp2 → vp6 span. The cumulative lift from the vp2 rung reaches at least 2.000 W on the CI-width scale.
>
> **H_SATURATE** — the response to price is SUB-LINEAR across that span. The lift is real and continues, but flattens with dose.
>
> **FORMAL CRITERION — the ONLY criterion this arm is scored against.**
> Quantity: POOLED (red + blue) utility keep-rate, n = 30, seeds 5001-5030, U-GATE paired `hand_dealt`/`plan_committed` method.
> ```
>   A   = vp2 pooled utility keep-rate   = 115 / 684 = 0.168129
>   W   = vp2 pooled 95% Wilson CI width = 0.1980 - 0.1420 = 0.0560
>   steps above the vp2 rung = (6 - 2) / 2 = 2
>   bar = A + 2 * W = 0.168129 + 0.112000 = 0.280129
>       -> rounded UP to 4 dp = 0.2802
> ```
> DECISION: pooled utility keep-rate >= 0.2802 supports H_DOSE. pooled utility keep-rate < 0.2802 supports H_SATURATE.

**The criterion is cumulative, and the pre-registration said so before the run.** The bar formula was fixed at rung 2, so this rung's bar asks the vp2 → vp6 span to deliver 2.000 W in total. Rung 2 delivered 0.777 W of that span, which meant clearing this bar required the vp4 → vp6 step alone to deliver **1.223 W** — more than any prior step. The pre-registration stated in advance that this was unlikely, predicted 0.255183 from the realised vp2 → vp4 slope (itself above the outcome), declined to move the bar, and added the unscored incremental reading in §1b so that "the cumulative criterion was missed" and "the response stopped" stay separable. Both readings are now in: the criterion was missed, **and** the response stopped. They agree, which is why this rung is decisive where rung 2 was not.

**Bar checkability.** Both inputs were read off the published vp2 evidence document before this battery ran. The bar is stable under rounding: at full precision 0.16812865 + 0.11203811 = 0.28016676, which rounds up to the same **0.2802**.

**The 0.5331 chance bar is a standing reference, not this arm's criterion** — pre-declared as such. It is reported in §1 (distance, one-proportion z) and nothing in this document scores against it.

---

## Method

Keep-rate is defined exactly as the U-GATE arm defined it. For each seat, every `hand_dealt` is paired with the `plan_committed` that follows it for the same `(match_id, seat)` in ledger order; keep-rate = (utility cards appearing in `plan_committed.registers[].card_id`) ÷ (utility cards appearing in `hand_dealt.card_ids`). Unpaired hands are excluded from **both** numerator and denominator. **Unpaired hands in this arm: 0** (121 paired rounds per seat, 242 total).

This is *programmed*, not *deployed*. Both are reported (§4).

Statistics: two-proportion z-tests for arm-vs-baseline comparisons; one-proportion z against the fixed 0.50 floor; 95% Wilson intervals throughout.

**Method-fidelity check.** The recompute code used here reproduces the published figures of all three baselines exactly — vp2 115/684 = 0.168129 with Wilson `[0.141973, 0.197992]`, vp4 138/652 = 0.211656 with Wilson `[0.182037, 0.244653]` and rounds 1–2 = 54/240, surfacing-fix 80/724 = 0.110497 — and returns an all-card control of 0.500000 exact on each, before being pointed at this arm's ledger. The measurement is the program's existing one, not a new one tuned for this rung.

---

## 1. PRIMARY — the scored criterion

| Quantity | Value |
|---|---|
| Pooled utility kept / dealt | **91 / 484** |
| **Pooled utility keep-rate (the SCORED quantity)** | **0.188017** |
| 95% Wilson CI | **[0.1557, 0.2252]** (width 0.0695 = 1.24 W) |
| Pre-registered bar | 0.2802 |
| **Meets bar?** | **NO — short by 0.092183** |
| Cards needed to reach the bar (same 484 denominator) | 136 programmed (observed 91) — **45 more** |
| **Is the bar inside the arm's own 95% CI?** | **NO** — 0.2802 > 0.2252 (miss = 1.33× the CI width) |
| Realised cumulative lift on the CI-width scale (vp2 → vp6) | **0.355 W** (linear required 2.000 W) |
| All-card keep-rate (mechanical control) | **0.500000 exactly** (1,210 / 2,420) |
| Standing reference — one-proportion z vs the 0.50 floor | **−13.73** |
| Standing reference — distance below chance | **2.66×** (short of 0.5331 by 0.3451) |

**Scoring.** 0.188017 < 0.2802 → **H_SATURATE**. That is the pre-registered rule applied mechanically.

**Strength of that scoring.** Unlike rung 2, the miss here is not a sampling story. The bar is **0.0550 above the top of this arm's 95% interval**; reaching it would take 45 more programmed utility cards out of the same 484 dealt, a ~50% increase in the numerator. No plausible n=30 replicate lands on the other side of this bar.

### 1a. Per seat (secondary, pre-declared, not scored)

| Seat | Kept / dealt | Keep-rate | 95% Wilson | vs vp4 | vs vp2 | Below chance by |
|---|---:|---:|---|---:|---:|---:|
| red (brawler) | 39 / 242 | **0.161157** | [0.1202, 0.2127] | 1.07× | 1.62× | 3.10× |
| blue (sniper) | 52 / 242 | **0.214876** | [0.1678, 0.2709] | 0.79× | 0.91× | 2.33× |

**The seats moved in opposite directions from rung 2, and the aggregate turn-over is blue's.** Red held roughly its vp4 level (0.150 → 0.161) and remains 1.62× its vp2 level; blue fell from 0.273 to 0.215, back below its own vp2 reading (0.237). Rung 2's finding was that the second doubling landed almost entirely on red while blue decelerated. Rung 3 continues that pattern to its conclusion: blue's response reversed, red's flattened. Neither seat's interval comes within 0.22 of the 0.50 floor.

### 1b. Dose-response across the ladder (secondary, pre-declared, not scored)

| Rung | `vp_per_deploy` | Pooled keep-rate | Increment | Increment in W |
|---|---:|---:|---:|---:|
| comparator (incentive OFF) | 0 | 80/724 = 0.110497 | — | — |
| rung 1 | 2 | 115/684 = 0.168129 | +0.057631 | **+1.029 W** |
| rung 2 | 4 | 138/652 = 0.211656 | +0.043528 | **+0.777 W** |
| **rung 3 (this arm)** | **6** | **91/484 = 0.188017** | **−0.023640** | **−0.422 W** |

**The unscored incremental reading, which the pre-registration required precisely so this could not be blurred.** The third price step delivered a *negative* increment. It is not significantly negative (z = −0.982, p = 0.326), so the honest statement is not "price hurts" — it is that **the response is flat from vp4 onward and this rung cannot be distinguished from either of the two rungs beneath it**.

**Unweighted linear trend across all four doses:** slope **+0.013804 per VP**, intercept 0.128162, R² = 0.680. Fitted values 0.1282 / 0.1558 / 0.1834 / 0.2110 versus observed 0.1105 / 0.1681 / 0.2117 / 0.1880 — the line over-predicts at vp6 and under-predicts at vp2 and vp4, which is the signature of a curve that rises then flattens rather than a straight line. Restricted to the three *priced* rungs the slope collapses to **+0.004972 per VP**, a quarter of the four-point slope. Extrapolating the four-point line to the 0.5331 chance bar gives `vp ≈ 29.3`, up from rung 2's `vp ≈ 17` — and at `vp_per_deploy ≥ 15` a single resolved deploy wins the match outright, so that dose is not merely impractical, it is outside the arena's definition.

**Distance from the incentive-OFF comparator to chance closed:** vp2 13.6%, vp4 23.9%, **vp6 18.3%**. The ladder's best rung is vp4, and it closed under a quarter of the gap.

**Which of the three pre-declared shapes:** **(c) no further response** — this rung is indistinguishable from vp4 (p = 0.326). Shape (a) is refuted (the bar is far outside the interval). Shape (b) — saturation while remaining above the preceding rung — is not supported either, since the point estimate fell below vp4 rather than continuing to rise.

### 1c. Comparisons against baselines (secondary, pre-declared, not scored)

| Comparison | Baseline rate | This arm | Multiple | z | p (two-sided) | Significant at α=0.05? |
|---|---:|---:|---:|---:|---:|---|
| **Pooled vs vp4 rung (the one-step dose comparison)** | 138/652 = 0.211656 | 0.188017 | **0.89×** | **−0.982** | **0.326** | No |
| **Pooled vs vp2 rung** | 115/684 = 0.168129 | 0.188017 | **1.12×** | **0.878** | **0.380** | No |
| **Pooled vs surfacing-fix comparator (incentive OFF)** | 80/724 = 0.110497 | 0.188017 | **1.70×** | **3.787** | **1.5e-04** | **Yes** |
| Pooled vs U-GATE original (pre-#139 prompt code — **not** a clean single-lever comparison) | 30/812 = 0.036946 | 0.188017 | 5.09× | 9.042 | <1e-18 | Yes |

**Confound (5) discharged explicitly: H_SATURATE here does not mean "no effect."** The bounty is still worth 1.70× the incentive-OFF comparator at high significance. What died at this rung is the *dose* response, not the lever.

### 1d. This arm against the program

| Measure | Program maximum (all 23 prior arms) | This arm | New maximum? |
|---|---|---:|---|
| Pooled utility keep-rate | 0.211656 (vp4 rung) | 0.188017 | No — 2nd best |
| red-seat keep-rate | 0.150307 (vp4 rung) | **0.161157** | **Yes** |
| blue-seat keep-rate | 0.273006 (vp4 rung) | 0.214876 | No — 3rd best |

Red set a new program maximum; the pooled and blue figures did not. vp4 remains the ladder's best rung on the scored quantity.

---

## 2. Secondary — truncation-immunity checks (confound 2, pre-declared)

The bounty ends matches early, so the pre-registration required proof that truncation shortens *exposure* and not the *rate*, and stated that rung 2's clean result "does not automatically extend to rung 3 … it must be re-run there." It is re-run here, **and this is the rung where the check is weakest.**

**Round-capped keep-rate, rounds 1–2 only** — the pre-declared truncation-immune secondary.

| Window | This arm | vp4 reference | vp2 reference | vs vp2 z | p |
|---|---:|---:|---:|---:|---:|
| Rounds 1–2 only | **43 / 228 = 0.188596** `[0.1436, 0.2437]` | 54/240 = 0.225000 | 40/232 = 0.172414 | 0.451 | 0.652 |
| Full battery | 91 / 484 = 0.188017 | 138/652 = 0.211656 | 115/684 = 0.168129 | 0.878 | 0.380 |

**The two readings agree to within 0.0006 and agree in DIRECTION** — both put this rung below vp4 and marginally above vp2. The pre-registration's escape clause (if round-capped and pooled disagree in direction, pooled still scores and the disagreement becomes a first-class limitation) is **not triggered**. The scored conclusion does not depend on which rounds survived truncation.

**Seat-matches failing to reach round 2: 2 of 58** (both seats of seed 5007, a 6-tick timeout abort). Disclosed as pre-declared; at both prior rungs this count was zero.

**Stationarity in round index — the weakest of the three rungs:**

| Window | Kept / dealt | Rate |
|---|---:|---:|
| Rounds 1–3 | 68 / 324 | 0.209877 |
| Rounds 4+ | 23 / 160 | 0.143750 |

Two-proportion z = **1.752**, p = **0.0799**. Compare vp2 (z = 0.855, p ≈ 0.39) and vp4 (z = −0.067, p = 0.946). This is the drift the pre-registration warned about — "a seat two deploys from the line has an endgame incentive that does not exist at vp2" — and it does not reach significance but is no longer negligible. **Its direction matters for reading the verdict: late rounds are the *lower*-rate ones, and truncation removes late rounds, so truncation inflates the pooled rate.** The scored figure is therefore, if anything, flattered by truncation, and the arm still misses its bar by 1.33 CI widths.

**Per-round-index keep-rate:**

| Round | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kept/dealt | 19/116 | 24/112 | 25/96 | 14/76 | 3/36 | 3/24 | 3/16 | 0/4 | 0/4 |
| rate | 0.1638 | 0.2143 | 0.2604 | 0.1842 | 0.0833 | 0.1250 | 0.1875 | 0.0000 | 0.0000 |
| cumulative | 0.1638 | 0.1886 | 0.2099 | 0.2050 | 0.1950 | 0.1913 | 0.1912 | 0.1896 | 0.1880 |

### 2b. The abort artefact, and what removing it does (UNSCORED robustness check)

Seven matches terminated early (§3). Six carry exactly one `llm_completion_failed` with `reason_code: timeout`, one-to-one with the six `aborted` terminals (seeds 5007, 5008, 5009, 5011, 5020, 5025); the seventh (seed 5029) is a genuine `provider_semantic_failure` after three `invalid_response` failures. Because the pooled figure is the scored one, the effect of the artefact is reported and not substituted:

| Subset | Kept / dealt | Keep-rate | 95% Wilson | vs vp4 | Meets 0.2802 bar? |
|---|---:|---:|---|---:|---|
| **All 30 matches (SCORED)** | **91 / 484** | **0.188017** | [0.1557, 0.2252] | z = −0.982, p = 0.326 | **No, by 0.0922** |
| Non-aborted matches only (23) | 81 / 400 | 0.202500 | [0.1660, 0.2446] | z = −0.355, p = 0.723 | No, by 0.0777 |
| Aborted matches only (7) | 10 / 84 | 0.119048 | [0.0660, 0.2054] | — | — |

Removing every aborted match **raises** the arm's reading by 0.0145 and leaves it 0.0777 below the bar — still more than one CI width short, still indistinguishable from vp4. **The artefact depressed this arm's number, and the verdict is unchanged when it is removed.** This subset is a post-hoc robustness check, is reported here only, and is not the scored quantity.

---

## 3. Secondary — terminal mix, win rate, VP composition (pre-declared, NOT scored)

| Metric | This arm (vp6) | vp4 rung | vp2 rung | Surfacing-fix (OFF) |
|---|---|---|---|---|
| `match_started` / `match_ended` | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 |
| Terminal-class mix | **`vp_threshold` 12, `elimination` 11, `abort` 7** | `elimination` 16, `vp_threshold` 14, `abort` 0 | `elimination` 28, `vp_threshold` 1, `abort` 1 | `elimination` 29, `abort` 1 |
| `end_reason` × victory kind | `vp_threshold` 12, `last_mech_standing` 11, `aborted` 6, `provider_semantic_failure` 1 | — | — | — |
| `play_terminal_fraction` | **0.7667 — O-GATE FAIL** (threshold 0.95; `o_gate_pass: false`) | 1.0000 | 0.9667 | 0.9667 |
| Winner distribution | blue 20, **red 3**, draw 7 | blue 28, red 2 | blue 29, none 1 | blue 30 |
| **Red (brawler) win rate** | **3/30 = 0.100 all-match; 3/23 = 0.130 decided** | 2/30 = 0.0667 | 0/30 | 0/30 |
| Replay validity | **1/1 both players, all 30 matches** (`all_replay_valid: true`) | 1/1 all 30 | 1/1 all 30 | — |
| Aborts | **7/30** | 0/30 | 1/30 | 1/30 |

**`vp_threshold` terminals: 12 of 30 (40%)** — squarely on the vp2-replay projection (12/30, N = 532) and well under the closer vp4-replay projection (19–23/30). Realised N = 484 came in *below* both projections (508–532) because the timeout aborts removed rounds the projections assumed would be played.

**Confound (1) disclosure — the per-match `vp_threshold` path.** The pre-registration required disclosing every match that reached the line via the 2-deploy + ≥3-objective-VP shortcut rather than the structural 3-deploy path. **Zero matches took the shortcut.** All 12 `vp_threshold` terminals were won on exactly **3 resolved deploys (18 VP) with zero objective VP on the winning side**:

| seed | winner | deploys | bounty VP | obj VP | VP totals (blue / red) | margin | ticks |
|---|---|---:|---:|---:|---|---:|---:|
| 5002 | blue | 3 | 18 | 0 | 18 / 0 | 18 | 15 |
| 5003 | blue | 3 | 18 | 0 | 18 / 5 | 13 | 18 |
| 5006 | red | 3 | 18 | 0 | 12 / 18 | 6 | 16 |
| 5010 | blue | 3 | 18 | 0 | 18 / 0 | 18 | 16 |
| 5013 | blue | 3 | 18 | 0 | 18 / 12 | 6 | 8 |
| 5017 | blue | 3 | 18 | 0 | 18 / 0 | 18 | 8 |
| 5019 | blue | 3 | 18 | 0 | 18 / 6 | 12 | 16 |
| 5021 | red | 3 | 18 | 0 | 0 / 18 | 18 | 36 |
| 5022 | blue | 3 | 18 | 0 | 18 / 6 | 12 | 18 |
| 5023 | blue | 3 | 18 | 0 | 18 / 6 | 12 | 28 |
| 5027 | red | 3 | 18 | 0 | 12 / 18 | 6 | 36 |
| 5028 | blue | 3 | 18 | 0 | 18 / 6 | 12 | 17 |

Objective awards were rarer than at either prior rung: **6 awards across 2 matches, all red** — seed 5003 (`objective.west_yard` ×3, `objective.east_gate` ×2 = 5 VP) and seed 5014 (`objective.west_yard` ×1 = 1 VP) — with zero control changes. vp2 had 5 awards, vp4 had 8.

**All three of red's wins are bounty purchases** (seeds 5006, 5021, 5027 — each 3 deploys, 18 VP, zero objective VP), not firefight victories. Red has now gone 0/30 → 2/30 → 3/30 across the ladder while the blue standoff configuration is unchanged.

### VP composition (the win-rate confound, quantified)

| Source | VP | Share of all VP |
|---|---:|---:|
| Utility-deploy bounty (84 deploys × 6) | **504** | **98.8%** |
| Objective control (6 awards × 1) | 6 | 1.2% |
| **Total across all 30 matches** | **510** | 100% |

Bounty VP by seat: blue 300, red 204. Objective VP by seat: red 6, blue 0. **98.8% of every victory point scored in this arm is bounty VP** (vp2: 97.6%; vp4: 98.3%) — as pre-declared, the share rose again. Any win-rate or VP reading from this arm measures the bounty, not the seats. **This arm's win rate is not a balance result and must not be cited as one.**

---

## 4. Secondary — utility deployment (resolution layer)

| Metric | This arm (vp6) | vp4 rung | vp2 rung | Surfacing-fix (OFF) |
|---|---:|---:|---:|---:|
| `utility_deploy_intent` | 84 | 119 | 102 | — |
| `utility_deployed` (resolved) | **84** | 119 | 102 | 72 |
| by seat | blue 50, red 34 | blue 77, red 42 | blue 73, red 29 | blue 54, red 18 |
| by kind | smoke 53 (blue 33 / red 20), chaff 25 (blue 14 / red 11), flares 6 (blue 3 / red 3) | smoke 72, chaff 35, flares 12 | smoke 61, chaff 25, flares 16 | smoke 46, chaff 20, flares 6 |
| Matches with ≥1 deploy | 27/30 | 29/30 | 28/30 | — |
| Deploys per match (matches with ≥1) | **1–5, median 3** | 1–7, median 4 | 1–10, median 3 | — |
| **Programmed-to-resolved conversion** | **84 / 91 = 92.3%** | 119 / 138 = 86.2% | 102 / 115 = 88.7% | — |

Every deploy intent resolved (84/84). The **maximum deploys per match fell 7 → 5 and the median 4 → 3**: at vp6 the third deploy ends the match, so the distribution is truncated by construction, exactly as the tier arithmetic (`ceil(15/6) = 3`) predicts. Conversion rose to 92.3%, the highest of the three rungs — shorter matches leave less programmed utility stranded by a match ending before resolution.

---

## 5. Secondary — match length and completion health

| Metric | This arm (vp6) | vp4 rung | vp2 rung | Surfacing-fix (OFF) |
|---|---:|---:|---:|---:|
| min ticks | 1 (an abort) | 8 | 1 (the abort) | 13 |
| median ticks | **18.0** | 25.0 | 28.5 | 29.0 |
| mean ticks | **19.67** | 26.13 | 27.2 | 28.67 |
| max ticks | **44** | 40 | 59 | 73 |

Sorted durations (n=30): 1, 6, 8, 8, 8, 11, 15, 16, 16, 16, 16, 17, 17, 18, 18, 18, 19, 19, 19, 19, 21, 24, 24, 26, 28, 31, 35, 36, 36, 44.

Matches got shorter again (median 25.0 → 18.0). This is the mechanical consequence of a 3-deploy win condition compounded by seven early terminations, not a strategic finding.

| Completion metric | Value |
|---|---|
| `llm_completion_requested` | 259 |
| `llm_completion_resolved` | 244 |
| `llm_completion_failed` | **15 — 9 `invalid_response` (6 `invalid_action_parameters`, 3 `malformed_json`) + 6 `timeout`** |
| `plan_committed` | 242 |
| `finish_reason` distribution | `stop`: 244/244 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 242/242 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | **7/30** |

259 requested − 244 resolved = 15, matching `llm_completion_failed` exactly. The 244 − 242 = **2 resolved-but-uncommitted** completions both fall in aborted matches (seeds 5020, 5029), where the match ended before the resolved plan could commit; at vp4 this gap was zero.

**The 6 `timeout` failures are the arm's central caveat and have no counterpart in either prior rung** (vp2: 14 failures, all `invalid_response`; vp4: 8 failures, all `invalid_response`). They are a client-side 45-second transport ceiling being hit, not a model behaviour — see §7.

---

## 6. Verdict

**H_SATURATE is supported, and unlike rung 2 the evidence behind that verdict is strong.** Pooled utility keep-rate at `vp_per_deploy: 6` is 0.188017 against a bar of 0.2802 — short by 0.092183, which is 1.33× the arm's own CI width, with the bar 0.0550 clear of the top of the interval. The cumulative vp2 → vp6 span delivered 0.355 W where a linear response required 2.000 W.

**What the third point settles that two points could not:**

- **The dose response is over.** vp4 → vp6 delivered −0.422 W. This rung cannot be distinguished from vp4 (p = 0.326) or from vp2 (p = 0.380). Of the three pre-declared shapes the data support **(c) no further response**; **(a)** is refuted outright and **(b)** is not supported, because the point estimate fell rather than continued to rise.
- **The lever itself is not dead.** 1.70× the incentive-OFF comparator (z = 3.787, p = 1.5e-04). Confound (5) discharged: "the dose response stopped" is not "the bounty does nothing."
- **The ladder's best rung is vp4**, at 23.9% of the distance from the incentive-OFF baseline to chance. vp6 sits at 18.3%. Buying more price past vp4 bought nothing and cost structural damage to the arena (12/30 matches decided on 3 deploys, 98.8% bounty VP).
- **The turn-over is blue's.** Red set a new program maximum (0.161157) and held its rung-2 level; blue fell from 0.273 to 0.215, below its own vp2 reading. The seat with the strongest baseline utility aversion is the one that kept responding to price; the seat that started higher stopped and reversed.
- **The extrapolation moved the wrong way.** Rung 2 projected chance at `vp ≈ 17`; the four-point line now projects `vp ≈ 29.3`, past the `vp ≥ 15` point where one deploy wins the match outright. **No price on this ladder reaches the chance floor inside a non-degenerate arena** — rung 2 stated this as a projection and rung 3 confirms it with a measured turn-over rather than an extrapolated slope.

**The design implication, stated precisely.** Across three priced rungs the model's utility-drafting bias is **price-sensitive over a narrow band and then insensitive**. A structural in-register price is worth roughly a 1.3–1.9× lift in utility drafting and nothing beyond that, regardless of how much more you pay: the slope over the priced rungs alone is +0.005 per VP, a quarter of the four-point slope, and the ladder's peak (0.2117 at vp4) is still 2.4× below chance. Pricing is a real but bounded lever, and the remaining gap to chance is not a pricing problem.

**What this arm does NOT settle.** Whether the vp4 → vp6 decline is a true turn-over or flat response with sampling noise: the step is not significant (p = 0.326), so "flat from vp4 onward" is the supported reading and "declining" is not. Nothing here is a balance result (§3). The arm also carries an infrastructure artefact (§7) that a replicate on a quiet endpoint would not.

---

## 7. Limitations

- **Seven of thirty matches terminated early and the O-GATE failed.** `play_terminal_fraction` = 0.7667 against a 0.95 threshold (`o_gate_pass: false`). Six of the seven are one-to-one with `llm_completion_failed` `reason_code: timeout` — a 45-second client transport ceiling hit while the shared inference host was under heavy unrelated load — and the seventh is a genuine `provider_semantic_failure`. **Neither prior rung recorded a single `timeout`.** This is an infrastructure artefact of when the battery ran, not a property of `vp_per_deploy: 6`. Its measured effect is in §2b: removing all seven aborted matches raises keep-rate to 0.202500, which still misses the bar by 0.0777 and is still indistinguishable from vp4. The artefact worked against this arm and the verdict survives its removal — which is why it is disclosed as a limitation rather than used as grounds to discard the run.
- **The pre-registered discard rule is exhaustive, and it does not cover the O-GATE failure.** The rule discards a run **if and only if** it fails to complete all 30 seeds; this run reports `skipped_seeds: []`, 30 rows, driver exit 0. "No other discard reason is permitted" was committed before the run precisely so that a rule could not be invented afterwards to reject an inconvenient result. Scoring this run is compliance with the pre-registration, not endorsement of its completion health. A replicate on a quiet endpoint is the right follow-up, and it is a *new* arm, not a re-score of this one.
- **The scored run executed on a different workstation than rungs 1 and 2**, moved there by the previous session after three consecutive local runs died on network transport failures (see the discard disclosure below). The execution host sits on the same network segment as the inference host, so the identical overlay reaches the identical endpoint and model over a far shorter path. Nothing about the arm changed — same overlay file (verified byte-identical by SHA-256 against the local copy), same commit `8816f24` (verified, clean tree), same endpoint, same model, same seeds — but the client host is a difference from the two rungs this arm is compared against, and it is stated rather than buried. Six timeouts survived even on the shorter path, so the move mitigated the problem without eliminating it.
- **Realised N = 484 is the smallest pooled utility-dealt count of any clean n=30 arm in this program, and the pre-registered disclosure trigger fires.** The pre-registration flagged 620 as that threshold and predicted 384–532; realised 484 is inside the predicted band and below the trigger. Realised Wilson width 0.0695 = **1.24× W**, inside the projected 1.14–1.48× band. The bar is a fixed rate, so a smaller N could never move it — only widen this arm's interval — and even at this width the bar is far outside the interval.
- **Stationarity in round index is the weakest of the three rungs** (z = 1.752, p = 0.0799, versus p ≈ 0.39 at vp2 and p = 0.946 at vp4). The pre-registration predicted this specific risk at this specific rung. It does not reach significance, and its direction inflates rather than deflates the scored figure (late rounds are lower-rate; truncation removes late rounds), so it cannot explain the miss. The truncation-immune rounds-1–2 window agrees with the pooled reading to within 0.0006 and in direction, so the pre-registered escape clause is not triggered.
- **The blue standoff configuration this family inherits (the P1–P7 harpoon framing error, OMN-15119 class) applies to this arm unchanged.** Blue carries `weapon.siege.artillery_mortar` at range 50 and `weapon.heavy.harpoon_gun` at range 30 against red's range-12 machine gun and range-8 shrapnel thrower. Blue holds an uncontested standoff envelope; every win-rate and terminal figure in §3 must be read against it. The configuration is held at baseline deliberately — it is what makes the keep-rate comparison single-lever — and is not corrected here.
- **The bounty counts toward `vp_threshold`, and at this rung the win condition is effectively "three utility deploys."** `ceil(15/6) = 3`, so 12 of 30 matches (40%) ended on the bounty rather than on play, and all three of red's wins were bought with deploys. 98.8% of all VP was bounty VP. Zero matches took the 2-deploy + objective-VP shortcut the pre-registration required be disclosed per match.
- **The criterion is cumulative, which made this rung's bar demand acceleration.** Clearing 0.2802 required the vp4 → vp6 step alone to deliver 1.223 W, more than any earlier step delivered. The pre-registration disclosed this before the run, predicted the miss, and declined to move the bar. A reader who wants the incremental question answered should read §1b (the step delivered −0.422 W and is not significant) rather than the scored verdict, which answers the cumulative question.
- **"Criterion missed" and "response stopped" are separate claims and here they happen to agree.** That agreement is what makes this rung decisive; it is not a property of the criterion, and confound (5) still stands — a real-but-sub-cumulative move would have scored H_SATURATE too. The unscored tests in §1c are what separate the two, and they show the lever intact against the incentive-OFF comparator at p = 1.5e-04.
- **Comparator choice is load-bearing.** The scored anchor is the vp2 rung (0.168129) because the pre-committed formula anchors there; the most informative comparison for shape is the vp4 rung (0.211656), a battery on the same tree from the same day. The surfacing-fix comparator (0.110497) predates engine changes since 2026-07-23; the U-GATE original (0.036946) additionally predates the #139 prompt-surfacing fix and is reported for lineage only. The 0.89× (vs vp4), 1.12× (vs vp2) and 1.70× (vs surfacing-fix) figures are the defensible ones; 5.09× is not this arm's effect.
- **Keep-rate measures programming, not resolution.** 92.3% of programmed utility cards resolved into a deploy (§4). A reader comparing this document's keep-rate to a sibling arm's `utility_deployed`-based proxy is comparing two different quantities.
- **The per-rung dose comparison is a between-battery comparison, not a within-match one.** vp2, vp4 and vp6 are separate n=30 batteries on the same seeds and the same tree, run within hours of each other. Seeds are shared, which controls arena/deal variation, but LLM sampling is not held fixed across them.
- **One model, one arena, three priced rungs.** `foundry_60_asym_v1`, Qwen3.6-35B-A3B on both seats. The sub-chance keep-rate replicated across qwen35, deepseek, gemma and glm, but only qwen35 has been priced at any rung, and the shape finding here is a qwen35 finding.
- **n = 30 still cannot separate adjacent rungs.** vp6 is indistinguishable from both vp4 and vp2. The verdict is decisive against the *bar*, not against the neighbouring rungs, and this document does not claim the decline from vp4 is real.
- **Discarded runs, disclosed in full.** Four runs were discarded under the pre-registered rule before the scored run, every one for the sole permitted reason — failure to complete all 30 seeds from `LlmTransportError` seed kills — and each is retained on disk with its log under a `_DISCARDED_transport_errors_runN` lane name: run 1 (4 seeds skipped: 5005, 5012, 5013, 5014), run 2 (9 skipped: 5011, 5012, 5015, 5018, 5019, 5023, 5027, 5028, 5030), run 3 (killed by a session limit at seed 5023 with 4 already skipped), and run 4 (2 skipped, launched by this session and abandoned once the completed run was found). All four were evaluated on `skipped_seeds` alone, before any keep-rate was computed. **The scored run is the FIRST run that completed 30/30**, in accordance with the rule's "the first run that completes 30/30 is the scored run; it is not re-run"; a fifth run launched by this session before that run was discovered was killed mid-flight and its lane deleted without ever being scored. No run was discarded, kept, or re-run on the basis of its result.

---

## Citations (all relative paths)

- Recomputed metrics, this arm: `.onex_state/steel_onslaught/util_incentive_vp6/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `utility_deploy_intent`, `utility_deployed`, `objective_scored`, `victory_declared`, `weapon_fired`, `llm_completion_requested`/`resolved`/`failed`) and `battery_raw.jsonl` (30 rows, seeds 5001–5030); driver output `battery_summary.json`; run log `battery_run.log`.
- Pre-registration: overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp6_qwen.yaml`, commit `8816f24` (authored 2026-07-25T19:26:27Z), pushed before the first `match_started` at 2026-07-25T20:14:46.427769Z (margin 48 min 19 s). Branch cut from `main` at `8094e8f`; never rebased; SHA not rewritten.
- Preceding rung (rung 2): `docs/evidence/2026-07-25-util_incentive_vp4-battery.md`, ledger `.onex_state/steel_onslaught/util_incentive_vp4/events.sqlite3` (SO-UTIL-VP4 worktree), independently recomputed here.
- Scored anchor (rung 1): `docs/evidence/2026-07-25-util_incentive_vp2-battery.md`, ledger `.onex_state/steel_onslaught/util_incentive_vp2/events.sqlite3` (SO-UTIL-REWARD worktree), independently recomputed here.
- Single-lever comparator: `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`, ledger `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree).
- Lineage baseline: `docs/evidence/2026-07-23-ugate-asym-utility-battery.md`, ledger `.onex_state/steel_onslaught/ugate_asym_utility_battery/events.sqlite3` (SO-UGATE-ASYM worktree).
- Mechanism under test (unchanged this arm): `src/steel_onslaught/contracts/incentive.py`, `src/steel_onslaught/match/fold.py` (`_on_utility_deployed` payout, `_on_match_started` stamping), `src/steel_onslaught/llm/programming.py` (`legal_hand[].deploy_vp_bounty`, `incentives` block), merged `c6d0d9c`. Mechanism tests: `tests/match/test_utility_incentive.py`.
- Transport-error classification: `src/steel_onslaught/llm/client_http.py` (`HttpxJsonTransport.post_json` — `httpx.TimeoutException` → `reason_code: timeout`, `httpx.RequestError` → `LlmTransportError`).
- Battery driver: `scripts/run_ogate_objectives_battery.py` (non-zero exit on any skipped seed as of #204, which is what makes the discard rule exit-code checkable).
- Prompt-steering negative this ladder is contrasted against: `docs/evidence/2026-07-24-prompt_guidance_v2-battery.md`, `docs/evidence/2026-07-24-prompt_surfacing_v2-battery.md`.
- No secrets, keys, or absolute paths included.
