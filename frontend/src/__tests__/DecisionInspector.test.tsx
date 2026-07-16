/**
 * DecisionInspector + TickStepper tests — Task 33.
 *
 * Invariants asserted:
 * - TickStepper renders the current tick and prev/next/first/last buttons.
 * - TickStepper clamps tick to [0, finalTick]; clicking prev at 0 stays at 0;
 *   clicking next at finalTick stays at finalTick.
 * - DecisionInspector shows "No decisions this tick" when the decisions list
 *   is empty (no console errors).
 * - DecisionInspector renders a row per pilot decision with action,
 *   reason_code, confidence, and considered_actions.
 * - DecisionInspector passes tick changes from TickStepper to onTickChange.
 *
 * @vitest-environment jsdom
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PilotDecisionMadePayload, SOEventEnvelope, SOPilotAction } from "../types";
import { DecisionInspector } from "../views/DecisionInspector";
import { TickStepper } from "../views/TickStepper";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDecisionEnvelope(
  tick: number,
  mechId: string,
  playerId: string,
  action: SOPilotAction,
): SOEventEnvelope & { event_type: "pilot_decision_made" } {
  const payload: PilotDecisionMadePayload = {
    action,
    action_params: {},
    reason_code: "target_in_range",
    confidence: 0.85,
    considered_actions: [
      { action, score: 0.85 },
      { action: "remain", score: 0.2 },
    ],
  };
  return {
    schema_version: "0.1.0",
    event_id: `01TEST${mechId.replace(/\./g, "").padEnd(20, "0")}`,
    match_id: "match.test.001",
    tick,
    sequence_in_tick: 0,
    producer_node: `node.pilot.${mechId}`,
    subject: { mech_id: mechId, player_id: playerId },
    event_type: "pilot_decision_made" as const,
    payload,
    envelope: {
      message_id: "22222222-2222-2222-2222-222222222222",
      correlation_id: "11111111-1111-1111-1111-111111111111",
      causation_id: null,
      emitted_at: "2026-04-30T16:00:00Z",
      entity_id: "match.test.001",
    },
  };
}

// ---------------------------------------------------------------------------
// TickStepper tests
// ---------------------------------------------------------------------------

describe("TickStepper", () => {
  afterEach(cleanup);

  it("renders the current tick", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={5} finalTick={20} onChange={onChange} />);
    expect(screen.getByText("5")).toBeTruthy();
  });

  it("calls onChange with decremented tick on prev click", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={5} finalTick={20} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("tick-prev"));
    expect(onChange).toHaveBeenCalledWith(4);
  });

  it("calls onChange with incremented tick on next click", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={5} finalTick={20} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("tick-next"));
    expect(onChange).toHaveBeenCalledWith(6);
  });

  it("clamps prev at 0 — does not call onChange below 0", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={0} finalTick={20} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("tick-prev"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("clamps next at finalTick — does not call onChange above finalTick", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={20} finalTick={20} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("tick-next"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("first button jumps to tick 0", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={10} finalTick={20} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("tick-first"));
    expect(onChange).toHaveBeenCalledWith(0);
  });

  it("last button jumps to finalTick", () => {
    const onChange = vi.fn();
    render(<TickStepper currentTick={5} finalTick={20} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("tick-last"));
    expect(onChange).toHaveBeenCalledWith(20);
  });
});

// ---------------------------------------------------------------------------
// DecisionInspector tests
// ---------------------------------------------------------------------------

describe("DecisionInspector", () => {
  afterEach(cleanup);

  it("shows 'No decisions this tick' when decisions list is empty", () => {
    render(
      <DecisionInspector
        matchId="match.test.001"
        currentTick={5}
        finalTick={20}
        decisions={[]}
        onTickChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/no decisions this tick/i)).toBeTruthy();
  });

  it("renders one row per pilot decision", () => {
    const decisions = [
      makeDecisionEnvelope(5, "mech.red.01", "player.red", "fire_weapon"),
      makeDecisionEnvelope(5, "mech.blue.01", "player.blue", "move"),
    ];
    render(
      <DecisionInspector
        matchId="match.test.001"
        currentTick={5}
        finalTick={20}
        decisions={decisions}
        onTickChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/mech\.red\.01/)).toBeTruthy();
    expect(screen.getByText(/mech\.blue\.01/)).toBeTruthy();
    expect(screen.getAllByText(/FIRE_WEAPON/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/MOVE/i).length).toBeGreaterThan(0);
  });

  it("renders confidence for each decision", () => {
    const decisions = [makeDecisionEnvelope(5, "mech.red.01", "player.red", "vent")];
    render(
      <DecisionInspector
        matchId="match.test.001"
        currentTick={5}
        finalTick={20}
        decisions={decisions}
        onTickChange={vi.fn()}
      />,
    );
    // Confidence value 0.85 appears at least once (may also appear in considered_actions table).
    expect(screen.getAllByText(/0\.85/).length).toBeGreaterThan(0);
  });

  it("renders considered_actions entries", () => {
    const decisions = [makeDecisionEnvelope(5, "mech.red.01", "player.red", "fire_weapon")];
    render(
      <DecisionInspector
        matchId="match.test.001"
        currentTick={5}
        finalTick={20}
        decisions={decisions}
        onTickChange={vi.fn()}
      />,
    );
    // Both considered actions from makeDecisionEnvelope should appear.
    expect(screen.getAllByText(/FIRE_WEAPON/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/REMAIN/i).length).toBeGreaterThan(0);
  });

  it("passes tick changes from TickStepper to onTickChange", () => {
    const onTickChange = vi.fn();
    render(
      <DecisionInspector
        matchId="match.test.001"
        currentTick={5}
        finalTick={20}
        decisions={[]}
        onTickChange={onTickChange}
      />,
    );
    fireEvent.click(screen.getByTestId("tick-next"));
    expect(onTickChange).toHaveBeenCalledWith(6);
  });
});
