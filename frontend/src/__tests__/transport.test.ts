/**
 * MatchTransport engine — pure, injected-clock unit tests.
 *
 * Proves the client owns pacing: pause freezes the cursor, speed scales the
 * tick rate, step reveals/retracts exactly one tick, LIVE follows the buffer
 * end, and a match switch resets the fold and replays the other buffer.
 */
import { describe, expect, it, vi } from "vitest";
import { MatchTransport, type ReleaseSink } from "../lib/transport";
import type { SOEventEnvelope } from "../types";
import { makeEnvelope, makeLlmFailed, makeLlmRequest, makeLlmResolved } from "./helpers";

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
    const t = new MatchTransport({ msPerTick: 500 });
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

describe("MatchTransport — default auto-play replay (rule 1)", () => {
  it("auto-plays from tick 0 at ×1 without any explicit play() call", () => {
    const t = new MatchTransport({ msPerTick: 100 });
    for (const e of tickStream("m", 5)) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    // No play()/goLive() — the engine defaults to a paced replay.
    expect(t.snapshot().status).toBe("playing");
    expect(t.snapshot().speed).toBe(1);

    t.frame(0); // primeImmediate reveals only tick 0 — NOT the whole buffer
    expect(t.snapshot().cursorTick).toBe(0);
    expect(rec.released.map((e) => e.tick)).toEqual([0]);
    expect(t.snapshot().atEnd).toBe(false);

    t.frame(100); // one tick-duration → tick 1
    expect(t.snapshot().cursorTick).toBe(1);
    // Still mid-playback, cursor has NOT jumped to the buffer end.
    expect(t.snapshot().cursorTick).toBeLessThan(t.snapshot().bufferedTick);
  });

  it("holds at the buffer head of a still-streaming match, then resumes as frames arrive", () => {
    const t = new MatchTransport({ msPerTick: 100 });
    // Only ticks 0..2 buffered so far; the match is NOT finished.
    for (const e of tickStream("m", 3)) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    t.frame(0); // tick 0
    t.frame(100); // tick 1
    t.frame(200); // tick 2 — caught up to the buffer head
    expect(t.snapshot().cursorTick).toBe(2);
    expect(t.snapshot().atEnd).toBe(true);
    expect(t.snapshot().ended).toBe(false); // holding, not finished

    // A huge wall-clock jump while at the head must NOT force anything (no data).
    t.frame(10_000);
    expect(t.snapshot().cursorTick).toBe(2);

    // New frames stream in; playback resumes paced from `now` (no catch-up burst).
    t.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 3 }));
    t.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 4 }));
    t.frame(10_050); // < one tick-duration since re-anchor → nothing yet
    expect(t.snapshot().cursorTick).toBe(2);
    t.frame(10_100); // one tick-duration later → tick 3
    expect(t.snapshot().cursorTick).toBe(3);
  });
});

describe("MatchTransport — LIVE is opt-in (rule 2)", () => {
  it("goLive() jumps to the buffer end and follows new frames", () => {
    const t = new MatchTransport({ msPerTick: 500 });
    const stream = tickStream("m", 3);
    for (const e of stream) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    // LIVE must be entered explicitly — the default no longer jumps to the end.
    t.goLive();
    t.frame(0); // live → releases the whole buffer at once
    expect(rec.released).toHaveLength(3);
    expect(t.snapshot().cursorTick).toBe(2);
    expect(t.snapshot().status).toBe("live");

    // A late frame arrives; the next animation frame follows it.
    t.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 3 }));
    t.frame(16);
    expect(rec.released).toHaveLength(4);
    expect(t.snapshot().cursorTick).toBe(3);
  });
});

describe("MatchTransport — finished match stops with a REPLAY affordance (rule 3)", () => {
  it("stops on the final tick and flags `ended`; restart replays from tick 0", () => {
    const t = new MatchTransport({ msPerTick: 10 });
    const stream: SOEventEnvelope[] = [
      makeEnvelope(
        "match_started",
        { seed: 1, max_ticks: 3, mechs: [] },
        { matchId: "m", tick: 0 },
      ),
      makeEnvelope("match_tick", {}, { matchId: "m", tick: 1 }),
      makeEnvelope(
        "victory_declared",
        { winner_player_id: "player.red", reason: "pilot_killed" },
        {
          matchId: "m",
          tick: 2,
        },
      ),
      makeEnvelope(
        "match_ended",
        { reason: "pilot_killed", winner_id: "mech.red.01" },
        {
          matchId: "m",
          tick: 2,
        },
      ),
    ];
    for (const e of stream) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);
    expect(t.snapshot().matchComplete).toBe(true);

    // Drive the paced replay to the end.
    for (let now = 0; now <= 60; now += 10) t.frame(now);
    expect(t.snapshot().atEnd).toBe(true);
    expect(t.snapshot().cursorTick).toBe(2); // rested on the final tick
    expect(t.snapshot().ended).toBe(true); // REPLAY affordance is live

    // Further frames do nothing — playback has stopped.
    const releasedAtEnd = rec.released.length;
    t.frame(100_000);
    expect(rec.released.length).toBe(releasedAtEnd);

    // Restart replays from tick 0 and clears `ended`.
    const resetsBefore = rec.resets;
    t.restart();
    t.frame(100_010);
    expect(rec.resets).toBe(resetsBefore + 1);
    expect(t.snapshot().cursorTick).toBe(0);
    expect(t.snapshot().ended).toBe(false);
    expect(t.snapshot().status).toBe("playing");
  });

  it("does not flag `ended` while a live-followed match sits at its end", () => {
    const t = new MatchTransport({ msPerTick: 500 });
    const stream: SOEventEnvelope[] = [
      ...tickStream("m", 2),
      makeEnvelope(
        "match_ended",
        { reason: "pilot_killed", winner_id: null },
        { matchId: "m", tick: 1 },
      ),
    ];
    for (const e of stream) t.ingest(e);
    t.goLive();
    t.frame(0);
    expect(t.snapshot().atEnd).toBe(true);
    expect(t.snapshot().matchComplete).toBe(true);
    // LIVE is a deliberate follow — no REPLAY affordance.
    expect(t.snapshot().ended).toBe(false);
  });
});

describe("MatchTransport — match switch auto-plays the new match (rule 4)", () => {
  it("switching active match resets the fold and auto-plays that buffer from tick 0", () => {
    const t = new MatchTransport({ msPerTick: 100 });
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

    // Active = alpha (first seen); default paced replay reveals alpha's tick 0.
    t.frame(0);
    expect(rec.released.every((e) => e.match_id === "match.alpha")).toBe(true);

    const resetsBefore = rec.resets;
    t.selectMatch("match.bravo");
    t.frame(1);

    expect(rec.resets).toBe(resetsBefore + 1); // fold was cleared
    expect(rec.released.length).toBeGreaterThan(0);
    expect(rec.released.every((e) => e.match_id === "match.bravo")).toBe(true);
    // The replay begins at tick 0 with the match's setup frame …
    expect(rec.released[0]?.event_type).toBe("match_started");
    expect(t.snapshot().cursorTick).toBe(0);
    // … and it is a paced auto-play (playing), not a jump-to-end.
    expect(t.snapshot().status).toBe("playing");
    expect(t.snapshot().activeMatchId).toBe("match.bravo");

    // Paced playback continues on subsequent frames.
    t.frame(101);
    expect(t.snapshot().cursorTick).toBe(1);
  });

  it("auto-plays from tick 0 even when the prior mode was LIVE", () => {
    const t = new MatchTransport({ msPerTick: 500 });
    for (const e of tickStream("match.alpha", 3)) t.ingest(e);
    for (const e of tickStream("match.bravo", 5)) t.ingest(e);
    const rec = recordingSink();
    t.setSink(rec.sink);

    // Operator was following alpha live …
    t.goLive();
    t.frame(0);
    expect(t.snapshot().status).toBe("live");

    // … switching leaves LIVE and starts bravo as a paced replay from tick 0.
    t.selectMatch("match.bravo");
    t.frame(1);
    expect(rec.released.map((e) => e.match_id)).toEqual(["match.bravo"]);
    expect(rec.released[0]?.event_type).toBe("match_started");
    expect(t.snapshot().status).toBe("playing");
    expect(t.snapshot().cursorTick).toBe(0);
    expect(t.snapshot().atEnd).toBe(false); // did NOT jump to bravo's end
  });
});

/** A complete match 0..(n-1); the final tick carries a `match_ended` terminal. */
function completeMatch(matchId: string, n: number): SOEventEnvelope[] {
  const out: SOEventEnvelope[] = [
    makeEnvelope("match_started", { seed: 1, max_ticks: n, mechs: [] }, { matchId, tick: 0 }),
  ];
  for (let t = 1; t < n - 1; t += 1) {
    out.push(makeEnvelope("match_tick", {}, { matchId, tick: t }));
  }
  out.push(
    makeEnvelope(
      "match_ended",
      { reason: "pilot_killed", winner_id: null },
      { matchId, tick: n - 1 },
    ),
  );
  return out;
}

describe("MatchTransport — StrictMode double-connect (D1 pacing-burst race)", () => {
  it("dedupes a full duplicate re-stream after a partial one and stays paced", () => {
    // Exact StrictMode sequence: transport created → sink set → rAF frames pumped
    // with realistic epochs (start at 5000ms, NOT 0) → partial ingest (stream #1
    // that closed early) → sink unset/reset (unmount) → full duplicate ingest
    // (stream #2 re-streaming ALL events) → assert paced release with no burst and
    // no duplicate rows downstream.
    const t = new MatchTransport({ msPerTick: 500 });
    const rec = recordingSink();
    let unsink = t.setSink(rec.sink);

    // The server's canonical stream for a 6-tick match, built once so the
    // duplicate re-stream reuses identical envelope `message_id`s.
    const full = completeMatch("m", 6); // ticks 0..5, ended at 5

    // --- stream #1: delivered ticks 0,1,2 then the socket closed early. ---
    for (const e of full.slice(0, 3)) t.ingest(e);

    let now = 5000; // realistic performance.now() epoch, not 0
    t.frame(now); // prime → tick 0
    expect(t.snapshot().cursorTick).toBe(0);
    now += 500;
    t.frame(now); // tick 1
    now += 500;
    t.frame(now); // tick 2 — caught up to the partial head
    expect(t.snapshot().cursorTick).toBe(2);

    // Idle wall-clock passes while the cursor holds at the partial head (rAF keeps
    // pumping). Unanchored, this accrued time is what floods out as a burst.
    for (let k = 0; k < 20; k += 1) {
      now += 500;
      t.frame(now);
    }
    expect(t.snapshot().cursorTick).toBe(2); // still holding, no burst

    // --- unmount (sink unset) then remount (sink re-set); stream #2 re-streams
    //     the ENTIRE match — every envelope duplicated. ---
    unsink();
    unsink = t.setSink(rec.sink);
    for (const e of full) t.ingest(e); // dup of 0,1,2 + new 3,4,5

    // Dedup: the duplicate re-stream must NOT have doubled the buffer.
    expect(t.snapshot().bufferedCount).toBe(full.length); // 6, not 9

    // Resume: the remaining ticks release paced — one per ~500ms — and the
    // accrued idle time does NOT flood.
    const releasedBefore = rec.released.length;
    now += 16;
    t.frame(now); // < one tick-duration since resume-anchor → nothing yet
    expect(rec.released.length).toBe(releasedBefore);
    now += 500;
    t.frame(now);
    expect(t.snapshot().cursorTick).toBe(3);
    now += 500;
    t.frame(now);
    expect(t.snapshot().cursorTick).toBe(4);
    now += 500;
    t.frame(now);
    expect(t.snapshot().cursorTick).toBe(5);

    // No duplicate rows downstream: each tick appears exactly once, in order.
    expect(rec.released.map((e) => e.tick)).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("rejects fresh events after canonical match_ended", () => {
    const t = new MatchTransport({ msPerTick: 500 });
    for (const e of completeMatch("m", 6) /* 0..5 */) t.ingest(e);
    expect(() => t.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 6 }))).toThrow(
      /after match_ended/,
    );
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

describe("MatchTransport — projection integrity", () => {
  it("deduplicates an identical message but rejects reused identity with different content", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    transport.ingest(started);
    const event = makeEnvelope("match_tick", {}, { matchId: "m", tick: 1, messageId: "same" });
    transport.ingest(event);
    transport.ingest(event);
    expect(transport.snapshot().bufferedCount).toBe(2);
    expect(() => transport.ingest({ ...event, producer_node: "node.tampered" })).toThrow(
      /different envelope content/,
    );
  });

  it("rejects one message identity reused across match boundaries", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    transport.ingest(
      makeEnvelope(
        "match_started",
        { seed: 1, max_ticks: 1, mechs: [] },
        { matchId: "match.alpha", messageId: "global-message" },
      ),
    );
    expect(() =>
      transport.ingest(
        makeEnvelope(
          "match_started",
          { seed: 1, max_ticks: 1, mechs: [] },
          { matchId: "match.bravo", messageId: "global-message" },
        ),
      ),
    ).toThrow(/reused with different envelope content/);
  });

  it("fingerprints structural content independent of object key insertion order", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    transport.ingest(started);
    const decision = makeEnvelope(
      "pilot_decision_made",
      {
        action: "remain",
        action_params: { alpha: 1, beta: 2 },
        reason_code: "no_viable_action",
        confidence: 1,
        considered_actions: [{ action: "remain", score: 1 }],
        rationale: null,
      },
      { matchId: "m", tick: 1, messageId: "canonical-content" },
    );
    transport.ingest(decision);
    transport.ingest({
      ...decision,
      payload: { ...decision.payload, action_params: { beta: 2, alpha: 1 } },
    });
    expect(transport.snapshot().bufferedCount).toBe(2);
    expect(() =>
      transport.ingest({
        ...decision,
        payload: { ...decision.payload, action_params: { beta: 3, alpha: 1 } },
      }),
    ).toThrow(/different envelope content/);
  });

  it("orders same-position events without consulting process locale", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    transport.ingest(started);
    const first = makeEnvelope("match_tick", {}, { matchId: "m", tick: 1, seq: 0 });
    const second = makeEnvelope("match_tick", {}, { matchId: "m", tick: 1, seq: 0 });
    const localeCompare = vi.spyOn(String.prototype, "localeCompare").mockImplementation(() => {
      throw new Error("ambient locale authority used");
    });
    try {
      transport.ingest(first);
      transport.ingest(second);
    } finally {
      localeCompare.mockRestore();
    }
    transport.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 2 }));
    expect(transport.snapshot().bufferedCount).toBe(4);
  });

  it("rejects entity mismatch, non-canonical first event, and per-match order regression", () => {
    const entityMismatch = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    expect(() =>
      entityMismatch.ingest({
        ...started,
        envelope: { ...started.envelope, entity_id: "different" },
      }),
    ).toThrow(/does not equal match_id/);

    const missingStart = new MatchTransport({ msPerTick: 500 });
    expect(() =>
      missingStart.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 1 })),
    ).toThrow(/first event/);

    const outOfOrder = new MatchTransport({ msPerTick: 500 });
    outOfOrder.ingest(started);
    outOfOrder.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 2 }));
    expect(() =>
      outOfOrder.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 1 })),
    ).toThrow(/not strictly monotonic/);
  });

  it("treats only match_ended as terminal", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    transport.ingest(started);
    transport.ingest(
      makeEnvelope(
        "victory_declared",
        { winner_player_id: "player.red", reason: "last_mech_standing" },
        { matchId: "m", tick: 1 },
      ),
    );
    expect(transport.snapshot().matchComplete).toBe(false);
    transport.ingest(makeEnvelope("match_tick", {}, { matchId: "m", tick: 2 }));
    transport.ingest(
      makeEnvelope(
        "match_ended",
        { reason: "last_mech_standing", winner_id: "player.red" },
        { matchId: "m", tick: 3 },
      ),
    );
    expect(transport.snapshot().matchComplete).toBe(true);
  });

  it("requires exactly one causally-linked terminal per LLM request", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    transport.ingest(started);
    const request = makeLlmRequest({ matchId: "m", tick: 1, messageId: "request-1" });
    transport.ingest(request);
    transport.ingest(makeLlmResolved({ matchId: "m", tick: 1, seq: 1, causationId: "request-1" }));
    expect(() =>
      transport.ingest(makeLlmFailed({ matchId: "m", tick: 2, causationId: "request-1" })),
    ).toThrow(/multiple terminals/);

    const orphan = new MatchTransport({ msPerTick: 500 });
    orphan.ingest(started);
    expect(() =>
      orphan.ingest(makeLlmResolved({ matchId: "m", tick: 1, causationId: "missing" })),
    ).toThrow(/canonical request message_id/);
  });

  it("rejects match_ended while an LLM request lacks terminal evidence", () => {
    const transport = new MatchTransport({ msPerTick: 500 });
    const [started] = tickStream("m", 1);
    if (started === undefined) throw new Error("missing match_started fixture");
    transport.ingest(started);
    transport.ingest(makeLlmRequest({ matchId: "m", tick: 1, messageId: "pending" }));
    expect(() =>
      transport.ingest(
        makeEnvelope(
          "match_ended",
          { reason: "aborted", winner_id: null },
          { matchId: "m", tick: 2 },
        ),
      ),
    ).toThrow(/unresolved LLM completion/);
  });
});
