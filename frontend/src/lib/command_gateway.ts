/**
 * Browser command ingress for a live process-local match.
 *
 * This is deliberately separate from EventStream: events are receive-only,
 * while this injected socket is the sole place where browser commands may be
 * sent.  The gateway never adds credentials, resolves providers, or infers a
 * server endpoint.  A missing binding therefore remains fail-closed.
 */

import type { RuntimeCommand } from "./runtime_contract";

export const BROWSER_COMMAND_CONTRACT = "steel_onslaught.browser_command_gateway.v1";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export interface CommandGatewayBinding {
  readonly kind: "websocket";
  readonly contract: typeof BROWSER_COMMAND_CONTRACT;
  readonly websocket_url: string;
  readonly authority_scope: "injected_process_session";
}

export interface CommandSocketLike {
  send(data: string): void;
  addEventListener(
    type: "open" | "message" | "close",
    listener: (event: { data?: unknown }) => void,
  ): void;
  close(): void;
}

export interface CommandSocketFactory {
  open(url: string): CommandSocketLike;
}

export type GatewayStatus = "idle" | "pending" | "accepted" | "cancelled" | "failed" | "rejected";

export interface BrowserStartIntent {
  readonly expected_overlay_sha256: string;
  readonly roster_id: string;
  readonly expected_roster_sha256: string;
  readonly selections: readonly [
    { readonly side: "red"; readonly option_id: string },
    { readonly side: "blue"; readonly option_id: string },
  ];
}

export interface BrowserActionIntent {
  readonly match_id: string;
  readonly side: "red" | "blue";
  readonly turn_id: string;
  readonly expected_tick: number;
  readonly observation_sha256: string;
  readonly action: Record<string, string | number | null>;
}

export interface BrowserHumanTurnPrompt {
  readonly match_id: string;
  readonly turn_id: string;
  readonly side: "red" | "blue";
  readonly expected_tick: number;
  readonly observation_sha256: string;
  readonly available_actions: readonly Record<string, string | number | null>[];
}

interface RequestFrame {
  readonly schema_version: "1";
  readonly kind:
    | "steel_onslaught.browser_start_intent"
    | "steel_onslaught.browser_player_action"
    | "steel_onslaught.browser_cancel";
  readonly request_id: string;
  readonly intent?: BrowserStartIntent;
  readonly action?: BrowserActionIntent;
}

interface ResultFrame {
  readonly kind:
    | "steel_onslaught.browser_start_accepted"
    | "steel_onslaught.browser_action_accepted"
    | "steel_onslaught.runtime_command_accepted"
    | "steel_onslaught.browser_cancelled"
    | "steel_onslaught.browser_command_failed";
  readonly outcome: "accepted" | "cancelled" | "failed";
}

function parsePrompt(value: Record<string, unknown>): BrowserHumanTurnPrompt | null {
  if (value["kind"] !== "steel_onslaught.human_turn") return null;
  requireClosedKeys(value, [
    "schema_version",
    "kind",
    "match_id",
    "turn_id",
    "side",
    "expected_tick",
    "observation_sha256",
    "available_actions",
  ]);
  if (
    typeof value["match_id"] !== "string" ||
    typeof value["turn_id"] !== "string" ||
    (value["side"] !== "red" && value["side"] !== "blue") ||
    typeof value["expected_tick"] !== "number" ||
    !Number.isInteger(value["expected_tick"]) ||
    typeof value["observation_sha256"] !== "string" ||
    !Array.isArray(value["available_actions"])
  ) {
    throw new Error("command gateway: invalid human turn prompt");
  }
  const actions = value["available_actions"].map((action) => {
    const record = object(action);
    if (record === null || typeof record["kind"] !== "string") {
      throw new Error("command gateway: invalid human action choice");
    }
    const closed: Record<string, string | number | null> = {};
    for (const [key, candidate] of Object.entries(record)) {
      if (candidate !== null && typeof candidate !== "string" && typeof candidate !== "number") {
        throw new Error("command gateway: invalid human action choice");
      }
      closed[key] = candidate;
    }
    return closed;
  });
  return {
    match_id: value["match_id"],
    turn_id: value["turn_id"],
    side: value["side"],
    expected_tick: value["expected_tick"],
    observation_sha256: value["observation_sha256"],
    available_actions: actions,
  };
}

function object(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return Object.fromEntries(Object.entries(value));
}

function parseFrame(value: unknown): ResultFrame | null {
  const record = object(value);
  if (record === null) return null;
  if (typeof record["event_type"] === "string") {
    throw new Error("command gateway is receive-only for event frames");
  }
  if (typeof record["kind"] !== "string") return null;
  if (record["kind"] === "steel_onslaught.browser_start_accepted") {
    requireClosedKeys(record, [
      "schema_version",
      "kind",
      "authority_scope",
      "outcome",
      "command_id",
      "command_sha256",
      "match_id",
      "overlay_sha256",
      "roster_sha256",
    ]);
    if (record["outcome"] !== "accepted") throw new Error("command gateway: invalid start result");
    return { kind: record["kind"], outcome: "accepted" };
  }
  if (record["kind"] === "steel_onslaught.browser_action_accepted") {
    requireClosedKeys(record, [
      "schema_version",
      "kind",
      "authority_scope",
      "outcome",
      "command_id",
      "command_sha256",
      "match_id",
      "turn_id",
      "expected_tick",
      "side",
      "prompt_sha256",
    ]);
    if (record["outcome"] !== "accepted") throw new Error("command gateway: invalid action result");
    return { kind: record["kind"], outcome: "accepted" };
  }
  if (record["kind"] === "steel_onslaught.runtime_command_accepted") {
    requireClosedKeys(record, [
      "schema_version",
      "kind",
      "authority_scope",
      "outcome",
      "command_id",
      "status",
    ]);
    if (
      record["outcome"] !== "accepted" ||
      typeof record["command_id"] !== "string" ||
      typeof record["status"] !== "object" ||
      record["status"] === null ||
      Array.isArray(record["status"])
    ) {
      throw new Error("command gateway: invalid runtime result");
    }
    validateRuntimeStatusResult(record["status"]);
    return { kind: record["kind"], outcome: "accepted" };
  }
  if (record["kind"] === "steel_onslaught.browser_cancelled") {
    requireClosedKeys(record, [
      "schema_version",
      "kind",
      "authority_scope",
      "outcome",
      "request_id",
    ]);
    if (record["outcome"] !== "cancelled" || typeof record["request_id"] !== "string") {
      throw new Error("command gateway: invalid cancellation result");
    }
    return { kind: record["kind"], outcome: "cancelled" };
  }
  if (record["kind"] === "steel_onslaught.browser_command_failed") {
    requireClosedKeys(record, [
      "schema_version",
      "kind",
      "authority_scope",
      "outcome",
      "error_code",
    ]);
    if (record["outcome"] !== "failed" || typeof record["error_code"] !== "string") {
      throw new Error("command gateway: invalid command failure result");
    }
    return { kind: record["kind"], outcome: "failed" };
  }
  if (record["kind"].includes("event")) {
    throw new Error("command gateway is receive-only for event frames");
  }
  return null;
}

function requireClosedKeys(record: Record<string, unknown>, expected: readonly string[]): void {
  const keys = new Set(expected);
  for (const key of Object.keys(record)) {
    if (!keys.has(key)) throw new Error(`command gateway: unknown result field ${key}`);
  }
  for (const key of expected) {
    if (!(key in record)) throw new Error(`command gateway: missing result field ${key}`);
  }
}

function validateRuntimeStatusResult(value: unknown): void {
  const record = object(value);
  if (record === null) throw new Error("command gateway: runtime status must be an object");
  requireClosedKeys(record, [
    "status",
    "mode",
    "revision",
    "owner_id",
    "match_index",
    "last_command_id",
  ]);
  if (
    record["status"] !== "ready" &&
    record["status"] !== "running" &&
    record["status"] !== "paused" &&
    record["status"] !== "ended"
  ) {
    throw new Error("command gateway: invalid runtime status");
  }
  if (record["mode"] !== null && record["mode"] !== "one_game" && record["mode"] !== "continuous") {
    throw new Error("command gateway: invalid runtime status mode");
  }
  if (
    (record["status"] === "ready" && record["mode"] !== null) ||
    (record["status"] !== "ready" && record["mode"] === null)
  ) {
    throw new Error("command gateway: runtime status mode does not match status");
  }
  if (
    typeof record["revision"] !== "number" ||
    !Number.isSafeInteger(record["revision"]) ||
    record["revision"] < 0 ||
    typeof record["match_index"] !== "number" ||
    !Number.isSafeInteger(record["match_index"]) ||
    record["match_index"] < 0
  ) {
    throw new Error("command gateway: invalid runtime status revision");
  }
  if (
    typeof record["owner_id"] !== "string" ||
    record["owner_id"].length === 0 ||
    record["owner_id"].length > 128
  ) {
    throw new Error("command gateway: invalid runtime status owner");
  }
  const commandId = record["last_command_id"];
  if (commandId !== null && (typeof commandId !== "string" || !UUID_PATTERN.test(commandId))) {
    throw new Error("command gateway: invalid runtime status command id");
  }
  if (record["status"] === "ready" && commandId !== null) {
    throw new Error("command gateway: ready runtime status requires no command id");
  }
}

export interface BrowserCommandGatewayOptions {
  readonly binding: CommandGatewayBinding | null;
  readonly socketFactory: CommandSocketFactory;
  readonly requestId?: () => string;
  readonly onStatus?: (status: GatewayStatus) => void;
  readonly onPrompt?: (prompt: BrowserHumanTurnPrompt) => void;
}

export class BrowserCommandGateway {
  private readonly binding: CommandGatewayBinding | null;
  private readonly socketFactory: CommandSocketFactory;
  private readonly makeRequestId: () => string;
  private readonly statusListener: ((status: GatewayStatus) => void) | undefined;
  private readonly promptListener: ((prompt: BrowserHumanTurnPrompt) => void) | undefined;
  private currentPrompt: BrowserHumanTurnPrompt | null = null;
  private readonly promptListeners = new Set<(prompt: BrowserHumanTurnPrompt | null) => void>();
  private socket: CommandSocketLike | null = null;
  private socketOpen = false;
  private readonly queuedFrames: string[] = [];
  private closeAfterOpen = false;
  private currentStatus: GatewayStatus = "idle";
  private activeRequestId: string | null = null;

  constructor(options: BrowserCommandGatewayOptions) {
    this.binding = options.binding;
    this.socketFactory = options.socketFactory;
    this.makeRequestId = options.requestId ?? (() => crypto.randomUUID());
    this.statusListener = options.onStatus;
    this.promptListener = options.onPrompt;
  }

  get status(): GatewayStatus {
    return this.currentStatus;
  }

  get enabled(): boolean {
    return this.binding !== null;
  }

  get prompt(): BrowserHumanTurnPrompt | null {
    return this.currentPrompt;
  }

  clearPrompt(): void {
    this.currentPrompt = null;
    for (const listener of this.promptListeners) listener(null);
  }

  subscribePrompt(listener: (prompt: BrowserHumanTurnPrompt | null) => void): () => void {
    this.promptListeners.add(listener);
    return () => this.promptListeners.delete(listener);
  }

  requestStart(intent: BrowserStartIntent): GatewayStatus {
    if (this.binding === null || this.currentStatus === "rejected") {
      this.setStatus("rejected");
      return this.currentStatus;
    }
    if (this.currentStatus === "pending" || this.currentStatus === "accepted") {
      return this.currentStatus;
    }
    const requestId = this.makeRequestId();
    this.activeRequestId = requestId;
    this.send({
      schema_version: "1",
      kind: "steel_onslaught.browser_start_intent",
      request_id: requestId,
      intent,
    });
    this.setStatus("pending");
    return this.currentStatus;
  }

  submitAction(action: BrowserActionIntent): GatewayStatus {
    if (this.binding === null || this.currentStatus === "rejected") {
      this.setStatus("rejected");
      return this.currentStatus;
    }
    const requestId = this.makeRequestId();
    this.activeRequestId = requestId;
    this.send({
      schema_version: "1",
      kind: "steel_onslaught.browser_player_action",
      request_id: requestId,
      action,
    });
    this.setStatus("pending");
    return this.currentStatus;
  }

  sendRuntime(command: RuntimeCommand): GatewayStatus {
    if (this.binding === null || this.currentStatus === "rejected") {
      this.setStatus("rejected");
      return this.currentStatus;
    }
    this.activeRequestId = command.command_id;
    this.send(command);
    this.setStatus("pending");
    return this.currentStatus;
  }

  cancel(): void {
    if (this.socket !== null) {
      const requestId = this.activeRequestId ?? this.makeRequestId();
      this.send({
        schema_version: "1",
        kind: "steel_onslaught.browser_cancel",
        request_id: requestId,
      });
      if (this.socketOpen) this.socket.close();
      else this.closeAfterOpen = true;
    }
    this.activeRequestId = null;
    this.clearPrompt();
    this.setStatus("cancelled");
  }

  close(): void {
    this.socket?.close();
    this.socket = null;
    this.socketOpen = false;
    this.queuedFrames.length = 0;
    this.closeAfterOpen = false;
  }

  private send(frame: RequestFrame | RuntimeCommand): void {
    if (this.socket === null) {
      const socket = this.socketFactory.open(this.binding?.websocket_url ?? "");
      this.socket = socket;
      socket.addEventListener("open", () => {
        this.socketOpen = true;
        for (const queued of this.queuedFrames.splice(0)) this.socket?.send(queued);
        if (this.closeAfterOpen) {
          this.closeAfterOpen = false;
          socket.close();
        }
      });
      socket.addEventListener("message", (event) => {
        const payload = object(
          typeof event.data === "string" ? JSON.parse(event.data) : event.data,
        );
        if (payload !== null) {
          const prompt = parsePrompt(payload);
          if (prompt !== null) {
            this.currentPrompt = prompt;
            this.promptListener?.(prompt);
            for (const listener of this.promptListeners) listener(prompt);
            return;
          }
        }
        const result = parseFrame(payload);
        if (result !== null) {
          this.activeRequestId = null;
          this.clearPrompt();
          this.setStatus(result.outcome);
        }
      });
      socket.addEventListener("close", () => {
        this.socketOpen = false;
        this.queuedFrames.length = 0;
        this.closeAfterOpen = false;
        if (this.socket === socket) this.socket = null;
        if (this.currentStatus === "pending") {
          this.clearPrompt();
          this.setStatus("cancelled");
        }
      });
    }
    const serialized = JSON.stringify(frame);
    if (this.socketOpen) this.socket.send(serialized);
    else this.queuedFrames.push(serialized);
  }

  private setStatus(status: GatewayStatus): void {
    this.currentStatus = status;
    this.statusListener?.(status);
  }
}
