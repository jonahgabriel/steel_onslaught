# Scenario-axis variation: qwen35 utility deprioritization on a symmetric arena

**Date:** 2026-07-23
**Model:** Qwen3.6-35B-A3B (qwen35), keyless endpoint `http://omninode-pc.tail75df5e.ts.net:8000/v1`
**Question:** Does qwen35's sub-chance utility deprioritization (established on an asymmetric arena) survive a swap to a symmetric arena, or is it scenario-dependent?
**Verdict:** SCENARIO-ROBUST (magnitude MIXED — both keep-rates drop ~35–42% but stay far sub-chance)

## Batteries

| Battery | State-root | n | seeds | arena |
|---|---|---|---|---|
| ASYM baseline | `.onex_state/steel_onslaught/ugate_surfacing_fix_battery` (SO-PROMPT-SURFACING) | 30 | 5001–5030 | asymmetric (foundry_60_asym_v1) |
| SYM (this test) | `.onex_state/steel_onslaught/ugate_qwen35_symmetric_battery` (SO-SCENARIO-SYM2) | 30 | 5001–5030 | `foundry_60` (symmetric) |

SYM run: 30/30 matches, `all_replay_valid=true`, `play_terminal_fraction=1.0`, `o_gate_pass=true`.

## Keep-rate (independently recomputed from raw sqlite ledgers)

Method: `dealt` = utility-partition card count summed over each seat's `hand_dealt` events; `programmed` = `plan_committed` register slots with `card_id` matching `card.utility.*`; keep-rate = programmed / dealt. Recomputation reproduces the reported figures exactly.

| Scenario | Seat | programmed | dealt | keep-rate |
|---|---|---|---|---|
| ASYM | player.red  | 20 | 362 | 0.0552 |
| ASYM | player.blue | 60 | 362 | 0.1657 |
| SYM  | player.red  | 23 | 722 | 0.0319 |
| SYM  | player.blue | 89 | 722 | 0.1233 |
| SYM combined | — | 112 | 1444 | 0.0776 |

All-card sanity (SYM): red 1805/3610 = 0.5000, blue 1805/3610 = 0.5000 (exactly at chance, 5 registers of 10 dealt) — confirms utility-specific deprioritization is not a dealing artifact.

## Findings

1. Sub-chance deprioritization HOLDS on the symmetric arena: red 0.0319 and blue 0.1233 are both far below the 0.5000 all-card baseline.
2. blue > red ordering PERSISTS: blue keeps utility ~3.9× red (SYM) vs ~3.0× red (ASYM).
3. Magnitude drops for both seats (red 0.0552→0.0319, blue 0.1657→0.1233), ~35–42% lower — same sign, changed degree.

## Corroborating ledger facts (SYM)

- Winner distribution: player.blue 30, player.red 0.
- failed_completions = 71 (red 61 / blue 10), all `invalid_response` / `invalid_action_parameters`; zero match aborts (max_attempts=1 absorbed all via per-round fallback).
- Terminal class: elimination 30/30 (symmetric `foundry_60` has `objectives={}`, no VP terminals).
- Utility deploys total 101 (smoke 73, chaff 22, flares 6; blue 81 / red 20).
- Rounds/match: mean 12.03 (range 6–18); duration ticks mean 57.2.

## Verdict and caveats

VERDICT: SCENARIO-ROBUST on the qualitative finding (sub-chance keep + red-under-blue ordering reproduce across arenas), MIXED on magnitude (both keep-rates ~35–42% lower in SYM).

Caveats (coarse contrast — single-axis attribution not possible):
- The two scenarios differ in geometry AND objectives simultaneously; this test does not isolate which axis (if either) drives the magnitude shift.
- SYM matches run longer (722 dealt/seat, ~12 rounds/match) than ASYM (362, ~6); a confound on absolute magnitude, not on the ratio.
- Both scenarios share blue-wins/red-loses lopsidedness and red-dominated completion failures (SYM red 61 vs blue 10), so the red-under-blue keep asymmetry tracks the losing seat + model, not the arena — which is why it survives the arena swap. A clean single-axis test (same geometry, toggle objectives only) is the recommended follow-up.

## Provenance

- SYM ledger: `.onex_state/steel_onslaught/ugate_qwen35_symmetric_battery/events.sqlite3` (30 matches; hand_dealt 722, plan_committed 722). Overlay `tactical_split_overdeal_utility_sym_v1_qwen.yaml` (PR #148), driver `--expected-arena` (PR #147). max_attempts=1, byte-identical retry to the asym utility overlay; no tracked-file edits during the run.
- ASYM ledger: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3`.
- Recompute independent of the reporting agent; figures matched to the last digit.

## Note for follow-up
PR #148's overlay header comment was copied verbatim from the asym overlay and still describes objectives/vp_threshold that do not apply to the symmetric arena — a cosmetic doc cleanup (does not affect parsing or the binding). Its ledger state paths also still name the asym lane; the battery used `--state-root` to isolate output, but a future edit should give the overlay its own paths.
