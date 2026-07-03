/**
 * Causation graph tests — PRESSURE DECK (spec §constraints-4/5).
 *
 * Ancestry/lane math is a pure module, tested directly per the spec's demand
 * for a unit-tested `lib/causation.ts`.
 */
import { describe, expect, it } from "vitest";
import {
  ancestryOf,
  assignLanes,
  buildCausationIndex,
  descendantsOf,
  highlightChain,
  rootOf,
} from "../lib/causation";
import { makeEnvelope } from "./helpers";

// A chain: root(m1) → m2 → m3, plus a sibling branch m1 → m4, and an
// unrelated root m5.
function chain() {
  const m1 = makeEnvelope(
    "match_started",
    { seed: 1, max_ticks: 10, mechs: [] },
    {
      messageId: "m1",
      causationId: null,
    },
  );
  const m2 = makeEnvelope("match_tick", {}, { messageId: "m2", causationId: "m1", tick: 1 });
  const m3 = makeEnvelope("match_tick", {}, { messageId: "m3", causationId: "m2", tick: 2 });
  const m4 = makeEnvelope("match_tick", {}, { messageId: "m4", causationId: "m1", tick: 1 });
  const m5 = makeEnvelope("match_tick", {}, { messageId: "m5", causationId: null, tick: 3 });
  return { envs: [m1, m2, m3, m4, m5], index: buildCausationIndex([m1, m2, m3, m4, m5]) };
}

describe("buildCausationIndex", () => {
  it("records parents, children and presence", () => {
    const { index } = chain();
    expect(index.parent.get("m3")).toBe("m2");
    expect(index.parent.get("m1")).toBeNull();
    expect(index.children.get("m1")).toEqual(["m2", "m4"]);
    expect(index.present.has("m5")).toBe(true);
  });
});

describe("ancestryOf", () => {
  it("returns self plus every ancestor up to the root", () => {
    const { index } = chain();
    expect(ancestryOf("m3", index)).toEqual(new Set(["m3", "m2", "m1"]));
  });

  it("a root's ancestry is just itself", () => {
    const { index } = chain();
    expect(ancestryOf("m1", index)).toEqual(new Set(["m1"]));
  });

  it("does not walk past an unknown parent", () => {
    const orphan = makeEnvelope("match_tick", {}, { messageId: "x", causationId: "gone" });
    const index = buildCausationIndex([orphan]);
    expect(ancestryOf("x", index)).toEqual(new Set(["x", "gone"]));
    expect(ancestryOf("gone", index)).toEqual(new Set(["gone"]));
  });
});

describe("descendantsOf", () => {
  it("returns self plus every transitive child", () => {
    const { index } = chain();
    expect(descendantsOf("m1", index)).toEqual(new Set(["m1", "m2", "m3", "m4"]));
  });

  it("a leaf has only itself", () => {
    const { index } = chain();
    expect(descendantsOf("m3", index)).toEqual(new Set(["m3"]));
  });
});

describe("highlightChain", () => {
  it("is ancestors ∪ self ∪ descendants — the full lineage of a mid-chain node", () => {
    const { index } = chain();
    expect(highlightChain("m2", index)).toEqual(new Set(["m1", "m2", "m3"]));
  });

  it("excludes unrelated chains", () => {
    const { index } = chain();
    expect(highlightChain("m2", index).has("m5")).toBe(false);
  });
});

describe("rootOf / assignLanes", () => {
  it("every node in a chain resolves to the same present root", () => {
    const { index } = chain();
    expect(rootOf("m3", index)).toBe("m1");
    expect(rootOf("m4", index)).toBe("m1");
    expect(rootOf("m5", index)).toBe("m5");
  });

  it("assigns a shared lane to a whole chain and a distinct lane to another root", () => {
    const { envs, index } = chain();
    const ids = envs.map((e) => e.envelope.message_id);
    const lanes = assignLanes(ids, index);
    expect(lanes.get("m1")).toBe(lanes.get("m3"));
    expect(lanes.get("m1")).toBe(lanes.get("m4"));
    expect(lanes.get("m5")).not.toBe(lanes.get("m1"));
  });

  it("wraps lanes at laneCount", () => {
    const roots = Array.from({ length: 5 }, (_, i) =>
      makeEnvelope("match_tick", {}, { messageId: `r${i}`, causationId: null }),
    );
    const index = buildCausationIndex(roots);
    const lanes = assignLanes(
      roots.map((r) => r.envelope.message_id),
      index,
      2,
    );
    expect(new Set(lanes.values())).toEqual(new Set([0, 1]));
  });
});
