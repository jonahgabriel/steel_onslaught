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
| B4 | Interpretive limit, stated in advance: in card mode both duel sides' register programming is qwen (same personas); candidate and parent differ only in deterministic pilot-spec parameters, so duel outcomes may be dominated by LLM variance → draws and declines are plausible and legitimate. |

## RUN A results

_(filled in after the run — see git history: predictions committed first)_

## RUN B results

_(filled in after the run)_

## Verdict on L-GATE-2 behavioral half

_(filled in after the runs)_
