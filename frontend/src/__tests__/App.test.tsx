// @vitest-environment jsdom
import "./setup-dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import App from "../App";
import {
  createFrontendApplication,
  type FrontendCapabilities,
  parseFrontendBootstrap,
} from "../lib/application";
import type { CommandSocketLike } from "../lib/command_gateway";
import type { WebSocketLike } from "../lib/event_stream";
import type { MatchStartedPayload } from "../types";
import { makeEnvelope } from "./helpers";

const BOOTSTRAP_FIXTURE = resolve(
  process.cwd(),
  "src/__tests__/fixtures/bootstrap/frontend_bootstrap.json",
);
const MATCH_STARTED_FIXTURE = resolve(process.cwd(), "src/__tests__/fixtures/match_started.json");

function bootstrap() {
  const parsed = parseFrontendBootstrap(JSON.parse(readFileSync(BOOTSTRAP_FIXTURE, "utf-8")));
  return {
    ...parsed,
    command_gateway: {
      kind: "websocket" as const,
      contract: "steel_onslaught.browser_command_gateway.v1" as const,
      websocket_url: "ws://127.0.0.1:8765/commands",
      authority_scope: "injected_process_session" as const,
    },
  };
}

function startedPayload(): MatchStartedPayload {
  const raw = JSON.parse(readFileSync(MATCH_STARTED_FIXTURE, "utf-8")) as {
    payload: MatchStartedPayload;
  };
  return raw.payload;
}

class FakeEventSocket implements WebSocketLike {
  private listener: ((event: { data: unknown }) => void) | null = null;
  closed = false;

  addEventListener(type: "message", listener: (event: { data: unknown }) => void): void {
    if (type === "message") this.listener = listener;
  }

  emit(data: unknown): void {
    this.listener?.({ data });
  }

  close(): void {
    this.closed = true;
  }
}

class FakeCommandSocket implements CommandSocketLike {
  private readonly listeners = new Map<
    "open" | "message" | "close",
    (event: { data?: unknown }) => void
  >();
  readonly sent: string[] = [];
  opened = false;
  closed = false;

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
    this.listeners.get("close")?.({});
  }

  emitOpen(): void {
    this.opened = true;
    this.listeners.get("open")?.({});
  }

  emit(data: unknown): void {
    this.listeners.get("message")?.({ data });
  }
}

function capabilities(
  eventSocket: FakeEventSocket,
  commandSockets: FakeCommandSocket[],
): FrontendCapabilities {
  return {
    socketFactory: { open: () => eventSocket },
    commandSocketFactory: {
      open: () => {
        const socket = new FakeCommandSocket();
        commandSockets.push(socket);
        return socket;
      },
    },
    scheduler: {
      request: () => 1,
      cancel: () => {},
    },
    clock: { now: () => 0 },
  };
}

describe("App match lifecycle", () => {
  afterEach(cleanup);

  it("keeps setup through acceptance, hides on MATCH_STARTED, and rearms after MATCH_ENDED", async () => {
    const eventSocket = new FakeEventSocket();
    const commandSockets: FakeCommandSocket[] = [];
    const application = createFrontendApplication(
      bootstrap(),
      capabilities(eventSocket, commandSockets),
    );
    render(<App application={application} />);

    const start = screen.getByRole("button", { name: "START MATCH" });
    fireEvent.click(start);
    expect(screen.getByRole("button", { name: "START PENDING" })).toBeDisabled();
    const commandSocket = commandSockets.at(0);
    if (commandSocket === undefined) throw new Error("command socket was not opened");
    commandSocket.emitOpen();
    commandSocket.emit(
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
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "START ACCEPTED" })).toBeDisabled(),
    );
    expect(screen.getByRole("form", { name: "Match setup" })).toBeInTheDocument();

    const matchId = "match.01JABCDE0123456789ABCDEFGX";
    eventSocket.emit(
      JSON.stringify(makeEnvelope("match_started", startedPayload(), { matchId, tick: 0 })),
    );
    await waitFor(() =>
      expect(screen.queryByRole("form", { name: "Match setup" })).not.toBeInTheDocument(),
    );

    eventSocket.emit(
      JSON.stringify(
        makeEnvelope("match_ended", { reason: "aborted", winner_id: null }, { matchId, tick: 1 }),
      ),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "START MATCH" })).toBeEnabled());
    expect(commandSocket.closed).toBe(true);
  });
});
