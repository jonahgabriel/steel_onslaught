# U-GATE + O-GATE Combined Battery — ASYM arena + utility counterplay (2026-07-23)

- **Verdict:** U-GATE **FAIL** (keep-rate criterion); O-GATE re-measure **negative** — brawler still does not contest VP.
- **Overlay:** `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_qwen.yaml` (PR #137) · arena `foundry_60_asym_v1` · `vp_threshold=15` · seeds 5001–5030 · deal 10 (4 mv + 4 wpn + 2 util), program 5.
- **Model:** live Qwen3.6-35B-A3B @ `omninode-pc.tail75df5e.ts.net:8000/v1` (keyless), n=30, `all_replay_valid=true`.
- **Ledger (baseline-retained):** `.onex_state/steel_onslaught/ugate_asym_utility_battery/{events,leaderboard}.sqlite3` in the SO-UGATE-ASYM worktree.
- **Design basis:** `docs/design/2026-07-22-unified-depth-learning-design.md` §5.
- All figures below are independently recomputed by an adversarial analyst from the raw sqlite ledgers, NOT copied from the battery agent's report.

## Negatives first

1. **Utility keep-rate is far below chance — U-GATE fails.** chance = register_count 5 ÷ hand 10 = 0.50.
   - red (brawler): 7 utility programmed / 406 dealt = **0.0172**
   - blue (sniper): 23 / 406 = **0.0567**
   - Overall keep-rate (all card types) is exactly 0.50 for both seats (1015/2030) — pilots keep cards at chance in aggregate but *systematically dump* utility specifically.
   Query: parse `plan_committed.registers[].card_id` (programmed) and `hand_dealt.card_ids` (dealt), filter `card.utility.*`, per seat.

2. **The brawler still cannot contest VP.** No match reached the 15-VP threshold; every terminal was elimination.
   - VP-threshold terminals: **0/30**; max cumulative VP any side: **7** (red) / 3 (blue).
   - Brawler scored any objective in **3/30** matches (prior baseline: 0/30); sniper in 2/30.
   - Total objective awards red/blue = 16/4.
   - Winner side: **blue (sniper) 30 / red 0 / draw 0**; brawler win-rate **0/30**.
   - Elimination outran VP accrual in all 30 matches (median 31 ticks, min 17 / max 71).

3. **Report sub-count error (flagged for the record):** the battery report cited `weapon_fire_rejected` as 185/68/1; actual ledger counts are **389 out_of_range / 113 cooldown / 5 insufficient_pressure = 507**. Qualitative claim (all legal rejections, no coherence failure) is unaffected.

## Positives / mechanism-proven

- **The utility fold bites where it deploys.** Of 207 sniper (blue) shots, the 4 fired while smoke was active on the line all had hit_probability = 0.000 (0 hits); the 203 fired without active smoke had mean hit_prob 0.393 and 83 hits (0.409). Smoke → aimed-hit-rate 0 is real and replay-reproducible (window [T..T+dur-1], duration_ticks=2). Flares (12) and chaff (3) also deploy and consult the resolver.
- **No coherence regression on aborts:** 0 terminal-class aborts, 0 invalid-action/plan rejections. (10 `llm_completion_failed` across 7 matches were tolerated; none aborted a match.)
- **No balance knob touched:** utility effect expressed only through LOS/lock/targeting consults; no damage/evasion/range number changed; arenas byte-frozen.

## Comparison to prior O-GATE baseline (2026-07-22, non-utility ASYM)

| Metric | This battery | Prior baseline |
|---|---|---|
| VP-threshold terminals | 0/30 | 0/30 |
| Max VP any side | 7 (red) | 8 |
| Brawler scored any VP | 3/30 | 0/30 |
| Brawler win-rate | 0/30 | 0/30 |
| Winner side | blue 30 / red 0 | blue 30 / red 0 |

Net: adding utility counterplay to hand produced a marginal draft-layer signal (brawler now scores an objective in 3/30) but did **not** change the outcome — sniper still wins 30/30 and no match reaches VP threshold.

## Recomputed-figure query index

- Terminals: `SELECT json_extract(payload_json,'$.victory_kind'),json_extract(payload_json,'$.reason'),COUNT(*) FROM events WHERE event_type='victory_declared' GROUP BY 1,2`
- VP per match: `SELECT match_id, MAX(json_extract(payload_json,'$.cumulative_vp."player.red"')), MAX(json_extract(payload_json,'$.cumulative_vp."player.blue"')) FROM events WHERE event_type='objective_scored' GROUP BY match_id`  (dotted seat key MUST be double-quoted in the JSON path, else it silently returns NULL)
- Winner side: `SELECT winner_player_id,COUNT(*) FROM leaderboard_entries GROUP BY 1` (leaderboard.sqlite3)
- Deploys: `SELECT json_extract(payload_json,'$.utility_kind'),COUNT(*) FROM events WHERE event_type='utility_deployed' GROUP BY 1`
- Sniper hits: `SELECT json_extract(payload_json,'$.result.hit'),COUNT(*) FROM events WHERE event_type='hit_resolved' AND json_extract(payload_json,'$.attacker_id')='mech.blue.01' GROUP BY 1`
- Smoke-window overlap: Python join of `utility_deployed`(smoke) ticks to blue `weapon_fired` ticks within [T, T+duration_ticks-1] per match.

## Conclusion / next step

Utility counterplay does not open the objective mode for the brawler. Two independent blockers are proven: (1) pilots draft utility at ~2–6% keep-rate (below chance), so it almost never deploys; (2) even in the 3/30 matches that contested an objective, elimination fired before VP passed 7/15. Two candidate next steps: an **objective-placement / VP-pacing re-cut** (contested control must convert to a threshold win before the sniper eliminates), or a **cross-model probe** of the draft-layer finding (is the ~2–6% utility keep-rate qwen35-specific or general?). U-GATE remains FAILED on keep-rate; O-GATE outcome (sniper 30/0) is unchanged from the prior baseline.
