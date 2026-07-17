/**
 * Event River logic — PRESSURE DECK.
 *
 * Pure functions that turn a flat stream of `SOEventEnvelope`s into the
 * ordered, tick-grouped, side-attributed, filterable river the UI renders.
 * No React, no DOM — unit-tested directly (`__tests__/river.test.ts`).
 *
 * LLM evidence is carried by three first-class `SOEventType` members
 * (`llm_completion_requested` / `llm_completion_resolved` /
 * `llm_completion_failed`) emitted by the
 * effect node (`steel_onslaught/llm/effect.py`). We discriminate solely on
 * the canonical `event_type` field.
 */
import type { SOEventEnvelope } from "../types";

// ---------------------------------------------------------------------------
// Side attribution
// ---------------------------------------------------------------------------

export type Side = "red" | "blue" | "neutral";

export interface SideMap {
  readonly byMech: ReadonlyMap<string, Side>;
  readonly byPlayer: ReadonlyMap<string, Side>;
}

const EMPTY_SIDE_MAP: SideMap = { byMech: new Map(), byPlayer: new Map() };

/** Build side indexes exclusively from explicit canonical match metadata. */
export function buildSideMap(
  mechs: readonly {
    readonly mech_id: string;
    readonly player_id: string;
    readonly side: Side;
  }[],
): SideMap {
  const byPlayer = new Map<string, Side>();
  const byMech = new Map<string, Side>();
  for (const m of mechs) {
    byMech.set(m.mech_id, m.side);
    const existing = byPlayer.get(m.player_id);
    if (existing !== undefined && existing !== m.side) {
      throw new Error(`player ${m.player_id} declares conflicting side metadata`);
    }
    byPlayer.set(m.player_id, m.side);
  }
  return { byMech, byPlayer };
}

/** The side of an envelope, from its subject. */
export function sideOf(env: SOEventEnvelope, sides: SideMap = EMPTY_SIDE_MAP): Side {
  const byMech = sides.byMech.get(env.subject.mech_id);
  if (byMech !== undefined) return byMech;
  const byPlayer = sides.byPlayer.get(env.subject.player_id);
  if (byPlayer !== undefined) return byPlayer;
  return "neutral";
}

// ---------------------------------------------------------------------------
// LLM evidence discrimination (first-class event_type)
// ---------------------------------------------------------------------------

export type LlmEvidenceKind = "requested" | "resolved" | "failed";

/** Discriminate LLM evidence solely on the first-class `event_type`. */
export function llmEvidenceKind(env: SOEventEnvelope): LlmEvidenceKind | null {
  if (env.event_type === "llm_completion_requested") return "requested";
  if (env.event_type === "llm_completion_resolved") return "resolved";
  if (env.event_type === "llm_completion_failed") return "failed";
  return null;
}

export interface LlmPair {
  readonly requested: SOEventEnvelope;
  /** null while the request has no resolved-or-failed terminal evidence. */
  readonly resolved: SOEventEnvelope | null;
}

export interface LlmPairing {
  readonly pairs: readonly LlmPair[];
  /** message_ids of requests still awaiting a resolution. */
  readonly unresolved: ReadonlySet<string>;
}

/**
 * Pair a terminal with the request named by its `causation_id`. Unmatched
 * requests remain "thinking"; orphan terminals remain visible as lone rows.
 * The first terminal wins if duplicate evidence arrives.
 */
export function pairLlmEvidence(envelopes: readonly SOEventEnvelope[]): LlmPairing {
  const pairs: LlmPair[] = [];
  const pairByRequestId = new Map<string, number>();
  const unresolved = new Set<string>();

  for (const env of envelopes) {
    const kind = llmEvidenceKind(env);
    if (kind === null) continue;
    if (kind === "requested") {
      pairByRequestId.set(env.envelope.message_id, pairs.length);
      pairs.push({ requested: env, resolved: null });
      unresolved.add(env.envelope.message_id);
    } else {
      const causationId = env.envelope.causation_id;
      const idx = causationId === null ? undefined : pairByRequestId.get(causationId);
      if (idx !== undefined) {
        const open = pairs[idx];
        if (open !== undefined && open.resolved === null) {
          pairs[idx] = { requested: open.requested, resolved: env };
          unresolved.delete(open.requested.envelope.message_id);
        }
      } else {
        // Terminal with no visible request — surface it as a lone terminal.
        pairs.push({ requested: env, resolved: env });
      }
    }
  }

  return { pairs, unresolved };
}

// ---------------------------------------------------------------------------
// Filter groups
// ---------------------------------------------------------------------------

export type FilterGroup = "combat" | "decisions" | "thermal" | "llm" | "lifecycle";

export const FILTER_GROUPS: readonly FilterGroup[] = [
  "combat",
  "decisions",
  "thermal",
  "llm",
  "lifecycle",
] as const;

export const FILTER_GROUP_LABELS: Record<FilterGroup, string> = {
  combat: "COMBAT",
  decisions: "DECISIONS",
  thermal: "THERMAL",
  llm: "LLM",
  lifecycle: "LIFECYCLE",
};

const GROUP_BY_EVENT: Record<string, FilterGroup> = {
  // combat — weapon / hit / damage / armor
  weapon_fired: "combat",
  hit_resolved: "combat",
  armor_absorbed: "combat",
  damage_applied: "combat",
  // decisions — pilot_decision_made + intents
  pilot_decision_made: "decisions",
  move_intent: "decisions",
  weapon_fire_intent: "decisions",
  mode_switch_intent: "decisions",
  // thermal — boiler / heat / vent (+ mode transitions carry heat cost)
  vent_intent: "thermal",
  boiler_updated: "thermal",
  heat_redline_entered: "thermal",
  heat_redline_exited: "thermal",
  boiler_overloaded: "thermal",
  boiler_ruptured: "thermal",
  mode_transition_started: "thermal",
  mode_transition_completed: "thermal",
  // lifecycle — match / spawn / death / victory / scored (+ telemetry)
  match_started: "lifecycle",
  match_tick: "lifecycle",
  mech_spawned: "lifecycle",
  sensor_observation: "lifecycle",
  pilot_injured: "lifecycle",
  pilot_killed: "lifecycle",
  mech_destroyed: "lifecycle",
  victory_declared: "lifecycle",
  match_ended: "lifecycle",
  match_scored: "lifecycle",
};

/** The filter group of an envelope; LLM evidence overrides the event type. */
export function groupOf(env: SOEventEnvelope): FilterGroup {
  if (llmEvidenceKind(env) !== null) return "llm";
  return GROUP_BY_EVENT[env.event_type] ?? "lifecycle";
}

// ---------------------------------------------------------------------------
// Ordering, tick grouping, filtering, windowing
// ---------------------------------------------------------------------------

export interface RiverRow {
  readonly env: SOEventEnvelope;
  /** Monotonic arrival index — the stable tiebreak within a (tick, seq). */
  readonly arrival: number;
}

/** Order by (tick, sequence_in_tick, arrival) ascending — oldest first. */
export function compareRows(a: RiverRow, b: RiverRow): number {
  if (a.env.tick !== b.env.tick) return a.env.tick - b.env.tick;
  if (a.env.sequence_in_tick !== b.env.sequence_in_tick) {
    return a.env.sequence_in_tick - b.env.sequence_in_tick;
  }
  return a.arrival - b.arrival;
}

/** A stably-sorted copy (never mutates the input). */
export function orderRows(rows: readonly RiverRow[]): RiverRow[] {
  return [...rows].sort(compareRows);
}

export interface TickGroup {
  readonly tick: number;
  readonly rows: readonly RiverRow[];
}

/** Group already-ordered rows under contiguous tick separators. */
export function groupByTick(rows: readonly RiverRow[]): TickGroup[] {
  const groups: TickGroup[] = [];
  let current: { tick: number; rows: RiverRow[] } | null = null;
  for (const row of rows) {
    if (current === null || current.tick !== row.env.tick) {
      current = { tick: row.env.tick, rows: [row] };
      groups.push(current);
    } else {
      current.rows.push(row);
    }
  }
  return groups;
}

/** Keep only rows whose group is currently enabled. */
export function filterRows(
  rows: readonly RiverRow[],
  active: ReadonlySet<FilterGroup>,
): RiverRow[] {
  return rows.filter((r) => active.has(groupOf(r.env)));
}

export interface RiverWindow {
  readonly visible: readonly RiverRow[];
  readonly hiddenCount: number;
}

/** Window to the last `n` rows (newest at the bottom of the river). */
export function windowRows(rows: readonly RiverRow[], n: number): RiverWindow {
  if (rows.length <= n) return { visible: rows, hiddenCount: 0 };
  return { visible: rows.slice(rows.length - n), hiddenCount: rows.length - n };
}

/** Per-group counts across a row set (for the ticker chips). */
export function groupCounts(rows: readonly RiverRow[]): Record<FilterGroup, number> {
  const counts: Record<FilterGroup, number> = {
    combat: 0,
    decisions: 0,
    thermal: 0,
    llm: 0,
    lifecycle: 0,
  };
  for (const r of rows) counts[groupOf(r.env)] += 1;
  return counts;
}

// ---------------------------------------------------------------------------
// One-line payload summaries (hand-written per type — never raw JSON)
// ---------------------------------------------------------------------------

function shortId(id: string): string {
  const dot = id.lastIndexOf(".");
  return dot === -1 ? id : id.slice(dot + 1);
}

/** A human, one-line summary of an envelope's payload. */
export function summarizeEnvelope(env: SOEventEnvelope): string {
  if (env.event_type === "llm_completion_requested")
    return `LLM request · ${env.payload.persona_id}`;
  if (env.event_type === "llm_completion_resolved")
    return `LLM resolved · ${shortId(env.payload.model)} · ${env.payload.prompt_tokens}→${env.payload.completion_tokens} tok`;
  if (env.event_type === "llm_completion_failed") return `LLM failed · ${env.payload.reason_code}`;

  switch (env.event_type) {
    case "match_started":
      return `seed ${env.payload.seed} · ${env.payload.mechs.length} mechs · max ${env.payload.max_ticks}t`;
    case "match_tick":
      return `tick ${env.tick}`;
    case "mech_spawned":
      return `spawn @ (${env.payload.position.x}, ${env.payload.position.y})`;
    case "sensor_observation":
      return `contact ${shortId(env.payload.enemy_mech_id)} · d≈${env.payload.distance_estimate.toFixed(1)}`;
    case "pilot_decision_made":
      return `${env.payload.action} · ${env.payload.reason_code}`;
    case "move_intent":
    case "weapon_fire_intent":
    case "mode_switch_intent":
    case "vent_intent":
      return env.event_type.replace(/_/g, " ");
    case "movement_resolved":
      return `(${env.payload.from.x},${env.payload.from.y}) → (${env.payload.to.x},${env.payload.to.y})`;
    case "boiler_updated":
      return `heat ${env.payload.heat_before.toFixed(0)}→${env.payload.heat_after.toFixed(0)} · psi ${env.payload.pressure_after.toFixed(0)}`;
    case "heat_redline_entered":
      return `REDLINE · heat ${env.payload.heat.toFixed(0)}/${env.payload.redline_threshold.toFixed(0)}`;
    case "heat_redline_exited":
      return `redline cleared · heat ${env.payload.heat.toFixed(0)}`;
    case "boiler_overloaded":
      return `OVERLOAD · heat ${env.payload.heat.toFixed(0)} · ${env.payload.redline_consecutive_ticks}t`;
    case "boiler_ruptured":
      return `RUPTURE · ${env.payload.direct_damage} dmg + ${env.payload.area_damage} area`;
    case "mode_transition_started":
      return `${env.payload.from_mode} → ${env.payload.to_mode} (starting)`;
    case "mode_transition_completed":
      return `mode → ${env.payload.new_mode}`;
    case "weapon_fired":
      return `${shortId(env.payload.weapon_id)} → ${shortId(env.payload.target_id)} · p${(env.payload.hit_probability * 100).toFixed(0)}%`;
    case "hit_resolved":
      return env.payload.result.hit
        ? `HIT ${shortId(env.payload.defender_id)} · ${env.payload.result.damage_after_armor} dmg`
        : `MISS ${shortId(env.payload.defender_id)}`;
    case "armor_absorbed":
      return `armor absorbed ${env.payload.absorbed_amount} · ${env.payload.armor_after} left`;
    case "damage_applied":
      return `${env.payload.damage} dmg → ${shortId(env.payload.target_id)} · hp ${env.payload.hp_after}`;
    case "pilot_injured":
      return "pilot injured";
    case "pilot_killed":
      return `PILOT KILLED ${shortId(env.payload.mech_id)}`;
    case "mech_destroyed":
      return `DESTROYED · ${env.payload.cause}`;
    case "victory_declared":
      return `VICTORY · ${shortId(env.payload.winner_player_id)}`;
    case "match_ended":
      return `match ended · ${env.payload.reason}`;
    case "match_scored":
      return `scored · winner ${shortId(env.payload.winner_player_id)} ${env.payload.winner_score.toFixed(0)}`;
    default:
      return "event";
  }
}

/** A short glyph per group, for the row marker. */
export function glyphOf(env: SOEventEnvelope): string {
  if (llmEvidenceKind(env) !== null) return "❯";
  switch (groupOf(env)) {
    case "combat":
      return "◆";
    case "decisions":
      return "◇";
    case "thermal":
      return "▲";
    case "lifecycle":
      return "●";
    default:
      return "•";
  }
}

/** Danger events get a red glow / border in the river. */
export function isDangerEvent(env: SOEventEnvelope): boolean {
  switch (env.event_type) {
    case "boiler_ruptured":
    case "mech_destroyed":
    case "pilot_killed":
    case "boiler_overloaded":
      return true;
    default:
      return false;
  }
}

/** The tick.seq stamp shown at the head of a row (e.g. `047.03`). */
export function formatStamp(env: SOEventEnvelope): string {
  const tick = String(env.tick).padStart(3, "0");
  const seq = String(env.sequence_in_tick).padStart(2, "0");
  return `${tick}.${seq}`;
}

/**
 * The fallback class for an `LLM_FALLBACK` decision, or null for a normal
 * decision.  A fallback decision is a heuristic that stepped in when the LLM
 * pilot could not answer — its `reason_code` carries "fallback".
 */
export function fallbackClassOf(env: SOEventEnvelope): string | null {
  if (env.event_type !== "pilot_decision_made") return null;
  const rc = env.payload.reason_code;
  if (!/fallback/i.test(rc)) return null;
  const cls = env.payload.action_params["fallback_class"];
  return typeof cls === "string" ? cls : rc;
}

/** Confidence rendered as N filled of 5 amber segments. */
export function confidenceSegments(confidence: number): boolean[] {
  const filled = Math.max(0, Math.min(5, Math.round(confidence * 5)));
  return Array.from({ length: 5 }, (_, i) => i < filled);
}
