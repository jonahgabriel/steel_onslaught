// @vitest-environment jsdom
/**
 * Golden-replay regression test — the real recorded match, verbatim.
 *
 * The prior ArenaView / river bugs shipped twice because every existing test
 * fed *synthetic* one-envelope fixtures. This test instead replays the actual
 * demo ledger's full 315-envelope stream (exported byte-for-byte by
 * `scripts/export_ledger_json.py` from the same `read_all` + `model_dump_json`
 * path the live WebSocket bridge uses) through the versioned historical replay
 * projection and the REAL PressureDeck / ArenaView reducers, then asserts what
 * the two bugs got wrong:
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
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EnvelopeHandler } from "../lib/event_stream";
import { MatchTransport, type ReleaseSink } from "../lib/transport";
import { parseHistoricalReplayEnvelope, type SOEventEnvelope } from "../types";
import { ARENA_INITIAL_STATE, type ArenaState, arenaReduce, GRID_CELLS } from "../views/ArenaView";
import EventRiver from "../views/EventRiver";
import PressureDeck from "../views/PressureDeck";

const FIXTURE = join(process.cwd(), "src/__tests__/fixtures/golden_match/envelopes.json");
const FIXTURE_SHA256 = "3edaaeebbf3cab37f5b0344e1759d3b19ac8086336da8b2b4cc95e9293bb5757";

/** The immutable recorded stream, parsed only through its versioned compatibility path. */
function loadGoldenStream(): SOEventEnvelope[] {
  const raw = JSON.parse(readFileSync(FIXTURE, "utf-8")) as unknown[];
  return raw.map((row) => parseHistoricalReplayEnvelope(row));
}

afterEach(() => {
  cleanup();
});

describe("golden replay — transport auto-plays from tick 0 (rule 1)", () => {
  const stream = loadGoldenStream();

  it("with the real buffer + a mocked clock, the cursor is mid-playback, NOT at end", () => {
    // maxTick of the recorded match — the LIVE-jump bug parked the cursor here.
    const maxTick = Math.max(...stream.map((e) => e.tick));
    expect(maxTick).toBeGreaterThan(1);

    const transport = new MatchTransport({ msPerTick: 100 });
    const released: SOEventEnvelope[] = [];
    const sink: ReleaseSink = {
      reset: () => {
        released.length = 0;
      },
      release: (batch) => released.push(...batch),
    };
    transport.setSink(sink);

    // Pipe the entire recorded stream in (as the WS bridge would, full-speed).
    for (const env of stream) transport.ingest(env);

    // DEFAULT is a paced replay — no play()/goLive() call.
    expect(transport.snapshot().status).toBe("playing");

    // Advance a mocked wall clock a few tick-durations into the match.
    let now = 0;
    for (let i = 0; i < 5; i += 1) {
      transport.frame(now);
      now += 100;
    }

    const snap = transport.snapshot();
    // The cursor is somewhere in 0..maxTick, mid-playback — the whole point of
    // the fix: it did NOT jump to the buffer end on the first frame.
    expect(snap.cursorTick).toBeGreaterThanOrEqual(0);
    expect(snap.cursorTick).toBeLessThan(maxTick);
    expect(snap.atEnd).toBe(false);
    expect(snap.ended).toBe(false);
    // And it actually started from the top: the setup frame released first.
    expect(released[0]?.event_type).toBe("match_started");
    expect(released.every((e) => e.tick <= snap.cursorTick)).toBe(true);
  });

  it("drives the paced replay to the finished match's final tick and offers REPLAY", () => {
    const maxTick = Math.max(...stream.map((e) => e.tick));
    const transport = new MatchTransport({ msPerTick: 1 });
    for (const env of stream) transport.ingest(env);
    expect(transport.snapshot().matchComplete).toBe(true);

    // Enough frames (1ms/tick) to walk past every tick boundary.
    for (let now = 0; now <= (maxTick + 2) * 2; now += 1) transport.frame(now);

    const snap = transport.snapshot();
    expect(snap.cursorTick).toBe(maxTick); // rested on the final tick
    expect(snap.atEnd).toBe(true);
    expect(snap.ended).toBe(true); // REPLAY affordance is live
  });
});

describe("golden replay — arena state (BUG A)", () => {
  const stream = loadGoldenStream();

  it("the fixture is the real recorded match, not a synthetic stub", () => {
    expect(createHash("sha256").update(readFileSync(FIXTURE)).digest("hex")).toBe(FIXTURE_SHA256);
    expect(stream.length).toBeGreaterThan(100);
    expect(stream.filter((e) => e.event_type === "match_started")).toHaveLength(1);
  });

  it("projects pre-side replay mechs as explicitly neutral without rewriting evidence", () => {
    const started = stream.find((event) => event.event_type === "match_started");
    if (started?.event_type !== "match_started") throw new Error("no match_started");
    expect(started.payload.mechs.map((mech) => mech.side)).toEqual(["neutral", "neutral"]);
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

    const transport = new MatchTransport({ msPerTick: 500 });
    render(
      <PressureDeck
        subscribe={subscribe}
        transport={transport.snapshot()}
        scheduler={{
          request: (callback) => requestAnimationFrame(callback),
          cancel: (handle) => cancelAnimationFrame(handle),
        }}
        controls={{
          togglePlay: () => transport.togglePlay(),
          play: () => transport.play(),
          pause: () => transport.pause(),
          setSpeed: (speed) => transport.setSpeed(speed),
          stepForward: () => transport.stepForward(),
          stepBackward: () => transport.stepBackward(),
          restart: () => transport.restart(),
          goLive: () => transport.goLive(),
          selectMatch: (matchId) => transport.selectMatch(matchId),
        }}
      />,
    );

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
    expect(screen.getByTestId("arena-contract")).toHaveTextContent(
      `ARENA ${started.payload.arena.arena_id} · ${started.payload.arena.size}×${started.payload.arena.size}`,
    );
    for (const mech of started.payload.mechs) {
      const rendered = screen.getByTestId(`arena-mech-${mech.mech_id}`);
      expect(rendered).toBeInTheDocument();
      expect(rendered).toHaveAttribute("data-side", "neutral");
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
