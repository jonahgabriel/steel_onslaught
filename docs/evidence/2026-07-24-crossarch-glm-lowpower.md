# Cross-Architecture Utility Deprioritization — GLM-4.5 (4th lineage, lower-power) arm

**Date:** 2026-07-24
**Experiment:** Steel Onslaught U-GATE cross-architecture battery, GLM arm (Zhipu/GLM, glm-4.5, z.ai coding endpoint, thinking disabled)
**State root (retained):** `.onex_state/steel_onslaught/ugate_glm_battery` (SO-B-GLM2 worktree) — `events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`
**Wiring/resilience:** PRs #151 (glm-4.5 overlay + `thinking:{type:disabled}` typed field + secret injection `secret://llm/glm`→`LLM_GLM_API_KEY`) and #152 (retry `max_attempts:4`, backoff 1→2→4s, `timeout_seconds:45`; relaxed the selected-provider single-attempt guard so the battery path retries transient z.ai timeouts). Key never committed/printed.

## Provenance / independent verification
All figures recomputed from `events.sqlite3` by an analyst who did not run the battery. Keep-rate = (utility card_ids in `plan_committed.registers`) / (utility card_ids in `hand_dealt` utility partition), by seat. Chance baseline = 0.5 (2 utility of 10 dealt, 5 registers), corroborated by all-card keep-rate = 0.5000 for both seats.

## Health (n=30, FULL run — not partial)
- 30 distinct matches; 30 each match_started/ended/scored; 30 leaderboard entries; all_replay_valid=true.
- Rounds/match: mean 5.13, median 5, min 0, max 15 (5 matches committed 0 plans).
- Failed completions: 111 — invalid_response 110 / timeout 1; invalid_action_parameters 109 / malformed_json 1; by seat red 90 / blue 21.
- Terminals: abort 19 (18 provider_semantic_failure, 1 aborted), elimination 11; play_terminal_fraction 0.3667; o_gate_pass=false.
- Winners: draw 19, blue 11, red 0.
- Retry fix: 1/111 failures was a timeout; no battery-level abort → fix effective for its target (z.ai latency stalls).
- CAVEAT: 63% abort rate; only 11/30 reached a play terminal. Dominant failure is model-quality (GLM-4.5 red/berserker seat emits invalid plans), NOT infra.

## Keep-rate (recomputed)
| seat | loadout | programmed | dealt | keep-rate | vs chance (0.5) |
|------|---------|-----------|-------|-----------|-----------------|
| red  | berserker_scout | 29 | 308 | 0.0942 | ~5.3× below |
| blue | sniper_ironclad | 158 | 308 | 0.5130 | AT chance |

All-card sanity: red 770/1540 = 0.5000, blue 770/1540 = 0.5000. Utility deploys: 183 total (chaff 66 / smoke 59 / flares 58); blue 155, red 28.

## Four-model comparison (red = aggressive/berserker, blue = defensive/sniper)
| Model | Lineage | red keep | blue keep | blue/red | blue sub-chance? | caveat |
|-------|---------|-----|------|----------|------------------|--------|
| qwen35   | Alibaba Qwen | 0.0552 | 0.1657 | 3.0× | yes | clean, n=30 |
| deepseek | DeepSeek | 0.0735 | 0.3088 | 4.2× | yes | confounded (abort storm) |
| gemma    | Google Gemma | 0.1776 | 0.3224 | 1.8× | yes | n=19 partial |
| glm-4.5  | Zhipu/GLM | 0.0942 | 0.5130 | 5.4× | **NO (at chance)** | n=30; red confounded (63% abort) |

## Findings
1. **GENERAL:** the aggressive/berserker (red) seat programs utility ≪ chance in all four lineages (red 0.055–0.178). Architecture-independent — four independent model families, same directional behavior.
2. **LINEAGE-SPECIFIC:** defensive-seat (blue) deprioritization holds for Qwen/DeepSeek/Gemma (blue 0.17–0.32, sub-chance) but BREAKS on GLM (blue 0.513, at chance). The *scope* of the effect (one seat vs both) is not general.
3. **CAPABILITY AXIS (non-monotonic, n=4, hypothesis only):** lower-power glm-4.5 shows the sharpest seat asymmetry (5.4×), not uniform suppression — inconsistent with a monotonic "lower-power → deprioritizes more" story; more consistent with the seat/role prompt dominating, executed more coarsely (all-or-nothing per seat) by the weaker model. Capability does not cleanly predict suppression *magnitude*; it appears to predict *sharpness of the seat split*.

## Verdict
**MIXED:** a general, architecture-independent core (aggressive-seat utility suppression, 4/4 lineages) wrapped in a lineage/capability-specific shell (whether the defensive seat also suppresses, and how sharp the seat split is).

## Confounds
- GLM red: 63% abort, 90/111 semantic failures; committed red plans are a biased survivor sample; low red utility may partly reflect fallback to simple movement/attack cards when a valid plan lands, not deliberate strategy. The general red-suppression claim survives (holds across clean + confounded arms); the capability-axis reading does not — directional only.
- deepseek confounded (abort storm); gemma n=19; glm reached only 11 play-terminal matches. qwen35 is the cleanest arm.
