---
date: 2026-06-10
status: design-addendum
extends: 2026-04-30-steel-onslaught-design.md
summary: Contract-tunable pilots — expose each archetype's decision thresholds and weights as a bounded, versioned pilot contract that players edit and fork, closing the gap between "player skill is system design" and the MVP's three fixed heuristics, deterministically and before any LLM/learning work.
---

# Steel Onslaught — Contract-Tunable Pilots (Design Addendum)

## 1. Executive Summary

The MVP ships three pilot archetypes (aggressive, defensive, predictive) as hardcoded Python decision trees (MVP plan Tasks 15–17). Players design loadouts; they do not design orchestrators. But the design thesis (§5: "Player skill is system design"; §11: "Pilot is the orchestrator") says the pilot IS the player's system. The MVP gap: the most important system in the game is the one thing the player cannot touch.

Contract-tunable pilots close that gap deterministically, before any LLM or learning work. Every decision threshold and weight in the three archetype heuristics becomes a field in a new contract kind, `steel_onslaught.pilot`. Players edit values within validated bounds, fork specs with explicit lineage parents (§18), and field their tuned pilot via the existing loadout `pilot_id`. Archetypes become canonical templates — specs whose parameter values are exactly the MVP's hardcoded constants — and the heuristic code becomes a pure interpreter of the spec.

Nothing about match physics changes. Tuning moves decision points within safe ranges; it never bypasses heat/pressure physics (§23). Pilots remain pure deterministic functions. Replay guarantees are untouched.

## 2. Relationship to Prior Documents

- **Extends** the 2026-04-30 design (`docs/plans/2026-04-30-steel-onslaught-design.md`). Section references (§N) below point at that document.
- **Depends on** the 2026-04-30 MVP plan (`docs/plans/2026-04-30-steel-onslaught-mvp.md`), all 34 tasks, fully merged from branch `jonah/steel-onslaught-mvp`. The companion implementation plan (`2026-06-10-tunable-pilots-mvp-plan.md`) must not execute before that merge completes.
- **Does not modify or renumber** the MVP plan. The MVP's task numbering, architectural decisions, and determinism contract (MVP Architectural Decisions #6 and #7) are frozen and are cited here as-is.

## 3. Motivation

Observed gap, stated as fact:

- Design §11.5 promises pilot progression improves "decision thresholds, mode-switch timing, heat-risk judgment" — but in the MVP those thresholds are literals inside `src/steel_onslaught/pilots/{aggressive,defensive,predictive}.py`. No progression surface exists.
- Design §18 (lineage and minting) and §19 (learning) both assume a versionable pilot artifact with a parent pointer. The MVP has no such artifact — a pilot is a class name.
- Design §7.1 step 10 is "Refine." For loadouts that works (edit YAML, re-run). For pilots there is nothing to refine.

The fix is the smallest one consistent with the architecture: make the pilot a contract, like everything else in the game already is (chassis §9.4, gizmo §14.3, loadout §15.3, mode transition §16.3). The decision *structure* of each archetype stays fixed and code-owned; the decision *constants* move to a bounded, validated, forkable spec.

## 4. New Contract Kind: `steel_onslaught.pilot`

### 4.1 Schema — `ModelSOPilotSpec`

| Field | Type | Rules |
|---|---|---|
| `schema_version` | `Literal["0.1.0"]` | required |
| `kind` | `Literal["steel_onslaught.pilot"]` | required |
| `id` | `str` | must match `^pilot\.[a-z0-9_]+\.[a-z0-9_]+$` |
| `display_name` | `str` | non-empty |
| `archetype` | `Literal["aggressive", "defensive", "predictive"]` | unknown archetypes rejected at validation |
| `lineage` | `ModelSOPilotLineage` | `{parent: <pilot id> | null}`; `parent`, when present, must match the pilot id regex; `parent == id` (self-parent) is rejected |
| `parameters` | archetype-specific model | `ModelSOAggressivePilotParams` \| `ModelSODefensivePilotParams` \| `ModelSOPredictivePilotParams`; the parameters model MUST match `archetype` (cross-field validation); every field bounded with min/max enforced by Pydantic; unknown fields rejected (`extra="forbid"`) |

All models are frozen (`ConfigDict(frozen=True, extra="forbid")`), consistent with the MVP's contract models. A spec that validates is legal to field; there is no second approval step for tuned values — the bounds ARE the approval.

### 4.2 Template example (shipped, canonical)

`contracts_data/pilots/template_aggressive.yaml`:

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.pilot
id: pilot.template.aggressive
display_name: "Template — Aggressive"
archetype: aggressive
lineage:
  parent: null
parameters:
  vent_at_heat_margin: 5
  idle_vent_heat_threshold: 90
  mode_switch_pressure_floor: 12
  mode_switch_heat_ceiling: 80
  weapon_preference: highest_damage
```

### 4.3 Fork example (player-authored)

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.pilot
id: pilot.player_17.aggressive_hot_v1
display_name: "Hot-Running Aggressive"
archetype: aggressive
lineage:
  parent: pilot.template.aggressive
parameters:
  vent_at_heat_margin: 3        # tolerates heat 2 points closer to rupture than the template
  idle_vent_heat_threshold: 92
  mode_switch_pressure_floor: 14
  mode_switch_heat_ceiling: 84
  weapon_preference: highest_damage
```

The fork is a complete spec, not a diff. Lineage records ancestry; it does not imply inheritance of values.

## 5. Tunable Parameters by Archetype

Parameter names and template values are derived from the MVP plan's heuristic definitions (Tasks 15, 16, 17). Each table cites the exact MVP rule the constant comes from. Bounds are enforced by Pydantic `Field(ge=..., le=...)` on the parameter models.

### 5.1 Aggressive (`ModelSOAggressivePilotParams`) — MVP Task 15

| Parameter | Type | Template value | Bounds | MVP source | Bound rationale |
|---|---|---|---|---|---|
| `vent_at_heat_margin` | int | `5` | 2–20 | Rule 5: "Tolerates redline up to heat == rupture_threshold − 5"; invariants: fires at heat 92/rupture 100, vents at 96/100 | Semantics: the pilot refuses to FIRE and VENTs instead when `heat > rupture_threshold − vent_at_heat_margin` (strict `>`: heat 95 with rupture 100 and margin 5 still fires, matching the MVP invariant pair). Lower bound 2: margin 0–1 lets a pilot fire into its own rupture — death must stay "avoidable in hindsight" (§12) and self-destruction farming is rejected (§23). Upper bound 20: above redline-width the pilot vents through the entire redline band and the archetype stops being aggressive (§11.4 archetype identity). |
| `idle_vent_heat_threshold` | int | `90` | 40–96 | Rule 3: "heat ≥ 90 → VENT" (absolute constant; fires only when no fire/mode-switch rule applies) | This is an *absolute* heat value in the MVP, not rupture-relative (see §5.4). Lower bound 40: a pilot that vents from mid-heat never builds pressure tempo — a stall/draw-farming configuration (§23). Upper bound 96: must remain reachable below the reference rupture threshold of 100 (§10.3) with room for one weapon's heat. |
| `mode_switch_pressure_floor` | int | `12` | 0–60 | Rule 2: "pressure ≥ 12" gate on SWITCH_MODE assault | Template value equals the recon→assault transition pressure cost (§16.3: `costs.pressure: 12`). Floor below the cost is legal — the intent is simply rejected by the mode reducer (MVP Task 23), wasting the decision; the reducer remains the physics gate. Upper bound 60: two-thirds of the largest shipped boiler capacity (industrial bessemer_90, pressure 90 — MVP Task 8); above that the rule can starve permanently. |
| `mode_switch_heat_ceiling` | int | `80` | 0–92 | Rule 2: "heat ≤ 80" gate on SWITCH_MODE assault | Template value equals the reference redline threshold (§10.3). Upper bound 92 equals the mode contract's own `cannot_switch_if_heat_above: 92` (§16.3) — any higher ceiling is unreachable because the mode reducer rejects the intent regardless. The contract gate, not the pilot, is the enforcement point. |
| `weapon_preference` | enum | `highest_damage` | `highest_damage` \| `lowest_heat` | Rule 1: "FIRE highest-damage available weapon"; invariant: equal damage → "deterministically picks the lowest-id alphabetically" | A tiebreak *policy*, not a number. `lowest_heat` selects the ready weapon with the lowest `heat_generated` instead. The final tiebreak (lexicographically lowest weapon id) is FIXED and not tunable — it is the determinism guard from the Task 15 invariant and applies to both policies. |

### 5.2 Defensive (`ModelSODefensivePilotParams`) — MVP Task 16

| Parameter | Type | Template value | Bounds | MVP source | Bound rationale |
|---|---|---|---|---|---|
| `vent_headroom_below_redline` | int | `8` | 0–40 | Rule 1: "heat ≥ redline_threshold − 8 → VENT"; invariant: heat 73 of redline 80 vents | Redline-relative, as in the MVP. Lower bound 0: venting exactly at redline is the least cautious legal defensive pilot. Upper bound 40: half the reference heat scale — beyond that the pilot is permanently venting, a stall/draw-farming configuration (§23). |
| `fire_confidence_floor` | float | *landed constant* (see §5.4) | 0.4–0.95 | Rule 3: "high-confidence target"; invariants: does NOT fire at confidence 0.4, DOES fire at 0.8 | The MVP plan does not pin this constant — the invariants bound it to the interval (0.4, 0.8]. The template MUST copy the constant verbatim from the merged `src/steel_onslaught/pilots/defensive.py` (implementation plan Task 3 Step 1 reads it; the golden test then enforces it mechanically). Lower bound 0.4: firing below the MVP's own "low confidence" test point erases the archetype's defining trait (§11.4: defensive does not waste heat on uncertain shots). Upper bound 0.95: above sensor-precision ceilings the pilot effectively never fires — draw farming (§23). |
| `fire_heat_headroom` | int | `12` | 0–40 | Rule 3: "heat headroom ≥ 12" gate on FIRE | Semantics: fire only when `redline_threshold − heat ≥ fire_heat_headroom` (the defensive archetype's reference line is redline, never rupture — §11.4 "avoids redline"). Lower bound 0: firing right up to redline is legal. Upper bound 40: same stall rationale as `vent_headroom_below_redline`. |
| `disengage_hp_pct` | int | `30` | 0–60 | Rule 4: "hp_percent < 30 → DISENGAGE"; invariant: hp 25 disengages | Lower bound 0 disables disengagement entirely (a legal, brawlier defensive). Upper bound 60: a pilot that flees above 60% hp concedes the match by attrition and farms draws (§23). |

### 5.3 Predictive (`ModelSOPredictivePilotParams`) — MVP Task 17

| Parameter | Type | Template value | Bounds | MVP source | Bound rationale |
|---|---|---|---|---|---|
| `lock_confidence_floor` | float | `0.65` | 0.3–0.95 | Rule 3: "lock_confidence ≥ 0.65"; invariants: holds at 0.5, fires at 0.7 | Lower bound 0.3: below long-range radar's base precision 0.6 degraded by jamming there is no meaningful lock — firing on noise is chaos, not prediction (§11.4 weakness becomes the whole pilot). Upper bound 0.95: never-fire / draw-farming cap (§23). |
| `predicted_hit_floor` | float | `0.55` | 0.2–0.95 | Rule 3: "predicted_hit_probability ≥ 0.55"; invariant: fires at predicted hit 0.6 | Lower bound 0.2: below that the pilot sprays — pressure waste is self-defeating but legal down to a floor that keeps the archetype recognizable. Upper bound 0.95: never-fire cap (§23). |
| `preemptive_vent_headroom` | int | `5` | 0–30 | Rule 4: "heat ≥ redline_threshold − 5 → VENT preemptively" | Redline-relative, matching the MVP. Lower bound 0: venting at redline exactly. Upper bound 30: permanent-vent stall cap (§23). |
| `regen_pressure_floor` | int | `30` | 0–60 | Rule 5: "pressure < 30 AND no immediate threat → MOVE to defensive position to regen" | Lower bound 0 disables regen repositioning. Upper bound 60: two-thirds of the largest shipped boiler — above that the pilot camps regen permanently (stall, §23). |

**Not tunable (structural, fixed):** the predictive lookahead window (linear extrapolation of the last 3 observations, MVP Task 17 rule 1) is part of the archetype's decision *structure*, not a threshold. Changing it changes the algorithm, not a decision point. It stays code-owned. The same applies to rule ordering within every archetype: the decision tree shape is frozen; only the constants the tree compares against are tunable.

### 5.4 Derivation notes (deviations from the parameter sketch)

These are the places where the MVP plan's actual text forced a deviation from the one-line parameter sketch this addendum was commissioned with:

1. **Aggressive vent behavior is TWO constants, not one.** MVP Task 15 contains both a rupture-relative tolerance (rule 5: `rupture_threshold − 5`, pinned by the fires-at-92 / vents-at-96 invariant pair) and an absolute standing vent trigger (rule 3: `heat ≥ 90`, consulted only when no fire/switch rule applies). A single `vent_at_heat_margin` cannot reproduce both. This addendum models both: `vent_at_heat_margin` (rupture-relative, template value 5) and `idle_vent_heat_threshold` (absolute, template value 90). Re-expressing the absolute 90 as "rupture − 10" was rejected: it is only equivalent when `rupture_threshold == 100`, and the MVP plan does not pin the rupture thresholds of the compact and volatile boilers. An absolute parameter is the only form that is decision-identical to the hardcoded literal on *any* observation, which the golden test (§6) requires.
2. **Defensive `fire_confidence_floor` is unpinned in the MVP plan.** Task 16's invariants establish only that the pilot holds at confidence 0.4 and fires at 0.8 — the constant lies in (0.4, 0.8] and the plan never states it. The template value is therefore defined as "whatever constant the merged implementation contains", read at implementation time and locked in by the golden test. This addendum deliberately does not invent a number.
3. **`weapon_preference` tiebreak is split from the policy.** The MVP invariant fixes lowest-id-alphabetical as the equal-score tiebreak. That tiebreak is preserved as a non-tunable invariant under both `highest_damage` and `lowest_heat`; only the primary sort key is player-tunable.

## 6. Canonical Templates and the Golden Behavioral Invariant

Three template specs ship under `contracts_data/pilots/`:

- `contracts_data/pilots/template_aggressive.yaml` — `pilot.template.aggressive`
- `contracts_data/pilots/template_defensive.yaml` — `pilot.template.defensive`
- `contracts_data/pilots/template_predictive.yaml` — `pilot.template.predictive`

All three have `lineage.parent: null`. They are the only specs permitted to have a null parent (§8). Their parameter values are exactly the MVP's hardcoded constants — not approximately, not "rebalanced while we're here."

**The golden behavioral invariant:** an archetype constructed from its template spec is decision-for-decision identical to the MVP's hardcoded version on any observation. Concretely, for every observation in a committed fixture battery (and the battery spans the full decision tree: every rule branch, every boundary value from the MVP invariants, all three shipped boilers), `spec_pilot.decide(obs) == hardcoded_pilot.decide(obs)` with full `ModelSOPilotDecision` equality — action, action_params, reason_code, confidence, and `considered_actions` scores.

**Consequence for Proof of Life:** the seed-12345 PoL duel (MVP Task 34) produces an identical ledger before and after this change. "Identical" is scoped by the MVP's own determinism contract (Architectural Decisions #6 and #7): identical canonical event sequence — `(tick, sequence_in_tick, event_type, producer_node, subject, payload)` byte-identical in canonical order — with `event_id` (a ULID, uniqueness-only per Decision #7) and `emitted_at` (metadata-only per Decision #7) excluded, exactly as the MVP excludes them. CLI replay output remains byte-identical per the Task 28 invariant. Both PoL tests re-run unchanged and green. No event payload gains, loses, or reorders a field anywhere in this work — spec audit embedding in `match_started` was considered and deferred (§10) precisely to keep this invariant strict.

## 7. Loadout Integration

The loadout contract (§15.3) already carries `pilot_id`. This addendum gives that field a resolution rule instead of a hardcoded class mapping:

1. If the loadout's optional new field `pilot_spec_path` is present, load and validate the spec from that path (relative to the loadout file's directory). The loaded spec's `id` MUST equal the loadout's `pilot_id`; mismatch is a load-time error. Player-supplied specs resolved this way MUST have a non-null `lineage.parent` (§8).
2. Otherwise, resolve `pilot_id` against the registry built from `contracts_data/pilots/*.yaml` (keyed by spec `id`).
3. Otherwise, fall back to the MVP's existing archetype resolution, constructing the archetype from its canonical template spec. This keeps the four PoL loadout YAMLs and both PoL tests byte-unchanged.

**Budget axes are unchanged for now.** A pilot spec contributes zero mass, slots, pressure draw, heat, and signature to the multi-axis budget validator (MVP Task 13). The design's decision-latency cost axis (§13 "decision latency", §22 "decision latency" scoring term) is the natural place for tuned pilots to eventually pay a cost — e.g., wider deviation from template = higher latency — but that is explicitly future work and out of scope here. Stated plainly: in this addendum, tuning is free along every budget axis.

## 8. Lineage Tie-In (§18 on-ramp)

- Every fork MUST name a `lineage.parent` that is a valid pilot id. The three shipped templates are the only null-parent specs; a repo test asserts this for everything under `contracts_data/pilots/`, and the loadout resolver rejects player-supplied null-parent specs (§7 rule 1).
- Self-parenting is rejected at validation. Cycle detection across a spec *population* is a minting-time concern (§18), not a single-spec validation concern, and is future work.
- This is deliberately the on-ramp to §18 minting: a minted pilot needs "a clear lineage parent" and "replayable match evidence" — tunable specs provide the former natively, and every match a tuned spec plays already produces the latter (the ledger). The §18 trivial-clone rejection maps directly: a fork whose parameters equal its parent's is a trivial clone.
- It is equally the on-ramp to the §19 learning loop: candidate generation becomes parameter search over the bounded spec space — generate a candidate spec inside bounds, run it against its parent per §19's promotion pipeline, promote or reject. The learning system never needs a new artifact type. This too is future work; nothing in this addendum executes a search.

## 9. Bounds Enforcement and Anti-Exploit (§23)

Two independent gates, by design:

1. **Contract gate (new):** Pydantic bounds on every parameter. Out-of-bounds values never construct a spec; there is no warn-and-clamp, no "soft" range. A spec that fails validation cannot be fielded.
2. **Physics gate (existing, unchanged):** every pilot decision is still an *intent* (MVP Tasks 21/23/24). The mode reducer still rejects switches that violate the mode contract; the weapon reducer still rejects fires without pressure; the boiler reducer still owns heat and rupture. A tuned pilot can be configured to *attempt* foolish things (e.g., a pressure floor below the transition cost) — the attempt wastes the decision and the reducer drops it. Tuning can never bypass heat/pressure physics, mutate opponent state, or touch reducer truth, because pilots never could (§4.2).

Bounds therefore serve a narrower purpose than the reducers: they keep every legal spec inside the archetype's identity (§11.4) and outside the degenerate-strategy space §23 names — never-fire draw farming, permanent-vent stalling, fire-into-rupture self-damage farming. The upper/lower bound rationales in §5 each cite the specific §23 exploit they exclude.

## 10. Determinism

- Pilots remain pure functions of `(observation, spec)`. The spec is loaded once at match start and is immutable (frozen model) for the match's duration.
- No new RNG. No spec parameter introduces randomness; `MatchRng` usage is untouched.
- Replay guarantees are untouched. Replay reconstructs state by folding ledger events through reducers (MVP Task 27); it never re-executes pilots, so it is indifferent to how a decision was produced. Decision events already record the full decision (MVP Task 21).
- No event schema or payload changes (§6). Embedding the resolved spec in the `match_started` payload as §18 audit evidence was considered and **deferred**: it would change PoL ledger payloads and break the before/after ledger-identity invariant. It belongs in the future minting work.

## 11. Non-Goals

- No LLM pilots, no learned policies, no parameter search execution (§19 remains future work; this addendum only makes its search space well-defined).
- No new archetypes (opportunistic and swarm commander remain post-MVP, §11.4).
- No decision-latency budget costs for tuned pilots (§7 — future work).
- No minting, promotion, or hidden-evaluation enforcement (§18/§23.1 — future work; this addendum supplies the artifact they will govern).
- No rebalancing of template values. Templates are transcriptions of the MVP constants, byte-for-byte where the MVP pins them.
