# Brawler Re-Cut v2 Battery — Arena Sightline Breaks + Medium-Range Refit (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/30 = 0.0000** — below the 0.10 FAILED threshold, and identical to the qwen35 asym v1 anchor (also 0/30). The combined arena + loadout re-cut produced **zero measurable change in outcome**.

**Ledger:** `.onex_state/steel_onslaught/brawler_recut_v2_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-RECUT worktree.
**Change under test:** PR #157 (merged to `main` at `233b3eb5d01b915c5e4d4b8bf43e09c26c4db448`) — `foundry_60_asym_v2.yaml` (two inset cover blocks break the y=28–32 sniper sightline into three segments) + `llm_qwen35_berserker_v2.yaml` (swaps `weapon.light.shrapnel_thrower` → `weapon.medium.heat_lance`, fills freed slot with `gizmo.efficiency.efficient_regulator`) + `tactical_split_overdeal_utility_asym_v2_qwen.yaml` (rebinds the proven overlay shape to arena v2). All three v2 files are additive; v1 files are byte-identical pre/post-merge (verified below).
**Model:** live Qwen3.6-35B-A3B, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baseline anchor:** qwen35 asym v1 combined overlay — 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue utility keep-rate 0.1657 (`.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
- All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger, not copied from the implementer's or battery runner's report.

---

## Method

- **Decided-match win rate per seat** = wins ÷ `match_ended` count, aborts excluded from denominator (there were no aborts this run — see Completion health below).
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt. `json_each`/`json_extract` over `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by `seat`. Identical method to the 2026-07-23 baseline doc.
- **Terminal-class mix** from `match_ended.payload_json.reason` / `battery_summary.json.terminal_classes`.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_ended` events (= decided matches) | 30 / 30 |
| `match_started` events | 30 (1:1 with `match_ended`, zero orphans) |
| play_terminal_fraction | **1.0** (gate: ≥0.9 — PASS, battery is trustworthy) |
| Terminal-class mix | elimination 30/30 (0 VP-threshold, 0 draw, 0 tick_cap) |
| Winner distribution | player.blue 30 / player.red 0 |
| **Decided-match red win rate** | **0/30 = 0.0000** |
| Decided-match blue win rate | 30/30 = 1.0000 |
| terminal reason | `last_mech_standing` × 30 (from `match_ended` payload) |

No aborts occurred, so the decided-match denominator equals the raw match count (30). `all_replay_valid=true` and `o_gate_pass=true` in `battery_summary.json` are consistent with the raw ledger.

## 2. Match length

| Metric | v2 (this battery) | v1 anchor |
|---|---:|---:|
| min ticks | 14 | 17 |
| max ticks | 53 | 71 |
| mean ticks | 33.4 | — (not reported in anchor doc) |
| median ticks | 33.0 | 31 |

Match length did **not** collapse or grow materially — median rose 31 → 33 (+2 ticks, +6.5%), well within noise for n=30. The sightline-breaking cover did not measurably lengthen approach time, and the heat-lance swap did not measurably shorten kill time.

## 3. Utility keep-rate (causal-attribution check)

| Seat | v2 programmed / dealt | v2 keep-rate | v1 anchor keep-rate | Δ |
|---|---:|---:|---:|---:|
| red (brawler) | 22 / 418 | **0.0526** | 0.0552 | −0.0026 |
| blue (sniper) | 75 / 418 | **0.1794** | 0.1657 | +0.0137 |
| all-card (sanity, both seats) | 1045 / 2090 | 0.5000 | 0.5000 (mechanical) | 0 |

Keep-rate held flat on both seats (red essentially unchanged, blue +0.0137 — noise-band for n=30, not a directional shift). This confirms the re-cut is genuinely geometric/loadout-only and did not perturb the draft-layer behavior. **However, because win-rate also did not move (0/30 → 0/30), this is not a clean positive causal attribution — there is no outcome change to attribute to the flat keep-rate.** The only valid claim is negative: the re-cut changed neither drafting behavior nor outcome.

## 4. Objectives (secondary signal, not the gating metric)

| Objective | Awards | Red | Blue | Matches scored |
|---|---:|---:|---:|---:|
| objective.west_yard | 46 | 46 | 0 | 9 |
| objective.north_works | 9 | 9 | 0 | 3 |
| objective.east_gate | 8 | 5 | 3 | 4 |

Red continues to accumulate objective control awards (60 of 63 total awards) in matches where it survives long enough to hold ground, consistent with prior batteries — but this has never converted to a VP-threshold win in any recorded battery on this arena family, and does not here either (0/30 VP terminals).

## 5. Completion health

| Metric | Value |
|---|---|
| `llm_completion_failed` total | 19 |
| Matches with ≥1 failure | **14 / 30** (not 15 — see discrepancy note below) |
| Max single-match failures | 3 (seeds 5016, 5022) |
| Matches reaching `LlmSemanticExhaustedError`/abort | 0 |
| `match_ended` reason | `last_mech_standing` × 30, zero `provider_semantic_failure` aborts |

All 19 failures were bounded semantic retries that resolved within the retry budget; none escalated to an abort. This matches the "no aborts" claim in both upstream reports.

**Discrepancy flagged:** the battery runner's raw tally text states failures occurred in "15 of 30 matches," but both the runner's own per-seed table (14 seeds with nonzero counts: 5001, 5007, 5013, 5014, 5015, 5016, 5017, 5019, 5020, 5022, 5023, 5026, 5028, 5029) and the independently recomputed `SELECT COUNT(DISTINCT match_id)` against `events.sqlite3` agree on **14**, not 15. The sum (19) and max-count claims are correct. This is a minor internal inconsistency in the raw tally's own prose, not a ledger integrity problem — flagged for the record, does not affect the verdict.

---

## 6. Merge / additivity verification

- PR #157 merged to `main` at `233b3eb5d01b915c5e4d4b8bf43e09c26c4db448` (`gh pr view 157`: state MERGED, mergedAt 2026-07-24T14:27:24Z).
- 4/4 CI checks green on the PR head **and independently reconfirmed green on the merge commit itself** (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: success`).
- `git diff 378d7d7 233b3eb -- contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml` returns **empty** — all three v1 baseline files are byte-identical across the merge. Only new files (`*_v2.yaml`, `tactical_split_overdeal_utility_asym_v2_qwen.yaml`) and two mechanical catalog-assertion updates (`test_arena.py`, `test_pilot_registry.py`, +9/−1 lines) landed.

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/30), inside the `<0.10` FAILED band and numerically identical to the v1 anchor's 0/30. `play_terminal_fraction=1.0` clears the ≥0.9 trust gate, so this is a trustworthy null result, not a measurement artifact. Match length is flat (median 31→33). Utility keep-rate is flat on both seats (red 0.0552→0.0526, blue 0.1657→0.1794), confirming the change was purely geometric/loadout as designed — but with win-rate also flat, there is nothing for the flat keep-rate to be a clean control for. The combined re-cut (sightline breaks + medium-weapon refit) did not move the brawler off a 0/30 record.

**Most important next lever:** the failure mode is not upstream of combat — it is *within* combat. Two independent priors already established (a) elimination outruns VP accrual in 100% of matches regardless of overlay, and (b) the brawler drafts utility at sub-chance rates. This re-cut targeted approach-phase sightline exposure and post-arrival damage math, and neither moved the outcome, which suggests the bottleneck is earlier in the causal chain than either lever reached — most plausibly the brawler's **tactical decision-making under the LLM planner** (does it actually path through the new cover, or does the planner ignore terrain-relative reasoning entirely?). Before any further geometry/loadout iteration, instrument `plan_committed.rationale` + `movement_resolved` positions per-tick against the new cover-block coordinates (x=20-24/x=36-40, y=29-31) to check whether the brawler's movement register choices ever route through the broken sightline segments, or whether it continues to approach on the same exposed line as v1 regardless of the new cover being available. If the brawler never uses the cover, the geometry fix is inert by construction and the real blocker is planner-level spatial reasoning, not arena design.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/brawler_recut_v2_battery/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `llm_completion_failed` event types), cross-checked against `battery_summary.json` in the same directory.
- v1 anchor: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- Merge commit: `233b3eb5d01b915c5e4d4b8bf43e09c26c4db448` (PR #157, `main`).
- No secrets, keys, or absolute paths included.
