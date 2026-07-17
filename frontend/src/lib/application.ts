import { EventStream, type WebSocketLike } from "./event_stream";
import { MatchTransport } from "./transport";

export const FRONTEND_BOOTSTRAP_PATH = "/steel-onslaught/bootstrap.json";
export const FRONTEND_TRANSPORT_CONTRACT = "steel_onslaught.frontend_transport.v1";
export const FRONTEND_EXPECTED_OVERLAY_HEADER = "X-Steel-Onslaught-Expected-Overlay";
export const GENERATED_FRONTEND_BOOTSTRAP = ".steel-onslaught-bootstrap.generated.json";

export interface FrontendTransportBinding {
  readonly kind: "websocket";
  readonly contract: typeof FRONTEND_TRANSPORT_CONTRACT;
  readonly websocket_url: string;
  readonly event_schema: "canonical_event_v1";
  readonly milliseconds_per_tick: number;
}

export type PlayerSide = "red" | "blue";

export interface PublicHumanPlayerOption {
  readonly kind: "human";
  readonly option_id: string;
  readonly display_name: string;
}

export interface PublicModelPlayerOption {
  readonly kind: "model";
  readonly option_id: string;
  readonly display_name: string;
  readonly model_identity_id: string;
}

export type PublicPlayerOption = PublicHumanPlayerOption | PublicModelPlayerOption;

export interface PublicSeatLaunchPolicy {
  readonly side: PlayerSide;
  readonly allowed_option_ids: readonly string[];
}

export interface PlayerRosterProjection {
  readonly schema_version: "1";
  readonly kind: "steel_onslaught.player_roster_projection";
  readonly roster_id: string;
  readonly roster_sha256: string;
  readonly options: readonly PublicPlayerOption[];
  readonly seats: readonly PublicSeatLaunchPolicy[];
}

export interface FrontendBootstrap {
  readonly schema_version: "1";
  readonly kind: "steel_onslaught.frontend_bootstrap";
  readonly overlay_sha256: string;
  readonly frontend_transport: FrontendTransportBinding;
  readonly player_roster: PlayerRosterProjection | null;
}

export interface BootstrapHeaders {
  get(name: string): string | null;
}

export interface BootstrapResponse {
  readonly ok: boolean;
  readonly status: number;
  readonly headers: BootstrapHeaders;
  json(): Promise<unknown>;
}

export type BootstrapFetcher = (path: string) => Promise<BootstrapResponse>;

export interface FrameScheduler {
  request(callback: () => void): number;
  cancel(handle: number): void;
}

export interface MonotonicClock {
  now(): number;
}

export interface SocketFactory {
  open(url: string): WebSocketLike;
}

export interface FrontendCapabilities {
  readonly socketFactory: SocketFactory;
  readonly scheduler: FrameScheduler;
  readonly clock: MonotonicClock;
}

export interface FrontendApplication {
  readonly bootstrap: FrontendBootstrap;
  readonly transport: MatchTransport;
  readonly makeStream: () => EventStream;
  readonly scheduler: FrameScheduler;
  readonly clock: MonotonicClock;
}

function fail(message: string): never {
  throw new Error(`frontend bootstrap: ${message}`);
}

function object(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${context} must be an object`);
  }
  return Object.fromEntries(Object.entries(value));
}

function exactKeys(record: Record<string, unknown>, expected: readonly string[], context: string) {
  const allowed = new Set(expected);
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) fail(`${context} contains unknown field ${key}`);
  }
  for (const key of expected) {
    if (!(key in record)) fail(`${context} is missing field ${key}`);
  }
}

function list(value: unknown, context: string): readonly unknown[] {
  if (!Array.isArray(value)) fail(`${context} must be an array`);
  return value;
}

function identifier(value: unknown, pattern: RegExp, context: string): string {
  if (typeof value !== "string" || !pattern.test(value)) fail(`${context} is invalid`);
  return value;
}

function displayName(value: unknown, context: string): string {
  if (typeof value !== "string" || value.length < 1 || value.length > 80) {
    fail(`${context} must contain 1 to 80 characters`);
  }
  return value;
}

function playerOption(value: unknown, context: string): PublicPlayerOption {
  const option = object(value, context);
  const kind = option["kind"];
  if (kind === "human") {
    exactKeys(option, ["kind", "option_id", "display_name"], context);
    return {
      kind: "human",
      option_id: identifier(
        option["option_id"],
        /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
        `${context}.option_id`,
      ),
      display_name: displayName(option["display_name"], `${context}.display_name`),
    };
  }
  if (kind === "model") {
    exactKeys(option, ["kind", "option_id", "display_name", "model_identity_id"], context);
    return {
      kind: "model",
      option_id: identifier(
        option["option_id"],
        /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
        `${context}.option_id`,
      ),
      display_name: displayName(option["display_name"], `${context}.display_name`),
      model_identity_id: identifier(
        option["model_identity_id"],
        /^model_identity\.[a-z0-9][a-z0-9_.-]*$/,
        `${context}.model_identity_id`,
      ),
    };
  }
  fail(`${context}.kind must be human or model`);
}

function seatPolicy(value: unknown, context: string): PublicSeatLaunchPolicy {
  const seat = object(value, context);
  exactKeys(seat, ["side", "allowed_option_ids"], context);
  const side = seat["side"];
  if (side !== "red" && side !== "blue") fail(`${context}.side must be red or blue`);
  const allowed = list(seat["allowed_option_ids"], `${context}.allowed_option_ids`).map(
    (optionId, index) =>
      identifier(
        optionId,
        /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
        `${context}.allowed_option_ids[${index}]`,
      ),
  );
  if (allowed.length < 1 || new Set(allowed).size !== allowed.length) {
    fail(`${context}.allowed_option_ids must be nonempty and unique`);
  }
  return { side, allowed_option_ids: allowed };
}

function playerRoster(value: unknown): PlayerRosterProjection {
  const roster = object(value, "player_roster");
  exactKeys(
    roster,
    ["schema_version", "kind", "roster_id", "roster_sha256", "options", "seats"],
    "player_roster",
  );
  if (roster["schema_version"] !== "1") fail('player_roster.schema_version must be "1"');
  if (roster["kind"] !== "steel_onslaught.player_roster_projection") {
    fail("player_roster.kind mismatch");
  }
  const options = list(roster["options"], "player_roster.options").map((option, index) =>
    playerOption(option, `player_roster.options[${index}]`),
  );
  if (options.length < 1) fail("player_roster.options must be nonempty");
  const optionIds = options.map((option) => option.option_id);
  if (new Set(optionIds).size !== optionIds.length) {
    fail("player_roster.options must have unique option_id values");
  }
  const seats = list(roster["seats"], "player_roster.seats").map((seat, index) =>
    seatPolicy(seat, `player_roster.seats[${index}]`),
  );
  if (
    seats.length !== 2 ||
    new Set(seats.map((seat) => seat.side)).size !== 2 ||
    !seats.some((seat) => seat.side === "red") ||
    !seats.some((seat) => seat.side === "blue")
  ) {
    fail("player_roster.seats must contain exactly one red and one blue policy");
  }
  const known = new Set(optionIds);
  const reachable = new Set<string>();
  for (const seat of seats) {
    for (const optionId of seat.allowed_option_ids) {
      if (!known.has(optionId)) fail("player_roster seat references unknown option_id");
      reachable.add(optionId);
    }
  }
  if (reachable.size !== known.size) fail("every player_roster option must be reachable");
  return {
    schema_version: "1",
    kind: "steel_onslaught.player_roster_projection",
    roster_id: identifier(
      roster["roster_id"],
      /^roster\.[a-z0-9][a-z0-9_.-]*$/,
      "player_roster.roster_id",
    ),
    roster_sha256: identifier(
      roster["roster_sha256"],
      /^[0-9a-f]{64}$/,
      "player_roster.roster_sha256",
    ),
    options,
    seats,
  };
}

function parseWebSocketUrl(value: unknown): string {
  if (typeof value !== "string") fail("frontend_transport.websocket_url must be a string");
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    fail("frontend_transport.websocket_url must be a complete URL");
  }
  if (parsed.protocol !== "ws:" && parsed.protocol !== "wss:") {
    fail("frontend_transport.websocket_url must use ws or wss");
  }
  if (
    parsed.hostname === "" ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.pathname === "/" ||
    parsed.port === ""
  ) {
    fail("frontend_transport.websocket_url is not a closed stream endpoint");
  }
  return value;
}

export function parseFrontendBootstrap(value: unknown): FrontendBootstrap {
  const root = object(value, "root");
  exactKeys(
    root,
    ["schema_version", "kind", "overlay_sha256", "frontend_transport", "player_roster"],
    "root",
  );
  if (root["schema_version"] !== "1") fail('schema_version must be "1"');
  if (root["kind"] !== "steel_onslaught.frontend_bootstrap") {
    fail("kind does not identify the frontend bootstrap contract");
  }
  const overlaySha = root["overlay_sha256"];
  if (typeof overlaySha !== "string" || !/^[0-9a-f]{64}$/.test(overlaySha)) {
    fail("overlay_sha256 must be a lowercase SHA-256 digest");
  }

  const transport = object(root["frontend_transport"], "frontend_transport");
  exactKeys(
    transport,
    ["kind", "contract", "websocket_url", "event_schema", "milliseconds_per_tick"],
    "frontend_transport",
  );
  if (transport["kind"] !== "websocket") fail('frontend_transport.kind must be "websocket"');
  if (transport["contract"] !== FRONTEND_TRANSPORT_CONTRACT) {
    fail("frontend_transport.contract mismatch");
  }
  if (transport["event_schema"] !== "canonical_event_v1") {
    fail("frontend_transport.event_schema mismatch");
  }
  const millisecondsPerTick = transport["milliseconds_per_tick"];
  if (
    typeof millisecondsPerTick !== "number" ||
    !Number.isInteger(millisecondsPerTick) ||
    millisecondsPerTick <= 0 ||
    millisecondsPerTick > 60_000
  ) {
    fail("frontend_transport.milliseconds_per_tick must be an integer in [1, 60000]");
  }
  return {
    schema_version: "1",
    kind: "steel_onslaught.frontend_bootstrap",
    overlay_sha256: overlaySha,
    frontend_transport: {
      kind: "websocket",
      contract: FRONTEND_TRANSPORT_CONTRACT,
      websocket_url: parseWebSocketUrl(transport["websocket_url"]),
      event_schema: "canonical_event_v1",
      milliseconds_per_tick: millisecondsPerTick,
    },
    player_roster: root["player_roster"] === null ? null : playerRoster(root["player_roster"]),
  };
}

/** Derive the dev bootstrap proxy origin from the validated WebSocket binding. */
export function frontendBootstrapHttpTarget(bootstrap: FrontendBootstrap): string {
  const endpoint = new URL(bootstrap.frontend_transport.websocket_url);
  endpoint.protocol = endpoint.protocol === "wss:" ? "https:" : "http:";
  endpoint.pathname = "/";
  endpoint.search = "";
  endpoint.hash = "";
  return endpoint.origin;
}

export async function loadFrontendBootstrap(fetcher: BootstrapFetcher): Promise<FrontendBootstrap> {
  const response = await fetcher(FRONTEND_BOOTSTRAP_PATH);
  if (!response.ok) fail(`request failed with HTTP ${response.status}`);
  const bootstrap = parseFrontendBootstrap(await response.json());
  const responseContract = response.headers.get("X-Steel-Onslaught-Contract");
  if (responseContract !== bootstrap.frontend_transport.contract) {
    fail("response contract header mismatch");
  }
  const responseEtag = response.headers.get("ETag");
  if (responseEtag !== `"${bootstrap.overlay_sha256}"`) {
    fail("response overlay identity mismatch");
  }
  return bootstrap;
}

export function createFrontendApplication(
  bootstrap: FrontendBootstrap,
  capabilities: FrontendCapabilities,
): FrontendApplication {
  const transport = new MatchTransport({
    msPerTick: bootstrap.frontend_transport.milliseconds_per_tick,
  });
  return {
    bootstrap,
    transport,
    makeStream: () =>
      new EventStream(capabilities.socketFactory.open(bootstrap.frontend_transport.websocket_url)),
    scheduler: capabilities.scheduler,
    clock: capabilities.clock,
  };
}
