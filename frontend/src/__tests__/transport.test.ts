/**
 * MatchTransport engine — pure, injected-clock unit tests.
 *
 * Proves the client owns pacing: pause freezes the cursor, speed scales the
 * tick rate, step reveals/retracts exactly one tick, LIVE follows the buffer
 * end, and a match switch resets the fold and replays the other buffer.
 */
import { describe, expect, it } from "vitest";
import { MatchTransport, type ReleaseSink } from "../lib/transport";
import type { SOEventEnvelope } from "../types";
import { makeEnvelope } from "./helpers";

/** One `match_tick` per tick 0..n-1 for `matchId`. */
function tickStream(matchId: string, n: number): SOEventEnvelope[] {
  const out: SOEventEnvelope[] = [
    makeEnvelope("match_started", { seed: 1, max_ticks: n, mechs: [] }, { matchId, tick: 0 }),
  ];
  for (let t = 1; t < n; t += 1) {
    out.push(makeEnvelope("match_tick", {}, { matchId, tick: t }));
  }
  return out;
}

/** A sink that mirrors a downstream fold: reset() clears, release() appends. */
function recordingSink(): {
  sink: ReleaseSink;
  released: SOEventEnvelope[];
  resets: number;
} {
  const state = { released: [] as SOEventEnvelope[], resets: 0 };
  const sink: ReleaseSink = {
    reset: () => {
      state.resets += 1;
      state.released = [];
    },
    release: (batch) => {
      state.released.push(...batch);
    },
  };
  return {
    sink,
    get released() {
      return state.released;
    },
    get resets() {
      return state.resets;
    },
  };
}

describe("MatchTransport — buffering", () => {
  it("splits an interleaved multi-match stream into per-match buffers", () => {
    const t = new MatchTransport();
    const a = tickStream("match.alpha", 3);
    const b = tickStream("match.bravo", 5);
    // Interleave the two matches' frames as a mux would deliver them.
    for (let i = 0; i < 5; i += 1) {
      const eventA = a[i];
      const eventB = b[i];
      if (eventA !== undefined) t.ingest(eventA);
      if (eventB !== undefined) t.ingest(eventB);
    }
    const snap = t.snapshot();
    expect(snap.matches.map((m) => m.matchId).sort()).toEqual(["match.alpha", "match.bravo"]);
    const alpha = snap.matches.find((m) => m.matchId === "match.alpha");
    const bravo = snap.matches.find((m) => m.matchId === "match.bravo");
    expect(alpha?.tickCount).toBe(3); // ticks 0..2 → count 3
    expect(bravo?.tickCount).toBe(5);
    expect(snap.activeMatchId).toBe("match.alpha"); // first seen is active
  });
});

describe("MatchTransport — pause freezes the cursor", () => {
  it("advances while playing and freezes on pause", () => {
    const t = new MatchTransport({ msPerTick: 100 });
    for (const e of tickStream("m", 5)) t.ingest(e);

    t.play();
    t.frame(0); // primeImmediate reveals tick 0
    expect(t.snapshot().cursorTick).toBe(0);
    t.frame(100); // one tick-duration elapsed → tick 1
    expect(t.snapshot().cursorTick).toBe(1);

    t.pause();
    t.frame(100_000); // huge jump, but paused → cursor frozen
    expect(t.snapshot().cursorTick).toBe(1);
    expect(t.snapshot().status).toBe("paused");
  });
});

describe("MatchTransport — speed scales the tick rate", () => {
  it("×2 releases twice as many ticks per wall-clock window as ×1", () => {
    const build = (): MatchTransport => {
      const t = new MatchTransport({ msPerTick: 100 });
      for (const e of tickStream("m", 6)) t.ingest(e);
      t.play();
      return t;
    };

    const one = build();
    one.frame(0); // tick 0
    one.frame(100); // +1 tick → tick 1
    expect(one.snapshot().cursorTick).toBe(1);

    const two = build();
    two.setSpeed(2); // dur 50ms
    two.frame(0); // tick 0
    two.frame(100); // 100ms / 50ms → +2 ticks → tick 2
    expect(two.snapshot().cursorTick).toBe(2);
  });
});

describe("MatchTransport — step ±1 tick", () => {
  it("reveals one tick forward, then retracts it (rebuilding the prefix)", () => {
    const t = new MatchTransport({ msPerTick: 100 });
    for (const e of tickStream("m", 4)) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    t.stepForward();
    t.frame(0);
    expect(t.snapshot().cursorTick).toBe(0);
    expect(t.snapshot().status).toBe("paused");

    t.stepForward();
    t.frame(1);
    expect(t.snapshot().cursorTick).toBe(1);

    const resetsBefore = rec.resets;
    t.stepBackward();
    t.frame(2);
    // Fold is forward-only, so a backward step resets and replays the prefix.
    expect(rec.resets).toBe(resetsBefore + 1);
    expect(t.snapshot().cursorTick).toBe(0);
    // Rebuilt prefix is exactly tick 0 (the match_started frame).
    expect(rec.released.map((e) => e.tick)).toEqual([0]);
  });
});

describe("MatchTransport — LIVE follows the buffer end", () => {
  it("releases everything buffered and keeps following new frames", () => {
    const t = new MatchTransport();
    const stream = tickStream("m", 3);
    for (const e of stream) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    // Default status is live → first frame releases the whole buffer.
    t.frame(0);
    expect(rec.released).toHaveLength(3);
    expect(t.snapshot().cursorTick).toBe(2);

    // A late frame arrives; the next animation frame follows it.
    t.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 3 }));
    t.frame(16);
    expect(rec.released).toHaveLength(4);
    expect(t.snapshot().cursorTick).toBe(3);
  });
});

describe("MatchTransport — match switch resets and replays", () => {
  it("switching active match resets the fold and replays only that buffer", () => {
    const t = new MatchTransport();
    const a = tickStream("match.alpha", 3);
    const b = tickStream("match.bravo", 4);
    // Interleaved ingest — buffers must stay separate.
    for (let i = 0; i < 4; i += 1) {
      const eventA = a[i];
      const eventB = b[i];
      if (eventA !== undefined) t.ingest(eventA);
      if (eventB !== undefined) t.ingest(eventB);
    }
    const rec = recordingSink();
    t.setSink(rec.sink);

    // Active = alpha (first seen), live → releases alpha in full.
    t.frame(0);
    expect(rec.released.every((e) => e.match_id === "match.alpha")).toBe(true);

    const resetsBefore = rec.resets;
    t.selectMatch("match.bravo");
    t.frame(1);

    expect(rec.resets).toBe(resetsBefore + 1); // fold was cleared
    expect(rec.released.length).toBeGreaterThan(0);
    expect(rec.released.every((e) => e.match_id === "match.bravo")).toBe(true);
    // The replay begins with the match's setup frame.
    expect(rec.released[0]?.event_type).toBe("match_started");
    expect(t.snapshot().activeMatchId).toBe("match.bravo");
  });

  it("switching while paused reveals the new match's setup tick immediately", () => {
    const t = new MatchTransport();
    for (const e of tickStream("match.alpha", 3)) t.ingest(e);
    for (const e of tickStream("match.bravo", 3)) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    t.pause();
    t.selectMatch("match.bravo");
    t.frame(0);
    // Even paused, the operator sees bravo's tick 0 board (not a blank deck).
    expect(rec.released.map((e) => e.match_id)).toEqual(["match.bravo"]);
    expect(rec.released[0]?.event_type).toBe("match_started");
    expect(t.snapshot().cursorTick).toBe(0);
  });
});

describe("MatchTransport — restart", () => {
  it("rewinds to tick 0 and plays forward", () => {
    const t = new MatchTransport({ msPerTick: 100 });
    for (const e of tickStream("m", 4)) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    t.play();
    t.frame(0);
    t.frame(100);
    t.frame(200); // advanced a few ticks
    expect(t.snapshot().cursorTick).toBeGreaterThan(0);

    const resetsBefore = rec.resets;
    t.restart();
    t.frame(300); // reset + prime reveals tick 0
    expect(rec.resets).toBe(resetsBefore + 1);
    expect(t.snapshot().cursorTick).toBe(0);
    expect(t.snapshot().status).toBe("playing");
  });
});
