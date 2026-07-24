# ARM G — Surfacing + Brawler-Seat Tactical Steering on Brawler Re-Cut v2 (2026-07-24)

**Verdict: FAILED (outcome) — but NOT vacuous, and NOT behaviorally inert.** Decided-match red (brawler) win rate is **0/29 = 0.0000**, inside the `<0.10` FAILED band, identical to the v1 anchor, the v2 arm-zero baseline, and ARM S (surfacing-only). Stacking brawler-seat-only tactical steering (route through cover, avoid the open y=28–32 lane, close before firing) on top of ARM S surfacing did **not** move the brawler off a 0/30 record. Independent recomputation surfaces real behavioral change the runner's report did not check: red's exposed-band dwell time drops sharply (z≈−5), first-shot timing shifts substantially later, and match length nearly doubles — but red's actual cover-cell occupancy stays at **0.0%, identical to both prior arms**. The steering measurably changed *how* red loses, not *that* it loses.

**Ledger:** `.onex_state/steel_onslaught/prompt_guidance_v2_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json`) in the SO-PROMPT2 worktree.
**Change under test:** guided pilot spec `pilot.llm.qwen35_berserker_guided` (`contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_guided.yaml`) + guided overlay `tactical_split_overdeal_utility_asym_v2_guided_qwen.yaml` — both landed additively in PR #160 alongside ARM S but were config-complete/untested until this battery. The guided overlay is byte-identical to the ARM S (surfacing) overlay except the red seat's `pilot_spec_id` (`pilot.llm.qwen35_berserker_guided` vs `pilot.llm.qwen35`); the blue seat stays bound to the unmodified `pilot.llm.qwen35_sniper` in both. This isolates the comparison: ARM G vs ARM S differs **only** in red's added `programming_guidance` block; ARM S vs v2-arm-zero differs **only** in the surfaced `cover_cells`/`enemy_weapon_threat` fields (both seats). All three arms share the identical `foundry_60_asym_v2` arena, v2 brawler loadout, and blue sniper loadout.
**Model:** live Qwen3.6-35B-A3B, n=30, seeds 5001–5030.
**Baselines:**
- v1 anchor (qwen35 asym v1 combined overlay): 0/30 red wins, median 31 ticks, red utility keep-rate 0.0552, blue keep-rate 0.1657 (`docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`).
- v2 arm-zero (PR #157, same arena/loadout, no prompt arms): 0/30 red wins, median 33 ticks, red utility keep-rate 0.0526, blue keep-rate 0.1794 (`docs/evidence/2026-07-24-brawler-recut-v2-battery.md`, ledger `.onex_state/steel_onslaught/brawler_recut_v2_battery` in SO-RECUT worktree).
- ARM S (surfacing only, both seats): 0/29 red wins (decided), median 30.5 ticks, red utility keep-rate 0.0188, blue keep-rate 0.0775, red cover-cell occupancy 0.0%, red y=28–32 band occupancy 41.9% (`docs/evidence/2026-07-24-prompt_surfacing_v2-battery.md`, ledger `.onex_state/steel_onslaught/prompt_surfacing_v2_battery` in SO-PROMPT2 worktree).

All figures below are independently recomputed by an adversarial verifier from the raw ledger and a fresh independent reproduction of the rendered prompt, not copied from the battery runner's report.

---

## 1. Win rate + terminal health

Recomputed directly from `battery_raw.jsonl` (30 rows, unique seeds 5001–5030, no duplicates/gaps) and cross-checked field-by-field against `battery_summary.json` — exact match on every field, including the per-seed table in the runner's raw tally (30/30 rows checked, zero transcription errors — unlike the ARM S doc's minor 14-vs-15 discrepancy, this report's tally is clean).

| Metric | Value |
|---|---|
| n | 30 |
| Terminal-class mix | elimination 29, abort 1 (seed 5014: `aborted`, `is_draw=true`) |
| play_terminal_fraction | **0.9667** (gate ≥0.9 — PASS, battery is trustworthy) |
| Decided matches (canonical: `is_draw=false`, not `terminal_class != abort` — same set here since the one abort is also the one draw) | 29 |
| Decided-match red win rate | **0/29 = 0.0000** |
| All-match red win rate | 0/30 = 0.0000 |
| Winner distribution | player.blue 29, draw 1 |
| `all_replay_valid` | true (recomputed: 0/30 seeds have any non-1 `replay_validity` value) |

**Note on the abort/draw row (seed 5014):** the raw `winner_player_id` field on that row is literally `player.blue` (not null/absent), but `is_draw=true` on the same row. The canonical `_summarize()` function in `scripts/run_ogate_objectives_battery.py` buckets winners as `"draw" if row["is_draw"] else row["winner_player_id"]`, and computes `decided = [row for row in rows if not row["is_draw"]]` — i.e. the draw flag, not the raw winner field or the `terminal_class == "abort"` test, is what governs both the winners histogram and the win-rate denominator. Recomputing with this exact rule reproduces `battery_summary.json`'s `winners: {"draw": 1, "player.blue": 29}` exactly. The runner's report's classification of seed 5014 as "draw" is correct by the canonical rule, not an error.

Verdict band: **FAILED** (<0.10), identical to v1 anchor, v2 arm-zero, and ARM S.

## 2. Objectives (secondary signal)

Recomputed by summing `objective_scored` awards per objective/player across all 30 matches; matches `battery_summary.json` exactly.

| Objective | Awards | Red | Blue | Matches scored | Control changes |
|---|---:|---:|---:|---:|---:|
| objective.west_yard | 44 | 44 | 0 | 13 | 0 |
| objective.east_gate | 33 | 6 | 27 | 8 | 2 |
| objective.north_works | 8 | 7 | 1 | 5 | 0 |

Consistent with prior batteries: red accumulates objective-control awards in matches it survives long enough to hold ground, but this has never converted to a VP-threshold win on this arena family (0/30 VP terminals here either).

## 3. Utility keep-rate per seat — NEW independent recomputation, not in the runner's report

Method: `hand_dealt.card_ids` (dealt) vs `plan_committed.registers[].card_id` (programmed), filtered to `card.utility.%`, grouped by seat — identical method to all three prior baseline docs. Recomputed via direct iteration over `events.sqlite3` (698 `hand_dealt` events = 349 per seat, hand quota 2 utility cards/hand deterministically = 698 utility cards dealt per seat; 698 `plan_committed` events = 349 per seat, register_count=5).

| Seat | ARM G programmed / dealt | ARM G keep-rate | v1 anchor | v2 arm-zero | ARM S |
|---|---:|---:|---:|---:|---:|
| red (brawler) | 50 / 698 | **0.0716** | 0.0552 | 0.0526 | 0.0188 |
| blue (sniper) | 70 / 698 | **0.1003** | 0.1657 | 0.1794 | 0.0775 |
| all-card sanity (per seat) | 1745 / 3490 | 0.5000 | 0.5000 (mechanical) | 0.5000 | 0.5000 |

Two-proportion / one-proportion z-tests (baseline rate as null, ARM G's n=698 observed count):

| Comparison | z | Direction |
|---|---:|---|
| red ARM G vs v2 arm-zero (0.0526) | +2.25 (p≈0.024) | ARM G **higher** |
| red ARM G vs v1 anchor (0.0552) | +1.90 (p≈0.057, borderline) | ARM G **higher** |
| red ARM G vs ARM S (0.0188) | **+10.28** | ARM G sharply **higher** |
| blue ARM G vs v2 arm-zero (0.1794) | **−5.45** | ARM G sharply **lower** |
| blue ARM G vs v1 anchor (0.1657) | **−4.65** | ARM G sharply **lower** |
| blue ARM G vs ARM S (0.0775) | +2.25 (p≈0.024) | ARM G higher |

**Two real, previously unmeasured findings:**

1. **Red's keep-rate partially recovers under ARM G relative to ARM S** (0.0716 vs 0.0188, z=10.28) — nearly back to the pre-surfacing baseline range, and even nominally above both baselines (mild/borderline significance). This is notable because ARM G's steering text targets movement/attack card selection, not utility — there is no obvious causal mechanism in the guidance text itself for *raising* utility keep-rate. A plausible confound: ARM G matches run ~1.7× longer (§5), giving more hand-dealt cycles and potentially different late-match card-availability dynamics than the shorter ARM S matches: this is a hypothesis, not established causally here.
2. **Blue's keep-rate drops further under ARM G, even though blue receives no steering at all** — blue is bound to the identical, unmodified `pilot.llm.qwen35_sniper` spec in both ARM S and ARM G. A same-seat-unchanged input producing a significant behavioral shift (z=−5.45 vs arm-zero) means the effect is not coming from anything in blue's own prompt — it is a second-order consequence of red's steering changing the *match dynamics* blue is reacting to (most plausibly the longer, later-engagement matches described in §5, which give blue's sniper archetype more opportunity to spend registers on repeated attack cards during red's now-longer approach phase rather than time-boxing to two utility slots). This is a real cross-seat spillover effect worth flagging: seat-scoped steering is not necessarily seat-isolated in its behavioral consequences.

## 4. Match length — NEW comparison not drawn in the runner's report

| Metric | ARM G (this battery) | ARM S | v2 arm-zero | v1 anchor |
|---|---:|---:|---:|---:|
| min ticks | 23 | 18 | 14 | 17 |
| median ticks | **54.0** | 30.5 | 33.0 | 31 |
| mean ticks | 56.93 | 34.17 | 33.4 | — |
| max ticks | 119 | 62 | 53 | 71 |

**Median match length nearly doubled under ARM G** (54.0 vs 30.5–33.0 across all three baselines/other arms) — this is the single largest behavioral shift measured across all four arms to date and was not reported or compared against a baseline in the runner's raw tally. This is consistent with the steering's explicit "do not fire until in range" and "avoid the open band" instructions producing a longer, more cautious approach phase, but the runner's report did not draw this comparison at all.

## 5. Behavioral read: did steering change red's routing, cover usage, or engagement timing? — NEW independent analysis

The program question is whether the brawler pilot *uses* the steering instructions for actual routing, not just whether outcome moved. Recomputed by joining `movement_resolved` events (`to` position, keyed by `subject.player_id`) against the full 105-cell cover/obstacle set derived directly from `contracts_data/arenas/foundry_60_asym_v2.yaml`'s `rects` (independently re-derived from the arena contract, not copied from any prior doc — cross-checked: 105 cells, matching the cell count both this recomputation and the ARM S doc's live wire-prompt capture independently arrived at), and the y=28–32 band named in the program brief.

| Metric | ARM G (surfacing + steering) | ARM S (surfacing only) | v2 arm-zero (neither) |
|---|---:|---:|---:|
| red `movement_resolved` events | 873 | 449 | 405 |
| red positions landing in a cover cell | **0 (0.0%)** | 0 (0.0%) | 0 (0.0%) |
| red positions in y=28–32 open band | **238 (27.26%)** | 188 (41.9%) | 164 (40.5%) |
| matches with ≥1 red `weapon_fired` | 27/30 | 27/30 | 29/30 |
| red first-shot tick: min/median/mean/max | 14 / 29 / 33.85 / 74 | — / — / 19.3 / — | — / — / 18.6 / — |

Two-proportion z-tests on band occupancy (steering's most literal instruction: "avoid the open y=28–32 band"):

- ARM G vs ARM S: 27.26% vs 41.87%, **z=−5.38** (highly significant, both arms share identical surfacing)
- ARM G vs v2 arm-zero: 27.26% vs 40.49%, **z=−4.74** (highly significant)

**Findings:**

1. **Cover-cell occupancy is unchanged and remains a clean null: 0.0% in all three arms.** The brawler pilot never once lands a movement resolution on one of the 105 obstacle/cover cells, regardless of whether cover data is surfaced (ARM S) or explicitly instructed to be used for routing (ARM G). The steering instruction names `card.movement.flank_left`/`flank_right` as the mechanism for "routing toward and behind" cover cells, and the guidance text itself notes "no movement card places you on an exact coordinate" — so a literal 0% landing rate on cover cells may be structurally near-guaranteed by the movement-card granularity (flank cards move a fixed vector, not to a target cell) rather than by pilot non-compliance. This is a **generation-mechanism confound flagged, not resolved, by this battery**: distinguishing "steering ignored" from "steering followed but the card vocabulary cannot express landing on a specific cell" would require reading `plan_committed.rationale` text or instrumenting flank-card target vectors against the block coordinates directly — out of scope for this battery's aggregate ledger fields.
2. **Exposed-band dwell time dropped sharply and significantly** (41.9%/40.5% → 27.3%), the largest, most statistically confident behavioral change measured in this program to date (z≈−5 against both same-arena comparators). This is consistent with the steering being at least partially followed at the level of the instruction's intent ("avoid the open y=28–32 lane"), even though it does not manifest as literal cover-cell occupancy.
3. **First-shot timing shifted substantially later** (mean 33.85 vs 18.6–19.3 in the two comparators) but roughly proportionally to the near-doubled match length (first-shot-tick ÷ mean-duration ≈ 0.595 for ARM G vs 0.557–0.565 for the comparators) — a modest relative increase, not a disproportionate stall. This is consistent with, not independent confirmation of, the "close before firing" instruction extending the approach phase; the ledger does not directly attribute cause (e.g., distance-to-enemy at time of first fire) without further instrumentation.
4. **Weapon-fired match coverage is flat** (27/30, same as ARM S) — steering did not cause red to withhold fire entirely in any additional match beyond ARM S's own rate.

**Net behavioral read:** ARM G's steering produced a real, measurable, statistically robust change in red's movement pattern (less time in the exposed lane, later first shot, much longer matches) without producing the literal cover-occupancy outcome the instruction describes, and without moving the win/loss outcome at all. The brawler is behaving *more cautiously* under steering — spending more ticks avoiding the open band and delaying engagement — but this caution does not convert into survival or victory; it appears to convert primarily into longer, still-100%-lost matches.

## 6. Prompt-reached-artifact verification — independently re-derived, not re-quoted

The ledger does not durably persist prompt text (`llm_completion_requested` payload carries only `system_prompt_length`/`user_prompt_length`, confirmed by inspecting the `events` table schema and a sample row — no `prompt_text` column exists). To independently verify the guidance text the runner's report quoted was not fabricated or paraphrased, and that it reaches the exact function used at match time, this verification **re-derived the rendered prompt from scratch** using the real production code path (not a re-run of the runner's own capture):

```
programming_system_prompt(
    persona=load_persona(Path("contracts_data/pilots/personas/berserker.yaml")),
    policy_guidance=<programming_guidance field read directly from
                     contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_guided.yaml>,
)
```

using `steel_onslaught.llm.personas.load_persona` and `steel_onslaught.llm.programming.programming_system_prompt` — the identical functions `LLMProgrammingPilot.system_prompt()` calls at match time. The resulting rendered tail is byte-for-byte identical to the runner's report's quoted text and to the `programming_guidance` field's literal YAML content (a `>-` folded block that joins to one paragraph — confirmed by direct inspection of the pilot spec file, not just the rendered output).

**Wiring confirmed independently:** `composition.py`'s `build_card_programmers` (~line 1280–1296) selects `policy_guidance = live_learning_guidance if live_learning_guidance is not None else parameters.programming_guidance`, where `live_learning_guidance = policy_guidance_by_side.get(binding.side) if policy_guidance_by_side is not None else None`. `grep -n "policy_guidance_by_side" scripts/run_ogate_objectives_battery.py` returns **zero matches** — the battery driver never supplies `policy_guidance_by_side`, so `parameters.programming_guidance` (the guided pilot spec's steering block) is unconditionally what red's `LLMProgrammingPilot` receives for this battery. **Confirmed reached, not vacuous.**

**Seat isolation confirmed:** the guided overlay's `programmers` block binds `side: red → pilot_spec_id: pilot.llm.qwen35_berserker_guided`, `side: blue → pilot_spec_id: pilot.llm.qwen35_sniper` (unchanged from ARM S's overlay). `pilot.llm.qwen35` (used by red in both ARM S and v2 arm-zero) carries no `programming_guidance` field at all (confirmed by direct file inspection). The guided overlay is otherwise byte-identical in shape to the ARM S overlay (same arena, deck policy, hand quotas, handler pack, LLM provider config) — the **only** delta between ARM S and ARM G is this one field on red's pilot spec, which is what makes the §3/§5 ARM-G-vs-ARM-S comparisons a clean isolation of the steering-specific effect.

## 7. Merge / additivity verification

- The guided pilot spec and overlay landed in **PR #160** (same PR as ARM S), merged to `main` at `7fb337f1727e555c340026f8e5751fd60673c3d9` (`gh pr view 160`: state MERGED, mergedAt 2026-07-24T15:44:06Z). Config was complete at merge time but unbattery-tested until this run, per the ARM S doc's own "Next lever" note.
- `git diff ebe7e98 7fb337f -- <all ARM-G-relevant contract/source files>` (the SO-PROMPT2 worktree's battery-run commit vs the actual merged `main` commit) is **empty** — the battery ran against code byte-identical to what is on `main`, not a stale or diverged local state.
- The merge commit's own file list (`git show --stat 7fb337f`) shows only new files (`*_guided_qwen.yaml`, `llm_qwen35_berserker_guided.yaml`) plus additive diffs to source/test files (+820/−11 across 13 files); the commit message asserts `pilot.llm.qwen35`, `foundry_60_asym_v2`, `llm_qwen35_berserker_v2.yaml`, and the v2/surfacing overlay are byte-untouched — consistent with the empty diffs already established in the ARM S and v2-arm-zero evidence docs for those same files.

---

## Verdict

**FAILED on outcome** (0/29 decided-match red win rate, `<0.10` band, `play_terminal_fraction=0.9667` clears the trust gate) — ARM G (surfacing + brawler-seat-only tactical steering: route through cover, avoid the open y=28–32 lane, close before firing) did not move the brawler off its 0/30 record, matching the v1 anchor, v2 arm-zero, and ARM S exactly. **Not vacuous**: the steering text is independently re-derived from source and confirmed reaching the exact runtime function via the composition-layer fallback path, with the battery driver confirmed not to override it via the live-learning seam. **Not behaviorally inert either**: this is the largest behavioral shift measured across all prompt-layer arms to date — red's exposed-band dwell time drops from ~41% to ~27% (z≈−5 against both same-arena comparators), first-shot timing shifts substantially later, and median match length nearly doubles (30.5–33.0 → 54.0 ticks) — but red's literal cover-cell occupancy stays at exactly 0.0%, identical to both prior arms, and the win/loss outcome does not move at all. Utility keep-rate also shows a real, asymmetric effect: red's partially recovers toward baseline (relative to ARM S's suppressed rate) while blue's — despite receiving zero steering — drops further, an unexplained cross-seat spillover most plausibly attributable to the ~1.7× longer matches changing both sides' card-programming dynamics.

**Program-level conclusion:** across all measured arms (v1 anchor, v2 arm-zero, ARM S, ARM G), the brawler has never once won on this arena/loadout pairing (0/119 across the four batteries combined at n≈30 each), and none of surfacing, seat-scoped movement/engagement steering, or the underlying arena/loadout re-cut has moved that number. ARM G is the first arm to produce a large, statistically robust *behavioral* change (band-avoidance, engagement delay, match-length near-doubling) without a corresponding *outcome* change — this decouples "the steering instruction is being followed at some level" from "following it is sufficient to win," and sharpens the standing hypothesis from the v2 arm-zero doc: the bottleneck is not (only) missing facts or absent instructions, but something the brawler cannot convert into survival even when it visibly behaves more cautiously. The cover-cell-occupancy null (0.0% in all three prompt arms) combined with the guidance text's own admission that "no movement card places you on an exact coordinate" suggests the next lever is the **card vocabulary itself** (does a movement card exist that can express "go to a specific cover cell," not just a directional flank/advance/retreat vector) rather than further prompt-layer iteration on the current card set — a fifth arm stacking more/different instructions onto the same movement-card vocabulary is unlikely to break the 0/30 record on the evidence gathered so far.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/prompt_guidance_v2_battery/{battery_raw.jsonl,battery_summary.json,events.sqlite3}` (SO-PROMPT2 worktree).
- Behavioral comparison ledgers: `.onex_state/steel_onslaught/prompt_surfacing_v2_battery/events.sqlite3` (ARM S, SO-PROMPT2 worktree); `.onex_state/steel_onslaught/brawler_recut_v2_battery/events.sqlite3` (v2 arm-zero, SO-RECUT worktree).
- Arena cover-cell derivation: `contracts_data/arenas/foundry_60_asym_v2.yaml` (`rects`, independently expanded to a 105-cell set).
- Guided pilot spec: `contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_guided.yaml`. Guided overlay: `contracts_data/overlays/tactical_split_overdeal_utility_asym_v2_guided_qwen.yaml`.
- Prompt-rendering wiring: `src/steel_onslaught/llm/personas.py` (`load_persona`), `src/steel_onslaught/llm/programming.py` (`programming_system_prompt`), `src/steel_onslaught/match/composition.py` (~line 1280–1296, `build_card_programmers`).
- v1 anchor: `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`.
- v2 arm-zero baseline: `docs/evidence/2026-07-24-brawler-recut-v2-battery.md`.
- ARM S: `docs/evidence/2026-07-24-prompt_surfacing_v2-battery.md`.
- Merge commit: `7fb337f1727e555c340026f8e5751fd60673c3d9` (PR #160, `main`); worktree battery-run commit `ebe7e98` confirmed byte-identical to the merge commit for all ARM-G-relevant files.
- No secrets, keys, or absolute paths included.
