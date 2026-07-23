# Cross-Model B-Question: Utility Deprioritization — DeepSeek-V4-Flash vs Qwen35

**Date:** 2026-07-23
**Question (design §4.1, within-model contrast):** Does DeepSeek-V4-Flash also program utility below its own 0.50 chance floor (deprioritization REPRODUCES cross-family → GENERAL), or at/above chance (→ QWEN-SPECIFIC)?
**Verdict:** GENERAL — both families deprioritize utility sub-chance. The DeepSeek datapoint is CONFOUNDED by a completion-health abort storm (directional, not level-comparable).

## Method
Independent recompute from raw immutable event ledgers (not reported summaries):
- DeepSeek: `.onex_state/steel_onslaught/ugate_surfacing_deepseek_battery/events.sqlite3` (SO-B-DEEPSEEK worktree; overlay `tactical_split_overdeal_utility_asym_v1_deepseek.yaml`, model `deepseek-v4-flash` on .200 @ `:8101/v1`, `max_tokens 4096`, n=30 seeds 5001–5030).
- Qwen35 baseline: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree; same overlay family, n=30).

Utility keep-rate = utility cards placed in registers (`plan_committed.registers`) ÷ utility cards dealt (`hand_dealt.card_ids`), matched on `card.utility.%`, per seat, via `json_each`. Chance floor = all-card keep-rate = 0.5000 exactly (register mechanic keeps 5 of 10 dealt).

## Recomputed keep-rate (paired)
| Seat | Model | util prog | util dealt | keep-rate | chance floor | vs floor |
|------|-------|-----------|------------|-----------|--------------|----------|
| red  | Qwen35   | 20 | 362 | 0.0552 | 0.5000 | 89% below |
| red  | DeepSeek |  5 |  68 | 0.0735 | 0.5000 | 85% below |
| blue | Qwen35   | 60 | 362 | 0.1657 | 0.5000 | 67% below |
| blue | DeepSeek | 21 |  68 | 0.3088 | 0.5000 | 38% below |

All-card keep-rate = 0.5000 for every seat, both families (sanity holds exactly). Both recomputations reproduce the reported baselines to the digit.

## Within-model structure (reproduces on both axes)
1. Every seat, both families, programs utility far below its own 0.50 floor. None reach chance.
2. blue > red asymmetry holds in both families (Qwen 3.0x, DeepSeek 4.2x); red deprioritizes hardest.

## Completion health (the load-bearing caveat)
| | Qwen35 | DeepSeek |
|-|--------|----------|
| requested/resolved/failed | 380/362/18 (4.7%) | 100/70/30 (30%) |
| failure kinds | 18 stop | 24 length (4096-cap) + 6 timeout |
| clean play-terminal | 29/30 last_mech_standing | 0/30 (all aborted) |
| O-GATE | pass | o_gate_pass=false (play_terminal_fraction 0.0) |
| dealt hands (rounds) | 362 (~12/match) | 68 (~2.3/match) |

DeepSeek pre-abort rounds were clean: 68/68 `plan_source=llm`, 340/340 `register_resolved=resolved` (zero fallback fills). The failures are purely terminal length/timeout overflow — the flagged risk (CoT narrated into `content`, 4096 cap hit, register JSON never closed).

## Verdict
GENERAL. DeepSeek red 0.0735 and blue 0.3088 are both below the 0.50 chance floor, mirroring Qwen35 red 0.0552 / blue 0.1657, with matching sign, sub-chance magnitude, and red-hardest asymmetry. Utility deprioritization is a cross-family behavior on this overlay, not a Qwen artifact. The signal survives DeepSeek's truncated sample; its magnitude is NOT level-comparable to Qwen (see caveat).

## Limitations
- n=2 models, single overlay, n=30 each — first cross-family datapoint, not a law.
- Qwen and DeepSeek are same-tradition open-weight CoT models — not maximally independent.
- The DeepSeek datapoint is confounded by a 30% completion-abort storm (68-hand small sample, ~2.3 rounds/match). The signal survives truncation but its magnitude is not level-comparable to Qwen.

## Next step
1. Fix DeepSeek completion health (`max_tokens` >> 4096 / stricter JSON mode / separate reasoning channel), re-run n=30 for a full-length uncontaminated keep-rate.
2. Add a lineage-independent 3rd family (frontier or non-reasoning) to move from "two related open-weight families" to a cross-architecture claim.
3. Vary the overlay to rule out scenario-specificity.

Design implication (holds cross-family): utility surfacing needs a structural nudge (reward shaping / prompt scaffold / explicit utility-in-register incentive) — models will not surface utility to chance unprompted.

## Provenance
- DeepSeek ledger: SO-B-DEEPSEEK/.../ugate_surfacing_deepseek_battery/events.sqlite3 (30 matches, 30 aborted).
- Qwen35 ledger: SO-PROMPT-SURFACING/.../ugate_surfacing_fix_battery/events.sqlite3 (30 matches, 29 elimination).
- Wiring PR #142; config: json_object mode, `max_tokens 4096` (too low — cause of the abort storm), endpoint `stickybeatz-studio.tail75df5e.ts.net:8101`.
