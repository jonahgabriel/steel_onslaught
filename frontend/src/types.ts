/**
 * Hand-written TS mirror of the Python event payloads — Task 31.
 *
 * Type-mirror policy (chosen, not optional): these types are written by hand;
 * `__tests__/types_parity.test.ts` parses every Python-emitted fixture under
 * `__tests__/fixtures/` through `parseEnvelope`.  Any field added or renamed
 * in a Python event payload breaks that test until this file is updated.
 *
 * Parsers consume `unknown` and construct fresh, fully typed objects field by
 * field — no `any`, no unchecked casts.  Closed payloads reject unknown
 * fields; intent payloads (`*_intent`, `pilot_injured`) mirror Python's open
 * `dict[str, Any]` as `Record<string, JsonValue>`.
 */

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

// ---------------------------------------------------------------------------
// Event type enum (mirror of steel_onslaught.events.envelope.SOEventType)
// ---------------------------------------------------------------------------

export const SO_EVENT_TYPES = [
  "match_started",
  "match_tick",
  "mech_spawned",
  "sensor_observation",
  "pilot_decision_made",
  "move_intent",
  "weapon_fire_intent",
  "mode_switch_intent",
  "vent_intent",
  "movement_resolved",
  "boiler_updated",
  "heat_redline_entered",
  "heat_redline_exited",
  "boiler_overloaded",
  "boiler_ruptured",
  "mode_transition_started",
  "mode_transition_completed",
  "weapon_fired",
  "hit_resolved",
  "armor_absorbed",
  "damage_applied",
  "pilot_injured",
  "pilot_killed",
  "mech_destroyed",
  "victory_declared",
  "match_ended",
  "match_scored",
] as const;

export type SOEventType = (typeof SO_EVENT_TYPES)[number];

// ---------------------------------------------------------------------------
// Shared structures
// ---------------------------------------------------------------------------

export interface SOEventSubject {
  mech_id: string;
  player_id: string;
}

export interface SOPosition {
  x: number;
  y: number;
}

/** Mirror of steel_onslaught.contracts.boiler.ModelSOBoilerState. */
export interface SOBoilerState {
  schema_version: string;
  kind: string;
  match_id: string;
  mech_id: string;
  tick: number;
  pressure_current: number;
  pressure_maximum: number;
  regeneration_per_tick: number;
  heat_current: number;
  heat_redline_threshold: number;
  heat_rupture_threshold: number;
  heat_vent_rate: number;
  status_redline: boolean;
  status_rupture_warning: boolean;
  status_disabled: boolean;
  status_ruptured: boolean;
  modifier_heat_weapon_pressure: number;
  modifier_venting_penalty: number;
  modifier_mode_switch_heat_delta: number;
}

/** Mirror of steel_onslaught.match.state.ModelSOMechRuntimeState. */
export interface SOMechRuntimeState {
  schema_version: string;
  kind: string;
  mech_id: string;
  player_id: string;
  loadout_id: string;
  pilot_id: string;
  chassis_id: string;
  chassis_class: "light" | "medium" | "heavy";
  sensor_ids: string[];
  gizmo_ids: string[];
  base_speed: number;
  position: SOPosition;
  facing: number;
  speed: number;
  hp: number;
  hp_max: number;
  armor_value: number;
  armor_max: number;
  alive: boolean;
  pilot_alive: boolean;
  current_mode: string;
  mode_lock_until: number;
  transition_ticks_remaining: number;
  transition_to_mode: string | null;
  sensor_dropout_ticks_remaining: number;
  mode_switch_disabled_until: number;
  weapon_cooldowns: Record<string, number>;
  evasion: number;
  accuracy_penalty_next_fire: number;
  jamming_intensity: number;
  under_sensor_lock: boolean;
  boiler: SOBoilerState;
  redline_consecutive_ticks: number;
  overloaded: boolean;
  overloaded_consecutive_ticks: number;
}

// ---------------------------------------------------------------------------
// Per-event payloads
// ---------------------------------------------------------------------------

export interface MatchStartedPayload {
  seed: number;
  max_ticks: number;
  mechs: SOMechRuntimeState[];
}

export type MatchTickPayload = Record<string, never>;

export interface MechSpawnedPayload {
  position: SOPosition;
  facing: number;
}

export interface SensorObservationPayload {
  enemy_mech_id: string;
  distance_estimate: number;
  confidence: number;
  heat_estimate?: number;
  mode_estimate?: string;
}

export interface ConsideredAction {
  action: string;
  score: number;
}

export interface PilotDecisionMadePayload {
  action: string;
  action_params: Record<string, JsonValue>;
  reason_code: string;
  confidence: number;
  considered_actions: ConsideredAction[];
}

/** Intent payloads mirror Python's open `dict[str, Any]` action params. */
export type IntentPayload = Record<string, JsonValue>;

export interface MovementResolvedPayload {
  from: SOPosition;
  to: SOPosition;
  ticks_consumed: number;
  pressure_consumed: number;
}

export interface BoilerUpdatedPayload {
  pressure_before: number;
  pressure_after: number;
  heat_before: number;
  heat_after: number;
}

export interface HeatRedlinePayload {
  heat: number;
  redline_threshold: number;
}

export interface BoilerOverloadedPayload {
  heat: number;
  redline_threshold: number;
  redline_consecutive_ticks: number;
  accuracy_penalty_next_fire: number;
  mode_switch_disabled_until: number;
}

export interface BoilerRupturedPayload {
  cause: string;
  heat: number;
  rupture_threshold: number;
  direct_damage: number;
  area_damage: number;
  area_radius_cells: number;
}

export interface ModeTransitionCosts {
  pressure: number;
  heat: number;
  transition_ticks: number;
}

export interface ModeTransitionStartedPayload {
  from_mode: string;
  to_mode: string;
  costs: ModeTransitionCosts;
  sensor_dropout_ticks: number;
  evasion_penalty: number;
}

export interface ModeTransitionCompletedPayload {
  from_mode: string;
  new_mode: string;
  mode_lock_until: number;
}

export interface WeaponFiredPayload {
  weapon_id: string;
  target_id: string;
  hit_probability: number;
  pressure_cost: number;
  heat_generated: number;
}

export interface HitResult {
  hit: boolean;
  damage_after_armor: number;
}

export interface HitResolvedPayload {
  attacker_id: string;
  defender_id: string;
  result: HitResult;
}

export interface ArmorAbsorbedPayload {
  target_id: string;
  absorbed_amount: number;
  armor_after: number;
}

export interface DamageAppliedPayload {
  target_id: string;
  damage: number;
  cause: string;
  hp_after: number;
  source_mech_id?: string;
  radius_cells?: number;
}

/** No Python emitter yet (design-declared); open record until one lands. */
export type PilotInjuredPayload = Record<string, JsonValue>;

export interface PilotKilledPayload {
  mech_id: string;
  survival_probability: number;
  roll: number;
  safety_gizmos_equipped: number;
}

export interface MechDestroyedPayload {
  cause: string;
  source_mech_id?: string;
}

export interface VictoryDeclaredPayload {
  winner_player_id: string;
  reason: string;
}

export interface MatchEndedPayload {
  reason: string;
  winner_id: string | null;
}

export interface SOPlayerScore {
  victory: number;
  damage_dealt: number;
  damage_efficiency: number;
  pressure_efficiency: number;
  overload_penalty: number;
  replay_validity: number;
  final_score: number;
}

export interface SOScoredWinner {
  player_id: string;
  mech_id: string;
}

export interface MatchScoredPayload {
  kind: string;
  match_id: string;
  winner: SOScoredWinner | null;
  scores: Record<string, SOPlayerScore>;
  winner_player_id: string;
  winner_loadout_id: string;
  winner_score: number;
  loser_player_id: string;
  loser_score: number;
  duration_ticks: number;
  scored_at: string;
  is_draw: boolean;
}

export interface PayloadMap {
  match_started: MatchStartedPayload;
  match_tick: MatchTickPayload;
  mech_spawned: MechSpawnedPayload;
  sensor_observation: SensorObservationPayload;
  pilot_decision_made: PilotDecisionMadePayload;
  move_intent: IntentPayload;
  weapon_fire_intent: IntentPayload;
  mode_switch_intent: IntentPayload;
  vent_intent: IntentPayload;
  movement_resolved: MovementResolvedPayload;
  boiler_updated: BoilerUpdatedPayload;
  heat_redline_entered: HeatRedlinePayload;
  heat_redline_exited: HeatRedlinePayload;
  boiler_overloaded: BoilerOverloadedPayload;
  boiler_ruptured: BoilerRupturedPayload;
  mode_transition_started: ModeTransitionStartedPayload;
  mode_transition_completed: ModeTransitionCompletedPayload;
  weapon_fired: WeaponFiredPayload;
  hit_resolved: HitResolvedPayload;
  armor_absorbed: ArmorAbsorbedPayload;
  damage_applied: DamageAppliedPayload;
  pilot_injured: PilotInjuredPayload;
  pilot_killed: PilotKilledPayload;
  mech_destroyed: MechDestroyedPayload;
  victory_declared: VictoryDeclaredPayload;
  match_ended: MatchEndedPayload;
  match_scored: MatchScoredPayload;
}

// ---------------------------------------------------------------------------
// Envelope (mirror of ModelSOEventEnvelope) — discriminated on event_type
// ---------------------------------------------------------------------------

/** The composed ONEX ModelEnvelope — tracing identity + causation chain. */
interface OnexEnvelope {
  message_id: string;
  correlation_id: string;
  causation_id: string | null;
  emitted_at: string;
  entity_id: string;
}

interface EnvelopeBase {
  schema_version: string;
  event_id: string;
  match_id: string;
  tick: number;
  sequence_in_tick: number;
  producer_node: string;
  subject: SOEventSubject;
  /** The ONEX canonical envelope (correlation/causation/identity). */
  envelope: OnexEnvelope;
}

export type SOEventEnvelope = {
  [K in SOEventType]: EnvelopeBase & { event_type: K; payload: PayloadMap[K] };
}[SOEventType];

export type SOEventEnvelopeOf<K extends SOEventType> = Extract<SOEventEnvelope, { event_type: K }>;

// ---------------------------------------------------------------------------
// Parsing primitives
// ---------------------------------------------------------------------------

class ParseError extends Error {}

function fail(context: string, message: string): never {
  throw new ParseError(`${context}: ${message}`);
}

function asRecord(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(context, `expected an object, got ${typeof value}`);
  }
  return Object.fromEntries(Object.entries(value));
}

function rejectUnknown(
  record: Record<string, unknown>,
  allowed: readonly string[],
  context: string,
): void {
  for (const key of Object.keys(record)) {
    if (!allowed.includes(key)) {
      fail(context, `unknown field ${JSON.stringify(key)}`);
    }
  }
}

function str(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key];
  if (typeof value !== "string") {
    fail(context, `field ${JSON.stringify(key)} must be a string, got ${typeof value}`);
  }
  return value;
}

function num(record: Record<string, unknown>, key: string, context: string): number {
  const value = record[key];
  if (typeof value !== "number" || Number.isNaN(value)) {
    fail(context, `field ${JSON.stringify(key)} must be a number, got ${typeof value}`);
  }
  return value;
}

function bool(record: Record<string, unknown>, key: string, context: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
    fail(context, `field ${JSON.stringify(key)} must be a boolean, got ${typeof value}`);
  }
  return value;
}

function nullableStr(record: Record<string, unknown>, key: string, context: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string") {
    fail(context, `field ${JSON.stringify(key)} must be a string or null, got ${typeof value}`);
  }
  return value;
}

function optionalNum(
  record: Record<string, unknown>,
  key: string,
  context: string,
): number | undefined {
  if (!(key in record)) {
    return undefined;
  }
  return num(record, key, context);
}

function optionalStr(
  record: Record<string, unknown>,
  key: string,
  context: string,
): string | undefined {
  if (!(key in record)) {
    return undefined;
  }
  return str(record, key, context);
}

function strArray(record: Record<string, unknown>, key: string, context: string): string[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    fail(context, `field ${JSON.stringify(key)} must be an array`);
  }
  return value.map((item, index) => {
    if (typeof item !== "string") {
      fail(context, `field ${JSON.stringify(key)}[${index}] must be a string`);
    }
    return item;
  });
}

function asJsonValue(value: unknown, context: string): JsonValue {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && !Number.isNaN(value))
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => asJsonValue(item, `${context}[${index}]`));
  }
  if (typeof value === "object") {
    const result: { [key: string]: JsonValue } = {};
    for (const [key, item] of Object.entries(value)) {
      result[key] = asJsonValue(item, `${context}.${key}`);
    }
    return result;
  }
  fail(context, `not a JSON value: ${typeof value}`);
}

function openRecord(value: unknown, context: string): Record<string, JsonValue> {
  const record = asRecord(value, context);
  const result: Record<string, JsonValue> = {};
  for (const [key, item] of Object.entries(record)) {
    result[key] = asJsonValue(item, `${context}.${key}`);
  }
  return result;
}

function numRecord(
  record: Record<string, unknown>,
  key: string,
  context: string,
): Record<string, number> {
  const inner = asRecord(record[key], `${context}.${key}`);
  const result: Record<string, number> = {};
  for (const [innerKey, value] of Object.entries(inner)) {
    if (typeof value !== "number" || Number.isNaN(value)) {
      fail(context, `field ${JSON.stringify(key)}.${innerKey} must be a number`);
    }
    result[innerKey] = value;
  }
  return result;
}

// ---------------------------------------------------------------------------
// Structure parsers
// ---------------------------------------------------------------------------

function parsePosition(value: unknown, context: string): SOPosition {
  const record = asRecord(value, context);
  rejectUnknown(record, ["x", "y"], context);
  return { x: num(record, "x", context), y: num(record, "y", context) };
}

function parseSubject(value: unknown, context: string): SOEventSubject {
  const record = asRecord(value, context);
  rejectUnknown(record, ["mech_id", "player_id"], context);
  return {
    mech_id: str(record, "mech_id", context),
    player_id: str(record, "player_id", context),
  };
}

const BOILER_FIELDS = [
  "schema_version",
  "kind",
  "match_id",
  "mech_id",
  "tick",
  "pressure_current",
  "pressure_maximum",
  "regeneration_per_tick",
  "heat_current",
  "heat_redline_threshold",
  "heat_rupture_threshold",
  "heat_vent_rate",
  "status_redline",
  "status_rupture_warning",
  "status_disabled",
  "status_ruptured",
  "modifier_heat_weapon_pressure",
  "modifier_venting_penalty",
  "modifier_mode_switch_heat_delta",
] as const;

function parseBoilerState(value: unknown, context: string): SOBoilerState {
  const record = asRecord(value, context);
  rejectUnknown(record, BOILER_FIELDS, context);
  return {
    schema_version: str(record, "schema_version", context),
    kind: str(record, "kind", context),
    match_id: str(record, "match_id", context),
    mech_id: str(record, "mech_id", context),
    tick: num(record, "tick", context),
    pressure_current: num(record, "pressure_current", context),
    pressure_maximum: num(record, "pressure_maximum", context),
    regeneration_per_tick: num(record, "regeneration_per_tick", context),
    heat_current: num(record, "heat_current", context),
    heat_redline_threshold: num(record, "heat_redline_threshold", context),
    heat_rupture_threshold: num(record, "heat_rupture_threshold", context),
    heat_vent_rate: num(record, "heat_vent_rate", context),
    status_redline: bool(record, "status_redline", context),
    status_rupture_warning: bool(record, "status_rupture_warning", context),
    status_disabled: bool(record, "status_disabled", context),
    status_ruptured: bool(record, "status_ruptured", context),
    modifier_heat_weapon_pressure: num(record, "modifier_heat_weapon_pressure", context),
    modifier_venting_penalty: num(record, "modifier_venting_penalty", context),
    modifier_mode_switch_heat_delta: num(record, "modifier_mode_switch_heat_delta", context),
  };
}

const MECH_FIELDS = [
  "schema_version",
  "kind",
  "mech_id",
  "player_id",
  "loadout_id",
  "pilot_id",
  "chassis_id",
  "chassis_class",
  "sensor_ids",
  "gizmo_ids",
  "base_speed",
  "position",
  "facing",
  "speed",
  "hp",
  "hp_max",
  "armor_value",
  "armor_max",
  "alive",
  "pilot_alive",
  "current_mode",
  "mode_lock_until",
  "transition_ticks_remaining",
  "transition_to_mode",
  "sensor_dropout_ticks_remaining",
  "mode_switch_disabled_until",
  "weapon_cooldowns",
  "evasion",
  "accuracy_penalty_next_fire",
  "jamming_intensity",
  "under_sensor_lock",
  "boiler",
  "redline_consecutive_ticks",
  "overloaded",
  "overloaded_consecutive_ticks",
] as const;

function parseChassisClass(value: unknown, context: string): "light" | "medium" | "heavy" {
  if (value === "light" || value === "medium" || value === "heavy") {
    return value;
  }
  fail(context, `chassis_class must be light|medium|heavy, got ${JSON.stringify(value)}`);
}

function parseMechState(value: unknown, context: string): SOMechRuntimeState {
  const record = asRecord(value, context);
  rejectUnknown(record, MECH_FIELDS, context);
  return {
    schema_version: str(record, "schema_version", context),
    kind: str(record, "kind", context),
    mech_id: str(record, "mech_id", context),
    player_id: str(record, "player_id", context),
    loadout_id: str(record, "loadout_id", context),
    pilot_id: str(record, "pilot_id", context),
    chassis_id: str(record, "chassis_id", context),
    chassis_class: parseChassisClass(record["chassis_class"], context),
    sensor_ids: strArray(record, "sensor_ids", context),
    gizmo_ids: strArray(record, "gizmo_ids", context),
    base_speed: num(record, "base_speed", context),
    position: parsePosition(record["position"], `${context}.position`),
    facing: num(record, "facing", context),
    speed: num(record, "speed", context),
    hp: num(record, "hp", context),
    hp_max: num(record, "hp_max", context),
    armor_value: num(record, "armor_value", context),
    armor_max: num(record, "armor_max", context),
    alive: bool(record, "alive", context),
    pilot_alive: bool(record, "pilot_alive", context),
    current_mode: str(record, "current_mode", context),
    mode_lock_until: num(record, "mode_lock_until", context),
    transition_ticks_remaining: num(record, "transition_ticks_remaining", context),
    transition_to_mode: nullableStr(record, "transition_to_mode", context),
    sensor_dropout_ticks_remaining: num(record, "sensor_dropout_ticks_remaining", context),
    mode_switch_disabled_until: num(record, "mode_switch_disabled_until", context),
    weapon_cooldowns: numRecord(record, "weapon_cooldowns", context),
    evasion: num(record, "evasion", context),
    accuracy_penalty_next_fire: num(record, "accuracy_penalty_next_fire", context),
    jamming_intensity: num(record, "jamming_intensity", context),
    under_sensor_lock: bool(record, "under_sensor_lock", context),
    boiler: parseBoilerState(record["boiler"], `${context}.boiler`),
    redline_consecutive_ticks: num(record, "redline_consecutive_ticks", context),
    overloaded: bool(record, "overloaded", context),
    overloaded_consecutive_ticks: num(record, "overloaded_consecutive_ticks", context),
  };
}

// ---------------------------------------------------------------------------
// Payload parsers (closed unless the Python side is an open dict)
// ---------------------------------------------------------------------------

type PayloadParsers = { [K in SOEventType]: (value: unknown, context: string) => PayloadMap[K] };

const PAYLOAD_PARSERS: PayloadParsers = {
  match_started: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["seed", "max_ticks", "mechs"], context);
    const mechs = record["mechs"];
    if (!Array.isArray(mechs)) {
      fail(context, 'field "mechs" must be an array');
    }
    return {
      seed: num(record, "seed", context),
      max_ticks: num(record, "max_ticks", context),
      mechs: mechs.map((mech, index) => parseMechState(mech, `${context}.mechs[${index}]`)),
    };
  },
  match_tick: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, [], context);
    return {};
  },
  mech_spawned: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["position", "facing"], context);
    return {
      position: parsePosition(record["position"], `${context}.position`),
      facing: num(record, "facing", context),
    };
  },
  sensor_observation: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["enemy_mech_id", "distance_estimate", "confidence", "heat_estimate", "mode_estimate"],
      context,
    );
    return {
      enemy_mech_id: str(record, "enemy_mech_id", context),
      distance_estimate: num(record, "distance_estimate", context),
      confidence: num(record, "confidence", context),
      heat_estimate: optionalNum(record, "heat_estimate", context),
      mode_estimate: optionalStr(record, "mode_estimate", context),
    };
  },
  pilot_decision_made: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["action", "action_params", "reason_code", "confidence", "considered_actions"],
      context,
    );
    const considered = record["considered_actions"];
    if (!Array.isArray(considered)) {
      fail(context, 'field "considered_actions" must be an array');
    }
    return {
      action: str(record, "action", context),
      action_params: openRecord(record["action_params"], `${context}.action_params`),
      reason_code: str(record, "reason_code", context),
      confidence: num(record, "confidence", context),
      considered_actions: considered.map((item, index) => {
        const inner = asRecord(item, `${context}.considered_actions[${index}]`);
        rejectUnknown(inner, ["action", "score"], `${context}.considered_actions[${index}]`);
        return {
          action: str(inner, "action", context),
          score: num(inner, "score", context),
        };
      }),
    };
  },
  move_intent: (value, context) => openRecord(value, context),
  weapon_fire_intent: (value, context) => openRecord(value, context),
  mode_switch_intent: (value, context) => openRecord(value, context),
  vent_intent: (value, context) => openRecord(value, context),
  movement_resolved: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["from", "to", "ticks_consumed", "pressure_consumed"], context);
    return {
      from: parsePosition(record["from"], `${context}.from`),
      to: parsePosition(record["to"], `${context}.to`),
      ticks_consumed: num(record, "ticks_consumed", context),
      pressure_consumed: num(record, "pressure_consumed", context),
    };
  },
  boiler_updated: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["pressure_before", "pressure_after", "heat_before", "heat_after"],
      context,
    );
    return {
      pressure_before: num(record, "pressure_before", context),
      pressure_after: num(record, "pressure_after", context),
      heat_before: num(record, "heat_before", context),
      heat_after: num(record, "heat_after", context),
    };
  },
  heat_redline_entered: (value, context) => parseHeatRedline(value, context),
  heat_redline_exited: (value, context) => parseHeatRedline(value, context),
  boiler_overloaded: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      [
        "heat",
        "redline_threshold",
        "redline_consecutive_ticks",
        "accuracy_penalty_next_fire",
        "mode_switch_disabled_until",
      ],
      context,
    );
    return {
      heat: num(record, "heat", context),
      redline_threshold: num(record, "redline_threshold", context),
      redline_consecutive_ticks: num(record, "redline_consecutive_ticks", context),
      accuracy_penalty_next_fire: num(record, "accuracy_penalty_next_fire", context),
      mode_switch_disabled_until: num(record, "mode_switch_disabled_until", context),
    };
  },
  boiler_ruptured: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["cause", "heat", "rupture_threshold", "direct_damage", "area_damage", "area_radius_cells"],
      context,
    );
    return {
      cause: str(record, "cause", context),
      heat: num(record, "heat", context),
      rupture_threshold: num(record, "rupture_threshold", context),
      direct_damage: num(record, "direct_damage", context),
      area_damage: num(record, "area_damage", context),
      area_radius_cells: num(record, "area_radius_cells", context),
    };
  },
  mode_transition_started: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["from_mode", "to_mode", "costs", "sensor_dropout_ticks", "evasion_penalty"],
      context,
    );
    const costs = asRecord(record["costs"], `${context}.costs`);
    rejectUnknown(costs, ["pressure", "heat", "transition_ticks"], `${context}.costs`);
    return {
      from_mode: str(record, "from_mode", context),
      to_mode: str(record, "to_mode", context),
      costs: {
        pressure: num(costs, "pressure", context),
        heat: num(costs, "heat", context),
        transition_ticks: num(costs, "transition_ticks", context),
      },
      sensor_dropout_ticks: num(record, "sensor_dropout_ticks", context),
      evasion_penalty: num(record, "evasion_penalty", context),
    };
  },
  mode_transition_completed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["from_mode", "new_mode", "mode_lock_until"], context);
    return {
      from_mode: str(record, "from_mode", context),
      new_mode: str(record, "new_mode", context),
      mode_lock_until: num(record, "mode_lock_until", context),
    };
  },
  weapon_fired: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["weapon_id", "target_id", "hit_probability", "pressure_cost", "heat_generated"],
      context,
    );
    return {
      weapon_id: str(record, "weapon_id", context),
      target_id: str(record, "target_id", context),
      hit_probability: num(record, "hit_probability", context),
      pressure_cost: num(record, "pressure_cost", context),
      heat_generated: num(record, "heat_generated", context),
    };
  },
  hit_resolved: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["attacker_id", "defender_id", "result"], context);
    const result = asRecord(record["result"], `${context}.result`);
    rejectUnknown(result, ["hit", "damage_after_armor"], `${context}.result`);
    return {
      attacker_id: str(record, "attacker_id", context),
      defender_id: str(record, "defender_id", context),
      result: {
        hit: bool(result, "hit", context),
        damage_after_armor: num(result, "damage_after_armor", context),
      },
    };
  },
  armor_absorbed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["target_id", "absorbed_amount", "armor_after"], context);
    return {
      target_id: str(record, "target_id", context),
      absorbed_amount: num(record, "absorbed_amount", context),
      armor_after: num(record, "armor_after", context),
    };
  },
  damage_applied: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["target_id", "damage", "cause", "hp_after", "source_mech_id", "radius_cells"],
      context,
    );
    return {
      target_id: str(record, "target_id", context),
      damage: num(record, "damage", context),
      cause: str(record, "cause", context),
      hp_after: num(record, "hp_after", context),
      source_mech_id: optionalStr(record, "source_mech_id", context),
      radius_cells: optionalNum(record, "radius_cells", context),
    };
  },
  pilot_injured: (value, context) => openRecord(value, context),
  pilot_killed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["mech_id", "survival_probability", "roll", "safety_gizmos_equipped"],
      context,
    );
    return {
      mech_id: str(record, "mech_id", context),
      survival_probability: num(record, "survival_probability", context),
      roll: num(record, "roll", context),
      safety_gizmos_equipped: num(record, "safety_gizmos_equipped", context),
    };
  },
  mech_destroyed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["cause", "source_mech_id"], context);
    return {
      cause: str(record, "cause", context),
      source_mech_id: optionalStr(record, "source_mech_id", context),
    };
  },
  victory_declared: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["winner_player_id", "reason"], context);
    return {
      winner_player_id: str(record, "winner_player_id", context),
      reason: str(record, "reason", context),
    };
  },
  match_ended: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["reason", "winner_id"], context);
    return {
      reason: str(record, "reason", context),
      winner_id: nullableStr(record, "winner_id", context),
    };
  },
  match_scored: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      [
        "kind",
        "match_id",
        "winner",
        "scores",
        "winner_player_id",
        "winner_loadout_id",
        "winner_score",
        "loser_player_id",
        "loser_score",
        "duration_ticks",
        "scored_at",
        "is_draw",
      ],
      context,
    );
    const winnerValue = record["winner"];
    let winner: SOScoredWinner | null = null;
    if (winnerValue !== null && winnerValue !== undefined) {
      const winnerRecord = asRecord(winnerValue, `${context}.winner`);
      rejectUnknown(winnerRecord, ["player_id", "mech_id"], `${context}.winner`);
      winner = {
        player_id: str(winnerRecord, "player_id", context),
        mech_id: str(winnerRecord, "mech_id", context),
      };
    }
    const scoresRecord = asRecord(record["scores"], `${context}.scores`);
    const scores: Record<string, SOPlayerScore> = {};
    for (const [playerId, scoreValue] of Object.entries(scoresRecord)) {
      const score = asRecord(scoreValue, `${context}.scores.${playerId}`);
      rejectUnknown(
        score,
        [
          "victory",
          "damage_dealt",
          "damage_efficiency",
          "pressure_efficiency",
          "overload_penalty",
          "replay_validity",
          "final_score",
        ],
        `${context}.scores.${playerId}`,
      );
      scores[playerId] = {
        victory: num(score, "victory", context),
        damage_dealt: num(score, "damage_dealt", context),
        damage_efficiency: num(score, "damage_efficiency", context),
        pressure_efficiency: num(score, "pressure_efficiency", context),
        overload_penalty: num(score, "overload_penalty", context),
        replay_validity: num(score, "replay_validity", context),
        final_score: num(score, "final_score", context),
      };
    }
    return {
      kind: str(record, "kind", context),
      match_id: str(record, "match_id", context),
      winner,
      scores,
      winner_player_id: str(record, "winner_player_id", context),
      winner_loadout_id: str(record, "winner_loadout_id", context),
      winner_score: num(record, "winner_score", context),
      loser_player_id: str(record, "loser_player_id", context),
      loser_score: num(record, "loser_score", context),
      duration_ticks: num(record, "duration_ticks", context),
      scored_at: str(record, "scored_at", context),
      is_draw: bool(record, "is_draw", context),
    };
  },
};

function parseHeatRedline(value: unknown, context: string): HeatRedlinePayload {
  const record = asRecord(value, context);
  rejectUnknown(record, ["heat", "redline_threshold"], context);
  return {
    heat: num(record, "heat", context),
    redline_threshold: num(record, "redline_threshold", context),
  };
}

// ---------------------------------------------------------------------------
// Envelope parser
// ---------------------------------------------------------------------------

const ENVELOPE_FIELDS = [
  "schema_version",
  "event_id",
  "match_id",
  "tick",
  "sequence_in_tick",
  "producer_node",
  "subject",
  "event_type",
  "payload",
  "envelope",
] as const;

const ONEX_ENVELOPE_FIELDS = [
  "message_id",
  "correlation_id",
  "causation_id",
  "emitted_at",
  "entity_id",
] as const;

function isEventType(value: string): value is SOEventType {
  return (SO_EVENT_TYPES as readonly string[]).includes(value);
}

function buildEnvelope(
  base: EnvelopeBase,
  eventType: SOEventType,
  payloadValue: unknown,
): SOEventEnvelope {
  // event_type and payload are correlated by construction: PAYLOAD_PARSERS is
  // keyed by the same event_type literal used as the discriminant.  TS cannot
  // express that correlation without 27 duplicate case arms, so it is
  // asserted once here (supertype → union member; not an `any` cast).
  const payload = PAYLOAD_PARSERS[eventType](payloadValue, `payload(${eventType})`);
  return { ...base, event_type: eventType, payload } as SOEventEnvelope;
}

/** Parse one wire envelope (a parsed-JSON value) into a typed SOEventEnvelope. */
export function parseEnvelope(raw: unknown): SOEventEnvelope {
  const context = "envelope";
  const record = asRecord(raw, context);
  rejectUnknown(record, ENVELOPE_FIELDS, context);

  const eventTypeRaw = str(record, "event_type", context);
  if (!isEventType(eventTypeRaw)) {
    fail(context, `unknown event_type ${JSON.stringify(eventTypeRaw)}`);
  }

  const eventId = str(record, "event_id", context);
  if (eventId.length !== 26) {
    fail(context, `event_id must be a 26-char ULID, got length ${eventId.length}`);
  }

  const onexRecord = asRecord(record["envelope"], `${context}.envelope`);
  rejectUnknown(onexRecord, ONEX_ENVELOPE_FIELDS, `${context}.envelope`);
  const matchId = str(record, "match_id", context);
  const entityId = str(onexRecord, "entity_id", `${context}.envelope.entity_id`);
  if (entityId !== matchId) {
    fail(
      `${context}.envelope.entity_id`,
      `must equal match_id ${JSON.stringify(matchId)}, got ${JSON.stringify(entityId)}`,
    );
  }
  const onexEnvelope: OnexEnvelope = {
    message_id: str(onexRecord, "message_id", `${context}.envelope.message_id`),
    correlation_id: str(onexRecord, "correlation_id", `${context}.envelope.correlation_id`),
    causation_id: nullableStr(onexRecord, "causation_id", `${context}.envelope.causation_id`),
    emitted_at: str(onexRecord, "emitted_at", `${context}.envelope.emitted_at`),
    entity_id: entityId,
  };

  const base: EnvelopeBase = {
    schema_version: str(record, "schema_version", context),
    event_id: eventId,
    match_id: matchId,
    tick: num(record, "tick", context),
    sequence_in_tick: num(record, "sequence_in_tick", context),
    producer_node: str(record, "producer_node", context),
    subject: parseSubject(record["subject"], `${context}.subject`),
    envelope: onexEnvelope,
  };

  return buildEnvelope(base, eventTypeRaw, record["payload"]);
}

/** Parse a raw WebSocket text frame into a typed SOEventEnvelope. */
export function parseEnvelopeFrame(frame: string): SOEventEnvelope {
  return parseEnvelope(JSON.parse(frame));
}
