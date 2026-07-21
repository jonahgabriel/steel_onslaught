import { BrowserCommandGateway, type CommandSocketFactory } from "./command_gateway";
import { EventStream, type WebSocketLike } from "./event_stream";
import { MatchTransport } from "./transport";

export const FRONTEND_BOOTSTRAP_PATH = "/steel-onslaught/bootstrap.json";
export const FRONTEND_TRANSPORT_CONTRACT = "steel_onslaught.frontend_transport.v1";
export const FRONTEND_EXPECTED_OVERLAY_HEADER = "X-Steel-Onslaught-Expected-Overlay";
export const GENERATED_FRONTEND_BOOTSTRAP = ".steel-onslaught-bootstrap.generated.json";
/**
 * Dev-server proxy target used when no generated bootstrap exists yet.
 *
 * The generated document is gitignored, so a clean checkout has none until a
 * match server writes one. This origin is the port every packaged overlay's
 * `frontend_transport` binds (`so play --port` default), which lets `npm run
 * dev` start and render before — or without — a generated bootstrap.
 */
export const DEFAULT_FRONTEND_BOOTSTRAP_TARGET = "http://127.0.0.1:8765";
export const FRONTEND_COMMAND_GATEWAY_CONTRACT = "steel_onslaught.browser_command_gateway.v1";

export interface FrontendTransportBinding {
  readonly kind: "websocket";
  readonly contract: typeof FRONTEND_TRANSPORT_CONTRACT;
  readonly websocket_url: string;
  readonly event_schema: "canonical_event_v1";
  readonly milliseconds_per_tick: number;
}

export interface FrontendCommandGatewayBinding {
  readonly kind: "websocket";
  readonly contract: typeof FRONTEND_COMMAND_GATEWAY_CONTRACT;
  readonly websocket_url: string;
  readonly authority_scope: "injected_process_session";
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
  /** Server-declared default; null means this seat intentionally has no default. */
  readonly default_option_id: string | null;
}

export interface PlayerRosterProjection {
  readonly schema_version: "1";
  readonly kind: "steel_onslaught.player_roster_projection";
  readonly roster_id: string;
  readonly roster_sha256: string;
  readonly options: readonly PublicPlayerOption[];
  readonly seats: readonly PublicSeatLaunchPolicy[];
}

export interface PublicHumanModelCatalogOption {
  readonly kind: "human";
  readonly option_id: string;
  readonly display_name: string;
}

export interface PublicModelModelCatalogOption {
  readonly kind: "model";
  readonly option_id: string;
  readonly display_name: string;
  readonly model_identity_id: string;
  readonly provider_binding_id: string;
  readonly provider_model: string;
}

export type PublicModelCatalogOption =
  | PublicHumanModelCatalogOption
  | PublicModelModelCatalogOption;

export interface ModelCatalogProjection {
  readonly schema_version: "1";
  readonly kind: "steel_onslaught.model_catalog_projection";
  readonly catalog_id: string;
  readonly catalog_sha256: string;
  readonly options: readonly PublicModelCatalogOption[];
  readonly default_option_ids: readonly [string | null, string | null];
  readonly mirror_match_mode: boolean;
}

export interface FrontendBootstrap {
  readonly schema_version: "1";
  readonly kind: "steel_onslaught.frontend_bootstrap";
  readonly overlay_sha256: string;
  readonly frontend_transport: FrontendTransportBinding;
  readonly player_roster: PlayerRosterProjection | null;
  readonly command_gateway: FrontendCommandGatewayBinding | null;
  readonly model_catalog: ModelCatalogProjection | null;
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
  readonly commandSocketFactory?: CommandSocketFactory;
  readonly scheduler: FrameScheduler;
  readonly clock: MonotonicClock;
}

export interface FrontendApplication {
  readonly bootstrap: FrontendBootstrap;
  readonly transport: MatchTransport;
  readonly makeStream: () => EventStream;
  readonly scheduler: FrameScheduler;
  readonly clock: MonotonicClock;
  readonly commandGateway: BrowserCommandGateway;
}

function fail(message: string): never {
  throw new Error(`frontend bootstrap: ${message}`);
}

const NULL_COMMAND_SOCKET_FACTORY: CommandSocketFactory = {
  open: () => fail("command socket factory is unavailable for a null command gateway"),
};

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

function providerModel(value: unknown, context: string): string {
  if (typeof value !== "string" || value.length < 1 || value.length > 160) {
    fail(`${context} must contain 1 to 160 characters`);
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
  // `default_option_id` was added after the original public projection. Keep
  // old projections parseable, but normalize the omitted field to null so
  // MatchSetup remains empty/disabled rather than inferring a model.
  const seatForExactKeys = { ...seat };
  delete seatForExactKeys["default_option_id"];
  exactKeys(seatForExactKeys, ["side", "allowed_option_ids"], context);
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
  const rawDefault = seat["default_option_id"] ?? null;
  const defaultOption =
    rawDefault === null
      ? null
      : identifier(
          rawDefault,
          /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
          `${context}.default_option_id`,
        );
  if (defaultOption !== null && !allowed.includes(defaultOption)) {
    fail(`${context}.default_option_id must be one of allowed_option_ids`);
  }
  return { side, allowed_option_ids: allowed, default_option_id: defaultOption };
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

function modelCatalog(value: unknown): ModelCatalogProjection {
  const catalog = object(value, "model_catalog");
  exactKeys(
    catalog,
    [
      "schema_version",
      "kind",
      "catalog_id",
      "catalog_sha256",
      "options",
      "default_option_ids",
      "mirror_match_mode",
    ],
    "model_catalog",
  );
  if (catalog["schema_version"] !== "1") fail('model_catalog.schema_version must be "1"');
  if (catalog["kind"] !== "steel_onslaught.model_catalog_projection") {
    fail("model_catalog.kind mismatch");
  }
  const options: PublicModelCatalogOption[] = list(catalog["options"], "model_catalog.options").map(
    (option, index): PublicModelCatalogOption => {
      const candidate = object(option, `model_catalog.options[${index}]`);
      const kind = candidate["kind"];
      if (kind === "human") {
        exactKeys(
          candidate,
          ["kind", "option_id", "display_name"],
          `model_catalog.options[${index}]`,
        );
        return {
          kind: "human",
          option_id: identifier(
            candidate["option_id"],
            /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
            `model_catalog.options[${index}].option_id`,
          ),
          display_name: displayName(
            candidate["display_name"],
            `model_catalog.options[${index}].display_name`,
          ),
        };
      }
      if (kind === "model") {
        exactKeys(
          candidate,
          [
            "kind",
            "option_id",
            "display_name",
            "model_identity_id",
            "provider_binding_id",
            "provider_model",
          ],
          `model_catalog.options[${index}]`,
        );
        return {
          kind: "model",
          option_id: identifier(
            candidate["option_id"],
            /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
            `model_catalog.options[${index}].option_id`,
          ),
          display_name: displayName(
            candidate["display_name"],
            `model_catalog.options[${index}].display_name`,
          ),
          model_identity_id: identifier(
            candidate["model_identity_id"],
            /^model_identity\.[a-z0-9][a-z0-9_.-]*$/,
            `model_catalog.options[${index}].model_identity_id`,
          ),
          provider_binding_id: identifier(
            candidate["provider_binding_id"],
            /^[a-z][a-z0-9_.-]*$/,
            `model_catalog.options[${index}].provider_binding_id`,
          ),
          provider_model: providerModel(
            candidate["provider_model"],
            `model_catalog.options[${index}].provider_model`,
          ),
        };
      }
      return fail(`model_catalog.options[${index}].kind must be human or model`);
    },
  );
  if (options.length < 1) fail("model_catalog.options must be nonempty");
  const optionIds = options.map((option) => option.option_id);
  if (new Set(optionIds).size !== optionIds.length) {
    fail("model_catalog.options must have unique option_id values");
  }
  const defaults = list(catalog["default_option_ids"], "model_catalog.default_option_ids");
  if (defaults.length !== 2) fail("model_catalog.default_option_ids must contain two entries");
  const defaultOptionIds: [string | null, string | null] = [
    defaults[0] === null
      ? null
      : identifier(
          defaults[0],
          /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
          "model_catalog.default_option_ids[0]",
        ),
    defaults[1] === null
      ? null
      : identifier(
          defaults[1],
          /^player_option\.[a-z0-9][a-z0-9_.-]*$/,
          "model_catalog.default_option_ids[1]",
        ),
  ];
  const mirrorMatchMode = catalog["mirror_match_mode"];
  if (typeof mirrorMatchMode !== "boolean") {
    fail("model_catalog.mirror_match_mode must be boolean");
  }
  return {
    schema_version: "1",
    kind: "steel_onslaught.model_catalog_projection",
    catalog_id: identifier(
      catalog["catalog_id"],
      /^catalog\.[a-z0-9][a-z0-9_.-]*$/,
      "model_catalog.catalog_id",
    ),
    catalog_sha256: identifier(
      catalog["catalog_sha256"],
      /^[0-9a-f]{64}$/,
      "model_catalog.catalog_sha256",
    ),
    options,
    default_option_ids: defaultOptionIds,
    mirror_match_mode: mirrorMatchMode,
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

function parseCommandGatewayUrl(value: unknown): string {
  const url = parseWebSocketUrl(value);
  const parsed = new URL(url);
  if (!["127.0.0.1", "localhost", "[::1]", "::1"].includes(parsed.hostname)) {
    fail("command_gateway.websocket_url must use a loopback host");
  }
  return url;
}

function commandGateway(value: unknown): FrontendCommandGatewayBinding {
  const gateway = object(value, "command_gateway");
  exactKeys(gateway, ["kind", "contract", "websocket_url", "authority_scope"], "command_gateway");
  if (gateway["kind"] !== "websocket") fail('command_gateway.kind must be "websocket"');
  if (gateway["contract"] !== FRONTEND_COMMAND_GATEWAY_CONTRACT) {
    fail("command_gateway.contract mismatch");
  }
  if (gateway["authority_scope"] !== "injected_process_session") {
    fail("command_gateway.authority_scope mismatch");
  }
  return {
    kind: "websocket",
    contract: FRONTEND_COMMAND_GATEWAY_CONTRACT,
    websocket_url: parseCommandGatewayUrl(gateway["websocket_url"]),
    authority_scope: "injected_process_session",
  };
}

export function parseFrontendBootstrap(value: unknown): FrontendBootstrap {
  const root = object(value, "root");
  // Older replay-only bootstrap documents predate the optional command root;
  // absence is equivalent to an explicit null capability. Unknown fields still
  // fail through the closed-key check below.
  if (!("command_gateway" in root)) root["command_gateway"] = null;
  if (!("model_catalog" in root)) root["model_catalog"] = null;
  exactKeys(
    root,
    [
      "schema_version",
      "kind",
      "overlay_sha256",
      "frontend_transport",
      "player_roster",
      "command_gateway",
      "model_catalog",
    ],
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
    command_gateway:
      root["command_gateway"] === null ? null : commandGateway(root["command_gateway"]),
    model_catalog: root["model_catalog"] === null ? null : modelCatalog(root["model_catalog"]),
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
  if (bootstrap.command_gateway !== null && capabilities.commandSocketFactory === undefined) {
    fail("commandSocketFactory is required for a non-null command gateway");
  }
  const transport = new MatchTransport({
    msPerTick: bootstrap.frontend_transport.milliseconds_per_tick,
  });
  return {
    bootstrap,
    transport,
    makeStream: () =>
      new EventStream(() =>
        capabilities.socketFactory.open(bootstrap.frontend_transport.websocket_url),
      ),
    scheduler: capabilities.scheduler,
    clock: capabilities.clock,
    commandGateway: new BrowserCommandGateway({
      binding: bootstrap.command_gateway,
      socketFactory: capabilities.commandSocketFactory ?? NULL_COMMAND_SOCKET_FACTORY,
    }),
  };
}
