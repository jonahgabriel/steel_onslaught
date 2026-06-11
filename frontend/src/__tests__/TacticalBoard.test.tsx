// @vitest-environment jsdom
/**
 * TacticalBoard tests — Task 32.
 *
 * Renders the tactical board with a stub event stream and asserts:
 *  - Mech markers appear for each mech in the match_started payload.
 *  - Each marker carries chassis-class, heat-bar, pressure-bar, and hp-bar.
 *  - WEAPON_FIRED produces a firing-line element.
 *  - MECH_DESTROYED replaces the marker with a wreckage glyph.
 *  - VICTORY_DECLARED shows the victory banner with the winner's player_id.
 *  - The component never issues any write (pure projection — no fetch/POST).
 */
import "./setup-dom";
import { cleanup, render, screen, act } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { EnvelopeHandler, WebSocketLike } from "../lib/event_stream";
import { EventStream } from "../lib/event_stream";
import TacticalBoard from "../views/TacticalBoard";

// jsdom environment: import.meta.url is not a file URL, so use process.cwd().
// process.cwd() resolves to the frontend/ directory (where npm test is run).
const FIXTURES_DIR = join(process.cwd(), "src/__tests__/fixtures");

function fixtureText(name: string): string {
  return readFileSync(join(FIXTURES_DIR, `${name}.json`), "utf-8");
}

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Stub WebSocket + EventStream
// ---------------------------------------------------------------------------

type MessageListener = (event: { data: unknown }) => void;

class FakeSocket implements WebSocketLike {
  listeners: MessageListener[] = [];
  closed = false;

  addEventListener(_type: "message", listener: MessageListener): void {
    this.listeners.push(listener);
  }

  close(): void {
    this.closed = true;
  }

  emit(data: string): void {
    for (const listener of this.listeners) {
      listener({ data });
    }
  }
}

/** Helper — returns [socket, subscribe] without constructing a full stream. */
function makeStubStream(): {
  socket: FakeSocket;
  subscribe: (handler: EnvelopeHandler) => () => void;
} {
  const socket = new FakeSocket();
  const stream = new EventStream({ socket });
  return { socket, subscribe: stream.subscribe.bind(stream) };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TacticalBoard", () => {
  it("renders mech markers for both mechs after match_started", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<TacticalBoard subscribe={subscribe} />);

    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });

    // Two mechs in the match_started fixture: mech.a.01 and mech.b.01
    expect(screen.getByTestId("mech-marker-mech.a.01")).toBeInTheDocument();
    expect(screen.getByTestId("mech-marker-mech.b.01")).toBeInTheDocument();
  });

  it("each mech marker contains heat-bar, pressure-bar and hp-bar", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<TacticalBoard subscribe={subscribe} />);

    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });

    const marker = screen.getByTestId("mech-marker-mech.a.01");
    expect(marker.querySelector('[data-testid="heat-bar"]')).toBeInTheDocument();
    expect(marker.querySelector('[data-testid="pressure-bar"]')).toBeInTheDocument();
    expect(marker.querySelector('[data-testid="hp-bar"]')).toBeInTheDocument();
  });

  it("shows a firing-line after WEAPON_FIRED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<TacticalBoard subscribe={subscribe} />);

    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    await act(async () => {
      socket.emit(fixtureText("weapon_fired"));
    });

    // At least one firing-line element should be present
    const lines = document.querySelectorAll('[data-testid^="firing-line-"]');
    expect(lines.length).toBeGreaterThan(0);
  });

  it("replaces mech marker with wreckage glyph after MECH_DESTROYED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<TacticalBoard subscribe={subscribe} />);

    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });

    // Confirm marker exists before destruction
    expect(screen.getByTestId("mech-marker-mech.b.01")).toBeInTheDocument();

    await act(async () => {
      socket.emit(fixtureText("mech_destroyed"));
    });

    // Marker should be gone; wreckage glyph should appear
    expect(screen.queryByTestId("mech-marker-mech.b.01")).not.toBeInTheDocument();
    expect(screen.getByTestId("wreckage-mech.b.01")).toBeInTheDocument();
  });

  it("shows victory banner with winner player_id after VICTORY_DECLARED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<TacticalBoard subscribe={subscribe} />);

    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    await act(async () => {
      socket.emit(fixtureText("victory_declared"));
    });

    // The victory_declared fixture has winner_player_id: "player.a"
    const banner = screen.getByTestId("victory-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveAttribute("data-winner", "player.a");
    expect(banner.textContent).toContain("player.a");
  });

  it("board SVG is rendered (40x40 grid)", async () => {
    const { subscribe } = makeStubStream();
    render(<TacticalBoard subscribe={subscribe} />);

    const svg = document.querySelector('[data-testid="tactical-board-svg"]');
    expect(svg).toBeInTheDocument();
  });

  it("component does not issue any fetch or POST (pure projection)", async () => {
    const fetchCalls: string[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input: RequestInfo | URL, _init?: RequestInit) => {
      fetchCalls.push(String(input));
      return new Response(null, { status: 200 });
    };

    try {
      const { socket, subscribe } = makeStubStream();
      render(<TacticalBoard subscribe={subscribe} />);

      await act(async () => {
        socket.emit(fixtureText("match_started"));
        socket.emit(fixtureText("weapon_fired"));
        socket.emit(fixtureText("victory_declared"));
      });

      expect(fetchCalls).toHaveLength(0);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("HeatBar", () => {
  it("is green when heat is well below redline", async () => {
    const { default: HeatBar } = await import("../views/HeatBar");
    render(<HeatBar heat={10} redlineThreshold={70} ruptureThreshold={100} />);
    const bar = screen.getByTestId("heat-bar");
    expect(bar).toBeInTheDocument();
    expect(bar.getAttribute("data-heat-level")).toBe("normal");
  });

  it("is amber when heat is between redline-10 and redline", async () => {
    const { default: HeatBar } = await import("../views/HeatBar");
    render(<HeatBar heat={65} redlineThreshold={70} ruptureThreshold={100} />);
    const bar = screen.getByTestId("heat-bar");
    expect(bar.getAttribute("data-heat-level")).toBe("warning");
  });

  it("is red when heat exceeds redline", async () => {
    const { default: HeatBar } = await import("../views/HeatBar");
    render(<HeatBar heat={80} redlineThreshold={70} ruptureThreshold={100} />);
    const bar = screen.getByTestId("heat-bar");
    expect(bar.getAttribute("data-heat-level")).toBe("redline");
  });
});

describe("PressureBar", () => {
  it("renders a filled bar proportional to current/max pressure", async () => {
    const { default: PressureBar } = await import("../views/PressureBar");
    render(<PressureBar current={45} maximum={90} />);
    const bar = screen.getByTestId("pressure-bar");
    expect(bar).toBeInTheDocument();
    expect(bar.getAttribute("data-pressure-pct")).toBe("50");
  });
});

describe("MechMarker", () => {
  it("shows chassis-class label", async () => {
    const { default: MechMarker } = await import("../views/MechMarker");
    render(
      <MechMarker
        mechId="mech.a.01"
        chassisClass="light"
        heat={20}
        redlineThreshold={70}
        ruptureThreshold={100}
        pressureCurrent={45}
        pressureMaximum={90}
        hp={100}
        hpMax={100}
        x={5}
        y={5}
        cellSize={10}
        alive={true}
      />,
    );
    const marker = screen.getByTestId("mech-marker-mech.a.01");
    expect(marker).toBeInTheDocument();
    expect(marker.getAttribute("data-chassis-class")).toBe("light");
  });

  it("is not rendered when alive is false", async () => {
    const { default: MechMarker } = await import("../views/MechMarker");
    render(
      <MechMarker
        mechId="mech.a.01"
        chassisClass="heavy"
        heat={0}
        redlineThreshold={70}
        ruptureThreshold={100}
        pressureCurrent={0}
        pressureMaximum={90}
        hp={0}
        hpMax={100}
        x={10}
        y={10}
        cellSize={10}
        alive={false}
      />,
    );
    expect(screen.queryByTestId("mech-marker-mech.a.01")).not.toBeInTheDocument();
  });
});
