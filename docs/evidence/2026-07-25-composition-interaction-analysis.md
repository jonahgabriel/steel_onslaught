# Composition Interaction Analysis (SO-COMP-INT) — the "long right tail is an interaction" reading does not survive a factorial decomposition; the real interaction is in out-of-range fire (2026-07-25)

**What this is:** a re-analysis, not a battery. No LLM was called and no match was run. All four corners of the `covered_advance` × `spatial R1` factorial at the ×16 dose already exist as completed n=30 batteries on the same arena with the same loadouts and the same seed block (5001–5030). This document decomposes them.

**Headline, stated plainly and with its limits attached:**

1. **Match-length location shows NO interaction.** On the log (multiplicative) scale the two levers are cleanly additive: `covered_advance` ×1.686, spatial R1 ×1.152, predicted composition geometric mean 44.03 vs observed **41.92**. The interaction term is **×0.952** (95% CI ×0.736 to ×1.231, z = −0.37). Median interaction is **−2.0 ticks**, mean **+2.90** — both bootstrap CIs straddle zero comfortably.
2. **The composition's long right tail is NOT evidence of an interaction.** It is what a no-interaction *multiplicative* model predicts. The count of matches longer than 60 ticks (a length no single-lever arm ever produced) is **6/30 observed against a no-interaction null median of 5–6** under both a nonparametric surrogate and a parametric lognormal null. The closest thing to an anomaly is dispersion — `sd(log) = 0.485` against a null 95% interval of [0.29, **0.49**], one-sided P = 0.032 — i.e. still inside the interval, uncorrected for multiplicity, and driven by two matches.
3. **The one endpoint that does show an interaction is out-of-range fire, and it is antagonistic.** `covered_advance` alone suppresses red's out-of-range fraction by 4.5 pp; spatial R1 alone suppresses it by 10.1 pp; stacked, the suppression essentially vanishes (0.7649 vs a 0.6325 additive prediction). Interaction **+0.1324**, cluster-bootstrap 95% CI **[+0.012, +0.256]**. R1's in-range flags stop binding once `covered_advance` is in red's movement deck.
4. **Mechanism of the tail:** the composition's long matches are *slow-closing* matches, not high-attrition ones. Total hits landed per match is invariant across all four arms (3.07–3.39) — at ×16 damage a match is over after ~3 hits, so match length is essentially time-to-contact. Decomposing length into close / convert / finish phases puts the *entire* residual interaction in the **close** phase (+7.80 ticks) and none in convert (−0.66) or finish (+0.08).

**What this document does not claim:** this is an **observational decomposition of four independently-run arms**, not a pre-registered factorial experiment. No criterion was pre-registered here; nothing is graded PASS/FAIL. Every arm is n=30, one arm per cell, one model, one arena, one blue standoff configuration. Several endpoints are examined, so nominal p-values are not multiplicity-corrected. Where a term is not distinguishable from zero at this n, that is stated rather than rounded into a story.

---

## 1. Provenance — the four corners and their raw ledgers

All four ledgers were located and read directly. No number below is taken from a published document, from `battery_summary.json`, or from driver stdout; `battery_summary.json` under per-seed invocation describes only the last single-seed run and is not a source for anything here.

| Corner | `covered_advance` | spatial R1 | State root (relative to that worktree's repo root) | Worktree | Merge |
|---|---|---|---|---|---|
| **P6** (neither) | no | no | `.onex_state/steel_onslaught/pair_p6_dmg16` | `SO-COMP-P5` sibling checkout `steel_onslaught_p6` | `93aaa43` (PR #191) |
| **CA** (`covered_advance` only) | **yes** | no | `.onex_state/steel_onslaught/composition_ca_only_dmg16` | `SO-COMP-CA` | `a894ad2` (PR #202) |
| **R1** (spatial R1 only) | no | **yes** | `.onex_state/steel_onslaught/composition_r1_only_dmg16` | `SO-COMP-R1` | `6c34db9` (PR #200) |
| **COMP** (both) | **yes** | **yes** | `.onex_state/steel_onslaught/composition_p6dmg16_covadv_r1` | `SO-COMP-P5` sibling checkout `steel_onslaught_comp16` | `37ab224` (PR #193) |

Every state root contains `events.sqlite3` + `battery_raw.jsonl` with exactly **30 rows, seeds 5001–5030, no duplicates, no gaps**. No corner's raw ledger was unlocatable; nothing in this analysis substitutes a published number for a distribution.

**Contamination handling.** Raw `match_started` counts in the ledgers are 33 (P6), 34 (CA), 31 (R1), 31 (COMP) — orphans left by transport retries. **Every query in this document filters to the 30 `match_id`s present in `battery_raw.jsonl`.** The unfiltered counts are never used as a denominator.

**Factorial cleanliness, verified from the overlays rather than assumed:**

| | P6 | CA | R1 | COMP |
|---|---|---|---|---|
| `arena_id` | `foundry_60_asym_v1` | `foundry_60_asym_v1` | `foundry_60_asym_v1` | `foundry_60_asym_v1` |
| red `movement_deck_id` | `deck.movement.v1` | **`deck.movement.v2`** | `deck.movement.v1` | **`deck.movement.v2`** |
| blue `movement_deck_id` | `deck.movement.v1` | `deck.movement.v1` | `deck.movement.v1` | `deck.movement.v1` |
| red pilot spec | `pilot.llm.qwen35` | `pilot.llm.qwen35` | **`…_berserker_spatial_r1`** | **`…_berserker_spatial_r1`** |
| blue pilot spec | `pilot.llm.qwen35_sniper` | `pilot.llm.qwen35_sniper` | **`…_sniper_spatial_r1`** | **`…_sniper_spatial_r1`** |

This is a clean 2×2 at the configuration level: same arena, same loadouts (`mortar_r30` blue / `machine_gun_dmg16` red), same seed block, one lever varied per axis. **Note the R1 lever is a two-seat manipulation** — it changes *both* pilots' card-programmer specs, not red's alone — so "spatial R1" throughout means "both seats got the R1 prompt treatment."

**Reproduction.** Every figure below is emitted by `scripts/analyze_composition_interaction.py`, which takes the four state roots as arguments:

```
python scripts/analyze_composition_interaction.py \
    --p6 <p6-state-root> --ca <ca-state-root> \
    --r1 <r1-state-root> --comp <comp-state-root>
```

---

## 2. Match-length distributions

Method: `duration_ticks` from each `battery_raw.jsonl` row (sourced from the `MATCH_SCORED` payload). All 30 matches per arm, aborts included, unless a table says otherwise.

| Metric | **P6** (neither) | **CA** (cov_adv) | **R1** (spatial) | **COMP** (both) |
|---|---:|---:|---:|---:|
| n | 30 | 30 | 30 | 30 |
| min | 15 | 22 | 11 | 16 |
| median | 23.00 | 39.50 | 25.50 | 40.00 |
| mean | 23.30 | 39.87 | 27.77 | 47.23 |
| p75 | 27.75 | 48.00 | 31.75 | 56.75 |
| p90 | 29.30 | 57.10 | 38.40 | 78.10 |
| max | 40 | 60 | 52 | **134** |
| sd | 5.65 | 11.48 | 10.07 | 24.72 |
| geometric mean | 22.66 | 38.20 | 26.11 | 41.92 |
| sd(log) | 0.2345 | 0.2944 | 0.3493 | 0.4848 |

Full sorted distributions:

- **P6:** 15, 16, 16, 17, 17, 18, 18, 19, 19, 20, 20, 21, 22, 22, 23, 23, 24, 24, 24, 24, 24, 27, 28, 28, 28, 29, 29, 32, 32, 40
- **CA:** 22, 24, 26, 27, 27, 28, 29, 29, 30, 31, 32, 33, 34, 35, 37, 42, 42, 43, 45, 47, 47, 48, 48, 49, 53, 54, 57, 58, 59, 60
- **R1:** 11, 16, 17, 18, 18, 19, 19, 22, 22, 22, 23, 23, 25, 25, 25, 26, 27, 28, 28, 30, 30, 31, 32, 33, 34, 37, 37, 51, 52, 52
- **COMP:** 16, 16, 22, 23, 28, 29, 31, 31, 32, 33, 33, 35, 35, 36, 37, 43, 46, 48, 51, 52, 53, 53, 58, 59, 64, 68, 78, 79, 94, 134

Non-elimination terminals (all short, all excluded from the elimination-only tables): CA seed 5022 (`provider_semantic_failure`), R1 seed 5008 (`provider_semantic_failure`), COMP seeds 5009 (`aborted`) and 5020 (`provider_semantic_failure`). P6 had none.

---

## 3. Factorial decomposition of match length

Interaction term is `COMP − CA − R1 + P6` on whatever statistic is named.

### 3.1 Additive (raw-tick) scale

| Statistic | P6 | CA | R1 | COMP | ME `cov_adv` | ME `R1` | Additive prediction | **Interaction** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| median | 23.00 | 39.50 | 25.50 | 40.00 | +16.50 | +2.50 | 42.00 | **−2.00** |
| mean | 23.30 | 39.87 | 27.77 | 47.23 | +16.57 | +4.47 | 44.33 | **+2.90** |
| p75 | 27.75 | 48.00 | 31.75 | 56.75 | +20.25 | +4.00 | 52.00 | **+4.75** |
| p90 | 29.30 | 57.10 | 38.40 | 78.10 | +27.80 | +9.10 | 66.20 | **+11.90** |
| max | 40 | 60 | 52 | 134 | +20.00 | +12.00 | 72.00 | **+62.00** |
| sd | 5.65 | 11.48 | 10.07 | 24.72 | +5.83 | +4.42 | 15.90 | **+8.82** |

Elimination-only (aborts dropped; n = 30/29/29/28) moves nothing qualitatively: median interaction **−0.50**, mean **+4.07**, p90 **+10.60**, max unchanged at **+62.00**.

The gradient is the whole story of this table: the interaction term is ~zero at the median, small at the mean, and grows monotonically into the upper quantiles. That is the pattern the SO-COMP-CA document flagged as an open question. Sections 3.2–3.4 test whether it is a real interaction.

### 3.2 Bootstrap intervals on the length interaction

20,000 resamples, matches as the resampling unit, each arm resampled independently.

| Statistic | Interaction (point) | Bootstrap 95% CI | Share of draws ≤ 0 |
|---|---:|---|---:|
| median | −2.00 | [−15.00, +15.00] | 0.561 |
| mean | +2.90 | [−7.23, +13.97] | 0.301 |
| p75 | +4.75 | [−11.00, +21.75] | 0.347 |
| p90 | +11.90 | [−18.40, +40.50] | 0.281 |

**Every interval straddles zero, including p90.** At n=30 per cell this analysis cannot distinguish the composition's length behaviour from a purely additive one. That is a statement about power, not a demonstration of absence — but it does mean the tail cannot be cited as an established interaction.

### 3.3 Log (multiplicative) scale — the levers are cleanly additive here

Match length is a positive, right-skewed duration; the multiplicative scale is the natural one.

| | P6 | CA | R1 | COMP |
|---|---:|---:|---:|---:|
| geometric mean | 22.66 | 38.20 | 26.11 | 41.92 |

- `covered_advance` main effect: **×1.686**
- spatial R1 main effect: **×1.152**
- additive-in-log prediction for the composition: **44.03**; observed **41.92**
- **interaction: ×0.952** (log term −0.0491, SE 0.1311, 95% CI **[×0.736, ×1.231]**, z = **−0.37**)

On the scale where these levers actually operate, the composition is *marginally below* the no-interaction prediction, and indistinguishable from it. The location of the composition distribution needs no interaction term.

### 3.4 Does the no-interaction model reproduce the tail?

This is the question the SO-COMP-CA document left open ("the composition's long right tail is unexplained"). Two nulls, because each has a defect the other repairs.

**(a) Nonparametric surrogate.** Resample one single-lever arm (n=30) and scale it by the *other* lever's estimated log main effect (itself resampled). Two directions, since the surrogate inherits whichever base arm's dispersion.

| Statistic | Observed COMP | Surrogate `CA × exp(ME_R1)` null 95% (median) | P(null ≥ obs) | Surrogate `R1 × exp(ME_CA)` null 95% (median) | P(null ≥ obs) |
|---|---:|---|---:|---|---:|
| median | 40.00 | [33.96, 57.76] (44.70) | 0.744 | [36.04, 53.21] (43.54) | 0.813 |
| mean | 47.23 | [38.03, 55.01] (45.79) | 0.374 | [38.80, 56.43] (46.63) | 0.446 |
| p90 | 78.10 | [52.12, 76.35] (64.29) | **0.014** | [50.92, 96.83] (65.43) | 0.329 |
| max | 134 | [58.43, 79.43] (68.53) | 0.000 | [62.61, 100.23] (87.30) | 0.000 |
| sd(log) | 0.485 | [0.24, 0.33] (0.29) | 0.000 | [0.25, 0.43] (0.34) | 0.001 |
| n > 60 ticks | 6 | [0, 13] (5) | 0.477 | [1, 10] (5) | 0.371 |

**The `max` row of this table is not usable evidence and is printed only so it cannot be quoted as if it were.** A nonparametric bootstrap can never emit a value above `base_max × scale` — 60 × 1.15 = 69.1 and 52 × 1.69 = 87.7 respectively — so P = 0.0000 against an observed 134 is a structural property of the resampling scheme, not a finding. The p90 row is also surrogate-dependent (0.014 one way, 0.329 the other), i.e. not robust.

**(b) Parametric lognormal null with unbounded support**, with both the mean and the variance of `log(length)` taken as additive across levers (μ = 3.7849, geometric mean 44.03; σ = 0.3988). This null *can* produce arbitrarily long matches, which is exactly the defect it exists to repair.

| Statistic | Observed COMP | Null 95% interval (median) | P(null ≥ obs) |
|---|---:|---|---:|
| median | 40.00 | [36.94, 52.48] (44.01) | 0.858 |
| mean | 47.23 | [41.01, 55.05] (47.55) | 0.534 |
| p90 | 78.10 | [57.12, 90.19] (70.82) | 0.201 |
| **max** | **134** | **[71.05, 153.52] (97.82)** | **0.073** |
| **sd(log)** | **0.485** | **[0.29, 0.49] (0.39)** | **0.032** |
| **n > 60 ticks** | **6** | **[2, 11] (6)** | **0.671** |

**Reading this honestly:** under a no-interaction model that scales both location *and* dispersion multiplicatively, a 134-tick match is unremarkable (P = 0.073) and six matches over 60 ticks is the null's own median prediction. The composition arm produced exactly the tail two multiplicative main effects predict. **No statistic falls outside the null's 95% interval** — `sd(log) = 0.485` sits at its extreme upper edge (interval [0.29, 0.49], one-sided P = 0.032), which is one test among ~six reported here with no multiplicity correction, and it drops well inside on removal of the single longest match (0.442) or the two longest (0.419).

**Consequence for the open question.** The SO-COMP-CA document's framing — medians match but means and maxima do not, so "something in the composition produces long matches this arm never produced" — is arithmetically correct but the inference does not follow. **Neither single-lever arm needs to reproduce the composition's tail for the model to be additive.** Multiplying a right-skewed distribution's scale by ~1.9 stretches its tail by ~1.9 as a matter of arithmetic; the 0/90 count above 60 ticks in the other three arms is a consequence of their *lower location*, not evidence that a distinct mechanism is switched on when the levers are stacked.

### 3.5 The tail-count contrast, and why it is weaker than it looks

| Threshold | COMP | Pooled P6+CA+R1 |
|---|---:|---:|
| > 40 | 15/30 | 18/90 |
| > 45 | 14/30 | 14/90 |
| > 50 | 12/30 | 9/90 |
| > 55 | 8/30 | 4/90 |
| > 60 | 6/30 | **0/90** |
| > 70 | 4/30 | 0/90 |
| > 80 | 2/30 | 0/90 |

Fisher exact, two-sided, 6/30 vs 0/90 above 60 ticks: **p = 0.00016**. This is a real and clean separation *of the composition from the other three arms*, and it is the strongest-looking number in this document. It is also **not a test of interaction**: it compares the composition against arms with a lower location, so a pure main-effects model predicts the same separation. §3.4(b) is the test that holds location constant, and it returns P = 0.671 for this exact statistic. The 60-tick threshold was additionally chosen *after* seeing the data (it is the maximum of the pooled other arms); the sweep is printed so the choice is visible rather than hidden.

---

## 4. Out-of-range fire — where a real interaction does show up

Method: red-seat `weapon_fire_rejected` with `reason = target_out_of_range`, over red's total fire attempts (`weapon_fired` + all `weapon_fire_rejected`), from `events.sqlite3`, filtered to the 30 valid matches. This reproduces each arm's published figure exactly (P6 0.7781, CA 429/585 = 0.7333, R1 212/313 = 0.6773, COMP 436/570 = 0.7649), which is the cross-check that the extraction is the same one those documents used.

| | P6 | CA | R1 | COMP |
|---|---:|---:|---:|---:|
| out-of-range / attempts | 263/338 | 429/585 | 212/313 | 436/570 |
| fraction | 0.7781 | 0.7333 | 0.6773 | **0.7649** |

- `covered_advance` main effect: **−0.0448**
- spatial R1 main effect: **−0.1008**
- additive prediction for the composition: **0.6325**
- observed: **0.7649**
- **interaction: +0.1324**, cluster bootstrap (matches as the unit, numerator/denominator resampled together) 95% CI **[+0.0118, +0.2556]**, share of draws ≤ 0 = **0.017**

A per-match mean-of-fractions variant (which weights every match equally instead of every shot) gives a smaller but same-signed term: **+0.1114**.

**Statement:** this is the one endpoint in the analysis whose interaction interval excludes zero. It is **antagonistic / sub-additive**: each lever alone reduces red's out-of-range fire, and stacked they recover almost all of it (0.7649 vs a 0.7781 no-lever floor — a net effect of only −1.3 pp from two levers worth −14.6 pp additively). The mechanistic reading consistent with this — **R1's in-range flags stop binding once `covered_advance` is in red's movement deck** — is a hypothesis this decomposition supports directionally, not a demonstrated mechanism.

**Caveats that apply specifically here.** (i) One nominal p-value, uncorrected, among several endpoints; the lower bound is +0.012, i.e. barely off zero. (ii) The endpoint is a rate over clustered observations and the four denominators differ by a factor of ~1.9 (313 to 585); the cluster bootstrap addresses the clustering but not the differing exposure. (iii) A rate whose denominator is itself an outcome (attempts scale with match length, which the levers also move) is not a clean endpoint — this is a compositional artefact risk, not a resolved one.

---

## 5. Which matches form the composition tail

Tail defined as **longer than any single-lever or floor arm ever produced** (> 60 ticks): **6 matches, seeds 5003 (68), 5006 (78), 5010 (134), 5015 (64), 5022 (79), 5030 (94).**

| Per-match mean | **TAIL** (n=6) | **REST** (n=24) |
|---|---:|---:|
| ticks | 86.2 | 37.5 |
| tick of first landed hit | 60.3 | 27.8 |
| tick of first close (mechs within 12 grid units) | 55.5 | 31.3 |
| red fire attempts | 34.7 | 15.1 |
| red out-of-range fraction | 0.798 | 0.769 |
| **total hits landed (both seats)** | **3.33** | **3.12** |
| hits per tick | 0.0408 | 0.0839 |
| blue zero-hit-probability shots | 11.33 | 2.54 |
| **`covered_advance` share of red's programmed registers** | **0.231** | **0.244** |
| blue wins | 3/6 | 7/24 |

**What distinguishes them is time-to-contact, and nothing else that was measured.**

- **Total hits landed is flat** (3.33 vs 3.12), and it is flat across all four arms too (P6 3.17, CA 3.10, R1 3.07, COMP 3.39). At ×16 red damage, ~3 landed hits ends a match regardless of condition. Match length is therefore near-equivalent to *time until those hits land*, not to attrition depth.
- Within the composition arm, `r(length, tick of first landed hit) = +0.883`; `r(length, total hits) = +0.160`. (P6 +0.694 / +0.168; CA +0.324 / +0.430; R1 +0.272 / −0.053.)
- **The tail is not "more `covered_advance`."** Red's `covered_advance` share of programmed registers is **0.231 in the tail vs 0.244 in the rest** — flat, slightly lower. Nothing about card selection marks these matches out. This is a direct negative for the intuitive "the tail is matches where red leaned hardest on the cover card" story.
- Blue's behaviour in the tail is a symptom of the delay, not obviously a cause: 11.3 zero-hit-probability shots per match vs 2.5, i.e. blue spending its mortar on shots the resolver already scores at p(hit)=0 while the two mechs are still far apart.
- Blue wins 3/6 in the tail vs 7/24 elsewhere. n=6; not tested; noted only because the three longest matches (5010, 5030, 5022) are all blue wins.

**The longest match, concretely.** Seed 5010 (134 ticks): red traverses from (4,30) to (45,9) to (33,56) over 59 resolved moves; the mechs first come within 12 units at tick 42, but the first landed hit is at tick **107** — 65 ticks of intermittent proximity with no conversion — then the match resolves in 27 more ticks. It has 4 landed hits total, 1 `llm_completion_failed`, and terminates cleanly as `last_mech_standing`. It is a genuine slow match, not a harness stall or an abort.

### 5.1 Phase decomposition — the residual interaction is entirely pre-contact

Length split into three phases on elimination matches that both close and land a hit: **close** (start → first sub-12-unit separation), **convert** (close → first landed hit), **finish** (first landed hit → end).

| Arm | n | close | convert | finish |
|---|---:|---:|---:|---:|
| P6 | 27 | 16.30 | −0.59 | 8.19 |
| CA | 26 | 26.08 | +2.04 | 12.27 |
| R1 | 28 | 19.50 | −1.54 | 10.39 |
| COMP | 25 | 37.08 | +0.44 | 14.56 |

| Phase | ME `cov_adv` | ME `R1` | **Interaction** |
|---|---:|---:|---:|
| close | +9.78 | +3.20 | **+7.80** |
| convert | +2.63 | −0.94 | **−0.66** |
| finish | +4.08 | +2.21 | **+0.08** |

(A negative `convert` mean simply means the first landed hit often precedes the first sub-12 close — long-range mortar fire connects before the mechs converge.)

Whatever residual non-additivity exists in match length lives **entirely in the closing phase**. Both levers independently slow the approach; stacked, the approach is slower still than additivity predicts. Bootstrap on this subset (matches as the unit):

| Component | Interaction (point) | Bootstrap 95% CI | Share ≤ 0 |
|---|---:|---|---:|
| pre-contact (start → first landed hit) | +7.14 | [−1.38, +16.73] | 0.052 |
| post-contact (first landed hit → end) | +0.08 | [−8.31, +8.12] | 0.490 |
| total length | +7.22 | [−3.45, +19.14] | 0.104 |

**Two cautions attach to this table and both matter.** (i) It is computed on a *subset* — matches that both close to within 12 units and land a hit (n = 27/26/28/25) — which drops 3–5 matches per arm including all the aborts. That is a different estimand from §3's full-sample analysis, which is why the total-length interaction here (+7.22) is larger than §3's (+2.90 across all 30, +4.07 elimination-only); the subset is not a corrected version of §3 and must not be quoted as one. (ii) Even on this more favourable subset the pre-contact interval still includes zero (share ≤ 0 = 0.052). This is the closest any length-derived interaction in the analysis gets to separating from zero, and it still does not.

---

## 6. Win rate — reported, not read

Decided-match red (brawler) win rate, aborts excluded:

| | P6 | CA | R1 | COMP |
|---|---:|---:|---:|---:|
| red wins / decided | 17/30 | 20/29 | 19/29 | 18/28 |
| rate | 0.5667 | 0.6897 | 0.6552 | **0.6429** |

Main effects +0.1230 (`cov_adv`) and +0.0885 (R1), additive prediction 0.7782, **interaction −0.1353**, parametric bootstrap 95% CI **[−0.480, +0.212]**. The interval spans almost 0.7 of probability space. **This endpoint carries no information at these sample sizes** and is included only so it cannot later be quoted selectively in either direction.

---

## 7. Telemetry gap found while doing this

`plan_committed.spatial_read` is **null in 100% of plans in every arm, including the R1-only arm** (0/302 P6, 0/500 CA, 0/358 R1, 0/590 COMP). The spatial R1 lever leaves **no marker whatsoever in the event ledger**. Its presence is verifiable only from the overlay's `pilot_spec_id`, which is a *configuration* fact, not a *runtime* one.

Practical consequence: for the `covered_advance` lever there is a runtime uptake receipt (the card appears in `hand_dealt.card_ids` and in `plan_committed.registers`; red programmed it in 24.2% of composition registers), so "the lever engaged" is provable from the ledger. For spatial R1 there is no equivalent — an arm that silently failed to apply the R1 pilot spec would produce a ledger indistinguishable from one that applied it. That is a live attribution weakness in every R1-bearing arm in this program, this one included, and it is worth closing before any further R1 decomposition is run.

---

## 8. Limitations

1. **Observational decomposition, not a designed factorial.** Four arms run at different times (P6 and COMP on 2026-07-24, CA and R1 on 2026-07-25), against the same shared vLLM endpoint but not in a randomised or interleaved order. Any drift in the served model or endpoint between 07-24 and 07-25 is confounded with the factorial contrast, and there is no way to separate it from these ledgers.
2. **No pre-registered criterion.** Nothing here was declared before the numbers were seen. Section 3.5's 60-tick threshold is explicitly post-hoc. Multiple endpoints are examined (length location, length dispersion, tail counts, out-of-range, win rate, phase durations) with no multiplicity correction; the one nominally-significant interaction (§4) would not survive a Bonferroni adjustment across the ~6 primary endpoints reported.
3. **n=30 per cell.** The interaction term is a difference of four estimates, so its variance is roughly four times a single-arm estimate's. Nothing in the length analysis had the power to detect a moderate interaction; "no interaction detected" here means "not distinguishable at n=30," not "interaction absent."
4. **Blue standoff configuration (OMN-15119 class).** All four arms hold blue on the `mortar_r30` long-range loadout against red's short-range `machine_gun_dmg16`, on `foundry_60_asym_v1`. This is precisely the geometry in which "match length" is dominated by red's approach, which is why the close phase carries the whole signal in §5.1. Conclusions about how these levers interact are **conditional on that standoff configuration** and do not transfer to a symmetric-range or short-range pairing without re-measurement. The `SO-RANGECAP` / `SO-STANDOFF` arms establish that range configuration is itself a live and material axis.
5. **Seed pairing is not usable.** Although all four arms ran seeds 5001–5030, the rank correlation of match length between arms is nil (Spearman ρ: P6–CA −0.075, P6–R1 −0.174, P6–COMP −0.132, CA–R1 −0.201, CA–COMP −0.234, R1–COMP +0.202). Seed 5010 is 134 ticks in the composition and 23 / 23 / 54 in P6 / R1 / CA. Different decks and prompts consume the RNG stream differently, so a seed does not name a comparable scenario across arms; all comparisons here are unpaired between-arm comparisons, and the tail seeds are **not** intrinsically long matches.
6. **Single model, single arena, single dose.** Qwen3.6-35B-A3B both seats, `foundry_60_asym_v1`, ×16 red damage. Everything above is a statement about that one cell of a much larger space.
7. **`sd(log)` as the surviving anomaly rests on ~2 matches.** The composition's dispersion excess is the closest any statistic comes to the edge of a no-interaction null band — and it is still *inside* it (0.485 vs an upper bound of 0.49). Dropping seed 5010 alone takes it to 0.442, and 5010 + 5030 to 0.419. It is a lead worth a properly-powered arm, not a result.

---

## 9. What would actually settle it

Stated as options, not a commitment, and none of them was run here:

- **Power.** Detecting a length interaction of the observed mean size (~+3 ticks) against the observed spread needs roughly n ≥ 150–200 per cell, not 30. A tail/dispersion interaction needs more. The honest read of §3.2 is that this factorial was never powered for the question it is being asked.
- **A pre-registered dispersion endpoint.** If the composition's over-dispersion is the real claim, it should be declared as the primary endpoint *before* the arm runs, with the no-interaction lognormal null of §3.4(b) as the pre-registered comparator.
- **Runtime telemetry for the R1 lever** (§7) — an in-ledger receipt that the spatial prompt was applied, so R1-bearing arms have the same uptake proof `covered_advance` already has.
- **A range-configuration control** for the OMN-15119 class: repeat the 2×2 at a symmetric or reduced blue range and check whether the out-of-range interaction of §4 survives when the approach phase is not dominant.

---

## Appendix — sources

- Raw ledgers: `.onex_state/steel_onslaught/{pair_p6_dmg16, composition_ca_only_dmg16, composition_r1_only_dmg16, composition_p6dmg16_covadv_r1}` — `events.sqlite3` + `battery_raw.jsonl` (30 rows each, seeds 5001–5030), in the `SO-COMP-P5` (`steel_onslaught_p6`, `steel_onslaught_comp16`), `SO-COMP-CA`, and `SO-COMP-R1` worktrees respectively.
- Analysis code: `scripts/analyze_composition_interaction.py` (this PR). Deterministic — bootstrap seed 20260725 pinned in the module.
- Overlays inspected for factorial cleanliness: `contracts_data/overlays/tactical_split_overdeal_utility_asym_{pair_p6_dmg16, composition_ca_only_dmg16, composition_r1_only_dmg16, composition_p6dmg16_covadv_r1}_qwen.yaml`.
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md`, `docs/evidence/2026-07-25-composition-ca-only-dmg16-battery.md`, `docs/evidence/2026-07-25-composition-r1-only-dmg16-battery.md`, `docs/evidence/2026-07-24-composition-p6dmg16-covadv-r1-battery.md`, `docs/evidence/2026-07-24-composition-p4dmg8-covadv-r1-battery.md`.
- Merge provenance: `93aaa43` (P6, #191), `a894ad2` (CA, #202), `6c34db9` (R1, #200), `37ab224` (COMP, #193).
