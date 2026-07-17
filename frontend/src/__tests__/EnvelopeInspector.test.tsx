// @vitest-environment jsdom
/**
 * EnvelopeInspector tests — PRESSURE DECK (spec §constraints-4).
 *
 * The inspector opens with the full envelope JSON, exposes a copy button and
 * a clickable ancestry chain, and closes on Esc.
 */
import "./setup-dom";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EnvelopeInspector from "../views/EnvelopeInspector";
import { makeEnvelope } from "./helpers";

afterEach(cleanup);

describe("EnvelopeInspector", () => {
  it("opens with the full envelope JSON, including event_id and event_type", () => {
    const env = makeEnvelope("weapon_fired", {
      weapon_id: "module.weapon.mg.02",
      target_id: "mech.blue.01",
      hit_probability: 0.65,
      pressure_cost: 4,
      heat_generated: 6,
    });
    render(<EnvelopeInspector env={env} ancestry={[env]} onClose={vi.fn()} onSelect={vi.fn()} />);
    const json = screen.getByTestId("inspector-json");
    expect(json.textContent).toContain(env.event_id);
    expect(json.textContent).toContain("weapon_fired");
    expect(json.textContent).toContain("module.weapon.mg.02");
    expect(screen.getByTestId("inspector-event-type").textContent).toBe("weapon_fired");
    expect(screen.getByTestId("inspector-copy")).toBeInTheDocument();
  });

  it("renders a clickable ancestry chain and selects an ancestor", () => {
    const parent = makeEnvelope(
      "pilot_decision_made",
      {
        action: "fire_weapon",
        action_params: {},
        reason_code: "target_in_range",
        confidence: 0.9,
        considered_actions: [],
        rationale: null,
      },
      { messageId: "p1" },
    );
    const child = makeEnvelope(
      "weapon_fired",
      {
        weapon_id: "w",
        target_id: "t",
        hit_probability: 0.5,
        pressure_cost: 1,
        heat_generated: 1,
      },
      { messageId: "c1", causationId: "p1" },
    );
    const onSelect = vi.fn();
    render(
      <EnvelopeInspector
        env={child}
        ancestry={[parent, child]}
        onClose={vi.fn()}
        onSelect={onSelect}
      />,
    );
    const ancestryList = screen.getByTestId("inspector-ancestry");
    expect(ancestryList).toBeInTheDocument();
    fireEvent.click(screen.getByTestId(`ancestry-${parent.event_id}`));
    expect(onSelect).toHaveBeenCalledWith(parent);
  });

  it("closes on Esc", () => {
    const env = makeEnvelope("match_tick", {});
    const onClose = vi.fn();
    render(<EnvelopeInspector env={env} ancestry={[env]} onClose={onClose} onSelect={vi.fn()} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
