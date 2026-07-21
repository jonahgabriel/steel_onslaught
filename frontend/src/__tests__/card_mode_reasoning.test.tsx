// @vitest-environment jsdom
/**
 * Demo-path visibility, end to end — card-cadence reasoning AND seat identity.
 *
 * The demo runs the CARD cadence, and in that cadence the runner never invokes
 * `ReducerPilotTick` (`match/runner.py`), which is the only emitter of
 * `pilot_decision_made`. So a deck that surfaces reasoning only for
 * `pilot_decision_made` surfaces NONE of it in the demo: the river showed rows
 * labelled "plan committed … event" with no rationale, and the spec rail's
 * DECISIONS tally sat at 0 for the whole match while the LLM's tactical
 * reasoning sat unread on `plan_committed.rationale`.
 *
 * The second half of the same visibility gap is WHO is flying each seat:
 * `match_started.launch_provenance.seat_assignments` is the launch record's own
 * answer, and it reaches the screen only through the deck's `match_started`
 * branch. Every seat assertion elsewhere hand-builds `GaugeState`s and calls
 * `initGauges` directly, which walks straight past both the closed parser and
 * that wiring — so this file drives the real fixture through `parseEnvelope`
 * into the REAL PressureDeck and asserts the two seats read differently on
 * screen. Delete the deck's seat wiring and these tests go red; that is the
 * point of them.
 */
import "./setup-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EnvelopeHandler } from "../lib/event_stream";
import { MatchTransport } from "../lib/transport";
import { parseEnvelope, type SOEventEnvelope } from "../types";
import PressureDeck from "../views/PressureDeck";

const FIXTURES_DIR = join(process.cwd(), "src/__tests__/fixtures");

function fixtureJson(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(FIXTURES_DIR, `${name}.json`), "utf-8"));
}

function fixture(name: string): SOEventEnvelope {
  return parseEnvelope(fixtureJson(name));
}

/**
 * The recorded plan, re-subjected onto a mech the match_started declares.
 * Identity stays distinct per seat (event_id + UUID message_id), because the
 * river keys rows by it.
 */
function planFor(mechId: string, playerId: string, seat: string): SOEventEnvelope {
  const plan = fixture("plan_committed");
  if (plan.event_type !== "plan_committed") throw new Error("fixture is not plan_committed");
  const suffix = seat.toUpperCase();
  return {
    ...plan,
    event_id: `${plan.event_id.slice(0, -1)}${suffix}`,
    subject: { mech_id: mechId, player_id: playerId },
    payload: { ...plan.payload, seat },
    envelope: {
      ...plan.envelope,
      message_id: `569d9ec4-2007-5f75-bc7b-da1f1f917cf${seat === "a" ? "4" : "5"}`,
    },
  };
}

/** One resolving register of the recorded plan, re-subjected onto a mech. */
function registerFor(
  mechId: string,
  playerId: string,
  seat: string,
  registerIndex: number,
): SOEventEnvelope {
  const resolved = fixture("register_resolved");
  if (resolved.event_type !== "register_resolved")
    throw new Error("fixture is not register_resolved");
  const tag = `${seat.toUpperCase()}${registerIndex}`;
  return {
    ...resolved,
    event_id: `${resolved.event_id.slice(0, -2)}${tag}`,
    subject: { mech_id: mechId, player_id: playerId },
    payload: { ...resolved.payload, seat, register_index: registerIndex },
    envelope: {
      ...resolved.envelope,
      message_id: `dc7746a8-cafa-594c-81a8-7f5e40672${seat === "a" ? "1" : "2"}${registerIndex}d`,
    },
  };
}

beforeEach(() => {
  // PressureDeck batches envelopes per animation frame; jsdom has no rAF.
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) =>
    setTimeout(() => cb(Date.now()), 0),
  );
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

async function renderCardMatch(stream: readonly SOEventEnvelope[]): Promise<void> {
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
  await act(async () => {
    for (const env of stream) {
      for (const handler of [...handlers]) handler(env);
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  });
}

describe("card-cadence match — the Event River you can watch think", () => {
  it("renders the committed plan's rationale, registers and confidence in the river", async () => {
    await renderCardMatch([fixture("match_started"), planFor("mech.a.01", "player.a", "a")]);

    const rationale = screen.getByTestId("decision-rationale");
    expect(rationale.textContent).toContain("Advance, fire, then vent.");
    expect(screen.getByTestId("plan-registers").textContent).toContain("R0 advance");
    expect(
      screen.getByTestId("decision-confidence").querySelectorAll('i[data-on="true"]'),
    ).toHaveLength(
      4, // round(0.8 * 5)
    );
  });

  it("counts each committed plan in its own mech's DECISIONS gauge", async () => {
    await renderCardMatch([
      fixture("match_started"),
      planFor("mech.a.01", "player.a", "a"),
      planFor("mech.b.01", "player.b", "b"),
    ]);

    const red = screen.getByTestId("spec-mech.a.01");
    expect(within(red).getByTestId("spec-decisions-mech.a.01").textContent).toContain("1");
    const blue = screen.getByTestId("spec-mech.b.01");
    expect(within(blue).getByTestId("spec-decisions-mech.b.01").textContent).toContain("1");
  });

  it("keeps the plan in the order lane so the filter chip cannot hide it", async () => {
    await renderCardMatch([fixture("match_started"), planFor("mech.a.01", "player.a", "a")]);
    // A plan row filed under LIFECYCLE would vanish the moment the filter is
    // used — the chip counting it is the proof it is in the right lane.
    expect(screen.getByTestId("filter-decisions").textContent).toContain("1");
  });

  it("labels the order-lane chip ORDERS, not DECISIONS — the two count different things", async () => {
    // A realistic card round: one committed plan, then its three registers
    // resolving. The spec rail counts ONE decision; the order lane holds FOUR
    // rows. Those numbers must not both be presented as "DECISIONS".
    await renderCardMatch([
      fixture("match_started"),
      planFor("mech.a.01", "player.a", "a"),
      registerFor("mech.a.01", "player.a", "a", 0),
      registerFor("mech.a.01", "player.a", "a", 1),
      registerFor("mech.a.01", "player.a", "a", 2),
    ]);

    const spec = within(screen.getByTestId("spec-mech.a.01")).getByTestId(
      "spec-decisions-mech.a.01",
    );
    expect(spec.textContent).toContain("DECISIONS");
    expect(spec.textContent).toContain("1");

    const chip = screen.getByTestId("filter-decisions");
    expect(chip.textContent).toContain("ORDERS");
    expect(chip.textContent).not.toContain("DECISIONS");
    expect(chip.textContent).toContain("4");
  });
});

describe("card-cadence match — who is flying each seat", () => {
  it("projects the launch record's seat assignments onto the spec rail, distinctly per seat", async () => {
    // Nothing but MATCH_STARTED: the seat identity is launch evidence, so it
    // must be on screen before a single tick is played. This drives the real
    // closed parser and the deck's own `match_started` branch — remove that
    // branch's `launch_provenance` argument and these queries find nothing.
    await renderCardMatch([fixture("match_started")]);

    const red = screen.getByTestId("spec-seat-mech.a.01");
    const blue = screen.getByTestId("spec-seat-mech.b.01");
    expect(red).toHaveAttribute("data-seat-kind", "MODEL");
    expect(blue).toHaveAttribute("data-seat-kind", "MODEL");
    expect(red.textContent).toContain("aggressor");
    expect(red.textContent).toContain("model_identity.fixture_red");
    expect(red.textContent).toContain("loadout.fixture.alpha");
    expect(blue.textContent).toContain("sentinel");
    expect(blue.textContent).toContain("model_identity.fixture_blue");
    expect(blue.textContent).toContain("loadout.fixture.bravo");
    // The entire point of the readout: the two seats must not read the same.
    expect(blue.textContent).not.toBe(red.textContent);
  });

  it("renders no seat line when MATCH_STARTED carries no launch record", async () => {
    const raw = fixtureJson("match_started");
    const payload = raw["payload"] as Record<string, unknown>;
    delete payload["launch_provenance"];
    await renderCardMatch([parseEnvelope(raw)]);

    // The rail still renders — only the launch-evidence line is absent, which
    // is what a legacy/historical replay looks like.
    expect(screen.getByTestId("spec-mech.a.01")).toBeInTheDocument();
    expect(screen.queryByTestId("spec-seat-mech.a.01")).not.toBeInTheDocument();
    expect(screen.queryByTestId("spec-seat-mech.b.01")).not.toBeInTheDocument();
  });
});
