/**
 * Projection-only arena feedback.
 *
 * These views deliberately consume the canonical envelope stream instead of
 * inventing a second combat state.  Momentum is a recent-event presentation
 * cue (not a gameplay modifier), telegraphs are unresolved canonical intents,
 * and recap/league data come from terminal ledger events.
 */
import type { SOEventEnvelope } from "../types";
import {
  orderRows,
  type RiverRow,
  type Side,
  type SideMap,
  sideOf,
  summarizeEnvelope,
} from "./river";

export interface MomentumSnapshot {
  readonly red: number;
  readonly blue: number;
  readonly redDelta: number;
  readonly blueDelta: number;
  readonly leader: Side;
}

export type TelegraphKind = "MOVE" | "FIRE" | "MODE" | "VENT";

export interface Telegraph {
  readonly messageId: string;
  readonly mechId: string;
  readonly side: Side;
  readonly kind: TelegraphKind;
  readonly label: string;
  readonly tick: number;
  readonly status: "TELEGRAPHED" | "RESOLVED";
}

export interface RecapEntry {
  readonly eventId: string;
  readonly tick: number;
  readonly side: Side;
  readonly label: string;
}

export interface DecisionCard {
  readonly mechId: string;
  readonly side: Side;
  readonly action: string;
  readonly reason: string;
  readonly rationale: string | null;
  readonly confidence: number;
  readonly tick: number;
}

export interface LeagueEntry {
  readonly playerId: string;
  readonly side: Side;
  readonly score: number;
  readonly damageDealt: number;
  readonly efficiency: number;
  readonly winner: boolean;
}

export interface LeagueSnapshot {
  readonly durationTicks: number;
  readonly isDraw: boolean;
  readonly entries: readonly LeagueEntry[];
}

const MOMENTUM_WINDOW = 48;
const RECAP_WINDOW = 5;
const TELEGRAPH_WINDOW = 4;

type IntentEnvelope = Extract<
  SOEventEnvelope,
  {
    event_type: "move_intent" | "weapon_fire_intent" | "mode_switch_intent" | "vent_intent";
  }
>;

function clamp(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function deltaFor(env: SOEventEnvelope, sides: SideMap): { red: number; blue: number } {
  let red = 0;
  let blue = 0;
  const add = (side: Side, value: number): void => {
    if (side === "red") red += value;
    if (side === "blue") blue += value;
  };
  const subjectSide = sideOf(env, sides);
  switch (env.event_type) {
    case "pilot_decision_made":
      add(subjectSide, 1);
      break;
    case "movement_resolved":
      add(subjectSide, 1);
      break;
    case "hit_resolved":
      add(sides.byMech.get(env.payload.attacker_id) ?? "neutral", env.payload.result.hit ? 3 : -1);
      add(sides.byMech.get(env.payload.defender_id) ?? "neutral", env.payload.result.hit ? -2 : 1);
      break;
    case "damage_applied":
      add(sides.byMech.get(env.payload.source_mech_id ?? "") ?? "neutral", 3);
      add(sides.byMech.get(env.payload.target_id) ?? "neutral", -3);
      break;
    case "armor_absorbed":
      add(sides.byMech.get(env.payload.target_id) ?? "neutral", -1);
      break;
    case "boiler_ruptured":
      add(subjectSide, -5);
      break;
    case "mech_destroyed":
      add(subjectSide, -8);
      break;
    case "victory_declared":
      add(sides.byPlayer.get(env.payload.winner_player_id) ?? "neutral", 10);
      break;
    default:
      break;
  }
  return { red, blue };
}

/** Compute a bounded recent-event edge; this never feeds back into gameplay. */
export function buildMomentum(rows: readonly RiverRow[], sides: SideMap): MomentumSnapshot {
  let redDelta = 0;
  let blueDelta = 0;
  for (const row of orderRows(rows).slice(-MOMENTUM_WINDOW)) {
    const delta = deltaFor(row.env, sides);
    redDelta += delta.red;
    blueDelta += delta.blue;
  }
  const red = clamp(50 + redDelta * 2);
  const blue = clamp(50 + blueDelta * 2);
  const leader: Side = red === blue ? "neutral" : red > blue ? "red" : "blue";
  return { red, blue, redDelta, blueDelta, leader };
}

function isIntent(env: SOEventEnvelope): env is IntentEnvelope {
  return (
    env.event_type === "move_intent" ||
    env.event_type === "weapon_fire_intent" ||
    env.event_type === "mode_switch_intent" ||
    env.event_type === "vent_intent"
  );
}

function intentKind(env: IntentEnvelope): TelegraphKind {
  switch (env.event_type) {
    case "move_intent":
      return "MOVE";
    case "weapon_fire_intent":
      return "FIRE";
    case "mode_switch_intent":
      return "MODE";
    case "vent_intent":
      return "VENT";
  }
}

function intentLabel(env: IntentEnvelope): string {
  switch (env.event_type) {
    case "move_intent":
      return `${env.payload.direction.replaceAll("_", " ")}${env.payload.speed === null ? "" : ` · ${env.payload.speed}`}`;
    case "weapon_fire_intent": {
      const target = env.payload.target_mech_id === null ? "target" : env.payload.target_mech_id;
      return `${env.payload.weapon_id.split(".").pop() ?? env.payload.weapon_id} → ${target}`;
    }
    case "mode_switch_intent":
      return `switch → ${env.payload.target_mode}`;
    case "vent_intent":
      return "dump boiler heat";
  }
}

function resolvesIntent(intent: Telegraph, env: SOEventEnvelope): boolean {
  if (env.envelope.causation_id === intent.messageId) return true;
  if (env.subject.mech_id !== intent.mechId) return false;
  if (intent.kind === "MOVE") return env.event_type === "movement_resolved";
  if (intent.kind === "FIRE") return env.event_type === "weapon_fired";
  if (intent.kind === "MODE") {
    return (
      env.event_type === "mode_transition_started" || env.event_type === "mode_transition_completed"
    );
  }
  return env.event_type === "boiler_updated" || env.event_type === "heat_redline_exited";
}

/** Fold intent/resolution pairs into a compact telegraph strip. */
export function buildTelegraphs(rows: readonly RiverRow[], sides: SideMap): readonly Telegraph[] {
  const pending = new Map<string, Telegraph>();
  const resolved: Telegraph[] = [];
  for (const row of orderRows(rows)) {
    const { env } = row;
    if (isIntent(env)) {
      const kind = intentKind(env);
      const item: Telegraph = {
        messageId: env.envelope.message_id,
        mechId: env.subject.mech_id,
        side: sideOf(env, sides),
        kind,
        label: intentLabel(env),
        tick: env.tick,
        status: "TELEGRAPHED",
      };
      pending.set(item.messageId, item);
      continue;
    }
    if (env.event_type === "pilot_decision_made") {
      for (const [messageId, item] of pending) {
        if (item.mechId === env.subject.mech_id) pending.delete(messageId);
      }
      continue;
    }
    const match = [...pending.values()].find((item) => resolvesIntent(item, env));
    if (match !== undefined) {
      pending.delete(match.messageId);
      resolved.push({ ...match, status: "RESOLVED", tick: env.tick });
    }
  }
  return [...resolved.slice(-TELEGRAPH_WINDOW), ...pending.values()].slice(-TELEGRAPH_WINDOW);
}

/** The latest notable canonical events, suitable for a small tactical recap. */
export function buildRecap(rows: readonly RiverRow[], sides: SideMap): readonly RecapEntry[] {
  const notable = new Set<SOEventEnvelope["event_type"]>([
    "pilot_decision_made",
    "movement_resolved",
    "hit_resolved",
    "damage_applied",
    "boiler_ruptured",
    "mech_destroyed",
    "victory_declared",
    "match_ended",
  ]);
  return orderRows(rows)
    .filter((row) => notable.has(row.env.event_type))
    .slice(-RECAP_WINDOW)
    .reverse()
    .map((row) => ({
      eventId: row.env.event_id,
      tick: row.env.tick,
      side: sideOf(row.env, sides),
      label: summarizeEnvelope(row.env),
    }));
}

/** Latest per-mech pilot decision, rendered as a safe read-only decision card. */
export function buildDecisionCards(
  rows: readonly RiverRow[],
  sides: SideMap,
): readonly DecisionCard[] {
  const latest = new Map<string, DecisionCard>();
  for (const row of orderRows(rows)) {
    if (row.env.event_type !== "pilot_decision_made") continue;
    latest.set(row.env.subject.mech_id, {
      mechId: row.env.subject.mech_id,
      side: sideOf(row.env, sides),
      action: row.env.payload.action,
      reason: row.env.payload.reason_code,
      rationale: row.env.payload.rationale,
      confidence: row.env.payload.confidence,
      tick: row.env.tick,
    });
  }
  return [...latest.values()].sort((left, right) => left.side.localeCompare(right.side));
}

/** Project the canonical terminal score into a small league-style overlay. */
export function buildLeague(rows: readonly RiverRow[], sides: SideMap): LeagueSnapshot | null {
  const scored = orderRows(rows)
    .map((row) => row.env)
    .filter(
      (env): env is Extract<SOEventEnvelope, { event_type: "match_scored" }> =>
        env.event_type === "match_scored",
    )
    .at(-1);
  if (scored === undefined) return null;
  const entries = Object.entries(scored.payload.scores)
    .map(([playerId, score]) => ({
      playerId,
      side: sides.byPlayer.get(playerId) ?? "neutral",
      score: score.final_score,
      damageDealt: score.damage_dealt,
      efficiency: score.damage_efficiency,
      winner: playerId === scored.payload.winner_player_id,
    }))
    .sort((left, right) => right.score - left.score);
  return { durationTicks: scored.payload.duration_ticks, isDraw: scored.payload.is_draw, entries };
}
