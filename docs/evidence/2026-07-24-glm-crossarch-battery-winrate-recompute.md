# GLM (4th lineage) Cross-Architecture Battery — Win-Rate/Wilson-CI Recompute + Ledger Disposition

**Date:** 2026-07-24
**Scope:** Two things, reported together because the investigation for one produced the answer to the other.
1. GLM smoke + battery health check (dispatched task), on `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_glm.yaml`.
2. `SO-B-GLM` vs `SO-B-GLM2` ledger disposition (pending item from `docs/handoffs/2026-07-24-brawler-competitiveness-session.md` §9 / line 133).

---

## 0. Headline

**A complete, trust-gate-relevant GLM battery already exists and is already merged** — `.onex_state/steel_onslaught/ugate_glm_battery` in the `SO-B-GLM2` worktree, n=30 (seeds 5001–5030), backing the merged evidence doc `docs/evidence/2026-07-24-crossarch-glm-lowpower.md` (PR #154) and the keep-rate finding in the session handoff. That doc reports terminal-class mix and utility keep-rate but does **not** report the win-rate/Wilson-CI framing this program uses for every other arm (P1–P4, tournament arms, etc.) or match length in ticks. This document:
- Independently re-verifies every figure in the merged doc directly from `events.sqlite3` (all matched, see §2).
- Adds the missing win-rate + Wilson CI + match-length figures in the program's standard format (§1).
- Runs a fresh n=1 smoke (this session, clean — §3) to confirm the provider path is still live today.
- Resolves the `SO-B-GLM`/`SO-B-GLM2` disposition question with corrected facts — **the 2026-07-24 handoff's characterization of which worktree holds what is backwards** (§4).
- Documents a fresh, independent n=30 replication battery launched this session under the identical overlay/loadout pair, reported as in-progress/partial (§5) — it is not needed to answer either question above, since a complete, verified battery already exists, but is left running as a same-wiring replication check with no metered-cost downside (z.ai CODING plan is flat-rate).

**Trust gate:** the existing battery's `play_terminal_fraction = 0.3667` (11/30) **fails** both the task gate (≥0.90) and the codebase default (≥0.95). This is a severe trust-gate failure, more severe than any other arm in this program's ledger (worst prior was spatial R2 at 0.80). The proximate cause is confirmed model-quality, not infra or CoT-truncation (§2.3): 111 total `llm_completion_failed` events, 110 `invalid_response`/`stop` (109 `invalid_action_parameters`, 1 `malformed_json`), 1 `timeout`; **zero** `finish_reason=length` — the CoT-budget-truncation failure class this task brief asked me to watch for did **not** occur, in the existing battery or in this session's smoke. 90/111 (81%) of failures are on the red/berserker seat.

---

## 1. Win rate + Wilson CI (recomputed from `ugate_glm_battery`, not previously published in this form)

Method matches `docs/evidence/2026-07-24-pair_p4_dmg8-battery.md`: decided-match win rate = wins ÷ `elimination`/`vp_threshold`-class terminals (aborts excluded from the denominator); all-30 basis also reported. Wilson 95% CI, z=1.95996.

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 |
| Terminal-class mix | elimination 11/30, abort 19/30 (18 `provider_semantic_failure`, 1 `aborted`) |
| **play_terminal_fraction** | **0.3667** (task gate ≥0.90 — **FAIL**; codebase default ≥0.95 — **FAIL**) |
| Winner distribution (decided, n=11) | player.blue 11, player.red 0 |
| Winner distribution (all-30, draws separate) | draw 19, player.blue 11, player.red 0 |
| **Decided-match red win rate** | **0/11 = 0.0000** |
| **All-match red win rate** (aborts included, denominator 30) | **0/30 = 0.0000** |
| 95% Wilson CI, decided-11 basis | **[0.0000, 0.2588]** |
| 95% Wilson CI, all-30 basis | [0.0000, 0.1135] |
| Replay validity | 1/1 both players, all 30 matches (`all_replay_valid=true`) |

**Verdict: FAILED** (point estimate 0.0000, well under the 0.10 FAILED/DIRECTIONAL boundary; even the Wilson upper bound on the decided-11 basis, 0.259, stays under the 0.35 COMPETITIVE line). Consistent directionally with every other arm's baseline (qwen35, deepseek, gemma all show red 0/N at this overlay's baseline lever settings) — GLM adds a fourth confirmation that the brawler seat does not win against this sniper loadout on the base overlay, independent of pilot lineage.

**Caveat on this verdict's reliability:** with only 11/30 matches reaching a decidable terminal, this is the smallest decided-sample arm in the program (P3's 28/30 and P4's 29/30 are typical; spatial R2's 24/30 was previously the low-water mark). The 0/11 result should be read as "no evidence of red competitiveness in the matches that resolved," not as a fully-powered null — the abort mechanism (§2.3) truncates the sample before most matches can even reach a decidable state.

### Match length

| Metric | All 30 matches | Decided (elimination) only, n=11 |
|---|---:|---:|
| min ticks | 1 (abort) | 15 |
| median ticks | 26.0 | 40 |
| mean ticks | 25.57 | 41.18 |
| max ticks | 73 | 73 |

Median match length among matches that actually resolve (40 ticks) runs longer than every pair-sweep arm on the qwen35 lineage (24–33 ticks) — consistent with a slower/more deliberate GLM-4.5 pilot when it does produce valid plans, though this is a directional read on n=11, not a controlled comparison (different model, different overlay history).

---

## 2. Independent re-verification of the merged doc's figures

Every number below was recomputed directly from `.onex_state/steel_onslaught/ugate_glm_battery/{events.sqlite3,battery_raw.jsonl}` in the `SO-B-GLM2` worktree by an analyst (this session) who did not run that battery — the same "recompute, don't trust the summary/stdout" convention this program applies everywhere.

### 2.1 Health / terminal mix — MATCHES merged doc exactly
- 30 distinct `match_id`s in `battery_raw.jsonl`, seeds 5001–5030, zero duplicates/gaps.
- Terminal classes: abort 19 (18 `provider_semantic_failure`, 1 `aborted`), elimination 11. `play_terminal_fraction = 0.3667`. `all_replay_valid = true` (30/30, both seats).
- Winners: draw 19 (the 19 aborts, `is_draw=true`), player.blue 11, player.red 0.

### 2.2 Utility keep-rate — MATCHES merged doc exactly
Method: utility `card_id`s (`card.utility.*`) programmed into `plan_committed.registers[]` ÷ utility `card_id`s dealt in `hand_dealt.card_ids`, per seat, recomputed directly from `payload_json` on both event types (not from the summary).

| Seat | Loadout | Dealt (utility) | Programmed (utility) | Keep-rate | All-card sanity (programmed/dealt) |
|---|---|---:|---:|---:|---:|
| red | berserker_scout | 308 | 29 | **0.0942** | 770/1540 = 0.5000 |
| blue | sniper_ironclad | 308 | 158 | **0.5130** | 770/1540 = 0.5000 |

Both figures match the merged doc (`docs/evidence/2026-07-24-crossarch-glm-lowpower.md`) to 4 decimal places — independent confirmation, not a restatement. Blue keep-rate (0.513) sits essentially **at chance** (0.5), the one lineage in the 4-model comparison where the defensive-seat suppression effect does not hold (qwen35 0.166, deepseek 0.309, gemma 0.322, all sub-chance; glm 0.513, at chance).

### 2.3 Completion-failure breakdown — MATCHES merged doc exactly; explicitly rules out CoT-budget truncation
Queried directly from `llm_completion_failed` event `payload_json`/`subject_json`:

| Field | Breakdown |
|---|---|
| `reason_code` | `invalid_response` 110, `timeout` 1 |
| `semantic_failure_code` | `invalid_action_parameters` 109, `malformed_json` 1, null 1 (the timeout) |
| `finish_reason` | `stop` 110, null 1 (the timeout has no finish_reason) — **`length` occurs 0 times** |
| By seat (via `subject.mech_id`) | red 90, blue 21 (total 111) |

**This directly answers the task brief's named risk.** GLM is a hybrid-reasoning model and the brief flagged "CoT-budget truncation" (`finish_reason=length`, no repair attempt) as the specific failure mode to watch for. It did not occur here: every semantic failure returned `finish_reason=stop` with a syntactically-complete-but-invalid JSON payload (`invalid_action_parameters` / `malformed_json`), not a truncated one. The overlay's `thinking: {type: disabled}` field (PR #151) is doing its job — this is a **model-quality** confound (GLM-4.5's red/berserker seat producing schema-invalid action parameters at a high rate), not an infra, budget, or truncation problem. The retry fix (PR #152) is also confirmed effective for its target: only 1/111 failures was a `timeout`, and it did not cascade into a battery-level abort.

---

## 3. Fresh smoke (this session, 2026-07-24 ~13:53)

Run before discovering the existing battery, per the task brief's "prove the provider path is alive before spending a full battery" instruction. State root `.onex_state/steel_onslaught/glm_smoke` (`SO-GLM-SMOKE` worktree), same overlay/loadout pair, seed 5001, `--n 1`.

| Metric | Value |
|---|---|
| `all_replay_valid` | true (1/1 both seats) |
| `play_terminal_fraction` | 1.0 |
| Terminal class | elimination (`last_mech_standing`), winner player.blue |
| Duration | 24 ticks |
| `failed_completions` | 2 |

Both failures: `reason_code=invalid_response`, `semantic_failure_code=invalid_action_parameters`, `finish_reason=stop`, `completion_tokens` 94 and 87 (overlay `max_tokens=4096`) — nowhere near the budget ceiling, confirming (again, independently, on a fresh call today) that this is not truncation. **Smoke verdict: CLEAN — provider path alive, auth valid, completions parse, JSON-mode compliant when valid, match terminates correctly.** This one match happening to reach a clean elimination terminal is consistent with — not in tension with — the 0.3667 play-terminal fraction measured over n=30: at an 63%-ish per-match abort rate, drawing a clean terminal on a single n=1 sample is unsurprising (roughly a 1-in-3 chance).

---

## 4. `SO-B-GLM` vs `SO-B-GLM2` ledger disposition

### 4.1 The handoff's claim is backwards

`docs/handoffs/2026-07-24-brawler-competitiveness-session.md:133` states: *"`SO-B-GLM2` holds a unique `ugate_glm_battery_smoke2` ledger not present in `SO-B-GLM`."* This is **incorrect on both the ledger name and the direction of the asymmetry**. Live filesystem state (this session):

| Worktree | State dirs present | Match count (`match_ended`) | Timestamp range (UTC) |
|---|---|---:|---|
| `SO-B-GLM` | `ugate_glm_battery_smoke` | 1 | 09:24:48–09:26:48 |
| `SO-B-GLM` | `ugate_glm_battery_smoke2` | 1 | 09:30:04–09:33:46 |
| `SO-B-GLM` | `tactical_split_v1_qwen` | 0 (no `events.sqlite3`; empty scaffold dirs only) | — |
| `SO-B-GLM2` | `ugate_glm_battery_smoke` | 1 | 10:04:17–10:09:26 |
| `SO-B-GLM2` | **`ugate_glm_battery`** | **30** | **10:11:25–11:39:43** |
| `SO-B-GLM2` | `tactical_split_v1_qwen` | 0 (same empty scaffold) | — |

The actual asymmetry is the reverse of what the handoff says: **`SO-B-GLM`** holds the unique `..._smoke2` lane (not `SO-B-GLM2`), and **`SO-B-GLM2`** holds a unique lane too — but it is `ugate_glm_battery`, the **complete 30-match battery that backs the merged PR #154 evidence doc**, not a second smoke test. The handoff undersold what is in `SO-B-GLM2` by an order of magnitude (one throwaway n=1 smoke vs. the entire program's GLM dataset).

### 4.2 What each ledger is, and why it exists

Read together, the four smoke-scale ledgers plus the full battery tell a coherent development story (all four smokes are n=1, `events.sqlite3` timestamps are strictly increasing across worktrees in the order shown above, i.e. `SO-B-GLM` ran first, `SO-B-GLM2` second):

1. `SO-B-GLM/ugate_glm_battery_smoke` (09:24) and `SO-B-GLM/ugate_glm_battery_smoke2` (09:30) — the **"reproduced 2/2 smoke runs"** cited narratively (not by path) in PR #152's body, which describes the z.ai intermittent-timeout-abort bug that motivated the retry fix. These two runs are the reproduction evidence for that bug report. Their content is already durably preserved as prose in the merged PR #152 body (a permanent GitHub record); no merged doc cites their `.onex_state` path directly.
2. `SO-B-GLM2/ugate_glm_battery_smoke` (10:04) — a third smoke, run after the retry fix (PR #152) landed, immediately before the full battery in the same worktree. Standard pre-battery smoke; superseded by the full battery it precedes.
3. `SO-B-GLM2/ugate_glm_battery` (10:11–11:39) — **the full n=30 battery**, the sole data source for the merged `docs/evidence/2026-07-24-crossarch-glm-lowpower.md` (PR #154) and for the GLM row in the session handoff's 4-model comparison table. This is confirmed by exact match on every recomputed figure in §2 above.
4. `tactical_split_v1_qwen` in both worktrees — empty scaffold directories (no `events.sqlite3`, just `evaluations/experiments/lineage/evaluation_storage` subfolders) with zero bytes of event data. Artifact of loading a qwen overlay for a wiring check that never reached `match_started`. Not data-bearing in either worktree.

### 4.3 Recommendation

- **`SO-B-GLM2/ugate_glm_battery` — KEEP, do not prune under any circumstance.** It is the sole surviving source for a merged, cited evidence doc (PR #154) and the GLM row of the 4-model handoff table. `.onex_state` is gitignored — there is no remote copy; deleting this worktree destroys the only backing data for already-published claims.
- **The four n=1 smoke lanes (`SO-B-GLM/ugate_glm_battery_smoke`, `SO-B-GLM/ugate_glm_battery_smoke2`, `SO-B-GLM2/ugate_glm_battery_smoke`, plus this session's own `SO-GLM-SMOKE/glm_smoke`) — safe to prune.** None is path-cited by a merged doc; the one with narrative significance (the pre-fix "2/2 smoke runs" in `SO-B-GLM`) already has its forensic point preserved as text in PR #152's merged body, which survives independently of the local worktree.
- **`tactical_split_v1_qwen` scaffold dirs (both worktrees) — safe to prune**, zero data either way.
- **Net effect if pruned:** `SO-B-GLM` becomes fully prunable (worktree GC candidate — it holds no unique, non-superseded, non-narratively-preserved data once its two smoke lanes are gone). `SO-B-GLM2` must be **retained** for its `ugate_glm_battery` lane specifically — do not prune the whole worktree; if a GC pass targets it, carve out that one directory first (e.g., copy `.onex_state/steel_onslaught/ugate_glm_battery` to a permanent evidence-archive location, or simply leave `SO-B-GLM2` as a long-lived baseline worktree, which is how the other cross-model baselines — `SO-B-DEEPSEEK*`, `SO-B-GEMMA`, `SO-B-QWEN*` equivalents — are already being kept per the handoff's own GC section).

This is a recommendation only; disposition (prune / archive / keep-as-is) remains an operator decision per the task brief.

---

## 5. Independent replication battery (in progress at time of writing)

A second, independent n=30 battery was launched this session in the `SO-GLM-SMOKE` worktree, under the byte-identical overlay/loadout pair, per-seed isolated invocation (one process per seed, `--n 1`, shared append-mode state root `.onex_state/steel_onslaught/glm_battery`, `--fresh` only on seed 5001, up to 2 attempts per seed with a 420s timeout — the P4 pattern). This was **not required** to answer either question above (a complete, independently-verified battery already exists — §2), but was left running as a same-wiring replication check once discovered, since the z.ai CODING plan is flat-rate (no metered cost for the extra 29 matches).

As of this document, it is **partial** (seed 5001 complete: elimination, player.blue win, 24 ticks, 4 failed completions, same failure signature as §2.3; seed 5002 onward in progress). Per this program's standing rule, **battery_summary.json from a per-seed invocation reflects only the single most recent seed's row and must not be read as cumulative** — do not treat any single seed's summary output as the battery result. If this replication completes, the correct next step is to recompute win-rate/Wilson-CI/terminal-mix/keep-rate figures the same way as §1–2 above, directly from the accumulated `battery_raw.jsonl` (30 rows) and `events.sqlite3`, and compare against §1–2 as a same-day replication of the existing result — not to treat it as the primary source, since §1–2 is already a complete, doubly-verified n=30 battery.
