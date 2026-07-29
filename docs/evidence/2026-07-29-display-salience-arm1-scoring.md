# Display-salience arm #1 (SO-SALIENCE) — pre-registered SCORING — 2026-07-29

**Verdict: SALIENCE-EMERGENT.** The pre-registered primary statistic `s = PROMINENT_total / DEFAULT_total` is
**undefined** — `DEFAULT_total = 0`. The overlay's own pre-declared out-of-interval escape governs that exact case,
and this arm lands on its second branch: `DEFAULT_total = 0 AND PROMINENT_total > 0 => SALIENCE-EMERGENT`.
`PROMINENT_total = 34`, `DEFAULT_total = 0`. Both seats land on the same escape branch (red 22/0, blue 12/0), so the
arm is **not** SEAT-SPLIT under any reading.

**What the label means, and what it does not.** SALIENCE-EMERGENT is a *qualitative* escape the pre-registration
explicitly declined to fold into the ratio scale. It says: the prominent lane produced objective-capture events and
the default lane produced none. It does **not** license "salience multiplies objective capture by N×" — there is no
N. Three facts qualify the finding hard, and each is developed below rather than parked in a footnote: the 34 events
are **extremely clumped** (4 of 30 matches; one match supplies 18 of 34), the DV `objective_scored` is an **engine
positional event that fires without pilot intent** (this program's own SO-OBJ-MASK arm scored 14 of them with the
objectives block entirely absent from the prompt), and the two lanes diverge on **unmeasured axes far larger than
the pre-registered one** (28–2 vs 15–15 win split; 2.21× total tick exposure). The direction of the finding is
solid; its mechanism is not established by this arm.

**Scope.** This is the arm's **scoring** document — the pre-registered analysis and nothing else. Artifact
acceptance (row counts, contamination, provenance, bus read-back, the 5018/5019 skip-and-makeup record) is a
**separate, already-landed deliverable**: `docs/evidence/2026-07-29-display-salience-arm1-acceptance-battery.md`
(PR #231), verdict **ACCEPT**. This document does not re-litigate acceptance; it cites it. Conversely, that document
deliberately did not compute `s`, the seat split, or the verdict — those are here.

**Artifacts.** `SNAP` = the frozen hermetic snapshot `~/.omnibase/battery_envs/omn15172-hermetic-20260727`;
`ROOT` = `$SNAP/battery_state/omn15172_acceptance_rerun2`. Both corners' `battery_raw.jsonl`, `events.sqlite3` and
delegation artifact stores are retained under `ROOT`. Every ledger open by this analysis used `?immutable=1`.

**Model:** live Qwen3.6-35B-A3B-8bit via the `onex_delegation` provider binding `onex-local-coder-mlx`, both seats,
per-seed isolated process invocation. n = 30 per corner, seeds 5001–5030.

---

## 0. Pre-registration

The pre-registration lives in the header of
`contracts_data/overlays/foundry_60_asym_v1_salience_prominent_delegation.yaml`, following this family's convention
of committing it on the manipulated arm's own file (the `_default` sibling's header points at it and restates
nothing). Not one character of the hypothesis, the primary statistic, the decision bands, the escapes, the
seat-split clause or the gates was edited by this session.

### 0a. Operative clauses, quoted verbatim

> **PRIMARY STATISTIC (one number):**
>
> `s = PROMINENT_total / DEFAULT_total`
>
> **DECISION (disjunctive, exactly one criterion, no illustrative bands):**
> `s >= 1.5` => SALIENCE-AMPLIFIES (prominent rendering at least 1.5x the default lane's objective-capture rate)
> `s <= 0.6667 (2/3)` => SALIENCE-DAMPENS (prominent rendering at most 2/3 the default lane's rate — symmetric on
> the log scale with the amplify threshold, 1.5 = 1/0.6667)
> `0.6667 < s < 1.5` => SALIENCE-INERT (supports H_SALIENCE_INERT — the channel's mere presence, not its intensity,
> carries the effect)

> **OUT-OF-INTERVAL ESCAPE (pre-declared, unclamped, for the degenerate denominator DEFAULT_total = 0 — a genuinely
> possible outcome given the published context above is single digits to teens per 30, not guaranteed nonzero):**
> `DEFAULT_total = 0 AND PROMINENT_total = 0` => SALIENCE-INERT (reported directly: both lanes measured zero
> objective-capture events; the ratio is undefined but the qualitative reading — no detectable effect in either
> direction — is unambiguous).
> `DEFAULT_total = 0 AND PROMINENT_total > 0` => SALIENCE-EMERGENT (qualitative escape, NOT folded into the 0-Inf
> ratio scale — reported with the raw PROMINENT_total and both lanes' full context).

> **MEASURED QUANTITIES.** From each lane's own n=30 ledger (seeds 5001-5030):
> `DEFAULT_total` = pooled OBJECTIVE_SCORED event count, `foundry_60_asym_v1_salience_default_delegation.yaml`
> `PROMINENT_total` = pooled OBJECTIVE_SCORED event count, THIS overlay
> `DEFAULT_red/DEFAULT_blue`, `PROMINENT_red/PROMINENT_blue` — the same counts split by seat, reported alongside
> (SECONDARY, see SEAT SPLIT).

> **SEAT SPLIT (reported, not a second criterion; identical clause to every prior arm in this family).** Per-seat
> ratios `s_red = PROMINENT_red / DEFAULT_red`, `s_blue = PROMINENT_blue / DEFAULT_blue` (same escapes as above, per
> seat) are always reported alongside `s`. If they straddle the decision boundaries (one >= 1.5 while the other
> <= 0.6667), the arm is reported SEAT-SPLIT and the pooled verdict is stated as not supported by both seats. The
> formal criterion remains `s`; this clause governs how honestly it is narrated, not what it decides.

> **SECONDARY (pre-declared, NOT scored as the primary criterion, reported alongside it):**
> `llm_completion_failed` rate on each lane, compared for a material increase on PROMINENT (the
> H_SALIENCE_DISRUPTS_COMPLIANCE reading named above). "Material" is deliberately NOT given a numeric threshold here
> — unlike the primary criterion, this is a qualitative safety check, following the same STATISTICAL HONESTY
> discipline the whole family applies to n=30 secondary reads.

> **MANIPULATION-LANDED GATE (must pass before any scoring).** Since this arm changes neither engine payout nor
> display presence (unlike DECOY/MASK, whose gates had to prove an engine-side or observation-side change landed),
> the gate here is:
> **(a) SALIENCE LANDED**, checked from each lane's own recorded prompts (the literal `user_prompt` text on every
> `llm_completion_requested` row): every PROMINENT-lane prompt with a nonempty objectives block must contain the
> literal `"!!! OBJECTIVES"` and must NOT contain the literal `"--- OBJECTIVES"`; every DEFAULT-lane prompt with a
> nonempty objectives block must contain `"--- OBJECTIVES"` and must NOT contain `"!!! OBJECTIVES"`. This is a
> direct string search over the ledger each lane actually ran on, matching MASK's own gate standard. […]
> **(b) PAYOUT + DISPLAY PRESENCE UNCHANGED**, proven structurally: both lanes declare
> `contracts.arena_id: foundry_60_asym_v1` — the SAME, byte-untouched arena file — so both lanes'
> `arena_contract_hash` (recorded on every match_started row) must be identical to each other AND to every other
> battery that has ever run on foundry_60_asym_v1 unmodified (drift in objective_scoring or objective_display would
> change the hash).

> **STATISTICAL HONESTY.** n=30 per lane, small integer counts (single digits to teens per the published context
> above) — a ratio of two such counts is a rank-ordering of effect strength, never calibrated evidence. Read
> generously toward INERT: this pre-registration does not claim n=30 can resolve anything short of the
> 1.5x/0.6667x bands declared above.

The two rival hypotheses, quoted in short: **H_SALIENCE_INERT** ("behaviour is driven by the presence of the
channel, not its intensity"); **H_SALIENCE_DOSE_RESPONSIVE** ("behaviour scales with display intensity, not just its
presence"); plus the escaped third reading **H_SALIENCE_DISRUPTS_COMPLIANCE** ("louder framing degrades
response-shape compliance rather than, or in addition to, moving objective-capture behaviour"). The overlay's
**MECHANICAL PRIOR** clause states the prior was "genuinely uncertain in EITHER direction" and commits "to scoring
the criterion exactly as measured, in either direction."

### 0b. Timing gate — run for the first time here, exit 0 on both corners

The acceptance report disclosed (§5.4, §7.5) that `scripts/check_preregistration_timing.py` had **not** been run and
asked that it be run before this scoring document was written. It was. Verbatim, against the snapshot repo the
battery actually executed under (`steel@985ca70c`):

```
$ python3 $SNAP/steel_onslaught/scripts/check_preregistration_timing.py \
    --state-root $ROOT/prominent \
    --overlay $SNAP/steel_onslaught/contracts_data/overlays/foundry_60_asym_v1_salience_prominent_delegation.yaml
Overlay:                    contracts_data/overlays/foundry_60_asym_v1_salience_prominent_delegation.yaml
Pre-registration commit:    23a88d09051565270f76cade8bc7b685cd790f38
  author timestamp:         2026-07-27T09:58:25-04:00   (load-bearing)
  committer timestamp:      2026-07-27T09:58:25-04:00   (NOT authoritative -- ...)
First match_started:        2026-07-28T05:35:07.747716+00:00
Gap (match_started - author date): 15:36:42.747716

OK: pre-registration commit's author timestamp precedes the first match_started.
EXIT=0
```

```
$ python3 $SNAP/steel_onslaught/scripts/check_preregistration_timing.py \
    --state-root $ROOT/default \
    --overlay $SNAP/steel_onslaught/contracts_data/overlays/foundry_60_asym_v1_salience_default_delegation.yaml
Overlay:                    contracts_data/overlays/foundry_60_asym_v1_salience_default_delegation.yaml
Pre-registration commit:    23a88d09051565270f76cade8bc7b685cd790f38
  author timestamp:         2026-07-27T09:58:25-04:00   (load-bearing)
  committer timestamp:      2026-07-27T09:58:25-04:00   (NOT authoritative -- ...)
First match_started:        2026-07-27T20:49:16.700827+00:00
Gap (match_started - author date): 6:50:51.700827

OK: pre-registration commit's author timestamp precedes the first match_started.
EXIT=0
```

The gate's "latest touch" is `23a88d09` (the 2026-07-27 OMN-15239 bounded-semantic-retry amendment), not the
original `f9b11aea` pre-registration — which is the gate's designed behaviour: the binding constraint is the *last*
edit to the file, so a criterion amended after seeing results cannot hide behind an early first commit. Margins:
**+15 h 36 m 42 s** (prominent) and **+6 h 50 m 51 s** (default). These match the timestamps the acceptance report
derived by hand from the two independent sources (§5.4); the checker now confirms them mechanically.

### 0c. A false VIOLATION if the gate is run against the canonical clone — recorded, not smoothed

Run against the **canonical clone at current `main`**, the same command **fails**:

```
$ python3 $SNAP/steel_onslaught/scripts/check_preregistration_timing.py \
    --state-root $ROOT/prominent --overlay <canonical clone>/…_salience_prominent_delegation.yaml
Pre-registration commit:    375c98015463b794c46dde59fca91c5805d19312
  author timestamp:         2026-07-28T14:00:29-04:00   (load-bearing)
First match_started:        2026-07-28T05:35:07.747716+00:00
Gap (match_started - author date): -1 day, 11:34:38.747716

VIOLATION: the pre-registration commit's AUTHOR timestamp is at or after the lane's earliest match_started.
EXIT=1
```

**This is a false positive and the pass above is the correct reading.** `375c980` is the **2026-07-28 OMN-15265
amendment** (#229), which landed *after* the battery ran. Three facts discharge it, in decreasing strength:

1. **The battery did not execute under that commit.** The hermetic snapshot is pinned at `steel@985ca70c`
   (2026-07-27T11:47:25-04:00), whose ancestry ends at `23a88d09`. `375c980` is not in the ancestry of the code that
   ran. The acceptance report independently corroborates this from the other direction: the driver at `985ca70c`
   "contains **no** `_drift_recheck`" (§6.2) — the very belt `375c980` adds.
2. **The amendment says so itself**, in its own committed text: it is "execution-infrastructure only," "Not a
   hypothesis, criterion, prompt, or arm-mechanism change of any kind," and "does not and cannot retroactively
   affect any battery already in flight under a prior driver build — it governs FUTURE runs only."
3. **The commit's diff to this overlay is comment text only** — and this is checkable mechanically, not by reading
   the diff. Extracting the criterion region (the header block from `# PRE-REGISTERED HYPOTHESIS AND DECISION
   CRITERION` to `# CORNER PROVENANCE NOTE`, which contains the hypothesis, primary statistic, decision bands,
   escapes, seat-split clause, secondary, alternative readings and both gates) at each of the four commits and
   hashing it:

   | commit | date | criterion-region sha256 (first 16) | lines | executable-config sha256 (prom / def) |
   |---|---|---|---:|---|
   | `f9b11aea` (#223, pre-registration) | 2026-07-26 | `a31a857d7042bdb8` | 205 | `c01cacce4e64f6af` / `902b52aa0746ccb9` |
   | `23a88d09` (#225, executing tip) | 2026-07-27 | `a31a857d7042bdb8` | 205 | `c01cacce4e64f6af` / `902b52aa0746ccb9` |
   | `985ca70c` (snapshot pin) | 2026-07-27 | `a31a857d7042bdb8` | 205 | `c01cacce4e64f6af` / `902b52aa0746ccb9` |
   | `c6c3bcd` (current `main`) | 2026-07-29 | `a31a857d7042bdb8` | 205 | `c01cacce4e64f6af` / `902b52aa0746ccb9` |

   **One hash, all four commits.** The scored criterion is byte-identical from the original pre-registration through
   current `main`, and so is every non-comment (executable) line of both overlays. Both amendments are pure appends
   *after* the criterion region. There is no version of this file in which the rule this document applies differs
   from the rule committed on 2026-07-26.

**The transferable lesson, stated because it will recur:** `check_preregistration_timing.py` must be run against the
ancestry the battery executed under, not against whatever `main` has since become. Its "latest touch" rule is
correct for catching a post-hoc criterion edit, but it cannot distinguish a post-run criterion edit from a post-run
execution-infrastructure note in the same file. Any arm whose overlay is touched again after its battery runs will
reproduce this. The cheap mitigation is procedural (run it against the pinned snapshot, as done here, and record
both results); a mechanical fix would require the gate to take the executing commit as an input. Recorded here as a
known gate limitation; **no ticket is filed by this document**, and none of this changes the arm's timing verdict.

---

## Method

`OBJECTIVE_SCORED` events are read directly from each lane's own `events.sqlite3`, opened `?immutable=1`, and
**restricted to the 30 `match_id`s present in that lane's `battery_raw.jsonl`** — the exclusion rule the acceptance
report requires (§4.5), because the prominent ledger holds 32 matches' events and only 30 are scored rows. Seat
attribution is `objective_scored.payload.controlling_player_id`, read per event, not inferred.

Two independent cross-checks that the counts are right:

- The per-row `total_awards` field in `battery_raw.jsonl` equals each match's `objective_scored` event count exactly,
  60/60 matches across both corners (established in acceptance §2.4 and reproduced here). Summing `total_awards`
  over the 30 prominent rows gives **34**; over the 30 default rows, **0**.
- The two withheld orphan matches contribute **zero** `objective_scored` events (acceptance §4.5), so
  `PROMINENT_total` is 34 whether the exclusion rule is applied or not. The numerator is insensitive to the one
  filtering decision this lane forces.

No figure in this document comes from any `battery_summary.json` — that file is a per-invocation destructive
overwrite and currently reports `n: 2` for the 30-row prominent lane (acceptance §7.2).

---

## 1. PRIMARY — the scored criterion

| Quantity | prominent | default |
|---|---:|---:|
| matches scored (rows) | 30 | 30 |
| **pooled `OBJECTIVE_SCORED`** | **34** | **0** |
| — red (`player.red`) | **22** | **0** |
| — blue (`player.blue`) | **12** | **0** |
| matches with ≥1 capture | **4 / 30** | **0 / 30** |
| distinct objectives ever captured | 1 (`objective.east_gate`) | 0 |
| VP awarded (1 VP per event) | red 22 / blue 12 | 0 / 0 |
| rows with nonzero `vp_totals` | 4 | 0 |
| terminal mix | 29 `elimination`, **1 `vp_threshold`** | 30 `elimination` |

```
PROMINENT_total = 34
DEFAULT_total   = 0

s = PROMINENT_total / DEFAULT_total = 34 / 0  ->  UNDEFINED (division by zero)
```

**Scoring, applied mechanically and exactly as written.** The DECISION block's three bands (`>= 1.5`, `<= 0.6667`,
strictly between) each require a defined `s`; none of them can be evaluated. The pre-registration anticipated
precisely this case and pre-declared an escape for it, naming `DEFAULT_total = 0` as "a genuinely possible outcome
given the published context above is single digits to teens per 30, **not guaranteed nonzero**." The escape's two
branches are mutually exclusive and jointly exhaustive over `DEFAULT_total = 0`, and this arm satisfies the second:
`DEFAULT_total = 0` **and** `PROMINENT_total = 34 > 0`.

**→ SALIENCE-EMERGENT.**

Reported with what the escape clause itself demands — "the raw `PROMINENT_total` and both lanes' full context":
raw `PROMINENT_total` = **34**, and both lanes' full context is §§1a–5 below.

### 1a. Where the 34 events actually are — the clumping, stated before anything is built on the total

All 34 events land in **4 of 30 matches**, on **one** of the arena's three objective cells:

| seed | winner | terminal | ticks | red | blue | total | scoring-tick window |
|---|---|---|---:|---:|---:|---:|---|
| 5004 | `player.blue` | elimination | 287 | 1 | 5 | **6** | 99–107 |
| 5006 | `player.red` | **`vp_threshold`** | 79 | 15 | 3 | **18** | 62–79 |
| 5020 | `player.red` | elimination | 300 | 3 | 1 | **4** | 49–241 |
| 5029 | `player.blue` | elimination | 265 | 3 | 3 | **6** | 81–87 |
| — | — | — | — | **22** | **12** | **34** | — |

The other **26 of 30** prominent matches scored zero, exactly as all 30 default matches did.

**One match (seed 5006) supplies 18 of 34 events — 53% of the entire numerator.** It is also the only match in
either lane that ended on VP: red reached the arena's `vp_threshold: 15` and won on points rather than by
elimination. Three of the remaining four scoring matches (5004, 5020, 5029 at 287/300/265 ticks) are the **three
longest matches in the lane**; seed 5006 at 79 ticks is the **shortest**.

So `PROMINENT_total = 34` is not 34 independent draws. It is **4 draws**, one of which is a runaway. The
pre-registration's own STATISTICAL HONESTY clause — "a ratio of two such counts is a rank-ordering of effect
strength, never calibrated evidence" — applies with more force here than it anticipated, because the clumping is
worse than a count of 34 suggests. Consistent with that clause and with ALTERNATIVE READINGS item (3) (which
rejected a per-match binary two-proportion z-test on the grounds that at this n it "could not support any calibrated
significance claim"), **this document reports the 4/30 vs 0/30 match-level split as a descriptive and does not
convert it into a p-value.**

Also worth stating plainly: only `objective.east_gate` was ever captured, in either lane. The arena declares three
objective cells (`west_yard` (18,30), `north_works` (30,22), `east_gate` (42,36)); `east_gate` sits in blue's
defense band and is described in the arena's own header as a "deep commitment for red." All 34 events, both seats,
one cell.

### 1b. Seat split (pre-declared, reported, not a second criterion)

```
s_red  = PROMINENT_red  / DEFAULT_red  = 22 / 0  ->  UNDEFINED
s_blue = PROMINENT_blue / DEFAULT_blue = 12 / 0  ->  UNDEFINED
```

The seat-split clause specifies "same escapes as above, per seat." Applying them:

| seat | PROMINENT | DEFAULT | ratio | escape branch | per-seat label |
|---|---:|---:|---|---|---|
| red | 22 | 0 | undefined | `DEFAULT = 0 AND PROMINENT > 0` | **SALIENCE-EMERGENT** |
| blue | 12 | 0 | undefined | `DEFAULT = 0 AND PROMINENT > 0` | **SALIENCE-EMERGENT** |

**Both seats land on the same escape branch as the pooled statistic. The arm is NOT reported SEAT-SPLIT.** This is
not a close call resolved in the arm's favour: the SEAT-SPLIT trigger is a *straddle* ("one >= 1.5 while the other
<= 0.6667"), and there is no reading — literal or generous — on which two seats sitting on the identical escape
branch straddle a boundary. Each seat independently reproduces the pooled reading, which is the cleanest
pooled/seat agreement the clause can return.

**A pedantic reading, named and dismissed rather than ignored:** one could argue the straddle test is strictly
*inapplicable* (not "unmet") because neither `s_red` nor `s_blue` exists to be compared against 1.5 or 0.6667, and
that the clause is therefore silent on this case. The two readings differ in wording only — "not SEAT-SPLIT" and
"SEAT-SPLIT is unevaluable" produce the same output, because the clause's only effect is to trigger the disclosure
"the pooled verdict is stated as not supported by both seats," and here both seats *do* support it. There is no
flattering-versus-honest choice hiding in this branch.

### 1c. Is the escape ambiguous on this exact case? No — and here is the check

The pre-registration is asked to do something unusual: adjudicate its own degenerate case. It does, and it does so
without leaving a gap. Read literally:

- The escape is scoped, in its own header, "for the degenerate denominator `DEFAULT_total = 0`." `DEFAULT_total`
  is 0. In scope.
- Its two branches partition that scope on `PROMINENT_total`: `= 0` and `> 0`. `PROMINENT_total = 34`. Exactly one
  branch matches, and it is not the one that would have returned INERT.
- The escape is marked "**unclamped**" and "NOT folded into the 0-Inf ratio scale," so there is no licence to
  substitute `s = ∞`, `s = 34`, or any large-number stand-in and then read a band. SALIENCE-AMPLIFIES is **not**
  reachable on this data, and this document does not claim it.
- The escape's ordering relative to the bands is unambiguous because the bands are unevaluable, not merely
  unfavourable. There is no competing rule to prioritise it against.

**The one place a critic could push, addressed head-on.** SALIENCE-EMERGENT is a *fourth* label that appears only in
the escape, never in the DECISION block, and the pre-registration never states what it implies about
H_SALIENCE_INERT vs H_SALIENCE_DOSE_RESPONSIVE. That is a real gap — but it is a gap in *interpretation*, not in
*scoring*, and this document resolves it the conservative way: §6 adjudicates the two named hypotheses on the
evidence and explicitly declines to convert SALIENCE-EMERGENT into a dose-response claim, because a dose-response
claim requires a ratio and the ratio does not exist. The label is reported as the pre-registration defines it —
qualitative — and nothing further is inferred from the label itself.

**No goal-post was moved.** The scored rule is `s`, computed on the pooled `OBJECTIVE_SCORED` counts the
pre-registration named, over the seeds it named, filtered by the exclusion rule the artifacts require. None of the
four ALTERNATIVE READINGS the pre-registration named and rejected — substituting ASYM_OBJ's published 2/30 as the
denominator (1), utility-card keep-rate (2), a per-match binary z-test (3), a per-seat majority vote (4) — was used
to rescue a defined ratio, and no new normalisation was promoted to criterion status (see §5.3, where per-tick and
per-completion normalisations are reported as descriptives and explicitly cannot change the verdict).

---

## 2. MANIPULATION-LANDED GATE (pre-registered; passed before any scoring)

### 2a. SALIENCE LANDED — executed exhaustively, 11,594 prompts, zero exceptions

The clause names "the literal `user_prompt` text on every `llm_completion_requested` row." **The canonical event
ledger does not persist prompt text** — `llm_completion_requested` payloads carry only
`provider_id`, `persona_id`, `system_prompt_length`, `user_prompt_length`. A direct string search over `payload_json`
and `envelope_json` for either literal returns **0 hits** in both ledgers. This is the same program-wide schema fact
SO-OBJ-MASK discovered and disclosed in its own §2b ("the raw prompt/response TEXT is never persisted to the
canonical ledger, by design, for every arm in this program").

**Unlike MASK, this arm can still execute the substance of the clause — exhaustively.** Because this arm is bound to
the `onex_delegation` provider, every completion request is captured by the delegation path's content-addressed
artifact store under `$ROOT/<corner>/delegation_state/artifacts/`, and each captured record carries the full
`prompt_text` actually transmitted to the provider. Walking every artifact file in both stores (46,388 files),
parsing each as JSON and string-searching every `prompt_text`:

| | prominent | default |
|---|---:|---:|
| artifact files walked | 32,492 | 13,896 |
| records carrying `prompt_text` | **8,123** | **3,474** |
| contain `"!!! OBJECTIVES"` | **8,121** | **0** |
| contain `"--- OBJECTIVES"` | **0** | **3,473** |
| contain **both** | **0** | **0** |
| contain **neither** | 2 | 1 |
| `llm_completion_requested` rows in that lane's ledger | **8,121** | **3,473** |

**Every prompt with a nonempty objectives block satisfies the clause, in both directions, with zero exceptions**, and
the counts match each lane's ledger row count **exactly** (8,121 and 3,473) — so coverage is 100% of every recorded
completion request, not a sample.

The 2 (prominent) and 1 (default) "neither" records are each a 268-character transport probe, quoted in full:
`"Preflight health check for the delegation CLI transport. Respond with exactly this JSON object and nothing else:
{\"action\": \"remain\", …}"`. They carry no observation and therefore no objectives block, so they fall outside the
clause's own scope ("every prompt **with a nonempty objectives block**"). They are named here rather than silently
dropped.

**Two disclosures, neither of which weakens the gate:**

1. **This is a different surface than the clause named.** The clause said "the ledger"; this is the delegation
   artifact store. It is arguably the *stronger* surface — it holds the exact bytes sent to the model, whereas the
   ledger would only ever have held a copy — but it is not the surface promised in advance, and the substitution is
   recorded here rather than glossed. The pre-registration itself frames clause (a) as "the LIVE re-confirmation" of
   a structural guarantee already enforced pre-battery in CI
   (`tests/llm/test_llm_pilot.py::test_prominent_delta_from_default_is_confined_to_the_objectives_block` and
   siblings), "not a substitute for it" — so the structural guarantee is the primary proof either way, and this is
   the live confirmation it asked for.
2. **The prominent scan spans all 32 matches, not the scored 30.** Artifacts are not match-attributed, so the scan
   cannot be filtered to the 30 scored rows. This is harmless in the strict direction: the scored set is a subset of
   the scanned set, and the scanned set has **zero** violations, so the scored subset has zero violations *a
   fortiori*.

**Mechanism, for the record.** `src/steel_onslaught/llm/pilot.py` renders the block under
`if obs.objectives and obs.victory_points is not None:`; the PROMINENT branch emits a `"=" * 60` rule, the
`"!!! OBJECTIVES -- SCORING NOW …"` header, `"VICTORY POINTS: YOU … -- ENEMY …"`, the per-objective lines, and one
added line `"REMINDER: capturing objectives is how this match is won."`; the DEFAULT branch emits
`"--- OBJECTIVES …"` and lower-case equivalents. Both branches emit **the same facts** — same cells, same
`vp_per_round`, same `vp_threshold`, same VP totals. The diff is header/emphasis characters plus the one REMINDER
line; no value and no new fact. Across all objectives-bearing prompts, mean length is 4,119.8 chars on prominent vs
3,922.7 on default (Δ ≈ 197). Pooled over whole batteries that comparison is uncontrolled — terrain and trajectory
also move prompt length — so it is corroboration only.

**A controlled version of the same check, which the pooled means cannot give.** Restricting to `tick <= 1` — the
opening tick of a seeded arena, where match state is identical across corners by construction — `user_prompt_length`
is a **single constant per (corner, persona)** across all 30 seeds, with no dispersion at all:

| persona | prominent | default | delta |
|---|---:|---:|---:|
| berserker (red) | **1939** (all 30) | **1743** (all 30) | **+196** |
| sniper (blue) | **1968** (all 30) | **1772** (all 30) | **+196** |

**+196 is exactly the byte delta the PROMINENT branch adds, reconstructed independently from `pilot.py`'s own
rendering code**: two `"=" * 60` rules (+122 with newlines), the header rewrite `--- OBJECTIVES (… first to N VP
wins) ---` → `!!! OBJECTIVES -- SCORING NOW (… FIRST TO N VP WINS) !!!` (+15), the VP line recase
`victory_points: you a vs enemy b` → `VICTORY POINTS: YOU a -- ENEMY b` (+2), and the added
`REMINDER: capturing objectives is how this match is won.` line (+57). The reconstruction is invariant to
`vp_threshold` digit count and to the number of objective cells (the per-objective lines change only `-` → `*`,
length-preserving), so the predicted delta is +196 unconditionally — and the observed delta is +196, on both
personas, on all 60 first-tick prompts. Over the full battery the distributions are also **completely separated**
(prominent min 1938 > default max 1877, n = 7,598 / 3,473), and `system_prompt_length` takes the **identical** value
set `{1704, 2357, 2717}` in both corners, confirming the delta is confined to the per-tick observation and not to the
persona system prompt. This is a same-match-state comparison with zero residual variance, and it agrees with the
exhaustive string search above.

### 2b. PAYOUT + DISPLAY PRESENCE UNCHANGED — structural, and the cross-battery leg is provable

Both lanes declare `contracts.arena_id: foundry_60_asym_v1` and neither overrides `objective_scoring` or
`objective_display` anywhere.

- **Within-pair:** one single `arena_contract_hash` —
  `b693c2e02ef3d37d29bc0ab28c4fa9c22ec1bfa9fc0e2d13ef710dbc29f333a7` — across **all 62** `match_started` rows
  (32 prominent + 30 default), independently confirmed by the acceptance verifier (§5.3). Both lanes also share one
  `max_ticks` (1000), one prompt-content sha256, one programming-instructions sha256 and four persona-prompt
  sha256s across all 62 matches.
- **Cross-battery:** the clause asks that the hash also match "every other battery that has ever run on
  foundry_60_asym_v1 unmodified." No prior evidence document publishes that arena's hash, so a direct
  document-to-document comparison is not available. It is provable structurally instead:
  `contracts_data/arenas/foundry_60_asym_v1.yaml` has **exactly one commit in its entire history** — `91c21d7`
  (2026-07-23T01:30:04-04:00, "Phase 4 — objective VP victory, victory_kind classification, and the
  foundry_60_asym_v1 arena", #132) — and has never been modified since. The arena contract every prior
  `foundry_60_asym_v1` battery hashed is byte-identical to the one both lanes here hashed. The drift the clause
  exists to catch (`objective_scoring` or `objective_display` changing under the arm) is therefore excluded by the
  file's own history, which is a stronger check than comparing two published hex strings.

Corner identity is independently machine-readable from the ledger via `pilot_id`/`loadout_id`
(`…_salience_prominent_{berserker,sniper}` vs `…_default_…`), uniform within each corner and including both makeup
matches (acceptance §5.3) — so the two lanes cannot have been swapped.

---

## 3. CONTAMINATION GATE (pre-registered)

The clause requires `check_contamination_gate.py` to be run against **both** lanes and quoted verbatim before either
lane's counts are read. It was, in the acceptance report (§4.1), which is cited rather than re-run here:

- **default: exit 0.** Bijective — 30 `match_started` / 30 `match_ended` / 30 rows, 30 distinct seeds 5001–5030, 0
  duplicates, 0 gaps, 0 out-of-range, 0 `match_id` collisions.
- **prominent: exit 1**, on two `ended_not_in_raw` orphans — **reconciled and discharged** in acceptance §4.2–§4.5.
  Both orphans are *completed* matches (seeds 5018/5019) deliberately withheld from `battery_raw.jsonl` because a
  post-match, post-persistence Kafka forward failed during a transport outage; the driver's contamination-safety
  contract guarantees no row is written in that case. The gate models only two orphan classes and not this third
  one, so **the gate and the driver disagree by construction — a real gap in the gate, not in the lane**. Filed as
  **OMN-15377**.

**§4 of the acceptance report must travel with any citation of the prominent lane**, per that report's own standing
condition: a downstream reader who runs the gate cold and sees `exit 1` without §4 in hand will read a clean lane as
contaminated. The exclusion rule this scoring document applies (§Method) is the one that report specifies, and the
orphans contribute zero to the numerator regardless.

---

## 4. SECONDARY — H_SALIENCE_DISRUPTS_COMPLIANCE (pre-declared, not scored)

The pre-registration's third, escaped reading predicted that louder framing might degrade response-shape compliance,
"showing up as an increase in `llm_completion_failed` on the PROMINENT lane." Measured on scored rows only (the
filter matters — the two orphans add one failure and 523 requests to the unfiltered prominent ledger):

| | prominent | default |
|---|---:|---:|
| `llm_completion_requested` | 7,598 | 3,473 |
| `llm_completion_resolved` | 7,586 | 3,436 |
| `llm_completion_failed` | **12** | **37** |
| failure rate | **0.158 %** | **1.065 %** |

**The observed direction is the opposite of the predicted one: prominent's failure rate is ~6.75× *lower* than
default's.** There is no material increase on PROMINENT, so **H_SALIENCE_DISRUPTS_COMPLIANCE is not supported** —
neither by the loose qualitative standard the clause set, nor by any reading of these numbers.

Read with the discipline the clause asks for, three caveats:

- "Material" was deliberately left unthresholded, so this is a qualitative read, not a test. A 6.75× gap on 12 and
  37 raw events at n=30 is a rank ordering, not a calibrated effect.
- The reverse direction is **not** claimed as a finding. "Prominent rendering improves compliance" would need its own
  pre-registration; this arm pre-registered only a one-sided safety check and that check passes.
- Both lanes ran with the OMN-15239 bounded semantic-retry fix live (amendment `23a88d09`, 2026-07-27T13:58Z;
  earliest match 2026-07-27T20:49Z), applied identically to both, so the counter measures the same thing on both
  sides. The accounting closes on both lanes: `requested = resolved + failed`.

The pre-registration's own concern about the O-GATE precedent (11/413 completions in that battery answering an
imperative rule line with a malformed response) does not reproduce here. The PROMINENT rendering's one added
imperative-adjacent line (`REMINDER: …`) did not degrade response shape.

---

## 5. Negatives and what the number does not mean — first-class, not a footnote

The verdict is SALIENCE-EMERGENT. Everything in this section is a reason not to read more into it than it carries.
None of it changes the scored label; all of it changes what a reader should conclude.

### 5.1 The DV fires without pilot intent — this program's own strongest counter-evidence

`objective_scored` is an **engine positional event**: the fold awards VP when a mech holds a cell within 1,
uncontested, for a round. Nothing about it requires the pilot to have noticed, understood or intended the objective.

**The decisive in-repo evidence is this program's own SO-OBJ-MASK arm**
(`docs/evidence/2026-07-26-objmask-battery.md` §2a): with the objectives block **entirely absent from the prompt**
— pilots structurally unable to see objectives at all — that battery fired **14 `objective_scored` events across 5
of 30 matches**, *more* than the visible-display ASYM_OBJ corner's own 2, and its own report notes that 13 of 14
went to "the losing side, which still fought for and held objectives it was never told existed."

So a nonzero `PROMINENT_total` is **not by itself** evidence of objective-*directed* behaviour, and the
pre-registration's ALTERNATIVE READINGS item (2) — which chose this DV partly on the grounds that it is "directly and
only about objective-capture behaviour" — overstates the DV's specificity. That argument was already falsifiable
from MASK's published numbers at the time the pre-registration was written, and it was not caught. Recorded as a
defect in the arm's DV justification, not in its execution.

**What survives this objection, and it is not nothing:** seed 5006 reached the arena's 15-VP threshold and **won on
points** — the only `vp_threshold` terminal in either lane, and the only one this arm's family has produced on this
geometry (MASK: 0 VP terminals in 30; ASYM_OBJ: 0 in 30). Accumulating 15 VP requires sustained, repeated,
uncontested control across many rounds, which is a much harder outcome to reach by incidental occupancy than a single
award is. That is **one match**. It is suggestive of genuine objective-seeking under the prominent rendering; it is
not a result.

### 5.2 The zero is real, and short matches do not explain it

The default lane's matches are much shorter (median 59.5 vs 107.5 ticks; max 93 vs 300). The obvious deflationary
story is that default matches simply ended before objectives could be scored. **The data does not support that
story:**

| earliest tick at which any prominent capture occurred | default matches reaching that tick |
|---|---|
| 49 (seed 5020's first capture) | **20 of 30** |
| 62 (seed 5006's first) | **13 of 30** |
| 79 | 6 of 30 |
| 81 (seed 5029's first) | 5 of 30 |
| 99 (seed 5004's first) | **0 of 30** |

Twenty of thirty default matches ran at least as long as the tick at which prominent's earliest capture landed, and
thirteen ran past tick 62 — and **none of them ever scored, on any of the three objective cells, on either seat**.
Only one of the four prominent scoring windows (seed 5004's, ticks 99–107) lies entirely beyond default's longest
match. Every default row's `vp_totals` and `total_awards` is zero, all 30. The zero denominator is a real
measurement, not a truncation artefact.

### 5.3 Exposure normalisation — reported as a descriptive, and it cannot change the verdict

| | prominent | default |
|---|---:|---:|
| total ticks across 30 rows | 3,794 | 1,718 |
| `objective_scored` per 1,000 ticks | 8.962 | **0.000** |
| `objective_scored` per 1,000 completions | 4.475 | **0.000** |

Prominent had **2.21×** the total tick exposure. This qualifies the *magnitude* — "34 vs 0" partly reflects more
match-time, and the pre-registration scored an unnormalised pooled count, which this document computes as written.
It **cannot change the verdict**: every normalisation of a zero numerator is zero, so the escape's
`DEFAULT_total = 0` condition holds under any exposure denominator. The escape branch is robust to this choice; the
effect size is not, and no effect size is claimed.

These normalisations are **descriptives, not criteria.** Promoting one to the scored rule would be exactly the
goal-post movement the pre-registration's ALTERNATIVE READINGS section exists to prevent.

### 5.4 The corner-provenance confound is at its *worst* under this outcome

The pre-registration disclosed this confound honestly in advance and argued it away with a ratio:

> "A shared-infrastructure confound (e.g. an endpoint drift or model-version change between the two launches) could
> in principle move both lanes' absolute levels together without being visible in either lane alone. The RATIO `s`
> is more robust to this than either raw total would be, but it is not immune to it."

**That mitigation does not survive the outcome.** With `s` undefined, the escape hands the reader a **raw total** —
precisely the form the pre-registration identified as least robust to a between-launch shift. And the two lanes ran
**sequentially, not interleaved**: default 2026-07-27T20:49:16Z → 2026-07-28T05:34:45Z, prominent 05:35:07Z →
2026-07-29T03:20:37Z (plus a makeup window). Any endpoint-side drift across that boundary is **perfectly confounded**
with the manipulation.

The available controls are strong but do not close it: provider identity is a single constant `onex-local-coder-mlx`
across every window and both corners (acceptance §5.2); all three repo pins were frozen and verified
byte-identical before and after with zero drift, and the co-installed `omnimarket` is pinned to an immutable
commit id so it *cannot* drift (§6.1–§6.2); arena, prompt, persona and instruction hashes are single-valued across
all 62 matches (§5.3). What none of that controls is **model-server state** — restarts, KV-cache/batching state,
thermal or load conditions on the MLX endpoint across an eight-hour lane boundary. This is unclosable from the
artifacts. The honest mitigation is an **interleaved-corner replication**, which this arm did not run.

### 5.5 The two lanes diverge far more than the manipulation should predict — the biggest open question

Reported as descriptives; neither is pre-registered and neither is scored (acceptance §7.3 flagged that this needed
an explicit paragraph here rather than a silent table):

| | prominent | default |
|---|---|---|
| win split | **28 red / 2 blue** | **15 / 15** |
| median duration | 107.5 ticks | 59.5 ticks |
| max duration | 300 | 93 |

A one-line rendering change applied **symmetrically to both seats** producing a **28–2** asymmetry where the paired
lane is dead even is a large, unexplained effect, and it deserves to be stated as the arm's biggest loose end rather
than absorbed into the verdict.

One coherent single-mechanism story exists: red is the light scout/berserker and blue the heavy ironclad/sniper, and
this arena's own design notes describe blue's range advantage down a clear mid-lane sightline. If the prominent
rendering pulls **both** pilots toward objective cells, it drags the sniper off the standoff its advantage depends
on and into the brawler's effective range — which would simultaneously produce more red wins, longer matches, and
more contested objective cells. That is consistent with every number here.

**It is a hypothesis, not a finding.** This arm cannot distinguish it from the alternative that something other than
the manipulation differed between the two sequential lanes (§5.4). Testing it needs a purpose-built arm — an
interleaved-corner run, and ideally a positional/engagement-range DV rather than a capture count. Naming it here is
the honest disposition; claiming it would not be.

### 5.6 `PROMINENT_total` exceeds the pre-registration's own stated plausibility band

The pre-registration cited ASYM_OBJ (2 events / 30 matches) and SO-OBJ-MASK (14 / 30) as bounding "the plausible
ORDER OF MAGNITUDE for this metric on this arena/model family (single digits to teens per 30-match battery)."
**`PROMINENT_total = 34` is outside that band** — 2.4× the top of it. Flagged, not smoothed. Three non-exclusive
readings: (i) the effect is genuinely larger than the fixed reference context anticipated; (ii) the band was
measured on a different provider/model (qwen35 direct HTTP) and does not transfer, which the pre-registration itself
warned about when it refused to substitute ASYM_OBJ's rate as the denominator; (iii) the clumping (§1a) makes a
pooled count a poor scale for comparison against other batteries' pooled counts in the first place — MASK's 14 came
from 5 matches, this lane's 34 from 4. **This document does not choose between them.**

---

## 6. Verdict

**SALIENCE-EMERGENT**, under the pre-registered out-of-interval escape for `DEFAULT_total = 0`. Both seats
independently land on the same branch; the arm is not SEAT-SPLIT. The secondary safety check passes with the
opposite sign to the reading it was written to catch.

Adjudicating the two rival hypotheses the pre-registration named, on the evidence and no further:

- **H_SALIENCE_INERT is not supported.** It predicts that additional emphasis on an already-present, already-visible
  fact moves nothing. The paired lanes are 34 events across 4 matches versus 0 events across 30, on a byte-identical
  arena, byte-identical loadouts, byte-identical persona prompts, the same provider and the same seeds — with the
  only declared difference being the rendering of the objectives block, exhaustively verified as landed across all
  11,594 prompts (§2a). Default's zero is not a truncation artefact (§5.2). Saturation-by-mere-presence does not
  describe this data.
- **H_SALIENCE_DOSE_RESPONSIVE is directionally consistent but is NOT established.** The hypothesis is quantitative
  — "behaviour **scales** with display intensity" — and a scaling claim needs a ratio. The ratio does not exist, the
  escape is explicitly "unclamped" and "NOT folded into the 0-Inf ratio scale," and SALIENCE-AMPLIFIES was
  therefore not reachable on this data. Beyond that, the DV does not cleanly measure objective-*directed* behaviour
  (§5.1), the numerator is dominated by one match (§1a), the lanes ran sequentially so the corner-provenance
  confound is unmitigated (§5.4), and the lanes differ on unmeasured axes larger than the measured one (§5.5).
- **H_SALIENCE_DISRUPTS_COMPLIANCE is not supported** (§4), by a wide and opposite margin.

**The one-sentence version.** At fixed payout and fixed display presence, making the already-visible objectives block
louder is associated with objective-capture events appearing where the default rendering produced none — a
qualitative emergence, on both seats, that the pre-registration anticipated as a degenerate case and labelled in
advance; the *size* of that effect is not measurable from these artifacts, and its *mechanism* is not established by
them.

**The single most useful next experiment**, named because a scoring document that leaves a 28–2 divergence
unaddressed is incomplete: an **interleaved-corner** replication of this exact pair (alternating corners
seed-by-seed within one continuous provider process), which closes §5.4's confound at its root, and a DV that
separates objective-*seeking* from objective-*occupancy* — engagement range, or distance-to-objective over time —
which closes §5.1's.

---

## 7. Limitations

- **The primary statistic could not be computed.** `s` is undefined; the verdict rests entirely on a pre-declared
  qualitative escape. This is the pre-registration working as designed — it named `DEFAULT_total = 0` as a live
  possibility and pre-wrote the branch — but a reader should not treat SALIENCE-EMERGENT as equivalent in strength
  to a scored band. It is not a measurement of magnitude.
- **The DV is not intent-specific** (§5.1), and the pre-registration's own justification for choosing it was
  refutable from published in-repo evidence (MASK's 14 events with the display masked) at the time it was written.
- **n = 30 per lane, and the effective n on the numerator is 4.** One match supplies 53% of it. No significance
  claim is made, consistent with the pre-registration's STATISTICAL HONESTY clause and its rejection of a per-match
  z-test at this n.
- **Sequential, non-interleaved corners** leave the disclosed corner-provenance confound unmitigated in exactly the
  outcome where the ratio's robustness argument fails (§5.4). Provider identity and repo pins were constant and
  verified; model-server state was not and cannot be, from disk.
- **Two of thirty prominent rows are makeup draws** taken ~11–13 h after the other 28, in a second process
  (acceptance §3.5). Neither is one of the four scoring matches, so the numerator is untouched by the re-run; the
  residual is disclosed there in full and is not re-argued here.
- **The manipulation-landed gate was executed on a different surface than the clause named** (delegation artifact
  store rather than ledger rows), because the ledger does not persist prompt text on any arm in this program. The
  substitution is exhaustive and arguably stronger, but it is a substitution (§2a).
- **The contamination gate exits 1 on the prominent lane** — a false positive from a gate that does not model the
  ended-but-withheld orphan class, discharged in acceptance §4 and filed as OMN-15377. Any citation of this lane
  must carry that section.
- **`check_preregistration_timing.py` reports a false VIOLATION against current `main`** (§0c) because a post-run,
  execution-infrastructure-only amendment touched the overlay. The gate must be run against the executing
  snapshot's ancestry.
- **One model, one arena, one seed set, one non-card match path.** Qwen3.6-35B-A3B-8bit on both seats,
  `foundry_60_asym_v1`, seeds 5001–5030, plain per-tick `decide()` only. Card mode is out of scope by the
  pre-registration's own explicit scoping, not silently skipped.
- **Only one of the arena's three objective cells was ever captured**, in either lane. Whatever this arm measured, it
  measured at `objective.east_gate`.

---

## 8. What this does and does not close on OMN-15172

OMN-15172's acceptance gate has three legs: **(a)** infra-side golden chain green, **(b)** steel-side driver test
green, **(c)** the live display-salience arm #1 run end-to-end through the delegation-routed, bus-forwarded path
with an `event_ledger` row as terminal proof.

**This document closes the *scoring* of leg (c)'s arm, and nothing else.** Leg (c)'s artifact acceptance and its
live `event_ledger` read-back are closed by the companion acceptance report (PR #231). This document adds the
pre-registered analysis that report deliberately withheld.

**It does not adjudicate legs (a) or (b)** — those are **OMN-15169** and **OMN-15170** respectively, and both remain
**unadjudicated by this document**. Nothing here should be read as evidence for either.

**No Done-flip is claimed or authorized.** As recorded in acceptance §9, `dod_verify` for OMN-15172 returned
`status: skipped` on 2026-07-29 — no DoD contract exists for the ticket on `onex_change_control` `main` or `dev`, so
zero checks were verified. Under the standing rule that Done-flips route only through `dod_verify` with durable
evidence, the ticket stays where it is until a contract exists and verifies.

**It does not decide OMN-15174** (the deferred ~53-overlay delegation-migration candidate, explicitly gated on "the
OMN-15172 acceptance run"). This arm is the single migrated arm that gate was waiting on, so its operational record
is the relevant input — stated in both directions, and decided by nobody here:

*For migration.* The delegation path worked end-to-end and is provable: 11,594 live completions across 60 matches,
`replay_validity == 1` on all 120 seat-entries, all four terminal events forwarded on every published match, and
broker-side arithmetic closure on `.201` (244 rows over 62 match keys = 60×4 + 1 + 3, consumer group Stable, LAG 0).
Semantic-failure rates were 0.158 % (prominent) and 1.065 % (default). Nothing about the binding corrupted a result.

*Against migrating now.* The cost of migrating **one** arm was three defects and two discarded battery runs —
OMN-15239 (a single semantic rejection killed a whole match; burned 20 of 30 seeds), OMN-15240/OMN-15265 (mid-run
`omnimarket` drift; burned another 20 of 30), and OMN-15377 (the contamination gate cannot model the orphan class the
delegation path's own bus-forward failure produces). Two structural properties remain live: a completed, fully
persisted match is still **discarded** when its post-match Kafka forward fails (this run lost seeds 5018 and 5019 to
a `.201` reboot, and the makeup re-runs are fresh draws, not recoveries — acceptance §3.5), and throughput is heavy:
**8.7 h for 30 default matches (17.5 min/match) and 21.8 h for the prominent lane (43.5 min/match)**, wall-clock,
one seed at a time.

**Evidence-based reading, offered as input and not as a decision:** the gating condition is only partly discharged.
The acceptance run happened and its artifacts were accepted, but OMN-15172 itself is not closed (`dod_verify`
returned `skipped`; legs (a)/(b) are unadjudicated), so "after the OMN-15172 acceptance run" has not fully arrived.
On the merits, migrating 53 more overlays today would replicate the discard-on-forward-failure exposure and the
per-match wall-clock across the entire evidence corpus, for no measured gain in evidence quality — the two lanes'
results are as trustworthy as any `OpenAICompatibleClient` arm's, not more so. The cheap sequencing is to keep
`OpenAICompatibleClient` as the supported binding, land OMN-15377 and a durable-buffer/retry on the post-match
forward so a transport blip cannot discard a completed match, and only then reassess — ideally against a measured
throughput comparison, which no arm has yet produced.

---

## 9. Reproduction commands

```bash
SNAP="$HOME/.omnibase/battery_envs/omn15172-hermetic-20260727"
ROOT="$SNAP/battery_state/omn15172_acceptance_rerun2"

# §0b pre-registration timing gate (run against the SNAPSHOT repo — see §0c)
for c in prominent default; do
  python3 "$SNAP/steel_onslaught/scripts/check_preregistration_timing.py" \
    --state-root "$ROOT/$c" \
    --overlay "$SNAP/steel_onslaught/contracts_data/overlays/foundry_60_asym_v1_salience_${c}_delegation.yaml"
done

# §1 primary + seat split, filtered to the 30 scored rows, read-only immutable
python3 - <<'PY'
import sqlite3, json, os, collections
ROOT=os.path.expanduser("~/.omnibase/battery_envs/omn15172-hermetic-20260727/battery_state/omn15172_acceptance_rerun2")
for corner in ("prominent","default"):
    raw=[json.loads(l) for l in open(f"{ROOT}/{corner}/battery_raw.jsonl")]
    scored={r["match_id"] for r in raw}
    con=sqlite3.connect(f"file:{ROOT}/{corner}/events.sqlite3?immutable=1", uri=True)
    seat=collections.Counter()
    for mid,pj in con.execute("select match_id,payload_json from events where event_type='objective_scored'"):
        if mid in scored:
            seat[json.loads(pj)["controlling_player_id"]]+=1
    print(corner, "total:", sum(seat.values()), dict(seat),
          "| total_awards sum:", sum(r["total_awards"] for r in raw))
PY

# §2a manipulation-landed gate: string search over every captured prompt
python3 - <<'PY'
import os, json, collections
ROOT=os.path.expanduser("~/.omnibase/battery_envs/omn15172-hermetic-20260727/battery_state/omn15172_acceptance_rerun2")
for corner in ("prominent","default"):
    c=collections.Counter()
    for dirpath,_,files in os.walk(f"{ROOT}/{corner}/delegation_state/artifacts"):
        for f in files:
            txt=open(os.path.join(dirpath,f),errors="replace").read()
            if '"prompt_text"' not in txt: continue
            pt=json.loads(txt).get("prompt_text")
            if not isinstance(pt,str): continue
            c[("PROM" if "!!! OBJECTIVES" in pt else "")+("DEF" if "--- OBJECTIVES" in pt else "") or "NEITHER"]+=1
    print(corner, dict(c))
PY

# §2a controlled prompt-length delta: tick<=1 only, constant per (corner, persona)
python3 - <<'PY'
import sqlite3, json, os
ROOT=os.path.expanduser("~/.omnibase/battery_envs/omn15172-hermetic-20260727/battery_state/omn15172_acceptance_rerun2")
for corner in ("prominent","default"):
    scored={json.loads(l)["match_id"] for l in open(f"{ROOT}/{corner}/battery_raw.jsonl")}
    con=sqlite3.connect(f"file:{ROOT}/{corner}/events.sqlite3?immutable=1", uri=True)
    by={}
    for mid,pj in con.execute(
        "select match_id,payload_json from events "
        "where event_type='llm_completion_requested' and tick<=1"):
        if mid in scored:
            p=json.loads(pj); by.setdefault(p["persona_id"],set()).add(p["user_prompt_length"])
    print(corner, {k:sorted(v) for k,v in sorted(by.items())})
PY

# §0c criterion region is byte-identical across every commit that touched the overlay
python3 - <<'PY'
import subprocess, hashlib
P="contracts_data/overlays/foundry_60_asym_v1_salience_prominent_delegation.yaml"
for sha in ["f9b11aea","23a88d09","985ca70c","c6c3bcd"]:
    t=subprocess.run(["git","show",f"{sha}:{P}"],capture_output=True,text=True,check=True).stdout.splitlines()
    i=next(k for k,l in enumerate(t) if l.startswith("# PRE-REGISTERED HYPOTHESIS"))
    j=next(k for k,l in enumerate(t) if l.startswith("# CORNER PROVENANCE NOTE"))
    print(sha, hashlib.sha256("\n".join(t[i:j]).encode()).hexdigest()[:16], f"lines={j-i}")
PY

# §2b arena file has exactly one commit in its history
git -C "$SNAP/steel_onslaught" log --format="%h %aI %s" -- contracts_data/arenas/foundry_60_asym_v1.yaml
```

---

## Citations (all relative paths)

- **Companion acceptance report (separate deliverable, PR #231):**
  `docs/evidence/2026-07-29-display-salience-arm1-acceptance-battery.md` — artifact acceptance, contamination
  reconciliation (§4), split-window provenance (§5), pins + broker/`event_ledger` read-back (§6), the 5018/5019
  skip-and-makeup record (§3). Its §4 must travel with any citation of the prominent lane.
- **Pre-registration:** `contracts_data/overlays/foundry_60_asym_v1_salience_prominent_delegation.yaml` header
  (commit `f9b11aea61e48cbddc40ddaac844c25814375127`, 2026-07-26T18:24:21-04:00, #223, OMN-15166), amended
  `23a88d09051565270f76cade8bc7b685cd790f38` (2026-07-27T09:58:25-04:00, #225, OMN-15239) — the executing ancestry —
  and subsequently `375c98015463b794c46dde59fca91c5805d19312` (2026-07-28, #229, OMN-15265, post-run, future-runs-only;
  see §0c). Paired lane: `contracts_data/overlays/foundry_60_asym_v1_salience_default_delegation.yaml`.
- **Method gates:** `scripts/check_preregistration_timing.py` (exit 0, both corners, quoted verbatim §0b),
  `scripts/check_contamination_gate.py` (default exit 0; prominent exit 1, discharged — acceptance §4), both merged
  in #207.
- **Mechanism:** `src/steel_onslaught/llm/pilot.py` (`SODisplaySalience` branch in `_serialize_observation`),
  `src/steel_onslaught/contracts/pilot.py` (`SODisplaySalience`). Held-fields test:
  `tests/contracts/test_display_salience_overlays_omn15166.py`. Rendering tests: `tests/llm/test_llm_pilot.py`
  display-salience section.
- **Arena under test:** `contracts_data/arenas/foundry_60_asym_v1.yaml`, single commit `91c21d7` (#132), never
  modified; `arena_contract_hash b693c2e0…`, one value across all 62 `match_started`.
- **Pilots / loadouts:** `contracts_data/pilots/delegation_salience/llm_delegation_{berserker,sniper}_{prominent,default}.yaml`,
  `contracts_data/loadouts/delegation_salience/{red,blue}_{prominent,default}.yaml`.
- **Fixed reference context (cited, not re-measured):** ASYM_OBJ 2/30 —
  `docs/evidence/2026-07-25-objdecoy-asym-battery.md` §2a; SO-OBJ-MASK 14/30 across 5 matches —
  `docs/evidence/2026-07-26-objmask-battery.md` §2a (also the source of §5.1's counter-evidence and of the §2a
  precedent for a pre-registered clause the ledger cannot literally execute, its own §2b).
- **Tickets:** OMN-15172 (acceptance gate, leg c), OMN-15166 (arm mechanism + pre-registration), OMN-15239
  (bounded semantic retry), OMN-15240 / OMN-15265 (drift preflight + mid-run belt), OMN-15377 (contamination-gate
  orphan class), OMN-15169 / OMN-15170 (legs a / b — unadjudicated here), OMN-15174 (deferred migration decision —
  not decided here).
- No secrets, keys, or absolute developer-machine paths included.

*Every figure in this document was computed from a named artifact by a command reproduced in §9. No claim rests on
an agent self-report, and no figure was taken from any `battery_summary.json`.*
