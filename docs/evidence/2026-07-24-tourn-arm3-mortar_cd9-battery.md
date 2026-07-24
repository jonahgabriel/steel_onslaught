# Tournament Arm 3 (mortar_cd9) Battery — Sniper Mortar Cooldown 5→9 (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/29 = 0.0000** (aborted seed 5028 excluded) — below the 0.10 FAILED threshold, and numerically identical to the qwen35 asym v1 anchor (0/30). Nearly doubling the sniper mortar's cooldown (5→9 ticks) did not move the outcome off the floor.

**Ledger:** `.onex_state/steel_onslaught/tourn_arm3_mortar_cd9` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`) in the SO-TOURN worktree.
**Change under test:** PR #159 (merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97`) — `contracts_data/weapons/artillery_mortar_cd9.yaml` (additive weapon variant of `artillery_mortar.yaml`, `cooldown_ticks: 5 → 9`, every other field — range, damage, pressure_cost, heat_generated, accuracy_curve, target_class_effectiveness, damage_type, compatibility — byte-identical) bound via `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_cd9.yaml` (additive loadout variant of `sniper_ironclad.yaml`, single module swap `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_cd9`, every other module/field identical) and selected by `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen_mortar_cd9.yaml` (additive overlay, functionally identical to the v1 combined overlay except isolated `.onex_state` paths — arena and red/brawler loadout stay the driver defaults, unmodified). All baseline files (`artillery_mortar.yaml`, `sniper_ironclad.yaml`, `llm_qwen35_berserker.yaml`, `foundry_60_asym_v1.yaml`, the v1 combined overlay) verified byte-identical pre/post-merge below.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baseline anchor:** qwen35 asym v1 combined overlay — 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue utility keep-rate 0.1657 (`.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
- All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger and `battery_raw.jsonl`, not copied from the implementer's or battery runner's report.

---

## Method

- **Decided-match win rate per seat** = wins ÷ `match_ended` count, aborts/draws excluded from the denominator (1 abort this run — seed 5028, see Completion health below).
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt. `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed) parsed from `payload_json`, filtered to `card.utility.%`, grouped by `seat`. Identical method to the 2026-07-23 baseline doc and the arm 1/13 evidence docs.
- **Terminal-class mix** from `battery_raw.jsonl.terminal_class` / `battery_summary.json.terminal_classes`, cross-checked against `match_started`/`match_ended` event counts in `events.sqlite3`.
- **Per-seed cross-check**: every seed's `terminal_class`, `winner_player_id`, `duration_ticks`, `failed_completions` recomputed from `battery_raw.jsonl` and compared row-for-row against the runner's raw tally — exact match, zero discrepancy.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` / `match_ended` events | 30 / 30 (1:1, zero orphans) |
| play_terminal_fraction | **0.9667** (29/30 elimination; gate: ≥0.9 — PASS, battery is trustworthy) |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5028) |
| Winner distribution (all 30) | player.blue 29, draw 1 |
| **Decided-match red win rate** (29, abort excluded) | **0/29 = 0.0000** |
| Decided-match blue win rate | 29/29 = 1.0000 |
| Replay validity | 1/1 both players, all 30 matches; `all_replay_valid=true`, `o_gate_pass=true` |
| Aborted matches | 1 (seed 5028 — `end_reason=aborted`, `is_draw=true`, `victory_kind=null`; caused by an `llm_completion_failed` with `finish_reason=length` at `max_tokens=2048` under `failure_policy: raise`, not by the mortar cooldown lever) |

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 all present exactly once) and cross-checked against `events.sqlite3` (`match_started`=30, `match_ended`=30, `SELECT COUNT(DISTINCT match_id)`=30). Matches the runner's raw tally exactly, per-seed, with zero discrepancy, including the `winner_player_id="player.blue"` raw-field oddity on the abort row (not a scored win — `is_draw=true`).

## 2. Match length

| Metric | Arm 3 (mortar_cd9) | v1 anchor |
|---|---:|---:|
| min ticks | 6 (the abort, seed 5028) | 17 |
| median ticks | **29.0** | 31 |
| mean ticks | 29.9 | — |
| max ticks | 55 | — |

Median fell slightly (31 → 29, **−2 ticks, −6.5%**), and mean (29.9) sits close to median — a tight, unremarkable distribution once the 6-tick abort is set aside (elimination-only range is 13–55, in line with the anchor's spread). Nearly doubling the sniper's mortar cooldown (5→9 ticks) did **not** meaningfully lengthen matches — the brawler's approach window widened on paper, but match duration stayed essentially flat against baseline. This is a modest, not dramatic, shift and does not by itself explain or contradict the win-rate result.

## 3. Utility keep-rate (causal-attribution check)

| Seat | Arm 3 programmed / dealt | Arm 3 keep-rate | v1 anchor keep-rate | Δ (absolute / relative) |
|---|---:|---:|---:|---:|
| red (brawler) | 11 / 376 | **0.0293** | 0.0552 | −0.0259 / −46.9% |
| blue (sniper) | 57 / 376 | **0.1516** | 0.1657 | −0.0141 / −8.5% |
| all-card (sanity, both seats) | 940 / 1880 | 0.5000 | 0.5000 (mechanical) | 0 |

All-card keep-rate is exactly 0.5000 on both seats (940/1880 each), confirming the 5-of-10 register structure held and validating 0.50 as the null, same as every prior battery on this overlay shape.

Both seats moved in the **same direction** (down) relative to the anchor, which is the "clean" pattern (same-direction drift, not a divergence) — but the magnitude is not uniform: red dropped by nearly half in relative terms (0.0552 → 0.0293, still deep sub-chance, off an 11/376 count) while blue stayed within a plausible noise band (0.1657 → 0.1516, −8.5%). A weapon cooldown stat has no direct mechanism to move card-programming behavior at all, so any nonzero shift here is attributable to run-to-run sampling variance rather than the lever itself. Since **decided-match win rate also did not move** (0/29 vs. baseline 0/30 — both pinned at the floor), there is no win-rate delta for this keep-rate movement to explain either way: the causal read is clean in the narrow sense that nothing moved that needed explaining, but the red-seat keep-rate delta is large enough (−46.9% relative) that it should not be waved off as strictly flat, either — it is noise on a low-count metric (11 successes), not evidence of a behavioral shift induced by the lever.

## 4. Objectives (secondary signal, not the gating metric)

| Objective | Awards | Red | Blue | Matches scored | Control changes |
|---|---:|---:|---:|---:|---:|
| objective.north_works | 1 | 1 | 0 | 1 | 0 |
| objective.west_yard | 1 | 1 | 0 | 1 | 0 |
| objective.east_gate | 4 | 0 | 4 | 2 | 0 |

Red picks up a single objective-control award each at north_works and west_yard (1 match each, out of 30) — thin signal, and neither converts to a VP-threshold win (0/30 VP terminals; 29/30 elimination, 1/30 abort). `matches_with_control_change=0` across the whole battery.

## 5. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 396 |
| `llm_completion_resolved` | 376 |
| `llm_completion_failed` | 20 |
| `finish_reason` distribution (resolved) | `stop`: 376 / 376 (zero `length` truncations among resolved plans) |
| `plan_source` distribution | `llm`: 376 / 376 (zero fallback/heuristic plans) |
| completion tokens (min / mean / max) | 88 / 97.9 / 112 |
| `failed_completions` sum (battery_raw, per seed) | 20 (matches `llm_completion_failed` exactly) |
| Seeds with ≥1 failed_completions | 12 / 30 |
| Failure reason (all 20) | `reason_code=invalid_response`, `semantic_failure_code=invalid_action_parameters` — all `finish_reason=stop` (retried, not truncated) |
| Matches reaching an unrecovered abort | 1 (seed 5028 only — see §1; that abort's precipitating failure was a distinct `finish_reason=length` truncation, not one of the 20 `invalid_action_parameters` retries) |

396 requested − 376 resolved = 20, matching `llm_completion_failed`=20 exactly and matching the runner's raw-tally sum of per-seed `failed_completions`. 19 of 30 seeds' worth of retries resolved cleanly (bounded retry, `finish_reason=stop`, `plan_source=llm` on all 376 final plans); only seed 5028 escalated to an abort, and its trigger was a separate token-cap truncation (`finish_reason=length` at `max_tokens=2048`) under `failure_policy: raise` — an LLM completion-length issue unrelated to the mortar cooldown lever under test.

## 6. Merge / additivity verification

- PR #159 merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (`gh pr view 159`: state MERGED, mergedAt 2026-07-24T15:19:31Z).
- 4/4 CI checks green on the merged PR (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: success`).
- `git diff 9eac392 01b0b43 -- contracts_data/weapons/artillery_mortar.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml contracts_data/arenas/foundry_60_asym_v1.yaml` returns **empty** — all five baseline files are byte-identical across the merge. Only new additive files (`artillery_mortar_cd9.yaml`, `sniper_ironclad_mortar_cd9.yaml`, `tactical_split_overdeal_utility_asym_v1_qwen_mortar_cd9.yaml`, plus the sibling arm 1/4/11/13 files landed in the same PR) were added.
- `git log --oneline -- contracts_data/weapons/artillery_mortar.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml` shows no commits touching any baseline file since before PR #159 — they remain byte-frozen.
- Direct diff of `artillery_mortar_cd9.yaml` vs `artillery_mortar.yaml` confirms the only field change is `cooldown_ticks: 5 → 9` (plus `id`/`display_name` and header comments for the new weapon id); every combat-relevant field (`range`, `damage`, `pressure_cost`, `heat_generated`, `accuracy_curve`, `target_class_effectiveness`, `damage_type`, `compatibility`) is identical.
- Direct diff of `sniper_ironclad_mortar_cd9.yaml` vs `sniper_ironclad.yaml` confirms the only module change is the weapon swap; chassis, boiler, pilot, harpoon_gun, sensors, gizmos, and declared budgets are unchanged (the loadout file's own header notes weapon modules carry no `mass` field and `cooldown_ticks` does not feed any budget axis, so the swap changes zero budget arithmetic — confirmed by identical `budgets:` block values).
- Direct diff of the arm 3 overlay vs the v1 combined overlay confirms the only functional changes are the isolated `.onex_state/steel_onslaught/tourn_arm3_mortar_cd9/*` paths; `arena_id`, card-catalog, deck-policy, LLM-provider, and transport fields are all unchanged (unlike arm 13, this arm does not rebind `arena_id` — the lever is bound entirely via `--blue-loadout` at launch, outside the overlay file).

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/29, abort excluded), inside the `<0.10` FAILED band and numerically identical to the v1 anchor's 0/30. `play_terminal_fraction=0.9667` clears the ≥0.9 trust gate, so this is a trustworthy null result, not a measurement artifact. Match length stayed flat (median 31→29, −6.5%) rather than collapsing or growing. Utility keep-rate moved in the same direction on both seats (red −46.9% relative, blue −8.5% relative) — a weapon-cooldown lever has no mechanism to move card-programming behavior, so this is read as sampling noise on a low-count metric (red's move rides on only 11 successes), not a behavioral shift. Since win rate did not move at all, there is nothing for the keep-rate delta to causally explain either way. Nearly doubling the sniper mortar's cooldown (5→9 ticks) — with range, damage, and accuracy held fixed, and the arena/brawler loadout untouched — did not, on its own, give the brawler a competitive win rate against the qwen35 asym v1 anchor.

**Implication for the tournament:** arm 3's single lever (sniper fire-rate interval only, no range/damage/geometry/loadout change) is not sufficient on its own, joining arm 1 (mortar_r30) and arm 13 (leapfrog_cover) in the FAILED band. The single abort (seed 5028) was a completion-length issue orthogonal to the lever and does not weaken the result — 29/30 elimination-terminal matches all resolved decisively in blue's favor regardless of the slower mortar cadence, suggesting the sniper's per-shot lethality (not shot frequency) is the dominant factor at this arena/loadout configuration. The other levers in the same PR (arm 4 `mortar_acc`, arm 11 `corridor_spawn`) remain untested by this document and should be read as independent single-lever results, not compared against arm 3's magnitude without their own batteries.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/tourn_arm3_mortar_cd9/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `objective_scored`, `llm_completion_requested`, `llm_completion_resolved`, `llm_completion_failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against `battery_summary.json`.
- v1 anchor: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- Merge commit: `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (PR #159, `main`).
- No secrets, keys, or absolute paths included.
