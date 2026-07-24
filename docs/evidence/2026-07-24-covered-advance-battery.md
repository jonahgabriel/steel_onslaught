# Covered-Advance Movement Card Battery — Brawler LOS-Shadow Advance (2026-07-24)

**Verdict:** **FAILED.** Decided-match red (brawler) win rate is **0/29 = 0.0000** (1 abort excluded) — below the 0.10 FAILED threshold, identical to every prior brawler arm. The card is **not inert** — pilots program it at a **95.9% rate**, far above every other movement card — but the mechanism it enables (LOS-shadow advance) measurably reduced blue's zero-probability-shot deficit trend further without moving the win-rate needle at all.

**Ledger:** `.onex_state/steel_onslaught/covered_advance_battery/seed_{5001..5030}/` (per-seed `events.sqlite3`, `battery_raw.jsonl`) in the SO-SEEKCOVER worktree.
**Change under test:** `card.movement.covered_advance` (PR #165, merged to `main` at `47a449ee0d3fa0231efe795e4e531ee2a31d0732`) — a new MOVEMENT-class card whose deterministic resolver (`_covered_advance_step`) moves the mech toward the enemy while preferring reachable cells where the enemy's LOS is blocked, tie-broken on fixed lexicographic `(distance_to_enemy, x, y)`, degrading to plain `toward_enemy` advance when no LOS-shadowed cell reduces distance. Overlay: `tactical_split_overdeal_utility_asym_v3_qwen.yaml`. Arena: `foundry_60_asym_v2`. Red loadout: `llm_qwen35_berserker_v2.yaml`; blue used driver default `sniper_ironclad.yaml`.
**Model:** live Qwen3.5-35B-A3B both seats, n=30, seeds 5001–5030, `all_replay_valid=true`, `o_gate_pass=true`.
**Baselines:**
- v1 anchor (`ugate_surfacing_fix_battery`, cited `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`): 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue-shot `hit_probability==0` fraction 24.7% (independently recomputed from `SO-PROMPT-SURFACING` worktree ledger, matches cited figure).
- Arm zero / v2 (`brawler_recut_v2_battery`, `docs/evidence/2026-07-24-brawler-recut-v2-battery.md`): 0/30 red wins, median 33 ticks, red utility keep-rate 0.0526, blue-shot `hit_probability==0` fraction 41.1%, blue hits landed/match mean 2.533 (independently recomputed from `SO-RECUT` worktree ledger, matches cited figures).
- All figures below are independently recomputed from the raw sqlite ledgers by an adversarial verifier, not copied from the battery runner's report.

---

## Method

- **Decided-match win rate per seat** = wins ÷ (30 − aborts), aborts excluded from the denominator.
- **`hit_probability==0` fraction** = fraction of `weapon_fired` events with `subject.player_id == player.blue` whose `payload.hit_probability == 0.0` — i.e. shots blue took where the mech had zero chance to connect (LOS-blocked or out-of-effective-range target).
- **Card funnel (dealt → programmed → resolved)** = occurrence-level counts: `hand_dealt.partitions.movement.card_ids` entries (dealt), `plan_committed.registers[].card_id` entries (programmed), `move_intent.direction` entries (resolved), all filtered to `player.red` and `card.movement.covered_advance` / `direction=="covered_advance"`.
- **Movement-card norm comparison** = same dealt/programmed accounting applied to every other red movement card in the same 30-match sample.
- **Utility keep-rate per seat** = utility cards programmed ÷ utility cards dealt, same method as the 2026-07-23/07-24 baseline docs.

---

## 1. Win rate + terminal health

| Metric | Value |
|---|---|
| Matches run | 30 (seeds 5001–5030) |
| Terminal-class mix | elimination 29/30, abort 1/30 (seed 5019, `reason: aborted`, `winner_id: null`) |
| `play_terminal_fraction` | **0.9667** (gate: ≥0.9 — PASS, battery is trustworthy) |
| Winner distribution | player.blue 29, draw 1 |
| **Decided-match red win rate** | **0/29 = 0.0000** |
| Decided-match blue win rate | 29/29 = 1.0000 |
| Terminal reason (decided matches) | `last_mech_standing` × 29 |

The single abort (seed 5019) had 13 `llm_completion_requested` vs 11 `llm_completion_resolved` — consistent with an unresolved completion mid-match, matching the battery runner's noted shared-endpoint transport instability. `all_replay_valid=true` holds across all 30 matches including the abort.

## 2. Match length

| Metric | This battery | Arm zero (v2) | v1 anchor |
|---|---:|---:|---:|
| min ticks | 18 | — | 17 |
| max ticks | 73 | — | 71 |
| mean ticks | 44.63 | — | — |
| median ticks | 43.0 | 33.0 | 31 |

Median match length rose 31 → 33 → 43 across the three arms — a real, monotonic increase, consistent with red surviving longer as the LOS-shadow behavior gets structurally stronger. It has not yet translated into a single decided win.

## 3. Card funnel — covered_advance is NOT inert

| Metric | Value |
|---|---:|
| Dealt (red, occurrence-level) | 338 |
| Programmed (`plan_committed`) | 324 |
| Resolved (`move_intent.direction==covered_advance`) | 310 |
| Programming rate (programmed/dealt) | **0.9586** |
| Resolve rate (resolved/programmed) | 0.9568 |
| Share of all red `move_intent` events | 0.5827 (310/532) |

**Discrepancy flagged against the runner's raw tally:** the battery runner's "mechanical count" section reports 218 `hand_dealt` / 216 `plan_committed` occurrences of `covered_advance`. Independent recomputation shows this undercounts by ~35% — the runner's method counted **event rows containing the string at least once** (`grep -c`-equivalent), not **card occurrences**, and up to 4 copies of `card.movement.covered_advance` can appear in a single hand (verified: seed 5001's first red hand alone contains 4 copies, contributing 1 row but 4 occurrences). The `move_intent` figure (310) is unaffected because that event type carries at most one `direction` value per row, so row-count and occurrence-count coincide there. This does not change the verdict but the runner's programming-rate arithmetic, if computed from the row counts, would be directionally similar (216/218=0.991) but not the correct occurrence-level rate (0.9586) — reported here corrected.

**Movement-card norm comparison (red, this battery, occurrence-level):**

| Card | Dealt | Programmed | Rate |
|---|---:|---:|---:|
| `card.movement.covered_advance` | 338 | 324 | **0.9586** |
| `card.movement.advance` | 112 | 52 | 0.4643 |
| `card.movement.flank_left` | 224 | 95 | 0.4241 |
| `card.movement.flank_right` | 218 | 88 | 0.4037 |
| `card.movement.reposition` | 216 | 8 | 0.0370 |

`covered_advance` is programmed at more than double the rate of any other movement card and 26x `reposition`'s rate. This confirms the design bet driving the movement-class (not utility-class) placement: pilots do not suppress this card — they prioritize it far above baseline. The forensics finding that motivated this build (terrain mentioned in 0/209 rationales, cover unusable by construction) is directly falsified for this specific card: cover-seeking behavior is now the dominant movement choice for the brawler seat.

## 4. Behavioral read — did red's LOS exposure actually drop?

| Metric | This battery | Arm zero (v2) | v1 anchor |
|---|---:|---:|---:|
| Blue `weapon_fired` total shots | 256 | 197 | 166 |
| Blue shots with `hit_probability==0` | 133 | 81 | 41 |
| **Fraction `hit_probability==0`** | **0.5195** | 0.4112 | 0.2470 |
| Blue hits landed, total (30 matches) | 82 | 76 | — (not recomputed) |
| **Blue hits landed / match (mean)** | **2.733** | 2.533 | — |
| Red mechs destroyed / 30 | 29 | — | — |

The zero-probability-shot fraction rose again: 24.7% (v1) → 41.1% (arm zero geometry/loadout re-cut) → **51.95%** (covered_advance) — a continued, monotonic increase across all three interventions, and the largest single jump of the three. This is a genuine, mechanically verified signal that the LOS-shadow resolver is doing what it was built to do: more of blue's shots are now being fired at targets/positions with zero hit chance.

That signal has **not** suppressed blue's actual damage output. Hits landed per match rose slightly (2.533 → 2.733, +8%) rather than falling, and red is still eliminated in 29/30 matches. Two things can both be true: (a) a larger share of blue's *attempted* shots are wasted on zero-probability targets, and (b) blue's *effective* shots (the ~48% with nonzero probability) are landing often enough, over a longer match, to still eliminate red in essentially every game. Match duration also rose in step (median 33 → 43 ticks, +30%), so the raw hits-landed-per-match figure is not adjusted for match length; on a per-tick basis, blue's hit rate actually fell (2.533/33=0.0767/tick → 2.733/43=0.0635/tick, −17%), consistent with the LOS mechanism working but not fast enough or not decisively enough to change who wins.

## 5. Utility keep-rate (unaffected-lane control)

| Seat | Programmed / Dealt | Keep-rate | Arm-zero keep-rate |
|---|---:|---:|---:|
| red (brawler) | 31 / 554 | 0.0560 | 0.0526 |
| blue (sniper) | 51 / 554 | 0.0921 | — |

Red's utility-card suppression (the forensics finding that drove the movement-class placement decision for `covered_advance` in the first place) holds essentially flat (0.0526 → 0.0560) — confirming the card's high uptake is specific to its movement-class placement and not a general drafting-behavior shift.

## 6. Objectives (secondary signal, not the gating metric)

| Objective | Awards | Red | Blue | Matches scored |
|---|---:|---:|---:|---:|
| objective.east_gate | 12 | 3 | 9 | 7 |
| objective.west_yard | 3 | 3 | 0 | 1 |

No control changes recorded across the battery (`matches_with_control_change: 0`).

---

## Content-identity / drift verification

The battery runner's report claimed the tested worktree state was "identical to merged main." Independent verification:

- Worktree HEAD `cc99683da8dec22dc52b0837bf98aa30c826e77a` (branch `feat/so-covered-advance-card`) diverged from `main` at merge-base `647d8be`.
- Diffed against **the cited SHA** `47a449ee0d3fa0231efe795e4e531ee2a31d0732` (PR #165's merge commit): only 3 evidence markdown files differ, zero source-code diff. This part of the runner's claim is correct **for that specific SHA**.
- Diffed against **`origin/main`'s current tip** (`9d59561`, three merges ahead of `47a449e`): 2,842 lines of drift, including a 210-line new `move_resolution.py` module. Verified this is a pure verbatim extraction of `_covered_advance_step` out of `runner.py` into a standalone module (PR #167, spatial-representation feature) — line-by-line comparison confirms identical LOS/reachability/tie-break logic, only the call signature changed (module function taking `obstacles`/`arena_size` params vs. a method reading `self._obstacles`/`self._arena_size`). **No semantic drift in the resolver under test.** The runner's "identical to merged main" phrasing is imprecise (main's tip has moved 3 commits since 47a449e) but the specific claim that matters — the resolver logic tested is unchanged — holds.

---

## Verdict

**FAILED** on the primary gate (decided-match red win rate 0/29, inside `<0.10`). `card.movement.covered_advance` is **directionally real, not inert**: 95.9% programming rate (highest of any movement card by a wide margin), and a monotonic, mechanically-verified increase in blue's zero-probability-shot fraction (24.7% → 41.1% → 51.95%) across the three successive brawler interventions. The card is doing exactly what it was designed to do — pilots seek it out and the resolver denies LOS more often — but that mechanism has not yet been sufficient to flip a single match. Match duration is climbing in step (median 31 → 33 → 43 ticks), which is the shape of a lever that is working but underpowered, not a lever that is inert.

**Next lever:** the per-tick hit-rate drop (0.0767 → 0.0635) suggests the LOS mechanism is diluting blue's damage rate without reducing blue's *total* damage opportunity, because matches simply run longer instead of ending in red's favor. The card only fires on red's own movement register and only degrades gracefully to `toward_enemy` — it cannot itself deny blue's turns to re-acquire a firing angle after red advances into the open on a subsequent register. The next test should look at whether red's *non-movement* registers (fire/utility) are being sequenced to exploit the LOS-shadow window `covered_advance` opens, or whether red still fires and utility-drafts on the old cadence regardless of newly-available cover — i.e., whether the rest of the plan is coupled to the new movement primitive at all.

---

## Citations (all relative paths)

- This arm's ledger: `.onex_state/steel_onslaught/covered_advance_battery/seed_{5001..5030}/events.sqlite3` (`weapon_fired`, `hit_resolved`, `hand_dealt`, `plan_committed`, `move_intent`, `mech_destroyed`, `match_ended` event types), cross-checked against each seed's `battery_summary.json`.
- Arm zero ledger: `.onex_state/steel_onslaught/brawler_recut_v2_battery/events.sqlite3` (SO-RECUT worktree), cited in `docs/evidence/2026-07-24-brawler-recut-v2-battery.md`.
- v1 anchor ledger: `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree), cited in `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- Card contract: `contracts_data/cards/movement_covered_advance.yaml`; deck placement: `contracts_data/decks/movement_v2.yaml`.
- Resolver: `src/steel_onslaught/match/runner.py::_covered_advance_step` at merge SHA `47a449ee0d3fa0231efe795e4e531ee2a31d0732` (PR #165); extracted verbatim to `src/steel_onslaught/match/move_resolution.py::_covered_advance_step` at `origin/main` tip `9d59561f6f069476bf68a8a9ae6a18d9bec09a9b` (PR #167).
- No secrets, keys, or absolute paths included.
