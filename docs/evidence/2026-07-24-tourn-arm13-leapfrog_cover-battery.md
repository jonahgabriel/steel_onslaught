# Tournament Arm 13 (leapfrog_cover) Battery — Staggered North/South Cover in the Sniper Lane (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/30 = 0.0000** — below the 0.10 FAILED threshold, and numerically identical to the qwen35 asym v1 anchor (also 0/30). Breaking the sniper's mid-lane sightline into five staggered north/south cover blocks did not move the outcome.

**Ledger:** `.onex_state/steel_onslaught/tourn_arm13_leapfrog_cover` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`, `evaluations/matches/*.yaml`) in the SO-TOURN worktree.
**Change under test:** PR #159 (merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97`) — `foundry_60_asym_v1_leapfrog_cover.yaml` (additive arena variant of `foundry_60_asym_v1.yaml`, adding 5 staggered blocking rects inside the previously fully-open y=28..32 sightline lane; every spawn, objective, VP field, and pre-existing rect byte-identical) + `tactical_split_overdeal_utility_asym_v1_qwen_leapfrog_cover.yaml` (additive battery overlay, functionally identical to the v1 combined overlay except `arena_id` rebinding and isolated `.onex_state` paths — both loadouts stay the driver defaults, unmodified). All baseline files (`foundry_60_asym_v1.yaml`, `llm_qwen35_berserker.yaml`, `qwen35/sniper_ironclad.yaml`, the v1 combined overlay) verified byte-identical pre/post-merge below.
**Model:** live Qwen3.6-35B-A3B, both seats, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baseline anchor:** qwen35 asym v1 combined overlay — 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue utility keep-rate 0.1657 (`.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
- All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger and `battery_raw.jsonl`, not copied from the implementer's or battery runner's report.

---

## Method

- **Decided-match win rate per seat** = wins ÷ `match_ended` count, aborts excluded from denominator (there were no aborts this run — see Completion health below).
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt. `json_each`/`json_extract` over `hand_dealt.card_ids` (dealt) and `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by `seat`. Identical method to the 2026-07-23 baseline doc and the arm 1 evidence doc.
- **Terminal-class mix** from `battery_raw.jsonl.terminal_class` / `battery_summary.json.terminal_classes`, cross-checked against `match_started`/`match_ended` event counts in `events.sqlite3`.
- **Arena collision check** — an independent Python script loaded both the baseline (`foundry_60_asym_v1.yaml`) and variant (`foundry_60_asym_v1_leapfrog_cover.yaml`) YAML, expanded every rect to its constituent integer cell set, and checked the 5 new rects pairwise against each other, against every pre-existing rect, and against the 2 spawn cells + 3 objective cells.

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

Recomputed directly from `battery_raw.jsonl` (30 rows, seeds 5001–5030 all present exactly once) and cross-checked against `events.sqlite3` (`match_started`=30, `match_ended`=30, `SELECT COUNT(DISTINCT match_id)`=30, zero `match_started` rows lacking a matching `match_ended`). Matches the runner's raw tally exactly, per-seed, with zero discrepancy.

## 2. Match length

| Metric | Arm 13 (leapfrog_cover) | v1 anchor |
|---|---:|---:|
| min ticks | 13 | 17 |
| median ticks | **35.0** | 31 |
| mean ticks | 38.5 | — |
| max ticks | 80 | — |

Median rose 31 → 35 (**+4 ticks, +12.9%**), and mean (38.5) sits well above median (35.0) with a long right tail (max 80, min 13) — the distribution is more spread out than the v1 anchor's, but every match still terminated by elimination rather than hitting a tick cap or a degenerate early-abort pattern. Adding cover inside what was previously a fully open sniper lane is a plausible mechanism for a modest lengthening (the brawler now has intermittent cover to break line-of-sight while closing, extending the engagement window) rather than a shortening. This is directionally the opposite of arm 1 (mortar range cap), which shortened matches — consistent with the two levers acting on different sides of the engagement (denying sniper standoff range vs. giving the brawler cover) — but the shift here is still modest relative to n=30 noise and does not, by itself, change the win-rate verdict.

## 3. Utility keep-rate (causal-attribution check)

| Seat | Arm 13 programmed / dealt | Arm 13 keep-rate | v1 anchor keep-rate | Δ |
|---|---:|---:|---:|---:|
| red (brawler) | 20 / 482 | **0.0415** | 0.0552 | −0.0137 |
| blue (sniper) | 94 / 482 | **0.1950** | 0.1657 | +0.0293 |
| all-card (sanity, both seats) | 1205 / 2410 | 0.5000 | 0.5000 (mechanical) | 0 |

All-card keep-rate is exactly 0.5000 on both seats (1205/2410 each), confirming the 5-of-10 register structure held and validating 0.50 as the null, same as every prior battery on this overlay shape.

Utility keep-rate did **not** hold uniformly flat this run: red moved down slightly (−0.0137, consistent with the flat/noise-band pattern seen elsewhere), but blue moved up by +0.0293 — roughly double red's magnitude and in the opposite direction. Because decided-match win rate also did not move (0/30 → 0/30, identical to baseline), there is no win-rate delta for this keep-rate divergence to explain — it cannot be evidence of a behavioral shift that changed the outcome. But it is **not** the clean "both seats flat/same-direction" read seen in the arm 1 doc, and a single lever with no direct card-programming mechanism (an arena rect change) has no obvious causal path to a +0.0293 blue-seat keep-rate shift. The most defensible read is n=30 sampling noise on a low-base-rate metric (blue's own baseline is already the higher of the two seats at 0.1657, so a few extra utility-card picks in a 482-card sample moves the rate visibly) — but this arm's keep-rate data should **not** be cited as a "confirmed clean flat-keep-rate" result the way arm 1's was; the divergence should be flagged, not smoothed over.

## 4. Objectives (secondary signal, not the gating metric)

| Objective | Awards | Red | Blue | Matches scored | Control changes |
|---|---:|---:|---:|---:|---:|
| objective.west_yard | 31 | 31 | 0 | 8 | 0 |
| objective.east_gate | 19 | 5 | 14 | 7 | 1 |
| objective.north_works | 0 | 0 | 0 | 0 | 0 |

Red picks up objective-control awards exclusively at west_yard (its home-side objective, in the open lane) in 8 of 30 matches, consistent with prior batteries on this arena family — but as always, this never converts to a VP-threshold win (0/30 VP terminals, 30/30 elimination). north_works was never scored this run.

## 5. Completion health

| Metric | Value |
|---|---|
| `llm_completion_requested` | 515 |
| `llm_completion_resolved` | 482 |
| `llm_completion_failed` | 33 |
| `finish_reason` distribution | `stop`: 482 / 482 (zero `length` truncations) |
| `plan_source` distribution | `llm`: 482 / 482 (zero fallback/heuristic plans) |
| Matches with ≥1 failed_completions | 23 / 30 |
| Max single-match failures | 3 (seed 5011, `match.01KYAD14T70Q3JNF6RG18DY613`) |
| Matches reaching an unrecovered abort | 0 |

515 requested − 482 resolved = 33, matching `llm_completion_failed`=33 exactly and matching the runner's raw-tally sum of per-seed `failed_completions` — every failed completion was a bounded retry that eventually resolved (`finish_reason=stop`, `plan_source=llm` on all 482 final plans). None escalated to a match abort — consistent with `play_terminal_fraction=1.0` and zero draws/hard-failures.

## 6. Arena collision check

Per the arm spec, an independent script expanded every rect (baseline + variant) to its full integer cell set and checked the 5 new rects against spawns, objectives, pre-existing rects, and each other:

- **As-dispatched spec** for block 2 (`{x0:18,y0:31,x1:22,y1:33}`) **does collide** with a pre-existing v1 rect (`{x0:19,y0:33,x1:20,y1:33}`, the west_yard south flanking cover) at cells `(19,33)` and `(20,33)` — confirmed independently.
- **As-landed**, block 2 was corrected to `{x0:18,y0:31,x1:22,y1:32}` (dropping the colliding `y1:33` row). This is a **deviation from the literal dispatched spec**, made by the implementer and documented inline in the arena file's header comment. Independently verified: the corrected block 2 has zero collisions with any pre-existing rect, spawn, or objective cell, and introduces no new collision anywhere else.
- All 5 landed blocks (1, 3, 4, 5 unchanged from spec; 2 corrected) have **zero** overlap with the 2 spawn cells (`(4,30)`, `(52,30)`), **zero** overlap with the 3 objective cells (`(18,30)`, `(30,22)`, `(42,36)`), **zero** pairwise overlap among themselves, and **zero** overlap with any of the 22 pre-existing rects.
- The full landed rect list (27 rects) equals the baseline's 22 rects plus exactly the 5 new blocks (with the one corrected coordinate) — set-equality confirmed programmatically, no other rect was added, removed, or altered.
- `spawn_a`, `spawn_b`, `obstacles`, `objectives`, `vp_threshold`, `sudden_death_start_tick`, `sudden_death_damage_base` are all field-for-field identical between `foundry_60_asym_v1.yaml` and `foundry_60_asym_v1_leapfrog_cover.yaml`.

**Finding:** the arm's single lever is not byte-for-byte the literal dispatched coordinate set — one of the five rects was corrected by 1 cell-row to avoid a real collision the dispatched spec would have created. This is a legitimate, narrowly-scoped, and transparently-documented correction (it does not touch any other rect, spawn, or objective, and it is the only way to satisfy the arm's own no-collision verification requirement), but it means the arm as landed and battery-tested is "5 staggered cover blocks, one adjusted by one row to avoid an existing-rect collision" rather than the literal coordinates as dispatched. Flagging this for the record rather than silently treating dispatched-spec and landed-file as identical.

## 7. Merge / additivity verification

- PR #159 merged to `main` at `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (`gh pr view 159`: state MERGED, mergedAt 2026-07-24T15:19:31Z).
- 4/4 CI checks green on the merged PR (`evidence-schema`, `frontend-test`, `python-test`, `sanitize-text`, all `conclusion: success`).
- `git diff 9eac392 01b0b43 -- contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml` returns **empty** — all four baseline files are byte-identical across the merge. Only new additive files (`foundry_60_asym_v1_leapfrog_cover.yaml`, `tactical_split_overdeal_utility_asym_v1_qwen_leapfrog_cover.yaml`, plus the sibling arm 1/3/4/11 files landed in the same PR) were added.
- `git log --oneline -- contracts_data/arenas/foundry_60_asym_v1.yaml contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml contracts_data/loadouts/llm_qwen35_berserker.yaml contracts_data/loadouts/qwen35/sniper_ironclad.yaml` shows no commits touching any of the four baseline files since before PR #159 — they remain byte-frozen.
- Direct diff of the arm 13 overlay vs the v1 combined overlay confirms the only functional changes are `arena_id: foundry_60_asym_v1` → `foundry_60_asym_v1_leapfrog_cover` and the isolated `.onex_state/steel_onslaught/tourn_arm13_leapfrog_cover/*` paths; every card-catalog, deck-policy, LLM-provider, and transport field is unchanged.

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/30), inside the `<0.10` FAILED band and numerically identical to the v1 anchor's 0/30. `play_terminal_fraction=1.0` clears the ≥0.9 trust gate, so this is a trustworthy null result, not a measurement artifact. Match length lengthened modestly (median 31→35, +12.9%) rather than collapsing, and terminal-class mix stayed 100% elimination. Utility keep-rate moved in **opposite directions** on the two seats (red −0.0137, blue +0.0293) rather than staying uniformly flat — since win-rate also did not move, this cannot be evidence of an outcome-relevant behavioral shift, but it is a genuine divergence (not clean same-direction noise) that should be read as sampling variance on a low-base-rate metric, not smoothed into a "confirmed flat" claim. Staggering five cover blocks north/south across the sniper's mid-lane sightline — even with one block corrected off its dispatched coordinates to avoid a real collision with existing west_yard flanking cover — did not, on its own, give the brawler a competitive win rate against the qwen35 asym v1 anchor.

**Implication for the tournament:** arm 13's single lever (cover geometry inside the sightline lane only, no weapon/loadout/spawn change) is not sufficient on its own, joining arm 1 (mortar_r30) in the FAILED band. The lane-breaking mechanism (leapfrog cover) did lengthen matches in the expected direction (more cover → longer engagements) without producing a single red win in 30 matches, suggesting the sniper's ranged damage output remains decisive even when its clean sightline is interrupted. The other levers in the same PR (arm 3 `mortar_cd9` cooldown, arm 4 `mortar_acc`, arm 11 `corridor_spawn`) remain untested by this document and should be read as independent single-lever results, not compared against arm 13's magnitude without their own batteries.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/tourn_arm13_leapfrog_cover/events.sqlite3` (`match_started`, `match_ended`, `hand_dealt`, `plan_committed`, `objective_scored`, `llm_completion_requested`, `llm_completion_resolved`, `llm_completion_failed` event types) and `battery_raw.jsonl` (30 rows, seeds 5001–5030), cross-checked against `battery_summary.json` and the 30 `evaluations/matches/*.yaml` files (1:1 match_id correspondence confirmed) in the same directory.
- Arena collision check: `contracts_data/arenas/foundry_60_asym_v1.yaml` vs `contracts_data/arenas/foundry_60_asym_v1_leapfrog_cover.yaml`, independent Python cell-expansion script (not committed — ad hoc verification only).
- v1 anchor: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- Merge commit: `01b0b43c98c1712536ad722e5cd4cb3c79fbaa97` (PR #159, `main`).
- No secrets, keys, or absolute paths included.
