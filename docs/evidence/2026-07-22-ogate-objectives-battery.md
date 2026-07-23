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

## Results

_(appended after the battery ran; predictions above unedited)_

## Verdict

_(appended after the battery ran)_
