# SO-UTIL-REWARD Arm (structural in-register utility VP bounty, `vp_per_deploy: 2`) Battery — 2026-07-25

**Verdict:** **H_PRIOR is supported; the pre-registered formal criterion is NOT met — and the arm simultaneously produced the largest utility-drafting shift ever recorded in this program.** Pooled (red+blue) utility keep-rate is **115/684 = 0.1681** (95% Wilson `[0.1420, 0.1980]`). The pre-registered bar required **≥ 0.5331**. Observed is **0.3650 short** of that bar — the model is still programming utility **2.97× below the 0.50 chance floor**, and closing the gap would have taken **250 more** programmed utility cards out of the same 684 dealt. Scored against the one criterion the pre-registration named, the structural incentive did **not** lift keep-rate above chance.

That is the scored answer, and it is not the whole finding. Against the valid single-lever comparator — the same overlay measured after the surfacing fix (#139), pooled 80/724 = 0.1105 — this arm's keep-rate is **1.52× higher (z = 3.13, p = 0.0018)**, and it is the **highest pooled, highest red-seat, and highest blue-seat utility keep-rate of all 21 prior arms** in this program (previous maxima: pooled 0.1183, red 0.0772, blue 0.1950 — every one of them beaten). L-GATE-2 established that prompt-level steering does not move this model's drafting. **A price the model reads as game state does move it — significantly, reproducibly, and nowhere near enough.** That combination is the design finding, and it is a strictly different result from "the lever did nothing."

**Ledger:** `.onex_state/steel_onslaught/util_incentive_vp2` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `battery_run.log`, `evaluations/`, `experiments/`) in the SO-UTIL-REWARD worktree.

**Change under test:** exactly ONE lever versus the U-GATE baseline overlay — the `contracts.utility_incentive` binding (`kind: utility_deploy_vp_bounty`, `vp_per_deploy: 2`). The mechanism itself (`src/steel_onslaught/contracts/incentive.py`, the `MatchStateFold` payout, the `MATCH_STARTED` stamping, and the in-register prompt fields) merged unlaunched as `c6d0d9c`; this arm adds the pre-registration and runs the battery. No arena, loadout, deck, weapon, persona, prompt-instruction, or handler file differs from the baseline.

**Dose and range configuration (held at the UNSCALED baseline, stated explicitly):**
- **Red DOSE: unscaled.** `loadout.llm.qwen35_berserker` → `weapon.light.machine_gun` (damage 8, range 12) and `weapon.light.shrapnel_thrower` (damage 12, range 8). No P1–P7 dose-ladder variant (`_dmg3`/`_dmg8`/`_dmg11`/`_dmg16`/`_dmg24`/`_dmg55`/`_armor8`) is referenced anywhere in this arm.
- **Blue RANGE: uncut.** `loadout.llm.qwen35_sniper_ironclad` → `weapon.siege.artillery_mortar` (range 50, damage 45) and `weapon.heavy.harpoon_gun` (range 30, damage 28). No `_r30`/`_r15` SO-RANGECAP/SO-STANDOFF variant is referenced.
- Engine-layer confirmation of both: the ledger's `weapon_fired` breakdown carries only the stock, un-suffixed weapon ids — `weapon.siege.artillery_mortar` 104, `weapon.light.machine_gun` 86, `weapon.heavy.harpoon_gun` 52, `weapon.light.shrapnel_thrower` 32 (274 total). Zero ladder-variant ids appear.
- The ladders are deliberately **not** applied: the scored quantity here is keep-rate, and holding dose and range at baseline is what keeps this arm exactly one lever from the arm whose keep-rate it is scored against.

**Arena / deal:** `foundry_60_asym_v1`, `vp_threshold: 15`, over-deal 10 (4 movement + 4 weapon + 2 utility), program 5, utility handler pack `utility.resolution.v1` complete.
**Model:** live Qwen3.6-35B-A3B, both seats, keyless. n = 30, seeds 5001–5030, `--fresh`. `battery_raw.jsonl` holds exactly 30 rows; seeds 5001–5030 each present exactly once; zero duplicates, zero gaps; `events.sqlite3` shows exactly **30** `match_started` and **30** `match_ended`.
**Baselines (all independently recomputed from their own ledgers by the method in §Method, not copied from their published docs):**
- **Scored comparator — surfacing-fix re-measure** (same overlay `tactical_split_overdeal_utility_asym_v1_qwen.yaml`, post-#139 prompt code): pooled 80/724 = 0.110497; red 20/362 = 0.055249; blue 60/362 = 0.165746. `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- **U-GATE original** (same overlay, **pre**-#139 prompt code): pooled 30/812 = 0.036946; red 7/406 = 0.017241; blue 23/406 = 0.056650. `docs/evidence/2026-07-23-ugate-asym-utility-battery.md`.
- **Family anchor:** pooled 1,037/12,656 = 0.081937 over the 16 clean n=30 `utility_asym` qwen35 arms.

---

## 0. Pre-registered hypothesis and criterion (quoted from the overlay header, committed before this battery ran)

From `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp2_qwen.yaml`.

| Event | Commit (current) | Commit (as originally pushed, pre-rebase) | Author timestamp (preserved) |
|---|---|---|---|
| Pre-registration — hypotheses + the ONE formal criterion | `b8967e3` | `69ffd77` | **2026-07-25T17:26:48Z** |
| Amendment — discard rule only, criterion unchanged | `9443926` | `1fa6456` | **2026-07-25T18:00:44Z** |
| **First `match_started` of the scored run** | — | — | **2026-07-25T18:00:55.864143Z** |

Both pre-registration commits precede the first `match_started` of the scored run — the criterion by 34 minutes, the discard amendment by 11 seconds. Both were pushed to the remote branch before the run they govern. The branch was later rebased onto `main` to pick up a concurrently-landed sibling arm, which rewrote the commit SHAs; git's **author** timestamps are preserved unchanged through that rebase and are the ordering evidence. The pre-rebase SHAs are recorded above so the originally-pushed objects remain identifiable.

> **H_PRICED** — the drafting bias is a PREFERENCE the model will trade against a stated in-game price. Paying victory points per resolved utility deploy, surfaced as game state rather than as instruction text, lifts utility keep-rate above the chance floor.
>
> **H_PRIOR** — the drafting bias is a PRIOR the model holds regardless of price. The structural incentive fails to lift keep-rate above chance, exactly as prompt-level steering failed in L-GATE-2. A fully real, publishable, first-class negative result per house rule, and the prior-favoured outcome given the 0.0819 pooled baseline.
>
> **FORMAL CRITERION — the ONLY criterion this arm is scored against.**
> Quantity: POOLED (red + blue) utility keep-rate, n = 30, seeds 5001-5030, computed by the paired hand_dealt/plan_committed method above.
> ARITHMETIC (independently verified before this commit):
> ```
>   p0    = 5 / 10 = 0.500000            (chance floor, confirmed empirically
>                                         at 0.500000 exact, 31,640/63,280)
>   N_min = 620                          (smallest pooled utility-dealt count
>                                         observed in any of the 16 clean
>                                         n=30 arms — pair_p4_dmg8)
>   SE    = sqrt(p0 * (1 - p0) / N_min)
>         = sqrt(0.25 / 620) = sqrt(0.00040322580645) = 0.02008048
>   z     = 1.645                        (one-sided, alpha = 0.05)
>   delta = z * SE = 1.645 * 0.02008048 = 0.03303239
>   bar   = p0 + delta = 0.500000 + 0.03303239 = 0.53303239
>         -> rounded UP to 4 dp = 0.5331
> ```
> DECISION: pooled utility keep-rate >= 0.5331 supports H_PRICED. pooled utility keep-rate < 0.5331 supports H_PRIOR.

The header also pre-declared the secondary observables reported in §3–§5 as **reported, never scored**, precisely so a large-but-sub-chance move could not be written up post hoc as a rescue. It is a large-but-sub-chance move, and it is reported as exactly that.

### 0a. The chance floor, recomputed from prior arm artifacts (not eyeballed)

- **Structural:** p0 = `register_count` / `hand_size` = 5 / 10 = 0.5000.
- **Empirical confirmation:** pooled all-card keep-rate across the 16 clean n=30 `utility_asym` qwen35 arm ledgers = **31,640 / 63,280 = 0.500000 exactly**. Pilots keep cards at chance in aggregate; they dump *utility* specifically.
- **This arm's own all-card control held:** 1,710 kept / 3,420 dealt = **0.500000 exactly** (855/1,710 per seat). The utility gain came out of the register mix, not from committing more cards.

**Method-fidelity check.** The recompute code used throughout this document reproduces the two published baseline arms' figures exactly — U-GATE red 7/406 = 0.017241 and blue 23/406 = 0.056650; surfacing-fix red 20/362 = 0.055249 and blue 60/362 = 0.165746 — matching their evidence documents digit for digit. The measurement is the program's existing one, not a new one tuned for this arm.

---

## Method

Keep-rate is defined exactly as the U-GATE arm defined it. For each seat, every `hand_dealt` is paired with the `plan_committed` that follows it for the same `(match_id, seat)` in ledger order; keep-rate = (cards of the category appearing in `plan_committed.registers[].card_id`) ÷ (cards of that category appearing in `hand_dealt.card_ids`). Unpaired hands are excluded from **both** numerator and denominator. **Unpaired hands in this arm: 0** (171 paired rounds per seat, 342 total).

Note this is *programmed*, not *deployed*. Some sibling arm documents report a `utility_deployed`-based proxy; that measures resolution as well as drafting and is not the quantity the criterion names. Both are reported here (§4).

Statistics: two-proportion z-tests for arm-vs-baseline comparisons; one-proportion z against the fixed 0.50 floor; 95% Wilson intervals throughout.

---

## 1. PRIMARY — utility keep-rate versus chance

| Quantity | Value |
|---|---|
| Pooled utility kept / dealt | **115 / 684** |
| **Pooled utility keep-rate (the SCORED quantity)** | **0.168129** |
| 95% Wilson CI | **[0.1420, 0.1980]** |
| Pre-registered bar | 0.5331 |
| **Meets bar?** | **NO — short by 0.3650** |
| Cards needed to reach the bar (same 684 denominator) | 365 programmed (observed 115) — **250 more** |
| One-proportion z vs the 0.50 chance floor | **−17.36** (the rate is below chance, decisively) |
| Distance below chance, pooled | **2.97×** |
| All-card keep-rate (mechanical control) | 0.500000 exactly |

### 1a. Per seat (secondary, pre-declared, not scored)

| Seat | Kept / dealt | Keep-rate | 95% Wilson | Below chance by |
|---|---:|---:|---|---:|
| red (brawler) | 34 / 342 | **0.099415** | [0.0720, 0.1357] | 5.03× |
| blue (sniper) | 81 / 342 | **0.236842** | [0.1949, 0.2847] | 2.11× |

Both seats moved; blue moved further in absolute terms, red further in relative terms (§1b). Neither seat's Wilson interval comes within 0.21 of the 0.50 floor.

### 1b. Comparisons against baselines (secondary, pre-declared, not scored)

| Comparison | Baseline rate | This arm | Multiple | z | p (two-sided) | Significant at α=0.05? |
|---|---:|---:|---:|---:|---:|---|
| **Pooled vs surfacing-fix (same overlay, post-#139 — the valid single-lever comparator)** | 80/724 = 0.110497 | 115/684 = 0.168129 | **1.52×** | **3.129** | **0.0018** | **Yes** |
| red vs surfacing-fix | 20/362 = 0.055249 | 34/342 = 0.099415 | 1.80× | 2.201 | 0.0277 | Yes |
| blue vs surfacing-fix | 60/362 = 0.165746 | 81/342 = 0.236842 | 1.43× | 2.356 | 0.0185 | Yes |
| Pooled vs U-GATE original (pre-#139 prompt code — **not** a clean single-lever comparison, see Limitations) | 30/812 = 0.036946 | 0.168129 | 4.55× | 8.544 | 1.3e-17 | Yes |
| Pooled vs 16-arm family anchor | 1,037/12,656 = 0.081937 | 0.168129 | 2.05× | 7.817 | 5.4e-15 | Yes |

This is the first arm in the **qwen35 `utility_asym` lever family** whose adjacent-arm comparison reaches significance. Every prior adjacent-arm comparison in that family — dose ladder, range ladder, composition, spatial, scenario, prompt — has been non-significant at n=30, a record the sibling arm documents describe as unbroken. It is broken here, on the drafting axis, by a lever that is neither prompt- nor balance-shaped. (The claim is scoped to this family on purpose: the vision arms produced a much larger significant effect on a different model, arena and axis — `docs/evidence/2026-07-24-vl_vertex_rerun-battery.md`, red 16/30 → 0/30 — and are not part of this ladder.)

### 1c. Against every prior arm in the program

Recomputed from all 21 prior `utility_asym` qwen35 arm ledgers held under the sibling SO-* worktrees:

| Measure | Previous program maximum | This arm | New maximum? |
|---|---|---:|---|
| Pooled utility keep-rate | 0.118257 (`tourn_arm13_leapfrog_cover`) | **0.168129** | **Yes** |
| red-seat keep-rate | 0.077206 (`spatial_r1_battery`) | **0.099415** | **Yes** |
| blue-seat keep-rate | 0.195021 (`tourn_arm13_leapfrog_cover`) | **0.236842** | **Yes** |

All 21 prior arms are strictly below this arm on all three measures.

### 1d. Formal-criterion scoring — the pre-registered decision

| Reading | Value | vs bar 0.5331 | Result |
|---|---:|---|---|
| Pooled utility keep-rate (the ONLY scored reading) | 0.168129 | need ≥ 0.5331 | **falls short by 0.3650** |

**H_PRIOR is supported.** The miss is not marginal: the observed rate sits below the bar by 0.3650, which is **6.5× the full width of its own 95% Wilson interval** (0.0560), and below the raw chance floor by z = −17.36. No plausible n=30 sampling story puts this arm near the bar.

---

## 2. Secondary — win rate and terminal health (pre-declared, NOT scored; see Limitations)

| Metric | This arm | Surfacing-fix baseline | U-GATE original |
|---|---|---|---|
| `match_started` / `match_ended` | 30 / 30 | 30 / 30 | 30 / 30 |
| Terminal-class mix | `elimination` 28, **`vp_threshold` 1**, `abort` 1 | `elimination` 29, `abort` 1 | `elimination` 30 |
| `play_terminal_fraction` | **0.9667** (task gate ≥0.9 PASS; codebase default ≥0.95 PASS) | 0.9667 | 1.0000 |
| Winner distribution | blue 29, no winner (abort) 1 | blue 30 (its abort row still records a blue winner; the published doc reports that match as a draw) | blue 30 |
| **Red (brawler) all-match win rate** | **0/30 = 0.0000** | 0/30 | 0/30 |
| Replay validity | 1/1 both players, all 30 matches | — | — |

**Red's win rate is 0/30, identical to both baselines.** The bounty changed *drafting*; it did not change strategic balance. This is consistent with the surfacing-fix arm's own conclusion and with the fact that this arm runs the un-laddered configuration in which blue dominates (see Limitations).

**One `vp_threshold` terminal (seed 5024) — the first ever recorded in this arm family** (U-GATE 0/30, surfacing-fix 0/30). Blue reached 15 VP at tick 52: 14 bounty VP from 7 resolved deploys plus 1 objective award. This is a mechanism fact, not a balance fact — see §3 and Limitations.

**One abort (seed 5017),** `provider_semantic_failure`, 3 failed completions, died at tick 1 with `is_draw=true`, no winner, no VP. Same failure class and same 1/30 rate as the surfacing-fix baseline.

---

## 3. Secondary — VP composition (the win-rate confound, quantified)

| Source | VP | Share of all VP |
|---|---:|---:|
| Utility-deploy bounty (102 deploys × 2) | **204** | **97.6%** |
| Objective control (5 `objective_scored` awards × 1) | 5 | 2.4% |
| **Total across all 30 matches** | **209** | 100% |

Final VP totals: blue 148, red 61. Bounty VP by seat: blue 146, red 58. Objective awards: red 3, blue 2.

**97.6% of every victory point scored in this arm is bounty VP.** Any win-rate or VP reading from this arm measures the bounty, not the seats. This was pre-declared in the overlay header before the run and is restated in Limitations.

---

## 4. Secondary — utility deployment (resolution layer)

| Metric | This arm | Surfacing-fix baseline | U-GATE original |
|---|---:|---:|---:|
| `utility_deploy_intent` | 102 | — | — |
| `utility_deployed` (resolved) | **102** | 72 | 26 |
| by seat | blue 73, red 29 | blue 54, red 18 | — |
| by kind | smoke 61 (blue 42 / red 19), chaff 25 (blue 18 / red 7), flares 16 (blue 13 / red 3) | smoke 46, chaff 20, flares 6 | — |
| Matches with ≥1 deploy | 28/30 | — | — |
| Deploys per match (matches with ≥1) | 1–10, median 3 | — | — |

**Programmed-to-resolved conversion: 102 / 115 = 88.7%.** The 13-card shortfall is programmed utility that never reached resolution (match ended, mech destroyed, or heat lock) — the bounty pays on resolution, never on programming, so those cards paid nothing. Every deploy intent resolved (102/102), so the loss is upstream of the resolver, not in it.

---

## 5. Secondary — match length and completion health

| Metric | This arm | Surfacing-fix baseline | U-GATE original |
|---|---:|---:|---:|
| min ticks | 1 (the abort) | 13 | 17 |
| median ticks | **28.5** | 29.0 | 31.0 |
| mean ticks | **27.2** | 28.67 | 30.8 |
| max ticks | 59 | 73 | 71 |

Sorted durations (n=30): 1, 8, 8, 10, 10, 13, 20, 23, 23, 24, 24, 28, 28, 28, 28, 29, 29, 29, 29, 29, 30, 30, 31, 32, 33, 39, 39, 50, 52, 59.

Match length is essentially flat against both baselines (median 28.5 vs 29.0 vs 31.0). The bounty did not visibly lengthen or shorten matches; no mechanism is claimed for the small downward drift.

| Completion metric | Value |
|---|---|
| `llm_completion_requested` | 356 |
| `llm_completion_resolved` | 342 |
| `llm_completion_failed` | 14 (all `invalid_response`) |
| `finish_reason` distribution | `stop`: 342/342 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 342/342 committed plans (zero fallback/heuristic) |
| Matches reaching an unrecovered abort | 1/30 (seed 5017) |

356 requested − 342 resolved = 14, matching `llm_completion_failed` exactly, with zero gap between resolved and `plan_committed`. Failure count and class match the surfacing-fix baseline's own regression profile (18 `invalid_response`/`invalid_action_parameters`, 1 abort) rather than indicating anything new in this arm.

---

## 6. Verdict

**H_PRIOR is supported: the pre-registered formal criterion is not met, by a wide margin.** A structural, in-register, engine-paid victory-point price on utility deployment does **not** lift utility keep-rate above the 0.50 chance floor. At `vp_per_deploy: 2` against `vp_threshold: 15` — a price steep enough that eight resolved deploys win the match outright, and steep enough that it produced this family's first-ever VP-threshold victory — the model still programs utility at 0.1681, nearly 3× below chance, and 0.3650 below the pre-registered bar.

**And the same battery falsifies the stronger reading of the program's standing negative result.** Before this arm, the honest summary was "utility deprioritization survives every lever tried, including prompt-level steering (L-GATE-2)." That is no longer the summary. This lever moved it:

- **1.52× above the valid single-lever comparator, z = 3.13, p = 0.0018** — the first significant adjacent-arm comparison in the qwen35 `utility_asym` lever family, against that family's otherwise unbroken record of non-significance at n=30.
- **Highest pooled, red, and blue keep-rate of all 21 prior arms**, beating every previous maximum on all three measures.
- **Deploys 72 → 102**; first `vp_threshold` terminal ever observed in this family; 97.6% of all VP scored came from the bounty.

**The design implication, stated precisely.** The drafting bias is neither a pure preference (a preference would have traded against this price and cleared chance) nor a fixed prior immune to incentive (a fixed prior would not have moved 1.52× and set three program records). It behaves like a **strong prior that is priced-sensitive but heavily discounted**: the model registers the in-register price, reallocates registers toward utility in response, and stops far short of what the price alone would justify. Prompt-level steering produced no such reallocation. **Structural incentive is the first lever class in this program that reaches the drafting layer at all** — and at `vp_per_deploy: 2` it closes about **15%** of the distance from the comparator baseline to chance ((0.168129 − 0.110497) ÷ (0.5 − 0.110497) = 0.148).

**What this arm does NOT settle.** It tests exactly one price. A dose-response ladder on `vp_per_deploy` — the obvious next arm, and the one this result makes worth running — is the only way to distinguish "the response saturates well below chance" from "the response is real but this price is simply too small." This document makes no claim about which, and n=30 cannot distinguish them. Nothing here should be read as a balance result (§3).

---

## 7. Limitations

- **The blue standoff configuration this family inherits (the P1–P7 harpoon framing error, OMN-15119) applies to this arm unchanged.** Blue carries `weapon.siege.artillery_mortar` at range 50 and `weapon.heavy.harpoon_gun` at range 30 against red's range-12 machine gun and range-8 shrapnel thrower. Blue therefore holds an uncontested standoff envelope, red wins 0/30, and every win-rate/terminal figure in §2 must be read against that. This arm holds the configuration at baseline deliberately (it is what makes the keep-rate comparison single-lever) and does not attempt to correct it; the mortar-range and dose ladders that partially correct it live in the SO-RANGECAP / SO-STANDOFF / P1–P7 arms and are explicitly not applied here.
- **Win rate in this arm is not a balance result and must not be cited as one.** 97.6% of all VP scored was bounty VP (§3); the single `vp_threshold` victory was 14/15 bounty. The bounty is a live confound on the win condition by construction, pre-declared in the overlay header before the run.
- **Comparator choice is load-bearing and the pre-#139 baseline is not a clean comparison.** The scored comparator is the surfacing-fix re-measure (same overlay, post-#139 prompt code, pooled 0.1105). The U-GATE original (0.0369) predates the #139 prompt-surfacing fix, so the 4.55× figure against it conflates this arm's incentive with that fix and is reported for lineage completeness only, never as this arm's effect. The 1.52× figure is the defensible one.
- **The surfacing-fix comparator is 2 days old and the tree has moved.** Engine changes have landed since 2026-07-23 (for example the defense handler-pack refactor, `38dd334`). The comparator was not re-run on current code, so a small share of the 1.52× could in principle be unrelated drift. This is the closest available comparator, not a contemporaneous one, and no attempt is made here to bound that share.
- **Two earlier runs of this battery were discarded for incompleteness, under a rule committed before the scored run.** Run r1 lost 10 of 30 seeds (5008, 5011, 5012, 5013, 5015, 5016, 5018, 5019, 5022, 5024) to `LlmTransportError` while a sibling battery contended for the same single vLLM endpoint; run r2 lost 1 seed (5023) to an isolated provider blip. The overlay's `retry.max_attempts: 1` is byte-identical to the baseline and was deliberately **not** modified — changing it would break the one-lever property — so a provider blip kills a whole seed rather than producing an in-match abort. The discard condition ("any entry in `skipped_seeds`") is readable from `battery_summary.json` alone, is independent of the outcome, and was evaluated before any keep-rate was computed on any run; the primary outcome was not computed on either discarded run. Both are retained on disk with full run logs at `.onex_state/steel_onslaught/util_incentive_vp2_r1_DISCARDED_transport_contention` and `.onex_state/steel_onslaught/util_incentive_vp2_r2_DISCARDED_provider_error`. The scored run is the first to complete 30/30 and was not re-run.
- **Keep-rate measures programming, not resolution.** 88.7% of programmed utility cards resolved into a deploy (§4). A reader comparing this document's keep-rate to a sibling arm's `utility_deployed`-based proxy is comparing two different quantities; §4 reports both.
- **One abort (seed 5017, `provider_semantic_failure`, 1/30)** — same class and rate as the surfacing-fix baseline. It contributes 0 dealt and 0 programmed cards to the keep-rate denominator (the unpaired-hand rule), and is counted as a non-win in §2.
- **One price, one model, one arena.** `vp_per_deploy: 2`, Qwen3.6-35B-A3B on both seats, `foundry_60_asym_v1`. No dose-response ladder on the bounty rate, no cross-model replication, no scenario variation. The cross-model question is live: the sub-chance keep-rate replicated across qwen35, deepseek, gemma and glm, but only qwen35 has been priced.
- **n=30 bounds the secondary claims, not the scored one.** The criterion miss is far too large for sampling variance to be at issue. The 1.52× secondary lift rests on p = 0.0018 at n=30 and has not been replicated; it should be treated as a strong single-arm signal, not a settled effect size.
- **No re-run to chase a different number.** n=30, seeds 5001–5030, was pre-declared; the scored battery completed all 30 seeds and is reported as-is, including the abort.

---

## Citations (all relative paths)

- Recomputed metrics, this arm: `.onex_state/steel_onslaught/util_incentive_vp2/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `utility_deploy_intent`, `utility_deployed`, `objective_scored`, `victory_declared`, `weapon_fired`, `llm_completion_requested`/`resolved`/`failed`) and `battery_raw.jsonl` (30 rows, seeds 5001–5030); driver output `battery_summary.json`, full run log `battery_run.log`.
- Discarded runs (retained, disclosed): `.onex_state/steel_onslaught/util_incentive_vp2_r1_DISCARDED_transport_contention/`, `.onex_state/steel_onslaught/util_incentive_vp2_r2_DISCARDED_provider_error/`.
- Pre-registration: overlay `contracts_data/overlays/tactical_split_overdeal_utility_asym_incentive_vp2_qwen.yaml`, commits `b8967e3` (criterion, authored 2026-07-25T17:26:48Z, pre-rebase `69ffd77`) and `9443926` (discard-rule amendment, authored 2026-07-25T18:00:44Z, pre-rebase `1fa6456`) — see §0 for the ordering evidence.
- Mechanism under test: `src/steel_onslaught/contracts/incentive.py`, `src/steel_onslaught/match/fold.py` (`_on_utility_deployed` payout, `_on_match_started` stamping), `src/steel_onslaught/llm/programming.py` (`legal_hand[].deploy_vp_bounty`, `incentives` block), merged `c6d0d9c`. Mechanism tests: `tests/match/test_utility_incentive.py` (21 passed) — including `test_system_prompt_is_byte_identical_with_and_without_an_incentive` and `test_no_incentive_vocabulary_in_any_prompt_text`, which are what make "in-register, not in-prompt" a checked property rather than a claim.
- Scored comparator: `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`, ledger `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree), independently recomputed here.
- Lineage baseline: `docs/evidence/2026-07-23-ugate-asym-utility-battery.md`, ledger `.onex_state/steel_onslaught/ugate_asym_utility_battery/events.sqlite3` (SO-UGATE-ASYM worktree), independently recomputed here.
- Chance-floor confirmation and the 21-arm program comparison: the `utility_asym` qwen35 arm ledgers under the sibling SO-* worktrees, recomputed by the §Method pairing.
- Prompt-steering negative this arm is contrasted against: L-GATE-2 arms, `docs/evidence/2026-07-24-prompt_guidance_v2-battery.md` and `docs/evidence/2026-07-24-prompt_surfacing_v2-battery.md`.
- No secrets, keys, or absolute paths included.
