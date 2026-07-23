# Utility Surfacing-Fix Re-measure — Evidence Addendum

**Date:** 2026-07-23
**Model:** Qwen3.6-35B-A3B (live, keyless) @ omninode-pc.tail75df5e.ts.net:8000/v1
**Overlay:** tactical_split_overdeal_utility_asym_v1_qwen.yaml (asym: red=brawler, blue=sniper)
**Design:** 30 matches, seeds 5001–5030, `--seed-base 5000 --n 30`, paired against the SO-UGATE-ASYM baseline (identical seeds/method).
**Fix under test:** PR #139 — removed the resolution-priority leak from the programming prompt + added tactical effect descriptions to the utility cards.
**State roots (retained):**
- fix: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery` (SO-PROMPT-SURFACING worktree)
- baseline: `.onex_state/steel_onslaught/ugate_asym_utility_battery` (SO-UGATE-ASYM worktree)

## Question

The SO-UGATE-ASYM baseline measured sub-chance utility keep-rate (red 0.0172, blue 0.0567 vs a 0.50 register floor). One candidate explanation was a prompt-surfacing bias: the old prompt leaked an internal resolution-priority number (utility lowest) under a "keep the strongest card" instruction and never described what the utility cards do. This re-measure applies the surfacing fix and re-runs the identical paired battery to separate mechanism (bias removed) from measured effect (does deprioritization survive?).

## Result (independently recomputed from the append-only event ledgers)

Utility keep-rate = (utility cards programmed into registers, from `plan_committed`) ÷ (utility cards dealt to hands, from `hand_dealt`), per seat.

| Seat | Baseline | Surfacing fix | Δ (multiple) | vs 0.50 chance floor |
|---|---|---|---|---|
| red (brawler) | 7/406 = 0.0172 | 20/362 = 0.0552 | +0.0380 (3.2×) | still ~9× below |
| blue (sniper) | 23/406 = 0.0567 | 60/362 = 0.1657 | +0.1090 (2.9×) | still ~3× below |

Overall all-card keep-rate held at exactly 0.5000 both runs (5 registers ÷ 10-card deal; mechanical) — the utility gain came out of the register mix, not from committing more cards.

Supporting deltas:
- Utility deploys: 26 → 72 (smoke 46 / chaff 20 / flares 6; red 18, blue 54).
- Completion failures: 10 → 18, all `invalid_response` / `invalid_action_parameters` (regression; one cascaded to the single match abort, `provider_semantic_failure`).
- Fewer utility dealt in the fix run (362 vs 406/seat) because matches ended faster (181 vs 203 rounds); keep-rate is a ratio, so this is neutral.

## O-GATE terminal scorecard (paired)

| Metric | Baseline | Surfacing fix |
|---|---|---|
| VP-threshold terminations | 0/30 | 0/30 |
| Max cumulative VP (any seat/match) | 7 | 1 |
| Brawler (red) objectives scored | 16 VP | 2 VP |
| Winner distribution | blue 30 / red 0 | blue 29 / draw 1 (abort) / red 0 |
| Brawler win_rate | 0.0 | 0.0 |
| Terminal classes | elim 30 | elim 29 / abort 1 |

The fix did not make the brawler contest VP or win a single match; it changed utility programming, not strategic balance.

## Verdict

**DEPRIORITIZATION SURVIVES THE SURFACING FIX.** Keep-rate rose ~2.9–3.2× for both seats — confirming a real surfacing bias was present and removed (mechanism) — but both seats still program utility 3–9× below the 0.50 chance floor (measured effect). With utility now plainly surfaced, the model still declines to program it near neutral rates. The residual sub-chance deprioritization is genuine, not a prompt artifact.

Per the pre-registered rule of thumb, a null here is the stronger result: it warrants the cross-model B experiment. If keep-rate had jumped to ≥0.50 we would have attributed the entire effect to the surfacing bug; it did not.

## Threats to validity

- Engagement-effect (sniper hit-rate WITH active smoke) is n=1 (1/1) — statistically empty, carries no signal, not cited.
- Completion-failure rise (10 → 18, all `invalid_action_parameters`) is a real regression in the richer prompt and a watch item; it also removed one match from the decided set (abort).
- Single model, single overlay, n=30 paired — cross-model B required before generalizing.

## Reproduction

All figures above were independently recomputed from `events.sqlite3` in both state roots via `json_each`/`json_extract` aggregation over `hand_dealt`, `plan_committed`, `objective_scored`, `utility_deployed`, and `llm_completion_failed` events; seed pairing verified identical (5001–5030) from `battery_raw.jsonl`.

## Next step

Cross-model B: identical surfaced-prompt overlay, paired seeds 5001–5030, ≥2 additional model families, to establish whether sub-chance utility keep-rate is Qwen3.6-specific or a general LLM-tactical-planner property.
