# Spatial Representation ARM R2 Battery — Show-Don't-Tell + Required Spatial-Read Scaffold (2026-07-24)

**Verdict:** **FAILED on outcome, DIRECTIONAL on cognition — consistent with ARM R1, scaffold added no measurable win-rate lift.** Decided-match red (brawler) win rate is **0/24 = 0.0000** — inside the `<0.10` FAILED band, identical to R1 and every prior v1/v2 anchor. The representation (R1's map/previews/flags) plus the required one-line `spatial_read` scaffold both demonstrably reached the model: red plan rationales referencing cover/LOS-blocking concepts (clean-attribution, excluding persona-confounded "range") ran **22.8% (56/246)**, versus a **0/209** pre-representation baseline and comparable to R1's own 28.3%. Out-of-range fire fraction held at **46.1%** (R1: 47.4%; baseline: 79.4%) and blue's zero-hit-probability shot fraction held at **55.0%** (R1: 55.8%; baseline: 41.1%). All three cognition signals replicate R1 within noise — the scaffold did not measurably deepen or degrade the cognition shift R1 already established, and it did not move outcome. **`play_terminal_fraction=0.80` is BELOW the ≥0.9 trust gate** (6/30 aborts) — flagged explicitly below; the abort cause is independently traced to a pre-existing blue/sniper-seat JSON-malformation failure mode, not the red-side scaffold, so the win-rate/cognition read on the 24 decided matches is not invalidated, but the battery as a whole does not clear the stated trust threshold and a re-run to backfill to n=30 decided matches is recommended before treating this as a closed measurement.

**Ledger:** two-segment battery, concatenated for reporting (no hand-editing) — `.onex_state/steel_onslaught/spatial_r2_battery` (seeds 5001–5017, `events.sqlite3`, `battery_raw.jsonl`) + `.onex_state/steel_onslaught/spatial_r2_battery_part3` (seeds 5018–5030, same file set + `battery_summary.json`), both in the SO-SHOWMAP worktree at HEAD `4b87310` (branch `feat/so-spatial-representation`, PR #167 merged `7cb8634` on `main`).
**Change under test:** PR #167 (merged) — same additive spatial-representation layer as R1 (`spatial_view.py` DTOs, `match/spatial_preview.py` pure functions calling the same resolver/LOS primitives the live match uses, wired into `match/card_adapter.py`/`llm/programming.py` behind `spatial_representation: Literal["none","grid","grid_scaffold"]`, default `"none"`). ARM R2 sets `spatial_representation: grid_scaffold` — R1's map/previews/flags **plus** a required one-line `spatial_read` field in the response JSON, added before register selection, schema-tolerant (an omitted field is logged, never a hard failure — see Vacuity check §2 and the abort-attribution finding below). New pilot spec: `contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_spatial_r2.yaml` (red, `parent: pilot.llm.qwen35_berserker_spatial_r1`). Overlay: `contracts_data/overlays/tactical_split_overdeal_utility_asym_v2_spatial_r2_qwen.yaml` — **both seats** bound to grid_scaffold specs (symmetric information; confirmed below, blue's system-prompt length also grew by the scaffold-addendum's exact byte length).
**Model:** live Qwen3.6-35B-A3B, n=30, seeds 5001–5030. `play_terminal_fraction=0.80` (24/30 elimination, 6/30 abort) — **below the ≥0.9 trust gate.**
**Baseline anchors:** v2, no spatial representation (`docs/evidence/2026-07-24-brawler-recut-v2-battery.md`) — 0/30 red wins, median 33 ticks, blue LOS-blocked-shot fraction 41.1%, red utility keep-rate 0.0526. Cognition arm-zero (pre-representation): 0/209 red rationales mentioning terrain/cover/LOS; 85/107 red fire attempts out of range. R1 (`docs/evidence/2026-07-24-spatial_r1-battery.md`, this session's direct predecessor, same repo/ledger access): 0/30 red wins, median 38 ticks, cover-or-LOS clean-attribution 77/272 (28.3%), out-of-range fraction 47.4%, blue zero-probability fraction 55.8%, red utility keep-rate 0.0772.
- All figures below are independently recomputed from the raw sqlite ledgers (`events.sqlite3` × 2 state roots), not copied from the runner's report — the runner's raw per-seed tally was cross-checked row-for-row and matches exactly (see Vacuity check).

---

## Vacuity check (run first)

**PASS — not vacuous, on both counts (base representation and R2 scaffold).**

1. **Raw tally cross-check.** All 30 seed rows (`terminal_class`, `winner_player_id`, `duration_ticks`, `vp_totals`, `failed_completions`) recomputed directly from `battery_raw.jsonl` in both state roots match the runner's reported table exactly, seed-for-seed. Seeds are unique across the two segments (no duplicates), consistent with the reported crash-and-resplice run history (two `LlmTransportError` crashes at 5012 and 5018, no ledger hand-edits).
2. **Config wiring, statically read from `main`-derived code:** `llm_qwen35_berserker_spatial_r2.yaml` sets `spatial_representation: grid_scaffold`; `programming_system_prompt()` (`llm/programming.py`) appends `_SPATIAL_GRID_INSTRUCTIONS` whenever `spatial_representation != "none"` and additionally `_SPATIAL_SCAFFOLD_INSTRUCTIONS` (the required `spatial_read` field, exact text reproduced in the runner's raw tally and verified byte-identical against the source constant) only when `== "grid_scaffold"`. `card_adapter.py::_spatial_fields` computes `spatial_grid`/`movement_previews`/`weapon_range_flags` by calling `render_ascii_grid`, `compute_movement_previews`, `compute_weapon_range_flags` — the latter two import `resolve_move_destination` directly from `match.move_resolution`, the same function the live match resolver uses, not a reimplementation (`spatial_preview.py:18`). `tests/llm/test_llm_programming.py::test_serialized_prompt_surfaces_spatial_grid_and_previews_when_opted_in` passes on this checkout.
3. **Runtime signal from this battery's own ledger.** Red seat (`persona_id=berserker`), tick 1, seed 5001: `system_prompt_length=5248`, `user_prompt_length=10760` — independently re-queried from `events.sqlite3` and matches the runner's cited figures exactly. **Cross-arm confirmation that both seats received the R2 scaffold** (a check the R1 doc could not make, since R1 had no scaffold): blue seat (`persona_id=sniper`) `system_prompt_length` is **5901** in this R2 battery vs **5321** in the R1 battery (`spatial_r1_battery/events.sqlite3`) — a delta of **+580 chars**, which is exactly `len(_SPATIAL_SCAFFOLD_INSTRUCTIONS) + 2` (578 + 2 newlines = 580, computed directly from the source constant in `programming.py`). This confirms the scaffold text is present in both seats' system prompts, not just red's, matching the overlay's symmetric-binding design.
4. **`spatial_read` is parsed but never persisted to any durable event — a real gap, noted for completeness, not fatal to this measurement.** `LLMProgrammingPilot._parse_response` (`programming.py:783`) reads `parsed.spatial_read` off the raw completion, logs a warning if it is `None` when required, but the constructed `ModelSOPlanCommittedPayload` (`programming.py:794`) does **not** carry `spatial_read` through — confirmed by querying all 264 `plan_committed` payloads in this battery: **zero** contain a `spatial_read` key. This means the *content* of the model's spatial-read sentences (when present) is unrecoverable from the ledger; only the wire contract that it was *requested* is verifiable (points 2–3 above), and only omissions are logged (as a WARNING, not persisted as an event either — filed as a documentation/traceability gap, not a re-run blocker, since the cognition read below uses `rationale`, which is persisted).

Both seats bound to grid_scaffold specs (symmetric), consistent with the fairness design goal stated in the task.

---

## Axis 1 — Outcome (win rate, terminal health)

| Metric | Value |
|---|---|
| `match_started` / raw rows | 30 / 30 (1:1, zero orphans, seeds 5001–5030 all unique) |
| **play_terminal_fraction** | **0.80 (24/30) — BELOW the ≥0.9 trust gate** |
| Terminal-class mix | elimination 24/30 (80.0%), abort 6/30 (20.0%) |
| Abort breakdown | `aborted` 3/30 (5007, 5013, 5027), `provider_semantic_failure` 3/30 (5014, 5020, 5024) |
| Winner distribution (decided matches only) | player.blue 24 / player.red 0 |
| **Decided-match red win rate** | **0/24 = 0.0000 — FAILED band (<0.10)** |

Independently recomputed from both `events.sqlite3` ledgers: `winner_player_id='player.blue'` for all 24 non-abort matches, `terminal_class='elimination'` for the same 24; `mech_destroyed` fires for `player.red` in exactly those 24 matches and zero times for `player.blue` — red is eliminated in every decided match, never the reverse.

**Trust-gate flag.** This battery's `play_terminal_fraction` (0.80) is materially below R1's (1.0) and below the stated ≥0.9 gate. Per the abort-attribution finding below, none of the 6 aborts trace to the red-side scaffold under test, so the 0/24 decided-match result is not itself suspect — but 24 decided matches (vs the intended 30) is a smaller effective sample, and a formal re-run to backfill 6 more decided seeds is recommended before citing this battery as a closed n=30 measurement.

## Abort attribution (independent finding — corrects the raw tally's "cannot distinguish from this data alone" caveat)

The runner's raw tally flags the 4/6 `provider_semantic_failure` aborts as an open question: "warrants a look at whether the scaffold is actually triggering malformed-JSON aborts under load." **This is resolvable from the ledger and the answer is no.** Querying `llm_completion_failed` events (`subject_json.player_id`) for all 6 abort seeds:

| Seed | End reason | `semantic_failure_code` / `reason_code` | Seat |
|---|---|---|---|
| 5007 | aborted | `None` / `length` (truncated completion) | **player.blue** |
| 5013 | aborted | `None` / `length` | **player.blue** |
| 5014 | provider_semantic_failure | `malformed_json` / `invalid_response` ×3 | **player.blue** |
| 5020 | provider_semantic_failure | `malformed_json` / `invalid_response` ×3 | **player.blue** |
| 5024 | provider_semantic_failure | `malformed_json` / `invalid_response` ×3 | **player.blue** |
| 5027 | aborted | `None` / `length` | **player.blue** |

**All 6 aborts (100%) are attributed to `mech.blue.01`/`player.blue` (the sniper seat) — zero to `player.red` (the berserker seat under test).** This matches a documented, pre-existing failure mode unrelated to R2: a code comment at `programming.py:244` explicitly calls out "the sniper-specific abort driver, since the verbose sniper persona invites more chain-of-thought than the terse brawler" for reasoning-gateway `<think>`-span leaks that defeat JSON extraction. `spatial_read` is schema-tolerant by design (Vacuity check §4 above — an omission is logged, never raised as a semantic error), and even if it were the cause, the mechanism could only produce an error on the seat that omits a *required* field — red's spec sets `grid_scaffold` and `spatial_read_required=True` for red only in the *requirement* sense (though blue also receives the scaffold text symmetrically, only red's plan-parse path treats it as "required" per `card_adapter.py:704`, `spatial_read_required=request.spatial_representation == "grid_scaffold"`, evaluated per-seat). Blue is the one aborting, and blue's failures are the known sniper-verbosity `malformed_json`/`length` pattern, not a spatial_read-shaped defect. **Conclusion: the elevated abort rate (6/30 vs R1's 0/30) is not attributable to the R2 scaffold under test; it is sniper-seat prompt-length/verbosity variance, plausibly aggravated by the +580-char scaffold addendum now also present in blue's system prompt (Vacuity check §3), but not proven causal from this data — a fair caveat, distinct from the raw tally's broader and unresolved framing.**

## Match length

| Metric | R2 (this battery, 24 decided) | R1 anchor | v2 baseline anchor |
|---|---:|---:|---:|
| median ticks | 37.5 | 38.0 | 33.0 |
| mean ticks | 41.1 | 42.5 | 33.4 |
| min / max ticks | 10 / 114 | 21 / 77 | 14 / 53 |

Red survival is flat vs R1 (median 37.5 vs 38.0 — within noise) and still elevated vs the v2 baseline (+14% median). `mech_destroyed` for `player.red` fires in all 24 decided matches at a mean tick of 41.1, confirming red's death is the terminal event in every decided match, same as R1.

## Utility keep-rate per seat

Method: `hand_dealt.card_ids` (dealt) vs `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by seat — identical method to the R1/v2 baseline docs.

| Seat | R2 programmed / dealt | R2 keep-rate | R1 keep-rate | v2 baseline keep-rate |
|---|---:|---:|---:|---:|
| red (brawler) | 46 / 492 | **0.0935** | 0.0772 | 0.0526 |
| blue (sniper) | 80 / 492 | **0.1626** | 0.1360 | 0.1794 |

Red's keep-rate continues the R1 direction (v2 → R1 → R2: 0.0526 → 0.0772 → 0.0935, a monotonic rise), consistent with red continuing to find reasons to hold utility (smoke/chaff) cards as spatial information accumulates across arms. Blue's is between R1 and v2, not clearly directional. As with R1, this is a drafting-behavior shift, not a win-rate shift.

## Failed completions

Total `failed_completions` across the battery: **14**, distributed 5003=1, 5007=1, 5013=1, 5014=3, 5020=3, 5024=3, 5027=1, 5030=1 — independently recomputed from `battery_raw.jsonl` in both state roots and matches the runner's table exactly. Compare R1: 7 total, 0 aborts (all resolved within retry budget). R2's higher failed-completion count and its conversion into 6 outright aborts (vs R1's 0) is consistent with the abort-attribution finding above — concentrated on 6 blue-seat matches rather than spread thin across many matches.

---

## Axis 2 — Cognition read (the point of this lane)

### 1. Red plan rationales referencing spatial concepts

Same clean-attribution method as R1 (word-boundary-safe regex; "range" excluded as confounded — the berserker persona doctrine's own "CLOSE TO POINT-BLANK RANGE IMMEDIATELY" line produces "range" hits with no spatial-representation involvement):

| Keyword | Red mentions / 246 plans | Fraction |
|---|---:|---:|
| terrain (literal word) | 0 | 0.0% |
| cover | 24 | 9.8% |
| LOS / "line of sight" / "sightline" | 33 | 13.4% |
| **cover OR LOS (clean attribution)** | **56** | **22.8%** |
| range (confounded, reported not used) | 137 | 55.7% |
| obstacle | 0 | 0.0% |

**Baseline is 0/209.** R2's clean-attribution rate (22.8%) is a large, sustained jump from that baseline and comparable to R1's 28.3% (within the range expected for n=246 vs n=272 plans and normal seed-to-seed variance — not a statistically distinguishable difference without a formal test, but clearly not a regression to zero). Sample red rationales (verbatim, from this battery):
- "Close-range brawl for objective control, flank left to block LOS and secure east gate."
- "Flank for cover, fire harpoon twice while in range, advance to maintain standoff." *(blue example, shown for contrast — sniper doctrine already references cover pre-arm, so blue's numbers are not clean-attribution, same caveat as R1)*
- Red: "Advance to objective while firing both weapons and flanking for cover."

### 2. Out-of-range fire attempts

| | R2 (this battery) | R1 anchor | v2/arm-zero baseline |
|---|---:|---:|---:|
| Red fire attempts (`weapon_fired` + `weapon_fire_rejected` = `weapon_fire_intent`) | 471 | 502 | 107 |
| Red out-of-range rejections (`weapon_fire_rejected.reason='target_out_of_range'`) | 217 | 238 | 85 |
| **Out-of-range fraction** | **217/471 = 46.1%** | **47.4%** | **79.4%** |

Held flat vs R1 (46.1% vs 47.4%, within noise) and a sustained 33-point improvement over baseline. The in-range-now flags continue to suppress wasted fire attempts at the same rate whether or not the scaffold is present.

### 3. Blue zero-hit-probability (LOS-blocked) shot fraction

| | R2 (this battery) | R1 anchor | v2 baseline |
|---|---:|---:|---:|
| Blue `weapon_fired` total | 242 | 269 | — |
| Blue `weapon_fired` with `hit_probability=0.0` | 133 | 150 | — |
| **Zero-probability fraction** | **133/242 = 55.0%** | **55.8%** | **41.1%** |

Held flat vs R1 (55.0% vs 55.8%) and a sustained 14-point rise over baseline — consistent with red's cover/LOS-blocking behavior (axis 2.1) persisting at the same intensity under R2.

### 4. Red survival + blue hits landed per match

| | R2 (this battery, 24 decided) | R1 anchor | baseline |
|---|---:|---:|---:|
| Red survival ticks (= match duration, red destroyed in 24/24 decided matches) | median 37.5, mean 41.1 | median 38.0, mean 42.5 | median 33 (v2) |
| Blue hits landed per match (`hit_resolved`, `attacker_id=mech.blue.01`, hit=true) | 65 / 24 = **2.71** (median 3.0) | 2.63 | ~2.5 |

Both flat vs R1 within noise, both modestly elevated vs the pre-representation baseline. As in R1, the representation shifts red's survival and firing behavior without changing blue's kill efficiency or the terminal outcome.

---

## Verdict

**FAILED on outcome, DIRECTIONAL on cognition — same verdict shape as R1, scaffold added no measurable delta on either axis.**

- **Outcome axis:** 0/24 decided-match red wins (0.0000), inside the `<0.10` FAILED band. **`play_terminal_fraction=0.80` does not clear the ≥0.9 trust gate** — 6/30 aborts, all independently traced to a pre-existing blue/sniper-seat JSON-malformation/truncation failure mode unrelated to the red-side scaffold under test (see Abort attribution above). The 0/24 result is not invalidated by this, but the battery is short of a clean n=30 and a backfill re-run is recommended before treating it as closed.
- **Cognition axis:** replicates R1 within noise on all four measured signals — clean-attribution cover/LOS mentions (22.8% vs R1's 28.3%, both far above the 0/209 baseline), out-of-range fire fraction (46.1% vs R1's 47.4%, both far below baseline's 79.4%), blue zero-probability shot fraction (55.0% vs R1's 55.8%, both above baseline's 41.1%), and red survival/blue-hits-landed (flat vs R1, modestly above baseline). Utility keep-rate continues a monotonic rise across v2→R1→R2 (0.0526→0.0772→0.0935).
- **What the scaffold changed:** nothing measurable on cognition rate or outcome. The required `spatial_read` field's actual content is not recoverable from the ledger (Vacuity check §4) — only its presence/absence signal exists (as an unlogged-to-events WARNING on omission), so this battery cannot directly test whether the *scaffolded sentence itself* is higher-quality than R1's unscaffolded reasoning, only whether register selection and downstream behavior changed. It did not, within the resolution of these metrics.

**Bottom line — ARM R2 does not add value over ARM R1 on the metrics available.** The representation (map + previews + range flags) is doing the cognition work; the added one-line requirement to articulate a spatial read before selecting registers produced no distinguishable shift in rationale content, wasted-fire suppression, LOS-blocking behavior, survival, or win rate. Combined with R1's finding, representation-only (R1) remains the more defensible design if this program continues to test "show, don't tell" variants — the extra scaffold requirement adds prompt length and (plausibly, not proven) abort-rate risk without a demonstrated cognition or outcome benefit. Neither arm has moved red off 0 wins.

---

## Citations (all relative paths, from repo root)

- `.onex_state/steel_onslaught/spatial_r2_battery/battery_raw.jsonl`, `events.sqlite3` — seeds 5001–5017
- `.onex_state/steel_onslaught/spatial_r2_battery_part3/battery_raw.jsonl`, `events.sqlite3`, `battery_summary.json` — seeds 5018–5030
- `docs/evidence/2026-07-24-spatial_r1-battery.md` — R1 anchor (same program, prior arm)
- `docs/evidence/2026-07-24-brawler-recut-v2-battery.md` — v2/arm-zero anchor
- `contracts_data/overlays/tactical_split_overdeal_utility_asym_v2_spatial_r2_qwen.yaml`
- `contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_spatial_r2.yaml`
- `src/steel_onslaught/pilots/spatial_view.py`, `src/steel_onslaught/match/spatial_preview.py`, `src/steel_onslaught/llm/programming.py` (`_SPATIAL_SCAFFOLD_INSTRUCTIONS`, `_parse_response`), `src/steel_onslaught/match/card_adapter.py` (`_spatial_fields`)
