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
 *   - seat identity (authoritative) : match_started launch_provenance
 *                                     .seat_assignments, matched by player_id.
 *   - tallies                       : weapon_fired, damage_applied,
 *                                     pilot_decision_made / plan_committed.
 * There is no `display_name` on the wire, so the exact `mech_id` is displayed.
 */

import type { ChassisClass, MechState } from "../assets/theme";
import type { SOEventEnvelope, SOMechRuntimeState, SOSeatAssignment } from "../types";
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
  /**
   * The authoritative seat assignment for this mech's player, from
   * MATCH_STARTED `launch_provenance.seat_assignments` — who is actually flying
   * this seat (human vs model, which persona, which model identity, which
   * loadout). Null when the stream carries no launch provenance (a legacy or
   * historical-replay match). This is launch evidence, NOT runtime inference:
   * the runtime-derived `persona`/`model` below are folded separately and may
   * disagree — a disagreement is a real defect, not a display bug.
   */
  readonly seat: SOSeatAssignment | null;
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

/** The authoritative seat identity, flattened for display. */
export interface SeatDescriptor {
  /** Who holds the controls — the launch record's own discriminator. */
  readonly kind: "HUMAN" | "MODEL";
  /** `model_identity_id` for a model seat, `human_identity_id` for a human one. */
  readonly identityId: string;
  /** Persona id — model seats only; a human seat has none. */
  readonly personaId: string | null;
  readonly loadoutId: string;
  readonly pilotSpecId: string;
  readonly inputSource: string;
}

/**
 * The authoritative per-seat identity for a mech, or null when the match
 * carried no launch provenance. Read straight off the launch record — never
 * merged with, or defaulted from, the runtime-derived persona/model.
 */
export function seatDescriptor(g: GaugeState): SeatDescriptor | null {
  const seat = g.seat;
  if (seat === null) return null;
  const common = {
    loadoutId: seat.loadout_id,
    pilotSpecId: seat.pilot_spec_id,
    inputSource: seat.input_source,
  };
  if (seat.kind === "model") {
    return {
      kind: "MODEL",
      identityId: seat.model_identity_id,
      personaId: seat.persona_id,
      ...common,
    };
  }
  return { kind: "HUMAN", identityId: seat.human_identity_id, personaId: null, ...common };
}

function fromRuntime(
  state: SOMechRuntimeState,
  sides: SideMap,
  seat: SOSeatAssignment | null,
): GaugeState {
  return {
    mechId: state.mech_id,
    playerId: state.player_id,
    side: sides.byMech.get(state.mech_id) ?? "neutral",
    displayName: displayNameOf(state.mech_id),
    chassisClass: state.chassis_class,
    chassisId: state.chassis_id,
    pilotId: state.pilot_id,
    seat,
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

/**
 * Seed the gauge map from MATCH_STARTED. `seats` is the authoritative
 * `launch_provenance.seat_assignments` pair when the launch carried provenance;
 * assignments are matched to mechs by `player_id` (the one identifier both the
 * runtime state and the launch record agree on) and are never inferred.
 */
export function initGauges(
  mechs: readonly SOMechRuntimeState[],
  sides: SideMap,
  seats: readonly SOSeatAssignment[] = [],
): Gauges {
  const seatByPlayer = new Map<string, SOSeatAssignment>();
  for (const seat of seats) seatByPlayer.set(seat.player_id, seat);
  const out: Record<string, GaugeState> = {};
  for (const m of mechs) {
    out[m.mech_id] = fromRuntime(m, sides, seatByPlayer.get(m.player_id) ?? null);
  }
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
    case "plan_committed": {
      // The card cadence never runs ReducerPilotTick, so PLAN_COMMITTED is this
      // mech's decision for the round. Counting only pilot_decision_made left
      // the DECISIONS tally pinned at 0 for the entire demo.
      const cur = gauges[env.subject.mech_id];
      return patch(env.subject.mech_id, { decisions: (cur?.decisions ?? 0) + 1 });
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
