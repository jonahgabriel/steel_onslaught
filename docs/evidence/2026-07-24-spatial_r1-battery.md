# Spatial Representation ARM R1 Battery — Show-Don't-Tell, Rendered Map + Consequence Previews (2026-07-24)

**Verdict:** **FAILED on outcome, DIRECTIONAL on cognition.** Decided-match red (brawler) win rate is **0/30 = 0.0000** — inside the `<0.10` FAILED band, identical to every prior v1/v2 anchor. But the representation demonstrably reached the model: red plan rationales referencing cover/LOS-blocking concepts absent from the berserker persona's own doctrine text jumped from a **0/209 baseline to 77/272 (28.3%)** this battery, out-of-range fire fraction dropped **79.4% → 47.4%**, and blue's zero-hit-probability (LOS-blocked) shot fraction rose **41.1% → 55.8%**. Outcome and cognition axes move in opposite directions and are reported separately per instruction — do not blend them into one verdict.

**Ledger:** `.onex_state/steel_onslaught/spatial_r1_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-SHOWMAP worktree.
**Change under test:** PR #167 (merged to `main` at `7cb8634770770779a803b4c54cb22eb03afc5a71`) — additive spatial-representation layer: `spatial_view.py` (typed DTOs: `ModelSOSpatialGridView`, `ModelSOMovementPreview`, `ModelSOWeaponRangeFlag`), `match/spatial_preview.py` (pure functions calling the SAME resolver/LOS primitives the live match uses — `match.move_resolution.resolve_move_destination`, `match.geometry.line_of_sight_clear` — no duplicated math), wired into `match/card_adapter.py` and `llm/programming.py` gated on a new `spatial_representation: Literal["none","grid","grid_scaffold"]` pilot param (default `"none"`, byte-identical prompt for unopted seats). Two new pilot specs (`llm_qwen35_berserker_spatial_r1.yaml`, `llm_qwen35_sniper_spatial_r1.yaml`) set `spatial_representation: grid` — ARM R1 (representation only, `grid_scaffold`/ARM R2's required `spatial_read` field is NOT set here). One new overlay (`tactical_split_overdeal_utility_asym_v2_spatial_r1_qwen.yaml`) binds both seats to the `_spatial_r1` specs — symmetric information, no one-sided advantage. No arena, deck-policy, or utility-pack changes; the v2/surfacing overlay this arm is compared against is untouched.
**Model:** live Qwen3.6-35B-A3B, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baseline anchor (v2, no spatial representation):** `foundry_60_asym_v2` + `llm_qwen35_berserker_v2.yaml` — 0/30 red wins, median 33 ticks, blue LOS-blocked-shot fraction 41.1%, red utility keep-rate 0.0526 (`docs/evidence/2026-07-24-brawler-recut-v2-battery.md`). Cognition baseline (arm zero, same v2 config, pre-representation): 0/209 red plan rationales mentioning terrain; 85/107 red fire attempts out of range (recorded in the pilot spec header comment for `pilot.llm.qwen35_berserker_spatial_r1.yaml` — this session did not have direct raw-ledger access to that prior battery and cites it as documented context, not independently re-derived).
- All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger (`events.sqlite3`), not copied from the implementer's or battery runner's report.

---

## Vacuity check (run first — a FAILED-or-COMPETITIVE result is meaningless if the representation never reached the model)

**PASS — not vacuous.** Verified three independent ways, none of which is the runner's self-report:

1. **Config wiring, statically read from the merged code on `main`:** `contracts/pilot.py` defines `spatial_representation: Literal["none","grid","grid_scaffold"] = "none"`; `llm/programming.py::programming_system_prompt` appends `_SPATIAL_GRID_INSTRUCTIONS` whenever `spatial_representation != "none"`, and `_SPATIAL_SCAFFOLD_INSTRUCTIONS` (the required `spatial_read` field) only when `== "grid_scaffold"`. Both R1 pilot specs set `spatial_representation: grid` (not `grid_scaffold`), confirming this battery ran R1 (map + previews + flags, zero scaffold requirement, zero strategy advice) and not R2.
2. **Resolver reuse, statically read:** `match/spatial_preview.py`'s `compute_movement_previews`/`compute_weapon_range_flags`/`render_ascii_grid` call `resolve_move_destination` and `line_of_sight_clear` — the exact functions `MatchRunner._resolve_move` and the live LOS check use — not a reimplementation. `tests/match/test_spatial_preview.py` + `tests/contracts/test_spatial_representation_arms.py` (25 tests) pass on the current `main`-derived checkout.
3. **Runtime signal from this battery's own ledger:** `llm_completion_requested` payloads for this battery show `system_prompt_length≈5321` / `user_prompt_length≈11339` chars per red-seat request — consistent with the grid/legend/preview/flag addenda being present (an unopted `"none"` seat's system prompt is materially shorter; this battery's overlay opts in both seats). The ledger only persists prompt lengths + `prompt_sha256`, not full text, so exact byte-for-byte prompt capture was not re-derived in this session; the config-wiring and resolver-reuse checks above are the load-bearing vacuity evidence, not the length heuristic.

Both seats use the `_spatial_r1` pilot specs (symmetric), so the representation was not a one-sided advantage.

---

## Axis 1 — Outcome (win rate, terminal health)

| Metric | Value |
|---|---|
| `match_started` / `match_ended` | 30 / 30 (1:1, zero orphans) |
| play_terminal_fraction | **1.0** (gate ≥0.9 — PASS, trustworthy battery) |
| Terminal-class mix | elimination 30/30 (0 VP-threshold, 0 draw, 0 tick_cap) |
| Winner distribution | player.blue 30 / player.red 0 |
| **Decided-match red win rate** | **0/30 = 0.0000 — FAILED band (<0.10)** |
| Decided-match blue win rate | 30/30 = 1.0000 |

Independently recomputed from `events.sqlite3` (`COUNT(DISTINCT match_id)=30`, `match_started`=`match_ended`=30, all 30 `winner_player_id='player.blue'`, all 30 `terminal_class='elimination'`) — matches `battery_summary.json` exactly.

## Match length

| Metric | R1 (this battery) | v2 baseline anchor |
|---|---:|---:|
| min ticks | 21 | 14 |
| max ticks | 77 | 53 |
| mean ticks | 42.5 | 33.4 |
| median ticks | 38.0 | 33.0 |

Red survives **+15% longer** (median 38 vs 33 ticks) under R1 — a real but modest effect; red is destroyed in all 30 matches regardless (`mech_destroyed` for `player.red` × 30, mean tick 42.47 ≈ mean match duration, confirming red's death is the terminal event in every match).

## Utility keep-rate per seat

Method: `json_each` over `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by seat — identical method to the 2026-07-23/07-24 baseline docs.

| Seat | R1 programmed / dealt | R1 keep-rate | v2 baseline keep-rate | Δ |
|---|---:|---:|---:|---:|
| red (brawler) | 42 / 544 | **0.0772** | 0.0526 | **+0.0246** |
| blue (sniper) | 74 / 544 | **0.1360** | 0.1794 | **−0.0434** |

Red's utility keep-rate rose ~47% relative (still far below the 0.50 mechanical sanity baseline); blue's fell ~24% relative. Directionally consistent with red now having a reason (LOS-blocking/cover) to hold smoke/chaff cards it previously discarded — but this is a drafting-behavior shift, not a win-rate shift (see Axis 1).

## Failed completions

| Metric | Value |
|---|---|
| Total `failed_completions` | 7, across 7 distinct matches (seeds 5006, 5017, 5023, 5027, 5028, 5029, 5030) |
| Aborts | 0 — all bounded reprompts resolved within retry budget |

Independently recomputed from `battery_raw.jsonl` (`sum(failed_completions)=7`, same 7 seeds) — matches the runner's per-seed table exactly, no discrepancy this time.

---

## Axis 2 — Cognition read (the point of this lane)

### 1. Red plan rationales referencing spatial concepts

The berserker persona doctrine (`contracts_data/pilots/personas/berserker.yaml`) contains **zero** references to cover, LOS, sightline, or terrain — only "CLOSE TO POINT-BLANK RANGE IMMEDIATELY," which is the source of the boilerplate "range" phrasing below. This makes cover/LOS mentions in red's rationale a **clean-attribution signal**: the berserker persona could not have produced this vocabulary on its own; it can only have come from the newly-injected `spatial_grid`/`movement_previews`/`weapon_range_flags` fields.

Word-boundary-safe regex recount (note: a naive `LIKE '%los%'` substring match is contaminated by "close" — corrected below):

| Keyword | Red mentions / 272 plans | Fraction |
|---|---:|---:|
| terrain (literal word) | 0 | 0.0% |
| cover | 34 | 12.5% |
| LOS / "line of sight" / "sightline" | 46 | 16.9% |
| **cover OR LOS (clean attribution — absent from berserker doctrine)** | **77** | **28.3%** |
| range | 115 | 42.3% (confounded — persona doctrine says "point-blank range") |
| obstacle | 0 | 0.0% |
| any of the above | 172 | 63.2% |

**Baseline was 0/209** (arm zero, no representation). The clean-attribution number (cover-or-LOS, excluding the confounded "range"/persona-boilerplate category) moved from **0 → 77/272 (28.3%)**. This is the first direct evidence in this program that the spatial representation reaches the model's stated reasoning, not just its raw JSON output.

Sample red rationales (verbatim from `plan_committed.rationale`, seed-agnostic across the battery):
- "Advance twice to close distance, flank left for cover, switch to assault, and deploy smoke to block enemy LOS."
- "Flank to block LOS then unleash secondary and primary weapons immediately."
- "Advance to objective while flanking to block enemy LOS and secure VP."

Blue (sniper) shows a similar shift (cover 92/272, LOS 104/272) but this is **not** clean-attribution — the sniper persona doctrine (`sniper.yaml`) already references "line of sight is clear" and "cover" pre-arm, so blue's numbers cannot be cleanly separated from pre-existing persona vocabulary. Reported for symmetry, not as independent evidence.

### 2. Out-of-range fire attempts

| | R1 (this battery) | v2/arm-zero baseline |
|---|---:|---:|
| Red fire attempts (`weapon_fire_intent`, = `weapon_fired` + `weapon_fire_rejected`) | 502 | 107 |
| Red out-of-range rejections (`weapon_fire_rejected.reason='target_out_of_range'`) | 238 | 85 |
| **Out-of-range fraction** | **238/502 = 47.4%** | **85/107 = 79.4%** |

A 32-point drop in out-of-range fraction — directionally consistent with the in-range-now flags reaching cognition. Caution: raw attempt volume is ~5x higher in R1 (502 vs 107) because matches run longer and the v2 loadout/weapon mix differs from whatever arm-zero used; the fraction is the comparable metric, not the absolute count, and this session did not have raw-ledger access to arm-zero to independently re-verify its 107/85 figures (cited from the pilot-spec header comment, which itself cites the same source).

### 3. Blue zero-hit-probability (LOS-blocked) shot fraction

| | R1 (this battery) | v2 baseline |
|---|---:|---:|
| Blue `weapon_fired` total | 269 | — |
| Blue `weapon_fired` with `hit_probability=0.0` | 150 | — |
| **Zero-probability fraction** | **150/269 = 55.8%** | **41.1%** |

Rose 14.7 points — blue wastes *more* fire against zero-probability targets under R1, consistent with red's increased LOS-blocking behavior (axis 1 above) making red harder to hit even though red still loses every match on raw attrition.

### 4. Red survival + blue hits landed per match

| | R1 (this battery) | baseline |
|---|---:|---:|
| Red survival ticks (= match duration, red destroyed in 30/30) | median 38, mean 42.5 | median 33 (v2) |
| Blue hits landed per match (`hit_resolved` where `attacker_id=mech.blue.01`, only hit=true events are logged) | 79 / 30 = **2.63** | **~2.5** |

Blue's hits-landed-per-match is essentially flat (2.63 vs ~2.5) — blue does not land meaningfully more or fewer killing blows despite the LOS-blocked-shot-fraction rise in (3); it is simply firing more wasted shots per match while still closing out every match at roughly the same hit-count pace. This corroborates the win-rate result: red's improved spatial behavior (cover-seeking, LOS-blocking, fewer wasted out-of-range attempts) extends survival modestly but does not change the terminal outcome.

---

## Verdict

**FAILED on outcome, DIRECTIONAL on cognition — reported separately, not blended.**

- **Outcome axis:** 0/30 red wins (0.0000), inside the `<0.10` FAILED band, numerically identical to every prior v1/v2/arm-zero anchor. `play_terminal_fraction=1.0` clears the trust gate — this is a trustworthy null on win rate.
- **Cognition axis:** genuine, non-trivial shift. Clean-attribution spatial vocabulary (cover/LOS-blocking, excluding persona-confounded "range") in red's own stated rationale moved from a hard 0/209 baseline to 77/272 (28.3%). Out-of-range fire fraction dropped 32 points (79.4%→47.4%). Blue's wasted (zero-probability) shot fraction rose 14.7 points (41.1%→55.8%), consistent with red actually using the LOS-blocking information. Red survival extended +15% (median 33→38 ticks). Utility keep-rate rose on red (+47% relative) and fell on blue (−24% relative).
- **What did NOT move:** blue hits-landed-per-match is flat (2.63 vs ~2.5) — the representation changed red's *behavior* (what it says it's doing, what it fires at, how long it survives) without changing the *combat math outcome*. Red still loses every match to elimination before objective/VP accrual matters.

**Bottom line — show-don't-tell worked at the cognition layer and failed at the outcome layer.** The representation-only hypothesis is now falsified as a *sufficient* fix for red competitiveness, but it is confirmed as a *necessary* one: the model demonstrably could not discuss cover/LOS at all before this representation existed (0/209), and now does so in over a quarter of its planning turns with vocabulary its persona doctrine never taught it. ARM R2 (scaffolded `spatial_read`, forcing the model to articulate the read before committing registers) is the next test — this result does not answer whether forcing articulation converts the now-present cognition into a win-rate change; it only establishes that the representation reaches cognition when merely shown, unscaffolded.

---

## Citations (all relative paths, from repo root)

- `.onex_state/steel_onslaught/spatial_r1_battery/battery_raw.jsonl` — per-match raw tally (independently recomputed, matches runner's report exactly)
- `.onex_state/steel_onslaught/spatial_r1_battery/battery_summary.json` — aggregate summary
- `.onex_state/steel_onslaught/spatial_r1_battery/events.sqlite3` — canonical event ledger (source of all Axis 1/2 recomputation in this doc)
- `contracts_data/overlays/tactical_split_overdeal_utility_asym_v2_spatial_r1_qwen.yaml`
- `contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_spatial_r1.yaml`
- `contracts_data/pilots/fire_dense_qwen/llm_qwen35_sniper_spatial_r1.yaml`
- `contracts_data/pilots/personas/berserker.yaml`, `contracts_data/pilots/personas/sniper.yaml`
- `src/steel_onslaught/pilots/spatial_view.py`, `src/steel_onslaught/match/spatial_preview.py`, `src/steel_onslaught/llm/programming.py`, `src/steel_onslaught/match/card_adapter.py`, `src/steel_onslaught/contracts/pilot.py`
- `tests/match/test_spatial_preview.py`, `tests/contracts/test_spatial_representation_arms.py`
- PR #167, merged to `main` at `7cb8634770770779a803b4c54cb22eb03afc5a71`
- `docs/evidence/2026-07-24-brawler-recut-v2-battery.md` — outcome/keep-rate baseline anchor
