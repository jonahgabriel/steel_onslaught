/**
 * Event River logic tests — PRESSURE DECK (spec §constraints-4).
 *
 * Covers: ordering by (tick, sequence_in_tick); tick grouping; per-group
 * filter toggles; LLM-evidence `payload.kind` discrimination + pairing; side
 * attribution; windowing.
 */
import { describe, expect, it } from "vitest";
import {
  buildSideMap,
  compareRows,
  FILTER_GROUPS,
  filterRows,
  glyphOf,
  groupByTick,
  groupCounts,
  groupOf,
  isDangerEvent,
  llmEvidenceKind,
  orderRows,
  pairLlmEvidence,
  type RiverRow,
  sideOf,
  summarizeEnvelope,
  windowRows,
} from "../lib/river";
import { makeDecision, makeEnvelope, makeLlmRequest, makeLlmResolved } from "./helpers";

function row(env: RiverRow["env"], arrival: number): RiverRow {
  return { env, arrival };
}

describe("ordering by (tick, sequence_in_tick, arrival)", () => {
  it("sorts oldest-first and breaks ties by arrival", () => {
    const a = row(makeEnvelope("match_tick", {}, { tick: 2, seq: 0 }), 0);
    const b = row(makeEnvelope("match_tick", {}, { tick: 1, seq: 1 }), 1);
    const c = row(makeEnvelope("match_tick", {}, { tick: 1, seq: 0 }), 2);
    const d = row(makeEnvelope("match_tick", {}, { tick: 1, seq: 0 }), 3);
    const ordered = orderRows([a, b, c, d]);
    expect(ordered.map((r) => r.arrival)).toEqual([2, 3, 1, 0]);
  });

  it("compareRows is a total order on the key", () => {
    const x = row(makeEnvelope("match_tick", {}, { tick: 1, seq: 0 }), 0);
    const y = row(makeEnvelope("match_tick", {}, { tick: 1, seq: 0 }), 0);
    expect(compareRows(x, y)).toBe(0);
  });

  it("does not mutate its input", () => {
    const input = [
      row(makeEnvelope("match_tick", {}, { tick: 2 }), 0),
      row(makeEnvelope("match_tick", {}, { tick: 1 }), 1),
    ];
    const snapshot = [...input];
    orderRows(input);
    expect(input).toEqual(snapshot);
  });
});

describe("groupByTick", () => {
  it("collects contiguous rows under tick separators", () => {
    const rows = orderRows([
      row(makeEnvelope("match_tick", {}, { tick: 1, seq: 0 }), 0),
      row(
        makeEnvelope(
          "weapon_fired",
          {
            weapon_id: "w",
            target_id: "mech.blue.01",
            hit_probability: 0.5,
            pressure_cost: 1,
            heat_generated: 1,
          },
          { tick: 1, seq: 1 },
        ),
        1,
      ),
      row(makeEnvelope("match_tick", {}, { tick: 2, seq: 0 }), 2),
    ]);
    const groups = groupByTick(rows);
    expect(groups.map((g) => g.tick)).toEqual([1, 2]);
    expect(groups[0]?.rows).toHaveLength(2);
    expect(groups[1]?.rows).toHaveLength(1);
  });
});

describe("filter groups", () => {
  it("maps event types to the five ticker groups", () => {
    expect(
      groupOf(
        makeEnvelope("weapon_fired", {
          weapon_id: "w",
          target_id: "t",
          hit_probability: 0.5,
          pressure_cost: 1,
          heat_generated: 1,
        }),
      ),
    ).toBe("combat");
    expect(groupOf(makeDecision())).toBe("decisions");
    expect(
      groupOf(
        makeEnvelope("boiler_updated", {
          pressure_before: 1,
          pressure_after: 1,
          heat_before: 1,
          heat_after: 1,
        }),
      ),
    ).toBe("thermal");
    expect(groupOf(makeEnvelope("victory_declared", { winner_player_id: "p", reason: "r" }))).toBe(
      "lifecycle",
    );
  });

  it("LLM evidence overrides the underlying event type", () => {
    expect(groupOf(makeLlmRequest())).toBe("llm");
    expect(groupOf(makeLlmResolved())).toBe("llm");
  });

  it("toggling a group off hides its rows and keeps the rest", () => {
    const rows = [
      row(makeDecision(), 0),
      row(
        makeEnvelope("weapon_fired", {
          weapon_id: "w",
          target_id: "t",
          hit_probability: 0.5,
          pressure_cost: 1,
          heat_generated: 1,
        }),
        1,
      ),
      row(makeLlmRequest(), 2),
    ];
    const active = new Set(FILTER_GROUPS);
    active.delete("combat");
    const kept = filterRows(rows, active);
    expect(kept.map((r) => groupOf(r.env))).toEqual(["decisions", "llm"]);
  });

  it("groupCounts tallies every group", () => {
    const counts = groupCounts([row(makeDecision(), 0), row(makeLlmRequest(), 1)]);
    expect(counts.decisions).toBe(1);
    expect(counts.llm).toBe(1);
    expect(counts.combat).toBe(0);
  });
});

describe("LLM evidence discrimination + pairing", () => {
  it("discriminates on payload.kind, not on a new enum member", () => {
    expect(makeLlmRequest().event_type).toBe("sensor_observation");
    expect(llmEvidenceKind(makeLlmRequest())).toBe("requested");
    expect(llmEvidenceKind(makeLlmResolved())).toBe("resolved");
    expect(
      llmEvidenceKind(
        makeEnvelope("sensor_observation", {
          enemy_mech_id: "mech.blue.01",
          distance_estimate: 5,
          confidence: 0.9,
        }),
      ),
    ).toBeNull();
  });

  it("pairs a request with the next resolve for the same mech", () => {
    const req = makeLlmRequest({ mechId: "mech.red.01", messageId: "req1" });
    const res = makeLlmResolved({ mechId: "mech.red.01", model: "provider.glm.flash" });
    const { pairs, unresolved } = pairLlmEvidence([req, res]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0]?.resolved).not.toBeNull();
    expect(unresolved.size).toBe(0);
  });

  it("leaves an unmatched request 'thinking'", () => {
    const req = makeLlmRequest({ mechId: "mech.red.01", messageId: "req1" });
    const { pairs, unresolved } = pairLlmEvidence([req]);
    expect(pairs[0]?.resolved).toBeNull();
    expect(unresolved.has("req1")).toBe(true);
  });

  it("summarizes resolved evidence with token counts", () => {
    const res = makeLlmResolved({ promptTokens: 100, completionTokens: 40 });
    expect(summarizeEnvelope(res)).toContain("100→40 tok");
  });
});

describe("side attribution", () => {
  it("assigns RED/BLUE by sorted player id", () => {
    const sides = buildSideMap([
      { mech_id: "mech.blue.01", player_id: "player.b" },
      { mech_id: "mech.red.01", player_id: "player.a" },
    ]);
    expect(sides.byMech.get("mech.red.01")).toBe("red");
    expect(sides.byMech.get("mech.blue.01")).toBe("blue");
  });

  it("maps a row to its subject's side, neutral for the match subject", () => {
    const sides = buildSideMap([{ mech_id: "mech.red.01", player_id: "player.a" }]);
    expect(sideOf(makeDecision({ mechId: "mech.red.01" }), sides)).toBe("red");
    expect(sideOf(makeLlmRequest({ mechId: "mech.gone" }), sides)).toBe("neutral");
  });
});

describe("windowing + glyphs + danger", () => {
  it("windows to the last N rows and counts the hidden remainder", () => {
    const rows = Array.from({ length: 10 }, (_, i) =>
      row(makeEnvelope("match_tick", {}, { tick: i }), i),
    );
    const w = windowRows(rows, 4);
    expect(w.visible).toHaveLength(4);
    expect(w.hiddenCount).toBe(6);
    expect(w.visible[0]?.env.tick).toBe(6);
  });

  it("flags danger events and picks glyphs", () => {
    expect(isDangerEvent(makeEnvelope("mech_destroyed", { cause: "boiler" }))).toBe(true);
    expect(isDangerEvent(makeDecision())).toBe(false);
    expect(glyphOf(makeLlmRequest())).toBe("❯");
    expect(glyphOf(makeDecision())).toBe("◇");
  });
});
