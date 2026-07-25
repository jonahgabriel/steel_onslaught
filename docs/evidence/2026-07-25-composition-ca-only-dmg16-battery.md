# Decomposition Arm SO-COMP-CA — `covered_advance` Alone Reproduces Essentially All of the Composition Arm's Match-Length Elongation (2026-07-25)

**Verdict on the single pre-registered criterion: ISOLATED-CAUSE (H_CA).** Median match length is **39.5 ticks** (n=30), against the pre-registered threshold of **31.5**. `covered_advance` alone — with **no** spatial R1 anywhere in either seat's prompt — lands at essentially the two-lever composition arm's own median (40.0) and **71.7% above** the ×16 dose-alone floor (23.0). Expressed as a share of the gap this arm was built to attribute: **(39.5 − 23.0) / (40.0 − 23.0) = 16.5 / 17.0 = 97.1%** of the composition arm's median elongation is reproduced by one lever. The match-length negative signal that replicated across both composition arms is **attributable to `covered_advance`, not to spatial R1 and not to a two-lever interaction.**

The secondary out-of-range-fire endpoint read **429/585 = 0.7333** — squarely in the mechanically expected high band for an arm with no in-range flags in the prompt at all, and therefore **not informative in either direction**; it is reported, not read as evidence (§4). The tertiary win-rate endpoint moved up (decided 20/29 = 0.6897 vs P6's 17/30 = 0.5667) but is **not statistically separated** (z=0.98, p=0.33) and gates nothing (§5).

**Ledger:** `.onex_state/steel_onslaught/composition_ca_only_dmg16` (`events.sqlite3`, `battery_raw.jsonl`) in the `SO-COMP-CA` worktree.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, per-seed isolated process invocation.
**All figures below are independently recomputed from `events.sqlite3` and `battery_raw.jsonl`.** `battery_summary.json` is **not** a source for any number here — under per-seed invocation it only ever describes the last single-seed run (`"n": 1`), which is exactly why the program forbids citing it.

---

## 0. Pre-registration (committed before the first `match_started`)

| Item | Value |
|---|---|
| Pre-registration commit | `b1a01ddab40d5ae40913dd724cfb89d8a0b6875a` |
| Commit timestamp | **2026-07-25T16:38:58Z** |
| First `match_started` in the citable ledger | **2026-07-25T16:54:41.687280+00:00** |
| Gap (must be positive) | **+15m 43s** |

The commit contains the overlay with its full header block: the ONE changed field, the explicitly-unchanged dependency list, the comparison anchors, and the single formal criterion. Nothing was added to or altered in the criterion afterward — the criterion text in §0a is the commit's text.

An earlier, **discarded** run of this same overlay started its first match at `2026-07-25T16:39:17.310228+00:00` (gap +19s from the same commit). That run was abandoned on an environment fault and its ledger was wiped by `--fresh`; it is disclosed in full in §9 rather than omitted.

### 0a. The single formal criterion (verbatim intent, arithmetic shown)

- **PRIMARY ENDPOINT:** median `duration_ticks` over the n valid battery rows.
- **THRESHOLD:** the arithmetic midpoint of this arm's floor and ceiling medians — floor = P6 dose-alone **23.0**, ceiling = ×16 two-lever composition **40.0**; `(23.0 + 40.0) / 2 = 63.0 / 2 = **31.5**`.
- **ISOLATED-CAUSE (H_CA):** median **≥ 31.5** → `covered_advance` alone already drags match length materially toward the composition's elongation.
- **NOT-THE-CAUSE (H_NOT_CA):** median **< 31.5** → length stays near P6's floor; the composition's elongation requires R1 or the two-lever combination.

There is **no** second, softer prose band alongside this threshold. Every restatement of the criterion in this document uses the number 31.5 and no other. (This is the P7 defect, deliberately not repeated.)

---

## 1. The change under test — exactly one field

This overlay (`contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_ca_only_dmg16_qwen.yaml`) is a byte-copy of the P6 dose-alone overlay apart from the six isolated ledger/state paths and **one** experimental field:

| | P6 dose-alone | This arm | ×16 two-lever composition |
|---|---|---|---|
| red `movement_deck_id` | `deck.movement.v1` | **`deck.movement.v2`** | `deck.movement.v2` |
| blue `movement_deck_id` | `deck.movement.v1` | `deck.movement.v1` | `deck.movement.v1` |
| red programmer `pilot_spec_id` | `pilot.llm.qwen35` | `pilot.llm.qwen35` | `pilot.llm.qwen35_berserker_spatial_r1` |
| blue programmer `pilot_spec_id` | `pilot.llm.qwen35_sniper` | `pilot.llm.qwen35_sniper` | `pilot.llm.qwen35_sniper_spatial_r1` |
| arena | `foundry_60_asym_v1` | `foundry_60_asym_v1` | `foundry_60_asym_v1` |
| red loadout | `llm.qwen35_berserker_dmg16` | `llm.qwen35_berserker_dmg16` | `llm.qwen35_berserker_dmg16` |
| blue loadout | `llm.qwen35_sniper_ironclad_mortar_r30` | `llm.qwen35_sniper_ironclad_mortar_r30` | `llm.qwen35_sniper_ironclad_mortar_r30` |

`deck.movement.v2` shifts 6 of `deck.movement.v1`'s 8 `card.movement.advance` copies to `card.movement.covered_advance`, pool size held at 20 — a ~79.3% deal rate on a 4-card movement hand.

**Because the R1 pilot specs are absent, this arm's prompts carry no ASCII grid, no resolver-backed consequence previews, and no in-range flags at all.** That is the point of the arm and it is what makes the §4 reading uninformative by construction.

### 1a. Additivity verification

- `git status --short` on the worktree: **clean**. `git diff HEAD` restricted to every dependency (`movement_v1.yaml`, `movement_v2.yaml`, `contracts_data/cards/`, `machine_gun_dmg16.yaml`, `shrapnel_thrower_dmg16.yaml`, `artillery_mortar_r30.yaml`, `harpoon_gun.yaml`, both loadouts, `contracts_data/arenas/`, `contracts_data/pilots/`, and the P6 overlay itself) returns **empty** — this arm modifies zero existing files.
- Ancestry confirmed via `git merge-base --is-ancestor`: PR #165 `47a449ee0d3fa0231efe795e4e531ee2a31d0732` (`covered_advance` + `deck.movement.v2`), PR #191 `93aaa43d1fd5fb713a6cc3ceb157a3ea5f3aca97` (dmg16 loadout), PR #159 `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (mortar_r30) — all ancestors of this branch's HEAD.
- The arm adds exactly one new file besides this document: the overlay. No new loadout, weapon, deck, card, or pilot-spec file, and no `tests/contracts/test_pilot_registry.py` edit — every dependency's provenance is already pinned there.

---

## 2. Battery validity and the contamination guard

| Check | Value |
|---|---|
| `battery_raw.jsonl` rows | **30** |
| Distinct seeds | **30** (5001–5030) |
| Duplicate seeds / gaps | **0 / 0** |
| `match_id` collisions | 0 |
| **Unfiltered** ledger `match_started` | **34** |
| Unfiltered ledger `match_ended` | 30 |
| Orphaned `match_started` (no `match_ended`) | **4** |
| `replay_validity` | `{"player.blue": 1, "player.red": 1}` on all 30 |

**Every aggregate in this document is filtered to the 30 valid `match_id`s in `battery_raw.jsonl`.** The unfiltered count of 34 is never used as a denominator for anything (the P4-composition / P6 contamination class).

The 4 orphans reconcile exactly against the run log — each is one `LlmTransportError` skip that the driver reports loudly and then retries:

| Orphan `match_id` | Seed | Emitted at | Events |
|---|---|---|---|
| `match.01KYD3TAM9ZWEHXRBZC6B565H8` | 5025 | 17:05:27.693Z | 253 |
| `match.01KYD3TX3T3N4WPWFBSJMMT7AD` | 5025 | 17:05:46.620Z | 249 |
| `match.01KYD3VYNA6V6Y0ABYDV4NCZJE` | 5026 | 17:06:20.972Z | 119 |
| `match.01KYD3Y7MK4293FZ7WGTW5B5FM` | 5028 | 17:07:35.701Z | 179 |

Seed 5025 landed on attempt 3; seeds 5026 and 5028 on attempt 2. `34 − 30 = 4` skips, matching the 4 `SKIPPED — LlmTransportError` lines in the log one-for-one.

**Harness note worth recording:** `run_ogate_objectives_battery.py` **returns exit code 0 even when it skips a seed** (it force-fails `o_gate_pass` in the summary instead). A retry loop keyed on exit code alone therefore silently loses seeds — that is precisely how the discarded run in §9 ended up 4 rows short. This battery's loop retries on *absence of the seed's row in `battery_raw.jsonl`*, not on `rc`.

---

## 3. PRIMARY ENDPOINT — match length

| Metric | **This arm (CA alone, ×16)** | P6 (×16 dose alone) | ×16 composition (both levers) | ×8 composition (both levers) |
|---|---:|---:|---:|---:|
| min ticks | 22 | 15 | 16 | 19 |
| **median ticks** | **39.5** | **23.0** | **40.0** | 44.5 |
| mean ticks | 39.87 (all 30) / 40.34 (elim-only) | 23.3 | 47.23 (all) / 49.46 (elim-only) | 49.03 |
| max ticks | 60 | 40 | **134** | 96 |

Sorted `duration_ticks` (n=30): `22, 24, 26, 27, 27, 28, 29, 29, 30, 31, 32, 33, 34, 35, 37, 42, 42, 43, 45, 47, 47, 48, 48, 49, 53, 54, 57, 58, 59, 60`. Median = mean of the 15th and 16th values = `(37 + 42) / 2 = 39.5`.

**39.5 ≥ 31.5 → ISOLATED-CAUSE (H_CA).**

Framed against both anchors:

- vs the P6 floor: `39.5 / 23.0 = 1.717` → **+71.7%** elongation from one lever, against the two-lever arm's own **+73.9%** (`40.0 / 23.0`).
- vs the composition ceiling: `39.5 − 40.0 = −0.5` ticks, **−1.25%** — statistically indistinguishable at this granularity.
- share of the composition's median elongation attributable to this single lever: `(39.5 − 23.0) / (40.0 − 23.0) = 97.1%`.

**The one place the levers visibly differ is the tail, not the centre.** This arm's maximum is 60 ticks; the ×16 composition arm reached 134 and the ×8 arm 96. The composition's mean (47.23) also sits well above this arm's (39.87) despite near-identical medians — i.e. the second lever appears to contribute a **long right tail**, not the bulk shift. That distinction is visible in the distribution and is stated as an observation; with n=30 and one arm per condition this document does not claim to have isolated *which* lever produces the tail (the companion R1-alone decomposition arm is the surface that can answer it).

---

## 4. SECONDARY (diagnostic, explicitly NOT gating) — out-of-range fire

| | **This arm (CA alone)** | ×16 composition | ×8 composition | R1-alone (v2 arena) | pre-representation baseline (inherited, unverified) |
|---|---:|---:|---:|---:|---:|
| Red fire attempts (`weapon_fired` + `weapon_fire_rejected`) | 585 | 570 | 565 | 502 | 107 |
| Out-of-range rejections | 429 | 436 | 417 | 238 | 85 |
| **Out-of-range fraction** | **0.7333** | 0.7649 | 0.7381 | 0.4740 | 0.7944 |

Red's rejection reasons break down as `target_out_of_range: 429`, `weapon_on_cooldown: 9` — out-of-range is essentially the whole rejection budget.

**This reading is the mechanically expected one and proves nothing about the arm's question.** This arm carries no spatial R1, so there are no in-range flags in the prompt for red to use; a fraction in the 0.75–0.85 band near the pre-representation baseline (0.7944) was the prediction *regardless of which primary verdict came back*. The observed 0.7333 is in that expected region (marginally below the band's floor, and below both composition arms) and far from R1-alone's flag-informed 0.4740. The pre-registered "surprising" trigger — a fraction materially **below** 0.4740, which would have meant `covered_advance` itself suppresses out-of-range fire with no flags present — **did not fire.** No verdict is derived from this endpoint.

What this *does* establish, weakly and by elimination only: since removing R1 left out-of-range fire essentially where the two composition arms found it, the composition arms' out-of-range non-suppression is **at least consistent with** R1's flags failing to bind in that configuration. Attributing it properly requires the R1-alone decomposition arm; this arm cannot do it.

Blue's own figures for completeness: 96/355 = 0.2704 out-of-range (blue's rejections are mostly `weapon_on_cooldown`, 93), and blue's zero-hit-probability shot fraction is **87/166 = 0.5241** (×16 composition: 0.6085; `covered_advance`-alone on v2: 0.5195; R1-alone: 0.5580).

---

## 5. TERTIARY (reported context, NOT gating) — red win rate

| Metric | Value |
|---|---|
| Winner distribution | `player.red` 20, `player.blue` 9, draw/abort 1 |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5022) |
| `play_terminal_fraction` | **0.9667** (task gate ≥0.9 — PASS; codebase default ≥0.95 — **PASS**) |
| **Decided-match red win rate** | **20/29 = 0.6897**, Wilson 95% CI **[0.5077, 0.8272]** |
| All-30 red win rate | 20/30 = 0.6667, Wilson 95% CI [0.4878, 0.8077] |

Red-win seeds: 5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5010, 5015, 5017, 5018, 5019, 5020, 5021, 5024, 5025, 5026, 5028, 5030. Blue-win seeds: 5009, 5011, 5012, 5013, 5014, 5016, 5023, 5027, 5029.

| Comparison | z | p | Significant at α=0.05? |
|---|---:|---:|---|
| This arm decided (20/29) vs P6 decided (17/30) | 0.98 | 0.329 | No |
| This arm all-30 (20/30) vs P6 all-30 (17/30) | 0.80 | 0.426 | No |
| This arm decided (20/29) vs ×16 composition decided (18/28) | 0.37 | 0.708 | No |

**None of these clears significance, and none is treated as evidence of anything.** Adjacent-arm two-proportion z-tests at n≈30 have reached significance exactly once in this program's history (P6 vs P4, two dose-steps apart, z=2.26/p=0.024) — a point-estimate shift of +12pp against P6 here is fully consistent with sampling noise at this n. The reason this endpoint is reported at all is that the composition arm's own pre-registered criterion was win-rate-based; showing that a single lever reaches the same neighbourhood is context, not proof.

### 5a. Abort forensics — seed 5022

`end_reason = provider_semantic_failure`, `is_draw = true`, `failed_completions = 3`, died at tick 26. All 3 `llm_completion_failed` events carry `semantic_failure_code = malformed_json` (Pydantic validation errors on the model's response), not a transport fault. The match recorded **zero `hit_resolved` events on either side and zero `mech_destroyed`** — direct query — so it cannot have rescued either seat from an imminent loss. It is a clean provider dropout, excluded from the decided-match denominator and included in the all-30 basis.

---

## 6. `covered_advance` uptake — the lever demonstrably engaged

| Card | Dealt | Programmed | Rate |
|---|---:|---:|---:|
| `card.movement.covered_advance` | 303 | 290 | **0.9571** |
| `card.movement.advance` | 99 | 51 | 0.5152 |
| `card.movement.flank_right` | 201 | 82 | 0.4080 |
| `card.movement.flank_left` | 202 | 79 | 0.3911 |
| `card.movement.reposition` | 195 | 11 | 0.0564 |

**0.9571** sits between the ×16 composition arm's 0.9459 and the card's isolated-arm rate of 0.9586 (v2 arena) — the lever is not merely present, it is programmed at the same near-ceiling rate as everywhere else it has been measured. Whatever match-length effect §3 records, the mechanism was actually being exercised.

## 7. Rationale vocabulary — a card-name confound, stated rather than exploited

| Seat | Rationales | cover-or-LOS, **raw** substring | cover-or-LOS, **card-name stripped** | LOS-only |
|---|---:|---:|---:|---:|
| red | 250 | 171 (0.6840) | **141 (0.5640)** | 96 (0.3840) |
| blue | 250 | 49 (0.1960) | 49 (0.1960) | 22 (0.0880) |

The raw substring count is confounded: the card is literally named `covered_advance`, so a rationale that merely names the card it programmed scores a "cover" hit. Stripping `covered_advance` / `covered advance` / `covered-advance` before matching still leaves **56.4%** of red's rationales referencing cover or line-of-sight, and 38.4% referencing LOS specifically — with **no ASCII grid and no in-range flags in the prompt at all**.

**Comparability caveat, stated plainly:** the composition arms report "clean attribution" spatial vocabulary of 0.2678 (×16) and 0.2222 (×8), and R1-alone 0.2833, but this document did not re-derive those figures from their ledgers and **does not know whether their matcher applied the same card-name strip**. The numbers are therefore not safely comparable and no claim of the form "`covered_advance` produces more spatial reasoning than R1's grid" is made here. What *is* supported: giving the model a cover-semantics card, with zero spatial representation in the prompt, is followed by cover/LOS language in a majority of its rationales — a hypothesis worth a matched-matcher re-derivation, not a finding.

## 8. Mechanism checks — the combat math is untouched

### 8a. Dose verification (exact)

All 90 `hit_resolved` events paired cleanly to both a preceding same-tick `weapon_fired` (90/90) and an `armor_absorbed` at `sequence_in_tick + 1`.

| Weapon | Raw damage observed (`damage_after_armor` + `absorbed_amount`) | Prediction | Match? |
|---|---|---|---|
| `weapon.light.machine_gun_dmg16` | **89**, all 38 hits, zero variance | `int(128 × 0.7) = 89` | **exact** |
| `weapon.light.shrapnel_thrower_dmg16` | **115**, all 12 hits, zero variance | `int(192 × 0.6) = 115` | **exact** |
| `weapon.heavy.harpoon_gun` (blue) | 22, all 15 hits | — | — |
| `weapon.siege.artillery_mortar_r30` (blue) | 40, all 25 hits | — | — |

`armor_after == 0` on **50/50 red hits (100%)** — the corrected P5/P6 armor-saturation mechanism replicating again. The dose lever is behaving identically to P6; nothing about `covered_advance` alters how hard either side hits.

### 8b. Hits-to-kill and unconverted hits

| | This arm | P6 (dose alone) | ×16 composition |
|---|---:|---:|---:|
| Red kills blue — mean hits | **2.35** (n=20, median 2, `{2:13, 3:7}`) | 2.18 (n=17) | 2.39 (n=18) |
| Blue kills red — mean hits | **2.56** (n=9, median 2, `{2:5, 3:3, 4:1}`) | 2.62 (n=13) | 2.70 (n=10) |

Red's kill speed remains faster than blue's, unchanged in character from P6 — again consistent with the lever changing *how the match is played*, not the damage math.

| | This arm | P6 | ×16 composition |
|---|---:|---:|---:|
| Red hits landed | 50 | 43 | 49 |
| Red unconverted (hits in matches red lost) | **3 (6.0%)** | 6 (14.0%) | 6 (12.2%) |
| Blue hits landed | 40 | 52 | 46 |
| Blue unconverted | **17 (42.5%)** | 18 (34.6%) | 19 (41.3%) |

Blue's unconverted-hit share rises to 42.5%, essentially matching the ×16 composition arm's 41.3% and above P6's 34.6% — the approach-exposure signature the composition arm attributed to the stacked levers is present here with only `covered_advance`.

### 8c. Utility keep-rate and completion health

| Seat | Utility dealt | Programmed | Keep-rate | ×16 composition |
|---|---:|---:|---:|---:|
| red | 500 | 28 | 0.0560 | 0.0661 |
| blue | 500 | 56 | 0.1120 | 0.1288 |

| Metric | Value |
|---|---|
| `llm_completion_requested` | 522 |
| `llm_completion_resolved` | 500 |
| `llm_completion_failed` | 22 |
| `plan_committed` | 500 |
| `finish_reason` | `stop`: 500/500 (zero `length` truncations) |
| `plan_source` | `llm`: 500/500 (zero fallback/heuristic) |
| Matches with ≥1 failed completion | 15/30 |
| Max single-match failures | 3 (seed 5022, the abort) |

`522 requested − 500 resolved = 22`, matching `llm_completion_failed` exactly.

---

## 9. Discarded first run — full disclosure

A first execution of this identical overlay and identical seed plan began at 16:39:17Z and was **abandoned and wiped**, for a mechanical reason unrelated to its results:

- Seeds 5028–5030 failed with `SyntaxError: invalid syntax` on `<<<<<<< HEAD` inside `omnibase_core/enums/enum_contract_graph_edge_kind.py`. A **concurrent, unrelated session** left the canonical `omnibase_core` clone mid-merge with unresolved conflict markers, and the ambient `PYTHONPATH` pointed the battery at that clone's `src/` instead of the worktree venv's installed wheel (the known PYTHONPATH-shadowing trap).
- That run therefore landed only 26 of 30 rows (seed 5002 lost to a transport skip that the exit-code-keyed retry loop could not see; 5028–5030 lost to the import fault), and — worse — the 26 rows that *did* land resolved `omnibase_core` from a different, dirty source than any backfill would have. Backfilling would have produced a mixed-provenance battery.
- Remedy: the whole battery was re-run from scratch under `PYTHONPATH` unset, so all 30 rows resolve `omnibase-core 0.46.7` from the worktree `.venv` uniformly, with a retry loop keyed on row presence rather than exit code. The re-run is the citable battery; `--fresh` on seed 5001 wiped the first run's ledger.

**The discarded run's numbers, for transparency** (n=26, seeds 5001–5027 minus 5002, environment-contaminated, **not** citable): min 23, **median 36.5**, mean 38.15, max 78; red 17, blue 9. It would have returned the **same verdict** (36.5 ≥ 31.5 → H_CA) on the same criterion. The decision to re-run was made for provenance uniformity, before any aggregate was computed, and is disclosed here rather than silently dropped.

---

## 10. Limitations

1. **The blue standoff configuration is uncontrolled — stated explicitly, third arm running.** Blue's loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` caps `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_r30` (range 50 → 30, the P1-era approach-fix, held constant) but leaves `weapon.heavy.harpoon_gun` at its baseline **range 30, uncapped**. Red's two weapons are `machine_gun_dmg16` (**range 12**) and `shrapnel_thrower_dmg16` (**range 8**) — verified directly from the weapon contracts. Blue therefore retains a **18-cell** (30 − 12) to **22-cell** (30 − 8) standoff advantage across the whole approach. This was uncontrolled and unstated through the entire P1–P7 dose sweep and both composition arms (OMN-15119), and **this arm inherits it unchanged** — the blue loadout is byte-identical to every prior arm's. Every match-length and win-rate figure here is conditioned on that standoff; the SO-RANGECAP / SO-STANDOFF arms are the surface that varies it.
2. **The criterion's threshold is a construct, not a natural boundary.** 31.5 is the arithmetic midpoint of two point estimates from two n=30 batteries. Observed 39.5 clears it by a wide margin (+8.0 ticks, +25%), so the verdict is not threshold-sensitive here — but a result near 31.5 would have been essentially uninterpretable, and the criterion should not be reused as if the midpoint carried statistical meaning.
3. **Single-arm, single-n=30.** Every anchor in §3 is one battery per condition. The near-identity of this arm's median (39.5) and the composition arm's (40.0) is a comparison of two point estimates whose sampling variability is not characterised; it should not be read as "the second lever contributes exactly zero." The honest claim is that one lever reproduces ~97% of the median elongation, not that the other lever contributes nothing — §3 records a genuine mean/tail divergence pointing the other way.
4. **Cross-arena citations are flagged.** The `covered_advance`-alone (median 43.0 vs its own v2 baseline 33.0, +30%) and R1-alone (median 38.0 vs the same v2 baseline 33.0, +15%) figures used as context come from the **`foundry_60_asym_v2`** arena with no dose lever; this arm is `foundry_60_asym_v1` at ×16. They corroborate the direction of the result (on v2, `covered_advance` alone also elongated more than R1 alone) but are not same-arena evidence.
5. **The out-of-range endpoint is uninformative by construction** (§4) and the pre-representation baseline it is compared against (85/107 = 0.7944) is inherited and was never independently re-derived in this program.
6. **The §7 vocabulary comparison is not matcher-matched** and is explicitly not claimed as a finding.
7. **1 abort (seed 5022).** `play_terminal_fraction = 0.9667` clears both the ≥0.9 task gate and the ≥0.95 codebase default, but the battery is not the zero-abort run P6 was (1.0). The abort landed zero hits on either side, so it is not outcome-correlated.

---

## Verdict

**ISOLATED-CAUSE (H_CA).** Median match length **39.5 ≥ 31.5**. `covered_advance` alone, at the ×16 dose with no spatial R1 present, reproduces **97.1%** of the two-lever composition arm's median match-length elongation over the dose-alone floor (39.5 vs 40.0, against a floor of 23.0). The match-length negative signal that replicated unchanged across both composition arms is attributable to this one lever; it does not require spatial R1 and does not require a two-lever interaction.

Two things this arm does **not** settle, stated so the next arm is not mis-scoped:

- **Out-of-range fire is not attributed by this arm.** With no in-range flags in the prompt, 0.7333 was the expected reading whatever the primary endpoint did. Attribution needs the R1-alone decomposition arm.
- **The composition's long right tail is unexplained.** Medians match (39.5 vs 40.0) but means (39.87 vs 47.23) and maxima (60 vs 134) do not. Something in the composition — plausibly R1, plausibly the interaction — produces long matches this arm never produced. That is a live, unanswered question, not a rounding artifact.

The win-rate movement (+12pp over P6, p=0.33) is reported and is not evidence.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/composition_ca_only_dmg16/events.sqlite3` and `.onex_state/steel_onslaught/composition_ca_only_dmg16/battery_raw.jsonl` (30 rows, seeds 5001–5030). `battery_summary.json` in that directory describes only the final single-seed invocation and is not a source for any figure here.
- New overlay (the pre-registration artifact): `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_ca_only_dmg16_qwen.yaml`.
- Parent / anchor overlays, unmodified: `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p6_dmg16_qwen.yaml`, `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_p6dmg16_covadv_r1_qwen.yaml`.
- Lever contract: `contracts_data/decks/movement_v2.yaml`, `contracts_data/cards/movement_covered_advance.yaml` (PR #165).
- Held-constant contracts: `contracts_data/loadouts/llm_qwen35_berserker_dmg16.yaml`, `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`, `contracts_data/weapons/harpoon_gun.yaml`, `contracts_data/weapons/artillery_mortar_r30.yaml`, `contracts_data/weapons/machine_gun_dmg16.yaml`, `contracts_data/weapons/shrapnel_thrower_dmg16.yaml`, `contracts_data/decks/movement_v1.yaml`.
- Sibling arm evidence: `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md` (the floor anchor), `docs/evidence/2026-07-24-composition-p6dmg16-covadv-r1-battery.md` (the ceiling anchor), `docs/evidence/2026-07-24-composition-p4dmg8-covadv-r1-battery.md`, `docs/evidence/2026-07-24-covered-advance-battery.md`, `docs/evidence/2026-07-24-spatial_r1-battery.md`.
- Battery driver: `scripts/run_ogate_objectives_battery.py`.
- Program register: `docs/steel_onslaught/LEARNINGS.md` (in the `omni_home` workspace).
- No secrets, keys, or absolute paths included.
