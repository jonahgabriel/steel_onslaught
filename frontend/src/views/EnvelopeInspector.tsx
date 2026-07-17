/**
 * EnvelopeInspector — PRESSURE DECK (generalized from DecisionInspector).
 *
 * A right-side drawer that shows one envelope's full JSON (softly
 * syntax-tinted), its causation ancestry as a clickable list, and a copy-JSON
 * button.  `Esc` closes.  Presentational: the resolved ancestry chain is
 * passed in (computed by the deck via `lib/causation.ts`).
 */
import type React from "react";
import { useEffect } from "react";
import { formatStamp } from "../lib/river";
import type { SOEventEnvelope } from "../types";

const TOKEN_RE =
  /("(?:[^"\\]|\\.)*"\s*:)|("(?:[^"\\]|\\.)*")|(\btrue\b|\bfalse\b|\bnull\b)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

/** Tint a pretty-printed JSON string: keys, strings, numbers, booleans. */
function tintJson(json: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (let m = TOKEN_RE.exec(json); m !== null; m = TOKEN_RE.exec(json)) {
    if (m.index > last) nodes.push(json.slice(last, m.index));
    if (m[1] !== undefined) {
      nodes.push(
        <span className="k" key={key++}>
          {m[1]}
        </span>,
      );
    } else if (m[2] !== undefined) {
      nodes.push(
        <span className="s" key={key++}>
          {m[2]}
        </span>,
      );
    } else if (m[3] !== undefined) {
      nodes.push(
        <span className="b" key={key++}>
          {m[3]}
        </span>,
      );
    } else if (m[4] !== undefined) {
      nodes.push(
        <span className="n" key={key++}>
          {m[4]}
        </span>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < json.length) nodes.push(json.slice(last));
  return nodes;
}

export interface EnvelopeInspectorProps {
  env: SOEventEnvelope;
  /** Resolved ancestor chain, root → … → self (self last). */
  ancestry: readonly SOEventEnvelope[];
  onClose: () => void;
  onSelect: (env: SOEventEnvelope) => void;
}

export default function EnvelopeInspector({
  env,
  ancestry,
  onClose,
  onSelect,
}: EnvelopeInspectorProps): React.JSX.Element {
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const json = JSON.stringify(env, null, 2);

  function copy(): void {
    try {
      void navigator.clipboard?.writeText(json);
    } catch {
      /* clipboard unavailable (e.g. jsdom) — non-fatal */
    }
  }

  return (
    <aside
      className="pd-inspector pd-panel"
      data-testid="envelope-inspector"
      aria-label="Envelope inspector"
    >
      <div className="pd-inspector-head">
        <span data-testid="inspector-event-type">{env.event_type}</span>
        <button type="button" className="pd-iclose" onClick={onClose} aria-label="Close inspector">
          ✕ ESC
        </button>
      </div>
      <div className="pd-inspector-body">
        <button type="button" className="pd-copy" onClick={copy} data-testid="inspector-copy">
          COPY JSON
        </button>
        {ancestry.length > 1 ? (
          <ul className="pd-ancestry" data-testid="inspector-ancestry">
            {ancestry.map((a) => (
              <li key={a.event_id}>
                <button
                  type="button"
                  onClick={() => onSelect(a)}
                  data-testid={`ancestry-${a.event_id}`}
                  disabled={a.event_id === env.event_id}
                >
                  {formatStamp(a)} {a.event_type}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <pre className="pd-json" data-testid="inspector-json">
          {tintJson(json)}
        </pre>
      </div>
    </aside>
  );
}
