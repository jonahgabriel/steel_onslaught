# GLM (4th lineage) Cross-Architecture Battery — Win-Rate/Wilson-CI Recompute + Ledger Disposition

**Date:** 2026-07-24
**Scope:** Two things, reported together because the investigation for one produced the answer to the other.
1. GLM smoke + battery health check (dispatched task), on `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_glm.yaml`.
2. `SO-B-GLM` vs `SO-B-GLM2` ledger disposition (pending item from `docs/handoffs/2026-07-24-brawler-competitiveness-session.md` §9 / line 133).

---

## 0. Headline

**A complete, trust-gate-relevant GLM battery already exists and is already merged** — `.onex_state/steel_onslaught/ugate_glm_battery` in the `SO-B-GLM2` worktree, n=30 (seeds 5001–5030), backing the merged evidence doc `docs/evidence/2026-07-24-crossarch-glm-lowpower.md` (PR #154) and the keep-rate finding in the session handoff. **That merged doc is honest and self-caveating** — it already discloses `play_terminal_fraction 0.3667`, `o_gate_pass=false`, the 63% abort caveat, the "red confounded" label in its four-model table, and the explicit "committed red plans are a biased survivor sample… the capability-axis reading does not survive — directional only" scoping. Nothing here corrects a concealment; this document's genuine additions are (a) the win-rate/Wilson-CI/match-length framing that doc doesn't use, (b) the explicit CoT-truncation exclusion, and (c) the ledger-inventory correction. This document:
- Independently re-verifies every figure in the merged doc directly from `events.sqlite3` (all matched, see §2).
- Adds the missing win-rate + Wilson CI + match-length figures in the program's standard format (§1).
- Runs a fresh n=1 smoke (this session, clean — §3) to confirm the provider path is still live today.
- Resolves the `SO-B-GLM`/`SO-B-GLM2` disposition question with corrected facts — **the 2026-07-24 handoff's characterization of which worktree holds what is backwards** (§4). **Operator-settled disposition: keep everything, prune nothing.** Every `.onex_state` lane discussed here (both worktrees' smoke lanes, `SO-B-GLM2`'s full battery, both `tactical_split_v1_qwen` scaffolds) stays exactly where it is; §4.3 documents the analysis but no pruning was recommended for action, and none was taken.
- Reports a completed, independent n=30 replication battery run under the identical overlay/loadout pair (§5). **The replication materially diverges from the original on trust-gate health — abort rate 63.3% → 23.3%, a difference confirmed statistically significant (two-proportion z-test, z=3.13, two-sided p≈0.00177, §5.2) — but tightly reproduces both the win-rate finding (red 0/N in both runs) and the keep-rate finding (both seats within ~1pp of the original, including blue's at-chance defensive-seat result).** §5.4 draws the methodological implication: a single battery's trust-gate figure against a cloud-served model is not a durable verdict — it needs repetition. See §5 for the full side-by-side.

**Trust gate (original battery):** `play_terminal_fraction = 0.3667` (11/30) **fails** both the task gate (≥0.90) and the codebase default (≥0.95). This is a severe trust-gate failure, more severe than any other arm in this program's ledger (worst prior was spatial R2 at 0.80). The proximate cause is confirmed model-quality, not infra or CoT-truncation (§2.3): 111 total `llm_completion_failed` events, 110 `invalid_response`/`stop` (109 `invalid_action_parameters`, 1 `malformed_json`), 1 `timeout`; **zero** `finish_reason=length` — the CoT-budget-truncation failure class this task brief asked me to watch for did **not** occur, in the existing battery or in this session's smoke. 90/111 (81%) of failures are on the red/berserker seat. **The replication battery (§5) also shows zero `finish_reason=length` across its 98 completion failures — the truncation exclusion holds on both independent runs.**

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

### 4.3 Analysis (recommendation superseded by operator decision — see below)

Prior-to-decision analysis, left here for the record:
- `SO-B-GLM2/ugate_glm_battery` is the sole surviving source for a merged, cited evidence doc (PR #154) and the GLM row of the 4-model handoff table — pruning it would destroy the only backing data for already-published claims (`.onex_state` is gitignored, no remote copy exists).
- The four n=1 smoke lanes (`SO-B-GLM/ugate_glm_battery_smoke`, `SO-B-GLM/ugate_glm_battery_smoke2`, `SO-B-GLM2/ugate_glm_battery_smoke`, plus this session's own `SO-GLM-SMOKE/glm_smoke`) are not path-cited by any merged doc; the one with narrative significance (the pre-fix "2/2 smoke runs" in `SO-B-GLM`) already has its forensic point preserved as text in PR #152's merged body.
- `tactical_split_v1_qwen` scaffold dirs (both worktrees) hold zero data either way.

**Operator decision (this session): KEEP EVERYTHING, PRUNE NOTHING.** Every `.onex_state` lane named above — both worktrees' smoke lanes, `SO-B-GLM2`'s full battery, both `tactical_split_v1_qwen` scaffolds — stays exactly where it is. No deletion, archival move, or worktree GC was applied to any of them in this session or as a recommendation going forward. The analysis above stands as record of what was investigated, not as an action taken.

---

## 5. Independent replication battery — COMPLETE (n=30, same-day, same wiring)

A second, independent n=30 battery was run in the `SO-GLM-SMOKE` worktree under the byte-identical overlay/loadout pair (`tactical_split_overdeal_utility_asym_v1_glm.yaml`, `contracts_data/loadouts/glm/{berserker_scout,sniper_ironclad}.yaml`), per-seed isolated invocation (one process per seed, `--n 1`, shared append-mode state root `.onex_state/steel_onslaught/glm_battery`, `--fresh` only on seed 5001, up to 2 attempts per seed with a 420s timeout — the P4 pattern). This answers the question the merged doc and §1–2 above cannot: **is the original battery's abort profile a stable property of GLM-4.5's red seat, or did it catch something transient?** Short answer: **the win-rate and keep-rate findings replicate tightly; the raw abort-rate does not — it diverges by close to 3×.** Full breakdown below.

### 5.0 Provenance — exactly which seeds came from which invocation (read before trusting any summary)

Per this program's standing rule, `battery_summary.json` from a per-seed invocation reflects only the single most recent seed's row, never the cumulative battery — every figure below is recomputed from the accumulated `battery_raw.jsonl` (30 rows) and `events.sqlite3`, not from any summary file.

This run was **not** a single clean pass — it is segmented across three invocations, and the segmentation matters because one segment left an orphaned partial match in the ledger:

1. **Invocation 1** (14:01:49–~14:03, seed 5001 only, `--fresh`): wiped a stale mid-match ledger left by an earlier, separately-stopped agent run (0 completed matches in that stale state — nothing lost), then completed seed 5001 cleanly (elimination, player.blue win, 24 ticks, 4 failed completions). The driver script then **crashed** on seed 5002's flag-construction step — a macOS bash-3.2 `set -u` + empty-array-expansion incompatibility (`extra_flags[@]: unbound variable`) — before invoking the Python process at all for seed 5002. No match was started or lost; the crash was purely in the shell wrapper.
2. **Invocation 2** (relaunched ~14:07:42, resumed at seed 5002, no `--fresh`): ran seeds 5002–5030 to completion (29 matches) using a fixed driver (plain string flag instead of a bash array). Completed at 14:59:16.
3. **Within invocation 2, seed 5005 itself required an internal retry**: attempt 1 timed out at the 420s ceiling (`rc=124`, confirmed in the driver log) after getting deep into the match (many rounds, multiple `weapon_fired`/`hit_resolved` events, one final unresolved `llm_completion_requested` at the moment of the kill) — the timeout killed the process mid-request, leaving an **orphaned `match_started` with no `match_ended`** in `events.sqlite3` (`match.01KYAZGBJFTVESJRTTWG48QAVX`). Attempt 2 for seed 5005 created a fresh match_id and completed normally (this is the seed-5005 row that appears in `battery_raw.jsonl`).

**Net result:** `battery_raw.jsonl` has exactly 30 rows, seeds 5001–5030, zero duplicates/gaps — confirmed directly (`len(set(seeds))==30`, `min=5001`, `max=5030`). `events.sqlite3` has 31 `match_started` but only 30 `match_ended` — the one extra is the orphaned seed-5005 attempt-1 partial. **All sqlite-derived aggregates below (completion failures, keep-rate) are filtered to the 30 valid `match_id`s from `battery_raw.jsonl`, excluding the orphan** — the same "filter to valid match_ids, exclude orphans" convention the P4 doc names explicitly. Unfiltered, the orphan would add 1 extra `llm_completion_failed` (blue seat, `invalid_action_parameters`) and several extra `hand_dealt`/`plan_committed` rows; the effect on every ratio is under 1pp either way, but the filtered numbers are the ones reported here.

### 5.1 Side-by-side: original (SO-B-GLM2) vs replication (SO-GLM-SMOKE)

| Metric | Original (`ugate_glm_battery`, 10:11–11:39) | Replication (`glm_battery`, 14:01–14:59) | Divergence |
|---|---:|---:|---|
| `match_started` / `match_ended` | 30 / 30 | 31 / 30 (1 orphan, excluded — §5.0) | replication had 1 internal seed-level retry; original had none |
| Terminal-class mix | elimination 11, abort 19 | elimination 23, abort 7 | **large** — abort share 63.3% → 23.3% |
| `play_terminal_fraction` | 0.3667 (FAIL both gates) | 0.7667 (fails task gate ≥0.90 and codebase default ≥0.95, but far closer) | **large improvement, still failing** |
| Decided red win rate | 0/11 = 0.0000, Wilson [0, 0.259] | 0/23 = 0.0000, Wilson [0, 0.143] | **replicates exactly** (0 wins either run) |
| All-basis red win rate | 0/30 = 0.0000, Wilson [0, 0.114] | 0/30 = 0.0000, Wilson [0, 0.114] | **replicates exactly** |
| Match length (decided), median/mean | 40 / 41.18 ticks | 30 / 31.87 ticks | shorter in replication, consistent with fewer aborted-mid-plan matches truncating the sample differently |
| Total `llm_completion_failed` | 111 | 98 (filtered) | lower, tracks the lower abort rate |
| `semantic_failure_code` breakdown | `invalid_action_parameters` 109, `malformed_json` 1, null 1 (timeout) | `invalid_action_parameters` 98, 0 `malformed_json` | same dominant failure mode, no `malformed_json` this run |
| `reason_code` breakdown | `invalid_response` 110, `timeout` 1 | `invalid_response` 98, 0 `timeout` | same |
| `finish_reason` | `stop` 110, null 1 (timeout) | `stop` 98 | **zero `length` in both runs — CoT-truncation excluded on both** |
| Failures by seat | red 90 (81%), blue 21 (19%) | red 67 (68%), blue 31 (32%) | same direction (red-dominant), magnitude softer |
| Red keep-rate (utility) | 29/308 = **0.0942** | 38/364 = **0.1044** | **replicates closely** (+1.0pp) |
| Blue keep-rate (utility) | 158/308 = **0.5130** | 191/364 = **0.5247** | **replicates closely** (+1.2pp) — **blue stays at-chance in both runs** |
| All-card sanity (both seats) | 0.5000 | 0.5000 | mechanical, confirms register structure held in both |

### 5.2 What replicates and what doesn't

**Replicates tightly (2 of 2 confirmations):**
- **Red never wins.** 0/11 and 0/23 on the decided basis, 0/30 on the all-basis, in both independent n=30 runs — the strongest possible same-day confirmation available of "red cannot beat this sniper loadout with this overlay," independent of the abort-rate swing.
- **Blue's utility keep-rate stays at chance (~0.51–0.52 vs 0.50).** This is the specific figure the operator flagged as carrying the "defensive-seat suppression is lineage-specific" claim — it reproduces within 1.2pp. The claim that GLM is the one lineage where blue does *not* suppress utility stands on firmer ground after this replication, not weaker.
- **Red's utility keep-rate stays low (~0.094–0.104), an order of magnitude below chance.** Also reproduces closely.
- **Zero CoT-budget truncation in either run.** 209 total completion failures across both batteries (111 + 98), zero `finish_reason=length`. The task brief's named risk class did not manifest in either battery.
- **Same dominant failure mode and seat skew direction:** `invalid_response`/`invalid_action_parameters` on `finish_reason=stop` (syntactically complete, semantically invalid JSON — not truncated), red seat disproportionately affected in both runs (81% original, 68% replication).

**Does NOT replicate closely — diverges materially, and the divergence is statistically significant:**
- **The abort rate.** 19/30 aborts (original, 63.3%) vs 7/30 aborts (replication, 23.3%) — roughly a 2.7× difference in the fraction of matches that abort before reaching a decidable terminal. `play_terminal_fraction` moved from 0.3667 to 0.7667. **This is not within-noise for two n=30 samples: a two-proportion z-test on 19/30 vs 7/30 gives pooled p̂ = 26/60 = 0.4333, SE = 0.12795, z = (0.6333 − 0.2333)/0.12795 = 3.126, two-sided p ≈ 0.00177.** At p<0.002 this rejects the null that the two batteries were drawn from the same underlying abort rate — the difference is not sampling noise across two runs, something about the conditions actually varied. The replication still fails both trust gates (0.7667 < 0.90 and < 0.95), so the qualitative verdict ("this arm has a real trust-gate problem") does not flip — but the original 63% figure is **not** a stable, reproducible constant of this arm; it is one draw from a rate that moves by a statistically significant margin across a few hours on the same wiring.

### 5.3 Interpretation

Because the divergence is significant (not just "wide enough that two runs could plausibly disagree by chance"), this is a genuine update to how PR #154's confound caveat should be read, in one specific direction: the **abort-rate magnitude** in that doc (63%) should not be treated as a fixed characteristic of `glm-4.5` on this contract — it is one sample from a rate that provably moved between the two runs, not a stable constant. **Leading hypothesis, explicitly labeled as a hypothesis — not proven by this data:** the failure mode is identical in kind both times (`invalid_action_parameters`, `finish_reason=stop`, red-seat skewed), and only the *rate* moved, which points toward a provider-side cause — z.ai CODING-pool load, request routing, or `glm-4.5` model-version drift across the ~3–5 hour gap between the two batteries (10:11–11:39 vs 14:01–14:59) — rather than anything in the pinned overlay/loadout/contract configuration, which is byte-identical across both runs. This has not been instrumented (no request-level latency/routing telemetry was captured) and cannot be proven from this data; it is the most plausible explanation given what varied (rate) and what didn't (failure kind, contract config), not a demonstrated mechanism.

What does **not** need updating: the core findings PR #154 and the session handoff draw from this arm — red never wins, red suppresses utility far below chance, blue does *not* suppress utility (unlike the other three lineages) — all survive this replication intact, and in blue's case, more strongly confirmed than before. The confound caveat itself (already present in the merged doc: "committed red plans are a biased survivor sample… directional only") remains the correct level of hedging for the capability-axis reading; if anything, this replication is a reason to hedge the *abort-rate number* harder while leaving the *win-rate and keep-rate* claims as they stand — those are firmer, not weaker, after two independent confirmations.

### 5.4 Methodological implication: on this provider, a single battery's trust-gate result is not a verdict

The significance test above changes the shape of the lesson from "one noisy arm" to a general caution about how this program should treat cloud-provider arms. **A trust-gate figure measured once on a cloud-served model can be time-dependent, not a fixed property of the arm.** This battery failed the O-GATE at `play_terminal_fraction=0.3667` and — on the identical overlay, loadout, and model pin, a few hours later — passed a materially higher (though still-failing) `0.7667`, a shift too large to be sampling noise (§5.2, p≈0.00177). Any single battery run against a cloud endpoint in this program should therefore be read as **one sample of a possibly time-varying rate**, not a settled verdict on the arm — a arm that fails its trust gate once has not been shown to durably fail it, and one that passes once has not been shown to durably pass it either, until repeated.

This contrasts with the local qwen35 endpoint: the P4 battery (`docs/evidence/2026-07-24-pair_p4_dmg8-battery.md` §0b) ran 30/30 seeds succeeding on attempt 1, zero retries, zero transport failures — a pattern typical of every qwen35 arm in this program. That stability is itself evidence for keeping trust-gate-sensitive measurement on the local tier where possible: a local endpoint's failure/success rate is a property of the arm's own contract and prompt design, not of a shared remote pool's momentary load. A cloud-provider arm's trust-gate number carries an extra, unmeasured source of variance that a single battery cannot separate from the arm's true rate.

**Scope of this claim, stated honestly:** this is one significant same-day comparison on one provider (z.ai/GLM), not a general law about all cloud providers or a fully-powered study of GLM's own variance (a third or fourth battery would be needed to characterize the rate's actual distribution, e.g. whether it clusters near 0.63, near 0.77, or swings across the whole range). Treat it as a caution — repeat cloud-provider trust-gate measurements before trusting a single number — not as an established rule that cloud arms are unreliable in general.
