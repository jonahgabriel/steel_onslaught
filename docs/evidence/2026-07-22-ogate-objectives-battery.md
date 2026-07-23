# O-GATE objectives battery — 2026-07-22

Live measurement for the design's O-GATE row (`docs/design/2026-07-22-unified-depth-learning-design.md` §5):
**do matches end on play, not clock?** First live battery on the Phase-4
objective arena (`foundry_60_asym_v1`, merged in #132 @ `91c21d7`), red
berserker (the brawler) vs blue sniper on live keyless Qwen.

Discipline: predictions in this document are **pre-registered** — committed
before the first battery match ran (the #128 convention). The Results and
Verdict sections are appended afterwards without editing the predictions.

## Method

- Code under test: `main` @ `91c21d7` (`feat(objectives): Phase 4 — objective
  VP victory, victory_kind classification, and the foundry_60_asym_v1 arena`,
  #132).
- Harness: `scripts/run_ogate_objectives_battery.py` (committed with this
  doc) — headless in-process
  `steel_onslaught.match.composition.assemble_match_live`, the identical
  composition path used by `so play-live` and by the #124 / L-GATE-2
  batteries. Keyless provider (`secret_ref: null`), `NoSecretResolver`,
  overlay `retry.max_attempts=1`.
- Config: overlay
  `contracts_data/overlays/tactical_split_overdeal_asym_v1_qwen.yaml` (the
  O-GATE overlay shipped in #132 — identical to the over-deal split-deck
  overlay except `arena_id: foundry_60_asym_v1`), red
  `contracts_data/loadouts/llm_qwen35_berserker.yaml`, blue
  `contracts_data/loadouts/qwen35/sniper_ironclad.yaml` — the same seat and
  loadout pairing as the #124 abort battery, so terminal-class and
  winner-side shifts are attributable to the arena/objective change.
- Arena contract: 3 objectives at 1 VP per controlled tick (`west_yard`
  (18,30) near red spawn (4,30); `north_works` (30,22) anchoring the covered
  corridor; `east_gate` (42,36) in blue's band, blue spawn (52,30));
  `vp_threshold: 15`; control radius 1 (Chebyshev), mutual contest scores
  nobody; sudden death at tick 120.
- `max_ticks=1000` passed explicitly: the design's clock failsafe is the
  reachable anomaly class (`victory_kind=tick_cap_failsafe` /
  `draw_max_ticks`), not the engine's `aborted_runaway` guard.
- Battery: n=30 matches, seeds 5001–5030, sequential.
- Endpoint: Qwen3.6-35B-A3B (AI PC 5090), keyless — confirmed HTTP 200 on
  `/v1/models` immediately before launch.
- Metrics: read in-process from the canonical event ledger
  (`stack.ledger.read_all`); every MATCH_STARTED verified inline to carry
  `arena_contract_hash` equal to the recomputed digest of the shipped
  contract (the Phase-4 provenance seam). Raw per-match records:
  `.onex_state/steel_onslaught/ogate_objectives_battery/battery_raw.jsonl`
  (+ `battery_summary.json`), gitignored, retained in the
  `so-ogate` worktree.
- Terminal classes: `vp_threshold` (end reason `vp_threshold`);
  `elimination` (`last_mech_standing` / `pilot_killed` /
  `draw_mutual_destruction`, excluding cap-classified victories);
  `tick_cap` (`victory_kind=tick_cap_failsafe` or `draw_max_ticks`);
  `abort` (`aborted` / `aborted_runaway` / `provider_semantic_failure`).
  O-GATE passes iff (`vp_threshold` + `elimination`) / n >= 0.95.

## Pre-registered predictions (committed before the first match)

| # | Prediction | Grade after results |
|---|---|---|
| P1 | **Gate**: >= 95% of the 30 terminals are `vp_threshold` or `elimination`; specifically 0 `tick_cap` and 0 `abort` terminals. | — |
| P2 | **Terminal mix**: `vp_threshold` is the modal class, 50–85% of matches; the remainder eliminations. | — |
| P3 | **Brawler observable**: red win-rate moves off the floor to 15–40% of decided matches (baselines: 0/30 in #124 on this pairing; ~5% pooled across the knob rounds). | — |
| P4 | **Winner side**: blue still wins the majority of decided matches. | — |
| P5 | **Match length**: median `duration_ticks` 20–60 (shorter than #124's elimination-only median 66); max < 200. | — |
| P6 | **Objective contests**: `west_yard` awards majority-red, `east_gate` majority-blue, `north_works` has the most control changes; >= 30% of matches show >= 1 control change. | — |
| P7 | **Aborts**: 0 failed completions and 0 abort-class terminals (no regression vs #124's 0/840). | — |
| P8 | **Margins**: in `vp_threshold` matches the loser is on the board (VP > 0) in >= 60% of cases; median VP margin <= 8. | — |

Falsifiability note: P3 is the depth thesis's falsifiable core (design §7
item 4). Whatever the number is, it is reported; a flat win-rate is a
recorded finding that forces a design review, never a knob round (§2).

## Results (n = 30, seeds 5001–5030, all completed, all replay-valid)

### Terminal-class scorecard (the gate metric)

| Class | Count | Fraction |
|---|---|---|
| `vp_threshold` | **0** | 0.0% |
| `elimination` | **30** | 100.0% |
| `tick_cap` | 0 | 0.0% |
| `abort` | 0 | 0.0% |

Every terminal was `last_mech_standing` with `victory_kind=elimination`
(cross-tab `last_mech_standing/elimination: 30`). Play-terminal fraction
**1.00 >= 0.95** — the gate's numeric bar is met, with zero clock endings.

### Winner side and the brawler observable

- Winners: **blue (sniper) 30/30**. Draws: 0.
- **Brawler (red) win-rate: 0/30 = 0.0%** — decided-match rate 0.0%.
  The depth-thesis observable did **NOT** move off the floor (baselines:
  0/30 in #124, ~5% pooled knob rounds). Reported, not tuned (§2).

### Match length

- `duration_ticks`: min 11 / median 31 / mean 30.0 / max 59.
- Markedly **shorter** than #124 on symmetric `foundry_60` (range 21–103,
  median 66): on the asym arena the sniper kills roughly twice as fast.
  The obstacle-free mid-lane is working exactly as authored — as the
  sniper's E-W kill corridor — and the brawler walks it to reach
  objectives.

### Objective-contest metrics

- Matches with >= 1 `OBJECTIVE_SCORED` award: **7/30**; 19 awards total.
- Per objective: `east_gate` 12 awards (blue 9 / red 3, 1 control change);
  `west_yard` 5 awards (red 5, 0 changes); `north_works` 2 awards (blue 2,
  0 changes). Total control changes: **1** (matches with any: 1/30).
- Max single-side VP in any match: **8 of the 15 threshold** (blue,
  east_gate camp, seed 5002). Red's best: 4 (west_yard hold, seed 5022).
- `vp_threshold` margins: none (no VP terminals).

### Abort classes and completion health

- Abort-class terminals: **0** (no `aborted` / `aborted_runaway` /
  `provider_semantic_failure`).
- `llm_completion_failed`: **11 events across 10/30 matches** — all
  `semantic_failure_code=invalid_action_parameters`
  (`reason_code=invalid_response`, `finish_reason=stop`), blue 6/207
  requests (2.9%), red 5/206 (2.4%); 2.7 per 100 completions overall.
  All eleven recovered on the bounded first retry: 413 requested = 402
  resolved + 11 failed; **402/402 committed plans `plan_source=llm`**,
  zero deterministic fallback.
- This is a **regression signal vs #124's 0/840** on the same seats and
  loadouts (symmetric arena, pre-objective prompts): the class #120/#121
  drove to zero is back at ~2.7% under the objective observation/prompt
  block. Root cause not established here — recorded as a follow-up
  finding, not hidden inside a green scorecard.

### Prediction grades

| # | Prediction | Outcome | Grade |
|---|---|---|---|
| P1 | >= 95% play terminals; 0 tick_cap; 0 abort terminals | 100% / 0 / 0 | **CORRECT** |
| P2 | `vp_threshold` modal, 50–85% | 0% — never fired | **WRONG** |
| P3 | brawler 15–40% of decided | 0% | **WRONG** |
| P4 | blue majority | blue 30/30 | CORRECT |
| P5 | median ticks 20–60; max < 200 | median 31; max 59 | CORRECT |
| P6 | west_yard red-majority, east_gate blue-majority, north_works most contested, >= 30% of matches with a control change | first two held; north_works had 0 changes; 1/30 (3.3%) matches with a change | **MOSTLY WRONG** |
| P7 | 0 failed completions, 0 abort terminals | 0 abort terminals, but 11 failed completions | **HALF WRONG** |
| P8 | loser on the board in >= 60% of VP matches; median margin <= 8 | vacuous — no VP matches | N/A |

3 correct, 4 wrong or partly wrong, 1 vacuous. The misses all point the
same direction: kill speed dominates VP accumulation far harder than
predicted.

## Verdict

**O-GATE: CONDITIONAL PASS.**

- **The letter of the gate passes**: 30/30 matches ended on play, zero on
  the clock, zero aborts. "Do matches end on play, not clock?" — yes,
  unambiguously.
- **The pass is vacuous with respect to the new mechanism**: 0/30 matches
  ended on `vp_threshold`; the maximum VP any side banked was 8 of 15.
  Reaching the threshold requires ~15 held ticks after arrival; the median
  match is over (by kill) at tick 31, and the asym layout made the kill
  *faster* than on `foundry_60` (median 31 vs 66). At these parameters the
  VP victory path is live, observed scoring, and **unreachable in
  practice**. A clean "PASS" stamp would certify a mechanism that never
  decided a match.
- **The brawler observable is flat: 0/30.** The depth hypothesis —
  objectives move brawler win-rate off the ~5% floor without knob tuning —
  is **not supported** at these settings. Objectives gave red a reason to
  close but neither protection while closing nor time to convert board
  control into points; red held `west_yard` in 2 matches (max 4 VP) and
  died mid-lane in the rest. Per §5 fail semantics this is a **recorded
  finding that forces a design review**, not a knob round. The review
  levers are objective-layer design (§3.4 names layout + thresholds as
  exactly where the depth program tunes): VP threshold vs realistic match
  length, VP accrual rate, objective placement relative to cover (red's
  covered north corridor leads to `north_works`, which red never scored),
  or Phase-2 utility counterplay (smoke) landing before O-GATE re-measure.
- **Regression finding**: `invalid_action_parameters` completion failures
  recurred at ~2.7/100 completions (0/840 in #124) under the objective
  prompt block, fully absorbed by the bounded retry. Needs root-cause
  before the next battery treats completion health as solved.

Raw data: `.onex_state/steel_onslaught/ogate_objectives_battery/`
(`battery_raw.jsonl`, `battery_summary.json`, `events.sqlite3`) — gitignored,
retained in the `so-ogate` worktree.
