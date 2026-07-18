/** Strict browser-runtime command mirror.
 *
 * This parser is intentionally standalone: it validates the future command
 * boundary but does not open a socket, mutate transport state, or pause a
 * match.  Runtime ownership and revision admission remain server concerns.
 */

export const RUNTIME_COMMAND_KIND = "steel_onslaught.runtime_command" as const;

export type RuntimeAction = "start" | "pause" | "resume" | "stop";
export type RuntimeMode = "one_game" | "continuous";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface RuntimeCommandBase {
  readonly schema_version: "1";
  readonly kind: typeof RUNTIME_COMMAND_KIND;
  readonly command_id: string;
  readonly expected_revision: number;
  readonly owner_id: string;
}

export interface StartRuntimeCommand extends RuntimeCommandBase {
  readonly action: "start";
  readonly mode: RuntimeMode;
}

export interface PauseRuntimeCommand extends RuntimeCommandBase {
  readonly action: "pause";
}

export interface ResumeRuntimeCommand extends RuntimeCommandBase {
  readonly action: "resume";
}

export interface StopRuntimeCommand extends RuntimeCommandBase {
  readonly action: "stop";
}

export type RuntimeCommand =
  | StartRuntimeCommand
  | PauseRuntimeCommand
  | ResumeRuntimeCommand
  | StopRuntimeCommand;

function object(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${context}: expected an object`);
  }
  return Object.fromEntries(Object.entries(value));
}

function requireClosedKeys(
  record: Record<string, unknown>,
  expected: readonly string[],
  context: string,
): void {
  const keys = new Set(expected);
  for (const key of Object.keys(record)) {
    if (!keys.has(key)) throw new Error(`${context}: unknown field ${key}`);
  }
  for (const key of expected) {
    if (!(key in record)) throw new Error(`${context}: missing field ${key}`);
  }
}

function stringField(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${context}: field ${key} must be a non-empty string`);
  }
  return value;
}

function revisionField(record: Record<string, unknown>, context: string): number {
  const value = record["expected_revision"];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${context}: expected_revision must be a non-negative integer`);
  }
  return value;
}

function uuidField(record: Record<string, unknown>, key: string, context: string): string {
  const value = stringField(record, key, context);
  if (!UUID_PATTERN.test(value)) {
    throw new Error(`${context}: field ${key} must be a UUID`);
  }
  return value;
}

function ownerField(record: Record<string, unknown>, context: string): string {
  const value = stringField(record, "owner_id", context);
  if (value.length > 128) {
    throw new Error(`${context}: field owner_id must be at most 128 characters`);
  }
  return value;
}

/** Parse one strict runtime command and reject unknown/mode-mismatched fields. */
export function parseRuntimeCommand(value: unknown): RuntimeCommand {
  const context = "runtime command";
  const record = object(value, context);
  const action = stringField(record, "action", context);
  const baseFields = [
    "schema_version",
    "kind",
    "command_id",
    "expected_revision",
    "owner_id",
    "action",
  ] as const;
  const expectedFields = action === "start" ? [...baseFields, "mode"] : baseFields;
  requireClosedKeys(record, expectedFields, context);
  if (record["schema_version"] !== "1") {
    throw new Error(`${context}: schema_version must be "1"`);
  }
  if (record["kind"] !== RUNTIME_COMMAND_KIND) {
    throw new Error(`${context}: kind must be ${RUNTIME_COMMAND_KIND}`);
  }
  const commandId = uuidField(record, "command_id", context);
  const expectedRevision = revisionField(record, context);
  const ownerId = ownerField(record, context);
  if (action === "start") {
    const mode = record["mode"];
    if (mode !== "one_game" && mode !== "continuous") {
      throw new Error(`${context}: start mode must be one_game or continuous`);
    }
    return {
      schema_version: "1",
      kind: RUNTIME_COMMAND_KIND,
      command_id: commandId,
      expected_revision: expectedRevision,
      owner_id: ownerId,
      action: "start",
      mode,
    };
  }
  if (action !== "pause" && action !== "resume" && action !== "stop") {
    throw new Error(`${context}: action must be start, pause, resume, or stop`);
  }
  const common = {
    schema_version: "1" as const,
    kind: RUNTIME_COMMAND_KIND,
    command_id: commandId,
    expected_revision: expectedRevision,
    owner_id: ownerId,
  };
  if (action === "pause") return { ...common, action: "pause" };
  if (action === "resume") return { ...common, action: "resume" };
  return { ...common, action: "stop" };
}
