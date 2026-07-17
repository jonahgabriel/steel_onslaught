import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  type BootstrapResponse,
  createFrontendApplication,
  FRONTEND_BOOTSTRAP_PATH,
  FRONTEND_TRANSPORT_CONTRACT,
  frontendBootstrapHttpTarget,
  loadFrontendBootstrap,
  parseFrontendBootstrap,
} from "../lib/application";
import type { WebSocketLike } from "../lib/event_stream";

const SHA = "a".repeat(64);
const BOOTSTRAP_FIXTURE = fileURLToPath(
  new URL("./fixtures/bootstrap/frontend_bootstrap.json", import.meta.url),
);

function transportBinding(): Record<string, unknown> {
  return {
    kind: "websocket",
    contract: FRONTEND_TRANSPORT_CONTRACT,
    websocket_url: "ws://127.0.0.1:8765/events",
    event_schema: "canonical_event_v1",
    milliseconds_per_tick: 250,
  };
}

function playerRosterBinding(): Record<string, unknown> {
  return {
    schema_version: "1",
    kind: "steel_onslaught.player_roster_projection",
    roster_id: "roster.player_selector",
    roster_sha256: "b".repeat(64),
    options: [
      {
        kind: "human",
        option_id: "player_option.browser_human",
        display_name: "Browser Operator",
      },
      {
        kind: "model",
        option_id: "player_option.local_model",
        display_name: "Local Model",
        model_identity_id: "model_identity.local",
      },
      {
        kind: "model",
        option_id: "player_option.openrouter_model",
        display_name: "OpenRouter Model",
        model_identity_id: "model_identity.openrouter",
      },
      {
        kind: "model",
        option_id: "player_option.glm_model",
        display_name: "GLM Model",
        model_identity_id: "model_identity.glm",
      },
      {
        kind: "model",
        option_id: "player_option.gemini_model",
        display_name: "Gemini Model",
        model_identity_id: "model_identity.gemini",
      },
    ],
    seats: [
      {
        side: "red",
        allowed_option_ids: [
          "player_option.browser_human",
          "player_option.local_model",
          "player_option.openrouter_model",
          "player_option.glm_model",
          "player_option.gemini_model",
        ],
      },
      {
        side: "blue",
        allowed_option_ids: [
          "player_option.local_model",
          "player_option.openrouter_model",
          "player_option.glm_model",
          "player_option.gemini_model",
        ],
      },
    ],
  };
}

function binding(): Record<string, unknown> {
  return {
    schema_version: "1",
    kind: "steel_onslaught.frontend_bootstrap",
    overlay_sha256: SHA,
    frontend_transport: transportBinding(),
    player_roster: playerRosterBinding(),
  };
}

function response(body: unknown, overrides: Partial<BootstrapResponse> = {}): BootstrapResponse {
  return {
    ok: true,
    status: 200,
    headers: {
      get: (name) => {
        if (name === "ETag") return `"${SHA}"`;
        if (name === "X-Steel-Onslaught-Contract") return FRONTEND_TRANSPORT_CONTRACT;
        return null;
      },
    },
    json: async () => body,
    ...overrides,
  };
}

class FakeSocket implements WebSocketLike {
  addEventListener(): void {}
  close(): void {}
}

describe("frontend application bootstrap", () => {
  it("accepts the exact closed public binding", () => {
    const fixture: unknown = JSON.parse(readFileSync(BOOTSTRAP_FIXTURE, "utf-8"));
    const parsed = parseFrontendBootstrap(fixture);
    expect(parsed.frontend_transport.milliseconds_per_tick).toBe(250);
    expect(parsed.player_roster?.options.map((option) => option.kind)).toEqual([
      "human",
      "model",
      "model",
      "model",
      "model",
    ]);
    expect(
      parsed.player_roster?.options
        .filter((option) => option.kind === "model")
        .map((option) => option.model_identity_id),
    ).toEqual([
      "model_identity.local",
      "model_identity.openrouter",
      "model_identity.glm",
      "model_identity.gemini",
    ]);
  });

  it("accepts explicit null roster without inferring player options", () => {
    expect(parseFrontendBootstrap({ ...binding(), player_roster: null }).player_roster).toBeNull();
  });

  it("derives the dev bootstrap origin from a validated non-default binding", () => {
    const candidate = binding();
    candidate["frontend_transport"] = {
      ...transportBinding(),
      websocket_url: "wss://arena.example.test:9876/closed/events",
    };
    expect(frontendBootstrapHttpTarget(parseFrontendBootstrap(candidate))).toBe(
      "https://arena.example.test:9876",
    );
  });

  it.each([
    ["missing field", { ...binding(), overlay_sha256: undefined }],
    ["missing roster authority", { ...binding(), player_roster: undefined }],
    ["unknown root field", { ...binding(), implicit_url: "ws://ambient" }],
    [
      "unknown nested field",
      {
        ...binding(),
        frontend_transport: {
          ...transportBinding(),
          fallback_port: 8765,
        },
      },
    ],
    [
      "contract mismatch",
      {
        ...binding(),
        frontend_transport: {
          ...transportBinding(),
          contract: "steel_onslaught.frontend_transport.v0",
        },
      },
    ],
    [
      "query authority",
      {
        ...binding(),
        frontend_transport: {
          ...transportBinding(),
          websocket_url: "ws://127.0.0.1:8765/events?match=ambient",
        },
      },
    ],
  ])("fails closed on %s", (_description, candidate) => {
    expect(() => parseFrontendBootstrap(candidate)).toThrow(/frontend bootstrap/);
  });

  it.each([
    "provider_binding_id",
    "endpoint_url",
    "secret_ref",
    "key",
    "token",
    "header",
    "resolver",
    "path",
  ])("rejects forbidden nested roster field %s", (field) => {
    const roster = playerRosterBinding();
    const options = roster["options"];
    if (!Array.isArray(options)) throw new Error("test roster options must be an array");
    const first = options[0];
    if (typeof first !== "object" || first === null || Array.isArray(first)) {
      throw new Error("test roster option must be an object");
    }
    expect(() =>
      parseFrontendBootstrap({
        ...binding(),
        player_roster: {
          ...roster,
          options: [{ ...first, [field]: "forbidden" }, ...options.slice(1)],
        },
      }),
    ).toThrow(/unknown field/);
  });

  it("rejects unknown seat references and unreachable configured options", () => {
    const roster = playerRosterBinding();
    expect(() =>
      parseFrontendBootstrap({
        ...binding(),
        player_roster: {
          ...roster,
          seats: [
            { side: "red", allowed_option_ids: ["player_option.unknown"] },
            { side: "blue", allowed_option_ids: ["player_option.local_model"] },
          ],
        },
      }),
    ).toThrow(/unknown option_id/);

    expect(() =>
      parseFrontendBootstrap({
        ...binding(),
        player_roster: {
          ...roster,
          seats: [
            { side: "red", allowed_option_ids: ["player_option.browser_human"] },
            { side: "blue", allowed_option_ids: ["player_option.local_model"] },
          ],
        },
      }),
    ).toThrow(/option must be reachable/);
  });

  it("requires response contract and overlay identities to match the body", async () => {
    const paths: string[] = [];
    const loaded = await loadFrontendBootstrap(async (path) => {
      paths.push(path);
      return response(binding());
    });
    expect(paths).toEqual([FRONTEND_BOOTSTRAP_PATH]);
    expect(loaded.overlay_sha256).toBe(SHA);

    await expect(
      loadFrontendBootstrap(async () =>
        response(binding(), {
          headers: {
            get: (name) =>
              name === "X-Steel-Onslaught-Contract"
                ? FRONTEND_TRANSPORT_CONTRACT
                : `"${"b".repeat(64)}"`,
          },
        }),
      ),
    ).rejects.toThrow(/overlay identity mismatch/);
  });

  it("constructs transport and stream only from injected capabilities", () => {
    const parsed = parseFrontendBootstrap(binding());
    const opened: string[] = [];
    const application = createFrontendApplication(parsed, {
      socketFactory: {
        open: (url) => {
          opened.push(url);
          return new FakeSocket();
        },
      },
      scheduler: { request: () => 41, cancel: () => {} },
      clock: { now: () => 123 },
    });

    expect(application.transport.snapshot().status).toBe("playing");
    const stream = application.makeStream();
    expect(opened).toEqual(["ws://127.0.0.1:8765/events"]);
    stream.close();
  });
});
