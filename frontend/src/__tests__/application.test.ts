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

function binding(): Record<string, unknown> {
  return {
    schema_version: "1",
    kind: "steel_onslaught.frontend_bootstrap",
    overlay_sha256: SHA,
    frontend_transport: transportBinding(),
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
    expect(parseFrontendBootstrap(fixture).frontend_transport.milliseconds_per_tick).toBe(250);
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
