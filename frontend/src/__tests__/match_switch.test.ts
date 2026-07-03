/**
 * Match-switch fold reset — fixture-driven, two interleaved matches.
 *
 * Wires the real {@link MatchTransport} to the real PRESSURE DECK reducer and
 * feeds two full recorded matches (the golden ledger, cloned under a second
 * match id) interleaved frame-by-frame. Proves the operator ask — "run
 * multiple matches and pause them" — at the fold layer: switching the active
 * match RESETS the deck fold and replays ONLY the selected match, so match B's
 * deck never carries a single row from match A.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { MatchTransport } from "../lib/transport";
import { parseEnvelope, type SOEventEnvelope } from "../types";
import { INITIAL, reduce } from "../views/PressureDeck";

const FIXTURE = join(process.cwd(), "src/__tests__/fixtures/golden_match/envelopes.json");

function loadGolden(): SOEventEnvelope[] {
  const raw = JSON.parse(readFileSync(FIXTURE, "utf-8")) as unknown[];
  return raw.map((row) => parseEnvelope(row));
}

/** Re-home a recorded stream under a new match id (routing key is env.match_id). */
function cloneUnderMatchId(stream: SOEventEnvelope[], matchId: string): SOEventEnvelope[] {
  return stream.map((env) => ({
    ...env,
    match_id: matchId,
    envelope: { ...env.envelope, entity_id: matchId },
  }));
}

describe("transport match switch — deck fold reset (two interleaved matches)", () => {
  it("resets the fold and replays only the selected match", () => {
    const golden = loadGolden();
    const idA = golden[0]?.match_id ?? "match.a";
    const idB = "match.golden.bravo";
    const a = golden; // match A = the real recording
    const b = cloneUnderMatchId(golden, idB); // match B = same shape, new id

    const transport = new MatchTransport();

    // Drive the real deck reducer from the transport's release sink.
    let deck = INITIAL;
    transport.setSink({
      reset: () => {},
      release: (batch) => {
        deck = reduce(deck, { type: "BATCH", envs: [...batch] });
      },
    });

    // Interleave both matches frame-by-frame (a demux would separate them).
    const n = Math.max(a.length, b.length);
    for (let i = 0; i < n; i += 1) {
      const eventA = a[i];
      const eventB = b[i];
      if (eventA !== undefined) transport.ingest(eventA);
      if (eventB !== undefined) transport.ingest(eventB);
    }

    // Both matches are visible in the picker.
    expect(
      transport
        .snapshot()
        .matches.map((m) => m.matchId)
        .sort(),
    ).toEqual([idA, idB].sort());

    // Active = A (first seen), live → folds all of match A.
    transport.frame(0);
    expect(deck.matchId).toBe(idA);
    expect(deck.rows.length).toBeGreaterThan(0);
    expect(deck.rows.every((r) => r.env.match_id === idA)).toBe(true);
    const aRowCount = deck.rows.length;

    // Switch to B → fold resets, replays only B.
    transport.selectMatch(idB);
    transport.frame(1);
    expect(deck.matchId).toBe(idB);
    expect(deck.rows.length).toBeGreaterThan(0);
    expect(deck.rows.every((r) => r.env.match_id === idB)).toBe(true);
    // No leakage: B's fold is its own match, not A's rows appended after.
    expect(deck.rows.length).toBe(aRowCount);
    expect(deck.total).toBe(aRowCount);

    // Switch back to A → fold resets again, replays only A.
    transport.selectMatch(idA);
    transport.frame(2);
    expect(deck.matchId).toBe(idA);
    expect(deck.rows.every((r) => r.env.match_id === idA)).toBe(true);
  });
});
