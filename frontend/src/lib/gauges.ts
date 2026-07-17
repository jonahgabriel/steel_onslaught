/**
 * Gauge fold — PRESSURE DECK (Rev 2: full mech spec readout).
 *
 * Derives the complete per-mech spec panel (identity, vitals, thermal, mode,
 * per-weapon cooldowns, tallies, status) from the SAME envelope stream the
 * river reads — no separate data source, no re-derivation of game state. Pure
 * and immutable, so the left rail is a projection, not a store.
 *
 * Field provenance (read from `types.ts` + fixtures, never guessed):
 *   - identity / vitals / cooldowns : `MATCH_STARTED` mech runtime state.
 *   - hp / armor / heat / pressure  : boiler_updated, damage_applied,
 *                                     armor_absorbed.
 *   - overload + redline ticks      : boiler_overloaded / heat_redline_exited.
 *   - mode + transition countdown   : mode_transition_started / _completed.
 *   - pilot persona / model         : llm_completion_requested / _resolved.
 *   - tallies                       : weapon_fired, damage_applied,
 *                                     pilot_decision_made.
 * There is no `display_name` on the wire, so the exact `mech_id` is displayed.
 */

import type { ChassisClass, MechState } from "../assets/theme";
import type { SOEventEnvelope, SOMechRuntimeState } from "../types";
import type { Side, SideMap } from "./river";

export type MechStatus = "alive" | "pilot_killed" | "destroyed";

/**
 * The sprite damage tier for a mech, from its hp fraction + liveness:
 * dead → `destroyed`; else `nominal` > 60%, `damaged` > 30%, `critical` below.
 */
export function mechStateOf(hp: number, hpMax: number, alive: boolean): MechState {
  if (!alive) return "destroyed";
  const frac = hpMax > 0 ? hp / hpMax : 0;
  if (frac > 0.6) return "nominal";
  if (frac > 0.3) return "damaged";
  return "critical";
}

export interface GaugeState {
  readonly mechId: string;
  readonly playerId: string;
  readonly side: Side;
  // identity
  readonly displayName: string;
  readonly chassisClass: ChassisClass;
  readonly chassisId: string;
  readonly pilotId: string;
  /** True only after canonical LLM evidence identifies this pilot as LLM-backed. */
  readonly isLlm: boolean;
  /** LLM persona (from llm_completion_requested), else null (heuristic pilot). */
  readonly persona: string | null;
  /** LLM provider/model (from llm_completion_resolved), else null. */
  readonly model: string | null;
  // thermal
  readonly heat: number;
  readonly redlineThreshold: number;
  readonly ruptureThreshold: number;
  readonly redlineConsecutiveTicks: number;
  readonly overloaded: boolean;
  readonly pressureCurrent: number;
  readonly pressureMaximum: number;
  // vitals
  readonly hp: number;
  readonly hpMax: number;
  readonly armorValue: number;
  readonly armorMax: number;
  // mode
  readonly mode: string;
  readonly transitionToMode: string | null;
  readonly transitionTicksRemaining: number;
  // weapons
  readonly weaponCooldowns: Readonly<Record<string, number>>;
  // tallies
  readonly damageDealt: number;
  readonly damageTaken: number;
  readonly shotsFired: number;
  readonly decisions: number;
  // status
  readonly status: MechStatus;
}

export type Gauges = Readonly<Record<string, GaugeState>>;

/** Preserve the canonical mech identity exactly; presentation must not invent identity. */
export function displayNameOf(mechId: string): string {
  return mechId;
}

/**
 * Honest pilot descriptor for the spec panel (D4). Canonical LLM evidence
 * yields `LLM · <persona> · <provider>` once available. Without that evidence,
 * the descriptor remains `UNKNOWN` and preserves only the canonical pilot ID;
 * presentation never infers a persona or pilot kind from identifier text.
 */
export function pilotDescriptor(g: GaugeState): { kind: "LLM" | "UNKNOWN"; label: string } {
  const isLlm = g.isLlm || g.persona !== null || g.model !== null;
  if (isLlm) {
    const persona = g.persona ?? "unknown";
    return { kind: "LLM", label: g.model !== null ? `${persona} · ${g.model}` : persona };
  }
  return { kind: "UNKNOWN", label: g.pilotId || "unknown" };
}

function fromRuntime(state: SOMechRuntimeState, sides: SideMap): GaugeState {
  return {
    mechId: state.mech_id,
    playerId: state.player_id,
    side: sides.byMech.get(state.mech_id) ?? "neutral",
    displayName: displayNameOf(state.mech_id),
    chassisClass: state.chassis_class,
    chassisId: state.chassis_id,
    pilotId: state.pilot_id,
    isLlm: false,
    persona: null,
    model: null,
    heat: state.boiler.heat_current,
    redlineThreshold: state.boiler.heat_redline_threshold,
    ruptureThreshold: state.boiler.heat_rupture_threshold,
    redlineConsecutiveTicks: state.redline_consecutive_ticks,
    overloaded: state.overloaded,
    pressureCurrent: state.boiler.pressure_current,
    pressureMaximum: state.boiler.pressure_maximum,
    hp: state.hp,
    hpMax: state.hp_max,
    armorValue: state.armor_value,
    armorMax: state.armor_max,
    mode: state.current_mode,
    transitionToMode: state.transition_to_mode,
    transitionTicksRemaining: state.transition_ticks_remaining,
    weaponCooldowns: { ...state.weapon_cooldowns },
    damageDealt: 0,
    damageTaken: 0,
    shotsFired: 0,
    decisions: 0,
    status: state.alive ? "alive" : "destroyed",
  };
}

export function initGauges(mechs: readonly SOMechRuntimeState[], sides: SideMap): Gauges {
  const out: Record<string, GaugeState> = {};
  for (const m of mechs) out[m.mech_id] = fromRuntime(m, sides);
  return out;
}

/** Apply one envelope to the gauge map, returning a new map (or the same). */
export function applyGaugeEvent(gauges: Gauges, env: SOEventEnvelope): Gauges {
  const patch = (mechId: string, next: Partial<GaugeState>): Gauges => {
    const cur = gauges[mechId];
    if (cur === undefined) return gauges;
    return { ...gauges, [mechId]: { ...cur, ...next } };
  };

  switch (env.event_type) {
    case "boiler_updated":
      return patch(env.subject.mech_id, {
        heat: env.payload.heat_after,
        pressureCurrent: env.payload.pressure_after,
      });
    case "armor_absorbed":
      return patch(env.payload.target_id, { armorValue: env.payload.armor_after });
    case "damage_applied": {
      // Two folds: the victim's hp + damage-taken tally, and (when known) the
      // attacker's damage-dealt tally.
      const target = gauges[env.payload.target_id];
      if (target === undefined) return gauges;
      let next: Gauges = {
        ...gauges,
        [env.payload.target_id]: {
          ...target,
          hp: env.payload.hp_after,
          damageTaken: target.damageTaken + env.payload.damage,
        },
      };
      const sourceId = env.payload.source_mech_id;
      if (sourceId !== null) {
        const source = next[sourceId];
        if (source !== undefined) {
          next = {
            ...next,
            [sourceId]: { ...source, damageDealt: source.damageDealt + env.payload.damage },
          };
        }
      }
      return next;
    }
    case "weapon_fired":
      return patch(env.subject.mech_id, {
        shotsFired: (gauges[env.subject.mech_id]?.shotsFired ?? 0) + 1,
      });
    case "pilot_decision_made": {
      // An `llm_*` reason_code (LLM_DECISION / LLM_FALLBACK) is a stream-derived
      // confirmation that this mech is LLM-driven — the fallback classifier for a
      // pilot_id that did not encode `llm`.
      const isLlmDecision = env.payload.reason_code.startsWith("llm_");
      const cur = gauges[env.subject.mech_id];
      return patch(env.subject.mech_id, {
        decisions: (cur?.decisions ?? 0) + 1,
        ...(isLlmDecision ? { isLlm: true } : {}),
      });
    }
    case "boiler_overloaded":
      return patch(env.subject.mech_id, {
        overloaded: true,
        redlineConsecutiveTicks: env.payload.redline_consecutive_ticks,
      });
    case "heat_redline_exited":
      return patch(env.subject.mech_id, { overloaded: false, redlineConsecutiveTicks: 0 });
    case "mode_transition_started":
      return patch(env.subject.mech_id, {
        transitionToMode: env.payload.to_mode,
        transitionTicksRemaining: env.payload.costs.transition_ticks,
      });
    case "mode_transition_completed":
      return patch(env.subject.mech_id, {
        mode: env.payload.new_mode,
        transitionToMode: null,
        transitionTicksRemaining: 0,
      });
    case "llm_completion_requested":
      return patch(env.subject.mech_id, { persona: env.payload.persona_id });
    case "llm_completion_resolved":
      return patch(env.subject.mech_id, { model: env.payload.model });
    case "pilot_killed":
      return patch(env.payload.mech_id, { status: "pilot_killed" });
    case "mech_destroyed":
      return patch(env.subject.mech_id, { status: "destroyed" });
    default:
      return gauges;
  }
}
