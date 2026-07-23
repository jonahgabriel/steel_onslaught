# L-GATE-2 before/after adaptation battery — 2026-07-22

Gate question (design `docs/design/2026-07-22-unified-depth-learning-design.md`
§5, speculation register item 3): **does a promotion change a later live
decision, auditably?** Two claims are separable and are graded separately
below: (a) the *audit chain* — the next match verifiably flies the promoted
policy; (b) the *behavioral shift* — next-match selection metrics move in the
parameterized direction.

## Method

- Code under test: the L-GATE-2 branch (`feat/so-lgate2-policy-consumption`,
  rebased on `main` @ `855da9c`): per-seat `MATCH_STARTED` policy provenance,
  the policy-guidance prompt block, and the live-learning wiring from #123.
- Driver: `scripts/run_lgate2_adaptation_battery.py` (committed with this
  branch) — headless `assemble_match_live`, the identical composition path as
  the #124 abort battery. Overlay
  `contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml` with a
  battery-lane storage override and a `live_learning` binding
  (`win_damage_differential_v1`, archetype `aggressive`, learning seat
  `player.blue` — the sniper, the seat that wins — genesis
  `{aggression: 1.0}`, step `0.25`). Keyless Qwen3.6-35B-A3B (endpoint
  confirmed live via `/v1/models` before launch), red berserker vs blue
  sniper loadouts, sudden-death (`max_ticks=None`).
- Three phases over ONE durable lane (shared ledger + lineage store, so the
  promotion chain carries across phases exactly as across production
  processes; every match rehydrates its policy from the durable chain):
  1. **baseline** (seeds 4001–4010, n=10): evaluator capped at
     `max_value=1.0` so promotion is impossible — every match flies the
     generation-0 policy *with* its guidance block (`aggression 1.0`).
  2. **promote** (seed 4101): cap lifted (`max_value=3.0`) — the first match
     promoted (blue decisive win + positive damage differential).
  3. **post** (seeds 4201–4210, n=10): cap re-pinned at `max_value=1.25` so
     the chain freezes at generation 1 — every match flies the promoted
     policy (`aggression 1.25`).
- Metrics: read from the canonical event ledger per match — the #117
  instruments (per-category keep-rates = planned/dealt, category planned
  share for the blue seat) plus provenance, terminals, and per-player
  `replay_validity` from `MATCH_SCORED`. Raw rows:
  `.onex_state/steel_onslaught/lgate2_adaptation_battery/battery_raw.jsonl`
  (battery lane, not committed); summary `battery_summary.json` beside it.

## Result (a): the audit chain — VERIFIED

- **Promotion event:** `POLICY_PROMOTED` on the promoting match's stream
  (match `match.01KY68VBS8RN7ED3F7ZW4VKETG`, `evidence_scored_event_id`
  `01KY68VSVH611XN8RC70XZ3XPG`), generation 1,
  `policy_id policy.aggressive.72c1f2d94b4ad1a9`,
  `parent_spec_hash 04d58538…` (the genesis hash),
  `spec_hash 72c1f2d9…`, `source_lineage_digest 753e7466…`.
- **Lineage record:** the digest resolves to the persisted record on disk;
  the rehydration path re-verifies digest + spec/parent hashes on every
  subsequent composition (fail-closed loader).
- **Provenance flip:** all 10 baseline matches carry
  `{policy.aggressive.genesis, generation 0, digest null}`; all 10 post
  matches carry `{policy.aggressive.72c1f2d94b4ad1a9, generation 1,
  digest 753e7466…}` — byte-equal to the promotion event's identifiers
  (asserted per-match by the driver).
- **Prompt consumption:** the guidance block is a pure function of the policy
  (`policy_id`/`spec_hash` pin its bytes); the cross-boundary regression
  test asserts the wire system prompt for the same seams, and the post-phase
  block differs exactly in `aggression 1.0 -> 1.25`.
- **Replay:** 21/21 matches `replay_validity=1` for both players; 21/21 real
  gameplay terminals (`last_mech_standing`), zero draws, zero aborts.

Every element of the gate's chain (provenance -> `POLICY_PROMOTED` ->
lineage -> replay) is machine-checked by the driver, not eyeballed.

## Result (b): the behavioral shift — DIRECTIONALLY CONSISTENT BUT WEAK

Blue-seat selection metrics, baseline (gen-0, aggression 1.0) vs post
(gen-1, aggression 1.25), n=10 each; Welch t on per-match values:

| Metric | Baseline | Post | Δ | t | In direction? |
|---|---|---|---|---|---|
| attack keep-rate | 0.997 | 1.000 | +0.003 | — | ceiling (no headroom) |
| movement keep-rate | 0.494 | 0.472 | −0.022 | −1.20 | yes (movement down) |
| special keep-rate | 0.611 | 0.652 | +0.041 | 0.72 | yes (weapon-pile up) |
| vent keep-rate | 0.000 | 0.083 | +0.083 | 3.15 | **no** (vent up) |
| weapon-pile planned share (attack+special+vent) | 0.605 | 0.622 | +0.018 | 1.20 | yes |

**Honest reading.** The movement-vs-weapon axis moved the way the parameter
asks (less movement kept, more weapon-pile share) but the deltas are ~2 pp
and none is significant at n=10 (per-match variance is the same order as the
shift). Two structural reasons cap the effect: (1) the genesis sniper
already keeps essentially every dealt attack card (0.997), so the primary
axis is ceilinged before learning starts; (2) Δaggression = one step (0.25
on a 0–3 scale) is a deliberately small perturbation. The one significant
mover (vent keep 0 -> 0.083) is *against* the naive direction. Per the gate's
own fail semantics this is a **reported finding, not a hidden failure**: the
"auditably" half of L-GATE-2 is proven; the "changes a decision" half is
established for the *prompt input* (byte-verified) and only weakly for the
*measured selection distribution* at this step size on this seat.

## Residuals (honest)

1. **Effect size, not absence of effect, is the open question.** A larger
   step (e.g. genesis 0.5 vs promoted 2.5), a seat with headroom (the
   berserker), or n≥30 per phase would resolve direction vs noise. The
   committed driver re-runs any of these unchanged.
2. **Two `llm_completion_failed` events in baseline** (seeds 4004/4009, one
   each) were recovered by the bounded repair loop — 0 aborts, all plans
   landed. Post phase had zero. Consistent with #124's distributional bound.
3. **Balance unchanged:** blue won 21/21 (the known sniper dominance —
   balance lane, not this gate).
4. The win_damage evaluator lane (not the duel-gated
   `SelectionOutcomeEvaluator`) produced the promotion; the duel-gated lane
   is exercised by its own unit suite and remains to be run live.
