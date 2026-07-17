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
 * fields. Current intent payloads are closed just like their Python models;
 * only legacy `pilot_injured` remains an open JSON record.
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
  "llm_completion_requested",
  "llm_completion_resolved",
  "llm_completion_failed",
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

export type SOModeId = "recon" | "assault" | "evasion";
export type SOPilotAction =
  | "remain"
  | "move"
  | "fire_weapon"
  | "activate_module"
  | "vent"
  | "switch_mode"
  | "emergency_shutdown"
  | "disengage";
export type SOPilotReasonCode =
  | "target_in_range"
  | "mode_advantage"
  | "heat_critical"
  | "closing_distance"
  | "maintain_range"
  | "low_hp_retreat"
  | "low_confidence_hold"
  | "pressure_recovery"
  | "predicted_intercept"
  | "evade_sensor_lock"
  | "no_viable_action"
  | "llm_decision"
  | "llm_fallback";
export type SOMatchEndReason = "last_mech_standing" | "pilot_killed" | "draw_max_ticks" | "aborted";

/** Mirror of steel_onslaught.contracts.boiler.ModelSOBoilerState. */
export interface SOBoilerState {
  schema_version: "0.1.0";
  kind: "steel_onslaught.boiler_state";
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
  schema_version: "0.1.0";
  kind: "steel_onslaught.mech_runtime_state";
  mech_id: string;
  player_id: string;
  side: "red" | "blue" | "neutral";
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
  current_mode: SOModeId;
  mode_lock_until: number;
  transition_ticks_remaining: number;
  transition_to_mode: SOModeId | null;
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
  heat_estimate: number | null;
  mode_estimate: SOModeId | null;
}

export interface ConsideredAction {
  action: SOPilotAction;
  score: number;
}

export interface PilotDecisionMadePayload {
  action: SOPilotAction;
  action_params: Record<string, JsonValue>;
  reason_code: SOPilotReasonCode;
  confidence: number;
  considered_actions: ConsideredAction[];
  rationale: string | null;
}

export interface LlmCompletionRequestedPayload {
  provider_id: string;
  persona_id: string;
  system_prompt_length: number;
  user_prompt_length: number;
}

export interface LlmCompletionResolvedPayload {
  provider_id: string;
  model: string;
  finish_reason: string;
  prompt_tokens: number;
  completion_tokens: number;
  response_length: number;
  cost_usd: number | null;
}

export interface LlmCompletionFailedPayload {
  provider_id: string;
  reason_code: "provider_error" | "invalid_response" | "consumer_error" | "abandoned";
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cost_usd: number | null;
}

export interface MoveIntentPayload {
  direction: "toward_enemy" | "defensive";
  speed: "full" | null;
}

export interface WeaponFireIntentPayload {
  weapon_id: string;
  target_mech_id: string | null;
}

export interface ModeSwitchIntentPayload {
  target_mode: SOModeId;
}

export type VentIntentPayload = Record<string, never>;

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
  from_mode: SOModeId;
  to_mode: SOModeId;
  costs: ModeTransitionCosts;
  sensor_dropout_ticks: number;
  evasion_penalty: number;
}

export interface ModeTransitionCompletedPayload {
  from_mode: SOModeId;
  new_mode: SOModeId;
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
  source_mech_id: string | null;
  radius_cells: number | null;
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
  source_mech_id: string | null;
}

export interface VictoryDeclaredPayload {
  winner_player_id: string;
  reason: SOMatchEndReason;
}

export interface MatchEndedPayload {
  reason: SOMatchEndReason;
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
  kind: "steel_onslaught.match_scored";
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
  llm_completion_requested: LlmCompletionRequestedPayload;
  llm_completion_resolved: LlmCompletionResolvedPayload;
  llm_completion_failed: LlmCompletionFailedPayload;
  move_intent: MoveIntentPayload;
  weapon_fire_intent: WeaponFireIntentPayload;
  mode_switch_intent: ModeSwitchIntentPayload;
  vent_intent: VentIntentPayload;
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

function requireFields(
  record: Record<string, unknown>,
  required: readonly string[],
  context: string,
): void {
  for (const key of required) {
    if (!(key in record)) {
      fail(context, `missing field ${JSON.stringify(key)}`);
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
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(context, `field ${JSON.stringify(key)} must be a finite number, got ${typeof value}`);
  }
  return value;
}

function integer(record: Record<string, unknown>, key: string, context: string): number {
  const value = num(record, key, context);
  if (!Number.isInteger(value)) {
    fail(context, `field ${JSON.stringify(key)} must be an integer`);
  }
  return value;
}

function nonNegativeInt(record: Record<string, unknown>, key: string, context: string): number {
  const value = integer(record, key, context);
  if (value < 0) {
    fail(context, `field ${JSON.stringify(key)} must be >= 0`);
  }
  return value;
}

function positiveInt(record: Record<string, unknown>, key: string, context: string): number {
  const value = integer(record, key, context);
  if (value <= 0) {
    fail(context, `field ${JSON.stringify(key)} must be > 0`);
  }
  return value;
}

function boundedNum(
  record: Record<string, unknown>,
  key: string,
  context: string,
  minimum: number,
  maximum: number,
  maximumExclusive = false,
): number {
  const value = num(record, key, context);
  if (value < minimum || (maximumExclusive ? value >= maximum : value > maximum)) {
    const upper = maximumExclusive ? `< ${maximum}` : `<= ${maximum}`;
    fail(context, `field ${JSON.stringify(key)} must be >= ${minimum} and ${upper}`);
  }
  return value;
}

function boundedInt(
  record: Record<string, unknown>,
  key: string,
  context: string,
  minimum: number,
  maximum: number,
  maximumExclusive = false,
): number {
  const value = integer(record, key, context);
  if (value < minimum || (maximumExclusive ? value >= maximum : value > maximum)) {
    const upper = maximumExclusive ? `< ${maximum}` : `<= ${maximum}`;
    fail(context, `field ${JSON.stringify(key)} must be >= ${minimum} and ${upper}`);
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

function optionalNullableNum(
  record: Record<string, unknown>,
  key: string,
  context: string,
): number | null | undefined {
  if (!(key in record)) {
    return undefined;
  }
  if (record[key] === null) {
    return null;
  }
  return num(record, key, context);
}

function optionalNullableNonNegativeNum(
  record: Record<string, unknown>,
  key: string,
  context: string,
): number | null | undefined {
  const value = optionalNullableNum(record, key, context);
  if (typeof value === "number" && value < 0) {
    fail(context, `field ${JSON.stringify(key)} must be >= 0 or null`);
  }
  return value;
}

function optionalNullableNonNegativeInt(
  record: Record<string, unknown>,
  key: string,
  context: string,
): number | null | undefined {
  const value = optionalNullableNum(record, key, context);
  if (typeof value === "number" && (!Number.isInteger(value) || value < 0)) {
    fail(context, `field ${JSON.stringify(key)} must be a non-negative integer or null`);
  }
  return value;
}

function optionalNullableStr(
  record: Record<string, unknown>,
  key: string,
  context: string,
): string | null | undefined {
  if (!(key in record)) {
    return undefined;
  }
  if (record[key] === null) {
    return null;
  }
  return str(record, key, context);
}

function parseModeId(value: unknown, context: string): SOModeId {
  if (value === "recon" || value === "assault" || value === "evasion") {
    return value;
  }
  fail(context, `mode must be recon|assault|evasion, got ${JSON.stringify(value)}`);
}

function optionalNullableMode(
  record: Record<string, unknown>,
  key: string,
  context: string,
): SOModeId | null | undefined {
  if (!(key in record)) {
    return undefined;
  }
  if (record[key] === null) {
    return null;
  }
  return parseModeId(record[key], `${context}.${key}`);
}

function parsePilotAction(value: unknown, context: string): SOPilotAction {
  if (
    value === "remain" ||
    value === "move" ||
    value === "fire_weapon" ||
    value === "activate_module" ||
    value === "vent" ||
    value === "switch_mode" ||
    value === "emergency_shutdown" ||
    value === "disengage"
  ) {
    return value;
  }
  fail(context, `unknown pilot action ${JSON.stringify(value)}`);
}

function parsePilotReason(value: unknown, context: string): SOPilotReasonCode {
  if (
    value === "target_in_range" ||
    value === "mode_advantage" ||
    value === "heat_critical" ||
    value === "closing_distance" ||
    value === "maintain_range" ||
    value === "low_hp_retreat" ||
    value === "low_confidence_hold" ||
    value === "pressure_recovery" ||
    value === "predicted_intercept" ||
    value === "evade_sensor_lock" ||
    value === "no_viable_action" ||
    value === "llm_decision" ||
    value === "llm_fallback"
  ) {
    return value;
  }
  fail(context, `unknown pilot reason ${JSON.stringify(value)}`);
}

function parseEndReason(value: unknown, context: string): SOMatchEndReason {
  if (
    value === "last_mech_standing" ||
    value === "pilot_killed" ||
    value === "draw_max_ticks" ||
    value === "aborted"
  ) {
    return value;
  }
  fail(context, `unknown match end reason ${JSON.stringify(value)}`);
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
    (typeof value === "number" && Number.isFinite(value))
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
    if (typeof value !== "number" || !Number.isFinite(value) || !Number.isInteger(value)) {
      fail(context, `field ${JSON.stringify(key)}.${innerKey} must be a finite integer`);
    }
    if (value < 0) {
      fail(context, `field ${JSON.stringify(key)}.${innerKey} must be >= 0`);
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
  return { x: integer(record, "x", context), y: integer(record, "y", context) };
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
  requireFields(record, BOILER_FIELDS, context);
  if (record["schema_version"] !== "0.1.0") {
    fail(context, 'field "schema_version" must be "0.1.0"');
  }
  if (record["kind"] !== "steel_onslaught.boiler_state") {
    fail(context, 'field "kind" must be "steel_onslaught.boiler_state"');
  }
  const parsed: SOBoilerState = {
    schema_version: "0.1.0",
    kind: "steel_onslaught.boiler_state",
    match_id: str(record, "match_id", context),
    mech_id: str(record, "mech_id", context),
    tick: nonNegativeInt(record, "tick", context),
    pressure_current: nonNegativeInt(record, "pressure_current", context),
    pressure_maximum: positiveInt(record, "pressure_maximum", context),
    regeneration_per_tick: nonNegativeInt(record, "regeneration_per_tick", context),
    heat_current: nonNegativeInt(record, "heat_current", context),
    heat_redline_threshold: positiveInt(record, "heat_redline_threshold", context),
    heat_rupture_threshold: positiveInt(record, "heat_rupture_threshold", context),
    heat_vent_rate: nonNegativeInt(record, "heat_vent_rate", context),
    status_redline: bool(record, "status_redline", context),
    status_rupture_warning: bool(record, "status_rupture_warning", context),
    status_disabled: bool(record, "status_disabled", context),
    status_ruptured: bool(record, "status_ruptured", context),
    modifier_heat_weapon_pressure: boundedNum(
      record,
      "modifier_heat_weapon_pressure",
      context,
      0,
      Number.MAX_VALUE,
    ),
    modifier_venting_penalty: boundedNum(
      record,
      "modifier_venting_penalty",
      context,
      0,
      Number.MAX_VALUE,
    ),
    modifier_mode_switch_heat_delta: integer(record, "modifier_mode_switch_heat_delta", context),
  };
  if (parsed.heat_current > parsed.heat_rupture_threshold) {
    fail(context, "heat_current must not exceed heat_rupture_threshold");
  }
  return parsed;
}

const MECH_FIELDS = [
  "schema_version",
  "kind",
  "mech_id",
  "player_id",
  "side",
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

function parseSide(value: unknown, context: string): "red" | "blue" | "neutral" {
  if (value === "red" || value === "blue" || value === "neutral") {
    return value;
  }
  fail(context, `side must be red|blue|neutral, got ${JSON.stringify(value)}`);
}

function parseMechState(value: unknown, context: string): SOMechRuntimeState {
  const record = asRecord(value, context);
  rejectUnknown(record, MECH_FIELDS, context);
  requireFields(record, MECH_FIELDS, context);
  if (record["schema_version"] !== "0.1.0") {
    fail(context, 'field "schema_version" must be "0.1.0"');
  }
  if (record["kind"] !== "steel_onslaught.mech_runtime_state") {
    fail(context, 'field "kind" must be "steel_onslaught.mech_runtime_state"');
  }
  const parsed: SOMechRuntimeState = {
    schema_version: "0.1.0",
    kind: "steel_onslaught.mech_runtime_state",
    mech_id: str(record, "mech_id", context),
    player_id: str(record, "player_id", context),
    side: parseSide(record["side"], `${context}.side`),
    loadout_id: str(record, "loadout_id", context),
    pilot_id: str(record, "pilot_id", context),
    chassis_id: str(record, "chassis_id", context),
    chassis_class: parseChassisClass(record["chassis_class"], context),
    sensor_ids: strArray(record, "sensor_ids", context),
    gizmo_ids: strArray(record, "gizmo_ids", context),
    base_speed: positiveInt(record, "base_speed", context),
    position: parsePosition(record["position"], `${context}.position`),
    facing: boundedInt(record, "facing", context, 0, 360, true),
    speed: nonNegativeInt(record, "speed", context),
    hp: nonNegativeInt(record, "hp", context),
    hp_max: positiveInt(record, "hp_max", context),
    armor_value: nonNegativeInt(record, "armor_value", context),
    armor_max: nonNegativeInt(record, "armor_max", context),
    alive: bool(record, "alive", context),
    pilot_alive: bool(record, "pilot_alive", context),
    current_mode: parseModeId(record["current_mode"], `${context}.current_mode`),
    mode_lock_until: nonNegativeInt(record, "mode_lock_until", context),
    transition_ticks_remaining: nonNegativeInt(record, "transition_ticks_remaining", context),
    transition_to_mode: optionalNullableMode(record, "transition_to_mode", context) ?? null,
    sensor_dropout_ticks_remaining: nonNegativeInt(
      record,
      "sensor_dropout_ticks_remaining",
      context,
    ),
    mode_switch_disabled_until: nonNegativeInt(record, "mode_switch_disabled_until", context),
    weapon_cooldowns: numRecord(record, "weapon_cooldowns", context),
    evasion: boundedNum(record, "evasion", context, 0, 1),
    accuracy_penalty_next_fire: boundedNum(record, "accuracy_penalty_next_fire", context, 0, 1),
    jamming_intensity: boundedNum(record, "jamming_intensity", context, 0, 1),
    under_sensor_lock: bool(record, "under_sensor_lock", context),
    boiler: parseBoilerState(record["boiler"], `${context}.boiler`),
    redline_consecutive_ticks: nonNegativeInt(record, "redline_consecutive_ticks", context),
    overloaded: bool(record, "overloaded", context),
    overloaded_consecutive_ticks: nonNegativeInt(record, "overloaded_consecutive_ticks", context),
  };
  if (parsed.hp > parsed.hp_max) {
    fail(context, "hp must not exceed hp_max");
  }
  const inFlight = parsed.transition_ticks_remaining > 0;
  if (inFlight !== (parsed.transition_to_mode !== null)) {
    fail(context, "transition_ticks_remaining and transition_to_mode must be paired");
  }
  return parsed;
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
    if (mechs.length === 0) {
      fail(context, 'field "mechs" must contain at least one mech');
    }
    const parsedMechs = mechs.map((mech, index) =>
      parseMechState(mech, `${context}.mechs[${index}]`),
    );
    if (new Set(parsedMechs.map((mech) => mech.mech_id)).size !== parsedMechs.length) {
      fail(context, 'field "mechs" contains duplicate mech_id values');
    }
    return {
      seed: nonNegativeInt(record, "seed", context),
      max_ticks: positiveInt(record, "max_ticks", context),
      mechs: parsedMechs,
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
      facing: nonNegativeInt(record, "facing", context),
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
      distance_estimate: boundedNum(record, "distance_estimate", context, 0, Number.MAX_VALUE),
      confidence: boundedNum(record, "confidence", context, 0, 1),
      heat_estimate: optionalNullableNonNegativeNum(record, "heat_estimate", context) ?? null,
      mode_estimate: optionalNullableMode(record, "mode_estimate", context) ?? null,
    };
  },
  pilot_decision_made: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["action", "action_params", "reason_code", "confidence", "considered_actions", "rationale"],
      context,
    );
    const considered = record["considered_actions"];
    if (!Array.isArray(considered)) {
      fail(context, 'field "considered_actions" must be an array');
    }
    const action = parsePilotAction(record["action"], `${context}.action`);
    const considered_actions = considered.map((item, index) => {
      const innerContext = `${context}.considered_actions[${index}]`;
      const inner = asRecord(item, innerContext);
      rejectUnknown(inner, ["action", "score"], innerContext);
      return {
        action: parsePilotAction(inner["action"], `${innerContext}.action`),
        score: num(inner, "score", innerContext),
      };
    });
    if (!considered_actions.some((candidate) => candidate.action === action)) {
      fail(context, "considered_actions must include the chosen action");
    }
    const confidence = num(record, "confidence", context);
    return {
      action,
      action_params: openRecord(record["action_params"], `${context}.action_params`),
      reason_code: parsePilotReason(record["reason_code"], `${context}.reason_code`),
      confidence: Math.min(1, Math.max(0, confidence)),
      considered_actions,
      rationale: nullableStr(record, "rationale", context),
    };
  },
  llm_completion_requested: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["provider_id", "persona_id", "system_prompt_length", "user_prompt_length"],
      context,
    );
    return {
      provider_id: str(record, "provider_id", context),
      persona_id: str(record, "persona_id", context),
      system_prompt_length: nonNegativeInt(record, "system_prompt_length", context),
      user_prompt_length: nonNegativeInt(record, "user_prompt_length", context),
    };
  },
  llm_completion_resolved: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      [
        "provider_id",
        "model",
        "finish_reason",
        "prompt_tokens",
        "completion_tokens",
        "response_length",
        "cost_usd",
      ],
      context,
    );
    if (!("cost_usd" in record)) {
      fail(context, "nullable LLM resolved cost field is required");
    }
    return {
      provider_id: str(record, "provider_id", context),
      model: str(record, "model", context),
      finish_reason: str(record, "finish_reason", context),
      prompt_tokens: nonNegativeInt(record, "prompt_tokens", context),
      completion_tokens: nonNegativeInt(record, "completion_tokens", context),
      response_length: nonNegativeInt(record, "response_length", context),
      cost_usd: optionalNullableNonNegativeNum(record, "cost_usd", context) ?? null,
    };
  },
  llm_completion_failed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(
      record,
      ["provider_id", "reason_code", "model", "prompt_tokens", "completion_tokens", "cost_usd"],
      context,
    );
    const reason_code = str(record, "reason_code", context);
    if (
      reason_code !== "provider_error" &&
      reason_code !== "invalid_response" &&
      reason_code !== "consumer_error" &&
      reason_code !== "abandoned"
    ) {
      fail(context, 'field "reason_code" is not a recognized LLM failure reason');
    }
    if (
      !("prompt_tokens" in record) ||
      !("completion_tokens" in record) ||
      !("cost_usd" in record)
    ) {
      fail(context, "nullable LLM failure usage fields are required");
    }
    return {
      provider_id: str(record, "provider_id", context),
      reason_code,
      model: nullableStr(record, "model", context),
      prompt_tokens: optionalNullableNonNegativeInt(record, "prompt_tokens", context) ?? null,
      completion_tokens:
        optionalNullableNonNegativeInt(record, "completion_tokens", context) ?? null,
      cost_usd: optionalNullableNonNegativeNum(record, "cost_usd", context) ?? null,
    };
  },
  move_intent: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["direction", "speed"], context);
    const direction = str(record, "direction", context);
    if (direction !== "toward_enemy" && direction !== "defensive") {
      fail(context, 'field "direction" must be "toward_enemy" or "defensive"');
    }
    const rawSpeed = record["speed"];
    if (rawSpeed !== undefined && rawSpeed !== null && rawSpeed !== "full") {
      fail(context, 'field "speed" must be "full" or null');
    }
    return { direction, speed: rawSpeed ?? null };
  },
  weapon_fire_intent: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["weapon_id", "target_mech_id"], context);
    return {
      weapon_id: str(record, "weapon_id", context),
      target_mech_id: optionalNullableStr(record, "target_mech_id", context) ?? null,
    };
  },
  mode_switch_intent: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["target_mode"], context);
    const target_mode = parseModeId(record["target_mode"], `${context}.target_mode`);
    return { target_mode };
  },
  vent_intent: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, [], context);
    return {};
  },
  movement_resolved: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["from", "to", "ticks_consumed", "pressure_consumed"], context);
    return {
      from: parsePosition(record["from"], `${context}.from`),
      to: parsePosition(record["to"], `${context}.to`),
      ticks_consumed: positiveInt(record, "ticks_consumed", context),
      pressure_consumed: nonNegativeInt(record, "pressure_consumed", context),
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
      pressure_before: nonNegativeInt(record, "pressure_before", context),
      pressure_after: nonNegativeInt(record, "pressure_after", context),
      heat_before: nonNegativeInt(record, "heat_before", context),
      heat_after: nonNegativeInt(record, "heat_after", context),
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
      heat: nonNegativeInt(record, "heat", context),
      redline_threshold: positiveInt(record, "redline_threshold", context),
      redline_consecutive_ticks: positiveInt(record, "redline_consecutive_ticks", context),
      accuracy_penalty_next_fire: boundedNum(record, "accuracy_penalty_next_fire", context, 0, 1),
      mode_switch_disabled_until: nonNegativeInt(record, "mode_switch_disabled_until", context),
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
      heat: nonNegativeInt(record, "heat", context),
      rupture_threshold: positiveInt(record, "rupture_threshold", context),
      direct_damage: nonNegativeInt(record, "direct_damage", context),
      area_damage: nonNegativeInt(record, "area_damage", context),
      area_radius_cells: nonNegativeInt(record, "area_radius_cells", context),
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
      from_mode: parseModeId(record["from_mode"], `${context}.from_mode`),
      to_mode: parseModeId(record["to_mode"], `${context}.to_mode`),
      costs: {
        pressure: nonNegativeInt(costs, "pressure", `${context}.costs`),
        heat: nonNegativeInt(costs, "heat", `${context}.costs`),
        transition_ticks: positiveInt(costs, "transition_ticks", `${context}.costs`),
      },
      sensor_dropout_ticks: nonNegativeInt(record, "sensor_dropout_ticks", context),
      evasion_penalty: boundedNum(record, "evasion_penalty", context, 0, Number.MAX_VALUE),
    };
  },
  mode_transition_completed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["from_mode", "new_mode", "mode_lock_until"], context);
    return {
      from_mode: parseModeId(record["from_mode"], `${context}.from_mode`),
      new_mode: parseModeId(record["new_mode"], `${context}.new_mode`),
      mode_lock_until: nonNegativeInt(record, "mode_lock_until", context),
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
      hit_probability: boundedNum(record, "hit_probability", context, 0, 1),
      pressure_cost: nonNegativeInt(record, "pressure_cost", context),
      heat_generated: nonNegativeInt(record, "heat_generated", context),
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
        damage_after_armor: nonNegativeInt(result, "damage_after_armor", `${context}.result`),
      },
    };
  },
  armor_absorbed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["target_id", "absorbed_amount", "armor_after"], context);
    return {
      target_id: str(record, "target_id", context),
      absorbed_amount: nonNegativeInt(record, "absorbed_amount", context),
      armor_after: nonNegativeInt(record, "armor_after", context),
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
      damage: nonNegativeInt(record, "damage", context),
      cause: str(record, "cause", context),
      hp_after: nonNegativeInt(record, "hp_after", context),
      source_mech_id: optionalNullableStr(record, "source_mech_id", context) ?? null,
      radius_cells: optionalNullableNonNegativeInt(record, "radius_cells", context) ?? null,
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
      survival_probability: boundedNum(record, "survival_probability", context, 0, 1),
      roll: boundedNum(record, "roll", context, 0, 1, true),
      safety_gizmos_equipped: nonNegativeInt(record, "safety_gizmos_equipped", context),
    };
  },
  mech_destroyed: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["cause", "source_mech_id"], context);
    return {
      cause: str(record, "cause", context),
      source_mech_id: optionalNullableStr(record, "source_mech_id", context) ?? null,
    };
  },
  victory_declared: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["winner_player_id", "reason"], context);
    return {
      winner_player_id: str(record, "winner_player_id", context),
      reason: parseEndReason(record["reason"], `${context}.reason`),
    };
  },
  match_ended: (value, context) => {
    const record = asRecord(value, context);
    rejectUnknown(record, ["reason", "winner_id"], context);
    return {
      reason: parseEndReason(record["reason"], `${context}.reason`),
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
    if (record["kind"] !== "steel_onslaught.match_scored") {
      fail(context, 'field "kind" must be "steel_onslaught.match_scored"');
    }
    if (!("winner" in record)) {
      fail(context, 'field "winner" is required');
    }
    const winnerValue = record["winner"];
    let winner: SOScoredWinner | null = null;
    if (winnerValue !== null) {
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
        victory: boundedInt(score, "victory", context, 0, 1),
        damage_dealt: nonNegativeInt(score, "damage_dealt", context),
        damage_efficiency: boundedNum(score, "damage_efficiency", context, 0, Number.MAX_VALUE),
        pressure_efficiency: boundedNum(score, "pressure_efficiency", context, 0, 1),
        overload_penalty: nonNegativeInt(score, "overload_penalty", context),
        replay_validity: boundedInt(score, "replay_validity", context, 0, 1),
        final_score: nonNegativeInt(score, "final_score", context),
      };
    }
    const parsed: MatchScoredPayload = {
      kind: "steel_onslaught.match_scored",
      match_id: str(record, "match_id", context),
      winner,
      scores,
      winner_player_id: str(record, "winner_player_id", context),
      winner_loadout_id: str(record, "winner_loadout_id", context),
      winner_score: nonNegativeInt(record, "winner_score", context),
      loser_player_id: str(record, "loser_player_id", context),
      loser_score: nonNegativeInt(record, "loser_score", context),
      duration_ticks: positiveInt(record, "duration_ticks", context),
      scored_at: str(record, "scored_at", context),
      is_draw: bool(record, "is_draw", context),
    };
    if (parsed.winner_player_id === parsed.loser_player_id) {
      fail(context, "winner_player_id and loser_player_id must be distinct");
    }
    const expectedPlayers = new Set([parsed.winner_player_id, parsed.loser_player_id]);
    if (
      Object.keys(parsed.scores).length !== 2 ||
      !Object.keys(parsed.scores).every((playerId) => expectedPlayers.has(playerId))
    ) {
      fail(context, "scores must contain exactly the winner and loser player IDs");
    }
    const winnerScore = parsed.scores[parsed.winner_player_id];
    const loserScore = parsed.scores[parsed.loser_player_id];
    if (winnerScore === undefined || loserScore === undefined) {
      fail(context, "scores are missing the winner or loser player ID");
    }
    if (
      parsed.winner_score !== winnerScore.final_score ||
      parsed.loser_score !== loserScore.final_score
    ) {
      fail(context, "flattened scores must equal nested final_score values");
    }
    if (parsed.is_draw) {
      if (
        parsed.winner !== null ||
        Object.values(parsed.scores).some((score) => score.victory !== 0)
      ) {
        fail(context, "draw scores require winner=null and zero victory points");
      }
    } else if (
      parsed.winner === null ||
      parsed.winner.player_id !== parsed.winner_player_id ||
      winnerScore.victory !== 1 ||
      loserScore.victory !== 0
    ) {
      fail(context, "decisive score winner truth is inconsistent");
    }
    return parsed;
  },
};

function parseHeatRedline(value: unknown, context: string): HeatRedlinePayload {
  const record = asRecord(value, context);
  rejectUnknown(record, ["heat", "redline_threshold"], context);
  return {
    heat: nonNegativeInt(record, "heat", context),
    redline_threshold: positiveInt(record, "redline_threshold", context),
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
    tick: nonNegativeInt(record, "tick", context),
    sequence_in_tick: nonNegativeInt(record, "sequence_in_tick", context),
    producer_node: str(record, "producer_node", context),
    subject: parseSubject(record["subject"], `${context}.subject`),
    envelope: onexEnvelope,
  };

  return buildEnvelope(base, eventTypeRaw, record["payload"]);
}

/**
 * Parse immutable pre-Phase-B replay evidence through the sole sanctioned
 * compatibility projection.  Schema 0.1.0 recordings predate explicit mech
 * sides and resolved-cost evidence, so only those two absent fields are
 * projected.  Current live frames continue through strict {@link parseEnvelope}
 * and must carry both fields explicitly.
 */
export function parseHistoricalReplayEnvelope(raw: unknown): SOEventEnvelope {
  const context = "historical replay envelope";
  const record = asRecord(raw, context);
  if (record["schema_version"] !== "0.1.0") {
    fail(context, 'compatibility projection requires schema_version "0.1.0"');
  }

  let projected: Record<string, unknown> = record;
  if (record["event_type"] === "match_started") {
    const payload = asRecord(record["payload"], `${context}.payload`);
    const rawMechs = payload["mechs"];
    if (!Array.isArray(rawMechs)) {
      fail(`${context}.payload.mechs`, "must be an array");
    }
    const mechs = rawMechs.map((value, index) => {
      const mech = asRecord(value, `${context}.payload.mechs[${index}]`);
      return "side" in mech ? mech : { ...mech, side: "neutral" };
    });
    projected = { ...record, payload: { ...payload, mechs } };
  } else if (record["event_type"] === "llm_completion_resolved") {
    const payload = asRecord(record["payload"], `${context}.payload`);
    if (!("cost_usd" in payload)) {
      projected = { ...record, payload: { ...payload, cost_usd: null } };
    }
  }
  return parseEnvelope(projected);
}

/** Parse a raw WebSocket text frame into a typed SOEventEnvelope. */
export function parseEnvelopeFrame(frame: string): SOEventEnvelope {
  return parseEnvelope(JSON.parse(frame));
}
