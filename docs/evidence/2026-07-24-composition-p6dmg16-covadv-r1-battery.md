# Composition Arm at ×16 Battery — Retest Under a Regime Where Red Wins the Kill Race (2026-07-24)

**Verdict:** **By the pre-registered composite criteria, this reads as ADDITIVITY — but two of the arm's own behavioral signals replicate the ×8 composition arm's negative findings unchanged, and the result is not statistically distinguishable from ×16-dose-alone.** Decided-match red (brawler) win rate is **18/28 = 0.6429**, 95% Wilson CI **[0.4583, 0.7929]** (all-30 basis: 18/30 = 0.6000, CI [0.4232, 0.7541]) — materially above P6's dose-alone 56.67%, and `covered_advance` (94.6%) and spatial vocabulary (26.8%) both land inside the pre-registered "additivity" ranges. But this is **not statistically separated from P6** (decided-basis two-proportion z=0.59, p=0.55; all-30-basis z=0.26, p=0.79), and two of the specific mechanisms the ×8 composition arm flagged as evidence of interference — suppressed out-of-range-fire discipline and near-doubled match length — **replicate essentially unchanged at ×16**, not reversed. `play_terminal_fraction=0.9333` (28/30 elimination, 2 aborts) clears the task's own ≥0.9 gate but **does not** clear the codebase's stricter ≥0.95 default — a genuine trust-gate caveat this document does not paper over.

**Why this arm was run:** every geometry/approach lever tested earlier in this program (`covered_advance`, spatial R1, cover rects, cadence) was tested against red in a *0% win regime* — red could not win the kill race, so those levers never had lethality to spend. P6 (×16 dose alone, PR #191) showed red's kill speed had overtaken blue's (2.18 vs blue's 2.62 mean hits-to-kill, per-kill-sequence method) at 17/30 = 56.67%, with blue landing a disproportionate 34.6% of its hits in matches it ultimately lost — a signature consistent with approach exposure, not raw lethality, being the residual ceiling. This arm re-tests the geometry/approach levers in exactly that regime, on the hypothesis that they may only pay off once red survives the approach with lethality to spare.

**Ledger:** `.onex_state/steel_onslaught/composition_p6dmg16_covadv_r1` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-COMP-P5 worktree (`steel_onslaught_comp16`).
**Change under test:** the identical three-lever composition the ×8 arm used, stacked on the P6 dose instead of P4's:
1. Red loadout `loadout.llm.qwen35_berserker_dmg16` — reused byte-for-byte from PR #191 (verified: empty `git diff HEAD`).
2. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` — unmodified, held constant across every pair-sweep arm.
3. Red `movement_deck_id` rebound to `deck.movement.v2` (adds `card.movement.covered_advance`, PR #165) — blue's stays `deck.movement.v1`.
4. Both seats' card-programmer `pilot_spec_id` rebound to the existing, unmodified R1 pilot specs (`pilot.llm.qwen35_berserker_spatial_r1` / `_sniper_spatial_r1`, PR #167) — representation only (`spatial_representation: grid`), symmetric on both seats.

New file: `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_p6dmg16_covadv_r1_qwen.yaml`. No new loadout/weapon file is added — the dmg16 loadout's provenance is already pinned (PR #191). Arena `foundry_60_asym_v1`, unchanged.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, per-seed isolated invocation (`--fresh` only on seed 5001, up to 2 attempts per seed on a 420s timeout). One seed (5030) hit a transient `LlmTransportError` on attempt 1 and succeeded on attempt 2 — the raw file has exactly 30 rows, seeds 5001–5030, zero duplicates, zero gaps.
**Baselines:** ×8 composition (dose+covered_advance+R1, P4 arena/dose) 5/30 = 0.1667, INTERFERENCE-classified; P6 (×16 dose alone) 17/30 = 0.5667, the pre-registered comparison target for this arm — **not** the ×8 composition arm, which tested a fundamentally different (red-losing) regime.
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl` — not copied from `battery_summary.json` or stdout.

---

## 0. Pre-registered comparison target and additivity/interference criteria (written before reading results)

Committed in this overlay's own header comment before the battery ran:

- **Comparison target: P6's 56.67% (17/30, dose alone)** — not the ×8 composition arm's 16.67%, which is not the relevant baseline for a ×16-dose regime.
- **ADDITIVITY:** decided win rate materially ABOVE 56.67%, with `covered_advance` retaining its established ~94–96% programming rate and spatial vocabulary holding near R1-alone's 22–28% range.
- **INTERFERENCE:** decided win rate AT OR BELOW 56.67%, especially paired with degraded card/vocabulary metrics (as the ×8 arm showed: `covered_advance` held but out-of-range fire got worse, and match length nearly doubled).
- **INDETERMINATE:** win rate within noise of 56.67% (Wilson-CI-overlapping) with card/vocabulary metrics unchanged — an explicitly acceptable outcome, not something to force into a cleaner verdict.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events (valid matches) | 30 / 30 |
| Terminal-class mix | elimination 28/30, abort 2/30 (seeds 5009, 5020) |
| `play_terminal_fraction` | **0.9333** (task gate ≥0.9 — PASS; codebase default ≥0.95 — **FAIL**) |
| Winner distribution | player.red 18, player.blue 10, draw 2 (the aborts) |
| **Decided-match red win rate (aborts excluded)** | **18/28 = 0.6429** |
| **All-match red win rate (aborts included, denominator 30)** | **18/30 = 0.6000** |
| 95% Wilson CI, decided-28 basis | **[0.4583, 0.7929]** |
| 95% Wilson CI, all-30 basis | [0.4232, 0.7541] |
| Replay validity | 1/1 both players, all 30 matches |

**Red wins: seeds 5002, 5003, 5004, 5005, 5006, 5007, 5011, 5012, 5013, 5014, 5015, 5019, 5021, 5024, 5025, 5026, 5028, 5029** (18 seeds, corroborated by `mech_destroyed` on `mech.blue.01` × 18). **Aborts: seed 5009** (`reason_code=timeout`, red seat, single transport-class failure exhausting the retry budget) **and seed 5020** (`reason_code=invalid_response`/`semantic_failure_code=invalid_action_parameters`, blue seat, 4 consecutive attempts all citing `"program uses cards not present in the dealt hand: ['card.movement.flank_left']"`). Both aborted matches died at **tick 16 with zero `hit_resolved` events on either side** — confirmed by direct query — so neither abort could be systematically rescuing one side from an imminent loss; they are clean early-round provider dropouts, not outcome-correlated.

### 1a. Trust-gate caveat (stated plainly, not minimized)

This is the first pair-sweep or composition arm in this session with 2 aborts rather than 0 or 1 — `play_terminal_fraction=0.9333` clears the task-stated ≥0.9 threshold but **does not clear** the codebase's own stricter ≥0.95 default (`--gate-threshold=0.95`). Per program convention (the R2 spatial arm precedent, `docs/evidence/2026-07-24-spatial_r2-battery.md`), a battery that clears ≥0.9 but not ≥0.95 is reported with the figure it actually is, not silently backfilled to a cleaner denominator; a backfill re-run is a legitimate optional follow-up, not performed here. The seed 5020 abort (blue repeatedly proposing an undealt card) is worth flagging as a possible interaction with the larger, spatial-R1-enlarged prompt — the same failure class (`invalid_action_parameters`) the R2 abort-forensics entry in LEARNINGS documented for a different arm — but this is n=1 within this battery and is not claimed as proven here.

### 1b. Statistical comparison against the pre-registered target (P6)

| Comparison | z | p | Significant at α=0.05? |
|---|---:|---:|---|
| This arm, decided (18/28) vs P6 decided (17/30) | 0.59 | 0.553 | No |
| This arm, all-30 (18/30) vs P6 all-30 (17/30) | 0.26 | 0.793 | No |

The point estimate (60.0–64.3%) sits well above P6's 56.67% by both bases, but neither comparison clears conventional significance — consistent with essentially every other pairwise arm comparison in this program at n≈30. **Per the pre-registered criteria (§0), the point estimate alone satisfies "materially above 56.67%"** — the qualifying word in that criterion was "materially," judged against the point estimate, not against a significance test, exactly as the composite criteria were written before this result was known.

## 2. Match length — the ×8 arm's negative signal replicates unchanged

| Metric | This arm (×16 composition) | P6 (×16 dose alone) | ×8 composition | P4 (×8 dose alone) |
|---|---:|---:|---:|---:|
| min ticks | 16 | 15 | 19 | 14 |
| median ticks | **40.0** | 23.0 | 44.5 | 24 |
| mean ticks | 47.23 (all 30) / 49.46 (elim-only) | 23.3 | 49.03 | 24.07 |
| max ticks | 134 | 40 | 96 | 38 |

Match length under composition **nearly doubles the dose-alone baseline at ×16** (median 40.0 vs P6's 23.0, a 74% increase) — essentially the same relative effect the ×8 arm showed (median 44.5 vs P4's 24, an 85% increase). **This specific negative signal from the ×8 arm did not reverse.** The maximum this battery reached (134 ticks) is also the longest single match in the entire pair-sweep/composition program to date, well above the ×8 composition arm's own max (96).

## 3. Dose verification (raw weapon damage) — confirms the corrected P6 mechanism replicates a fourth time

### 3a. Contract layer

`git diff HEAD` against every file this arm depends on (`machine_gun_dmg16.yaml`, `shrapnel_thrower_dmg16.yaml`, `llm_qwen35_berserker_dmg16.yaml`, `sniper_ironclad_mortar_r30.yaml`, `foundry_60_asym_v1.yaml`, both movement decks, `covered_advance` card, both spatial R1 pilot specs) returns **empty** — this arm modifies zero existing files; the only new file is the overlay. `git merge-base --is-ancestor` confirms PR #191's merge commit (`93aaa43d1fd5fb713a6cc3ceb157a3ea5f3aca97`) is an ancestor of this branch.

### 3b. Engine layer

| Weapon | Baseline raw | This arm observed | Pre-registered prediction (P6, §0) | Match? |
|---|---:|---:|---|---|
| `machine_gun_dmg16` | 5 | **89** (37/49 red hits, zero variance) | int(128×0.7)=89 | **exact match** |
| `shrapnel_thrower_dmg16` | 7 | **115** (12/49 red hits, zero variance) | int(192×0.6)=115 | **exact match** |

All 95 `hit_resolved` events (49 red-caused, 46 blue-caused) paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches, zero unattributed weapon IDs. `armor_after == 0` on **49/49 red hits (100%)**, replicating P6's own 43/43 and the corrected P5 mechanism a fourth consecutive time: mean damage-after-armor is **85.51** here vs P6's 84.93 — essentially identical, confirming the composition levers did not alter the underlying damage math at all.

## 4. Hits-to-kill (per-kill-sequence method — see the LEARNINGS caveat on the biased crude estimator)

| | This arm | P6 (dose alone) |
|---|---:|---:|
| Red kills blue — mean hits (18 kills) | **2.39** (median 2, `{2:12, 3:6}`) | 2.18 (17 kills) |
| Blue kills red — mean hits (10 kills) | **2.70** (median 3, `{2:3, 3:7}`) | 2.62 (13 kills) |

Both figures track P6's own closely — red's kill speed (2.39) is still faster than blue's (2.70), the same crossing P6 first established, essentially unchanged by the composition levers. The underlying combat math (§3) is identical; composition changes *how the match is played*, not *how hard either side hits once it lands a shot*.

### 4a. Unconverted-hit share — the approach-exposure signature strengthens

| | This arm | P6 (dose alone) |
|---|---:|---:|
| Red total hits landed | 49 | 43 |
| Red hits in matches red won | 43 (87.8%) | 37 (86.0%) |
| Red hits in matches red lost (unconverted) | 6 (12.2%) | 6 (14.0%) |
| Blue total hits landed | 46 | 52 |
| Blue hits in matches blue won | 27 (58.7%) | 34 (65.4%) |
| Blue hits in matches blue lost (unconverted) | **19 (41.3%)** | 18 (34.6%) |

Blue's unconverted-hit share **rises further under composition** (41.3% vs P6-alone's 34.6%) — blue lands an even larger fraction of its hits in matches it ultimately loses when red also has `covered_advance` and spatial R1 available. This is consistent with (not proof of) the approach-exposure hypothesis this arm was built to test: blue gets early pot-shots in during red's approach, those pot-shots do not decide the match, and red's LOS-denial tools (§5, §7 below) make it harder for blue to convert its range advantage into a decisive early lead.

## 5. `covered_advance` under ×16 composition

| Metric | This arm | ×8 composition | R1-alone / `covered_advance`-alone (v2 arena) |
|---|---:|---:|---:|
| Programming rate | **350/370 = 0.9459** | 356/377 = 0.9443 | 0.9586 |

Essentially unchanged from the ×8 composition arm (94.6% vs 94.4%) and close to the card's isolated rate (95.9%) — retained exactly as expected, replicating the finding that this card's uptake is robust to the surrounding dose regime.

| Card | Dealt | Programmed | Rate |
|---|---:|---:|---:|
| `card.movement.covered_advance` | 370 | 350 | **0.9459** |
| `card.movement.flank_right` | 231 | 141 | 0.6104 |
| `card.movement.flank_left` | 230 | 130 | 0.5652 |
| `card.movement.advance` | 112 | 45 | 0.4018 |
| `card.movement.reposition` | 237 | 50 | 0.2110 |

## 6. Spatial R1 under ×16 composition — vocabulary holds better than at ×8

| | This arm | ×8 composition | R1-alone (v2 arena) |
|---|---:|---:|---:|
| cover OR LOS (clean attribution) | **79/295 = 0.2678** | 68/306 = 0.2222 | 77/272 = 0.2833 |
| range (confounded) | 76/295 = 0.2576 | 74/306 = 0.2418 | 115/272 = 0.4228 |

Clean-attribution spatial vocabulary (26.8%) is **higher than the ×8 composition arm's 22.2%** and sits close to R1-alone's own 28.3% — the closest this composition setup has come to fully preserving the isolated R1 vocabulary rate. Sample rationale: *"Advance through cover, flank to block LOS, then fire both weapons to press the kill."*

## 7. Out-of-range fire — the ×8 arm's negative signal replicates, essentially unchanged

| | This arm (×16 composition) | ×8 composition | R1-alone (v2 arena) | pre-representation baseline (inherited) |
|---|---:|---:|---:|---:|
| Red fire attempts | 570 | 565 | 502 | 107 |
| Out-of-range rejections | 436 | 417 | 238 | 85 |
| **Out-of-range fraction** | **436/570 = 0.7649** | 417/565 = 0.7381 | 238/502 = 0.4740 | 85/107 = 0.7944 |

**This is the arm's clearest non-reversal.** Out-of-range fire suppression does not hold under composition at ×16 any more than it did at ×8 — if anything the fraction is marginally worse (76.5% vs 73.8%), and both remain far closer to the pre-representation baseline (79.4%) than to R1-alone's in-range-flag-informed 47.4%. Whatever caused red to keep firing out of range under composition at ×8 (hypothesized in that document as the higher-lethality loadout competing with the in-range flags for attention) is not resolved by giving red an even higher-lethality loadout — the effect looks structural to the composition, not specific to the ×8 dose level.

## 8. Blue zero-probability shot fraction — the highest recorded in the program

| | This arm | ×8 composition | `covered_advance`-alone | R1-alone |
|---|---:|---:|---:|---:|
| Blue `weapon_fired` total | 212 | 217 | 256 | 269 |
| Zero-probability shots | 129 | 108 | 133 | 150 |
| **Fraction** | **129/212 = 0.6085** | 108/217 = 0.4977 | 133/256 = 0.5195 | 150/269 = 0.5580 |

Blue wastes a larger share of its shots on zero-probability targets under this arm than in any prior arm in the program — a real, mechanically verified LOS-denial signal, consistent with (and somewhat stronger than) the ×8 composition arm's own result.

## 9. Utility keep-rate per seat

| Seat | Dealt | Programmed | Keep-rate | ×8 composition |
|---|---:|---:|---:|---:|
| red (brawler) | 590 | 39 | **0.0661** | 0.0752 |
| blue (sniper) | 590 | 76 | **0.1288** | 0.1340 |
| all-card sanity, both seats | 1475/2950 (each seat) | — | 0.5000 (mechanical) | 0.500 |

No meaningful change from the ×8 composition arm.

## 10. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 600 |
| `llm_completion_resolved` | 591 |
| `llm_completion_failed` | 9 |
| `finish_reason` distribution | `stop`: 591/591 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 590/590 committed plans (zero fallback/heuristic) |
| Matches with ≥1 failed completion | 5/30 |
| Max single-match failures | 4 (seed 5020 — the semantic-failure abort) |
| Matches reaching an unrecovered abort | 2/30 (seeds 5009, 5020) |

600 requested − 591 resolved = 9, matching `llm_completion_failed` exactly. There is a 1-event gap between `llm_completion_resolved` (591) and `plan_committed` (590), fully explained by seed 5009's abort (blue's last completion resolved successfully, but the match aborted on red's timeout before a plan was committed for that final round) — the identical pattern the P4 doc documented for its own single abort.

---

## 11. Merge / additivity verification

- PR #191 merged to `main` at `93aaa43d1fd5fb713a6cc3ceb157a3ea5f3aca97` — confirmed an ancestor of this branch's HEAD.
- `git diff HEAD` against every dependency (dmg16 weapons/loadout, mortar_r30 loadout, `foundry_60_asym_v1`, both movement decks, `covered_advance` card, both spatial R1 pilot specs) returns **empty**.
- This arm adds exactly one new file (the overlay) — no existing loadout, weapon, deck, card, or pilot spec file is modified, and no new loadout file is needed (the dmg16 loadout's provenance was already pinned by PR #191).

---

## Verdict

**By the pre-registered composite criteria (§0), this reads as ADDITIVITY on the point estimate: 18/28 = 0.6429 (all-30: 0.6000) is materially above P6's 56.67%, `covered_advance` retains its programming rate (94.6%), and spatial vocabulary (26.8%) lands near the high end of the pre-registered "holds" range.** But three qualifications keep this from being a clean confirmation:

1. **Not statistically separated from P6** (z=0.59/0.26, p=0.55/0.79 on the two bases) — at n≈30 per arm, this program has not once produced a statistically significant adjacent-arm comparison, and this is no exception.
2. **The trust gate is weaker than P6's own** (`play_terminal_fraction=0.9333` vs P6's clean 1.0) — clears the task's ≥0.9 threshold, not the codebase's stricter ≥0.95 default. Both aborts died at tick 16 with zero hits landed on either side, so they are not outcome-correlated, but the battery is not as clean as P6 was.
3. **Two of the ×8 composition arm's specific negative findings replicate unchanged, not reversed:** out-of-range fire suppression still fails (76.5% vs the ×8 arm's 73.8% — both far from R1-alone's 47.4%), and match length still nearly doubles the dose-alone baseline (40.0 vs P6's 23.0, a 74% increase, close to the ×8 arm's own 85% increase). Whatever mechanism causes these two effects under composition is not specific to the ×8 dose level — it looks structural to stacking these particular levers, regardless of how lethal red already is.

**Net read:** the win-rate point estimate moved in the additive direction this time (unlike the ×8 arm, which moved backward), and spatial vocabulary held better than at ×8 — genuine differences from the earlier negative result. But the underlying behavioral picture is mixed, not uniformly positive: blue's zero-probability shot fraction and its unconverted-hit share both rose further under composition, which is consistent with the approach-exposure hypothesis this arm was designed to test, while out-of-range fire and match length show the same friction the ×8 arm already documented. This document reports the point estimate lean toward additivity plainly, without treating it as proof, and reports the replicated negative signals with equal weight rather than burying them under the headline number.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/composition_p6dmg16_covadv_r1/events.sqlite3` and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- New overlay: `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_p6dmg16_covadv_r1_qwen.yaml` (the only new file this arm adds).
- Seam verification (unchanged from the ×8 composition arm): `src/steel_onslaught/match/composition.py` (`validate_seat_programmer_identity`).
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md` (PR #191, pre-registered comparison target), `docs/evidence/2026-07-24-composition-p4dmg8-covadv-r1-battery.md` (PR #188, the ×8 composition arm this document retests), `docs/evidence/2026-07-24-pair_p5_dmg11-battery.md`.
- LEARNINGS entries this document is consistent with: the corrected armor-absorption mechanism (P5 entry), the per-kill-sequence-vs-crude-estimator caveat, and the P6 unconverted-hits finding — all in `docs/steel_onslaught/LEARNINGS.md`.
- No secrets, keys, or absolute paths included.
