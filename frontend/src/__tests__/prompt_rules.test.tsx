// @vitest-environment jsdom
/**
 * PromptRulesWorkbench + prompt_rules lib.
 *
 * Two blocks: the pure edit algebra (parse, split doctrine, derive overlay
 * fragment) and the rendered workbench (edit a doctrine, toggle a rule, see
 * the fragment update). The fixtures mirror the exact JSON the backend
 * `so prompts show --json` / `so rules list --json` commands emit.
 */
import "./setup-dom";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  computeOverlayFragment,
  type MatchPromptProvenance,
  PromptRulesParseError,
  parseMatchPromptProvenance,
  parseRuleCatalog,
  type RuleCatalog,
  splitDoctrine,
} from "../lib/prompt_rules";
import PromptRulesWorkbench from "../views/PromptRulesWorkbench";

afterEach(cleanup);

const INSTRUCTION =
  '\n\nRespond with ONLY a JSON object, no prose, of shape:\n{"action": "remain"}';

function provenanceDoc(): MatchPromptProvenance {
  return parseMatchPromptProvenance({
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
        prompt_sha256: "a".repeat(64),
        prompt_text: `You are a RECKLESS BERSERKER.${INSTRUCTION}`,
      },
      {
        schema_version: "0.1.0",
        kind: "steel_onslaught.effective_prompt",
        persona_id: "sniper",
        display_name: "Sniper",
        source: "operator_override",
        temperature: 0.3,
        prompt_sha256: "b".repeat(64),
        prompt_text: `You are a PATIENT SNIPER.${INSTRUCTION}`,
      },
    ],
    programming_instructions_sha256: "c".repeat(64),
    content_sha256: "d".repeat(64),
  });
}

function catalogDoc(): RuleCatalog {
  return parseRuleCatalog({
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
          implementation_sha256: "1".repeat(64),
        },
        display_name: "Fire-dense programming",
        description: "Trend a round toward shooting.",
      },
      {
        schema_version: "0.1.0",
        kind: "steel_onslaught.card_rule_descriptor",
        metadata: {
          schema_version: "0.1.0",
          kind: "steel_onslaught.card_rule_handler",
          handler_id: "ensure_movement_card",
          version: "v1.0.0",
          implementation_sha256: "2".repeat(64),
        },
        display_name: "Movement variety",
        description: "Guarantee one movement card per round.",
      },
    ],
    enabled_handler_ids: ["ensure_movement_card"],
  });
}

describe("prompt_rules parsing + edit algebra", () => {
  it("rejects an unknown-kind document", () => {
    expect(() => parseMatchPromptProvenance({ kind: "wrong" })).toThrow(PromptRulesParseError);
    expect(() => parseRuleCatalog({ kind: "wrong" })).toThrow(PromptRulesParseError);
  });

  it("rejects a catalog enabling an unavailable handler", () => {
    expect(() =>
      parseRuleCatalog({
        schema_version: "0.1.0",
        kind: "steel_onslaught.card_rule_catalog",
        pack_id: "rules.card_programming_v1",
        available: [],
        enabled_handler_ids: ["ghost"],
      }),
    ).toThrow(PromptRulesParseError);
  });

  it("splits the editable doctrine from the fixed output contract", () => {
    const { doctrine, instruction } = splitDoctrine(`Doctrine body.${INSTRUCTION}`);
    expect(doctrine).toBe("Doctrine body.");
    expect(instruction).toBe(INSTRUCTION);
  });

  it("emits an override only for a changed doctrine, in catalog order for rules", () => {
    const provenance = provenanceDoc();
    const catalog = catalogDoc();
    const fragment = computeOverlayFragment(provenance, catalog, {
      doctrines: new Map([
        ["berserker", "You are a RECKLESS BERSERKER."], // unchanged -> no override
        ["sniper", "Play even MORE cautiously than before."], // changed
      ]),
      enabledHandlerIds: new Set(["ensure_movement_card", "prefer_attack_cards"]),
    });
    expect(fragment.persona_overrides).toEqual([
      { persona_id: "sniper", doctrine: "Play even MORE cautiously than before." },
    ]);
    // Emitted in catalog order, not selection order.
    expect(fragment.balance_rule_pack).toEqual({
      kind: "card_programming_rules",
      pack_id: "rules.card_programming_v1",
      handler_ids: ["prefer_attack_cards", "ensure_movement_card"],
    });
  });

  it("emits a null rule pack when nothing is enabled", () => {
    const fragment = computeOverlayFragment(provenanceDoc(), catalogDoc(), {
      doctrines: new Map(),
      enabledHandlerIds: new Set(),
    });
    expect(fragment.balance_rule_pack).toBeNull();
    expect(fragment.persona_overrides).toEqual([]);
  });
});

describe("PromptRulesWorkbench rendering + interaction", () => {
  it("renders the effective doctrine and installed rules, and reacts to edits", () => {
    render(<PromptRulesWorkbench provenance={provenanceDoc()} catalog={catalogDoc()} />);

    // The editable field holds only the doctrine, never the JSON output block.
    const berserker = screen.getByLabelText("Doctrine for Berserker") as HTMLTextAreaElement;
    expect(berserker.value).toBe("You are a RECKLESS BERSERKER.");
    expect(berserker.value.includes("Respond with ONLY a JSON object")).toBe(false);

    // The overridden persona is badged EDITED from the source field.
    const sniperArticle = document.querySelector('[data-persona-id="sniper"]');
    expect(within(sniperArticle as HTMLElement).getByText("EDITED")).toBeTruthy();

    // Editing a doctrine produces a persona override in the fragment.
    fireEvent.change(berserker, { target: { value: "CHARGE and never stop." } });
    const fragment = screen.getByLabelText("Overlay fragment");
    expect(fragment.textContent).toContain('"persona_id": "berserker"');
    expect(fragment.textContent).toContain("CHARGE and never stop.");

    // Toggling a rule on adds it to the fragment in catalog order.
    fireEvent.click(screen.getByLabelText("Fire-dense programming"));
    expect(fragment.textContent).toContain("prefer_attack_cards");
    expect(fragment.textContent).toContain("ensure_movement_card");
  });
});
