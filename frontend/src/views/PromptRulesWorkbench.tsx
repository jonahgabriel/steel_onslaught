/**
 * PromptRulesWorkbench — operator surface for the two code-free experiment
 * knobs: the mech's editable system prompt and the plug-in rule handlers.
 *
 * It renders the *effective* (post-override) doctrine each persona is flying
 * with plus every installable rule handler, lets a human edit the doctrine and
 * toggle rules, and derives the exact overlay fragment those edits produce.
 * The workbench never mutates a match directly: an edit only takes effect
 * through the overlay -> composition -> MATCH_STARTED provenance path, which is
 * what keeps an edited prompt in the evidence and replay-detectable. The
 * derived fragment is presented for the operator to save into an overlay
 * (equivalently, `so prompts set` / `so rules set` emit the same fragment).
 */
import { useMemo, useState } from "react";
import {
  computeOverlayFragment,
  type MatchPromptProvenance,
  type RuleCatalog,
  splitDoctrine,
} from "../lib/prompt_rules";

export interface PromptRulesWorkbenchProps {
  readonly provenance: MatchPromptProvenance;
  readonly catalog: RuleCatalog;
}

export default function PromptRulesWorkbench({
  provenance,
  catalog,
}: PromptRulesWorkbenchProps): React.JSX.Element {
  const baseDoctrines = useMemo(() => {
    const map = new Map<string, string>();
    for (const prompt of provenance.prompts) {
      map.set(prompt.persona_id, splitDoctrine(prompt.prompt_text).doctrine);
    }
    return map;
  }, [provenance]);

  const [doctrines, setDoctrines] = useState<Map<string, string>>(() => new Map(baseDoctrines));
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(catalog.enabled_handler_ids));

  const fragment = useMemo(
    () =>
      computeOverlayFragment(provenance, catalog, {
        doctrines,
        enabledHandlerIds: enabled,
      }),
    [provenance, catalog, doctrines, enabled],
  );

  return (
    <section className="prompt-rules-workbench" aria-label="Prompt and rule workbench">
      <h2>Editable mech prompts</h2>
      {provenance.prompts.length === 0 ? (
        <p>No personas are bound by this overlay.</p>
      ) : (
        provenance.prompts.map((prompt) => {
          const value = doctrines.get(prompt.persona_id) ?? "";
          const dirty = value.trim() !== (baseDoctrines.get(prompt.persona_id) ?? "").trim();
          return (
            <article
              key={prompt.persona_id}
              className="persona-editor"
              data-persona-id={prompt.persona_id}
              data-dirty={dirty ? "true" : "false"}
            >
              <header>
                <span className="persona-name">{prompt.display_name}</span>
                <span className="persona-source" data-source={prompt.source}>
                  {prompt.source === "operator_override" ? "EDITED" : "contract"}
                </span>
                <span className="persona-sha">{prompt.prompt_sha256.slice(0, 12)}</span>
              </header>
              <label>
                <span className="visually-hidden">Doctrine for {prompt.display_name}</span>
                <textarea
                  aria-label={`Doctrine for ${prompt.display_name}`}
                  value={value}
                  rows={6}
                  onChange={(event) => {
                    const next = new Map(doctrines);
                    next.set(prompt.persona_id, event.target.value);
                    setDoctrines(next);
                  }}
                />
              </label>
            </article>
          );
        })
      )}

      <h2>Plug-in rule handlers ({catalog.pack_id})</h2>
      <ul className="rule-list">
        {catalog.available.map((descriptor) => {
          const checked = enabled.has(descriptor.handler_id);
          return (
            <li key={descriptor.handler_id} data-handler-id={descriptor.handler_id}>
              <label>
                <input
                  type="checkbox"
                  checked={checked}
                  aria-label={descriptor.display_name}
                  onChange={() => {
                    const next = new Set(enabled);
                    if (next.has(descriptor.handler_id)) next.delete(descriptor.handler_id);
                    else next.add(descriptor.handler_id);
                    setEnabled(next);
                  }}
                />
                <span className="rule-name">{descriptor.display_name}</span>
              </label>
              <p className="rule-description">{descriptor.description}</p>
            </li>
          );
        })}
      </ul>

      <h2>Overlay fragment</h2>
      <p className="fragment-hint">
        Save this into an overlay's <code>llm</code> / <code>contracts</code> sections (or run
        <code> so prompts set</code> / <code>so rules set</code>) to run these edits. The effective
        prompt is recorded in MATCH_STARTED, so replay stays honest.
      </p>
      <figure className="overlay-fragment" aria-label="Overlay fragment">
        <pre>{JSON.stringify(fragment, null, 2)}</pre>
      </figure>
    </section>
  );
}
