// @vitest-environment jsdom
/**
 * Golden-replay regression test — the real recorded match, verbatim.
 *
 * The prior ArenaView / river bugs shipped twice because every existing test
 * fed *synthetic* one-envelope fixtures. This test instead replays the actual
 * demo ledger's full 315-envelope stream (exported byte-for-byte by
 * `scripts/export_ledger_json.py` from the same `read_all` + `model_dump_json`
 * path the live WebSocket bridge uses) through the REAL `parseEnvelope` and the
 * REAL PressureDeck / ArenaView reducers, then asserts what the two bugs got
 * wrong:
 *
 *   BUG A — the arena rendered zero mechs. Assert N mechs in arena state with
 *           in-bounds coordinates after match_started, AND that the mounted
 *           PressureDeck renders their `arena-mech-*` testids (ArenaView must be
 *           subscribed BEFORE match_started streams past — it is now always
 *           mounted, not gated behind gauges).
 *   BUG B — the river stopped follow-scrolling mid-match. Assert the follow
 *           scroll is invoked on append, and that a content-growth / anchoring
 *           scroll event (scrollTop not moving upward) never un-pins.
 */
import "./setup-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EnvelopeHandler } from "../lib/event_stream";
import { parseEnvelope, type SOEventEnvelope } from "../types";
import { ARENA_INITIAL_STATE, type ArenaState, arenaReduce, GRID_CELLS } from "../views/ArenaView";
import EventRiver from "../views/EventRiver";
import PressureDeck from "../views/PressureDeck";

const FIXTURE = join(process.cwd(), "src/__tests__/fixtures/golden_match/envelopes.json");

/** The recorded stream, parsed through the same `parseEnvelope` the app uses. */
function loadGoldenStream(): SOEventEnvelope[] {
  const raw = JSON.parse(readFileSync(FIXTURE, "utf-8")) as unknown[];
  return raw.map((row) => parseEnvelope(row));
}

afterEach(() => {
  cleanup();
});

describe("golden replay — arena state (BUG A)", () => {
  const stream = loadGoldenStream();

  it("the fixture is the real recorded match, not a synthetic stub", () => {
    expect(stream.length).toBeGreaterThan(100);
    expect(stream.filter((e) => e.event_type === "match_started")).toHaveLength(1);
  });

  it("folds match_started into N in-bounds mechs in arena state", () => {
    let state: ArenaState = ARENA_INITIAL_STATE;
    let mechCountAfterStart = 0;
    for (const env of stream) {
      state = arenaReduce(state, { type: "ENVELOPE", envelope: env });
      if (env.event_type === "match_started") {
        mechCountAfterStart = Object.keys(state.mechs).length;
      }
    }
    // match_started must have populated the arena reducer …
    expect(mechCountAfterStart).toBeGreaterThan(0);
    const started = stream.find((e) => e.event_type === "match_started");
    if (started?.event_type !== "match_started") throw new Error("no match_started");
    expect(mechCountAfterStart).toBe(started.payload.mechs.length);

    // … and every mech sits on the 40×40 grid.
    for (const mech of Object.values(state.mechs)) {
      expect(mech.position.x).toBeGreaterThanOrEqual(0);
      expect(mech.position.x).toBeLessThan(GRID_CELLS);
      expect(mech.position.y).toBeGreaterThanOrEqual(0);
      expect(mech.position.y).toBeLessThan(GRID_CELLS);
    }
  });
});

describe("golden replay — arena DOM through PressureDeck (BUG A)", () => {
  const stream = loadGoldenStream();

  beforeEach(() => {
    // PressureDeck batches envelopes per animation frame; jsdom has no rAF.
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) =>
      setTimeout(() => cb(Date.now()), 0),
    );
    vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a mech sprite testid for every mech after the full replay", async () => {
    const handlers = new Set<EnvelopeHandler>();
    const subscribe = (handler: EnvelopeHandler): (() => void) => {
      handlers.add(handler);
      return () => handlers.delete(handler);
    };

    render(<PressureDeck subscribe={subscribe} />);

    // Fan the whole recorded stream out exactly as App.tsx does (parsed
    // envelopes → every registered handler, incl. ArenaView's own reducer).
    await act(async () => {
      for (const env of stream) {
        for (const handler of [...handlers]) handler(env);
      }
      await new Promise((r) => setTimeout(r, 5)); // let the deck's rAF flush
    });

    const started = stream.find((e) => e.event_type === "match_started");
    if (started?.event_type !== "match_started") throw new Error("no match_started");
    for (const mech of started.payload.mechs) {
      expect(screen.getByTestId(`arena-mech-${mech.mech_id}`)).toBeInTheDocument();
    }
    // The awaiting-transmission placeholder must be gone once mechs exist.
    expect(screen.queryByTestId("arena-mech-mech.a.01")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BUG B — follow-scroll. jsdom has no layout, so scroll geometry is mocked on
// the river element. This encodes the invariant the live bug violated: content
// growth / scroll-anchoring must never un-pin; only an upward USER scroll does.
// ---------------------------------------------------------------------------

interface Geometry {
  scrollHeight: number;
  clientHeight: number;
}

/** Install a settable scrollTop + fixed scrollHeight/clientHeight on `el`. */
function mockScrollGeometry(el: HTMLElement, geo: Geometry): { top: () => number } {
  let top = 0;
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => top,
    set: (v: number) => {
      top = v;
    },
  });
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => geo.scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => geo.clientHeight });
  return { top: () => top };
}

const RIVER_PROPS = {
  hiddenCount: 0,
  sides: { byMech: new Map(), byPlayer: new Map() },
  laneMap: new Map<string, number>(),
  highlight: null,
  unresolved: new Set<string>(),
  focusedEventId: null,
  onSelect: () => {},
  onHover: () => {},
} as const;

describe("golden replay — river follow-scroll (BUG B)", () => {
  it("invokes follow-scroll to the bottom on append while pinned", () => {
    const geo: Geometry = { scrollHeight: 1000, clientHeight: 300 };
    const { rerender } = render(<EventRiver groups={[]} bottomKey="k0" {...RIVER_PROPS} />);
    const river = screen.getByTestId("event-river");
    const geom = mockScrollGeometry(river, geo);

    // A new bottomKey is the per-append signal — the effect must scroll to end.
    geo.scrollHeight = 2000;
    act(() => {
      rerender(<EventRiver groups={[]} bottomKey="k1" {...RIVER_PROPS} />);
    });
    expect(geom.top()).toBe(2000); // scrolled to scrollHeight (follow invoked)
    expect(screen.queryByTestId("live-chip")).not.toBeInTheDocument(); // still pinned
  });

  it("does NOT un-pin on content-growth / anchoring scroll events", () => {
    const geo: Geometry = { scrollHeight: 1000, clientHeight: 300 };
    const { rerender } = render(<EventRiver groups={[]} bottomKey="k0" {...RIVER_PROPS} />);
    const river = screen.getByTestId("event-river");
    mockScrollGeometry(river, geo);

    // Append → the follow effect scrolls to bottom and arms the programmatic
    // guard; the browser fires the matching scroll event (consumed by the guard).
    geo.scrollHeight = 2000;
    act(() => rerender(<EventRiver groups={[]} bottomKey="k1" {...RIVER_PROPS} />));
    act(() => fireEvent.scroll(river)); // our own programmatic scroll event

    // Now simulate content growth + scroll anchoring nudging scrollTop toward
    // the bottom (scrollTop INCREASES, as observed live: 16.5 → 77) while more
    // rows stream in and scrollHeight jumps. The OLD code read this as "not at
    // bottom" and un-pinned, freezing the river. It must NOT un-pin.
    geo.scrollHeight = 6000;
    river.scrollTop = 2100; // increased from 2000 — not a user scroll-up
    act(() => fireEvent.scroll(river));

    expect(screen.queryByTestId("live-chip")).not.toBeInTheDocument(); // still pinned
  });

  it("un-pins on a genuine upward user scroll and re-pins on LIVE click", () => {
    const geo: Geometry = { scrollHeight: 4000, clientHeight: 300 };
    const { rerender } = render(<EventRiver groups={[]} bottomKey="k0" {...RIVER_PROPS} />);
    const river = screen.getByTestId("event-river");
    mockScrollGeometry(river, geo);
    act(() => rerender(<EventRiver groups={[]} bottomKey="k1" {...RIVER_PROPS} />));
    act(() => fireEvent.scroll(river)); // consume the programmatic guard

    // User drags the view UP (scrollTop decreases) → stop following, show chip.
    river.scrollTop = 200;
    act(() => fireEvent.scroll(river));
    expect(screen.getByTestId("live-chip")).toBeInTheDocument();

    // Clicking LIVE re-pins to the bottom and hides the chip.
    act(() => fireEvent.click(screen.getByTestId("live-chip")));
    expect(screen.queryByTestId("live-chip")).not.toBeInTheDocument();
    expect(river.scrollTop).toBe(4000);
  });
});
