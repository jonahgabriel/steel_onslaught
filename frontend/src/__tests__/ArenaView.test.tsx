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
import { parseEnvelope } from "../types";
import ArenaView, {
  GRID_CELLS,
  spriteOffsets,
  spritePlacements,
  spriteSizePct,
} from "../views/ArenaView";
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
  const stream = new EventStream(socket);
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

  it("drives the grid and obstacle layer from the required arena snapshot", async () => {
    const base = parseEnvelope(JSON.parse(fixtureText("match_started")));
    if (base.event_type !== "match_started") throw new Error("wrong fixture event type");
    const started = makeEnvelope("match_started", {
      ...base.payload,
      mechs: base.payload.mechs.map((mech, index) => ({
        ...mech,
        position: index === 0 ? { x: 4, y: 4 } : { x: 55, y: 55 },
      })),
      arena: {
        ...base.payload.arena,
        size: 60,
        spawn_a: { x: 4, y: 4 },
        spawn_b: { x: 55, y: 55 },
        obstacles: [
          { x: 30, y: 30 },
          { x: 31, y: 30 },
        ],
      },
    });
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => socket.emit(JSON.stringify(started)));
    expect(screen.getByTestId("arena-grid")).toHaveAttribute("viewBox", "0 0 60 60");
    expect(screen.getAllByTestId("arena-obstacle")).toHaveLength(2);
    expect(screen.getByTestId("arena-mech-mech.b.01")).toBeInTheDocument();
  });

  it("de-overlaps a nearby pair while preserving true-cell anchors", async () => {
    const base = parseEnvelope(JSON.parse(fixtureText("match_started")));
    if (base.event_type !== "match_started") throw new Error("wrong fixture event type");
    const started = makeEnvelope("match_started", {
      ...base.payload,
      mechs: base.payload.mechs.map((mech, index) => ({
        ...mech,
        position: { x: 10 + index, y: 10 },
      })),
      arena: {
        ...base.payload.arena,
        size: GRID_CELLS,
        spawn_a: { x: 10, y: 10 },
        spawn_b: { x: 11, y: 10 },
        obstacles: [],
      },
    });
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => socket.emit(JSON.stringify(started)));
    const a = screen.getByTestId("arena-mech-mech.a.01");
    const b = screen.getByTestId("arena-mech-mech.b.01");
    expect(a).toHaveAttribute("data-paired", "true");
    expect(b).toHaveAttribute("data-paired", "true");
    expect(screen.getByTestId("arena-cell-anchor-mech.a.01")).toBeInTheDocument();
    expect(screen.getByTestId("arena-cell-anchor-mech.b.01")).toBeInTheDocument();
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

  it("carries attacker side into a tracer when opposing mechs are co-located", async () => {
    const started = parseEnvelope(JSON.parse(fixtureText("match_started")));
    if (started.event_type !== "match_started") throw new Error("wrong fixture event type");
    const red = started.payload.mechs.find((mech) => mech.side === "red");
    const blue = started.payload.mechs.find((mech) => mech.side === "blue");
    if (red === undefined || blue === undefined) throw new Error("fixture sides missing");
    const sharedPosition = { x: 11, y: 13 };
    const moveRed = makeEnvelope(
      "movement_resolved",
      {
        from: red.position,
        to: sharedPosition,
        ticks_consumed: 30,
        pressure_consumed: 8,
      },
      { matchId: started.match_id, tick: 1, mechId: red.mech_id, playerId: red.player_id },
    );
    const moveBlue = makeEnvelope(
      "movement_resolved",
      {
        from: blue.position,
        to: sharedPosition,
        ticks_consumed: 30,
        pressure_consumed: 24,
      },
      { matchId: started.match_id, tick: 1, mechId: blue.mech_id, playerId: blue.player_id },
    );
    const blueFires = makeEnvelope(
      "weapon_fired",
      {
        weapon_id: "module.weapon.machine_gun",
        target_id: red.mech_id,
        hit_probability: 0.65,
        pressure_cost: 4,
        heat_generated: 6,
      },
      { matchId: started.match_id, tick: 1, mechId: blue.mech_id, playerId: blue.player_id },
    );
    const { socket, subscribe } = makeStubStream();
    render(<ArenaView subscribe={subscribe} />);
    await act(async () => {
      socket.emit(JSON.stringify(started));
      socket.emit(JSON.stringify(moveRed));
      socket.emit(JSON.stringify(moveBlue));
      socket.emit(JSON.stringify(blueFires));
    });

    expect(screen.getByTestId("tracer-light").style.getPropertyValue("--so-side")).toContain(
      "--arc",
    );
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

describe("arena sprite placement", () => {
  const anchor = (mechId: string, x: number, y: number) => ({
    mechId,
    position: { x, y },
  });

  it("scales the unit footprint with the arena size", () => {
    expect(spriteSizePct(40)).toBe(10);
    expect(spriteSizePct(60)).toBeCloseTo((4 / 60) * 100, 6);
  });

  it("nudges adjacent units apart deterministically", () => {
    const offsets = spriteOffsets([anchor("mech.a.01", 10, 10), anchor("mech.b.01", 11, 10)]);
    expect(offsets["mech.a.01"]?.paired).toBe(true);
    expect(offsets["mech.b.01"]?.paired).toBe(true);
    expect(offsets["mech.a.01"]?.dx).toBeLessThan(0);
    expect(offsets["mech.b.01"]?.dx).toBeGreaterThan(0);
  });

  it("keeps a corner pair inside the arena", () => {
    const placements = spritePlacements(
      [anchor("mech.a.01", 58, 58), anchor("mech.b.01", 59, 59)],
      60,
    );
    const half = (spriteSizePct(60) * 0.85) / 2;
    for (const placement of Object.values(placements)) {
      expect(placement.left).toBeGreaterThanOrEqual(half);
      expect(placement.left).toBeLessThanOrEqual(100 - half);
      expect(placement.top).toBeGreaterThanOrEqual(half);
      expect(placement.top).toBeLessThanOrEqual(100 - half);
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
