import { describe, expect, it } from "vitest";
import {
  buildDecisionCards,
  buildLeague,
  buildMomentum,
  buildRecap,
  buildTelegraphs,
} from "../lib/feedback";
import { buildSideMap, type RiverRow } from "../lib/river";
import { makeDecision, makeEnvelope } from "./helpers";

const sides = buildSideMap([
  { mech_id: "mech.red.01", player_id: "player.red", side: "red" },
  { mech_id: "mech.blue.01", player_id: "player.blue", side: "blue" },
]);

function rows(...envs: readonly RiverRow["env"][]): RiverRow[] {
  return envs.map((env, arrival) => ({ env, arrival }));
}

describe("arena feedback projections", () => {
  it("computes a bounded recent-event edge without changing source events", () => {
    const hit = makeEnvelope(
      "hit_resolved",
      {
        attacker_id: "mech.red.01",
        defender_id: "mech.blue.01",
        result: { hit: true, damage_after_armor: 8 },
      },
      { mechId: "mech.red.01", playerId: "player.red", tick: 4 },
    );
    const snapshot = buildMomentum(rows(hit), sides);
    expect(snapshot.red).toBeGreaterThan(snapshot.blue);
    expect(snapshot.red).toBeGreaterThanOrEqual(0);
    expect(snapshot.red).toBeLessThanOrEqual(100);
    expect(snapshot.leader).toBe("red");
  });

  it("keeps an intent telegraphed until its canonical resolution arrives", () => {
    const intent = makeEnvelope(
      "move_intent",
      { direction: "flank_left", speed: "full" },
      { mechId: "mech.red.01", playerId: "player.red", tick: 6 },
    );
    expect(buildTelegraphs(rows(intent), sides)[0]).toMatchObject({
      kind: "MOVE",
      status: "TELEGRAPHED",
    });

    const resolved = makeEnvelope(
      "movement_resolved",
      {
        from: { x: 3, y: 3 },
        to: { x: 4, y: 3 },
        ticks_consumed: 1,
        pressure_consumed: 2,
      },
      {
        mechId: "mech.red.01",
        playerId: "player.red",
        tick: 6,
        causationId: intent.envelope.message_id,
      },
    );
    expect(buildTelegraphs(rows(intent, resolved), sides)[0]).toMatchObject({
      kind: "MOVE",
      status: "RESOLVED",
    });
  });

  it("projects latest pilot rationale as a read-only decision card", () => {
    const decision = makeDecision({
      mechId: "mech.blue.01",
      playerId: "player.blue",
      action: "vent",
      rationale: "Bleed pressure before the next exchange.",
      confidence: 0.72,
      tick: 9,
    });
    expect(buildDecisionCards(rows(decision), sides)).toEqual([
      expect.objectContaining({
        mechId: "mech.blue.01",
        action: "vent",
        rationale: "Bleed pressure before the next exchange.",
        confidence: 0.72,
      }),
    ]);
  });

  it("builds a terminal recap and scorecard only from canonical events", () => {
    const ended = makeEnvelope(
      "match_ended",
      { reason: "last_mech_standing", winner_id: "player.red" },
      { mechId: "mech.red.01", playerId: "player.red", tick: 12 },
    );
    const scored = makeEnvelope(
      "match_scored",
      {
        kind: "steel_onslaught.match_scored",
        match_id: "match.test.0001",
        winner: { player_id: "player.red", mech_id: "mech.red.01" },
        scores: {
          "player.red": {
            victory: 1,
            damage_dealt: 30,
            damage_efficiency: 0.8,
            pressure_efficiency: 0.7,
            overload_penalty: 0,
            replay_validity: 1,
            final_score: 91,
          },
          "player.blue": {
            victory: 0,
            damage_dealt: 12,
            damage_efficiency: 0.4,
            pressure_efficiency: 0.5,
            overload_penalty: 2,
            replay_validity: 1,
            final_score: 48,
          },
        },
        winner_player_id: "player.red",
        winner_loadout_id: "loadout.red",
        winner_score: 91,
        loser_player_id: "player.blue",
        loser_score: 48,
        duration_ticks: 12,
        scored_at: "2026-07-18T00:00:00Z",
        is_draw: false,
      },
      { mechId: "mech.red.01", playerId: "player.red", tick: 12 },
    );
    const recap = buildRecap(rows(ended), sides);
    expect(recap[0]).toMatchObject({ tick: 12, side: "red" });
    expect(buildLeague(rows(ended, scored), sides)).toMatchObject({
      durationTicks: 12,
      entries: [
        expect.objectContaining({ playerId: "player.red", winner: true, score: 91 }),
        expect.objectContaining({ playerId: "player.blue", winner: false, score: 48 }),
      ],
    });
  });
});
