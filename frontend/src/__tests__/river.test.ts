/**
 * Event River logic tests — PRESSURE DECK (spec §constraints-4).
 *
 * Covers: ordering by (tick, sequence_in_tick); tick grouping; per-group
 * filter toggles; LLM-evidence event-type discrimination + pairing; side
 * attribution; windowing.
 */
import { describe, expect, it } from "vitest";
import {
  buildSideMap,
  compareRows,
  confidenceOf,
  FILTER_GROUPS,
  filterRows,
  glyphOf,
  groupByTick,
  groupCounts,
  groupOf,
  isDangerEvent,
  isReasoningEvent,
  llmEvidenceKind,
  orderedRegisters,
  orderRows,
  pairLlmEvidence,
  planSequence,
  type RiverRow,
  rationaleOf,
  sideOf,
  summarizeEnvelope,
  windowRows,
} from "../lib/river";
import {
  makeDecision,
  makeEnvelope,
  makeLlmFailed,
  makeLlmRequest,
  makeLlmResolved,
  makePlan,
} from "./helpers";

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
    expect(
      groupOf(
        makeEnvelope("victory_declared", {
          winner_player_id: "p",
          reason: "last_mech_standing",
          victory_kind: "elimination",
        }),
      ),
    ).toBe("lifecycle");
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
  it("discriminates on the first-class LLM event type", () => {
    expect(makeLlmRequest().event_type).toBe("llm_completion_requested");
    expect(makeLlmResolved().event_type).toBe("llm_completion_resolved");
    expect(makeLlmFailed().event_type).toBe("llm_completion_failed");
    expect(llmEvidenceKind(makeLlmRequest())).toBe("requested");
    expect(llmEvidenceKind(makeLlmResolved())).toBe("resolved");
    expect(llmEvidenceKind(makeLlmFailed())).toBe("failed");
    expect(
      llmEvidenceKind(
        makeEnvelope("sensor_observation", {
          enemy_mech_id: "mech.blue.01",
          distance_estimate: 5,
          confidence: 0.9,
          heat_estimate: null,
          mode_estimate: null,
        }),
      ),
    ).toBeNull();
  });

  it("pairs a resolved terminal to the request named by causation_id", () => {
    const req = makeLlmRequest({ mechId: "mech.red.01", messageId: "req1" });
    const res = makeLlmResolved({
      mechId: "mech.red.01",
      model: "provider.glm.flash",
      causationId: "req1",
    });
    const { pairs, unresolved } = pairLlmEvidence([req, res]);
    expect(pairs).toHaveLength(1);
    expect(res.envelope.causation_id).toBe(req.envelope.message_id);
    expect(pairs[0]?.resolved).toBe(res);
    expect(unresolved.size).toBe(0);
  });

  it("pairs a failed terminal to the request named by causation_id", () => {
    const req = makeLlmRequest({ mechId: "mech.red.01", messageId: "req1" });
    const failed = makeLlmFailed({ mechId: "mech.red.01", causationId: "req1" });
    const { pairs, unresolved } = pairLlmEvidence([req, failed]);
    expect(pairs).toHaveLength(1);
    expect(failed.envelope.causation_id).toBe(req.envelope.message_id);
    expect(pairs[0]?.resolved?.event_type).toBe("llm_completion_failed");
    expect(unresolved.size).toBe(0);
  });

  it("pairs interleaved terminals by causation rather than mech or arrival", () => {
    const first = makeLlmRequest({ mechId: "mech.red.01", messageId: "req1" });
    const second = makeLlmRequest({ mechId: "mech.red.01", messageId: "req2" });
    const secondTerminal = makeLlmResolved({ mechId: "mech.red.01", causationId: "req2" });
    const firstTerminal = makeLlmFailed({ mechId: "mech.red.01", causationId: "req1" });
    const { pairs, unresolved } = pairLlmEvidence([first, second, secondTerminal, firstTerminal]);
    expect(pairs).toHaveLength(2);
    expect(pairs[0]?.resolved).toBe(firstTerminal);
    expect(pairs[1]?.resolved).toBe(secondTerminal);
    expect(unresolved.size).toBe(0);
  });

  it("surfaces an orphan terminal as a lone terminal row", () => {
    const orphan = makeLlmResolved({ causationId: "missing-request" });
    const { pairs, unresolved } = pairLlmEvidence([orphan]);
    expect(pairs).toEqual([{ requested: orphan, resolved: orphan }]);
    expect(unresolved.size).toBe(0);
  });

  it("keeps the first terminal when duplicate terminal evidence arrives", () => {
    const req = makeLlmRequest({ messageId: "req1" });
    const first = makeLlmResolved({ causationId: "req1" });
    const duplicate = makeLlmFailed({ causationId: "req1" });
    const { pairs, unresolved } = pairLlmEvidence([req, first, duplicate]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0]?.resolved).toBe(first);
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

describe("card-cadence reasoning is a decision, not lifecycle noise", () => {
  it("groups plan_committed and register_resolved with the decisions filter", () => {
    expect(groupOf(makePlan())).toBe("decisions");
    expect(
      groupOf(
        makeEnvelope("register_resolved", {
          seat: "a",
          register_index: 0,
          card_id: "card.movement.advance",
          action: "move",
          outcome: "resolved",
          priority: 10,
          priority_rank: 0,
          fill_reason: null,
        }),
      ),
    ).toBe("decisions");
  });

  it("moves weapon_fire_rejected out of the lifecycle fallback and into combat", () => {
    // This is a BEHAVIOUR CHANGE, not a no-op: `weapon_fire_rejected` had no
    // GROUP_BY_EVENT entry, so `groupOf` returned its `lifecycle` fallback. A
    // refused shot is a combat outcome and belongs on the combat chip, where a
    // "why did nothing fire?" question is actually answerable.
    const rejected = makeEnvelope("weapon_fire_rejected", {
      weapon_id: "module.weapon.machine_gun",
      target_id: "mech.b.01",
      reason: "weapon_on_cooldown",
    });
    expect(groupOf(rejected)).toBe("combat");
    expect(summarizeEnvelope(rejected)).toBe("REJECTED machine_gun · weapon on cooldown");
  });

  it("exposes rationale + confidence identically for both decision cadences", () => {
    const plan = makePlan({ rationale: "Hold the ridge and let them close.", confidence: 0.6 });
    const tactical = makeDecision({ rationale: "Punish the overcommit.", confidence: 0.9 });
    expect(isReasoningEvent(plan)).toBe(true);
    expect(isReasoningEvent(tactical)).toBe(true);
    expect(rationaleOf(plan)).toBe("Hold the ridge and let them close.");
    expect(rationaleOf(tactical)).toBe("Punish the overcommit.");
    expect(confidenceOf(plan)).toBe(0.6);
    expect(confidenceOf(tactical)).toBe(0.9);
  });

  it("reports no reasoning for a non-decision envelope", () => {
    const tick = makeEnvelope("match_tick", {});
    expect(isReasoningEvent(tick)).toBe(false);
    expect(rationaleOf(tick)).toBeNull();
    expect(confidenceOf(tick)).toBeNull();
  });

  it("summarizes a plan as its ordered register sequence", () => {
    const plan = makePlan({
      cardIds: ["card.movement.advance", "card.attack.fire_primary"],
    });
    expect(summarizeEnvelope(plan)).toBe("2R · advance › fire primary");
  });

  it("orders registers by register_index, never by arrival order", () => {
    const scrambled = makeEnvelope("plan_committed", {
      seat: "a",
      registers: [
        { register_index: 1, card_id: "card.attack.fire_primary" },
        { register_index: 0, card_id: "card.movement.advance" },
      ],
      rationale: null,
      confidence: 0.5,
      plan_source: "llm",
      spatial_read: null,
    });
    expect(planSequence(scrambled.payload.registers)).toBe("advance › fire primary");
    expect(orderedRegisters(scrambled.payload.registers).map((r) => r.register_index)).toEqual([
      0, 1,
    ]);
  });
});

describe("intent summaries carry their tactical content", () => {
  it("keeps move direction and speed instead of collapsing to the event name", () => {
    expect(
      summarizeEnvelope(makeEnvelope("move_intent", { direction: "flank_right", speed: "full" })),
    ).toBe("move flank right · full");
    expect(
      summarizeEnvelope(makeEnvelope("move_intent", { direction: "toward_cover", speed: null })),
    ).toBe("move toward cover");
  });

  it("names the weapon and the target of a fire intent", () => {
    expect(
      summarizeEnvelope(
        makeEnvelope("weapon_fire_intent", {
          weapon_id: "module.weapon.steam_cannon",
          target_mech_id: "mech.blue.01",
        }),
      ),
    ).toBe("fire steam_cannon → 01");
  });
});

describe("side attribution", () => {
  it("assigns RED/BLUE only from explicit canonical metadata", () => {
    const sides = buildSideMap([
      { mech_id: "mech.blue.01", player_id: "player.a", side: "blue" },
      { mech_id: "mech.red.01", player_id: "player.z", side: "red" },
    ]);
    expect(sides.byMech.get("mech.red.01")).toBe("red");
    expect(sides.byMech.get("mech.blue.01")).toBe("blue");
  });

  it("maps a row to its subject's side, neutral for the match subject", () => {
    const sides = buildSideMap([{ mech_id: "mech.red.01", player_id: "player.a", side: "red" }]);
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
    expect(
      isDangerEvent(makeEnvelope("mech_destroyed", { cause: "boiler", source_mech_id: null })),
    ).toBe(true);
    expect(isDangerEvent(makeDecision())).toBe(false);
    expect(glyphOf(makeLlmRequest())).toBe("❯");
    expect(glyphOf(makeDecision())).toBe("◇");
  });
});
