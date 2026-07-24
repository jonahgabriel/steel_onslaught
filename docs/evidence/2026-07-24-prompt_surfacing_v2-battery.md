# ARM S — Factual Prompt Surfacing on Brawler Re-Cut v2 (2026-07-24)

**Verdict: FAILED (outcome) — but NOT vacuous, and NOT a clean negative control.** Decided-match red (brawler) win rate is **0/30 = 0.0000**, inside the `<0.10` FAILED band and identical to both the v1 anchor and the v2 arm-zero baseline. Adding neutral factual context (cover/obstacle cells + enemy weapon threat, both seats) did not move the brawler off a 0/30 record. Independent recomputation also surfaces two findings the runner's report did not check: (1) a large, statistically significant **drop** in utility-card keep-rate on both seats relative to both baselines, and (2) a direct behavioral read showing red's movement **never occupies a cover cell in either arm** (0.0% in ARM S, 0.0% in arm-zero) — the surfaced cover data reached the wire prompt but produced zero measurable routing change.

**Ledger:** `.onex_state/steel_onslaught/prompt_surfacing_v2_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-PROMPT2 worktree.
**Change under test:** PR #160, merged to `main` at `7fb337f1727e555c340026f8e5751fd60673c3d9` — `ModelSOPilotObservation` gains `cover_cells` (arena obstacle ground truth) and `enemy_weapon_threat` (declared enemy weapon id/range/damage); `programming.py`'s whole-round prompt serializer renders both as new keys (`own_observation.cover_cells`, top-level `enemy_weapon_threat`), always present as an empty list rather than absent. Applies to **both seats**, every match, via the existing v2 overlay — no new overlay needed, no steering/instruction text added (ARM S is surfacing-only; ARM G, which stacks seat-scoped steering on top, is unbuilt/untested — see §6).
**Model:** live Qwen3.6-35B-A3B, n=30, seeds 5001–5030.
**Baselines:**
- v1 anchor (qwen35 asym v1 combined overlay): 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue keep-rate 0.1657 (`docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
- v2 arm-zero (PR #157, same arena/loadout, no prompt arms): 0/30 red wins, median 33 ticks, red utility keep-rate 0.0526, blue keep-rate 0.1794 (`docs/evidence/2026-07-24-brawler-recut-v2-battery.md`, ledger `.onex_state/steel_onslaught/brawler_recut_v2_battery` in SO-RECUT worktree).

All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger and a fresh isolated match capture, not copied from the battery runner's report.

---

## 1. Win rate + terminal health

Recomputed directly from `battery_raw.jsonl` (30 rows, unique seeds 5001–5030) and cross-checked against `battery_summary.json` — exact match on every field.

| Metric | Value |
|---|---|
| n | 30 |
| Terminal-class mix | elimination 29, abort 1 (seed 5002: `provider_semantic_failure`, red malformed_json ×3, `is_draw=true`) |
| play_terminal_fraction | **0.9667** (gate ≥0.9 — PASS) |
| Decided matches (aborts excluded) | 29 |
| Decided-match red win rate | **0/29 = 0.0000** |
| All-match red win rate | 0/30 = 0.0000 |
| Winner distribution | player.blue 29, draw 1 |
| Duration ticks | min 18 / median 30.5 / mean 34.17 / max 62 |
| `all_replay_valid` | true |

Verdict band: **FAILED** (<0.10).

## 2. Objectives (secondary signal)

| Objective | Awards | By red | Matches scored | Control changes |
|---|---:|---:|---:|---:|
| objective.north_works | 2 | 2 | 2 | 0 |
| objective.west_yard | 52 | 52 | 10 | 0 |

Consistent with prior batteries: red accumulates objective-control awards in matches it survives long enough to hold ground, but this never converts to a VP-threshold win (0/30 VP terminals), and `matches_with_control_change=0`.

## 3. Utility keep-rate per seat — NEW independent recomputation, not in the runner's report

Method: `hand_dealt.card_ids` (dealt) vs `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by seat — identical method to the 2026-07-23/07-24 baseline docs. Recomputed via SQL against `events.sqlite3` (426 `hand_dealt` events split 213/213 by seat, 2 utility cards dealt per hand deterministically = 426 utility cards dealt per seat; 213 `plan_committed` events per seat).

| Seat | ARM S programmed / dealt | ARM S keep-rate | v1 anchor | v2 arm-zero | Δ vs v2 arm-zero |
|---|---:|---:|---:|---:|---:|
| red (brawler) | 8 / 426 | **0.0188** | 0.0552 | 0.0526 | **−0.0338 (−64% relative)** |
| blue (sniper) | 33 / 426 | **0.0775** | 0.1657 | 0.1794 | **−0.1019 (−57% relative)** |
| all-card sanity (both seats) | 2130 / 4260 | 0.5000 | 0.5000 (mechanical) | 0.5000 | 0 |

**This is a real, unreported finding.** Both seats' utility keep-rate dropped substantially versus both prior baselines — this is not noise: under the v2 arm-zero baseline rate as a null (red p=0.0526, n=426 dealt), the expected count is ~22.4; observed is 8 (z≈−3.1, p<0.002). For blue (null p=0.1794, n=426, expected ~76.4, observed 33), z≈−5.3. Both are large, consistent-direction drops.

**Interpretation, held to the causal-attribution standard the arm-zero doc set:** because win-rate is unchanged (0/30→0/30) there is no outcome shift to attribute the keep-rate drop to, so this is not evidence the surfacing *caused* the (flat) loss — but it does mean the "geometric/loadout-only, draft-layer-neutral" property the arm-zero doc established no longer holds once the surfacing fields are added. The added prompt content (cover_cells array of ~100 cells + enemy_weapon_threat block) measurably changed both seats' card-programming distribution away from utility cards, even though it left win/loss and match-length outcomes flat. Plausible mechanism: substantially longer/denser prompts (own_observation.cover_cells adds ~100 coordinate objects) may be diluting attention toward movement/attack registers at utility's expense — this is a hypothesis, not established causally here; a controlled ablation (surfacing without the full cover_cells array, or with a shorter derived summary) would be needed to isolate which of the two new fields drives the drop, and whether prompt length alone (independent of content) is the mechanism.

## 4. Match length

| Metric | ARM S | v2 arm-zero |
|---|---:|---:|
| min ticks | 18 | 14 |
| median ticks | 30.5 | 33.0 |
| mean ticks | 34.17 | 33.4 |
| max ticks | 62 | 53 |

Flat within noise for n=30 — no material change in approach/kill timing.

## 5. Behavioral read: did surfacing change red's routing or cover usage? — NEW independent analysis

The program question is whether the brawler *uses* the newly surfaced cover/threat data, not just whether it's present in the prompt. Recomputed by joining `movement_resolved` events (subject `player_id`) against the exact `cover_cells` set captured from a live wire prompt (§6), and against the y=28–32 open exposed band named in the program brief, for both this battery and the v2 arm-zero raw ledger (still present on disk in the SO-RECUT worktree, same arena `foundry_60_asym_v2` so the cover-cell set is identical).

| Metric | ARM S (surfacing) | v2 arm-zero (no surfacing) |
|---|---:|---:|
| red `movement_resolved` events | 449 | 405 |
| red positions landing in a cover cell | **0 (0.0%)** | **0 (0.0%)** |
| red positions in y=28–32 open band | 188 (41.9%) | 164 (40.5%) |
| matches with ≥1 red `weapon_fired` | 27/30 | 29/30 |
| red first-shot tick: min/mean/max | 12 / 19.3 / 34 | 8 / 18.6 / 33 |

**Red's movement never once lands on a cover cell in either arm — 0.0% cover occupancy, byte-identical between surfacing and no-surfacing.** Time spent in the exposed y=28–32 band is flat (41.9% vs 40.5%, within noise for n≈30). First-shot timing is flat (mean 19.3 vs 18.6 ticks). **This is a clean, direct answer to the program question for ARM S: the brawler pilot does not use the surfaced cover/threat data for routing — the facts reach the wire prompt (§6) but produce zero measurable change in movement behavior.** This is consistent with (not proof of, but consistent with) the recut-v2 doc's hypothesis that the bottleneck is planner-level spatial reasoning, not missing facts — surfacing the facts alone did not unlock cover-seeking behavior. It also sets up the actual test of that hypothesis: ARM G's seat-scoped steering explicitly instructs routing through cover, which this data has not yet tested.

## 6. Prompt-artifact verification (independent re-derivation, both seats)

The ledger's `llm_completion_requested` payload only persists `system_prompt_length`/`user_prompt_length` (confirmed: `SELECT payload_json FROM events WHERE event_type='llm_completion_requested' LIMIT 1` returns only those two length fields plus `provider_id`/`persona_id` — no prompt text). This was independently reproduced, not just re-quoted from the runner's report: a fresh throwaway n=1 match was run (seed 5001, same overlay/loadouts/command, `--state-root` pointed at a scratch directory entirely outside the repo under `/private/tmp/...`, deleted after; `git status --short` in the SO-PROMPT2 worktree confirmed clean before and after) with a monkeypatch on `LedgerLlmCompletionObserver.requested` capturing `request.user_prompt` for **both seats** before transmission (the runner's report only captured red).

Confirmed present in the actual rendered wire prompt at tick 1, both seats:

- **red**: `"cover_cells":[{"x":8,"y":20},{"x":8,"y":21},...]` (105 cells) and `"enemy_weapon_threat":[{"damage":28,...,"range":30,"weapon_id":"weapon.heavy.harpoon_gun"},{"damage":45,...,"range":50,"weapon_id":"weapon.siege.artillery_mortar"}]` — blue's declared loadout, correctly rendered from red's point of view.
- **blue**: same `cover_cells` set (105 cells — arena geometry is not seat-relative) and `"enemy_weapon_threat":[{"damage":8,...,"range":12,"weapon_id":"weapon.light.machine_gun"},{"damage":18,...,"range":20,"weapon_id":"weapon.medium.heat_lance"}]` — red's declared loadout, from blue's point of view.

This confirms the "both seats" claim in the PR description with direct evidence for both seats (not just an inference from source review), and confirms the code path (`pilot_tick.py::_build_observation` → `programming.py`'s serializer) is live and wired into the real provider call, not dead code. This was a fresh isolated match (seed 5001 on this rerun produced a different `match_id`/outcome than the battery's own seed-5001 row, as expected from LLM stochasticity) — it proves the code path is wired, not a byte-for-byte replay of a specific battery seed.

## 7. Discrepancy check against the runner's report

The runner's per-seed table, aggregate summary, objectives breakdown, and the abort-seed detail (5002) were independently recomputed from the raw ledger and matched exactly on every field — no discrepancies found. The runner's report did not compute utility keep-rate (§3) or a behavioral routing read (§5) at all; both are new in this verification pass and materially change the interpretation from "no effect" to "no outcome effect, but a real drafting-behavior side effect and a clean null on cover-seeking behavior."

## 8. Merge / additivity verification

- PR #160 merged to `main` at `7fb337f1727e555c340026f8e5751fd60673c3d9` (`gh pr view 160`: state MERGED, mergedAt 2026-07-24T15:44:06Z). 4/4 CI checks green on the merge commit (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`).
- The five touched source files (`contracts/pilot.py`, `llm/programming.py`, `match/composition.py`, `pilots/schemas.py`, `reducers/pilot_tick.py`) are byte-identical between the SO-PROMPT2 battery-run commit and the merged `main` commit (`git diff` empty on all five).
- `git diff 233b3eb 7fb337f -- <v1/v2 baseline arena/loadout/overlay files>` is empty — none of the pre-existing v1/v2 baseline contracts were modified by this landing.

---

## Verdict

**FAILED on outcome** (0/30 decided-match red win rate, `<0.10` band, `play_terminal_fraction=0.9667` clears the trust gate) — ARM S (neutral factual surfacing, both seats, no seat-scoped instructions) did not move the brawler off its 0/30 record, matching both the v1 anchor and the v2 arm-zero baseline exactly. **Not vacuous**: the surfaced facts are independently confirmed present in the live wire prompt for both seats (§6). **Not a clean negative control either**: utility-card keep-rate dropped sharply on both seats relative to both baselines (§3, red −64% relative, blue −57% relative, both individually significant) — a real, previously unmeasured side effect of the added prompt content that the flat win-rate does not explain away. The cleanest finding is the behavioral one (§5): red's movement occupies zero cover cells in both the surfaced and unsurfaced arm — identical 0.0%, so surfacing cover data produced no measurable routing change. Facts alone did not unlock cover-seeking or a win-rate change; whatever combination of a real steering instruction and/or the keep-rate side effect ARM G introduces is still an open, untested question — L-GATE-2's prior falsification of steering for utility-card usage is a different behavior class (card selection, not movement routing) and does not extend to a claim about routing steering either way.

**Next lever:** ARM G (surfacing + brawler-seat-only steering) is config-complete (`pilot.llm.qwen35_berserker_guided` spec + `tactical_split_overdeal_utility_asym_v2_guided_qwen.yaml` overlay landed in the same PR #160) but has **not been battery-tested** — no ARM G ledger exists yet. Before running it, note this verification adds a confound to watch: ARM G stacks steering on top of the same surfacing fields that already suppressed utility keep-rate on both seats in ARM S, so any keep-rate shift in ARM G needs to be checked against the ARM S keep-rate (not just the pre-surfacing baselines) to isolate the steering-specific effect from the surfacing-specific effect already measured here.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/prompt_surfacing_v2_battery/{battery_raw.jsonl,battery_summary.json,events.sqlite3}` (SO-PROMPT2 worktree).
- Behavioral comparison ledger: `.onex_state/steel_onslaught/brawler_recut_v2_battery/events.sqlite3` (SO-RECUT worktree, `movement_resolved` events).
- v1 anchor: `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- v2 arm-zero baseline: `docs/evidence/2026-07-24-brawler-recut-v2-battery.md`.
- Merge commit: `7fb337f1727e555c340026f8e5751fd60673c3d9` (PR #160, `main`).
- Prompt-artifact capture: fresh isolated n=1 match, scratch state root outside the repo, monkeypatch on `LedgerLlmCompletionObserver.requested`; SO-PROMPT2 worktree confirmed clean (`git status --short`) before and after.
- No secrets, keys, or absolute paths (other than repo-relative citations above) included.
