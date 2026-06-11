/**
 * DecisionInspector — Task 33.
 *
 * Displays pilot decision data for a given match tick.  Composed of:
 * - A `TickStepper` at the top for navigation.
 * - One card per `PILOT_DECISION_MADE` envelope, showing:
 *   - mech_id and player_id from the envelope subject
 *   - chosen action, reason_code, confidence
 *   - `considered_actions` table (action / score)
 *
 * Invariants:
 * - Pure projection — never mutates server state (read-only, no POST/PUT).
 * - Empty `decisions` array → shows "No decisions this tick."
 * - `onTickChange` is forwarded from the internal TickStepper.
 */

import React from "react";
import type { SOEventEnvelope, ConsideredAction } from "../types";
import { TickStepper } from "./TickStepper";

/** A PILOT_DECISION_MADE envelope narrowed to its specific event_type. */
type DecisionEnvelope = Extract<SOEventEnvelope, { event_type: "pilot_decision_made" }>;

export interface DecisionInspectorProps {
  /** The match being inspected (for display / future REST fetch). */
  matchId: string;
  /** Tick currently displayed — drives the TickStepper. */
  currentTick: number;
  /** Upper bound for the TickStepper (last tick in the ledger). */
  finalTick: number;
  /**
   * PILOT_DECISION_MADE envelopes for the current tick.
   * Pass `[]` when the tick has no pilot decisions.
   */
  decisions: DecisionEnvelope[];
  /** Called when the user navigates to a different tick. */
  onTickChange: (tick: number) => void;
}

function ConsideredActionsTable({
  items,
}: {
  items: ConsideredAction[];
}): React.ReactElement {
  return (
    <table
      style={{ borderCollapse: "collapse", fontSize: "0.85em", marginTop: "0.25rem" }}
    >
      <thead>
        <tr>
          <th style={{ textAlign: "left", paddingRight: "1rem" }}>action</th>
          <th style={{ textAlign: "right" }}>score</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, idx) => (
          <tr key={idx}>
            <td style={{ paddingRight: "1rem", fontFamily: "monospace" }}>{item.action}</td>
            <td style={{ textAlign: "right", fontFamily: "monospace" }}>
              {item.score.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DecisionCard({
  envelope,
}: {
  envelope: DecisionEnvelope;
}): React.ReactElement {
  const { payload, subject } = envelope;

  return (
    <div
      data-testid={`decision-card-${subject.mech_id}`}
      style={{
        border: "1px solid #555",
        borderRadius: "4px",
        padding: "0.75rem",
        marginBottom: "0.5rem",
        background: "#1e1e1e",
        color: "#ddd",
      }}
    >
      <div style={{ fontWeight: "bold", marginBottom: "0.25rem" }}>
        <span data-testid="decision-mech-id">{subject.mech_id}</span>
        {" "}
        <span style={{ fontSize: "0.8em", color: "#aaa" }}>({subject.player_id})</span>
      </div>
      <div>
        <strong>action:</strong>{" "}
        <span data-testid="decision-action" style={{ fontFamily: "monospace" }}>
          {payload.action}
        </span>
      </div>
      <div>
        <strong>reason:</strong>{" "}
        <span style={{ fontFamily: "monospace" }}>{payload.reason_code}</span>
      </div>
      <div>
        <strong>confidence:</strong>{" "}
        <span data-testid="decision-confidence">{payload.confidence.toFixed(2)}</span>
      </div>
      {payload.considered_actions.length > 0 && (
        <div style={{ marginTop: "0.5rem" }}>
          <strong>considered:</strong>
          <ConsideredActionsTable items={payload.considered_actions} />
        </div>
      )}
    </div>
  );
}

export function DecisionInspector({
  matchId,
  currentTick,
  finalTick,
  decisions,
  onTickChange,
}: DecisionInspectorProps): React.ReactElement {
  return (
    <div
      data-testid="decision-inspector"
      style={{ padding: "0.75rem", fontFamily: "sans-serif", color: "#ddd" }}
    >
      <div style={{ marginBottom: "0.75rem" }}>
        <TickStepper
          currentTick={currentTick}
          finalTick={finalTick}
          onChange={onTickChange}
        />
      </div>
      <div style={{ fontSize: "0.8em", color: "#888", marginBottom: "0.5rem" }}>
        {matchId} — tick {currentTick}
      </div>
      {decisions.length === 0 ? (
        <div
          data-testid="no-decisions"
          style={{ fontStyle: "italic", color: "#888" }}
        >
          No decisions this tick.
        </div>
      ) : (
        <div>
          {decisions.map((env, idx) => (
            <DecisionCard key={`${env.subject.mech_id}-${idx}`} envelope={env} />
          ))}
        </div>
      )}
    </div>
  );
}
