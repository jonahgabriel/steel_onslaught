# Decomposition Arm SO-COMP-R1 — Spatial R1 Alone at Red-Damage ×16 (2026-07-25)

**Verdict: PARTIAL ATTRIBUTION.** Exactly one of the two pre-registered endpoints crosses. Red's out-of-range fire fraction is **212/313 = 0.6773 ≥ 0.60** (Threshold A crosses — spatial R1 alone *does* substantially reproduce the composition arms' suppression failure), while median match length is **25.5 < 31.5 ticks** (Threshold B does not cross — spatial R1 alone does **not** reproduce the match-length inflation). Per the criterion committed before the first match ran, that is PARTIAL ATTRIBUTION, an explicitly legitimate terminal outcome, not a result to be forced into a binary call.

Read plainly: **the two negative signals that replicated across both composition arms have different causes.** Out-of-range fire is attributable in large part to the spatial R1 representation lever by itself; match-length inflation is not — that one is left to `covered_advance` or the two-lever interaction, which the sibling arm SO-COMP-CA tests.

**Ledger:** `.onex_state/steel_onslaught/composition_r1_only_dmg16` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`).
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, per-seed isolated process invocation (`--fresh` only on seed 5001, up to 2 attempts per seed on a 420 s timeout).
All figures below are **independently recomputed** from `events.sqlite3` and `battery_raw.jsonl`. `battery_summary.json` and driver stdout are not the source of any number here.

---

## 0. Why this arm exists

Both composition arms — `docs/evidence/2026-07-24-composition-p4dmg8-covadv-r1-battery.md` (×8) and `docs/evidence/2026-07-24-composition-p6dmg16-covadv-r1-battery.md` (×16) — stack **two** levers simultaneously on top of their dose-alone parent:

1. Red `movement_deck_id` `deck.movement.v1` → `deck.movement.v2` (adds `card.movement.covered_advance`, PR #165). Blue's movement deck is never touched in any arm of this program.
2. Both seats' card-programmer `pilot_spec_id` → the spatial R1 pilot specs (`pilot.llm.qwen35_berserker_spatial_r1` / `_sniper_spatial_r1`, PR #167) — ASCII grid, resolver-backed consequence previews, in-range flags, `spatial_representation: grid`.

(The "three additive rebindings" phrasing in both composition overlay headers counts these two levers at *field* granularity — one red `movement_deck_id` field plus two `pilot_spec_id` fields — not three distinct levers.)

Two **negative** signals replicated essentially unchanged across both composition arms: out-of-range fire stayed near the pre-representation baseline (×8 417/565 = 0.7381, ×16 436/570 = 0.7649, against R1-alone's own 238/502 = 0.4740) and match length roughly doubled the dose-alone baseline (×16 composition median 40.0 vs P6's 23.0). Nobody had isolated which lever caused them. **This arm applies only lever 2.** The sibling arm SO-COMP-R1's counterpart, SO-COMP-CA, applies only lever 1.

## 1. Pre-registration (committed before the first `match_started` event)

| | |
|---|---|
| Pre-registration commit | `28102317fa15087121d54d7dc47d3f1d87990941` |
| Commit timestamp | `2026-07-25T16:38:25Z` |
| First `match_started` event `emitted_at` | `2026-07-25T16:38:55.879124+00:00` |
| **Gap** | **+30.9 s (positive)** — the criterion was fixed in git before any match data existed |

The overlay's own header comment carries the criterion verbatim. **One formal criterion, two thresholds, no accompanying illustrative band.**

**Threshold A — out-of-range fire fraction (red seat): 0.60.**
Derivation: arithmetic midpoint between R1-alone's own suppression result (`238/502 = 0.4740`) and the composition arms' pooled ceiling (mean of `417/565 = 0.7381` and `436/570 = 0.7649` = `0.7515`):
`(0.4740 + 0.7515) / 2 = 0.61275` → rounded **down** to **0.60**. Rounding down is the conservative direction here: it makes ISOLATED-CAUSE *easier* to reach, so it does not flatter a "not the cause" reading.

**Threshold B — median match length: 31.5 ticks.**
Derivation: arithmetic midpoint between the P6 dose-alone floor (23.0) and the ×16 composition ceiling (40.0): `(23.0 + 40.0) / 2 = 31.5` exactly.

| Outcome | Rule |
|---|---|
| **ISOLATED-CAUSE** (R1 alone reproduces both negative signals) | out-of-range ≥ 0.60 **AND** median ≥ 31.5 |
| **NOT-THE-CAUSE** (R1 alone reproduces neither) | out-of-range < 0.60 **AND** median < 31.5 |
| **PARTIAL ATTRIBUTION** | exactly one endpoint crosses — a legitimate terminal outcome |

Secondary, reported but never used to decide the above: decided red win rate against P6's `17/30 = 0.5667`, with Wilson 95% CI and a two-proportion z-test.

## 2. The change under test

Exactly one new file: `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_r1_only_dmg16_qwen.yaml`.

Below the header comment the overlay is a byte-copy of the ×16 dose-alone parent (`contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p6_dmg16_qwen.yaml`) apart from **16 diff lines**: 6 lines of isolated ledger/state paths (4 config fields) and the 2 `pilot_spec_id` lines. Verified mechanically by diffing the two files from `schema_version:` onward.

| Field | P6 parent | This arm |
|---|---|---|
| red `pilot_spec_id` | `pilot.llm.qwen35` | `pilot.llm.qwen35_berserker_spatial_r1` |
| blue `pilot_spec_id` | `pilot.llm.qwen35_sniper` | `pilot.llm.qwen35_sniper_spatial_r1` |
| red `movement_deck_id` | `deck.movement.v1` | `deck.movement.v1` — **unchanged** |
| blue `movement_deck_id` | `deck.movement.v1` | `deck.movement.v1` — **unchanged** |
| arena | `foundry_60_asym_v1` | unchanged |
| red loadout | `loadout.llm.qwen35_berserker_dmg16` | unchanged |
| blue loadout | `loadout.llm.qwen35_sniper_ironclad_mortar_r30` | unchanged |

**`card.movement.covered_advance` is absent from this arm entirely** — confirmed empirically in §7: it appears in zero dealt hands and zero committed registers across all 30 matches.

`git diff HEAD` against every dependency file (both loadouts, both movement decks, both R1 pilot specs, the P6 overlay, the ×16 composition overlay) returns **empty**; `git merge-base --is-ancestor 93aaa43d1fd5fb713a6cc3ceb157a3ea5f3aca97 HEAD` confirms PR #191's merge commit is an ancestor. No test-file edit was needed — the dmg16 loadout is already provenance-pinned in `tests/contracts/test_pilot_registry.py` under PR #191, mortar_r30 under PR #159/#170, and both R1 pilot specs under PR #167.

## 3. Battery validity and the contamination guard

| Check | Value |
|---|---|
| `battery_raw.jsonl` rows | **30** |
| Distinct seeds | **30**, exactly 5001–5030, zero duplicates, zero gaps |
| Raw `match_started` events in `events.sqlite3` | **31** |
| `match_ended` events | **30** |
| Orphaned `match_started` (no `match_ended`) | **1** — `match.01KYD2BH2ER97JKW54TPAF0PQ8`, 118 events, `16:39:54Z`–`16:40:24Z` |
| Replay validity | `{player.red: 1, player.blue: 1}` on all 30 matches |

The single orphan is exactly the contamination class the P4-composition and P6 arms hit: seed 5004 failed on its first attempt with `LlmTransportError` and succeeded on a retry, leaving one partial-match `match_started` with no `match_ended`. **Every query in this document filters explicitly to the 30 valid `match_id`s present in `battery_raw.jsonl`.** The unfiltered ledger count of 31 is never used as a denominator anywhere.

**Environment note (recorded, not hidden):** the seed-5004 retry initially failed for a reason unrelated to the experiment — a concurrent session left the workspace's canonical `omnibase_core` clone (which the ambient `PYTHONPATH` points at) mid-merge-conflict, producing an import-time `SyntaxError`. The retry was run against a detached git worktree pinned to that clone's pre-merge `HEAD` (`c746bfb38d81f5b51b4b55cd24d164a2cf886127`), i.e. the same source tree the other 29 seeds imported, rather than falling back to a different `omnibase_core` build. Seed 5004 then completed on the first attempt.

## 4. Primary endpoint A — out-of-range fire

Method (identical to both composition docs): red-seat `weapon_fire_rejected` events with `reason == 'target_out_of_range'`, divided by red-seat (`weapon_fired` + `weapon_fire_rejected`), filtered to the 30 valid matches.

| | **This arm (R1 alone, ×16)** | ×16 composition | ×8 composition | R1-alone (v2 arena, zero dose) | pre-representation baseline (inherited) |
|---|---:|---:|---:|---:|---:|
| Red fire attempts | **313** | 570 | 565 | 502 | 107 |
| Out-of-range rejections | **212** | 436 | 417 | 238 | 85 |
| **Out-of-range fraction** | **0.6773** | 0.7649 | 0.7381 | 0.4740 | 0.7944 |

**Threshold A (0.60) — CROSSES.** 0.6773 sits well above the bar, close to the composition arms' 0.74–0.76 band and far from R1-alone's own 0.4740.

Supplementary two-proportion z-tests (reported for shape, not used to decide the criterion):

| Comparison | z | p |
|---|---:|---:|
| vs R1-alone 238/502 (**CROSS-ARENA** — v2 arena, zero dose) | 5.67 | <0.0001 |
| vs ×16 composition 436/570 | −2.82 | 0.005 |
| vs ×8 composition 417/565 | −1.91 | 0.056 |
| vs pre-representation baseline 85/107 | −2.30 | 0.022 |

This arm is significantly *worse* than R1-alone's suppression result and significantly *better* than the ×16 composition arm's — it lands between them, materially nearer the composition end. The R1-alone comparison is cross-arena (that arm ran on the v2 arena with zero dose) and must not be read as a like-for-like delta; the composition comparisons are same-arena, same-loadouts, same-dose and are the load-bearing ones.

Red's remaining rejections are 6 `weapon_on_cooldown`. Blue's out-of-range fraction is `36/221 = 0.1629` — the same seat asymmetry every arm in this program shows, and a direct consequence of the standoff configuration described in §11.

## 5. Primary endpoint B — match length

Method: `duration_ticks` on each `battery_raw.jsonl` row (sourced from the `MATCH_SCORED` payload in `scripts/run_ogate_objectives_battery.py`).

| Metric | **This arm (R1 alone)** | P6 (×16 dose alone) | ×16 composition | ×8 composition | P4 (×8 dose alone) |
|---|---:|---:|---:|---:|---:|
| min ticks | 11 | 15 | 16 | 19 | 14 |
| **median ticks** | **25.5** | 23.0 | 40.0 | 44.5 | 24 |
| mean ticks (all) | 27.77 | 23.3 | 47.23 | 49.03 | 24.07 |
| mean ticks (elimination only) | 28.34 (n=29) | — | 49.46 | — | — |
| max ticks | 52 | 40 | 134 | 96 | 38 |

**Threshold B (31.5) — DOES NOT CROSS.** Median 25.5 is +10.9 % over P6's dose-alone 23.0 and −36.3 % below the ×16 composition arm's 40.0. Mean is +19.2 % over P6. This arm sits close to the dose-alone floor, not the composition ceiling: the near-doubling of match length under composition is **not** reproduced by the spatial R1 lever alone.

Full sorted distribution: 11, 16, 17, 18, 18, 19, 19, 22, 22, 22, 23, 23, 25, 25, 25, 26, 27, 28, 28, 30, 30, 31, 32, 33, 34, 37, 37, 51, 52, 52.

## 6. Verdict against the pre-registered criterion

| Endpoint | Threshold | Observed | Crosses? |
|---|---:|---:|---|
| A — out-of-range fire fraction (red) | ≥ 0.60 | **0.6773** | **YES** |
| B — median match length | ≥ 31.5 | **25.5** | **NO** |

Exactly one endpoint crosses → **PARTIAL ATTRIBUTION**.

Substantively: spatial R1 by itself accounts for most of the composition arms' out-of-range-fire degradation (0.6773 against R1-alone's own 0.4740, and against the composition band of 0.7381–0.7649), but accounts for very little of the match-length inflation (25.5 against a dose-alone floor of 23.0 and a composition ceiling of 40.0). The two negative signals do not share a cause. What this arm cannot say is whether the residual out-of-range gap between 0.6773 and 0.7649 comes from `covered_advance`, from the interaction, or from run-to-run noise — SO-COMP-CA is the arm that addresses the first of those.

A mechanistic reading worth flagging as **hypothesis, not finding**: R1-alone's low 0.4740 was measured at zero dose on the v2 arena, where red had little reason to spam fire; here red carries the ×16 loadout, and the in-range flags apparently compete with a high-lethality incentive to fire regardless. That is exactly the hypothesis the ×8 composition doc floated. This arm is consistent with it but does not test it — the dose and the arena both differ from the R1-alone comparison.

## 7. Secondary and supporting metrics

### 7a. Win rate and terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` (valid matches) | 30 / 30 |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5008) |
| `play_terminal_fraction` | **0.9667** — clears both the task's ≥0.90 gate and the codebase's stricter ≥0.95 default |
| Winner distribution | player.red 19, player.blue 10, draw 1 (the abort) |
| **Decided red win rate** | **19/29 = 0.6552**, Wilson 95 % CI **[0.4735, 0.8006]** |
| All-30 red win rate | 19/30 = 0.6333, Wilson 95 % CI [0.4551, 0.7813] |

Red wins: seeds 5002, 5003, 5004, 5005, 5007, 5009, 5011, 5012, 5016, 5017, 5018, 5020, 5022, 5023, 5025, 5026, 5027, 5029, 5030.

| Comparison vs P6 (17/30 = 0.5667) | z | p | Significant at α=0.05? |
|---|---:|---:|---|
| decided (19/29) vs P6 (17/30) | 0.70 | 0.486 | No |
| all-30 (19/30) vs P6 (17/30) | 0.53 | 0.598 | No |

**Do not over-read this.** The point estimate is above P6's, but the comparison is not statistically separated, and **no adjacent-arm comparison in this program has reached significance at n≈30 except one** — P6 vs P4, which were two dose steps apart (z=2.26, p=0.024). A 19/30-vs-17/30 gap is two matches. It is reported because the pre-registration says to report it, and it decides nothing.

### 7b. Abort forensics (seed 5008)

`end_reason=provider_semantic_failure`, died at **tick 11 with zero `hit_resolved` events on either side**, 3 consecutive `llm_completion_failed` events with `semantic_failure_code=invalid_action_parameters` ("program uses cards not present in the dealt hand"). Same failure class the ×16 composition arm logged for its seed 5020. Zero hits landed means the abort cannot be systematically rescuing either side from an imminent loss; it is a clean early-round provider dropout, not outcome-correlated.

### 7c. Dose verification — the corrected P6 mechanism replicates again

Raw damage recovered as `damage_after_armor + armor_absorbed.absorbed_amount`, pairing each `hit_resolved` with the `armor_absorbed` event at `sequence_in_tick + 1` and with the preceding same-tick, same-seat `weapon_fired`. **89/89 hits paired cleanly, zero unattributed.**

| Weapon | Raw damage observed | Predicted | Match? |
|---|---:|---|---|
| `weapon.light.machine_gun_dmg16` | **89** (n=28, zero variance) | `int(128 × 0.7) = 89` | **exact** |
| `weapon.light.shrapnel_thrower_dmg16` | **115** (n=19, zero variance) | `int(192 × 0.6) = 115` | **exact** |
| `weapon.siege.artillery_mortar_r30` (blue) | 40 (n=28, zero variance) | — | — |
| `weapon.heavy.harpoon_gun` (blue) | 22 (n=14, zero variance) | — | — |

`armor_after == 0` on **47/47 red hits (100 %)**, replicating the corrected P5/P6 armor mechanism. Mean red damage-after-armor: 78.21 (machine gun) / 106.63 (shrapnel thrower).

### 7d. Hits-to-kill (per-kill-sequence method)

| | This arm | ×16 composition | P6 (dose alone) |
|---|---:|---:|---:|
| Red kills blue — mean hits | **2.16** (n=19, median 2, `{2:16, 3:3}`) | 2.39 | 2.18 |
| Blue kills red — mean hits | **2.70** (n=10, median 3, `{2:3, 3:7}`) | 2.70 | 2.62 |

Red's kill speed still leads blue's, matching P6 almost exactly — the R1 lever changes nothing about the underlying damage math, consistent with §7c. The standing LEARNINGS caveat about the biased crude estimator applies; this is the per-kill-sequence method.

### 7e. Unconverted-hit share

| | This arm | ×16 composition | P6 (dose alone) |
|---|---:|---:|---:|
| Red hits landed / in wins / unconverted | 47 / 41 (87.2 %) / 6 (**12.8 %**) | 49 / 43 / 6 (12.2 %) | 43 / 37 / 6 (14.0 %) |
| Blue hits landed / in wins / unconverted | 42 / 27 (64.3 %) / 15 (**35.7 %**) | 46 / 27 / 19 (41.3 %) | 52 / 34 / 18 (34.6 %) |

Blue's unconverted share (35.7 %) sits essentially at P6's 34.6 %, below the composition arm's 41.3 % — the further rise under composition is not reproduced by R1 alone.

### 7f. Spatial R1 vocabulary

Rationale-text scan over committed plans, **red seat only**, matching the composition docs' denominator convention (their 295 is exactly half of that arm's 590 committed plans; here 179 is half of 358). Regex: `cover\w*` OR `LOS` OR `line[- ]of[- ]sight` for clean attribution; `range` / `in-range` / `out-of-range` for the confounded band.

| | **This arm (red seat)** | ×16 composition | ×8 composition | R1-alone (v2 arena) |
|---|---:|---:|---:|---:|
| cover OR LOS (clean attribution) | **48/179 = 0.2682** | 79/295 = 0.2678 | 68/306 = 0.2222 | 77/272 = 0.2833 |
| range (confounded) | 87/179 = 0.4860 | 76/295 = 0.2576 | 74/306 = 0.2418 | 115/272 = 0.4228 |

Clean-attribution vocabulary is **0.2682**, indistinguishable from the ×16 composition arm's 0.2678 and close to R1-alone's 0.2833 — the R1 lever's own vocabulary effect is fully preserved without `covered_advance`. Blue's rate is much higher (104/179 = 0.5810), which is why the per-seat convention matters; the both-seats figure would be 152/358 = 0.4246 and is **not** comparable to the published composition numbers.

### 7g. Blue zero-probability shot fraction

| | This arm | ×16 composition | ×8 composition | `covered_advance`-alone | R1-alone |
|---|---:|---:|---:|---:|---:|
| Blue `weapon_fired` | 120 | 212 | 217 | 256 | 269 |
| Zero-probability shots | 43 | 129 | 108 | 133 | 150 |
| **Fraction** | **0.3583** | 0.6085 | 0.4977 | 0.5195 | 0.5580 |

**The lowest recorded in the program**, and roughly half the ×16 composition arm's. This is the clearest evidence that the composition arms' LOS-denial signal is driven by `covered_advance`, not by the spatial R1 representation: strip `covered_advance` and blue stops wasting shots on blocked targets. It also coheres with §5 — no LOS-denial means fewer stalled exchanges means shorter matches.

### 7h. Card programming rates (movement partition, `deck.movement.v1`)

| Card | Dealt | Programmed | Rate |
|---|---:|---:|---:|
| `card.movement.advance` | 570 | 420 | 0.7368 |
| `card.movement.flank_right` | 287 | 190 | 0.6620 |
| `card.movement.flank_left` | 289 | 187 | 0.6471 |
| `card.movement.reposition` | 286 | 136 | 0.4755 |
| `card.movement.covered_advance` | **0** | **0** | — (absent, as designed) |

The zero row is the empirical proof that this arm carries no `covered_advance`: it is dealt zero times across all 30 matches, confirming both seats stayed on `deck.movement.v1`.

### 7i. Utility keep-rate and completion health

| Seat | Utility dealt | Programmed | Keep-rate | ×16 composition |
|---|---:|---:|---:|---:|
| red (brawler) | 358 | 17 | 0.0475 | 0.0661 |
| blue (sniper) | 358 | 54 | 0.1508 | 0.1288 |

| Metric | Value |
|---|---|
| `llm_completion_requested` | 367 |
| `llm_completion_resolved` | 358 |
| `llm_completion_failed` | 9 |
| `plan_committed` | 358 |
| `finish_reason` distribution | `stop`: 358/358 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 358/358 (zero fallback/heuristic) |
| Matches with ≥1 failed completion | 6/30 (seeds 5008×3, 5025×2, 5004, 5005, 5016, 5027) |
| Matches reaching an unrecovered abort | 1/30 (seed 5008) |

367 requested − 358 resolved = 9, matching `llm_completion_failed` exactly; resolved = committed with no gap.

---

## 8. Limitations

**Blue standoff configuration (stated explicitly, by name).** The blue loadout `loadout.llm.qwen35_sniper_ironclad_mortar_r30` (`contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`) caps `weapon.siege.artillery_mortar` to range 30 — the P1-era "approach-fix", held constant across every arm here — but leaves `weapon.heavy.harpoon_gun` at its **baseline range 30, uncapped**. Per OMN-15119 and the 2026-07-25 handoff §2–3, that is an **18–22 cell standoff advantage for blue** which was uncontrolled and unstated through the entire P1–P7 dose sweep and both composition arms. **This arm inherits that identical uncontrolled standoff** (same blue loadout, unmodified). It is stated here rather than silently repeated a third time. Red's 0.6773 out-of-range fraction is measured inside that standoff and is not a property of the R1 representation in isolation; the SO-RANGECAP / SO-STANDOFF arms are the ones that move this variable.

**Cross-arena comparisons.** R1-alone (238/502 = 0.4740) and `covered_advance`-alone both ran on the **v2 arena at zero dose**. Every comparison against them in this document is cross-arena *and* cross-dose and is flagged as such at each use. The load-bearing comparisons — against P6 and against the ×16 composition arm — are same-arena, same-loadouts, same-dose, same-seed-range.

**No out-of-range figure exists for P6.** The dose-alone parent never measured out-of-range fire (the non-R1 pilot specs do not carry in-range flags). This arm's 0.6773 is therefore the first out-of-range reading at this dose on this arena for an R1-carrying condition, not a re-derivation of any prior number.

**n=30, adjacent-arm z-tests.** Adjacent-arm win-rate comparisons at n≈30 have reached significance exactly once in this program (P6 vs P4, two dose steps apart). Neither the win-rate secondary here nor any single-match difference should be read as an effect. The primary criterion is deliberately threshold-based rather than significance-based for this reason.

**Partial attribution is partial.** This arm shows the R1 lever alone reproduces one negative signal and not the other. It does **not** establish that `covered_advance` causes the match-length inflation — that requires SO-COMP-CA. If SO-COMP-CA also fails to reproduce it, the inflation is an interaction effect and neither single-lever arm can attribute it.

**Rationale-text vocabulary is a proxy.** §7f counts regex hits in free-text rationales, not verified spatial reasoning. The regex is stated inline so it can be re-run; a different regex would give different numbers, and the cross-arm comparison is only valid because the same per-seat denominator convention is used.

**Environment.** One seed's retry ran after a concurrent session corrupted the workspace's canonical `omnibase_core` clone; it was re-run against a pinned worktree of that clone's pre-merge `HEAD` so all 30 seeds used the same source tree (§3). This is recorded because it is the kind of detail that silently invalidates a battery if left unstated.

---

## 9. Citations (relative paths only)

- Recomputed metrics: `.onex_state/steel_onslaught/composition_r1_only_dmg16/events.sqlite3` and `.onex_state/steel_onslaught/composition_r1_only_dmg16/battery_raw.jsonl` (30 rows, seeds 5001–5030).
- New overlay (the only new contract file this arm adds): `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_r1_only_dmg16_qwen.yaml`.
- Dose-alone parent / comparison floor: `contracts_data/overlays/tactical_split_overdeal_utility_asym_pair_p6_dmg16_qwen.yaml`, `docs/evidence/2026-07-24-pair_p6_dmg16-battery.md`.
- Stacked composition ceiling: `contracts_data/overlays/tactical_split_overdeal_utility_asym_composition_p6dmg16_covadv_r1_qwen.yaml`, `docs/evidence/2026-07-24-composition-p6dmg16-covadv-r1-battery.md`, and `docs/evidence/2026-07-24-composition-p4dmg8-covadv-r1-battery.md`.
- Single-lever R1 anchor (cross-arena): `docs/evidence/2026-07-24-spatial_r1-battery.md`.
- Standoff context: `docs/evidence/2026-07-25-rangecap_r15_dmg16-battery.md`, `docs/evidence/2026-07-25-standoff_r15_dmg16-battery.md`.
- Pilot specs under test (unmodified): `contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_spatial_r1.yaml`, `contracts_data/pilots/fire_dense_qwen/llm_qwen35_sniper_spatial_r1.yaml`.
- Loadouts (unmodified): `contracts_data/loadouts/llm_qwen35_berserker_dmg16.yaml`, `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_r30.yaml`.
- Battery driver: `scripts/run_ogate_objectives_battery.py`.
- Program register: `docs/steel_onslaught/LEARNINGS.md`.
- No secrets, keys, or absolute paths included.
