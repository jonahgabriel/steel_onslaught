import { describe, expect, it, vi } from "vitest";
import {
  BrowserCommandGateway,
  type CommandSocketFactory,
  type CommandSocketLike,
} from "../lib/command_gateway";

const binding = {
  kind: "websocket" as const,
  contract: "steel_onslaught.browser_command_gateway.v1" as const,
  websocket_url: "ws://127.0.0.1:8765/commands",
  authority_scope: "injected_process_session" as const,
};

class FakeSocket implements CommandSocketLike {
  readonly sent: string[] = [];
  readonly listeners = new Map<string, (event: { data?: unknown }) => void>();
  closed = false;
  opened = false;

  send(data: string): void {
    if (!this.opened) throw new Error("send before open");
    this.sent.push(data);
  }

  addEventListener(
    type: "open" | "message" | "close",
    listener: (event: { data?: unknown }) => void,
  ): void {
    this.listeners.set(type, listener);
  }

  close(): void {
    this.closed = true;
  }

  emitOpen(): void {
    this.opened = true;
    this.listeners.get("open")?.({});
  }

  receive(data: unknown): void {
    this.listeners.get("message")?.({ data });
  }
}

function factory(socket: FakeSocket): CommandSocketFactory {
  return { open: vi.fn(() => socket) };
}

const intent = {
  expected_overlay_sha256: "a".repeat(64),
  roster_id: "roster.player_selector",
  expected_roster_sha256: "b".repeat(64),
  selections: [
    { side: "red" as const, option_id: "player_option.browser_human" },
    { side: "blue" as const, option_id: "player_option.local_model" },
  ] as const,
};

describe("BrowserCommandGateway", () => {
  it("opens the injected command socket and sends one pending start without secrets", () => {
    const socket = new FakeSocket();
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => "request.start.01",
    });

    expect(gateway.requestStart(intent)).toBe("pending");
    expect(gateway.requestStart(intent)).toBe("pending");
    expect(socket.sent).toHaveLength(0);
    socket.emitOpen();
    expect(socket.sent).toHaveLength(1);
    const frame = JSON.parse(socket.sent.at(0) ?? "") as Record<string, unknown>;
    expect(frame).toMatchObject({
      schema_version: "1",
      kind: "steel_onslaught.browser_start_intent",
      request_id: "request.start.01",
      intent,
    });
    expect(socket.sent.at(0) ?? "").not.toMatch(
      /secret|token|authorization|endpoint_url|provider_binding_id/i,
    );
    expect(gateway.status).toBe("pending");
  });

  it("accepts a closed result and keeps event ingress receive-only", () => {
    const socket = new FakeSocket();
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => "request.start.02",
    });
    gateway.requestStart(intent);
    socket.emitOpen();

    socket.receive(
      JSON.stringify({
        schema_version: "1",
        kind: "steel_onslaught.browser_start_accepted",
        authority_scope: "process_lifetime",
        outcome: "accepted",
        command_id: "11111111-1111-4111-8111-111111111111",
        command_sha256: "c".repeat(64),
        match_id: "match.01JABCDE0123456789ABCDEFGX",
        overlay_sha256: "a".repeat(64),
        roster_sha256: "b".repeat(64),
      }),
    );
    expect(gateway.status).toBe("accepted");
    expect(() =>
      socket.receive(
        JSON.stringify({ event_type: "match_tick", payload: {}, unknown: "forbidden" }),
      ),
    ).toThrow(/receive-only/);
  });

  it("rejects unknown fields on accepted results", () => {
    const socket = new FakeSocket();
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => "request.start.03",
    });
    gateway.requestStart(intent);
    socket.emitOpen();
    expect(() =>
      socket.receive(
        JSON.stringify({
          schema_version: "1",
          kind: "steel_onslaught.browser_start_accepted",
          authority_scope: "process_lifetime",
          outcome: "accepted",
          command_id: "11111111-1111-4111-8111-111111111111",
          command_sha256: "c".repeat(64),
          match_id: "match.01JABCDE0123456789ABCDEFGX",
          overlay_sha256: "a".repeat(64),
          roster_sha256: "b".repeat(64),
          secret: "forbidden",
        }),
      ),
    ).toThrow(/unknown result field secret/);
  });

  it("sends one human action and supports cancellation", () => {
    const socket = new FakeSocket();
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => "request.action.01",
    });
    const result = gateway.submitAction({
      match_id: "match.01JABCDE0123456789ABCDEFGX",
      side: "red",
      turn_id: "turn.red.000001",
      expected_tick: 1,
      observation_sha256: "d".repeat(64),
      action: { kind: "remain" },
    });
    expect(result).toBe("pending");
    socket.emitOpen();
    expect(socket.sent).toHaveLength(1);
    gateway.cancel();
    expect(socket.closed).toBe(true);
    expect(gateway.status).toBe("cancelled");
  });

  it("sends authoritative cancellation after Start is accepted and a prompt is active", () => {
    const socket = new FakeSocket();
    const ids = ["request.start.04", "request.cancel.04"];
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => ids.shift() ?? "request.unexpected",
    });
    gateway.requestStart(intent);
    socket.emitOpen();
    socket.receive({
      schema_version: "1",
      kind: "steel_onslaught.browser_start_accepted",
      authority_scope: "process_lifetime",
      outcome: "accepted",
      command_id: "00000000-0000-4000-8000-000000000004",
      command_sha256: "a".repeat(64),
      match_id: "match.01JABCDE0123456789ABCDEFGX",
      overlay_sha256: "b".repeat(64),
      roster_sha256: "c".repeat(64),
    });
    socket.receive({
      schema_version: "1",
      kind: "steel_onslaught.human_turn",
      match_id: "match.01JABCDE0123456789ABCDEFGX",
      turn_id: "turn.red.000001",
      side: "red",
      expected_tick: 1,
      observation_sha256: "d".repeat(64),
      available_actions: [{ kind: "remain" }],
    });

    gateway.cancel();

    expect(JSON.parse(socket.sent.at(1) ?? "")).toMatchObject({
      kind: "steel_onslaught.browser_cancel",
      request_id: "request.cancel.04",
    });
    expect(socket.closed).toBe(true);
    expect(gateway.status).toBe("cancelled");
    expect(gateway.prompt).toBeNull();
  });

  it("parses terminal failure and cancellation frames and clears the prompt", () => {
    const socket = new FakeSocket();
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => "request.terminal.01",
    });
    gateway.requestStart(intent);
    socket.emitOpen();
    socket.receive({
      schema_version: "1",
      kind: "steel_onslaught.human_turn",
      match_id: "match.01JABCDE0123456789ABCDEFGX",
      turn_id: "turn.red.000001",
      side: "red",
      expected_tick: 1,
      observation_sha256: "d".repeat(64),
      available_actions: [{ kind: "remain" }],
    });
    expect(gateway.prompt).not.toBeNull();
    socket.receive({
      schema_version: "1",
      kind: "steel_onslaught.browser_command_failed",
      authority_scope: "process_lifetime",
      outcome: "failed",
      error_code: "invalid_or_unauthorized_command",
    });
    expect(gateway.status).toBe("failed");
    expect(gateway.prompt).toBeNull();

    gateway.requestStart(intent);
    socket.receive({
      schema_version: "1",
      kind: "steel_onslaught.browser_cancelled",
      authority_scope: "process_lifetime",
      outcome: "cancelled",
      request_id: "request.terminal.01",
    });
    expect(gateway.status).toBe("cancelled");
    expect(gateway.prompt).toBeNull();
  });

  it("rejects extra fields on terminal failure frames", () => {
    const socket = new FakeSocket();
    const gateway = new BrowserCommandGateway({
      binding,
      socketFactory: factory(socket),
      requestId: () => "request.terminal.02",
    });
    gateway.requestStart(intent);
    socket.emitOpen();
    expect(() =>
      socket.receive({
        schema_version: "1",
        kind: "steel_onslaught.browser_command_failed",
        authority_scope: "process_lifetime",
        outcome: "failed",
        error_code: "invalid_or_unauthorized_command",
        secret: "forbidden",
      }),
    ).toThrow(/unknown result field secret/);
  });
});
