/**
 * prompt_rules — closed parsers + edit algebra for the operator prompt/rule
 * workbench.
 *
 * The backend emits two typed projections that never require editing code to
 * change a match:
 *   - `so prompts show --json`  -> ModelSOMatchPromptProvenance
 *   - `so rules list --json`     -> ModelSOCardRuleCatalogProjection
 *
 * This module parses those documents with the same closed-key discipline the
 * bootstrap parser uses, and computes the overlay fragment a human edit
 * produces. It intentionally holds no React and no I/O so it is unit-testable
 * in isolation and reusable by any surface.
 *
 * The editable unit is the *doctrine*, not the whole system prompt: the runner
 * appends a fixed JSON output contract that an operator must never rewrite.
 * `splitDoctrine` mirrors the backend `_substitute_doctrine` separator so the
 * workbench edits exactly the human-owned prefix.
 */

const DOCTRINE_SEPARATOR = "\n\nRespond with ONLY a JSON object";

export interface EffectivePrompt {
  readonly persona_id: string;
  readonly display_name: string;
  readonly source: "contract" | "operator_override";
  readonly temperature: number;
  readonly prompt_sha256: string;
  readonly prompt_text: string;
}

export interface MatchPromptProvenance {
  readonly prompts: readonly EffectivePrompt[];
  readonly programming_instructions_sha256: string;
  readonly content_sha256: string;
}

export interface RuleDescriptor {
  readonly handler_id: string;
  readonly display_name: string;
  readonly description: string;
  readonly version: string;
}

export interface RuleCatalog {
  readonly pack_id: string;
  readonly available: readonly RuleDescriptor[];
  readonly enabled_handler_ids: readonly string[];
}

export interface PersonaOverride {
  readonly persona_id: string;
  readonly doctrine: string;
  readonly temperature?: number;
}

export interface OverlayFragment {
  readonly persona_overrides: readonly PersonaOverride[];
  readonly balance_rule_pack: {
    readonly kind: "card_programming_rules";
    readonly pack_id: string;
    readonly handler_ids: readonly string[];
  } | null;
}

export class PromptRulesParseError extends Error {}

function fail(context: string): never {
  throw new PromptRulesParseError(context);
}

function asRecord(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${context} must be an object`);
  }
  return value as Record<string, unknown>;
}

function str(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    fail(`${context}.${key} must be a non-empty string`);
  }
  return value;
}

function num(record: Record<string, unknown>, key: string, context: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(`${context}.${key} must be a finite number`);
  }
  return value;
}

function list(value: unknown, context: string): unknown[] {
  if (!Array.isArray(value)) fail(`${context} must be an array`);
  return value;
}

/** Split an effective system prompt into its editable doctrine + fixed tail. */
export function splitDoctrine(promptText: string): { doctrine: string; instruction: string } {
  const index = promptText.indexOf(DOCTRINE_SEPARATOR);
  if (index < 0) return { doctrine: promptText, instruction: "" };
  return {
    doctrine: promptText.slice(0, index),
    instruction: promptText.slice(index),
  };
}

export function parseMatchPromptProvenance(value: unknown): MatchPromptProvenance {
  const root = asRecord(value, "prompt_provenance");
  if (root["kind"] !== "steel_onslaught.match_prompt_provenance") {
    fail("prompt_provenance.kind mismatch");
  }
  const prompts = list(root["prompts"], "prompt_provenance.prompts").map(
    (entry, index): EffectivePrompt => {
      const context = `prompt_provenance.prompts[${index}]`;
      const record = asRecord(entry, context);
      const source = str(record, "source", context);
      if (source !== "contract" && source !== "operator_override") {
        fail(`${context}.source must be contract or operator_override`);
      }
      return {
        persona_id: str(record, "persona_id", context),
        display_name: str(record, "display_name", context),
        source,
        temperature: num(record, "temperature", context),
        prompt_sha256: str(record, "prompt_sha256", context),
        prompt_text: str(record, "prompt_text", context),
      };
    },
  );
  return {
    prompts,
    programming_instructions_sha256: str(
      root,
      "programming_instructions_sha256",
      "prompt_provenance",
    ),
    content_sha256: str(root, "content_sha256", "prompt_provenance"),
  };
}

export function parseRuleCatalog(value: unknown): RuleCatalog {
  const root = asRecord(value, "rule_catalog");
  if (root["kind"] !== "steel_onslaught.card_rule_catalog") {
    fail("rule_catalog.kind mismatch");
  }
  const available = list(root["available"], "rule_catalog.available").map((entry, index) => {
    const context = `rule_catalog.available[${index}]`;
    const record = asRecord(entry, context);
    const metadata = asRecord(record["metadata"], `${context}.metadata`);
    return {
      handler_id: str(metadata, "handler_id", `${context}.metadata`),
      version: str(metadata, "version", `${context}.metadata`),
      display_name: str(record, "display_name", context),
      description: str(record, "description", context),
    };
  });
  const availableIds = new Set(available.map((descriptor) => descriptor.handler_id));
  const enabled = list(root["enabled_handler_ids"], "rule_catalog.enabled_handler_ids").map(
    (entry, index) => {
      const context = `rule_catalog.enabled_handler_ids[${index}]`;
      if (typeof entry !== "string" || entry.length === 0) fail(`${context} must be a string`);
      if (!availableIds.has(entry)) fail(`${context} enables unavailable handler ${entry}`);
      return entry;
    },
  );
  if (new Set(enabled).size !== enabled.length) {
    fail("rule_catalog.enabled_handler_ids must be unique");
  }
  return { pack_id: str(root, "pack_id", "rule_catalog"), available, enabled_handler_ids: enabled };
}

/**
 * Compute the overlay fragment a set of edits produces.
 *
 * A persona override is emitted only when its doctrine differs from the
 * effective doctrine, so an unedited prompt never pollutes the overlay (and
 * never changes its digest). The rule selection is emitted in catalog order,
 * which is the order composition applies handlers, so a UI checkbox set maps
 * to a deterministic, order-significant `handler_ids`.
 */
export function computeOverlayFragment(
  provenance: MatchPromptProvenance,
  catalog: RuleCatalog,
  edits: {
    readonly doctrines: ReadonlyMap<string, string>;
    readonly temperatures?: ReadonlyMap<string, number>;
    readonly enabledHandlerIds: ReadonlySet<string>;
  },
): OverlayFragment {
  const overrides: PersonaOverride[] = [];
  for (const prompt of provenance.prompts) {
    const editedDoctrine = edits.doctrines.get(prompt.persona_id);
    const baseDoctrine = splitDoctrine(prompt.prompt_text).doctrine;
    const editedTemperature = edits.temperatures?.get(prompt.persona_id);
    const doctrineChanged =
      editedDoctrine !== undefined && editedDoctrine.trim() !== baseDoctrine.trim();
    const temperatureChanged =
      editedTemperature !== undefined && editedTemperature !== prompt.temperature;
    if (!doctrineChanged && !temperatureChanged) continue;
    const doctrine = doctrineChanged ? editedDoctrine.trim() : baseDoctrine.trim();
    overrides.push(
      temperatureChanged
        ? { persona_id: prompt.persona_id, doctrine, temperature: editedTemperature }
        : { persona_id: prompt.persona_id, doctrine },
    );
  }
  const handlerIds = catalog.available
    .map((descriptor) => descriptor.handler_id)
    .filter((handlerId) => edits.enabledHandlerIds.has(handlerId));
  return {
    persona_overrides: overrides,
    balance_rule_pack:
      handlerIds.length === 0
        ? null
        : {
            kind: "card_programming_rules",
            pack_id: catalog.pack_id,
            handler_ids: handlerIds,
          },
  };
}
