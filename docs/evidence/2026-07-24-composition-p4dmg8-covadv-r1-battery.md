# Composition Arm Battery — dmg×8 + covered_advance + Spatial R1, Stacked (2026-07-24)

**Verdict:** **DIRECTIONAL, but the point estimate moved DOWN, not up.** Decided-match red (brawler) win rate is **5/30 = 0.1667** (all-30 basis identical: zero aborts, zero draws) — inside the `0.10–0.35` DIRECTIONAL band, 95% Wilson CI **[0.0734, 0.3356]**. This sits **below** P4's own dose-alone result (8/29 = 0.2759, all-30 8/30 = 0.2667, Wilson CI [0.1470, 0.4572]) — stacking `covered_advance` and spatial R1 representation on top of the P4 dose did **not** convert the prior arms' behavioral/cognitive movement into additional win rate; the point estimate went the wrong direction. A two-proportion z-test against P4 (pooled p=0.220, SE=0.108) gives **z=1.01, p=0.31** — the drop is **not statistically distinguishable from noise at this sample size**, so this is reported as a directional finding, not a proven regression. `play_terminal_fraction=1.0` (30/30 elimination, zero aborts) is the cleanest trust-gate result of any arm in this program to date.

**The composition question this arm answers:** every prior lever (`covered_advance`, ARM G prompt steering, spatial R1) moved behavior or cognition measurably without moving outcome, always tested against a near-zero-lethality baseline. Stacked on top of a dose that is actually lethal (P4, 27.6%), the composition's point estimate is **lower**, not higher — additivity is **not supported** by this result; interference is the more consistent read, though not statistically proven.

**Ledger:** `.onex_state/steel_onslaught/composition_p4dmg8_covadv_r1` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-COMP-P5 worktree.
**Change under test:** three levers stacked on the unmodified P4 arena/loadout pairing, all additive:
1. Red loadout `loadout.llm.qwen35_berserker_dmg8` (`contracts_data/loadouts/llm_qwen35_berserker_dmg8.yaml`, merged under PR #170) — **reused byte-for-byte, not re-created** (verified: `git diff HEAD` against this file and its two weapon files is empty).
2. Blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` (merged under PR #159/#170, unmodified) — the shared approach-fix lever, held constant across every pair-sweep arm including this one.
3. Red `movement_deck_id` rebound from `deck.movement.v1` to `deck.movement.v2` (`contracts_data/decks/movement_v2.yaml`, PR #165, unmodified) — adds `card.movement.covered_advance` at 6/20 copies. Blue's `movement_deck_id` stays `deck.movement.v1`, matching the precedent the original `covered_advance` battery itself set (only red seat rebound).
4. Both seats' card-programmer `pilot_spec_id` rebound to the existing, unmodified R1 pilot specs `pilot.llm.qwen35_berserker_spatial_r1` / `pilot.llm.qwen35_sniper_spatial_r1` (`contracts_data/pilots/fire_dense_qwen/`, PR #167) — ASCII grid + resolver-backed consequence previews + in-range flags, representation only (`spatial_representation: grid`, not R2's `grid_scaffold`). Symmetric on both seats, matching R1's own fairness design.

New file: `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_p4dmg8_covadv_r1_qwen.yaml`. Arena `foundry_60_asym_v1` — **unchanged, the same arena as P1–P4**, not the v2/broken-sightline arena the `covered_advance` and R1 batteries themselves ran on originally; mortar_r30 was designed as the approach-fix specifically for v1 and stays held constant per the dispatch instruction.

**Seam verified before wiring, not assumed:** in card mode, `validate_seat_programmer_identity` (`src/steel_onslaught/match/composition.py`) checks only that the resolved card programmer's `persona` matches the seat's declared `archetype` — never the loadout's own `pilot_id` field. The stricter `loadout.pilot_id == assignment.pilot_spec_id` check lives on a separate roster/session-gated path (`assemble_selected_match_live`) that the O-GATE battery driver does not use. This is exactly how the merged R1 battery itself paired `loadout.llm.qwen35_berserker_v2` (`pilot_id: pilot.llm.qwen35`) with programmer `pilot.llm.qwen35_berserker_spatial_r1` — so pairing the dmg8 loadout (same declared `pilot_id`) with the spatial_r1 programmer is the identical, already-proven-legal seam, confirmed by a clean single-seed smoke test before the full battery ran.

**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, per-seed isolated invocation (one process per seed, shared append-mode state root, `--fresh` only on seed 5001, up to 2 attempts per seed on a 420s timeout — same hardening pattern P4 used). `all_replay_valid=true` (1/1 both players, all 30 matches).
**Baselines:** P4 (mortar_r30 + dmg×8 alone) 8/29 = 0.2759 DIRECTIONAL; `covered_advance` alone (v2 arena, no dose, no R1) 0/29 = 0.0000 FAILED, 95.9% programming rate; spatial R1 alone (v2 arena, no dose, no `covered_advance`) 0/30 = 0.0000 FAILED, 28.3% clean-attribution spatial vocabulary, 47.4% out-of-range fire, 55.8% blue zero-probability fraction. **The `covered_advance`-alone and R1-alone baselines ran on `foundry_60_asym_v2` with different loadouts (no dose lever) — comparisons below against those two baselines are cross-arena and are flagged as such, not a clean single-variable comparison. P4 is the clean baseline (identical arena, identical dose, identical blue loadout) for the win-rate/match-length/hits-to-kill comparisons.**
- All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl` — not copied from `battery_summary.json` or stdout — with explicit contract-level and engine-level dose verification, exactly as the P1–P4 docs require.

---

## 0. Provenance note: two transport-error retries, correctly isolated

Per-seed isolation worked exactly as designed: seeds 5023 and 5025 each hit a `LlmTransportError` on their first attempt (shared-endpoint instability, the same class of failure the program has seen throughout) and were retried once, succeeding on attempt 2. Because the script only writes a row to `battery_raw.jsonl` on success, the raw file has exactly 30 rows, seeds 5001–5030, zero duplicates, zero gaps (`len(set(seeds))==30`). The two failed first attempts left orphaned partial-match events in `events.sqlite3` (`match.01KYB5E8ST6CJYY5TZZEWRD7GS` and `match.01KYB5HSSXE0G5V5DA31DVF0YW` — 1 `match_started` each, no `match_ended`, no `plan_committed` for at least one seat) that are **not** among the 30 valid `match_id`s in `battery_raw.jsonl`. **Every query in this document filters explicitly to the 30 valid match_ids** — the raw event count for `match_started` in the ledger is 32, not 30, and using it unfiltered would silently contaminate every aggregate below.

---

## Method

Identical to the P1–P4 method (see those docs for the full derivation):
- **Decided-match win rate** = wins ÷ `elimination`-class terminals (aborts excluded); all-30 basis also reported. This battery has zero aborts, so both bases are identical.
- **Dose verification, two layers:** contract-layer diff (confirming the dmg8 files are unmodified) and engine-layer reconstruction (`hit_resolved` paired with `armor_absorbed` at `sequence_in_tick + 1` in the same `(match_id, tick)`; `damage_raw = damage_after_armor + absorbed_amount`; weapon attribution from the closest preceding `weapon_fired` targeting the same defender in the same tick).
- **Card funnel (dealt → programmed → resolved)** = occurrence-level counts (a hand can carry multiple copies of the same card; row-count undercounts, as the `covered_advance`-alone doc's own correction documents) filtered to `player.red` and `card.movement.covered_advance`.
- **Spatial vocabulary** = word-boundary-safe regex over `plan_committed.rationale` for `cover`/`LOS`/`line of sight`/`sightline` (clean-attribution set, per the R1 doc's own method — the berserker persona doctrine contains none of this vocabulary) vs. `range`/`terrain`/`obstacle` (confounded/absent categories).
- **Out-of-range fire fraction** = `weapon_fire_rejected.reason='target_out_of_range'` ÷ (`weapon_fired` + `weapon_fire_rejected`), red seat only.
- **Blue zero-probability shot fraction** = `weapon_fired` events with `hit_probability==0.0` ÷ total blue `weapon_fired`.
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt, same method as every prior doc in this program.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` (valid matches) | 30 / 30 |
| Terminal-class mix | elimination 30/30 (zero aborts, zero VP-threshold, zero draws) |
| `play_terminal_fraction` | **1.0** (gate ≥0.9 — PASS; codebase default ≥0.95 — also PASS) |
| Winner distribution | player.blue 25, player.red 5 |
| **Decided-match red win rate** | **5/30 = 0.1667** |
| **All-match red win rate** | **5/30 = 0.1667** (identical — zero aborts) |
| 95% Wilson CI | **[0.0734, 0.3356]** |
| Replay validity | 1/1 both players, all 30 matches |

Independently recomputed from `battery_raw.jsonl` (30 rows, seeds 5001–5030 present exactly once) and cross-checked against `events.sqlite3` filtered to the 30 valid `match_id`s (`match_started`=`match_ended`=30). **Red wins are seeds 5003, 5009, 5011, 5024, 5027** (all `elimination`/`last_mech_standing`, cross-checked against `mech_destroyed` subject `mech.blue.01` × 5).

| | This arm | P4 (dose alone) | Δ |
|---|---:|---:|---:|
| Decided win rate | 0.1667 (5/30) | 0.2759 (8/29) | **−0.109** |
| Wilson 95% CI | [0.0734, 0.3356] | [0.1470, 0.4572] | wide overlap |
| Two-proportion z-test vs P4 | — | — | **z=1.01, p=0.31 (n.s.)** |

The point estimate is materially lower than P4's, and the confidence intervals overlap substantially (P4's CI upper bound 0.457 sits well inside this arm's own plausible range, and vice versa). A two-proportion z-test comparing 5/30 against P4's 8/29 gives **z=1.01, p≈0.31** — **not statistically significant** at conventional thresholds. The honest read: **this result does not support additivity** (the composition did not push win rate up from P4's baseline), and the point estimate is directionally consistent with **interference**, but n=30 per arm is not enough to statistically prove the composition made things worse — only that it did not make them measurably better.

## 2. Match length

| Metric | This arm | P4 (dose alone) | `covered_advance` alone (v2 arena) | R1 alone (v2 arena) |
|---|---:|---:|---:|---:|
| min ticks | 19 | 14 | 18 | 21 |
| median ticks | **44.5** | 24 | 43.0 | 38.0 |
| mean ticks | **49.03** | 24.07 | 44.63 | 42.5 |
| max ticks | 96 | 38 | 73 | 77 |

Match length under composition (median 44.5, mean 49.0) is **nearly double** P4's dose-alone median (24) and is close to — even somewhat longer than — the `covered_advance`-alone and R1-alone arms' own match lengths (43.0 and 38.0), despite this arm carrying the same ×8 lethality dose those two arms lacked entirely. This is a real behavioral signal: **the movement/representation levers are dominating match duration, not the dose lever** — matches run long regardless of how lethal red's weapons are, which is consistent with (though does not prove) a mechanism where red spends more register-turns maneuvering/positioning under the composed pilot spec + movement deck, diluting the raw lethality advantage P4 showed in isolation.

## 3. Dose verification (raw weapon damage) — confirms P4's dose landed unmodified

### 3a. Contract layer

`git diff HEAD` against `contracts_data/weapons/machine_gun_dmg8.yaml`, `contracts_data/weapons/shrapnel_thrower_dmg8.yaml`, and `contracts_data/loadouts/llm_qwen35_berserker_dmg8.yaml` (all three files this arm's red loadout depends on) returns **empty** — these files are byte-identical to the versions merged under PR #170 and used by P4; this arm does not re-create or modify them, per the dispatch instruction. `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`, `contracts_data/arenas/foundry_60_asym_v1.yaml`, `contracts_data/decks/movement_v1.yaml`, `contracts_data/decks/movement_v2.yaml`, `contracts_data/cards/movement_covered_advance.yaml`, and both spatial R1 pilot specs are likewise all byte-identical to their merged versions (empty diff, same command).

`match_started` runtime snapshot for seed 5001 confirms the wiring landed: `mech.red.01.loadout_id = "loadout.llm.qwen35_berserker_dmg8"` (light chassis, `armor_max=6`), `mech.blue.01.loadout_id = "loadout.llm.qwen35_sniper_ironclad_mortar_r30"` (heavy chassis).

### 3b. Engine layer (reconstructed from live event data)

Reconstructed `damage_raw` per hit via `hit_resolved` + `armor_absorbed` pairing (Method), weapon-attributed via the preceding `weapon_fired` event, filtered to the 30 valid match_ids:

| Weapon | Baseline raw (P1–P4 method) | This arm observed | P4's own observed | Match? |
|---|---:|---:|---:|---|
| `machine_gun_dmg8` | int(8×0.7)=5 | **44** (45/54 red hits, zero variance) | 44 (47/68 hits) | **exact match** |
| `shrapnel_thrower_dmg8` | int(12×0.6)=7 | **57** (9/54 red hits, zero variance) | 57 (21/68 hits) | **exact match** |

Every red-caused hit in this battery lands at exactly one of two raw-damage values (zero variance), identical to P4's own reconstruction — the dose landed unmodified, exactly as expected from a byte-identical loadout/weapon reuse. All 127 `hit_resolved` events in the battery (54 red-caused, 73 blue-caused) paired cleanly with an `armor_absorbed` event at `sequence_in_tick + 1` — zero mismatches, zero unattributed weapon IDs.

### 3c. Armor saturation — full saturation replicates P4 exactly

| | This arm | P4 |
|---|---:|---:|
| `armor_after == 0` on red hits | **54/54 = 100%** | 68/68 = 100% |
| Mean damage-after-armor (red hits) | 37.28 | 40.57 |
| Median | 40 | 41 |

Blue's armor pool (`armor_max=16`) is fully saturated on every single red hit, replicating P4's own finding exactly — this arm did not touch the dose or the armor model, so this is expected and confirms the composition did not alter the underlying damage mechanics at all. The lower mean damage-after-armor here (37.28 vs P4's 40.57) reflects a different mix of which weapon landed more hits (this arm: 45 machine-gun / 9 shrapnel, vs. P4's 47/21 — shrapnel's raw=57 pulls the mean up, so a lower shrapnel share pulls the mean down slightly), not a dose difference.

## 4. Hits-to-kill

| | This arm | P4 |
|---|---:|---:|
| Red kills blue — mean hits (n=5) | **4.20** (`{4:4, 5:1}`) | 4.13 (n=8) |
| Blue kills red — mean hits (n=25) | **2.68** (`{2:8, 3:17}`) | 2.38 (n=21) |

Both figures are close to P4's own — the underlying combat math is unchanged (§3), consistent with hits-to-kill being a function of dose and armor, not of movement/representation. `mech_destroyed` counts corroborate the win tally exactly: blue destroyed in 5 matches (= the 5 red wins), red destroyed in 25 matches (= the 25 blue wins), 5+25=30, zero unexplained destructions.

## 5. `covered_advance` under composition — does the card retain its programming rate?

| Metric | This arm (occurrence-level) | `covered_advance`-alone battery (v2 arena) |
|---|---:|---:|
| Dealt | 377 | 338 |
| Programmed | 356 | 324 |
| **Programming rate** | **0.9443** | 0.9586 |
| Resolved (`move_intent.direction==covered_advance`) | 344 | 310 |

**Yes — the programming rate holds, essentially unchanged (94.4% vs 95.9%, a 1.4pp gap well within battery-to-battery noise).** `covered_advance` remains by far the dominant movement-card choice under composition: the next-highest red movement card this battery is `flank_left` at 59.2% (245 dealt / 145 programmed), less than two-thirds `covered_advance`'s rate. This confirms the card's movement-class placement (not utility-class) continues to avoid the utility-suppression trap under composition exactly as it did in isolation — pilots seek this card out regardless of what else is stacked on top.

| Card | Dealt | Programmed | Rate |
|---|---:|---:|---:|
| `card.movement.covered_advance` | 377 | 356 | **0.9443** |
| `card.movement.flank_left` | 245 | 145 | 0.5918 |
| `card.movement.flank_right` | 240 | 129 | 0.5375 |
| `card.movement.advance` | 118 | 44 | 0.3729 |
| `card.movement.reposition` | 244 | 63 | 0.2582 |

## 6. Spatial R1 under composition — does the vocabulary shift hold near 28.3%?

| Keyword | This arm (red, n=306 plans) | R1-alone (v2 arena, n=272 plans) |
|---|---:|---:|
| cover | 20 (6.5%) | 34 (12.5%) |
| LOS / sightline | 52 (17.0%) | 46 (16.9%) |
| **cover OR LOS (clean attribution)** | **68/306 = 22.2%** | **77/272 = 28.3%** |
| range (confounded, persona boilerplate) | 74/306 = 24.2% | 115/272 = 42.3% |
| terrain / obstacle (literal) | 0 / 0 | 0 / 0 |

**Partially — present and far above the 0/209 pre-representation baseline, but somewhat lower than R1's own isolated result (22.2% vs 28.3%, a 6.1pp gap).** The representation is demonstrably still reaching the model's stated reasoning under composition (sample rationale: *"Advance through cover to close distance and score objective while maintaining LOS denial"*), but the shift is not fully preserved at the same magnitude as when R1 ran alone (different arena, different dose, and now competing for register attention against a `covered_advance`-heavy movement deck and a much higher-stakes damage lever — any of these could plausibly compete for the same limited reasoning budget in the rationale text). This comparison is cross-arena (v1 here vs. v2 for R1-alone) and is flagged as such — not a clean single-variable read.

## 7. Out-of-range fire — does suppression hold? **No — it got substantially worse.**

| | This arm | R1-alone (v2 arena) | pre-representation baseline (inherited, unverified) |
|---|---:|---:|---:|
| Red fire attempts (fired + rejected) | 565 | 502 | 107 |
| Out-of-range rejections | 417 | 238 | 85 |
| **Out-of-range fraction** | **417/565 = 73.8%** | 238/502 = 47.4% | 85/107 = 79.4% |

This is the most striking negative finding in this battery. Under composition, red's out-of-range fire fraction (73.8%) is **26.4 points worse than R1 running alone** (47.4%) and sits much closer to the **pre-representation baseline** (79.4%, itself flagged inherited-and-unverified in every prior doc in this program) than to R1's own in-range-flag-informed result. The in-range flags are present in the prompt (same pilot spec, same representation machinery — §0 vacuity note below), but red is attempting to fire out of range at nearly the pre-representation rate anyway. A plausible (not proven) mechanism: the dmg8 loadout's much higher lethality-per-hit may be driving the model to prioritize firing early and often over waiting to close to effective range — a dose-vs-representation interference effect, consistent with §2's finding that composition matches run *longer* than P4 alone despite red apparently being *more* trigger-happy at range, not less. **No P4-alone out-of-range figure exists to compare against directly** (the P4 doc did not report this metric) — this comparison is against R1-alone (different arena/dose) and the doubly-inherited pre-representation baseline, both flagged.

## 8. Blue zero-probability shot fraction

| | This arm | `covered_advance`-alone (v2) | R1-alone (v2) |
|---|---:|---:|---:|
| Blue `weapon_fired` total | 217 | 256 | 269 |
| Zero-probability shots | 108 | 133 | 150 |
| **Fraction** | **108/217 = 49.8%** | 133/256 = 51.95% | 150/269 = 55.8% |

Comparable to both prior arms (49.8% sits between them) — blue continues to waste a large share of its shots on zero-probability targets under composition, consistent with red's continued high `covered_advance` uptake (§5) denying LOS at roughly the same rate as when the card ran alone, despite the arena difference.

## 9. Utility keep-rate per seat

| Seat | Dealt | Programmed | Keep-rate |
|---|---:|---:|---:|
| red (brawler) | 612 | 46 | **0.0752** |
| blue (sniper) | 612 | 82 | **0.1340** |
| all-card sanity, both seats | 1530/3060 (each seat) | — | 0.5000 (mechanical, confirms 5-of-10 register structure held) |

Both seats' utility keep-rates are in the same low single-digit-to-low-double-digit range as every prior arm in this program — no new effect from the composition.

## 10. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 615 |
| `llm_completion_resolved` | 612 |
| `llm_completion_failed` | 3 |
| `finish_reason` distribution | `stop`: 612/612 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 612/612 committed plans (zero fallback/heuristic) |
| Matches with ≥1 failed completion | 3/30 |
| Max single-match failures | 1 |
| Matches reaching an unrecovered abort | **0/30** |

615 requested − 612 resolved = 3, matching `llm_completion_failed` exactly, zero gap between resolved and `plan_committed` (612=612) — every completion that failed was recovered within-match by retry, and the two seed-level transport failures (§0) were recovered by the per-seed isolation harness at the process level, not within a single match. This is the cleanest completion-health record of any live-model arm in the program (zero unrecovered aborts, zero orphaned completions inside the final 30 matches).

---

## 11. Merge / additivity verification

- PR #170 (P4 dose lever) merged to `main` at `255f23062d1ddb845faf3e2765bad6ba4e0521f0`; PR #165 (`covered_advance`) at `47a449ee0d3fa0231efe795e4e531ee2a31d0732`; PR #167 (spatial R1) at `7cb8634770770779a803b4c54cb22eb03afc5a71`. All three confirmed ancestors of this branch's HEAD via `git merge-base --is-ancestor <sha> HEAD` (exit 0 for all three).
- `git status --short` at battery time shows exactly 5 untracked, additive files: this arm's overlay, the P5 dmg×11 weapons/loadout/overlay (prepared for the second battery in this dispatch, not used by this arm), and nothing else. Zero modified files.
- `git diff HEAD` against every baseline file this arm depends on (dmg8 weapons/loadout, mortar_r30 loadout, `foundry_60_asym_v1`, both movement decks, `covered_advance` card, both spatial R1 pilot specs) returns empty — every dependency is byte-identical to its merged version.

---

## Verdict

**DIRECTIONAL** by the program's own band convention (0.1667, inside 0.10–0.35), but the central finding of this arm is that **the composition's point estimate is lower than P4's dose-alone result, not higher** (0.1667 vs 0.2759), and a two-proportion z-test against P4 (z=1.01, p=0.31) does not distinguish the two at this sample size. `play_terminal_fraction=1.0` is the cleanest trust-gate result in the program to date (zero aborts across all 30 seeds).

- **`covered_advance` retains its programming rate under composition** (94.4% vs 95.9% alone) — essentially unchanged.
- **Spatial vocabulary partially holds** (22.2% vs R1-alone's 28.3%) — present, far above the 0/209 baseline, but somewhat attenuated (cross-arena comparison, flagged).
- **Out-of-range fire suppression does NOT hold** — 73.8%, worse than R1-alone's 47.4% and close to the pre-representation 79.4% baseline. This is the strongest single piece of evidence for interference rather than additivity.
- **Match length nearly doubles P4's dose-alone median** (44.5 vs 24 ticks) while landing an identical dose (§3) — the movement/representation levers dominate match duration regardless of lethality.
- **The dose itself is unaffected** — engine-layer reconstruction (§3b) and full armor saturation (§3c, 54/54 = 100%, matching P4's 68/68) confirm the composition did not alter the underlying damage mechanics at all; the win-rate difference from P4 is attributable to the added movement/representation levers changing *how* the match is played, not to any change in *how hard red hits*.

**Additivity vs interference — the question this arm was built to answer:** the evidence points toward **interference, not additivity**, most concretely in the out-of-range fire regression (§7) and the near-doubling of match length at an unchanged dose (§2) — both consistent with a story where the movement/representation levers compete with the dose lever for the model's limited per-turn attention/register budget rather than compounding with it. This is **not statistically proven** (the win-rate gap alone is not significant at n=30), and it is one battery, not a replicated result — but it is the first evidence in this program that stacking behaviorally-real levers on top of a working dose does not straightforwardly help, and may cost some of the dose's own gains.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/composition_p4dmg8_covadv_r1/events.sqlite3` (`match_started`, `match_ended`, `hit_resolved`, `armor_absorbed`, `weapon_fired`, `weapon_fire_rejected`, `hand_dealt`, `plan_committed`, `move_intent`, `mech_destroyed`, `llm_completion_requested`/`resolved`/`failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030).
- New overlay: `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_p4dmg8_covadv_r1_qwen.yaml` (the only new file this arm adds — every loadout, weapon, deck, card, and pilot spec it references is reused byte-for-byte from a prior merged PR).
- Seam verification: `src/steel_onslaught/match/composition.py` (`validate_seat_programmer_identity`, `assemble_match_live` vs. `assemble_selected_match_live`).
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p4_dmg8-battery.md` (PR #184), `docs/evidence/2026-07-24-covered-advance-battery.md`, `docs/evidence/2026-07-24-spatial_r1-battery.md`.
- Dispatch context: `docs/handoffs/2026-07-24-brawler-competitiveness-session.md` §10 item 2 ("a composition check ... is an operator call against the legibility north star").
- No secrets, keys, or absolute paths included.
