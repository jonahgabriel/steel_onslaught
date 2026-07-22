// @vitest-environment jsdom
/**
 * Start-lifecycle regression test for the deck shell.
 *
 * Two reported defects live here:
 *
 *   1. The launch form and START control did not disappear once the match was
 *      running. The canonical event stream — not the command receipt — is the
 *      lifecycle authority, so `match_started` must unmount the form and
 *      `match_ended` must re-arm it.
 *   2. A replay-only bootstrap (no roster, no command gateway — what
 *      `so serve` and `scripts/export_frontend_bootstrap.py` produce) streams a
 *      recorded match the instant the page loads, while a permanently disabled
 *      "START DISABLED" panel sat on screen forever. A deck that cannot launch
 *      must not render a launch panel at all.
 */
import "./setup-dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import App from "../App";
import {
  createFrontendApplication,
  type FrontendApplication,
  type FrontendBootstrap,
  parseFrontendBootstrap,
} from "../lib/application";
import type { WebSocketLike } from "../lib/event_stream";
import { parseEnvelopeFrame } from "../types";

const FIXTURES = resolve(process.cwd(), "src/__tests__/fixtures");

function readFixture(name: string): unknown {
  return JSON.parse(readFileSync(resolve(FIXTURES, name), "utf-8"));
}

function bootstrap(): FrontendBootstrap {
  return parseFrontendBootstrap(readFixture("bootstrap/frontend_bootstrap.json"));
}

/** Receive-only socket double: the test drives the frames the server would send. */
class FakeSocket implements WebSocketLike {
  private listener: ((event: { data: unknown }) => void) | null = null;
  closed = false;

  addEventListener(_type: "message", listener: (event: { data: unknown }) => void): void {
    this.listener = listener;
  }

  close(): void {
    this.closed = true;
  }

  deliver(envelope: unknown): void {
    if (this.listener === null) throw new Error("socket has no message listener");
    this.listener({ data: JSON.stringify(envelope) });
  }
}

function application(source: FrontendBootstrap): {
  app: FrontendApplication;
  sockets: FakeSocket[];
} {
  const sockets: FakeSocket[] = [];
  const app = createFrontendApplication(source, {
    socketFactory: {
      open: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    },
    // No frame ever runs: the launch lifecycle is decided at ingest, not at
    // release, so the deck must re-render without pacing.
    scheduler: { request: () => 1, cancel: () => undefined },
    clock: { now: () => 0 },
  });
  return { app, sockets };
}

function deliver(sockets: readonly FakeSocket[], fixture: string): void {
  const envelope = parseEnvelopeFrame(JSON.stringify(readFixture(fixture)));
  act(() => {
    for (const socket of sockets) socket.deliver(envelope);
  });
}

afterEach(cleanup);

describe("deck start lifecycle", () => {
  it("hides the launch form on match_started and re-arms it on match_ended", () => {
    const { app, sockets } = application(bootstrap());
    render(<App application={app} />);

    expect(screen.getByLabelText("Match setup")).toBeInTheDocument();

    deliver(sockets, "match_started.json");
    expect(screen.queryByLabelText("Match setup")).toBeNull();
    expect(screen.queryByRole("button", { name: /START/ })).toBeNull();

    deliver(sockets, "match_ended.json");
    expect(screen.getByLabelText("Match setup")).toBeInTheDocument();
  });

  it("never renders a launch panel for a replay-only bootstrap", () => {
    const replayOnly: FrontendBootstrap = { ...bootstrap(), player_roster: null };
    const { app, sockets } = application(replayOnly);
    render(<App application={app} />);

    expect(screen.queryByLabelText("Match setup")).toBeNull();
    expect(screen.queryByTestId("roster-unavailable")).toBeNull();

    deliver(sockets, "match_started.json");
    expect(screen.queryByLabelText("Match setup")).toBeNull();
  });
});
