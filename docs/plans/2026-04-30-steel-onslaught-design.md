---
date: 2026-04-30
status: design
summary: Steel Onslaught — steampunk tactical mech battle game built as a deterministic, event-sourced, replayable, contract-driven OmniNode-native contest framework where pilots are orchestrators and the UI is an effect node.
---

# Steel Onslaught — Game Design

## 1. Executive Summary

Steel Onslaught is a steampunk tactical mech battle game built as an OmniNode-native contest system. On the surface, it is a game about programmable steam-powered war machines fighting in arenas. Under the surface, it is a deterministic, event-sourced, replayable agent competition framework.

Core abstraction: players design constrained mech systems. Pilots are orchestrators. Chassis, boilers, modules, gizmos, and modes define the available action space. Every decision, state transition, heat change, shot, failure, victory, replay, and learning trace flows through the event bus. The UI is not the game engine — it is an effect node that renders projections of the event stream.

## 2. Design Thesis

Implemented as a deterministic event stream with one or more visual projections, not a game with logs attached.

- The event bus is the source of truth.
- Reducers own canonical state.
- Effects render, notify, persist, or bridge.
- The UI never decides match truth.
- Every match must be replayable from events.
- Every learning update must be traceable to match evidence.
- Every balance-relevant rule must be versioned.

The visible product is a game. The strategic product is an agent-evaluation arena.

## 3. Core OmniNode Mapping

| Steel Onslaught | OmniNode |
|---|---|
| Match | Event-sourced workflow instance |
| Arena | Scenario contract |
| Mech | Composed node graph |
| Chassis | Execution envelope |
| Boiler | Runtime resource state |
| Pilot | Orchestrator node |
| Modules | Reducers, effects, handlers, adapters |
| Weapons | Effect-producing action modules |
| Sensors | Observation adapters |
| Armor | Constraint modifier |
| Gizmos | Bounded contract transformers |
| Mode | Runtime configuration profile |
| Mode switch | Contract graph transition |
| Damage | Reducer-governed state transition |
| Pilot death | Terminal orchestrator-instance loss |
| Replay | Ledger reconstruction |
| Spectator view | UI effect projection |
| Learning | Offline candidate policy generation |
| Lineage | Versioned policy/build ancestry |

## 4. Non-Negotiable Architecture Rules

### 4.1 Event Bus First

Every meaningful action must be emitted as an event. Required event classes: match lifecycle, arena initialization, mech spawn, sensor observation, pilot decision, module activation, boiler pressure, heat, mode transition, weapon discharge, hit resolution, damage, armor response, overload warning, boiler rupture, pilot injury/death, victory/defeat, replay checkpoint, learning trace, candidate policy evaluation, policy promotion/rejection.

### 4.2 Reducers Own Truth

Reducers decide canonical state transitions. Effects render/notify/persist/bridge but do not decide truth. Effects may NOT decide hits, mutate health, alter boiler state, grant victory, override pilot decisions, or mutate learning outcomes.

### 4.3 UI Is an Effect Node

UI subscribes to events and renders projections. Player intent enters as events. UI may not mutate canonical state. Valid projections: tactical board, animated battle view, replay viewer, debug trace, tournament viewer, leaderboard, pilot decision inspector, lineage explorer, balance dashboard.

### 4.4 Replay Is Mandatory

A match is valid only if it can be reconstructed from its event ledger. State that cannot be reconstructed is invalid state.

### 4.5 Learning Is Gated

Live matches collect traces. Live matches do not mutate active production pilots directly. Learning creates candidate variants. Variants are promoted only after evaluation.

## 5. Game Premise

Steampunk industrial war league. Each mech: chassis, boiler, pilot orchestrator, weapons, sensors, armor, mobility, gizmos, modes. The pilot decides based on sensor data, boiler pressure, heat state, weapon cooldowns, enemy proximity, mission objective, active mode, learned policy, risk constraints. Player skill is system design.

## 6. Design Goals

Reward: planning, adaptation, heat management, constrained optimization, good pilot design, good module composition, timing, risk control.
Do not reward: stat stacking, pay-to-win, unrestricted re-spec, plugin stacking, brute-force compute, meta copying.
Demonstrate: event sourcing, contract-driven workflows, reducer ownership, orchestrator decision policy, effect-node rendering, replay, lineage versioning, runtime constraints, policy learning.
Progression unlocks options, not raw power.

## 7. Core Loops

### 7.1 Player Loop
1. Choose chassis. 2. Choose boiler. 3. Choose pilot. 4. Assign modules. 5. Define modes. 6. Enter match. 7. Watch projection. 8. Review replay. 9. Inspect decisions. 10. Refine. 11. Run again.

### 7.2 Competitive Loop
Submit build → validate contracts → run match → score → rank → publish replay → update leaderboard → extract traces → mint qualifying variants.

### 7.3 Learning Loop
Collect traces → isolate decision points → attribute outcomes → generate candidates → validate on fixed and hidden scenarios → compare to parent → reject or promote → emit versioned promotion event.

## 8. Match Types

- **8.1 Duel** — 1v1. **MVP target.**
- **8.2 Squad Battle** — multi-mech sides.
- **8.3 Tournament** — bracketed.
- **8.4 Continuous Arena** — open-ended evaluation.
- **8.5 Scenario Challenge** — fixed scenario (artillery barrage, swarm, escort, sensor jamming, fog).

## 9. Chassis System

Chassis define mass capacity, module slots, boiler size, speed, turn rate, armor limit, sensor compatibility, weapon compatibility, signature, heat dissipation, mode-switch latency.

### 9.1 Light
Strengths: mobility, low signature, harder to hit, fast venting, fast mode transitions.
Weaknesses: low mass, small boiler, limited heavy weapons, fragile.
Roles: scout, skirmisher, flanker, sensor platform, heat harasser.

### 9.2 Medium
Strengths: balanced capacity, flexible loadout, moderate boiler, viable across roles.
Weaknesses: not dominant at extremes, vulnerable to specialized counters.
Roles: hunter-killer, flexible assault, anti-scout, support fighter.

### 9.3 Heavy
Strengths: high mass, large boiler, heavy weapon compat, thick armor, high burst.
Weaknesses: slow, large signature, slow venting, vulnerable to heat weapons, slow mode transitions.
Roles: artillery, siege, anchor, heavy brawler.

### 9.4 Example Contract

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.chassis
id: chassis.heavy.ironclad_mk1
display_name: "Ironclad Mk I"
class: heavy

constraints:
  max_mass: 120
  max_module_slots: 8
  max_boiler_volume: 90
  base_speed: 2
  base_turn_rate: 1
  base_signature: 85
  base_vent_rate: 4

compatibility:
  weapon_classes: [medium, heavy, siege]
  boiler_classes: [industrial, volatile, twin]
  mobility_classes: [tracked, reinforced_tracked]

penalties:
  mode_switch_latency_modifier: 1.35
  sensor_lock_penalty: 1.2
  heat_weapon_vulnerability: 1.25
```

## 10. Boiler System

Core tempo economy. Governs steam pressure, heat, weapon activation, movement bursts, sensor use, mode switching, venting, overload, rupture.

### 10.1 Attributes
pressure capacity, regeneration rate, heat capacity, heat multiplier, vent rate, redline threshold, rupture threshold, instability curve, repairability, mass, compatibility.

### 10.2 Types

- **Compact** — fast regen, fast venting, low rupture; low peak, poor heavy support. Scouts/light skirmishers.
- **Industrial** — high capacity, heavy weapon support, sustained output; slow venting, slow recovery, poor emergency. Artillery/siege.
- **Volatile** — huge burst, rapid spikes, ambush; high rupture, unstable, vulnerable to heat. Aggressive/burst.
- **Efficient** — low heat, stability, endurance; weak peak, limited burst. Defensive/attrition.
- **Twin** — redundancy, vent-while-power; high mass, coordination penalty, possible desync. Advanced/multi-mode.

### 10.3 Boiler State Contract

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.boiler_state
match_id: match.2026-04-30.001
mech_id: mech.red.01
tick: 142

pressure: { current: 64, maximum: 90, regeneration_per_tick: 5 }
heat: { current: 72, redline_threshold: 80, rupture_threshold: 100, vent_rate: 4 }
status: { redline: false, rupture_warning: false, disabled: false, ruptured: false }
modifiers: { heat_weapon_pressure: 1.15, venting_penalty: 0.0, mode_switch_heat_delta: 8 }
```

### 10.4 Failure States

- **Redline** — heat above redline. Warning event, accuracy degrades, mode switching risky, rupture probability rises.
- **Overload** — sustained redline or pressure spike. Possible shutdown, module damage, forced venting, lost action window.
- **Rupture** — rupture threshold exceeded. Possible explosion, mech destruction, area damage, pilot death. Terminal.

## 11. Pilot System

Pilot is the orchestrator. Decision policy controlling a constrained mech.

### 11.1 Responsibilities
move (when/where), fire (when/what), vent, redline, disengage, switch modes, sensor priority, steam spending, response to enemy.

### 11.2 Inputs
sensor observations, boiler/heat state, module cooldowns, current mode, chassis constraints, enemy estimates, objective, terrain, prior opponent behavior, match rules.

### 11.3 Outputs
movement, weapon activation, module activation, vent, mode switch, target priority, defensive posture, emergency shutdown.

### 11.4 Archetypes

- **Aggressive** — fires early, closes distance, tolerates heat, redlines often. Weak: prone to traps, vulnerable to heat weapons, poor disengagement.
- **Defensive** — vents early, avoids redline, prioritizes survival, disengages well. Weak: lower damage, may surrender initiative.
- **Predictive** — waits for target confidence, future-state estimation, optimizes positioning. Weak: higher latency, vulnerable to chaotic opponents.
- **Opportunistic** — exploits enemy state transitions (vent, mode switch). Weak: depends on sensors, may underperform without openings.
- **Swarm Commander** — coordinates light units, prioritizes coverage. Weak: coordination overhead, poor unit durability.

### 11.5 Progression
Improves: decision thresholds, mode-switch timing, heat-risk judgment, target prioritization, retreat discipline, sensor interpretation, scenario adaptation.
Does not grant: flat damage/health/accuracy bonuses, unavoidable stat superiority.

## 12. Pilot Death and Injury

States: healthy → shaken → injured → critically injured → dead.
Causes: boiler rupture, cockpit hit, catastrophic chassis damage, repeated overload shock, failed emergency venting, ammunition cook-off.
Death must be: rare, causally explainable, replay-visible, avoidable in hindsight.

## 13. Module System

Categories: weapons, sensors, armor, mobility, cooling, boiler control, command, disruption, safety.
Costs per module: mass, slot, pressure draw, heat generation, cooldown, signature delta, decision latency, compatibility limits.

### 13.2 Weapons
machine gun, steam cannon, artillery mortar, heat lance, grappling harpoon, pressure torpedo, shrapnel thrower.
Attrs: range, damage, pressure cost, heat generated, cooldown, accuracy curve, target class effectiveness, compatibility.

### 13.3 Sensors
long-range radar, short-range proximity scanner, thermal scope, acoustic detector, smoke-penetrating optics, pressure-trail detector.
Attrs: range, precision, latency, pressure draw, heat generation, signature impact, jamming vulnerability.

### 13.4 Cooling
auxiliary vent, emergency condenser, heat sink lattice, pressure dump valve, water-injection cooler.

### 13.5 Disruption
heat injector, sensor jammer, false-signature projector, pressure destabilizer, smoke boiler.

## 14. Gizmo and Plugin System

Gizmos are bounded contract transformers, not arbitrary rule overrides.

Categories:
- **Efficiency** — reduce pressure cost / heat / improve venting; trade lower peak / longer cooldown / reduced burst.
- **Amplifier** — increase output / fire rate / burst; trade heat spikes / instability / pressure drain.
- **Control** — improve targeting / pathing / mode timing; trade decision latency / compute / sensor dependence.
- **Disruption** — jam sensors / inject heat / spoof signatures; trade weak damage / high signature / counter-vulnerability.
- **Safety** — prevent rupture / force venting / dampen overload; trade ceiling / forced shutdown / slot consumption.

Gizmos must NOT: bypass heat/pressure/mass/slots, grant victory, mutate opponent state without events, create invisible state, overwrite reducers, ignore replay.

### 14.3 Example Gizmo Contract

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.gizmo
id: gizmo.cooling.emergency_condenser
display_name: "Emergency Condenser"
category: safety

constraints:
  mass: 8
  slots: 1
  compatible_chassis: [medium, heavy]

effects:
  on_redline:
    vent_bonus: 12
    duration_ticks: 2
    pressure_cost: 18
    cooldown_ticks: 25

tradeoffs:
  max_pressure_penalty: 5
  mode_switch_latency_delta: 0.1

forbidden_stacking:
  - gizmo.cooling.pressure_dump_valve
```

## 15. Loadout System

Players own many capabilities; only a constrained loadout fields. Multi-axis budgets prevent dominance: strategic points, mass, pressure draw, heat output, signature, latency, slot count.

### 15.3 Example Loadout Contract

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.loadout
id: loadout.player_17.ironclad_artillery_v3

chassis_id: chassis.heavy.ironclad_mk1
boiler_id: boiler.industrial.bessemer_90
pilot_id: pilot.player_17.predictive_v2

modules:
  weapons: [module.weapon.artillery_mortar, module.weapon.machine_gun]
  sensors: [module.sensor.long_range_radar, module.sensor.short_range_scanner]
  cooling: [module.cooling.auxiliary_vent]
  armor: [module.armor.reinforced_plating]
  gizmos: [gizmo.cooling.emergency_condenser]

budgets:
  points_used: 98
  points_max: 100
  mass_used: 116
  mass_max: 120
  slots_used: 8
  slots_max: 8
  expected_heat_peak: 84
  expected_signature: 91
```

## 16. Modes

Mechs have predefined operational modes. Switching costs time, pressure, heat, vulnerability, cooldown lockout.

### 16.1 Modes

- **Recon** — long-range radar, low weapon readiness, low heat, high sensor range. Weak: poor close-range, vulnerable to ambush.
- **Assault** — short-range scanner, machine gun, main cannon, targeting assist. Weak: high heat/pressure, higher signature.
- **Evasion** — mobility booster, emergency venting, low signature, minimal weapons. Weak: weak offense, poor sensor coverage.
- **Siege** — artillery, stabilizers, long-range targeting, reduced movement. Weak: slow exit, vulnerable to flankers, high heat.

### 16.3 Mode Switch Contract

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.mode_transition
from_mode: recon
to_mode: assault

costs: { pressure: 12, heat: 8, transition_ticks: 2 }

restrictions:
  minimum_lock_ticks_after_switch: 5
  cannot_switch_if_heat_above: 92
  cannot_switch_if_boiler_disabled: true

vulnerability:
  evasion_penalty_during_transition: 0.25
  sensor_dropout_ticks: 1
```

## 17. Store and Unlocks

Sells capability access, never power. Valid: chassis variants, boiler variants, weapon classes, sensor classes, gizmos, pilot archetypes, cosmetic skins, replay effects, arena themes, scenario packs. Invalid: flat damage/health/accuracy upgrades, exclusive dominant modules, paid leaderboard advantage, hidden boosts.

## 18. Lineage and Minting

A build/pilot may be minted only if: passes validation, has replayable match evidence, improves a meaningful metric, doesn't regress beyond thresholds, isn't a trivial clone, has a clear lineage parent.

### 18.2 Lineage Contract

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.lineage_record
id: lineage.pilot.player_17.predictive_v3

subject: { type: pilot, id: pilot.player_17.predictive_v3 }
parent: { type: pilot, id: pilot.player_17.predictive_v2 }

evidence:
  match_ids: [match.2026-04-30.001, match.2026-04-30.002]
  scenario_ids: [scenario.duel.standard_01, scenario.heat_pressure_ambush_02]

performance_delta:
  win_rate_delta: 0.07
  overload_rate_delta: -0.12
  damage_per_pressure_delta: 0.09
  critical_regressions: 0

promotion: { status: promoted, promoted_at: "2026-04-30T16:00:00Z" }
```

## 19. Learning System

Per-tick recording: observable state, hidden canonical state (if permitted), pilot input/output, available actions, action selected, module/boiler/mode state, resulting state delta, reward signal, outcome label.

Learning improves: vent timing, redline discipline, target selection, movement timing, mode switching, weapon selection, retreat, heat-weapon response, artillery avoidance, swarm coordination.

Learning does NOT mutate: chassis limits, boiler physics, module legality, match rules, reducer truth, hidden state access.

Promotion pipeline: collect → extract → generate candidate → run vs parent → run vs baselines → run vs hidden scenarios → reject if exploit/regression → promote if robust → emit promotion event.

## 20. Event Model

### 20.1 Core Envelope

```yaml
schema_version: "0.1.0"
kind: steel_onslaught.event
event_id: evt.01
match_id: match.2026-04-30.001
tick: 142
correlation_id: corr.match.2026-04-30.001.red.01
causation_id: evt.previous
producer_node: node.pilot.red.01
subject: { mech_id: mech.red.01, player_id: player.17 }
event_type: pilot_decision_made
payload: {}
emitted_at: "2026-04-30T16:00:00Z"
```

### 20.2 Pilot Decision

```yaml
kind: steel_onslaught.pilot_decision_made
match_id: match.2026-04-30.001
tick: 142
pilot_id: pilot.player_17.predictive_v3
mech_id: mech.red.01

input_summary:
  mode: recon
  pressure: 64
  heat: 72
  enemy_distance_estimate: 18
  enemy_confidence: 0.74

decision:
  action: switch_mode
  target_mode: assault
  reason_code: enemy_entered_close_range
  confidence: 0.81

considered_actions:
  - { action: remain_recon, score: 0.42 }
  - { action: vent, score: 0.55 }
  - { action: switch_mode_assault, score: 0.81 }

constraints_checked:
  pressure_available: true
  heat_below_switch_limit: true
  mode_lock_expired: true
```

### 20.3 Boiler Update

```yaml
kind: steel_onslaught.boiler_updated
match_id: match.2026-04-30.001
tick: 143
mech_id: mech.red.01

before: { pressure: 64, heat: 72 }
delta: { pressure: -12, heat: 8 }
after: { pressure: 52, heat: 80 }
cause: { event_id: evt.pilot_decision.142, reason: mode_switch_recon_to_assault }
```

### 20.4 Weapon Fired

```yaml
kind: steel_onslaught.weapon_fired
match_id: match.2026-04-30.001
tick: 148
mech_id: mech.red.01
weapon_id: module.weapon.machine_gun
target_id: mech.blue.01

costs: { pressure: 6, heat: 4 }
targeting: { range: 12, lock_confidence: 0.68, predicted_hit_probability: 0.59 }
```

### 20.5 Hit Resolution

```yaml
kind: steel_onslaught.hit_resolved
match_id: match.2026-04-30.001
tick: 149
attacker_id: mech.red.01
defender_id: mech.blue.01
weapon_id: module.weapon.machine_gun

result: { hit: true, damage_raw: 8, damage_after_armor: 5, critical: false }
deterministic_seed: { seed_id: seed.match.2026-04-30.001.tick.149 }
```

## 21. Replay System

Replay is reconstruction, not video playback. The replay engine consumes the event ledger and rebuilds state.

Must support: full match reconstruction, tick-by-tick stepping, pilot decision inspection, heat graph reconstruction, boiler pressure graph reconstruction, mode transition timeline, module activation timeline, causation chain inspection, alternate projection rendering.

Valid views: cinematic battle playback, tactical grid replay, state diff replay, pilot reasoning timeline, boiler stress timeline, decision tree replay, training trace viewer.

## 22. Scoring System

Score includes: outcome, survival, damage dealt/taken, pressure efficiency, heat efficiency, overload avoidance, module utilization, objective performance, decision latency, build cost, replay validity.

### 22.2 Scoring Event

```yaml
kind: steel_onslaught.match_scored
match_id: match.2026-04-30.001

winner: { player_id: player.17, mech_id: mech.red.01 }

scores:
  player_17:
    victory: 1
    damage_efficiency: 0.72
    pressure_efficiency: 0.81
    overload_penalty: 0
    replay_validity: 1
    final_score: 1842
  player_42:
    victory: 0
    damage_efficiency: 0.61
    pressure_efficiency: 0.54
    overload_penalty: 2
    replay_validity: 1
    final_score: 1210
```

## 23. Anti-Exploit Rules

Reject: non-replayable actions, invisible state mutation, free mode switching, unlimited reconfiguration, plugin stacking loops, heat/pressure bypasses, hidden information access, excessive compute pilots, degenerate self-damage farming, collusive match farming, trivial clone minting.

### 23.1 Hidden Evaluation
Promoted pilots must pass: fixed public scenarios, hidden private scenarios, adversarial counter-builds, regression tests, replay determinism checks.

## 24. MVP Scope

- one arena
- duel mode only
- three chassis (light scout, medium hunter, heavy ironclad)
- three boilers (compact, industrial, volatile)
- six weapons (machine gun, steam cannon, artillery mortar, heat lance, shrapnel thrower, harpoon gun)
- four sensors (long-range radar, short-range scanner, thermal detector, acoustic detector)
- four gizmos
- three pilot archetypes (aggressive, defensive, predictive) — heuristic, deterministic
- three operational modes (recon, assault, evasion)
- event ledger
- deterministic replay
- simple UI projection (CLI + minimal web)
- basic leaderboard
- no live learning promotion

## 25. Post-MVP Expansion

squad battles, tournaments, pilot injury and death, lineage minting, candidate policy learning, hidden evaluation arenas, cosmetic theme inheritance, user-created scenarios, public build marketplace, spectator events, team leagues, LLM-driven pilots, Kafka transport.

## 26. Strategic Value

Creates: replayable agent behavior traces, policy decision datasets, constrained orchestration examples, build lineage graphs, module interaction data, balance/cost metrics, public demonstration of OmniNode concepts.

The OmniNode thesis: the interface can be anything; the real system is the event-governed contract graph underneath.

## 27. Final Design Principle

Steel Onslaught is not optimized for bigger mechs, stronger weapons, or purchased dominance. It is optimized for: better decisions, better constraints, better replayability, better learning traces, better lineage, better system design.

The winning player is not the one who bought the biggest boiler. The winning player is the one whose orchestrator knows exactly when the boiler can be abused without becoming shrapnel.
