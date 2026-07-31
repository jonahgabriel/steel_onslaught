# OMN-15488 L-GATE-2 decisive learning-effect battery — pre-registered SCORING (DRAFT) — 2026-07-31

**Verdict: PRIMARY — NOT-SUPPORTED. CONFIRMATORY-SECONDARY (vent) — DIRECTIONAL-ONLY.** `D_ws = -0.00342`
(post mean 0.580853 < baseline mean 0.584278) — the primary lands in **NOT-SUPPORTED** on the `D_ws <= 0` clause
alone, before the p-value is even relevant (one-sided Welch `t = -0.5707`, `df = 57.644`, `p = 0.7148`, testing the
declared UP direction). The vent keep-rate moved in the twice-replicated paradoxical direction (`D_vent = +0.01960`,
`t = 1.5047`, `df = 38.289`, one-sided `p = 0.0703`) but **does not clear alpha = 0.05**, landing
**DIRECTIONAL-ONLY**, not CONFIRMED.

**Pre-declared interpretation-map consequence for this exact band pair (NOT-SUPPORTED / DIRECTIONAL-ONLY).** The
header's interpretation map has three primary-crossed-with-vent rows (SUPPORTED any-vent; NOT-SUPPORTED+CONFIRMED;
NOT-SUPPORTED+NOT-CONFIRMED) plus one closing clause: *"DIRECTIONAL-ONLY outcomes -> reported as unresolved; the
terminal/non-terminal call is NOT made from an unresolved band."* This run's vent result is DIRECTIONAL-ONLY, so
none of the three named rows apply and the closing clause governs: **this battery does NOT license the TERMINAL
call for the prompt-guidance mechanism, and does NOT license the "proven paradoxical channel, defect in wording"
call either.** Both readings remain open. This is a materially weaker outcome than either of the two clean rows the
pre-registration anticipated, and it is reported as such rather than rounded to the nearer-sounding one.

**The regime-contrast headroom argument does not hold up on its own terms, with one important caveat disclosed
up front.** This battery ran the maximally favorable contrast the prompt-guidance mechanism could offer — genesis
0.5 vs promoted 2.5, spanning both named endpoint regimes, a 4x larger step than #128's blue-seat rerun (1.0->1.5,
step 0.5). If dose-responsiveness scales with contrast size, the vent effect here should be *at least* as strong as
#128's (`d ~= 0.51`, `p = 0.053`, n=30). It is not: `d = 0.389`, `p = 0.070` — both weaker, on the endpoint contrast
that was supposed to give the mechanism its best shot. **The caveat:** #128's `d=0.51` figure was measured on the
BLUE (sniper) seat, not RED (berserker) — this battery, via the mirror pairing, is the first-ever *scored* vent
(or primary) contrast on the red seat at all, so the comparison below crosses seat/persona as well as step size.
See §5.1 for the full disclosure and why the finding still stands as a real negative, just not a clean isolated
step-size test.

---

**Scope.** This is the **scoring** document — the pre-registered analysis and nothing else, computed exclusively
from `battery_raw.jsonl`, never `battery_summary.json` (see the note below). **Note on `battery_summary.json`:**
it is not read anywhere in this document. A spot-check found its `mean_planned_share.vent` field uses a
present-key-only denominator (2 baseline / 5 post matches instead of 30) and is not usable for per-phase shares —
a driver summary defect worth a follow-up note, not a lane defect. **Gates** (contamination,
timing, manipulation-landed, canary disposition) are cited below with what this document independently verified,
but the full Gates/acceptance phase for this battery is a separate deliverable and its results are **merged in at
the landing phase**, not authored here. Do not read this document as a substitute for that phase.

**Artifacts.** `SNAP` = `~/.omnibase/battery_envs/omn15488-hermetic-20260730`; `ROOT` =
`$SNAP/battery_state/omn15488_learning_battery_r2` (the executing, non-abandoned state-root — see §0c). All figures
below are computed from `$ROOT/battery_raw.jsonl` (61 rows) and cross-checked against `$ROOT/events.sqlite3`
(opened `?immutable=1`).

**Model / binding:** `onex_delegation`, backend `local-coder-mlx` (served `mlx-community/Qwen3.6-35B-A3B-8bit` at
`stickybeatz-studio:8401`). Learning seat `player.red` (berserker), mirror opponent `player.blue` (same berserker
chassis). Card mode. n=30 baseline (seeds 4001-4030), promote budget 15 (seeds 4101-4115, promoted on the first
attempt, seed 4101), n=30 post (seeds 4201-4230).

---

## 0. Pre-registration

The pre-registration lives in the header of
`contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml`. Not one character of the hypothesis,
the endpoint definitions, the decision bands, the escapes, the multiplicity note, the interpretation map, or the
tertiary-descriptives clause was edited by this session. The original pre-registration commit (`ff5df34`) already
carried Amendment 1 (client contract-selection fixes); two further execution-infrastructure amendments — a
state-root correction and per-seed containment — were appended after that commit and before any scored match; none
touched the scored criteria. See §0c.

### 0a. Operative clauses, quoted verbatim

> **PRIMARY ENDPOINT** (the L-GATE-2 declared-direction question). For the learning seat (player.red) only, per
> match: `ws = (planned attack + planned special) / (total planned cards)`, defined when total planned > 0 (a
> match with zero planned cards is excluded from the primary and COUNTED in the scoring doc; expected occurrences:
> zero). Then `D_ws = mean(ws | post, n=30) - mean(ws | baseline, n=30)`, tested with a one-sided Welch t
> (direction: UP), alpha = 0.05.
>
> **DECISION BANDS** (exhaustive, no discretionary region):
> `SUPPORTED — D_ws > 0 AND p < 0.05 -> H_POLICY_DOSE_RESPONSIVE.`
> `DIRECTIONAL-ONLY — D_ws > 0 AND p >= 0.05 -> unresolved at this n; reported as such, NOT as support.`
> `NOT-SUPPORTED — D_ws <= 0.`

> **CONFIRMATORY-SECONDARY ENDPOINT** (the paradoxical channel's first pre-registered test). Per match, learning
> seat vent keep-rate (`planned vent / dealt vent`, defined when dealt vent > 0): `D_vent = mean(vent keep | post)
> - mean(vent keep | baseline)`, one-sided Welch t (direction: UP — the twice-replicated direction), alpha = 0.05.
> Bands: `CONFIRMED (D_vent > 0, p < 0.05) / DIRECTIONAL-ONLY / NOT-CONFIRMED (D_vent <= 0)`. The baseline vent
> floor (0.0 in #128) does not block this endpoint — UP from the floor is the most sensitive configuration for it.

> **MULTIPLICITY**, stated plainly: two pre-registered endpoints, each at alpha 0.05, testing DIFFERENT hypotheses
> (declared-direction vs paradoxical channel); no family-wise correction is applied and the scoring document must
> present both p-values uncorrected and say so. **[Both p-values above are uncorrected. No family-wise correction
> was applied to either.]**

> **PRE-DECLARED INTERPRETATION MAP** (scored bands -> program consequence):
> `primary SUPPORTED (any vent outcome) -> dose-responsiveness at regime contrast; L-GATE-2 behavioral half PASSES
> at this operating point; step-size sensitivity becomes the follow-up.`
> `primary NOT-SUPPORTED + vent CONFIRMED -> the guidance block IS causally consumed but the declared semantics are
> the defect (#128 revisit item (a): wording), NOT the learning chain; behavioral half remains FAILED as declared,
> with a proven paradoxical channel.`
> `primary NOT-SUPPORTED + vent NOT-CONFIRMED -> H_POLICY_INERT stands at the mechanism's most favorable operating
> point; TERMINAL for the prompt-guidance mechanism; the program moves to a non-prompt consumer (#128 revisit item
> (c)). No fourth step-size battery.`
> `DIRECTIONAL-ONLY outcomes -> reported as unresolved; the terminal/non-terminal call is NOT made from an
> unresolved band.`

> **PRE-DECLARED ESCAPES** (unclamped, reported rather than folded in):
> `NO-PROMOTION — the promote phase exhausts its 15-match budget without a POLICY_PROMOTED event... the finding is
> reported as "L-GATE-2 not exercised at this pairing/binding"...` **[did not occur — promoted on the first
> attempt, seed 4101; see §1b.]**
> `CEILING — baseline mean ws >= 0.95: the primary contrast has no arithmetic headroom; raw distributions are
> reported, the primary is not scored, and the vent endpoint is still scored...` **[did not occur — baseline mean
> ws = 0.584278, far below 0.95; primary IS scored normally; see §1.]**

> **TERTIARY DESCRIPTIVES** (reported, never gating): remaining per-category keep-rates and planned shares
> (movement predicted DOWN under dose-responsiveness); `llm_completion_failed` rate parity across phases
> (execution-infrastructure check on the retry belt, not a hypothesis metric); per-phase win counts (the mirror
> pairing makes win-rate itself uninformative about the hypothesis).

> **STATISTICAL HONESTY.** n=30 per phase with a one-sided Welch t at alpha 0.05 has ~80% power for a standardized
> effect of d ~= 0.65 per endpoint. A true effect smaller than that will likely land DIRECTIONAL-ONLY; that outcome
> is a power statement, not evidence of absence, and the scoring document must say so rather than upgrade or
> downgrade a band. For calibration: the replicated vent signal's observed sizes were `d ~= +0.5` (#128) and larger
> (#126, n=10) — near this battery's detection floor.

### 0b. Timing gate — run against the executing state-root, exit 0

```
$ python3 scripts/check_preregistration_timing.py \
    --state-root $ROOT \
    --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml
Pre-registration commit:    a3b0d8aa7f7392942f6d78c47bf7f98247c63d09
  author timestamp:         2026-07-31T03:39:43-04:00   (load-bearing)
First match_started:        2026-07-31T07:50:26.322742+00:00
Gap (match_started - author date): 0:10:43.322742

OK: pre-registration commit's author timestamp precedes the first match_started.
EXIT=0
```

**The margin is thin — 10m 43s** — because `a3b0d8a` is Amendment 3 (per-seed containment, the fix that let the r2
run complete at all), landed same-morning as the run. This gate's "latest touch" rule is designed exactly to catch
this: the amendment is execution-infrastructure only (its own text says so, verbatim, quoted in the overlay) and
touches nothing in the criterion region (hypothesis, endpoints, bands, escapes, interpretation map — all unchanged
since the original `ff5df34` pre-registration), but the gate still correctly requires it to precede the run because
it is the commit that shipped the driver code the run actually executed. **This is a real, independently-run gate
result, not a citation of a future phase's number** — included here because it is cheap, mechanical, and load-
bearing for trusting that no criterion was edited after seeing results. The broader Gates/acceptance
document (contamination-orphan class reconciliation, canary disposition narrative, manipulation-landed check) is
the separate deliverable referenced in Scope above.

### 0c. Abandoned first attempt — disposed, contributes nothing

The originally-launched run (state-root `$SNAP/battery_state/omn15488_learning_battery`, no `_r2` suffix) crashed
at baseline seed 4028 after 27 clean rows — independently confirmed here: `wc -l` on that state-root's
`battery_raw.jsonl` returns **27**, seeds 4001-4027, no seed 4028 or beyond. That lane is preserved untouched and
**zero rows from it are read by this document.** The battery re-ran `--fresh` in `omn15488_learning_battery_r2`
under Amendment 3's per-seed-containment fix, which is the state-root scored throughout this document. A separate
n=1 quarantined canary (`omn15488_canary`, seeds 9001/9002 per Amendments 1-2's narrative) is likewise excluded —
it is not part of any scored phase and this document does not read it.

---

## Method

Every figure below is computed directly from `$ROOT/battery_raw.jsonl`'s 61 rows using pure-stdlib Python (no
`battery_summary.json` read at any point). The Welch t/p implementation (Welch–Satterthwaite df, one-sided p via
the regularized incomplete beta function) was validated against the header's own reference values before being
trusted on this data:

```
t=2.0,  df=60 -> two-sided p = 0.050033   (reference: .0500)
t=3.15, df=18 -> two-sided p = 0.005538   (reference: .0055)
```

and cross-checked against `scipy.stats.t.sf` on the two scored endpoints' actual (t, df) pairs — agreement to
12 significant figures (`0.7147788549455135` vs `0.7147788549455151`; `0.07030566439850539` vs
`0.0703056643985075`). Full commands in §6.

**Independent ledger cross-check (not required by the pre-registration, run anyway because it is cheap and it is
the strongest available proof the raw file was not hand-edited or truncated):** `battery_raw.jsonl`'s per-row
`dealt`/`planned` category counts, summed over all 61 scored `match_id`s, are reproduced **exactly** from
`events.sqlite3`'s own `hand_dealt`/`plan_committed` event payloads for `seat=red`:

| | dealt (ledger) | dealt (raw sum) | planned (ledger) | planned (raw sum) |
|---|---:|---:|---:|---:|
| attack | 1913 | 1913 | 1913 | 1913 |
| movement | 2976 | 2976 | 1545 | 1545 |
| special | 534 | 534 | 252 | 252 |
| vent | 529 | 529 | 10 | 10 |

61/61 `match_started` events in the ledger have a matching `battery_raw.jsonl` row and vice versa (bijective, zero
orphans) — this run produced no withheld-match casualties and needed no makeup invocation. `empty_content_completions`
is `{}` on all 61 rows, `replay_validity` is `{player.red: 1, player.blue: 1}` on all 61 rows. Seed ranges and
generation/policy-id provenance are exactly as pre-registered: all 30 baseline rows carry seeds 4001-4030,
`policy_provenance.generation == 0`, `policy_id == policy.aggressive.genesis`; all 30 post rows carry seeds
4201-4230, `generation == 1`, `policy_id == policy.aggressive.31d9f8ceb1e3a5b6` (the promoted policy — see §1b);
the promote row carries seed 4101, `generation == 0` (pre-promotion provenance) with a `policy_promoted` payload
recording the transition to generation 1.

---

## 1. PRIMARY — the scored criterion

| Quantity | baseline (n=30) | post (n=30) |
|---|---:|---:|
| mean `ws` | 0.584278 | 0.580853 |
| sd `ws` | 0.022310 | 0.024138 |
| median `ws` | 0.583333 | 0.580000 |
| min / max `ws` | 0.523077 / 0.630769 | 0.533333 / 0.644444 |
| matches with total planned = 0 (excluded) | **0** | **0** |

```
D_ws  = mean(ws | post) - mean(ws | baseline) = 0.580853 - 0.584278 = -0.003425
t     = -0.570669   (one-sided Welch, direction UP)
df    = 57.644039   (Welch-Satterthwaite)
p     = 0.714779    (P(T > t), i.e. P(post > baseline))
Cohen's d (post - baseline, pooled sd) = -0.147346
```

**Decision.** `D_ws = -0.003425 <= 0` -> **NOT-SUPPORTED**, by the band's own first clause — the p-value does not
change this band (it is reported for completeness and because the header asks for `t`/`df`/`p` on every endpoint,
not because it is decision-relevant here). Baseline mean ws is 0.584278, well under the 0.95 CEILING threshold, so
the CEILING escape does not apply and this is a normally-scored NOT-SUPPORTED, not an unscored ceiling case.

**Direction, stated plainly.** The point estimate moved in the direction *opposite* the declared semantics: the
learning seat committed a slightly *smaller* share of attack+special cards after promotion to the high-aggression
policy than at genesis. The magnitude is small (`d = -0.15`) and the interval is wide relative to it (`p = 0.71` —
far from resolving even a null read with confidence), but the sign is unambiguous and is reported as scored, not
softened.

### 1a. Sorted per-match `ws` vectors (primary), by seed

**Baseline (sorted ascending, n=30):**

| ws | seed | | ws | seed | | ws | seed |
|---:|---:|---|---:|---:|---|---:|---:|
| 0.523077 | 4006 | | 0.573333 | 4027 | | 0.584615 | 4026 |
| 0.553846 | 4007 | | 0.580000 | 4008 | | 0.585714 | 4012 |
| 0.555556 | 4003 | | 0.580000 | 4020 | | 0.600000 | 4005 |
| 0.563636 | 4004 | | 0.580000 | 4029 | | 0.600000 | 4011 |
| 0.566667 | 4025 | | 0.581818 | 4013 | | 0.600000 | 4019 |
| 0.569231 | 4002 | | 0.583333 | 4014 | | 0.600000 | 4022 |
| 0.569231 | 4016 | | 0.583333 | 4015 | | 0.600000 | 4023 |
| 0.569231 | 4030 | | 0.584615 | 4001 | | 0.600000 | 4028 |
| 0.571429 | 4018 | | 0.584615 | 4017 | | 0.611111 | 4009 |
| — | — | | — | — | | 0.618182 | 4010 |
| — | — | | — | — | | 0.625000 | 4021 |
| — | — | | — | — | | 0.630769 | 4024 |

**Post (sorted ascending, n=30):**

| ws | seed | | ws | seed | | ws | seed |
|---:|---:|---|---:|---:|---|---:|---:|
| 0.533333 | 4225 | | 0.573333 | 4216 | | 0.583333 | 4211 |
| 0.542857 | 4209 | | 0.573333 | 4229 | | 0.583333 | 4228 |
| 0.550000 | 4215 | | 0.575000 | 4204 | | 0.584615 | 4224 |
| 0.553846 | 4222 | | 0.575000 | 4219 | | 0.584615 | 4230 |
| 0.557143 | 4206 | | 0.580000 | 4214 | | 0.600000 | 4201 |
| 0.560000 | 4208 | | 0.580000 | 4217 | | 0.600000 | 4202 |
| 0.563636 | 4210 | | 0.581818 | 4205 | | 0.600000 | 4203 |
| 0.563636 | 4226 | | — | — | | 0.600000 | 4207 |
| 0.569231 | 4227 | | — | — | | 0.600000 | 4218 |
| 0.571429 | 4212 | | — | — | | 0.600000 | 4223 |
| — | — | | — | — | | 0.616667 | 4221 |
| — | — | | — | — | | 0.625000 | 4220 |
| — | — | | — | — | | 0.644444 | 4213 |

Note the distributions overlap almost completely (baseline range 0.5231-0.6308, post range 0.5333-0.6444); post's
tails are marginally fatter in both directions (lower low, higher high) but the central mass sits in the same band.

### 1b. Promotion phase — NO-PROMOTION escape did not trigger

The promote phase is not part of either scored contrast (it exists only to advance the chain from generation 0 to
generation 1) but is reported here because the NO-PROMOTION escape hinges on it. `policy_promoted` fires on the
**first** promote-phase match, seed 4101 (budget was 15 attempts, seeds 4101-4115) — `policy.aggressive.genesis`
(gen 0, `spec_hash 0b6bd757...`) promotes to `policy.aggressive.31d9f8ceb1e3a5b6` (gen 1, `spec_hash
31d9f8ce...`), `evidence_scored_event_id 01KYVVH3N12QZEJPH5BCVEYBK2`, winner `player.red` (a decisive win with
positive damage differential, per `win_damage_differential_v1`'s stated promotion condition). The **NO-PROMOTION
escape does not trigger**: L-GATE-2 was exercised at this pairing/binding, and the post phase's 30 rows all carry
`policy_provenance.generation == 1` and `policy_id == policy.aggressive.31d9f8ceb1e3a5b6` (§Method), confirming the
chain froze at generation 1 as the pre-registration specifies.

---

## 2. CONFIRMATORY-SECONDARY — vent keep-rate

| Quantity | baseline (n=30) | post (n=30) |
|---|---:|---:|
| mean vent keep | 0.007037 | 0.026641 |
| sd vent keep | 0.026820 | 0.066131 |
| matches with dealt vent = 0 (excluded) | **0** | **0** |
| matches with vent keep = 0 | 28 / 30 | 25 / 30 |

```
D_vent = mean(vent keep | post) - mean(vent keep | baseline) = 0.026641 - 0.007037 = +0.019604
t      = 1.504681   (one-sided Welch, direction UP)
df     = 38.288517  (Welch-Satterthwaite)
p      = 0.070306   (P(T > t), i.e. P(post > baseline))
Cohen's d (post - baseline, pooled sd) = +0.388507
```

**Decision.** `D_vent = +0.019604 > 0` but `p = 0.070306 >= 0.05` -> **DIRECTIONAL-ONLY**, not CONFIRMED. The
direction replicates #126/#128's paradoxical signal a third time, but this pre-registered test — the first formal
one that signal has received — does not clear alpha.

### 2a. Sorted per-match vent keep-rate vectors, by seed

**Baseline (n=30):** 28 rows at exactly 0.0 (seeds 4002,4003,4004,4005,4006,4007,4008,4009,4010,4011,4012,4013,
4014,4015,4016,4017,4018,4019,4020,4021,4023,4024,4025,4026,4027,4028,4029,4030), then 0.100000 (seed 4001),
0.111111 (seed 4022).

**Post (n=30):** 25 rows at exactly 0.0 (seeds 4201,4202,4203,4206,4207,4208,4209,4210,4212,4213,4214,4215,4216,
4217,4218,4219,4220,4221,4223,4224,4225,4226,4227,4229,4230), then 0.090909 (seed 4204), 0.111111 (seed 4228),
0.125000 (seed 4205), 0.222222 (seed 4222), 0.250000 (seed 4211).

The distribution is floor-crowded in both phases (as #128 found at genesis 1.0), but post has both more nonzero
matches (5 vs 2) and higher nonzero values (max 0.250 vs max 0.111) — the mean shift is real in the data, not an
artifact of one outlier: dropping the single largest post value (seed 4211, 0.250) still leaves post's mean above
baseline's (`(0.799242 - 0.25)/29 = 0.018939` vs baseline `0.007037`).

---

## 3. Gates — cited, not re-litigated here

Per Scope: the full Gates/acceptance phase for this battery (contamination-orphan reconciliation if any, canary
disposition narrative, manipulation-landed / delegation-contract-selection proof) is a separate deliverable and its
results are merged in at landing. What this document independently ran or verified, and is safe to cite now:

- **Pre-registration timing gate: PASS, exit 0**, margin +10m 43s against the executing commit `a3b0d8a` — §0b.
- **Row/ledger bijection**: 61/61 `match_started` <-> `battery_raw.jsonl` rows, zero orphans, zero makeup
  invocations needed for this (`_r2`) run — §Method. This is the load-bearing fact for treating this specific run
  as contamination-clean, though it is not the same thing as running `check_contamination_gate.py` (that script is
  built for a single seed-base/n pair and this battery has three phases with different seed bases/n — baseline
  4001+30, promote 4101+budget-15, post 4201+30 — so it was not force-fit here; the seed-range/generation/policy-id
  checks in §Method and §1c serve the same purpose for this multi-phase battery).
- **Abandoned-attempt disposal**: independently confirmed (27 rows, seeds 4001-4027, dies before 4028) in the
  non-`_r2` state-root — §0c.
- **Ledger arithmetic cross-checks**: `llm_completion_requested = resolved + failed` closes exactly on all three
  phases (§4.3); `dealt`/`planned` category sums reproduce exactly from raw ledger events (§Method).

Not re-run here (explicitly deferred to the landing-phase Gates document): the manipulation-landed proof that every
post-phase prompt actually carried the promoted-generation guidance text, and the canary (`omn15488_canary`)
disposition writeup referenced in Amendments 1-2.

---

## 4. TERTIARY descriptives (reported, never gating)

### 4.1 Per-category keep-rates

| category | baseline mean | post mean | D (post - baseline) | predicted direction under dose-response |
|---|---:|---:|---:|---|
| attack | 1.000000 | 1.000000 | 0.000000 | (in primary numerator) |
| special | 0.488568 | 0.460500 | -0.028068 | (in primary numerator) |
| movement | 0.518370 | 0.519289 | +0.000919 | DOWN |
| vent | 0.007037 | 0.026641 | +0.019604 | (the confirmatory-secondary; see §2) |

Attack keep-rate is **ceilinged at exactly 1.0 in both phases** — every dealt attack card was planned, at genesis
0.5 as well as promoted 2.5. This matches #128's genesis-1.0 phase, where attack was likewise ceilinged at 1.0 —
the ceiling is not new to the high-aggression regime; it appears to hold across this seat/pairing/binding
regardless of aggression setting. Because attack is at a hard ceiling in both phases, none of `D_ws`'s movement can
come from attack; it is entirely a special/movement/vent reallocation, and here special moved down (against the
"fill nearly every free register with legal attack cards" reading, since special is one of the two categories the
guidance names) while movement — the category the header explicitly predicts DOWN — moved marginally **up**, not
down. Neither category moved in the direction dose-responsiveness predicts.

### 4.2 Per-category planned shares

| category | baseline mean share | post mean share | D (post - baseline) |
|---|---:|---:|---:|
| attack | 0.515643 | 0.512327 | -0.003316 |
| movement | 0.414696 | 0.415431 | +0.000735 |
| special | 0.068635 | 0.068526 | -0.000109 |
| vent | 0.001026 | 0.003715 | +0.002689 |

Shares move by fractions of a percentage point in every category — the largest absolute mover is vent's share
(+0.27pp), consistent with the vent keep-rate finding in §2, everything else is within noise.

### 4.3 `llm_completion_failed` rate parity across phases (execution-infrastructure check, not a hypothesis metric)

Computed from `events.sqlite3`, restricted to the `match_id`s each phase's `battery_raw.jsonl` rows actually
contain (accounting closes exactly: `requested = resolved + failed` on all three phases):

| phase | requested | resolved | failed | failed rate |
|---|---:|---:|---:|---:|
| baseline | 750 | 746 | 4 | 0.533% |
| promote | 30 | 30 | 0 | 0.000% |
| post | 719 | 712 | 7 | 0.974% |

Post's raw rate is ~1.8x baseline's, but on 4 vs 7 events out of 750/719 attempts this is not a material shift by
any qualitative standard (the header, following the display-salience precedent, deliberately does not give this
check a numeric threshold) — both phases sit under 1% failure, and this is the retry belt's health, not a
hypothesis-bearing number. No completion failed to the point of aborting a match in either phase (per-seed
containment, landed under Amendment 3, was never invoked in this `_r2` run — see §Method's bijection result).

### 4.4 Per-phase win counts (mirror pairing — uninformative about the hypothesis by design, reported only)

| phase | red (learning seat) wins | blue wins | draws |
|---|---:|---:|---:|
| baseline | 15 | 15 | 0 |
| promote | 1 | 0 | 0 |
| post | 19 | 11 | 0 |

Per the pre-registration's own framing, this is not read as evidence for or against either hypothesis — "both
seats' boards evolve under one seat's policy shift" in the mirror pairing. Reported because the header names it as
a tertiary descriptive, not because a 15/15 -> 19/11 shift means anything here on its own.

---

## 5. Negatives and what these numbers do not mean — first-class, not a footnote

### 5.1 The regime-scale contrast did not produce a *stronger* vent signal than the smaller prior step — the most important negative in this document, WITH a seat-crossing caveat that must travel with it

This battery's entire justification (stated in the overlay's own "WHY A THIRD BATTERY IS JUSTIFIED" section) is
that genesis 0.5 -> promoted 2.5 is "the maximally favorable operating point the existing mechanism can offer" — a
4x larger step than #128's 1.0 -> 1.5 (step 0.5). If the vent channel's effect scales with contrast size the way a
dose-response mechanism should, this battery should show an effect *at least* as large as #128's:

| battery | seat/persona | step | n | D_vent | d | p (one-sided) |
|---|---|---:|---:|---:|---:|---:|
| #126 (2026-07-22) | blue (sniper) | 0.25 | 10 | +8.3pp | (not stated) | (t~3.15, not converted) |
| #128 (2026-07-22) | blue (sniper) | 0.5 | 30 | +4.5pp | ~0.51 | 0.027* |
| this battery (OMN-15488) | **red (berserker)** | 2.0 | 30 | +1.96pp | 0.389 | 0.070 |

*#128's source doc (`docs/evidence/2026-07-22-lgate2-significance-battery.md`) reports this endpoint as a
**two-sided** Welch test (t=+1.98, df=51.0, p=0.053). Converted here to one-sided (p/2 = 0.027) for a like-for-like
comparison against this battery's one-sided pre-registered test — `d=+0.51` is sidedness-independent and unchanged
by the conversion. Like-for-like, #128 cleared alpha one-sided (0.027 < 0.05) while this battery did not (0.070 >=
0.05). This conversion does not make the two rows a clean comparison on its own — the seat/persona caveat below is
what actually governs how directly comparable they are.

**Read the seat column before the effect-size columns.** Both prior instances of the "twice-replicated" vent signal
that this battery's pre-registration explicitly builds on were measured on the **BLUE sniper seat** — #126's own
header line says so directly ("blue sniper seat"), and #128's scored vent contrast came specifically from its
"Blue rerun," not its red-berserker attempt (which never reached a scored contrast at all: 0/35 wins meant the
win-gated promotion evaluator could never fire on that pairing, so #128's red-seat observation is limited to an
unscored keep-rate floor note — "red attack keep was ceilinged at 1.0 with vent keep at the 0.0 floor"). **This
battery, via the mirror pairing, is therefore the first-ever *scored* red-seat contrast on either endpoint** — not
a third replication of the same seat/persona at a bigger step. The comparison in the table above crosses seat and
persona (berserker vs sniper — different loadouts, different card-partition weights, plausibly different heat-
management incentives) simultaneously with step size, so "the bigger step didn't help" is not a clean, isolated
step-size test.

**What survives the caveat, and is still reported as a genuine negative:** even granting the seat/persona
confound, the pre-registration's own framing treated the vent channel as one signal worth testing "in either
direction, exactly as measured" regardless of which seat eventually supplied the test — and on the one and only
scored red-seat data this program has produced, at the most favorable contrast the mechanism can offer, the effect
is smaller and less significant than either blue-seat instance. That is consistent with either (a) a real
paradoxical mechanism that is weaker in the berserker/red configuration than the sniper/blue one, or (b) the
paradoxical mechanism being sniper/blue-specific rather than a general "aggression guidance" effect — both are live
readings this document does not adjudicate between, and neither was anticipated by name in the pre-registration's
three named hypotheses (which are agnostic to seat). What this section does **not** support is the pre-registration's
own implicit framing that a bigger step on the same mechanism should produce a stronger read; that framing is
undercut regardless of which explanation ((a) or (b)) is correct, because it assumed a same-seat ladder that this
battery does not actually supply.

### 5.2 n=30 statistical power, restated with this run's actual effect sizes

The header states n=30 per phase with a one-sided Welch t at alpha 0.05 has ~80% power for `d ~= 0.65`. Neither
observed effect reaches that floor: primary `d = -0.147` (an order of magnitude below the floor, and negative-signed
besides — this is not a "underpowered but real" case, the point estimate itself argues against the declared
direction), vent `d = 0.389` (below the floor but in the historically-replicated range: #126/#128 also landed
in the 0.4-0.6 region and only #128's larger-n run got close to significance). A DIRECTIONAL-ONLY vent read at this
n is exactly the power statement the header predicts, not evidence the effect is absent — but per §5.1, it is also
not evidence the effect is real and merely underpowered here, because a 4x larger manipulation did not produce a
larger estimate.

### 5.3 Single-run, single-model, single-pairing, sequential (not interleaved) phases

Baseline, promote, and post ran sequentially against one MLX endpoint process, not interleaved. The same
corner-provenance confound the display-salience precedent (§5.4 of that document) flags applies here in the same
form: an endpoint-side drift between the baseline window and the post window (server restart, KV-cache/batching
state, thermal/load conditions) could shift both phases' absolute levels without being visible in either phase
alone. This battery has no interleaved-phase control, and none is proposed by the pre-registration.

### 5.4 The delegation binding's known fidelity gaps are held constant, not absent

Per the overlay's own disclosure: `LlmBusDelegationClient` does not forward pilot-spec `temperature`, collapses the
system/user message split into one flat prompt, and encodes `json_mode` as an appended prompt sentence rather than
a wire parameter. These apply identically to both phases and both seats, so they are not a *differential* confound
within this battery — but they mean this battery's absolute numbers (e.g. the `ws` levels themselves, ~0.58 in both
phases) are **not comparable** to #126/#128's `OpenAICompatibleClient`-binding numbers. Only the within-battery
baseline-vs-post contrast is scored, exactly as the overlay states.

### 5.5 Zero exclusions on either endpoint — a genuine, not just formal, negative check

The primary excludes matches with `total planned = 0`; the vent endpoint excludes matches with `dealt vent = 0`.
Both exclusion counts are **0 of 30 in both phases, for both endpoints** (§1, §2) — every one of the 60 scored
matches contributes to every scored endpoint. This removes one class of "quiet data loss" concern but is also
unremarkable given the header itself predicted "expected occurrences: zero" for the primary's exclusion — reported
because the task asks that excluded/undefined counts be stated explicitly per statistic, not because zero is a
surprising result here.

### 5.6 Attack's hard ceiling constrains what the primary can show, independent of the CEILING escape

§4.1 above: attack keep-rate is 1.0 in both phases. The CEILING escape as written only triggers on *baseline mean
ws* (the combined attack+special share) reaching 0.95, which it does not (0.584). But attack alone being
individually ceilinged in both phases means the primary's only available movement channel is special (which moved
down) traded against movement/vent (which moved up, marginally) — the "fill nearly every free register with legal
attack cards" reading of the high-aggression regime has no headroom to express itself through attack at all here,
because attack was already fully kept at genesis. This is a real constraint on what this operating point could show
even in the H_POLICY_DOSE_RESPONSIVE-true world, disclosed rather than smoothed into the NOT-SUPPORTED read.

### 5.7 The primary is also this program's first-ever scored red-seat contrast — the "two nulls at smaller contrasts" prior needs the same caveat as §5.1

The pre-registration's MECHANICAL PRIOR clause says the prior "leans H_POLICY_INERT on the primary (two nulls at
smaller contrasts)." Those two nulls are #126 and #128, and per §5.1 both were scored on the blue sniper seat —
#128's red-berserker attempt never reached a scored primary contrast at all (0/35 wins, no promotion, no baseline-
vs-post comparison possible). So the "two nulls" the prior leans on are two blue-seat nulls, and this document's
NOT-SUPPORTED primary result is the first red-seat primary result of any kind, not a third data point on the same
seat's dose-response curve. The NOT-SUPPORTED band is still the mechanically correct read of `D_ws = -0.003425` on
its own terms (§1) — this does not change the scored band — but "the prior was already two-for-two toward INERT
and this makes three" overstates how directly comparable the three data points are. Stated for the same reason as
§5.1: the pre-registration's own framing of accumulating evidence assumes a same-seat ladder this program has not
actually built yet.

### 5.8 Limitations, collected in one place

- **Power.** n=30/phase, one-sided Welch t, alpha 0.05 -> ~80% power at `d ~= 0.65`. Observed `d`: primary
  `-0.147` (an order of magnitude under the floor, and negative-signed — not merely underpowered, the point
  estimate argues the other way), vent `+0.389` (under the floor, in the historically-replicated range) — §5.2.
- **Seat/persona crosses step size in every cross-battery comparison this document draws** (§5.1, §5.7): this is
  the first scored red-berserker contrast on either endpoint; #126/#128's scored contrasts were blue-sniper. Any
  "the effect got weaker at a bigger step" or "the prior was already two nulls" reading must carry this caveat.
- **Sequential, non-interleaved phases** on one MLX endpoint process — a between-phase server-state drift is
  unclosable from these artifacts (§5.3).
- **Delegation-binding fidelity gaps** (no `temperature` forwarding, collapsed system/user prompt, `json_mode` as
  prompt text) are held constant within this battery but make its absolute levels incomparable to #126/#128's
  HTTP-binding numbers (§5.4).
- **Attack is ceilinged at 1.0 in both phases**, removing one of the primary's two numerator categories from having
  any room to move at all (§5.6).
- **One model, one arena/loadout pairing (mirror berserker-vs-berserker), one seed set, one binding, card mode
  only.** No claim here generalizes beyond `local-coder-mlx` / Qwen3.6-35B-A3B-8bit on this exact configuration.
- **Gates not re-run here**: manipulation-landed proof and the canary disposition narrative are deferred to the
  landing-phase Gates document (§3, Scope).

---

## 6. Reproduction commands

```bash
SNAP="$HOME/.omnibase/battery_envs/omn15488-hermetic-20260730"
ROOT="$SNAP/battery_state/omn15488_learning_battery_r2"

# The executing driver invocation (Amendment 2's pinned command, re-run --fresh
# in the _r2 state-root per Amendment 3 after the abandoned first attempt):
#   uv run python scripts/run_lgate2_adaptation_battery.py \
#     --mode battery --seat red --genesis 0.5 --step 2.0 --n 30 \
#     --promote-attempts 15 \
#     --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml \
#     --red-loadout contracts_data/loadouts/llm_qwen35_berserker.yaml \
#     --blue-loadout contracts_data/loadouts/llm_qwen35_berserker_mirror_blue.yaml \
#     --state-root "$ROOT" --fresh
# (run from $SNAP/steel_onslaught, the OMN-15265 hermetic snapshot repo root)

# §0b pre-registration timing gate
cd "$SNAP/steel_onslaught"
python3 scripts/check_preregistration_timing.py \
  --state-root "$ROOT" \
  --overlay contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml

# §0c abandoned-attempt row count (disposed, not scored)
wc -l "$SNAP/battery_state/omn15488_learning_battery/battery_raw.jsonl"

# §1 / §2 PRIMARY + CONFIRMATORY-SECONDARY, pure stdlib, no battery_summary.json read
python3 - <<'PY'
import json, math, statistics

def betacf(a, b, x, maxit=200, eps=3e-14):
    qab=a+b; qap=a+1; qam=a-1
    c=1.0; d=1.0-qab*x/qap
    if abs(d)<1e-30: d=1e-30
    d=1.0/d; h=d
    for m in range(1,maxit+1):
        m2=2*m
        aa=m*(b-m)*x/((qam+m2)*(a+m2))
        d=1.0+aa*d
        if abs(d)<1e-30: d=1e-30
        c=1.0+aa/c
        if abs(c)<1e-30: c=1e-30
        d=1.0/d; h*=d*c
        aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2))
        d=1.0+aa*d
        if abs(d)<1e-30: d=1e-30
        c=1.0+aa/c
        if abs(c)<1e-30: c=1e-30
        d=1.0/d
        delta=d*c
        h*=delta
        if abs(delta-1.0)<eps: break
    return h

def betainc(a,b,x):
    if x<=0: return 0.0
    if x>=1: return 1.0
    lbeta=math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log(1-x)
    front=math.exp(lbeta)
    return front*betacf(a,b,x)/a if x<(a+1)/(a+b+2) else 1-front*betacf(b,a,1-x)/b

def student_t_sf(t, df):
    if t<=0: return 1-student_t_sf(-t,df)
    x=df/(df+t*t)
    return 0.5*betainc(df/2,0.5,x)

def welch(a,b):
    na,nb=len(a),len(b)
    ma,mb=statistics.mean(a),statistics.mean(b)
    va,vb=statistics.variance(a),statistics.variance(b)
    se=math.sqrt(va/na+vb/nb)
    t=(ma-mb)/se
    df=(va/na+vb/nb)**2/((va/na)**2/(na-1)+(vb/nb)**2/(nb-1))
    return dict(D=ma-mb, t=t, df=df, p=student_t_sf(t,df), mean_a=ma, mean_b=mb)

ROOT="battery_state/omn15488_learning_battery_r2"  # relative to $SNAP
rows=[json.loads(l) for l in open(f"{ROOT}/battery_raw.jsonl")]
baseline=[r for r in rows if r["phase"]=="baseline"]
post=[r for r in rows if r["phase"]=="post"]

def ws(r):
    p=r["learning_seat"]["planned"]
    tot=sum(p.get(k,0) for k in ("attack","movement","special","vent"))
    return None if tot<=0 else (p.get("attack",0)+p.get("special",0))/tot

def vk(r):
    d=r["learning_seat"]["dealt"].get("vent",0)
    p=r["learning_seat"]["planned"].get("vent",0)
    return None if d<=0 else p/d

b_ws=[ws(r) for r in baseline]; p_ws=[ws(r) for r in post]
b_vk=[vk(r) for r in baseline]; p_vk=[vk(r) for r in post]
print("PRIMARY  :", welch(p_ws, b_ws))
print("SECONDARY:", welch(p_vk, b_vk))
PY

# Validate the t/p implementation against the header's own reference values
# BEFORE trusting it on the battery data (append to the PRIMARY/SECONDARY
# script above, or run standalone with the same betacf/betainc/student_t_sf
# functions defined):
python3 - <<'PY'
# ... (paste betacf, betainc, student_t_sf from the block above) ...
print("t=2.0,  df=60 two-sided:", 2*student_t_sf(2.0, 60))    # expect ~0.0500
print("t=3.15, df=18 two-sided:", 2*student_t_sf(3.15, 18))   # expect ~0.0055
PY

# Independent cross-check against scipy (separate interpreter/venv with scipy
# installed; not required, corroboration only):
python3 -c "
import scipy.stats as st
print(st.t.sf(2.0,60)*2, st.t.sf(3.15,18)*2)
print(st.t.sf(-0.570669, 57.644039))   # primary p
print(st.t.sf(1.504681, 38.288517))    # vent p
"

# §Method ledger cross-check: dealt/planned sums reproduce exactly from raw events
python3 - <<'PY'
import sqlite3, json
from collections import Counter
ROOT="battery_state/omn15488_learning_battery_r2"
con=sqlite3.connect(f"file:{ROOT}/events.sqlite3?immutable=1", uri=True)
raw=[json.loads(l) for l in open(f"{ROOT}/battery_raw.jsonl")]
raw_mids={r["match_id"] for r in raw}
def cat(cid): return cid.split(".")[1]
dealt=Counter(); planned=Counter()
for mid,pj in con.execute("select match_id,payload_json from events where event_type='hand_dealt'"):
    if mid not in raw_mids: continue
    p=json.loads(pj)
    if p["seat"]!="red": continue
    for cid in p["card_ids"]: dealt[cat(cid)]+=1
for mid,pj in con.execute("select match_id,payload_json from events where event_type='plan_committed'"):
    if mid not in raw_mids: continue
    p=json.loads(pj)
    if p["seat"]!="red": continue
    for reg in p["registers"]: planned[cat(reg["card_id"])]+=1
print("dealt (ledger):", dict(dealt))
print("planned (ledger):", dict(planned))
PY

# §4.3 llm_completion_failed rate parity, per phase, restricted to scored match_ids
python3 - <<'PY'
import sqlite3, json
ROOT="battery_state/omn15488_learning_battery_r2"
con=sqlite3.connect(f"file:{ROOT}/events.sqlite3?immutable=1", uri=True)
raw=[json.loads(l) for l in open(f"{ROOT}/battery_raw.jsonl")]
phase_by_mid={r["match_id"]: r["phase"] for r in raw}
for phase in ("baseline","promote","post"):
    mids=[m for m,p in phase_by_mid.items() if p==phase]
    qs=",".join("?"*len(mids))
    req=con.execute(f"select count(*) from events where event_type='llm_completion_requested' and match_id in ({qs})", mids).fetchone()[0]
    res=con.execute(f"select count(*) from events where event_type='llm_completion_resolved' and match_id in ({qs})", mids).fetchone()[0]
    fail=con.execute(f"select count(*) from events where event_type='llm_completion_failed' and match_id in ({qs})", mids).fetchone()[0]
    print(phase, "requested", req, "resolved", res, "failed", fail, f"rate={fail/req*100:.3f}%")
PY
```

---

## Citations (all relative paths)

- **Pre-registration:** `contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning.yaml` header —
  original pre-registration commit `ff5df34` (2026-07-30, #235, OMN-15488), which already carried Amendment 1
  (client contract-selection defect fix); Amendment 2 (programming response contract, `4bae73e`, 2026-07-30, #239,
  OMN-15522) and Amendment 3 (abandoned-attempt disposal + per-seed containment, `a3b0d8a`, 2026-07-31, #240,
  OMN-15566) were appended after — the executing ancestry, gate-verified in §0b.
- **Driver:** `scripts/run_lgate2_adaptation_battery.py`.
- **Method gate:** `scripts/check_preregistration_timing.py` (exit 0, §0b).
- **Raw data:** `$ROOT/battery_raw.jsonl` (61 rows), `$ROOT/events.sqlite3` (opened `?immutable=1` throughout).
  `battery_summary.json` is not read anywhere in this document; a spot-check found its `mean_planned_share.vent`
  field uses a present-key-only denominator (2 baseline / 5 post matches instead of 30) and is not usable for
  per-phase shares — a driver summary defect worth a follow-up note, not a lane defect.
- **Prior batteries cited for context (not re-measured):** `docs/evidence/2026-07-22-lgate2-adaptation-battery.md`
  (#126); `docs/evidence/2026-07-22-lgate2-significance-battery.md` (#128, the source of the `d~0.51`/`p=0.053`
  vent comparison in §5.1).
- **Structural precedent for this document's format:**
  `docs/evidence/2026-07-29-display-salience-arm1-scoring.md`.
- **Gates/acceptance companion (the merge referenced in Scope, §3):**
  `docs/evidence/2026-07-31-lgate2-decisive-battery-acceptance.md` — ACCEPT, all four acceptance criteria (AC1
  timing, AC2 contamination/bijection, AC3 audit chain, AC6 receipts) PASS, gates agent independent of this
  document's assembler and recompute verifier.
- **Tickets:** OMN-15488 (this battery), OMN-15482 (delegation backend-coverage note, fidelity gaps cited in
  §5.4), OMN-15522 (programming response contract fix), OMN-15566 (semantic-retry parity / per-seed containment,
  Amendment 3), OMN-15377 (contamination-gate orphan-class gap, cited by the structural precedent, not reproduced
  here since this run has zero orphans).
- No secrets, keys, or absolute developer-machine paths included beyond the documented `$HOME/.omnibase/...`
  snapshot convention already used by the cited precedent.

*Every figure in this document was computed from `battery_raw.jsonl` and/or `events.sqlite3` by a command
reproduced in §6. No claim rests on an agent self-report, and no figure was taken from `battery_summary.json`.
This is the scoring phase only — the Gates/acceptance phase for this battery is a separate deliverable merged in
at landing (see Scope, §3).*
