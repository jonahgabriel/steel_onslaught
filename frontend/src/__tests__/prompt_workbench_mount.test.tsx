// @vitest-environment jsdom
import "./setup-dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseFrontendBootstrap } from "../lib/application";
import MatchSetup from "../views/MatchSetup";

/**
 * Integration coverage for mounting the prompt/rule workbench on the PLAYER
 * SELECT screen (previously CLI-only). Proves three things:
 *   1. the workbench renders and is reachable before a match, and
 *   2. an operator prompt edit reaches the derived overlay fragment AND the
 *      setup screen's pending-edit surface — the same fragment `so prompts set`
 *      emits, which flows overlay -> composition -> MATCH_STARTED provenance, so
 *      the edit stays recorded in the ledger; and
 *   3. the launch flow still issues a start command with the workbench mounted.
 */

const BOOTSTRAP_FIXTURE = resolve(
  process.cwd(),
  "src/__tests__/fixtures/bootstrap/frontend_bootstrap.json",
);

const HEX = "a".repeat(64);
const DOCTRINE_TAIL =
  "\n\nRespond with ONLY a JSON object with keys registers, confidence, rationale.";

function bootstrapWithWorkbench() {
  const raw = JSON.parse(readFileSync(BOOTSTRAP_FIXTURE, "utf-8")) as Record<string, unknown>;
  raw["prompt_provenance"] = {
    schema_version: "0.1.0",
    kind: "steel_onslaught.match_prompt_provenance",
    prompts: [
      {
        schema_version: "0.1.0",
        kind: "steel_onslaught.effective_prompt",
        persona_id: "berserker",
        display_name: "Berserker",
        source: "contract",
        temperature: 0.7,
        prompt_sha256: HEX,
        prompt_text: `Charge recklessly and never retreat.${DOCTRINE_TAIL}`,
      },
      {
        schema_version: "0.1.0",
        kind: "steel_onslaught.effective_prompt",
        persona_id: "card_opportunist",
        display_name: "Card Opportunist",
        source: "contract",
        temperature: 0.2,
        prompt_sha256: HEX,
        prompt_text: `Counter-punch from range.${DOCTRINE_TAIL}`,
      },
    ],
    programming_instructions_sha256: HEX,
    content_sha256: HEX,
  };
  raw["rule_catalog"] = {
    schema_version: "0.1.0",
    kind: "steel_onslaught.card_rule_catalog",
    pack_id: "rules.card_programming_v1",
    available: [
      {
        schema_version: "0.1.0",
        kind: "steel_onslaught.card_rule_descriptor",
        metadata: {
          schema_version: "0.1.0",
          kind: "steel_onslaught.card_rule_handler",
          handler_id: "prefer_attack_cards",
          version: "v1.0.0",
          implementation_sha256: HEX,
        },
        display_name: "Fire-dense programming",
        description: "Bias registers toward attack cards.",
      },
    ],
    enabled_handler_ids: [],
  };
  return parseFrontendBootstrap(raw);
}

afterEach(cleanup);

describe("PromptRulesWorkbench mounted on the setup screen", () => {
  it("renders and is reachable before a match", () => {
    render(
      <MatchSetup bootstrap={bootstrapWithWorkbench()} capability={{ requestStart: vi.fn() }} />,
    );
    const section = screen.getByTestId("prompt-rules-workbench");
    expect(section).toBeTruthy();
    expect(section.textContent).toContain("PROMPT & RULE WORKBENCH");
    // The effective prompt for each persona is editable, before any match.
    expect(screen.getByLabelText("Doctrine for Berserker")).toBeTruthy();
    expect(screen.getByLabelText("Doctrine for Card Opportunist")).toBeTruthy();
  });

  it("carries an edited prompt into the derived overlay fragment and the pending-edit surface", () => {
    render(
      <MatchSetup bootstrap={bootstrapWithWorkbench()} capability={{ requestStart: vi.fn() }} />,
    );
    // No pending edits before the operator touches anything.
    expect(screen.queryByTestId("pending-prompt-edits")).toBeNull();

    const editor = screen.getByLabelText("Doctrine for Berserker") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: "Hold the center and bait a charge." } });

    // The edit reaches the setup screen's pending-edit surface (lifted from the
    // workbench via onFragmentChange).
    const pending = screen.getByTestId("pending-prompt-edits");
    expect(pending.textContent).toContain("berserker");

    // The edit reaches the derived overlay fragment — the exact artifact that
    // flows through composition into MATCH_STARTED provenance.
    const fragment = screen.getByLabelText("Overlay fragment");
    expect(within(fragment).getByText(/Hold the center and bait a charge\./)).toBeTruthy();
    expect(fragment.textContent).toContain("persona_overrides");
    expect(fragment.textContent).toContain("berserker");
  });

  it("still issues a start command with the workbench mounted", () => {
    const requestStart = vi.fn();
    render(<MatchSetup bootstrap={bootstrapWithWorkbench()} capability={{ requestStart }} />);
    fireEvent.submit(
      screen.getByRole("button", { name: "START MATCH" }).closest("form") as HTMLFormElement,
    );
    expect(requestStart).toHaveBeenCalledTimes(1);
    const call = requestStart.mock.calls[0];
    if (!call) throw new Error("requestStart was never called");
    const intent = call[0];
    expect(intent.selections).toEqual([
      { side: "red", option_id: "player_option.glm_model" },
      { side: "blue", option_id: "player_option.glm_model" },
    ]);
  });
});
