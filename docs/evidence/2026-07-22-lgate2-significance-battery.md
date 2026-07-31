# L-GATE-2 significance battery + first live `selection_outcome_v1` run — 2026-07-22

Follow-up to `docs/evidence/2026-07-22-lgate2-adaptation-battery.md` (#126). That
battery PROVED the audit half of L-GATE-2 (provenance → promotion → lineage →
replay-valid chain, 21/21 matches) but left the behavioral half open: the
n=10+10 blue-sniper run showed only a weak, direction-mixed shift (attack keep
ceilinged at 0.997 pre-learning; vent keep moved +8.3pp AGAINST the aggression
direction, t≈3.15).

This document reports two runs with clean single-knob attribution:

- **RUN A** — significance rerun of the `win_damage_differential_v1` battery
  with the documented knob changes: learning seat moved to the **red berserker**
  (headroom on movement/vent instead of a ceilinged attack keep), perturbation
  step raised to **0.5** (aggression 1.0 → 1.5), **n=30 baseline + promote +
  n=30 post**.
- **RUN B** — first live run of the **`selection_outcome_v1`** evaluator lane
  (evidence-directed candidate + offline duel gate), small n: a spine proof for
  the real judgment path, not an effect-size claim.

Driver: `scripts/run_lgate2_adaptation_battery.py` (extended in this PR with
`--mode battery|live-fire`, `--seat blue|red`, `--step`, and the `--lf-*`
live-fire knobs; measurement instruments unchanged from #117/#126).

## Method

### RUN A (battery mode)

```
uv run python scripts/run_lgate2_adaptation_battery.py \
    --mode battery --seat red --step 0.5 --n 30 --fresh \
    --state-root .onex_state/steel_onslaught/lgate2_significance_battery
```

- Overlay `contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml`
  (over-deal 8 → program 5, both seats qwen35, live keyless endpoint).
- Learning seat: `player.red` / `mech.red.01` (berserker persona
  `pilot.llm.qwen35`); opponent: blue sniper (`pilot.llm.qwen35_sniper`).
- Chain label: archetype `aggressive`, parameter `aggression`, genesis 1.0.
- Phases exactly as #126: baseline (cap = genesis, promotion impossible,
  n=30, seeds 4001–4030) → promote (cap lifted, run to first
  `POLICY_PROMOTED`, seeds 4101+) → post (cap frozen at 1.5, generation 1,
  n=30, seeds 4201–4230).
- Instruments (#117): per-category keep-rates (planned/dealt) and planned
  category shares for the learning seat, read from the canonical event
  ledger; audit chain verified inline (per-seat MATCH_STARTED provenance,
  POLICY_PROMOTED payload, lineage record existence, per-match replay
  validity).
- Statistics: per metric, Welch two-sample t-test (baseline vs post
  per-match values, two-sided, α = 0.05) + Cohen's d (pooled SD). Computed
  from `battery_raw.jsonl` with no per-match exclusions (matches where a
  category was never dealt contribute no keep-rate sample for that
  category, same rule as the driver's summary).

### RUN B (live-fire mode)

```
uv run python scripts/run_lgate2_adaptation_battery.py \
    --mode live-fire --seat red --lf-matches 8 --fresh \
    --state-root .onex_state/steel_onslaught/lgate2_live_fire
```

- Same live overlay and seats. Live-learning binding kind
  `selection_outcome_v1`: archetype `aggressive`, complete spec-parameter
  genesis from `contracts_data/pilots/template_aggressive.yaml`
  (`vent_at_heat_margin=5`, `idle_vent_heat_threshold=90`,
  `mode_switch_pressure_floor=12`, `mode_switch_heat_ceiling=80`,
  `weapon_preference=highest_damage`), perturbed parameter
  `vent_at_heat_margin` (int lattice, step 1, bounds [2, 20] — headroom in
  both directions from 5).
- Duel gate: `base_loadout_path=llm_qwen35_berserker.yaml` (both duel sides
  field it; only the deterministic pilot spec differs),
  `n_search_seeds=2`, `n_holdout_seeds=2`, `duel_max_ticks=200`.
- **Threshold overrides, declared up front:** `min_decisive_n=1`,
  `p_value_max=1.0`, `max_draw_rate=1.0`. The offline defaults
  (`min_decisive_n=10`, `p≤0.05`) make a 4-seed live gate a *guaranteed*
  vacuous decline; these overrides keep the gate real (the parent can still
  win the duels and force a decline) while making promotion reachable. The
  remaining default (`max_overload_rate_increase=0.05`,
  `min_param_distance=0.05`) stay in force. `vent_at_heat_margin` 5→4 or
  5→6 is |Δ|/span = 1/18 ≈ 0.056 ≥ 0.05, so the param-distance rule is
  satisfiable but not vacuous.
- Protocol: run up to 8 live matches; every non-draw terminal fires the
  real evaluator (candidate proposal from match evidence direction, then
  the offline duel battery). Stop at first promotion, then fly ONE confirm
  match that must carry the generation-1 provenance. A decline across all 8
  is a reported finding, not a failure.

## Pre-registered predictions (written and committed BEFORE either run)

RUN A — effect of aggression 1.0 → 1.5 guidance on the red berserker seat
(guidance text biases selection toward weapon/attack cards, away from
movement and vent):

| # | Metric (learning seat) | Predicted direction post vs baseline |
|---|---|---|
| P1 | attack keep-rate | increase (+). Risk note: if baseline ≥ 0.99 the metric is ceilinged and uninformative, as it was for blue — fallback primary endpoints are P5/P6. |
| P2 | movement keep-rate | decrease (−) |
| P3 | vent keep-rate | decrease (−); if baseline is already at the 0.0 floor: stays at floor (no increase) |
| P4 | special keep-rate | exploratory, no confident direction (guidance names weapon/attack vs movement/vent; specials unnamed; prior blue run drifted +) |
| P5 | attack planned share | increase (+) |
| P6 | movement planned share | decrease (−) |

Primary endpoints: **P2 (movement keep-rate −)** and **P5 (attack planned
share +)** — chosen because the prior run showed attack keep can ceiling.
Success criterion for a "clean behavioral PASS": at least one primary
endpoint significant at α=0.05 in the predicted direction with no primary
endpoint significant in the opposite direction. An inconclusive or negative
result is reported as such.

RUN B — spine predictions:

| # | Prediction |
|---|---|
| B1 | The lane composes and runs live (first time ever): every non-draw terminal produces a duel-gate evaluation workspace under `evaluations/` with materialized candidate/parent specs and per-duel sqlite ledgers. |
| B2 | The gate reaches a real verdict (promote or decline) via the §18 rules with the declared threshold overrides; no crash, no silent skip. |
| B3 | If promoted: the next admission (confirm match) flies the generation-1 policy — provenance equality asserted hard. |
| B4 | Interpretive limit, stated in advance: in card mode both duel sides' register programming is qwen (same personas); candidate and parent differ only in deterministic pilot-spec parameters, so duel outcomes may be dominated by LLM variance → draws and declines are plausible and legitimate. | **SUPERSEDED 2026-07-31 — see the correction at the end of this document (OMN-15489): the effect was not "dominated by" LLM variance, it was a structural ZERO.**

## RUN A attempt 1 (red seat): structural finding, no promotion possible

The red-seat run executed 30 baseline + 5 promote matches and terminated with
the driver's own FINDING: **the red berserker lost all 35 matches to the blue
sniper** (`winner=player.blue` 35/35), and `win_damage_differential_v1`
promotes only on a decisive learner win with positive damage differential —
so the red-seat lane **cannot fire L-GATE-2's promotion at all** on this
overlay. Two further pre-registered risk notes materialized immediately in
the red baseline: red attack keep-rate is ALSO ceilinged (1.0 in every
match, P1 risk note) and red vent keep-rate sits at the 0.0 floor (P3 floor
note) — the hoped-for red-seat keep-rate headroom does not exist. Raw data
retained: `.onex_state/steel_onslaught/lgate2_red_seat_attempt/`
(35 rows, gitignored lane, worktree `SO-L2SIG`).

**Fallback, declared before the rerun:** re-run RUN A on the **blue sniper
seat** with step 0.5 and n=30 — the seat that demonstrably can win (21/21
in #126), preserving single-knob attribution against the #126 battery
(same seat, same instruments; ONLY the step 0.25 → 0.5 and n 10 → 30
change). All six pre-registered directional predictions above carry to the
blue rerun **unchanged** (they are directions of the aggression guidance,
not seat-specific); the P1 ceiling note is already known to bind for blue
(attack keep 0.997 baseline in #126) and P3's floor note is known for blue
(vent keep 0.0 baseline in #126, and it moved +8.3pp AGAINST direction
there — P3 stays "decrease or stay at floor", which is exactly what makes
it a real test). Driver knob added for the structural finding:
`--promote-attempts` (promote-phase match budget).

## RUN A results (blue seat, step 0.5, n=30+30)

Chain (audit half): **all green again** — promotion fired on the first
promote-phase match (`match.01KY6BW8V49GWBMQ47P72VQ86P`, policy
`policy.aggressive.70257e6d40a142ba`, spec
`70257e6d…b6c3154`, lineage digest `1d0646c4…128389f2`), all 30 post
matches flew generation 1 with exact provenance equality,
`lineage_record_exists=true`, `all_replay_valid=true`, blue won 60/60
learner matches, 2 failed completions total across 61 matches.

Per-metric baseline vs post (Welch two-sided t, Cohen's d; positive diff =
post higher). Predicted directions from the pre-registered table:

| Metric | Pred. | Baseline (n) | Post (n) | Diff | d | t | df | p |
|---|---|---|---|---|---|---|---|---|
| keep attack | + (P1) | 0.9981 (30) | 0.9977 (30) | −0.0005 | −0.06 | −0.22 | 55.0 | 0.83 |
| keep movement | **− (P2, primary)** | 0.4807 (30) | 0.4829 (30) | +0.0021 | +0.06 | +0.23 | 57.0 | 0.82 |
| keep special | n/a (P4) | 0.6709 (30) | 0.6627 (30) | −0.0081 | −0.06 | −0.23 | 57.6 | 0.82 |
| keep vent | − (P3) | 0.0292 (30) | 0.0743 (30) | **+0.0451** | **+0.51** | +1.98 | 51.0 | **0.053** |
| share attack | **+ (P5, primary)** | 0.5155 (30) | 0.5056 (30) | **−0.0099** | **−0.48** | −1.84 | 54.2 | 0.072 |
| share movement | − (P6) | 0.3846 (30) | 0.3863 (30) | +0.0017 | +0.06 | +0.23 | 57.0 | 0.82 |
| share special | n/a | 0.0959 (30) | 0.0973 (30) | +0.0014 | +0.06 | +0.23 | 54.4 | 0.82 |
| share vent | n/a | 0.0242 (5) | 0.0250 (13) | +0.0008 | +0.07 | +0.13 | 8.2 | 0.90 |

- **Neither primary endpoint moved in the predicted direction.** P2
  (movement keep) is a hard null (p=0.82, d=+0.06 wrong-signed); P5 (attack
  planned share) is wrong-signed at d=−0.48, p=0.072.
- **P1 ceiling and P3 floor notes both bound**, exactly as pre-registered:
  attack keep 0.998 both phases; vent keep baseline near floor.
- **The one near-significant movement is anti-directional and replicates
  #126:** vent keep-rate ROSE +4.5pp after the aggression-up promotion
  (d=+0.51, p=0.053), the same direction as #126's +8.3pp (t=3.15,
  p≈0.006, n=10+10, step 0.25). Post-hoc (not pre-registered): Fisher's
  combined p across the two independent batteries ≈ 0.003. Whatever the
  promoted guidance does to qwen35's selection, its only detectable effect
  is OPPOSITE to the declared aggression semantics.
- Sensitivity: with n=30/30 and α=0.05 this battery has ~80% power for
  d≈0.74; a small predicted-direction effect (d<0.5) could hide under the
  nulls — but the observed point estimates are wrong-signed on 2 of the 3
  informative metrics, in both batteries.

Raw data (worktree `SO-L2SIG`, gitignored lane):
`.onex_state/steel_onslaught/lgate2_significance_battery_blue/{battery_raw.jsonl,battery_summary.json}`
(61 rows). Statistics: Welch t with Welch–Satterthwaite df, two-sided p via
the regularized incomplete beta function (validated against reference
values t=2.0/df=60→p=.0500, t=1.0/df=10→.3409, t=3.15/df=18→.0055);
Cohen's d on pooled SD.

## RUN B results (selection_outcome_v1, first live run)

**Attempt 1 — crash, two structural findings.** The first live terminal
fired the real evaluator; the search battery (eval_0001, 2 seeds × 2
side-swapped duels, all real qwen35 card-programming matches) completed,
then one holdout duel's LLM call raised `LlmTransportError`
(retryable=true, overlay retry budget max_attempts=1) and the exception
propagated UNCONTAINED through `DuelEvaluator → run_learning_loop →
LiveLearningCoordinator.handle_after_match → AfterMatchLearningHandler →
bus publish → MatchRunner tick`, killing the live match and the process
(nested 4-deep ExceptionGroup). Findings, independent of the flake:
- **F1:** the duel gate executes its entire LLM duel battery synchronously
  inside the live match's `MATCH_SCORED` bus publish — minutes of LLM
  traffic inside a bus subscriber, mid-tick.
- **F2:** a single retryable transport error in one duel is fatal to the
  live match; the coordinator's retry-safe snapshot design is not
  exploited by any retry/containment layer in the live path.
  Forensics retained: `.onex_state/steel_onslaught/lgate2_live_fire_attempt1/`.

**Attempt 2 — full spine success, both live outcomes observed.**

- Match 1 (`match.01KY6D31RD0ZDYNCQNKC3V3KJA`, seed 4301): red LOST →
  evidence direction −1 → candidate `vent_at_heat_margin` 5→4 (reason
  `selection_outcome:vent_at_heat_margin-1 … winner=player.blue,
  learner=player.red, cards_planned=100/160 dealt`). Search battery
  (eval_0001) + holdout gate (eval_0002) ran 8 real duels; holdout: 1
  candidate-decisive + 1 draw → `decisive_n=1, win_rate_delta=0.5,
  draw_rate=0.5, p_value=1.0` → **PROMOTED** under the declared relaxed
  thresholds; `POLICY_PROMOTED` on the ledger
  (`evidence_scored_event_id=01KY6D3S1XSFYVSX1NPXY7CP1Y`, policy
  `policy.aggressive.3c9baf5678676237`, parent spec `5b19f451…b516fe`,
  lineage digest `3585fbb0…bc35195e`); lineage record exists on disk with
  `promotion.status=promoted`, `generator_id=live.selection_outcome.v1`.
- Confirm match (seed 4400): a **fresh composition** rehydrated the
  generation-1 policy purely from the durable `POLICY_PROMOTED` chain +
  lineage store (production cross-process semantics) and flew it —
  MATCH_STARTED provenance equality asserted hard (policy_id, spec_hash,
  source_lineage_digest, generation=1). Its own terminal fired the gate
  AGAIN (red lost again → 4→3 candidate); the search battery
  (eval_0001_0002) ran and the gate **legitimately DECLINED** (no second
  `POLICY_PROMOTED`, no crash). Both verdict classes of the real judgment
  path are now live-observed.
- Chain readback: `all_replay_valid=true`; 3 evaluation workspaces with
  materialized candidate/parent pilot specs + pinned loadouts; 12 per-duel
  sqlite ledgers under `evaluation_storage/`; 14 match records under
  `evaluations/matches/`. Raw:
  `.onex_state/steel_onslaught/lgate2_live_fire/{live_fire_raw.jsonl,live_fire_summary.json}`.

Scope note (pre-registered as B4; **this framing is SUPERSEDED — read the
2026-07-31 correction at the end of this document before citing anything in
this section**): RUN B proves the SPINE of the real
judgment path — evidence-directed proposal, real duel gate, event-sourced
promotion, durable rehydration, legitimate decline. It makes NO claim of
policy quality: the thresholds were relaxed as declared, and the promoted
record honestly carries `decisive_n=1, p_value=1.0`.

Prediction scorecard: B1 ✔ (workspaces + specs + duel ledgers), B2 ✔ on
attempt 2 (real verdicts both ways) but ✘ on attempt 1 (crash — F1/F2), B3
✔ (confirm provenance equality), B4 ✔ (draws present; decline observed).

## Verdict on L-GATE-2 behavioral half

**FAILED at the tested operating points.** The audit half of L-GATE-2 stays
PROVEN (#126, re-confirmed twice here). The behavioral half — "next-match
selection metrics shift in the parameterized direction vs pre-promotion
baseline" — is now answered by two independent live batteries (10+10 @
step 0.25, #126; 30+30 @ step 0.5, this run): **no metric moved in the
parameterized direction**; the only detectable movement (vent keep-rate,
d≈+0.5) is OPPOSITE to the declared aggression semantics and replicates
across both batteries. Promotion demonstrably changes the prompt (audit
half) but does not steer qwen35's card selection the way the parameter
semantics claim.

What it would take to revisit: different guidance semantics/wording (the
current block is one sentence of bias prose), a parameter whose semantics
the model can actually express under the over-deal decision space (e.g.
movement-pile biases — vent keep sits at the floor and attack keep at the
ceiling, so the aggression axis has almost no live decision surface), or a
non-prompt consumer (deterministic selection bias applied to legal_hand).
Structural side-findings for follow-up: the red berserker seat can NEVER
fire the win-gated `win_damage_differential_v1` lane (0/35 red wins —
promotion requires a decisive learner win); `selection_outcome_v1` needs
containment/async for its in-terminal duel battery (F1/F2) before it can
be trusted unattended.

---

## CORRECTION — 2026-07-31 (OMN-15489): RUN B's duel gate was causally vacuous

**Status of this correction:** it supersedes pre-registered limit **B4** and
constrains every citation of RUN B. B1/B2/B3 are unaffected — the spine
(workspaces, materialized specs, per-duel ledgers, real verdicts both ways,
generation-1 provenance equality) really did run and really was observed.

**The finding.** B4 said duel outcomes "may be dominated by LLM variance."
That understates what was actually true. In card mode the duel gate had **no
causal path at all** from the candidate/parent pilot spec to any decision:

- `DuelEvaluator._materialize` wrote real candidate/parent `ModelSOPilotSpec`
  YAMLs and `assemble_match_with_dependencies` resolved them into
  `AggressivePilot` instances passed to `MatchRunner(pilots=...)`.
- But in card mode `MatchRunner.run` branched to `_run_card_round`, which
  never referenced `self._pilots`. `self._pilots` existed there only to
  satisfy the `missing_pilots` check. `card_adapter.produce` resolved
  programmers exclusively from the overlay's
  `contracts.card_catalog.programmers` bindings.
- Exhaustive grep at the time: `vent_at_heat_margin`,
  `idle_vent_heat_threshold`, `mode_switch_pressure_floor`,
  `mode_switch_heat_ceiling`, and `weapon_preference` were consumed ONLY in
  `pilots/aggressive.py::decide()`, reachable only via the non-card
  `ReducerPilotTick` branch.

So the gate compared **two causally identical systems**. RUN B's promotion of
`vent_at_heat_margin` 5 → 4 is **not evidence about that parameter** — it is a
coin flip on provider variance between two seats running the same policy. Any
future citation of RUN B must carry this sentence. The correct reading of B4
is: **structural zero, not swamped signal.**

**Provenance.** Raised by a parallel-stream external review; independently
adversarially confirmed 4/4 on 2026-07-30 (session `fable-battery-0730`,
workflow `wf_17d18656-f95`); filed as OMN-15489.

**What has been fixed, and what has not.** OMN-15489 wires the seat's own
pilot spec into card-mode programming through the existing pure rule seam
(`pilots.programming.program_for_seat` / `CardProgrammingRuleHandler`):
`cards/pilot_policy.py::PilotPolicyCategoryRule` runs the seat's deterministic
pilot against the same `ModelSOPilotObservation` the non-card branch uses and
requires the committed round to *lead with* a card expressing that decision.
Proof is tests only — no battery was re-run for this correction:

- `tests/cards/test_pilot_policy_rule.py` pins the decision differences
  exactly at the threshold boundaries, with no provider anywhere.
- `tests/learning/test_duel_card_mode_causality_omn15489.py` runs the REAL
  duel executor in card mode and asserts that varying only the red seat's
  materialized spec changes its committed rounds, with a same-spec control
  proving the differential is the spec and not run-to-run variance. Both
  differential cases fail against pre-fix `src/`; the control passes.

**Residuals that a re-run must still confront — do not read the fix as
retroactively validating RUN B:**

1. **RUN B is not repaired, only correctly labelled.** Its numbers stand as
   evidence of nothing about `vent_at_heat_margin`. A re-measurement is
   required before any claim about that parameter (ticket AC4).
2. **Causal ≠ discriminating.** Whether a *given* battery's duels actually
   reach the state where a threshold flips is empirical. In the 6-tick
   hermetic duel used by the regression test, heat never approaches the
   rupture band, so `vent_at_heat_margin` / `idle_vent_heat_threshold` /
   `mode_switch_heat_ceiling` do not change a decision *in that duel* even
   though they are now wired. A re-run must report the fraction of duels that
   entered each parameter's active band; a non-discriminating result is
   recorded as a null, never used to justify moving a threshold.
3. **Separate pre-existing defect, reproducible on unmodified `main`:** a
   card-mode duel that ends DECISIVELY fails card-round replay validation —
   the final partial round emits `HAND_DEALT`/`PLAN_COMMITTED`/
   `REGISTER_RESOLVED` but no `CARDS_DISCARDED`, and
   `validate_card_round_events` raises `CardRoundReplayError`. This bounds
   what a live `selection_outcome_v1` battery can even collect and is NOT
   fixed by OMN-15489.
4. **Provenance of the seat rule is instance-scoped but not yet in
   `MATCH_STARTED`.** The rule's `implementation_sha256` is content-addressed
   against the exact spec parameters (candidate and parent are different rule
   identities), but it is a per-seat handler and therefore does not appear in
   the overlay-selected `card_rule_pack_provenance`. The specs themselves
   remain durably recorded in the evaluation workspace.
