// @vitest-environment jsdom
/**
 * frontend-02 — a drawn match must still render its scorecard.
 *
 * The backend subscribes the ledger BEFORE the scoring reducer, the bus is
 * synchronous and dispatches in subscription order, and `ReducerScoring` scores
 * while HANDLING `match_ended`.  On a draw there is no preceding
 * `victory_declared`, so `match_scored` is legitimately published AFTER the
 * terminal.  `MatchTransport.ingest` used to reject ANY event after
 * `match_ended`, so the scorecard died on every drawn match.
 *
 * This streams a whole drawn match through the real transport, releases it into
 * the real fold sink, and renders the real feedback panel.
 */
import "./setup-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildSideMap, type RiverRow } from "../lib/river";
import { MatchTransport, type ReleaseSink } from "../lib/transport";
import type { SOEventEnvelope } from "../types";
import ArenaFeedback from "../views/ArenaFeedback";
import { makeEnvelope, TEST_ARENA } from "./helpers";

const MATCH_ID = "match.test.draw";

const sides = buildSideMap([
  { mech_id: "mech.red.01", player_id: "player.red", side: "red" },
  { mech_id: "mech.blue.01", player_id: "player.blue", side: "blue" },
]);

/** The canonical event order a mutual-destruction draw actually produces. */
function drawStream(): SOEventEnvelope[] {
  return [
    makeEnvelope(
      "match_started",
      { seed: 17, max_ticks: null, mechs: [], arena: TEST_ARENA },
      { matchId: MATCH_ID, tick: 0 },
    ),
    makeEnvelope("match_tick", {}, { matchId: MATCH_ID, tick: 1 }),
    makeEnvelope(
      "mech_destroyed",
      { cause: "sudden_death", source_mech_id: null },
      { matchId: MATCH_ID, tick: 1, seq: 1, mechId: "mech.red.01", playerId: "player.red" },
    ),
    makeEnvelope(
      "mech_destroyed",
      { cause: "sudden_death", source_mech_id: null },
      { matchId: MATCH_ID, tick: 1, seq: 2, mechId: "mech.blue.01", playerId: "player.blue" },
    ),
    makeEnvelope(
      "match_ended",
      { reason: "draw_mutual_destruction", winner_id: null },
      { matchId: MATCH_ID, tick: 1, seq: 3 },
    ),
    // Emitted by the scoring reducer WHILE handling match_ended, so it lands
    // after the terminal on the synchronous bus.
    makeEnvelope(
      "match_scored",
      {
        kind: "steel_onslaught.match_scored",
        match_id: MATCH_ID,
        winner: null,
        scores: {
          "player.red": {
            victory: 0,
            damage_dealt: 0,
            damage_efficiency: 0,
            pressure_efficiency: 1,
            overload_penalty: 0,
            replay_validity: 1,
            final_score: 10,
          },
          "player.blue": {
            victory: 0,
            damage_dealt: 0,
            damage_efficiency: 0,
            pressure_efficiency: 1,
            overload_penalty: 0,
            replay_validity: 1,
            final_score: 10,
          },
        },
        winner_player_id: "player.blue",
        winner_loadout_id: "loadout.blue",
        winner_score: 10,
        loser_player_id: "player.red",
        loser_score: 10,
        duration_ticks: 1,
        scored_at: "2026-07-21T00:00:00Z",
        is_draw: true,
      },
      { matchId: MATCH_ID, tick: 1, seq: 4 },
    ),
  ];
}

function streamThroughTransport(events: readonly SOEventEnvelope[]): RiverRow[] {
  const released: SOEventEnvelope[] = [];
  const sink: ReleaseSink = {
    reset: () => {
      released.length = 0;
    },
    release: (batch) => {
      released.push(...batch);
    },
  };
  const transport = new MatchTransport({ msPerTick: 500 });
  transport.setSink(sink);
  for (const event of events) transport.ingest(event);
  transport.goLive();
  transport.frame(0);
  return released.map((env, arrival) => ({ env, arrival }));
}

describe("drawn match — scorecard", () => {
  it("ingests the whole draw stream without a projection-integrity failure", () => {
    expect(() => streamThroughTransport(drawStream())).not.toThrow();
  });

  it("renders the league scorecard for a drawn match", () => {
    const rows = streamThroughTransport(drawStream());
    expect(rows.some((row) => row.env.event_type === "match_scored")).toBe(true);

    render(<ArenaFeedback rows={rows} sides={sides} />);

    const league = screen.getByTestId("feedback-league");
    expect(league.textContent).toContain("DRAW");
    expect(screen.getByTestId("feedback-score-player.red")).toBeInTheDocument();
    expect(screen.getByTestId("feedback-score-player.blue")).toBeInTheDocument();
  });
});
