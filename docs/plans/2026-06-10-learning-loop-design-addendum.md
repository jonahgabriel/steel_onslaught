---
date: 2026-06-10
status: design-addendum
extends: 2026-04-30-steel-onslaught-design.md
summary: The §19 learning loop implemented as bounded parameter search over the tunable-pilots spec space, with the OmniNode platform's experiment discipline (paired comparisons, exact sign tests, negative controls, capsule identity, effectiveness decay, context authority) imported wholesale — making the game the cheap, deterministic, replay-proven testbed for the closed behavior-augmented feedback loop the platform does not yet have anywhere.
---

# Steel Onslaught — Learning Loop (Design Addendum)

## 1. Executive Summary

Design §19 promises a learning loop: collect traces → generate candidates → run vs parent → run vs hidden scenarios → reject or promote → emit a versioned promotion event. The tunable-pilots addendum (`2026-06-10-tunable-pilots-design-addendum.md` §8) made that loop's search space well-defined — "candidate generation becomes parameter search over the bounded spec space" — and explicitly deferred executing any search. This addendum is that deferred execution, specified.

**Core thesis:** the §19 learning loop is a bounded parameter search over the pilot spec space, governed end-to-end by the platform's experiment discipline. Candidate generation, evaluation, promotion, and lineage are each mapped one-to-one onto mechanisms the platform has already proven or specified:

- evaluation = paired candidate-vs-parent duels over fixed seed batteries, scored with the exact binomial sign test the June 8 platform experiment used (`docs/research/2026-06-08-behavior-augmented-context-research-plan.md` in `omni_home`);
- promotion = design §18's minting rules as code, including §23.1 hidden evaluation;
- lineage = §18.2's record plus the research plan's capsule-identity and effectiveness-decay disciplines;
- candidate generation = a deterministic baseline arm now, and (Phase 3) LLM-proposed candidates under the context-arm matrix of the platform's context-ROI plan (`docs/plans/2026-06-07-context-roi-fast-follow-plan.md` in `omni_home`).

**Why this matters beyond the game.** The platform research plan's first surviving open problem is blunt: *"Live closed loop. Everything proven is fixture/replay. No production path feeds real outcomes back onto stored context."* Steel Onslaught can close that loop first, cheaply, because it removes every confound the platform fights: the evaluator is deterministic (same seed → same outcome, bit-identical, replay-proven by MVP Task 27/34), outcomes are ground truth (a duel result, not an LLM-judged rubric), trials cost CPU-milliseconds instead of inference dollars, and the search space is small, bounded, and typed. The game is the testbed where "measure the behavioral effect, store it against a stable identity, let future selection rank by it" runs end-to-end before the platform attempts the same loop on generation tasks.

Scope discipline: this addendum specifies the loop. Its Phase 1 companion plan (`2026-06-10-learning-loop-phase1-plan.md`) builds only the seam-bound pure logic — protocols, statistics, search strategies, promotion gate, lineage records — with zero dependency on the in-flight MVP code. Everything that touches the real game engine is Phase 2+.

## 2. Relationship to Prior Documents

- **Extends** the 2026-04-30 design (`docs/plans/2026-04-30-steel-onslaught-design.md`). §N references below point there, chiefly §18 (Lineage and Minting), §19 (Learning System), §23 (Anti-Exploit), §23.1 (Hidden Evaluation).
- **Builds on** the tunable-pilots addendum (`2026-06-10-tunable-pilots-design-addendum.md`): the search space IS `ModelSOPilotSpec.parameters` with the §5 bounds tables; the evaluator IS the balance-harness machinery of the tunable-pilots implementation plan Task 6 (`so balance`, round-robin over seeds). Pilot spec semantics, bounds, and the golden behavioral invariant are normative there and are not restated.
- **Depends on** (for Phase 2 execution, not for Phase 1): the 2026-04-30 MVP plan fully merged, and tunable-pilots Tasks 1–5 merged (Task 6 strongly recommended — the evaluator binds to its match-running machinery).
- **Imports discipline from** three OmniNode platform documents (read-only references; this repo does not modify them):
  - `omni_home/docs/plans/2026-06-07-context-roi-fast-follow-plan.md` — the attempt-reduction experiment design (factor arms, K trials, variance, negative control, per-row metadata).
  - `omni_home/docs/research/2026-06-08-behavior-augmented-context-research-plan.md` — capsule identity, effectiveness decay, the Context Authority Rule, "hypotheses from observation, claims from intervention."
  - `omni_home/docs/plans/2026-06-10-full-feature-closure-and-statistical-proof-plan.md` — statistical acceptance gates and the no-overclaim rules, adapted near-verbatim in §4 and §9 below.
- **Does not modify or renumber** the MVP plan or the tunable-pilots plan. No event schema changes, no new `SOEventType` members, no payload changes anywhere in this work (Phase 1 emits no events at all; Phase 2 reuses existing match machinery unchanged).

## 3. Candidate Generation

### 3.1 The search space

A candidate is a complete `ModelSOPilotSpec` parameter assignment for one archetype, inside the tunable-pilots §5 bounds. Nothing else is searchable: rule ordering, decision-tree shape, and the predictive lookahead window are structural and code-owned (tunable-pilots §5.3); match physics is reducer-owned (§4.2 of the base design). The search space per archetype is the cartesian product of 4–5 bounded parameters — small enough that grid enumeration at coarse step is feasible and hill-climbing converges in tens of evaluations, which is the point: the loop's mechanics get proven where exhaustive verification is possible.

### 3.2 Baseline arm: deterministic search (no LLM)

The first and permanent candidate generator is deterministic, seeded, and free:

- **Grid** — exhaustive enumeration of the bounded lattice (parameter values quantized to each bound's step), in canonical order.
- **Greedy hill-climb** — from a parent spec, propose all single-parameter neighbors at a fixed step schedule (coarse → fine multipliers), evaluate, move to the best significant winner, repeat until no neighbor wins.
- **Random restart** — seeded PRNG draws of full parameter assignments on the lattice, for escaping local optima. Seeded `random.Random` only; no wall-clock, no global random state — the candidate sequence for a given seed is reproducible forever.

This arm is the experiment's control in the exact sense the context-ROI plan uses `off`: it establishes how many evaluations and how much cost a *contextless, modeless* searcher needs to find a promotable spec.

### 3.3 Experiment arms (Phase 3, future): LLM-proposed candidates

Phase 3 adds an LLM candidate generator (local model first, Gemini/cloud via routing as configured) and runs the context-ROI plan's question against deterministic ground truth: **does the right context reduce the attempts needed to reach a working (here: promotable) solution?** The context arms mirror the ROI plan's factor matrix, translated into the game's native artifacts:

| Arm | Context given to the LLM tuner | ROI-plan analogue |
|---|---|---|
| `llm_off` | task statement only (archetype, bounds, parent params, "propose a better spec") | `off` baseline |
| `llm_replay_trace` | + replay decision trace of the parent's lost duels (per-tick `pilot_decision_made` payloads from the ledger) | golden chain (the event-stream evidence) |
| `llm_decision_diff` | + decision diff: where the parent's decisions diverged from the winning opponent's on the same seeds | local failures |
| `llm_exemplar` | + exemplars: promoted lineage records (winning specs + their parameter deltas vs their parents) | exemplar |
| `llm_full_design_doc` | the full game design doc as context — **NEGATIVE CONTROL**, expected wasteful per the platform finding that full-document guidance is harmful as injected context | `full_guidance_negative_control` |

**Measured outcomes:** `attempts_to_promotion` (candidate evaluations consumed until the gate promotes) and `cost_per_promotion` (inference cost for LLM arms; compute-only for the baseline arm), per arm, with K-trial variance. The deterministic baseline arm of §3.2 is always run alongside as the floor. Every Phase 3 experiment carries the negative-control arm — a run without one is not a valid effectiveness experiment (research plan, theme 4, elevated to a hard requirement here).

What makes this a better experiment than the platform can currently run: the evaluator is noiseless. On the platform, a "winning factor may actually be a model/endpoint artifact" and per-cell n is chronically underpowered; here, given a candidate spec, its win rate over a fixed seed battery is a deterministic function — the only randomness is in the generator, exactly where the experiment wants it.

## 4. Evaluation

### 4.1 Paired comparison on identical seed sets

Evaluation is head-to-head: the candidate duels its parent, both fielding the **same loadout** (chassis, boiler, modules — only the pilot parameters differ), over a fixed battery of match seeds. Each seed is one paired trial; candidate and parent face identical conditions by construction. Per-seed outcome is `candidate | parent | draw`.

Phase 2 evaluator requirement (recorded here, binding then): each seed runs the duel **twice with sides swapped** (red/blue) to cancel spawn-position asymmetry; the per-seed outcome aggregates the pair (win both → win; split or double-draw → draw). The Phase 1 evaluator protocol is agnostic to this — it sees one outcome per seed.

### 4.2 The statistic: exact binomial sign test

Draws (ties) are excluded; over the n decisive seeds, the two-sided exact binomial sign test (stdlib `math.comb`, no scipy) gives the p-value that candidate and parent are equally strong. Alongside p: the candidate's decisive win rate, its **Wilson 95% confidence interval**, the effect size (win rate − 0.5), and the explicit n. Significance threshold: **p ≤ 0.05**.

This is byte-for-byte the test behind the platform's strongest existing evidence. Known-value anchor (verified arithmetic, used as a test vector in the Phase 1 plan): the June 8 experiment's 14 context-wins / 2 off-wins / 34 ties gives n = 16 decisive, two-sided exact p = 274/65536 = **0.004180908203125** — the published "p = 0.0042" is this value rounded. The phase-2 stress vector 8/0/22 gives p = 2/256 = **0.0078125** ("p = 0.0078").

### 4.3 No-overclaim rules (adapted verbatim)

From the full-feature-closure plan's statistical acceptance gates, adapted to the game:

- **A single seed battery is not a claim.** One candidate-vs-parent run informs the search; promotion claims require the full gate (§5) including held-out seeds.
- **Per-cell n < 10 is exploratory.** Fewer than 10 decisive (tie-excluded) paired comparisons cannot support a definitive promotion; the gate rejects with `insufficient_decisive_n` regardless of p-value.
- Every significance claim states **p-value, effect size, confidence interval, and explicit n** — never a bare "candidate is better."
- **Pooled claims state exactly what was pooled** (which seed batteries, which sides).
- Draws are reported, never silently dropped from the denominator narrative (they are excluded from the sign test, but `draw_rate` is a first-class secondary metric — §5).
- **Hypotheses from observation, claims from intervention:** lineage history is observational; only a controlled candidate-vs-parent run on declared seed sets supports a promotion or an arm-effectiveness claim.

## 5. Promotion Gate (§18 rules as code)

Design §18: a pilot may be minted only if it passes validation, has replayable match evidence, improves a meaningful metric, doesn't regress beyond thresholds, isn't a trivial clone, and has a clear lineage parent. The gate implements each rule as an explicit check with an explicit verdict; all failures are reported (not first-fail), mirroring the MVP budget validator's multi-violation style.

| §18 / §23.1 rule | Gate check |
|---|---|
| passes validation | Candidate parameters inside the tunable-pilots bounds. An out-of-bounds candidate is a generator bug and **raises** (fail fast) — bounds are the contract gate (tunable-pilots §9), not a promotion verdict. |
| improves a meaningful metric | `candidate_wins > parent_wins` AND sign-test `p ≤ 0.05` AND decisive `n ≥ 10` on the search battery. |
| doesn't regress beyond thresholds | Secondary metrics: candidate overload rate must not exceed parent overload rate by more than a configured threshold; draw rate of the pairing must not exceed a configured absolute cap (anti-draw-farming, §23). |
| isn't a trivial clone | Normalized parameter distance (L∞ over per-parameter deltas scaled by bound width; categorical params distance 1 if different) must meet a configured minimum. A candidate with identical parameters to its parent is rejected `trivial_clone`. |
| has a clear lineage parent | Parent spec (and its hash) is a required gate input; the emitted record always names it. |
| §23.1 hidden evaluation | A **held-out seed set, disjoint from every seed used during search**, never consumed by any generator or intermediate comparison. The candidate must not regress on it (`candidate_wins ≥ parent_wins` on holdout). Overlapping search/holdout seed sets are a harness bug and raise. |
| replayable match evidence | Both seed sets are recorded in the lineage record; Phase 2 retains the per-match ledgers so every recorded outcome is reconstructible (§21 replay is reconstruction). |

Verdict: `promoted` or `rejected` with the complete ordered list of rejection reasons. Every verdict — including every rejection — emits a versioned lineage record (§6): rejections are evidence too (§19's pipeline explicitly includes "reject if exploit/regression").

The hidden seed set rotates only deliberately: reusing one holdout battery across many candidates of the same lineage progressively leaks it (each promotion conditions the next search on specs that passed it). Phase 2 policy: derive the holdout battery per lineage generation from a master seed, record it in the lineage record, and never reuse a generation's holdout as a later generation's search battery.

## 6. Lineage Record

The lineage record is design §18.2's contract plus the research plan's capsule-identity discipline. `ModelSOLineageRecord` (full schema in the Phase 1 plan, Task 1) carries:

- **`spec_hash`** — SHA-256 over the canonical JSON (`sort_keys`, compact separators) of `{archetype, parameters}`. This is the capsule-identity rule applied to specs: **a changed spec is a new identity; history does not transfer.** Effectiveness, promotion standing, and evidence attach to the hash, never to a display name or file path. (Tunable-pilots §4.3 already states "the fork is a complete spec, not a diff" — the hash makes that mechanical.)
- **`parent_hash`** — the parent's spec hash. With `spec_hash`, this gives the §18 ancestry graph content-addressed identity.
- **`evidence`** — the search seed battery and the held-out seed battery (explicit integer lists), so any third party can re-run both and reproduce every outcome bit-identically.
- **`performance`** — candidate decisive win rate, win-rate delta, overload-rate delta, draw rate, p-value, decisive n: §18.2's `performance_delta` block with the statistical fields §4 requires.
- **`promotion`** — status + complete rejection reasons.
- **`generator`** — provenance per the authority rule (§7): generator identity, selection reason, experiment cohort.
- **`meta_hash`** — effectiveness decay, below.

**Effectiveness decay via `meta_hash`.** The research plan: "patterns age… a capsule whose surrounding code has drifted loses standing until re-measured." The game's analogue of drifting surrounding code is the **opponent pool — the meta**. A spec promoted by beating its parent (and, Phase 2, the template baselines) holds standing only relative to the pool it was evaluated against. `meta_hash` = SHA-256 over the sorted set of opponent spec hashes the evidence covers. When the live pool's meta hash differs from a record's, that record's standing is **stale**: the spec is not stripped of its promotion (the historical claim stays true and replayable), but it re-enters evaluation before being treated as a current champion — decayed standing feeds re-trial, exactly the explore/exploit role decay plays in the platform design.

Deliberate deviation from §18.2: the Phase 1 record carries no `promoted_at` timestamp. The promotion gate is pure and deterministic; wall-clock attribution is an effect-layer concern and gets added where the record is persisted (Phase 2), never defaulted inside the pure model.

## 7. Search Authority Rule (Context Authority Rule, adapted)

The research plan's Context Authority Rule, applied to candidate generation:

> **Rule:** No search strategy, context factor, or candidate source is hardcoded into the loop. Every candidate records, on its lineage record: `generator_id` (e.g. `search.grid`, `search.hill_climb`, `search.random_restart`, `llm.<model>@<arm>`), `selection_reason` (why this candidate was proposed — e.g. `hill_climb_neighbor:vent_at_heat_margin-1`, `grid_enumeration`, `llm_proposal`), and `cohort` (the experiment cohort, when arm-forced).
>
> **Experiment exception:** controlled experiment arms (§3.3) may force a generator/context factor for measurement, but must label `selection_reason = experiment_assignment` and record the cohort. Forced assignment is allowed only under an experiment cohort — never as a silent loop default.

This is what keeps the loop honest when Phase 3 arrives: "always use the LLM tuner" baked into the loop would be exactly the hidden authority no effectiveness measurement can correct. The loop selects generators by measured `attempts_to_promotion` / `cost_per_promotion`, and every selection is auditable per record.

## 8. Phasing (honest about dependencies)

**Phase 1 — NOW, parallel-safe (the companion plan).** Seam-bound pure logic only: evaluator/spec protocols, lineage record + canonical hashing, sign test + Wilson CI + paired-comparison summary, deterministic search strategies, promotion gate. Runtime imports limited to stdlib + pydantic; every game-engine touchpoint is behind a `Protocol`; the only evaluator is a deterministic table-driven fake. **New files only** — `src/steel_onslaught/learning/`, `tests/learning/`, and `src/steel_onslaught/contracts/lineage.py`, none of which is claimed by any MVP-plan or tunable-pilots-plan task (verified against both plans' file lists and against the in-flight `jonah/steel-onslaught-mvp` branch tree). Phase 1 therefore proceeds in parallel with the MVP build without merge risk.

**Phase 2 — after the MVP and tunable-pilots plans merge.** Bind the seams to the real game: a `RealEvaluator` satisfying `EvaluatorProtocol` by running side-swapped duels via the match entrypoint/balance-harness machinery (tunable-pilots Task 6); a `SpecLike` adapter over `ModelSOPilotSpec` (parameters via `model_dump`, bounds derived from the parameter models' field constraints — single source, no retyped bounds tables); the loop driver composing search → evaluate → stats → gate → record; `so learn` CLI (`so learn --archetype aggressive --parent <spec> --strategy hill_climb --seeds N --holdout M`); lineage records persisted as YAML under `contracts_data/lineage/` keyed by spec hash; per-match ledgers retained as replay evidence.

**Phase 3 — post-hackathon.** The LLM tuner and the §3.3 context-arm experiment, with model/endpoint identity resolved per configured routing (never hardcoded — §7). Each experiment row exports in a shape compatible with the platform's `node_context_roi_compute` row schema (`attempt_count`, `first_pass_success`, `final_success`, token/cost fields, `model_id`, `provider`, `context_factor_subset`, `run_id`/`correlation_id`, plus `context_pack_hash`-equivalent: the arm's context manifest hash), so game-generated evidence can flow into the platform's N-arm scoring pipeline as an additional, deterministic-ground-truth task family.

## 9. Anti-Exploit and Non-Goals

- **The gate inherits §23 wholesale.** Draw-farming and stall configurations are doubly excluded: the tunable-pilots bounds exclude the degenerate parameter regions, and the gate's draw-rate cap rejects pairings that stall anyway. Self-damage farming cannot arise (pilots cannot bypass physics; §4.2). Collusive farming is out of scope until there is a population (Phase 3+).
- **Searching the evaluator is the new exploit surface.** A candidate that overfits the search battery is the game's version of training-set leakage; the §23.1 holdout check is the defense, and holdout rotation (§5) prevents slow leakage across generations.
- **No live-match mutation** (§4.5 unchanged): learning runs offline against ledger-backed evaluations; promoted specs enter play only by being fielded in new matches.
- **Non-goals:** no LLM execution in Phases 1–2; no new event types or payload changes; no reinforcement learning, no gradient methods, no policy networks — the §19 loop here is spec-space search, deliberately; no minting marketplace/economy semantics (§17/§25); no modification of any platform (`omni_home`) document or pipeline.
