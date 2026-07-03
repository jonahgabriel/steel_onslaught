/**
 * Event River logic — PRESSURE DECK.
 *
 * Pure functions that turn a flat stream of `SOEventEnvelope`s into the
 * ordered, tick-grouped, side-attributed, filterable river the UI renders.
 * No React, no DOM — unit-tested directly (`__tests__/river.test.ts`).
 *
 * LLM evidence discrimination is intentionally structural: the effect node
 * (`steel_onslaught/llm/effect.py`) piggybacks a `kind` marker onto an
 * existing telemetry event type rather than adding a `SOEventType` member (a
 * pinned-member-set test forbids new members).  We read `payload.kind`
 * defensively so no enum change is ever required.
 */
import type { JsonValue, SOEventEnvelope } from "../types";

// ---------------------------------------------------------------------------
// Side attribution
// ---------------------------------------------------------------------------

export type Side = "red" | "blue" | "neutral";

export interface SideMap {
  readonly byMech: ReadonlyMap<string, Side>;
  readonly byPlayer: ReadonlyMap<string, Side>;
}

const EMPTY_SIDE_MAP: SideMap = { byMech: new Map(), byPlayer: new Map() };

/**
 * Assign sides deterministically: the two players are sorted by id, the first
 * becomes RED, the second BLUE.  Anything past two (or the `*` match subject)
 * is neutral.  There is no explicit side field on the wire, so first-seen
 * order is the only stable signal — sorting keeps it replay-stable.
 */
export function buildSideMap(
  mechs: readonly { readonly mech_id: string; readonly player_id: string }[],
): SideMap {
  const players = [...new Set(mechs.map((m) => m.player_id).filter((p) => p !== "*"))].sort();
  const byPlayer = new Map<string, Side>();
  players.forEach((p, i) => {
    byPlayer.set(p, i === 0 ? "red" : i === 1 ? "blue" : "neutral");
  });
  const byMech = new Map<string, Side>();
  for (const m of mechs) {
    byMech.set(m.mech_id, byPlayer.get(m.player_id) ?? "neutral");
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
// LLM evidence discrimination (payload.kind — never a new enum member)
// ---------------------------------------------------------------------------

export type LlmEvidenceKind = "requested" | "resolved";

const LLM_REQUEST_KIND = "llm_completion_requested";
const LLM_RESOLVED_KIND = "llm_completion_resolved";

function payloadRecord(env: SOEventEnvelope): Record<string, JsonValue> {
  // Every payload is a JSON object; open-record payloads carry the `kind`
  // marker the effect node stamps.  A single narrowing cast, no `any`.
  return env.payload as unknown as Record<string, JsonValue>;
}

/** Read a string field from an (open) payload, or undefined. */
export function payloadString(env: SOEventEnvelope, key: string): string | undefined {
  const v = payloadRecord(env)[key];
  return typeof v === "string" ? v : undefined;
}

/** Read a numeric field from an (open) payload, or undefined. */
export function payloadNumber(env: SOEventEnvelope, key: string): number | undefined {
  const v = payloadRecord(env)[key];
  return typeof v === "number" ? v : undefined;
}

/** Discriminate LLM evidence purely on `payload.kind`. */
export function llmEvidenceKind(env: SOEventEnvelope): LlmEvidenceKind | null {
  const kind = payloadRecord(env)["kind"];
  if (kind === LLM_REQUEST_KIND) return "requested";
  if (kind === LLM_RESOLVED_KIND) return "resolved";
  return null;
}

export interface LlmPair {
  readonly requested: SOEventEnvelope;
  /** null while the request is unresolved (the LLM is "thinking"). */
  readonly resolved: SOEventEnvelope | null;
}

export interface LlmPairing {
  readonly pairs: readonly LlmPair[];
  /** message_ids of requests still awaiting a resolution. */
  readonly unresolved: ReadonlySet<string>;
}

/**
 * Pair `llm_completion_requested` with the next `llm_completion_resolved` for
 * the same mech, in stream order.  Unmatched requests remain "thinking".
 */
export function pairLlmEvidence(envelopes: readonly SOEventEnvelope[]): LlmPairing {
  const pairs: LlmPair[] = [];
  const openByMech = new Map<string, number>(); // mech_id → index into pairs
  const unresolved = new Set<string>();

  for (const env of envelopes) {
    const kind = llmEvidenceKind(env);
    if (kind === null) continue;
    const mech = env.subject.mech_id;
    if (kind === "requested") {
      openByMech.set(mech, pairs.length);
      pairs.push({ requested: env, resolved: null });
      unresolved.add(env.envelope.message_id);
    } else {
      const idx = openByMech.get(mech);
      if (idx !== undefined) {
        const open = pairs[idx];
        if (open !== undefined) {
          pairs[idx] = { requested: open.requested, resolved: env };
          unresolved.delete(open.requested.envelope.message_id);
          openByMech.delete(mech);
        }
      } else {
        // Resolution with no visible request — surface it as a lone resolve.
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
  const llm = llmEvidenceKind(env);
  if (llm === "requested") {
    const persona = payloadString(env, "persona") || "pilot";
    return `LLM request · ${persona}`;
  }
  if (llm === "resolved") {
    const model = payloadString(env, "model") || "model";
    const pt = payloadNumber(env, "prompt_tokens") ?? 0;
    const ct = payloadNumber(env, "completion_tokens") ?? 0;
    return `LLM resolved · ${shortId(model)} · ${pt}→${ct} tok`;
  }

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
