# Tournament Arm 11 — corridor_spawn battery (n=30)

**Status:** COMPLETE, trustworthy. `play_terminal_fraction=1.0` (>= 0.9 gate), `all_replay_valid=true`, `o_gate_pass=true`.
**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/30 = 0.0000** — inside the `<0.10` FAILED band and numerically identical to the qwen35 asym v1 anchor's 0/30. Relocating the brawler's spawn into the covered corridor mouth produced **zero measurable change in outcome**.

**Ledger:** `.onex_state/steel_onslaught/tourn_arm11_corridor_spawn` (`events.sqlite3`, `leaderboard.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-TOURN worktree, branch `feat/so-tournament-arms`, HEAD `02f2e08b5252fa5b5fa3f894205936a7483c1f0e`.

**Change under test:** single-lever variant of `contracts_data/arenas/foundry_60_asym_v1.yaml` → `contracts_data/arenas/foundry_60_asym_v1_corridor_spawn.yaml`: `spawn_a` moves from `{x: 4, y: 30}` (open mid-lane, on the sniper's y=28–32 sightline) to `{x: 10, y: 22}` (inside the mouth of the north approach corridor, x=8–34/y=17–25). Bound via a new additive overlay (`contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen_corridor_spawn.yaml`) pointing at the new arena id. `foundry_60_asym_v1.yaml` and the v1 overlay are byte-untouched. No other field changed (spawn_b, obstacles, rects, objectives, VP schedule, sudden-death timing, loadouts, deck/over-deal shape all identical to v1).

**Coordinate correction (verified independently, before trusting the runner's report):** the dispatched value `{x: 8, y: 20}` collides with the pre-existing obstacle rect `{x0: 8, y0: 20, x1: 9, y1: 21}` — cell `(8,20)` is a member of that rect. The landed contract instead uses `{x: 10, y: 22}`. Re-verified here by loading the arena YAML and checking `(10, 22)` against all 22 `rects` entries (zero collisions), all 3 objective cells (`west_yard (18,30)`, `north_works (30,22)`, `east_gate (42,36)` — none coincide), and `spawn_b (52,30)` (Chebyshev distance 42, unchanged approach geometry). The correction is valid and the file as landed is internally consistent.

**Model:** live Qwen3.6-35B-A3B both seats, n=30, seeds 5001–5030, arena family `foundry_60_asym`.
**Baseline anchor:** qwen35 asym v1 combined overlay — 0/30 red wins, 100% elimination, median 31 ticks, red utility keep-rate 0.0552, blue utility keep-rate 0.1657 (`.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).

All figures below are independently recomputed by an adversarial verifier from the raw `events.sqlite3` ledger and `battery_raw.jsonl`, not copied from the implementer's or battery runner's report. The runner's raw tally is confirmed correct.

---

## Method

- **Trust gate:** `play_terminal_fraction >= 0.9` — measured `1.0` (30/30 matches reached a terminal state). Trustworthy.
- **Decided-match win rate** = wins / matches excluding aborts. All 30 matches terminated by `elimination` (no aborts, no draws), so decided n = 30 for both seats.
- **Utility keep-rate per seat = utility cards programmed / utility cards dealt.** `hand_dealt.card_ids` (dealt, matched against `card.utility.%`) vs `plan_committed.registers[].card_id` (programmed), grouped by `seat`, summed across all 30 matches. All-card keep-rate computed the same way over every card id as a sanity check on the 5-of-10 register structure (expected exactly 0.50).
- **Verdict bands** (decided-match red win rate): 0.35–0.65 COMPETITIVE / 0.10–0.35 DIRECTIONAL / <0.10 FAILED / >0.65 OVERSHOT.

---

## 1. Raw outcome tally

| Metric | Value |
|---|---:|
| n | 30 |
| play_terminal_fraction | 1.0000 |
| all_replay_valid | true |
| o_gate_pass | true |
| terminal_class | elimination: 30 / 30 (100%) |
| winner | player.blue: 30 / 30 |
| decided-match red win rate | **0 / 30 = 0.0000** |
| decided-match blue win rate | 30 / 30 = 1.0000 |
| failed_completions (sum, intra-match retry, not aborts) | 13 |
| replay-invalid seeds | 0 |
| seed coverage | 5001–5030, all 30 present, exact match to spec |

**Verdict band: FAILED** (< 0.10). Identical to baseline (0/30 both).

---

## 2. Match length

| Metric | corridor_spawn (n=30) | v1 anchor | Δ |
|---|---:|---:|---:|
| median ticks | **26.5** | 31 | **−4.5 (−14.5%)** |
| mean ticks | 25.87 | — | — |
| min / max ticks | 8 / 43 | — | — |

Match length **fell** — matches ended faster than the v1 anchor, even though the outcome (elimination, 0/30 red) did not change. This is consistent with the corridor spawn removing the brawler's initial open-ground crossing: it reaches contact (and dies) sooner rather than being picked off while approaching, but the terminal outcome is unaffected.

---

## 3. Utility keep-rate (causal-attribution check)

| Seat | Programmed / dealt | Keep-rate | v1 anchor keep-rate | Δ |
|---|---:|---:|---:|---:|
| red (brawler) | 16 / 328 | **0.0488** | 0.0552 | −0.0064 (−11.6% relative) |
| blue (sniper) | 53 / 328 | **0.1616** | 0.1657 | −0.0041 (−2.5% relative) |
| all-card (sanity, both seats) | 1640 / 3280 | 0.5000 | 0.5000 (mechanical) | 0 |

All-card keep-rate is exactly 0.5000 on both seats — confirms the 5-of-10 register structure and validates the sanity check. Utility keep-rate held essentially **flat** on both seats relative to the v1 anchor (red −0.0064, blue −0.0041; both within noise band for n=30 vs the anchor battery). This confirms the corridor-spawn lever did not perturb draft-layer behavior — as expected, since the lever only moves a starting coordinate and touches nothing in the card/deck/handler surface.

**Causal attribution: not clean, because there is nothing to attribute.** The instructions ask whether keep-rate moving alongside win rate would make attribution clean (it would). Here **neither moved**: win rate stayed at 0/30 (identical to baseline) and keep-rate stayed flat. The only valid claim is negative — the corridor spawn changed neither drafting behavior nor outcome. This mirrors the finding in `docs/evidence/2026-07-24-brawler-recut-v2-battery.md` (a different single-lever arm that also left both win rate and keep-rate unmoved).

---

## Verdict

**FAILED.** Decided-match red win rate is 0.0000 (0/30), inside the `<0.10` FAILED band, numerically identical to the qwen35 asym v1 anchor. `play_terminal_fraction=1.0` clears the trust gate — this is a trustworthy null result, not a measurement artifact. Match length **collapsed** (median 31 → 26.5 ticks, −14.5%): matches end faster with the brawler starting inside the corridor, but they still end in elimination with blue winning every time. Utility keep-rate is flat on both seats (red 0.0552→0.0488, blue 0.1657→0.1616), and since win rate is also flat, there is no outcome change for the flat keep-rate to explain — this is a clean negative control, not a positive causal story.

Starting the brawler already inside the covered corridor did not change who wins. Combined with the recurring cross-arm finding that the brawler under-programs utility regardless of starting position, terrain, or loadout re-cut, the bottleneck is most plausibly upstream of spawn geometry entirely — in the LLM planner's tactical decision-making (does the brawler ever program utility/cover-relative movement in a way that changes engagement outcomes, independent of where it starts?), not in the arena's spatial layout.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/tourn_arm11_corridor_spawn/events.sqlite3` (`hand_dealt`, `plan_committed` events) and `battery_raw.jsonl` (30 complete matches, seeds 5001–5030).
- Arena/overlay diff verified against: `contracts_data/arenas/foundry_60_asym_v1.yaml`, `contracts_data/arenas/foundry_60_asym_v1_corridor_spawn.yaml`, `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen_corridor_spawn.yaml`.
- qwen35 baseline anchor: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery`, cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- No secrets, keys, or absolute paths included.
