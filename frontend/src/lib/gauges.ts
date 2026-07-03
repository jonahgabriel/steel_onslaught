/**
 * Gauge fold — PRESSURE DECK.
 *
 * Derives per-mech boiler/heat/armor/mode/status from the SAME envelope
 * stream the river reads (no separate data source, no re-derivation of game
 * state).  Pure and immutable so the left rail is a projection, not a store.
 */

import type { SOEventEnvelope, SOMechRuntimeState } from "../types";
import type { Side, SideMap } from "./river";

export type MechStatus = "alive" | "pilot_killed" | "destroyed";

export interface GaugeState {
  readonly mechId: string;
  readonly playerId: string;
  readonly side: Side;
  readonly heat: number;
  readonly redlineThreshold: number;
  readonly ruptureThreshold: number;
  readonly pressureCurrent: number;
  readonly pressureMaximum: number;
  readonly hp: number;
  readonly hpMax: number;
  readonly armorValue: number;
  readonly armorMax: number;
  readonly mode: string;
  readonly status: MechStatus;
}

export type Gauges = Readonly<Record<string, GaugeState>>;

function fromRuntime(state: SOMechRuntimeState, sides: SideMap): GaugeState {
  return {
    mechId: state.mech_id,
    playerId: state.player_id,
    side: sides.byMech.get(state.mech_id) ?? "neutral",
    heat: state.boiler.heat_current,
    redlineThreshold: state.boiler.heat_redline_threshold,
    ruptureThreshold: state.boiler.heat_rupture_threshold,
    pressureCurrent: state.boiler.pressure_current,
    pressureMaximum: state.boiler.pressure_maximum,
    hp: state.hp,
    hpMax: state.hp_max,
    armorValue: state.armor_value,
    armorMax: state.armor_max,
    mode: state.current_mode,
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
    case "damage_applied":
      return patch(env.payload.target_id, { hp: env.payload.hp_after });
    case "mode_transition_completed":
      return patch(env.subject.mech_id, { mode: env.payload.new_mode });
    case "pilot_killed":
      return patch(env.payload.mech_id, { status: "pilot_killed" });
    case "mech_destroyed":
      return patch(env.subject.mech_id, { status: "destroyed" });
    default:
      return gauges;
  }
}
