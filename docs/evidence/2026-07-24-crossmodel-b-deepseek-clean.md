# Cross-Model B — DeepSeek-V4-Flash CLEAN rerun (n=22 partial)

**Status:** CLEAN partial. Killed at 22/30 complete matches after ~14h (~32 min/match). n=22 is a clean partial, killed for time — NOT a failure.
**Supersedes:** This datapoint **SUPERSEDES the earlier CONFOUNDED DeepSeek run** (red 0.0735 / blue 0.3088) for the deepseek-family cross-model B slot. The confounded run's numbers came from ~2.3 rounds/match with an abort storm (every match aborted early); they are not a valid measurement of programmed utility and should not be quoted as the deepseek datapoint.

**Ledger:** `.onex_state/steel_onslaught/ugate_deepseek_clean_battery` (`events.sqlite3` + `battery_raw.jsonl`).
**Config:** deepseek-v4-flash, `max_tokens=16384`, full-length matches, restricted to the 22 complete `match_id`s in `battery_raw.jsonl`. The one started-but-incomplete match (killed mid-run) is excluded from all figures.

---

## Method

- **Complete-match filter:** 22 `match_id`s from `battery_raw.jsonl`; 1 extra `match_started` (the killed in-progress match) excluded.
- **Utility keep-rate per seat = utility cards programmed / utility cards dealt.** `json_each` over `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed), matching `card.utility.%`, grouped by `seat`.
- **Chance reference = 0.50** — each round deals 10 cards and commits 5 registers; the all-card keep-rate below confirms exactly 0.50, so 0.50 is the correct null for "program utility at random."

---

## Recomputed keep-rate table (n=22 complete matches)

| Seat | Utility programmed | Utility dealt | **Utility keep-rate** | Sub-chance (<0.50)? |
|------|-------------------:|--------------:|----------------------:|:-------------------:|
| red  | 34  | 278 | **0.1223** | YES (strong) |
| blue | 113 | 278 | **0.4065** | YES (mild) |
| combined | 147 | 556 | **0.2644** | YES |

**All-card keep-rate (sanity):** red 695/1390 = **0.5000**, blue 695/1390 = **0.5000**. Exactly chance on both seats — confirms the 5-of-10 register structure and validates 0.50 as the null. Utility is programmed **below** the rate at which cards are kept overall, on both seats.

---

## Completion health — NO abort storm, full-length, clean

| Metric | Value |
|--------|-------|
| `failed_completions` (battery_raw, per match) | 0 for all 22 (sum 0) |
| `llm_completion_requested` / `llm_completion_resolved` | 278 / 278 (1:1) |
| `*fail*` event types anywhere in DB | **none** |
| `finish_reason` distribution | **stop: 278 / 278** (zero `length` truncations) |
| `plan_source` distribution | **llm: 278 / 278** (zero fallback/heuristic plans) |
| completion tokens (min / mean / max) | 706 / 3218 / 8928 (max well under the 16384 cap) |

Every plan was a real LLM completion that terminated on `stop` — no abort storm, no token-cap truncation, no fallback plans. This is the fix working: the confounded run's abort storm is gone.

**Match length / terminal class:**

| Metric | Value |
|--------|-------|
| terminal_class | elimination: 22 / 22 |
| victory_kind | elimination: 22 / 22 |
| winner | player.blue: 22 / 22 (0 draws) |
| mean rounds/match | **6.32** (range 3–10) |
| mean duration_ticks | 28.95 (range 12–47) |

Matches ran to natural elimination, not to an abort. **Mean 6.32 rounds/match** (not ~12 — matches end on a kill, and deepseek's play resolved eliminations in ~6 rounds). This is ~2.7× the confounded run's ~2.3 rounds/match: full-length, healthy play. Note blue won all 22 and also programmed ~3.3× the utility red did (113 vs 34) — reported as an observation, not a causal claim (n=22, single-seat-winner).

---

## Clean vs confounded — did the magnitude hold once matches ran healthy?

| Seat | Confounded (aborted, ~2.3 rds) | **CLEAN (full-length, ~6.3 rds)** | Direction | Distance below chance (conf → clean) |
|------|-------------------------------:|----------------------------------:|-----------|--------------------------------------|
| red  | 0.0735 | **0.1223** | rose | 0.4265 → 0.3777 (suppression **fell**) |
| blue | 0.3088 | **0.4065** | rose | 0.1912 → 0.0935 (suppression **fell**) |

**Verdict:** YES — the CLEAN, full-length, healthy DeepSeek run **still programs utility sub-chance on both seats** (red 0.1223 ≪ 0.50; blue 0.4065 < 0.50). The qualitative finding **HELD**. The **magnitude attenuated**: keep-rates **rose toward chance on both seats** once the abort storm was removed and matches ran full-length, so the suppression is real but **weaker** than the confounded run implied. The confounded numbers overstated the effect (early-aborted, degraded rounds). The clean run is the trustworthy datapoint: utility under-programming persists, red strongly, blue mildly.

---

## 4-model cross-model context (utility keep-rate: red / blue)

| Model | red | blue | n | Notes |
|-------|----:|-----:|--:|-------|
| qwen35 (baseline) | 0.0552 | 0.1657 | — | `.onex_state/steel_onslaught/ugate_surfacing_fix_battery` |
| **deepseek-v4-flash CLEAN** | **0.1223** | **0.4065** | **22 (partial)** | this doc; supersedes confounded 0.0735 / 0.3088 |
| gemma | 0.1776 | 0.3224 | 19 | |
| glm-4.5 | 0.0942 | 0.5130 | 30 | red confound noted; blue ≈ chance |

**Robust cross-model pattern:** all four models program **red-seat utility below chance** (0.055–0.178, all ≪ 0.50). Blue-seat behavior varies by model (qwen 0.166 → gemma 0.322 → deepseek 0.407 → glm 0.513 ≈ chance). DeepSeek-CLEAN sits at the high end of blue keep-rate (2nd after glm) while remaining sub-chance; on red it is mid-pack. The universal finding — systematic utility under-programming, strongest on red — holds across all four models.

---

## Operational finding

DeepSeek-v4-flash is **impractically slow at `max_tokens=16384`**: ~32 min/match, ~14h to reach only 22/30 complete matches before the run was killed. The utility-suppression fix worked and the completions are clean, but this config is too slow to complete a 30-match battery in a reasonable window. For future cross-model B runs, either lower `max_tokens` for deepseek or budget accordingly. n=22 is cited honestly as a clean partial (killed for time, not error).

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/ugate_deepseek_clean_battery/events.sqlite3` (events table; `hand_dealt`, `plan_committed`, `llm_completion_resolved`) restricted to the 22 `match_id`s in `.onex_state/steel_onslaught/ugate_deepseek_clean_battery/battery_raw.jsonl`.
- qwen35 baseline: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`.
- No secrets, keys, or absolute paths included.
