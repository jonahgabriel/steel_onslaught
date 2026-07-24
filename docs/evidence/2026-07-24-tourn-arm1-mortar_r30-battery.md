# Tournament Arm 1 (mortar_r30) Battery — Sniper Mortar Range 50 → 30 (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/30 = 0.0000** — below the 0.10 FAILED threshold, and numerically identical to the qwen35 asym v1 anchor (also 0/30). Capping the sniper's mortar range alone did not move the outcome.

**Ledger:** `.onex_state/steel_onslaught/tourn_arm1_mortar_r30` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/matches/*.yaml`) in the SO-TOURN worktree.
**Change under test:** PR #159 (merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97`) — `artillery_mortar_r30.yaml` (additive weapon variant of `artillery_mortar.yaml`, `range: 50 → 30`, every other field — `damage`, `pressure_cost`, `heat_generated`, `cooldown_ticks`, `accuracy_curve`, `target_class_effectiveness`, `damage_type`, `compatibility` — byte-identical) + `sniper_ironclad_mortar_r30.yaml` (additive loadout variant of `qwen35/sniper_ironclad.yaml`, swaps only `weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_r30`, every other module/field identical) + `tactical_split_overdeal_utility_asym_v1_qwen_mortar_r30.yaml` (additive battery overlay, functionally identical to the v1 combined overlay except isolated `.onex_state` paths — arena `foundry_60_asym_v1` and red loadout `llm_qwen35_berserker.yaml` both stay the driver defaults, unmodified). All baseline files (`artillery_mortar.yaml`, `foundry_60_asym_v1.yaml`, `llm_qwen35_berserker.yaml`, `qwen35/sniper_ironclad.yaml`, the v1 combined overlay) verified byte-identical pre/post-merge below.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baseline anchor:** qwen35 asym v1 combined overlay — 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue utility keep-rate 0.1657 (`.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
- All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger and `battery_raw.jsonl`, not copied from the implementer's or battery runner's report.

---

## Method

- **Decided-match win rate per seat** = wins ÷ `match_ended` count, aborts excluded from denominator (there were no aborts this run — see Completion health below).
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt. `json_each`/`json_extract` over `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by `seat`. Identical method to the 2026-07-23 baseline doc and the 2026-07-24 recut-v2 doc.
- **Terminal-class mix** from `battery_raw.jsonl.terminal_class` / `battery_summary.json.terminal_classes`, cross-checked against `match_started`/`match_ended` event counts in `events.sqlite3`.

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

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 all present exactly once) and cross-checked against `events.sqlite3` (`match_started`=30, `match_ended`=30, `SELECT COUNT(DISTINCT match_id)`=30). Matches the runner's raw tally exactly, per-seed, with zero discrepancy.

## 2. Match length

| Metric | Arm 1 (mortar_r30) | v1 anchor |
|---|---:|---:|
| min ticks | 14 | 17 |
| median ticks | **28** | 31 |
| mean ticks | 27.7 | — |
| max ticks | 44 | — |

Median fell 31 → 28 (−3 ticks, −9.7%). This is a modest shortening, not a collapse — the distribution stays healthy (range 14–44, mean 27.7 close to median), and every match still terminated by elimination rather than hitting a tick cap or degenerate early-abort pattern. A range-capped mortar giving the sniper less standoff room is a plausible mechanism for slightly faster resolution (less time spent at maximum range before either side can meaningfully engage), but the shift is small relative to n=30 noise and does not, by itself, change the win-rate verdict.

## 3. Utility keep-rate (causal-attribution check)

| Seat | Arm 1 programmed / dealt | Arm 1 keep-rate | v1 anchor keep-rate | Δ |
|---|---:|---:|---:|---:|
| red (brawler) | 13 / 354 | **0.0367** | 0.0552 | −0.0185 |
| blue (sniper) | 56 / 354 | **0.1582** | 0.1657 | −0.0075 |
| all-card (sanity, both seats) | 885+885 / 1770+1770 | 0.5000 | 0.5000 (mechanical) | 0 |

All-card keep-rate is exactly 0.5000 on both seats (885/1770), confirming the 5-of-10 register structure held and validating 0.50 as the null, same as every prior battery on this overlay shape.

Utility keep-rate held flat-to-slightly-down on both seats (red −0.0185, blue −0.0075) — both movements are small relative to n=30 sampling noise and in the same direction (down), not diverging. Since win rate also did not move (0/30 → 0/30), this is a clean negative result: **the range cap changed neither drafting behavior nor outcome.** There is no confound to worry about here — a single weapon-range lever has no mechanism to touch card-programming behavior, and the ledger confirms it didn't.

## 4. Objectives (secondary signal, not the gating metric)

| Objective | Awards | Red | Blue | Matches scored | Control changes |
|---|---:|---:|---:|---:|---:|
| objective.east_gate | 9 | 2 | 7 | 2 | 1 |
| objective.north_works | 5 | 5 | 0 | 1 | 0 |
| objective.west_yard | 4 | 4 | 0 | 2 | 0 |

Red picks up objective-control awards in a handful of matches where it survives to hold ground (9 of 18 total awards), consistent with prior batteries — but as always, this never converts to a VP-threshold win (0/30 VP terminals, 30/30 elimination).

## 5. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 367 |
| `llm_completion_resolved` | 354 |
| `llm_completion_failed` | 13 |
| `finish_reason` distribution | `stop`: 354 / 354 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 354 / 354 (zero fallback/heuristic plans) |
| Matches with ≥1 failed_completions | 9 / 30 (seeds 5001, 5002, 5003, 5008, 5009, 5013, 5014, 5024, 5027) |
| Max single-match failures | 2 (seeds 5001, 5002, 5009, 5013) |
| Matches reaching an unrecovered abort | 0 |

367 requested − 354 resolved = 13, matching `llm_completion_failed`=13 exactly: every failed completion was a bounded retry that eventually resolved (`finish_reason=stop`, `plan_source=llm` on all 354 final plans). None escalated to a match abort — consistent with `play_terminal_fraction=1.0` and zero draws/hard-failures.

## 6. Merge / additivity verification

- PR #159 merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (`gh pr view 159`: state MERGED, mergedAt 2026-07-24T15:19:31Z).
- 4/4 CI checks green on the merged PR (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: success`).
- `git diff 9eac392 01b0b43 -- contracts_data/weapons/artillery_mortar.yaml contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml` returns **empty** — all five baseline files are byte-identical across the merge. Only new additive files (`artillery_mortar_r30.yaml`, `sniper_ironclad_mortar_r30.yaml`, `tactical_split_overdeal_utility_asym_v1_qwen_mortar_r30.yaml`, plus the sibling arm 3/4/11/13 files landed in the same PR) were added.
- Direct file-level diff of `artillery_mortar_r30.yaml` vs `artillery_mortar.yaml` confirms exactly one functional field changed (`range: 50` → `range: 30`); `sniper_ironclad_mortar_r30.yaml` vs `sniper_ironclad.yaml` confirms exactly one module swap (`weapon.siege.artillery_mortar` → `weapon.siege.artillery_mortar_r30`); the arm's battery overlay vs the v1 combined overlay differs only in comments and isolated `.onex_state` paths, with zero functional config-line changes.

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/30), inside the `<0.10` FAILED band and numerically identical to the v1 anchor's 0/30. `play_terminal_fraction=1.0` clears the ≥0.9 trust gate, so this is a trustworthy null result, not a measurement artifact. Match length shortened modestly (median 31→28, −9.7%) but did not collapse, and terminal-class mix stayed 100% elimination. Utility keep-rate moved slightly down on both seats (red 0.0552→0.0367, blue 0.1657→0.1582) rather than up — since win-rate also did not move, keep-rate held effectively flat as expected for a lever with no drafting-layer mechanism, and the small downward drift on both seats together (not diverging) is consistent with sampling noise rather than a directional effect. Capping the sniper's mortar range to 30 — inside the arena's own 40-cell sightline lane — did not, on its own, give the brawler a competitive win rate against the qwen35 asym v1 anchor.

**Implication for the tournament:** arm 1's single lever (range only, no accuracy/damage/cooldown change) is not sufficient. Per PR #159's own design note, arm 4 (`mortar_acc`, far-band accuracy nerf) was staged as the CONDITIONAL next arm specifically for this case — arm 1 undershooting. The other levers in the same PR (arm 3 `mortar_cd9` cooldown, arm 11 `corridor_spawn`, arm 13 `leapfrog_cover`) remain untested by this document and should be read as independent single-lever results, not compared against arm 1's magnitude without their own batteries.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/tourn_arm1_mortar_r30/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `llm_completion_requested`, `llm_completion_resolved`, `llm_completion_failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against `battery_summary.json` and the 30 `evaluations/matches/*.yaml` files (1:1 match_id correspondence confirmed) in the same directory.
- v1 anchor: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- Merge commit: `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (PR #159, `main`).
- No secrets, keys, or absolute paths included.
