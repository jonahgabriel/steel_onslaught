# Cross-Architecture Utility-Surfacing Evidence — Gemma (B-arm)

- Date: 2026-07-23
- Arm: OpenRouter FREE cross-architecture (`google/gemma-4-26b-a4b-it:free`, instruct/non-reasoning, Google lineage)
- Status: PARTIAL n=19/30 (free-tier daily request cap; resume seeds 5020–5030 after ~00:00 UTC reset)
- Ledger root: `.onex_state/steel_onslaught/ugate_gemma_battery/` (gitignored state; not committed)
- Verifier: independent recompute from raw ledgers, not author-reported summary

## Claim under test
Models will not surface tactically-available utility cards to their 0.50 chance floor unprompted. Prior evidence was confined to the Qwen/DeepSeek open-weight chain-of-thought lineage; Gemma (Google, non-reasoning instruct) is the independent architecture required to test generality.

## Chance floor
Each seat is dealt 10 cards/round (2 utility) and programs 5 registers. Random selection keeps 5/10 of dealt cards → expected utility keep-rate 0.50. Observed all-card keep = 0.5000 for every seat of every model confirms the floor and isolates the utility gap as a selection effect (not programming volume).

## Keep-rate results (all recomputed from each run's events.sqlite3)
| Model | Lineage | red util keep | blue util keep | all-card keep | n |
|---|---|---|---|---|---|
| qwen35 (surfacing-fix) | Qwen / open-weight CoT | 0.0552 (20/362) | 0.1657 (60/362) | 0.5000 | 30 |
| deepseek (prior, confounded) | DeepSeek / open-weight CoT | 0.0735 | 0.3088 | ~0.50 | prior |
| Gemma (this run) | Google / instruct (independent) | 0.1776 (38/214) | 0.3224 (69/214) | 0.5000 | 19 (partial) |

Recompute method: utility keep = count(plan_committed register card_id LIKE 'card.utility.%') / count(hand_dealt card_ids LIKE 'card.utility.%'), restricted to the valid match_ids in battery_raw.jsonl. Gemma red 38/214=0.1776, blue 69/214=0.3224; all-seat all-card 535/1070=0.5000. qwen35 recompute reproduced red 0.0552, blue 0.1657 exactly.

## Health (19 in-ledger matches)
- Completions: requested 214 / resolved 214 / failed 0 (clean).
- Transport discards: 22 whole-match (reason_code=provider_error / HTTP 429), never entered ledger; match_started 41 vs match_ended 19. 15 were intermittent OpenRouter "200-with-bad-body" (client classifies invalid_response as non-retryable → whole-match retry amplified request volume); 7 were HTTP 429 at the daily-cap window.
- Terminals: 19/19 elimination (last_mech_standing); all_replay_valid=true; 0 draws / 0 vp_threshold / 0 control changes.
- Winner: player.blue (sniper) 19/19; brawler 0 wins; max VP any match 3.
- Duration: min 12 / median 26 / mean 25.1 / max 36 ticks.
- Programming rounds/match: mean 5.63 (min 3, max 8) — sub-full-length because fast elimination ends matches early. Real signal, not a bug.
- O-GATE: play-terminal fraction 1.0 → PASS over partial set.
- Utility deploys (n=91): chaff 56 / smoke 22 / flares 13; blue 58 / red 33.

## Verdict: GENERAL-ACROSS-ARCHITECTURES
Gemma — an independent lineage — programs utility below the 0.50 chance floor on both seats (red 0.1776, blue 0.3224), reproducing the qwen35 and deepseek direction and the blue>red ordering. The effect is not an artifact of the open-weight-CoT tradition; it survives an architecture switch to a Google, non-reasoning instruct model. This supports the design decision to force utility surfacing via mechanism rather than rely on emergent model behavior. Notably Gemma has the highest keep-rates of the three, yet 0.18 / 0.32 is still decisively sub-chance — even the most utility-friendly model measured does not surface utility to chance.

## Limitations
- n=3 model families; Gemma is instruct-tier, not frontier.
- This Gemma run is n=19 partial; complete to n=30 after free-tier reset (~00:00 UTC) before treating as a full peer of the qwen35 n=30 baseline. Resume seeds 5020–5030 with completion-level retry (make invalid_response retryable inside the client's existing backoff) rather than whole-match retry, to avoid re-amplifying request volume.
- deepseek prior is confounded (carried, not re-run here); the clean deepseek rerun supersedes it.
- Single map/loadout/overlay set — generality proven on the ARCHITECTURE axis, not the SCENARIO axis.

## Provenance
- Model pin verified live: google/gemma-4-26b-a4b-it:free returns 200 at $0 (provider "Darkbloom").
- Key read at runtime from ~/.omnibase/.env via secret://llm/openrouter overlay ref; never printed, committed, or written to any file.
- No tracked files edited; artifacts in gitignored state root only. Wiring PR #145.
