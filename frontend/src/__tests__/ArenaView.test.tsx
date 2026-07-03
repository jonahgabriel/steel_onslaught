// @vitest-environment jsdom
/**
 * ArenaView tests — Rev 2 (migrated from the 13 pinned TacticalBoard tests).
 *
 * The board evolved into the dominant center arena: chassis SPRITES (by class,
 * facing, damage state), fading movement TRAILS, per-weapon-class TRACERS
 * (weapon_fired → hit_resolved impact), wreck + steam burst on destruction, and
 * range rings on the selected mech. These assertions replace the old
 * marker/firing-line contract; the HeatBar / PressureBar / MechMarker unit
 * coverage below is preserved verbatim (those presentational components remain).
 */
import "./setup-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EnvelopeHandler, WebSocketLike } from "../lib/event_stream";
import { EventStream } from "../lib/event_stream";
import ArenaView from "../views/ArenaView";
import { makeEnvelope } from "./helpers";

const FIXTURES_DIR = join(process.cwd(), "src/__tests__/fixtures");

function fixtureText(name: string): string {
  return readFileSync(join(FIXTURES_DIR, `${name}.json`), "utf-8");
}

afterEach(() => {
  cleanup();
});

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
    for (const listener of this.listeners) listener({ data });
  }
}

function makeStubStream(): {
  socket: FakeSocket;
  subscribe: (handler: EnvelopeHandler) => () => void;
} {
  const socket = new FakeSocket();
  const stream = new EventStream({ socket });
  return { socket, subscribe: stream.subscribe.bind(stream) };
}

describe("ArenaView", () => {
  it("renders a chassis sprite for each mech after match_started", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    const a = screen.getByTestId("arena-mech-mech.a.01");
    const b = screen.getByTestId("arena-mech-mech.b.01");
    expect(a).toBeInTheDocument();
    expect(b).toBeInTheDocument();
    // both fixture mechs are light → scout sprite silhouettes
    expect(a.querySelector('[data-testid="sprite-scout"]')).toBeInTheDocument();
    expect(a).toHaveAttribute("data-chassis-class", "light");
  });

  it("renders the arena plotting grid", async () => {
    const { subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    expect(screen.getByTestId("arena-grid")).toBeInTheDocument();
  });

  it("draws a per-weapon-class tracer after WEAPON_FIRED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    await act(async () => {
      socket.emit(fixtureText("weapon_fired"));
    });
    // machine_gun → light tracer style
    expect(screen.getByTestId("tracer-light")).toBeInTheDocument();
  });

  it("shows an impact ring after HIT_RESOLVED on the tracer", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
      socket.emit(fixtureText("weapon_fired"));
    });
    expect(screen.queryByTestId("tracer-impact")).not.toBeInTheDocument();
    await act(async () => {
      socket.emit(fixtureText("hit_resolved"));
    });
    expect(screen.getByTestId("tracer-impact")).toBeInTheDocument();
  });

  it("shows an armor-absorb shimmer after ARMOR_ABSORBED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
      socket.emit(fixtureText("armor_absorbed"));
    });
    expect(screen.getByTestId("arena-shimmer")).toBeInTheDocument();
  });

  it("leaves a wreck sprite + steam burst after MECH_DESTROYED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    expect(screen.getByTestId("arena-mech-mech.b.01")).toHaveAttribute("data-state", "nominal");
    await act(async () => {
      socket.emit(fixtureText("mech_destroyed"));
    });
    const wreck = screen.getByTestId("arena-mech-mech.b.01");
    expect(wreck).toHaveAttribute("data-state", "destroyed");
    expect(wreck.querySelector('[data-testid="sprite-wreck"]')).toBeInTheDocument();
    expect(screen.getByTestId("arena-wreck-mech.b.01")).toBeInTheDocument();
  });

  it("records a fading movement trail after MOVEMENT_RESOLVED", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
      socket.emit(fixtureText("movement_resolved"));
    });
    expect(screen.getAllByTestId("arena-trail-mech.a.01").length).toBeGreaterThan(0);
  });

  it("shows range rings only around the selected mech", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    expect(screen.queryByTestId("arena-range-ring")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Select mech.a.01"));
    });
    expect(screen.getAllByTestId("arena-range-ring").length).toBeGreaterThan(0);
  });

  it("transitions sprite damage state as HP falls", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
    });
    const dmg = (hpAfter: number) =>
      makeEnvelope(
        "damage_applied",
        {
          target_id: "mech.b.01",
          damage: 1,
          cause: "weapon_hit",
          hp_after: hpAfter,
          source_mech_id: "mech.a.01",
          radius_cells: 0,
        },
        { mechId: "mech.b.01", playerId: "player.b", tick: 1 },
      );
    await act(async () => {
      socket.emit(JSON.stringify(dmg(50)));
    });
    expect(screen.getByTestId("arena-mech-mech.b.01")).toHaveAttribute("data-state", "damaged");
    await act(async () => {
      socket.emit(JSON.stringify(dmg(10)));
    });
    expect(screen.getByTestId("arena-mech-mech.b.01")).toHaveAttribute("data-state", "critical");
  });

  it("shows the victory banner with the winner player_id", async () => {
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(fixtureText("match_started"));
      socket.emit(fixtureText("victory_declared"));
    });
    const banner = screen.getByTestId("arena-victory");
    expect(banner).toHaveAttribute("data-winner", "player.a");
    expect(banner.textContent).toContain("player.a");
  });

  it("does not issue any fetch or POST (pure projection)", async () => {
    const fetchCalls: string[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input: RequestInfo | URL, _init?: RequestInit) => {
      fetchCalls.push(String(input));
      return new Response(null, { status: 200 });
    };
    try {
      const { socket, subscribe } = makeStubStream();
      render(<ArenaView subscribe={subscribe} />);
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
      <svg role="img" aria-label="test">
        <title>test</title>
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
        />
      </svg>,
    );
    const marker = screen.getByTestId("mech-marker-mech.a.01");
    expect(marker).toBeInTheDocument();
    expect(marker.getAttribute("data-chassis-class")).toBe("light");
  });

  it("is not rendered when alive is false", async () => {
    const { default: MechMarker } = await import("../views/MechMarker");
    render(
      <svg role="img" aria-label="test">
        <title>test</title>
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
        />
      </svg>,
    );
    expect(screen.queryByTestId("mech-marker-mech.a.01")).not.toBeInTheDocument();
  });
});
