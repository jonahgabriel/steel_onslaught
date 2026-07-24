# Tournament Arm 4 (mortar_acc) Battery — Sniper Mortar Far-Band Accuracy Nerf (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/30 = 0.0000** — below the 0.10 FAILED threshold, and numerically identical to the qwen35 asym v1 anchor (also 0/30) and to sibling arm 1 (`mortar_r30`, also 0/30). Softening the sniper mortar's far-band accuracy — leaving max range at 50 but nerfing hit probability at 35/45/50 — did not move the outcome off the floor.

**Ledger:** `.onex_state/steel_onslaught/tourn_arm4_mortar_acc` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/`) in the SO-TOURN worktree.
**Change under test:** PR #159 (merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97`) — `contracts_data/weapons/artillery_mortar_acc.yaml` (additive weapon variant of `artillery_mortar.yaml`, `accuracy_curve` far-band entries nerfed: `{range:20, hit_probability:0.80}` unchanged, `{35: 0.70→0.35}`, `{45: 0.55→0.25}`, `{50: 0.40→0.15}`; every other field — `range`, `damage`, `pressure_cost`, `heat_generated`, `cooldown_ticks`, `target_class_effectiveness`, `damage_type`, `compatibility` — byte-identical) bound via `contracts_data/loadouts/qwen35/sniper_ironclad_mortar_acc.yaml` (additive loadout variant of `sniper_ironclad.yaml`, single module swap `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_acc`, every other module/field identical) and selected by `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen_mortar_acc.yaml` (additive overlay, functionally identical to the v1 combined overlay except isolated `.onex_state` paths and comments — arena and red/brawler loadout stay the driver defaults, unmodified). All baseline files (`artillery_mortar.yaml`, `sniper_ironclad.yaml`, `llm_qwen35_berserker.yaml`, `foundry_60_asym_v1.yaml`, the v1 combined overlay) verified byte-identical pre/post-merge below.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baseline anchor:** qwen35 asym v1 combined overlay — 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue utility keep-rate 0.1657 (`.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
**Conditional-arm trigger:** this arm is gated CONDITIONAL — battery-run only if arm 1 (`mortar_r30`, hard range cap 50→30) undershoots. Arm 1 landed **FAILED** at 0/30 (`docs/evidence/2026-07-24-tourn-arm1-mortar_r30-battery.md`), which triggered this run.
- All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger and `battery_raw.jsonl`, not copied from the implementer's or battery runner's report.

---

## Method

- **Decided-match win rate per seat** = wins ÷ `match_ended` count, aborts excluded from the denominator (there were no aborts this run — see Completion health below).
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt. `json_each` over `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed) parsed from `payload_json`, filtered to `card.utility.%`, grouped by `seat`. Identical method to the 2026-07-23 baseline doc and the arm 1/3/11/13 evidence docs.
- **Terminal-class mix** from `battery_raw.jsonl.terminal_class` / `battery_summary.json.terminal_classes`, cross-checked against `match_started`/`match_ended` event counts in `events.sqlite3`.
- **Per-seed cross-check**: every seed's `duration_ticks`, `failed_completions`, `winner_player_id`, `terminal_class` recomputed programmatically from `battery_raw.jsonl` and diffed against the runner's raw tally table — **exact match, zero discrepancy across all 30 seeds.**

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| `match_started` events | 30 |
| `match_ended` events (= decided matches) | 30 / 30 (1:1, zero orphans) |
| play_terminal_fraction | **1.0** (gate: ≥0.9 — PASS, battery is trustworthy) |
| Terminal-class mix | elimination 30/30 (0 VP-threshold, 0 draw, 0 tick_cap) |
| Winner distribution | player.blue 30 / player.red 0 |
| **Decided-match red win rate** | **0/30 = 0.0000** |
| Decided-match blue win rate | 30/30 = 1.0000 |
| Replay validity | 1/1 both players, all 30 matches |
| Draws | 0 |
| Aborted / hard-failed matches | 0 |

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 all present exactly once) and cross-checked against `events.sqlite3` (`match_started`=30, `match_ended`=30, `SELECT COUNT(DISTINCT match_id)`=30, `victory_declared.winner_player_id`=`player.blue` × 30). Matches the runner's raw tally exactly, per-seed, with zero discrepancy.

## 2. Match length

| Metric | Arm 4 (mortar_acc) | v1 anchor | Arm 1 (mortar_r30) |
|---|---:|---:|---:|
| min ticks | 12 | 17 | 14 |
| median ticks | **28.5** | 31 | 28 |
| mean ticks | 28.4 | — | 27.7 |
| max ticks | 50 | — | 44 |

Median fell 31 → 28.5 (−2.5 ticks, −8.1%), essentially matching arm 1's shortening (28) despite a very different mechanism (accuracy nerf vs. hard range cap). The distribution stays healthy (range 12–50, mean 28.4 close to median) and every match still terminated by elimination — no tick-cap or degenerate-abort pattern. Unlike arm 1, this run's max (50) is notably higher than v1/arm1's max — two matches (seeds 5023, 5027) ran to 50 ticks, the longest of any arm-4 seed, consistent with a softer accuracy nerf sometimes producing longer standoffs than a hard range cutoff. The shift is small relative to n=30 noise and does not, by itself, change the win-rate verdict.

## 3. Utility keep-rate (causal-attribution check)

| Seat | Arm 4 programmed / dealt | Arm 4 keep-rate | v1 anchor keep-rate | Δ |
|---|---:|---:|---:|---:|
| red (brawler) | 14 / 358 | **0.0391** | 0.0552 | −0.0161 |
| blue (sniper) | 57 / 358 | **0.1592** | 0.1657 | −0.0065 |
| all-card (sanity, both seats) | 895 / 1790 (each seat) | 0.5000 | 0.5000 (mechanical) | 0 |

All-card keep-rate is exactly 0.5000 on both seats (895/1790, i.e. 5-of-10 registers programmed), confirming the deal/program structure held and validating 0.50 as the null, same as every prior battery on this overlay shape.

Utility keep-rate held flat-to-slightly-down on both seats (red −0.0161, blue −0.0065) — both movements are small relative to n=30 sampling noise and in the same direction (down), not diverging, and closely tracking arm 1's own small downward drift (red −0.0185, blue −0.0075). Since win rate also did not move (0/30 → 0/30), this is a clean negative result: **the far-band accuracy nerf changed neither drafting behavior nor outcome.** A weapon-accuracy lever has no mechanism to touch card-programming behavior, and the ledger confirms it didn't — causal attribution to the lever (or lack thereof) is clean.

## 4. Objectives (secondary signal, not the gating metric)

| Objective | Awards | Red | Blue | Matches scored | Control changes |
|---|---:|---:|---:|---:|---:|
| objective.east_gate | 10 | 7 | 3 | 3 | 0 |
| objective.north_works | 14 | 9 | 5 | 3 | 1 |
| objective.west_yard | 2 | 2 | 0 | 1 | 0 |

Red picks up objective-control awards in a handful of matches where it survives to hold ground (16 of 26 total awards this run, a higher red share than arm 1's 9/18), consistent with prior batteries — but as always, this never converts to a VP-threshold win (0/30 VP terminals, 30/30 elimination). The elevated red objective share is a plausible side-effect of the accuracy nerf (red mechs surviving longer / holding ground more often before eventual elimination) but does not register as a win-condition change.

## 5. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 376 |
| `llm_completion_resolved` | 358 |
| `llm_completion_failed` | 18 |
| `finish_reason` distribution | `stop`: 358 / 358 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 358 / 358 (zero fallback/heuristic plans) |
| Matches with ≥1 failed_completions | 15 / 30 (seeds 5001, 5003, 5008, 5009, 5010, 5013, 5015, 5017, 5019, 5020, 5022, 5023, 5024, 5027, 5029) |
| Max single-match failures | 2 (seeds 5009, 5013, 5022) |
| Matches reaching an unrecovered abort | 0 |

376 requested − 358 resolved = 18, matching `llm_completion_failed`=18 exactly: every failed completion was a bounded retry that eventually resolved (`finish_reason=stop`, `plan_source=llm` on all 358 final plans). None escalated to a match abort — consistent with `play_terminal_fraction=1.0` and zero draws/hard-failures. This confirms the runner's note that the 18 failed completions were internal per-match retries under shared-endpoint contention (concurrent SO-PROMPT2/SO-SEEKCOVER battery lanes noted as running against the same qwen35 endpoint during this window), not measurement-affecting failures — no seed hard-failed or aborted, and no completion that ultimately fed a plan used a degraded `finish_reason` or non-LLM fallback.

**Operational note (from runner):** the first launch attempt (PID 26972) died silently mid-run around seed 5013 (~13/30 complete) with no recoverable crash trace, because `--fresh` wiped the state-root directory the nohup log was nested inside, unlinking the log before any error could be captured. The restart (PID 41703, log redirected outside the state root) ran to full completion in ~13 minutes. This verifier has no independent way to attribute a root cause to the first crash — flagging as an unconfirmed operational anomaly, not a battery-validity concern, since the surviving run's `battery_raw.jsonl`/`events.sqlite3` show a clean, complete, self-consistent 30/30 dataset with no artifacts of a partial/restarted run (all 30 `match_id`s are distinct ULIDs with no duplicates or gaps).

## 6. Merge / additivity verification

- PR #159 merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (`gh pr view 159`: state MERGED, mergedAt 2026-07-24T15:19:31Z, title "feat: tournament winner arms — 5 single-lever balance overlays (mortar r30/cd9/acc, leapfrog cover, corridor spawn)").
- 4/4 CI checks green on the merged PR (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: success`, verified via `gh pr checks 159`).
- `git diff 01b0b43c98c1712536ad722e5cd4cb3c79fbaa97^ 01b0b43c98c1712536ad722e5cd4cb3c79fbaa97 -- contracts_data/weapons/artillery_mortar.yaml contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml` returns **empty** — all five baseline files are byte-identical across the merge. Only new additive files were added (`artillery_mortar_acc.yaml`, `sniper_ironclad_mortar_acc.yaml`, `tactical_split_overdeal_utility_asym_v1_qwen_mortar_acc.yaml`, plus the sibling arm 1/3/11/13 files landed in the same PR).
- Direct file-level diff of `artillery_mortar_acc.yaml` vs `artillery_mortar.yaml` confirms **exactly one functional change**: the `accuracy_curve` far-band entries — `{range:20, hit_probability:0.80}` unchanged, `{35: 0.70→0.35}`, `{45: 0.55→0.25}`, `{50: 0.40→0.15}` — every other field (`range: 50`, `damage: 45`, `pressure_cost`, `heat_generated`, `cooldown_ticks`, `target_class_effectiveness`, `damage_type`, `compatibility`) byte-identical.
- Direct file-level diff of `sniper_ironclad_mortar_acc.yaml` vs `sniper_ironclad.yaml` confirms exactly one module swap (`weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_acc`), every other module (`chassis_id`, `boiler_id`, `pilot_id`, `harpoon_gun`, sensors, gizmos, budgets) byte-identical.
- The arm's battery overlay vs the v1 combined overlay differs only in comments and isolated `.onex_state` paths (`tourn_arm4_mortar_acc/...`), with zero functional config-line changes.

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/30), inside the `<0.10` FAILED band and numerically identical to the v1 anchor's 0/30 and to sibling arm 1's 0/30. `play_terminal_fraction=1.0` clears the ≥0.9 trust gate, so this is a trustworthy null result, not a measurement artifact. Match length shortened modestly (median 31→28.5, −8.1%) but did not collapse, and terminal-class mix stayed 100% elimination. Utility keep-rate moved slightly down on both seats (red 0.0552→0.0391, blue 0.1657→0.1592) rather than up — since win-rate also did not move, keep-rate held effectively flat as expected for a lever with no drafting-layer mechanism, and the small downward drift on both seats (not diverging) is consistent with sampling noise, matching arm 1's own drift almost exactly. Softening the sniper mortar's far-band accuracy — leaving max range untouched at 50 but degrading hit probability at 35/45/50 — did not, on its own, give the brawler a competitive win rate against the qwen35 asym v1 anchor.

**Implication for the tournament:** neither of the two mortar-only single-lever variants tested so far — arm 1 (hard range cap 50→30) and arm 4 (far-band accuracy nerf, this doc) — moves the outcome off the 0/30 floor. Both isolate a different mechanism (denying range entirely vs. degrading long-range reliability while preserving range) and both land at exactly 0/30 with near-identical keep-rate and match-length signatures. This is consistent with the sniper's advantage not being concentrated in the mortar's far-band accuracy or maximum range alone — the remaining untested levers from PR #159 (arm 3 `mortar_cd9` cooldown, arm 11 `corridor_spawn`, arm 13 `leapfrog_cover`) target different mechanisms (fire rate, spawn geometry, cover) and should be read as independent single-lever results, not compared against arm 1/4's magnitude without their own batteries. Per the tournament's single-lever design, a combined multi-lever arm was never in scope for this phase.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/tourn_arm4_mortar_acc/events.sqlite3` (`match_started`, `match_ended`, `victory_declared`, `hand_dealt`, `plan_committed`, `objective_scored`, `llm_completion_requested`, `llm_completion_resolved`, `llm_completion_failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against `battery_summary.json` in the same directory.
- v1 anchor: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- Sibling arm: `docs/evidence/2026-07-24-tourn-arm1-mortar_r30-battery.md` (conditional-arm trigger).
- Merge commit: `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (PR #159, `main`).
- No secrets, keys, or absolute paths included.
