// @vitest-environment jsdom
/**
 * EventRow tests — PRESSURE DECK (spec §constraints-4).
 *
 * Covers decision-row rationale + LLM_FALLBACK rendering, the confidence
 * meter, and the LLM evidence request/resolve strip.
 */
import "./setup-dom";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EventRow from "../views/EventRow";
import {
  makeDecision,
  makeEnvelope,
  makeLlmFailed,
  makeLlmRequest,
  makeLlmResolved,
} from "./helpers";

afterEach(cleanup);

function row(env: Parameters<typeof EventRow>[0]["env"], props = {}) {
  return render(
    <EventRow env={env} side="red" lane={0} parentLane={null} onSelect={vi.fn()} {...props} />,
  );
}

describe("EventRow — decisions", () => {
  it("renders a quoted rationale for an LLM pilot decision", () => {
    row(makeDecision({ rationale: "Enemy overcommitted to proximity; punish it." }));
    const rationale = screen.getByTestId("decision-rationale");
    expect(rationale).toBeInTheDocument();
    expect(rationale.textContent).toContain("Enemy overcommitted");
  });

  it("stays single-line (no rationale element) for a heuristic pilot", () => {
    row(makeDecision({ rationale: null }));
    expect(screen.queryByTestId("decision-rationale")).not.toBeInTheDocument();
  });

  it("renders a 5-segment confidence meter", () => {
    row(makeDecision({ confidence: 0.8 }));
    const meter = screen.getByTestId("decision-confidence");
    const segs = meter.querySelectorAll("i");
    expect(segs).toHaveLength(5);
    const on = meter.querySelectorAll('i[data-on="true"]');
    expect(on).toHaveLength(4); // round(0.8 * 5)
  });

  it("marks an LLM_FALLBACK decision with a fallback chip and danger border", () => {
    const env = makeEnvelope("pilot_decision_made", {
      action: "remain",
      action_params: { fallback_class: "aggressor" },
      reason_code: "llm_fallback",
      confidence: 0.1,
      considered_actions: [],
      rationale: null,
    });
    row(env);
    const chip = screen.getByTestId("fallback-chip");
    expect(chip.textContent).toContain("aggressor");
    expect(screen.getByTestId(`event-row-${env.event_id}`).getAttribute("data-fallback")).toBe(
      "true",
    );
  });

  it("fires onSelect when clicked", () => {
    const onSelect = vi.fn();
    const env = makeDecision();
    row(env, { onSelect });
    fireEvent.click(screen.getByTestId(`event-row-${env.event_id}`));
    expect(onSelect).toHaveBeenCalledWith(env);
  });
});

describe("EventRow — LLM evidence", () => {
  it("renders a request strip and marks it thinking while unresolved", () => {
    const env = makeLlmRequest({ persona: "aggressor" });
    row(env, { thinking: true });
    const rowEl = screen.getByTestId(`event-row-${env.event_id}`);
    expect(rowEl.getAttribute("data-group")).toBe("llm");
    expect(rowEl.getAttribute("data-thinking")).toBe("true");
    expect(rowEl.textContent).toContain("aggressor");
  });

  it("renders a resolved usage strip with token counts", () => {
    const env = makeLlmResolved({ promptTokens: 120, completionTokens: 48 });
    row(env);
    const usage = screen.getByTestId("llm-usage");
    expect(usage.textContent).toContain("120");
    expect(usage.textContent).toContain("48");
  });

  it("renders sanitized failure evidence with optional cost", () => {
    const env = makeLlmFailed({ costUsd: 0.0004 });
    row(env);
    const usage = screen.getByTestId("llm-usage");
    expect(usage.textContent).toContain("consumer_error");
    expect(usage.textContent).toContain("$0.0004");
  });
});
