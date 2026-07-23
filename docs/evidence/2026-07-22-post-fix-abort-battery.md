# Post-fix live-Qwen abort battery — 2026-07-22

End-to-end proof that the #119 (sniper strict-output contract) + #120 (dealt-hand
copy clamp) + #121 (seat-generic dealt-hand discipline) fix chain eliminated the
live abort classes, measured on merged `main` after #121. This is the outstanding
residual (3) recorded in #120: no fresh live battery had been run post-merge.

## Method

- Code under test: `main` @ `f1fd18e` (`fix(pilots): seat-generic dealt-hand
  discipline across all personas`, #121 — includes #117 over-deal, #119, #120).
- Harness: headless, in-process
  `steel_onslaught.match.composition.assemble_match_live(max_ticks=None)` — the
  identical composition path used by `so play-live` and by the 2026-07-22
  round-4/4b batteries. No new harness; keyless providers
  (`secret_ref: null`), `NoSecretResolver` + `HttpxJsonTransport`, overlay
  `retry.max_attempts=1`.
- Config: overlay `contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml`
  (the merged-main over-deal split-deck config whose live failures #119/#120
  fixed), red `contracts_data/loadouts/llm_qwen35_berserker.yaml`, blue
  `contracts_data/loadouts/qwen35/sniper_ironclad.yaml`.
- Endpoint: Qwen3.6-35B-A3B, keyless (confirmed HTTP 200 on `/v1/models`
  immediately before launch).
- Battery: 30 sudden-death matches, seeds 3001–3030, run sequentially
  (~33 s/match, ~16.5 min wall total).
- Metrics: read in-process from the canonical event ledger
  (`stack.ledger.read_all(match_id)`), then independently re-verified with raw
  SQL against the durable lane ledger
  (`.onex_state/steel_onslaught/tactical_split_overdeal_v1_qwen/events.sqlite3`).
  Raw per-match records: `2026-07-22-post-fix-abort-battery-raw.jsonl` (same
  directory).

## Results (n = 30 matches, 840 LLM completions)

| Metric | RED (berserker) | BLUE (sniper) | Total |
|---|---|---|---|
| `llm_completion_requested` | 420 | 420 | 840 |
| `llm_completion_resolved` | 420 | 420 | 840 |
| `llm_completion_failed` — any class | **0** | **0** | **0** |
| — `invalid_action_parameters` | 0 | 0 | 0 |
| — `malformed_json` | 0 | 0 | 0 |
| — `length` (truncation) | 0 | 0 | 0 |
| — `provider_error` / transport | 0 | 0 | 0 |

Terminals: **30/30 `last_mech_standing`** — 100 % real gameplay terminals.
Zero `provider_semantic_failure`, zero `aborted`, zero `transport_error`, zero
stalls (tick range 21–103, median 66).

Plan provenance: 840/840 `plan_committed` with `plan_source=llm`, zero
`deterministic_fallback`. 840 requested = 840 resolved = 840 committed plans:
**every whole-round plan was first-shot accepted — the bounded repair loop was
never even needed.**

## Baseline comparison (pre-fix)

Baseline: the 2026-07-22 round-4/4b battery ledger on the
`tactical_split_range_band_evasion_qwen` lane (SO-C11-COOLDOWN worktree
`.onex_state`, PR #116 branch content). Verified by direct SQL readback for this
doc: 148 RED vs 40 BLUE `invalid_action_parameters` failed-completion events,
2 BLUE `malformed_json`, 4 `length`, 4 `provider_error`, over 1024 RED / 934
BLUE requested completions; terminals 36 `last_mech_standing`, 15
`provider_semantic_failure`, 4 `aborted`, 1 `draw_mutual_destruction` (56
ended).

**Honesty caveat:** the baseline ran different balance settings (unmerged #116
range-band-evasion overlay + defense-carbine content) and pools rounds that
partially include the #119 sniper fix. Match outcomes are therefore NOT
comparable; abort **rates per completion** are the comparison, and the dominant
baseline abort class (RED `invalid_action_parameters` — doctrine overriding the
dealt-hand multiset) is balance-independent in mechanism.

| Abort class (per 100 completions, per seat) | Baseline | Post-fix |
|---|---|---|
| RED `invalid_action_parameters` | 14.5 (148/1024) | **0.0** (0/420) |
| BLUE `invalid_action_parameters` | 4.3 (40/934) | **0.0** (0/420) |
| BLUE `malformed_json` | 0.2 (2/934) | **0.0** (0/420) |
| `length` + `provider_error` (both seats) | 0.4 (8/1958) | **0.0** (0/840) |
| Non-gameplay terminal fraction | 33.9 % (19/56) | **0.0 %** (0/30) |

With zero failures in 840 completions, the rule-of-three 95 % upper bound on
the post-fix per-completion abort rate is ≈ 0.36 % — versus the 14.5 %
baseline rate for the single worst class.

## Residuals (honest)

1. **Balance, not robustness: BLUE won 30/30.** On merged-main over-deal
   settings the sniper seat is completely dominant (baseline content that
   contested this — range-band evasion + carbine, PR #116 — remains unmerged).
   Not an abort class; flagged for the balance lane.
2. **`transport_error` untested under fault.** The endpoint stayed healthy for
   all 30 matches; this battery proves the semantic-abort classes are gone, not
   endpoint-outage behavior (`retry.max_attempts=1` unchanged).
3. **Distributional bound, not impossibility.** Temperature > 0; 0/840 bounds
   the residual abort rate, it does not prove zero forever. The contract-level
   matrix tests landed in #121 are the durable guard.
