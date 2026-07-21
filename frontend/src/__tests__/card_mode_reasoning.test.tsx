// @vitest-environment jsdom
/**
 * Card-cadence reasoning visibility — the demo path, end to end.
 *
 * The demo runs the CARD cadence, and in that cadence the runner never invokes
 * `ReducerPilotTick` (`match/runner.py`), which is the only emitter of
 * `pilot_decision_made`. So a deck that surfaces reasoning only for
 * `pilot_decision_made` surfaces NONE of it in the demo: the river showed rows
 * labelled "plan committed … event" with no rationale, and the spec rail's
 * DECISIONS tally sat at 0 for the whole match while the LLM's tactical
 * reasoning sat unread on `plan_committed.rationale`.
 *
 * This replays a card-cadence stream (fixture `match_started` + the recorded
 * `plan_committed` fixture, both through the real closed parser) into the REAL
 * PressureDeck and asserts the reasoning is on screen.
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

function fixture(name: string): SOEventEnvelope {
  return parseEnvelope(JSON.parse(readFileSync(join(FIXTURES_DIR, `${name}.json`), "utf-8")));
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

  it("counts the plan in the DECISIONS gauge and the DECISIONS filter chip", async () => {
    await renderCardMatch([
      fixture("match_started"),
      planFor("mech.a.01", "player.a", "a"),
      planFor("mech.b.01", "player.b", "b"),
    ]);

    const red = screen.getByTestId("spec-mech.a.01");
    expect(within(red).getByTestId("spec-decisions-mech.a.01").textContent).toContain("1");
    const blue = screen.getByTestId("spec-mech.b.01");
    expect(within(blue).getByTestId("spec-decisions-mech.b.01").textContent).toContain("1");

    // The bottom filter bar's DECISIONS chip must see them too — a plan row
    // filed under LIFECYCLE would vanish the moment the filter is used.
    const chip = screen.getByTestId("filter-decisions");
    expect(chip.textContent).toContain("2");
  });
});
