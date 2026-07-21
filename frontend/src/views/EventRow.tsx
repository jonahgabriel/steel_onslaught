/**
 * EventRow — PRESSURE DECK.
 *
 * One punch-card river row.  Four shapes, discriminated purely on data:
 *  - LLM evidence (event_type)   → a bracketed request/terminal strip.
 *  - pilot_decision_made         → an expanded decision row (rationale,
 *                                   confidence meter, reason chip, fallback).
 *  - plan_committed              → the same expanded decision row for the card
 *                                   cadence, with the programmed register
 *                                   sequence in place of the single action.
 *                                   This is the ONLY reasoning carrier in the
 *                                   card/paced mode the demo runs.
 *  - everything else             → a single-line telemetry row.
 *
 * Presentational: all state (side, lane, dim, focus, thinking) arrives as
 * props so the row is trivially unit-testable.
 */
import type React from "react";
import {
  cardLabel,
  confidenceSegments,
  fallbackClassOf,
  formatStamp,
  glyphOf,
  groupOf,
  isDangerEvent,
  orderedRegisters,
  rationaleOf,
  type Side,
  summarizeEnvelope,
} from "../lib/river";
import type { SOEventEnvelope } from "../types";

const SIDE_COLOR: Record<Side, string> = {
  red: "var(--ember)",
  blue: "var(--arc)",
  neutral: "var(--ash)",
};

// Rev 2: causation gutter narrowed to ~32px for the right-column river.
const GUTTER_W = 32;
const ROW_H = 34;
const LANE_STEP = 5;
const LANE_X0 = 5;

function laneX(lane: number): number {
  return LANE_X0 + lane * LANE_STEP;
}

export interface EventRowProps {
  env: SOEventEnvelope;
  side: Side;
  lane: number;
  parentLane: number | null;
  focused?: boolean;
  dimmed?: boolean;
  thinking?: boolean;
  onSelect: (env: SOEventEnvelope) => void;
  onHover?: (env: SOEventEnvelope | null) => void;
}

function CausationCell({
  side,
  lane,
  parentLane,
}: {
  side: Side;
  lane: number;
  parentLane: number | null;
}): React.JSX.Element {
  const x = laneX(lane);
  const color = SIDE_COLOR[side];
  return (
    <svg className="pd-gutter" width={GUTTER_W} height={ROW_H} aria-hidden="true">
      <line x1={x} y1={0} x2={x} y2={ROW_H} stroke="var(--seam)" strokeWidth={1} />
      {parentLane !== null && parentLane !== lane ? (
        <line
          className="pd-thread"
          x1={laneX(parentLane)}
          y1={0}
          x2={x}
          y2={ROW_H / 2}
          stroke={color}
          strokeWidth={1.4}
          fill="none"
        />
      ) : null}
      <circle cx={x} cy={ROW_H / 2} r={3} fill={color} />
    </svg>
  );
}

function LlmContent({ env }: { env: SOEventEnvelope }): React.JSX.Element | null {
  if (env.event_type === "llm_completion_requested") {
    return (
      <>
        <span className="pd-type">LLM ▸ REQUEST</span>
        <span className="pd-summary">persona {env.payload.persona_id} · thinking…</span>
      </>
    );
  }
  if (env.event_type === "llm_completion_failed") {
    return (
      <>
        <span className="pd-type">LLM ▸ FAILED</span>
        <span className="pd-usage" data-testid="llm-usage">
          {env.payload.model ?? "unknown"} · {env.payload.reason_code}
          {env.payload.cost_usd !== null ? (
            <>
              {" "}
              · <b>${env.payload.cost_usd.toFixed(4)}</b>
            </>
          ) : (
            <> · cost unknown</>
          )}
        </span>
      </>
    );
  }
  if (env.event_type !== "llm_completion_resolved") return null;
  return (
    <>
      <span className="pd-type">LLM ▸ RESOLVED</span>
      <span className="pd-usage" data-testid="llm-usage">
        {env.payload.model} · <b>{env.payload.prompt_tokens}</b>→
        <b>{env.payload.completion_tokens}</b> tok
        {env.payload.cost_usd !== null ? (
          <>
            {" "}
            · <b>${env.payload.cost_usd.toFixed(4)}</b>
          </>
        ) : (
          <> · cost unknown</>
        )}
      </span>
    </>
  );
}

/** The 5-segment confidence meter — identical in both decision cadences. */
function ConfidenceMeter({ confidence }: { confidence: number }): React.JSX.Element {
  return (
    <span
      className="pd-conf"
      data-testid="decision-confidence"
      role="img"
      aria-label={`confidence ${confidence.toFixed(2)}`}
    >
      {confidenceSegments(confidence).map((on, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed 5-segment meter, never reorders
        <i key={i} data-on={on} />
      ))}
    </span>
  );
}

function DecisionContent({
  env,
}: {
  env: SOEventEnvelope & { event_type: "pilot_decision_made" };
}): React.JSX.Element {
  const { payload } = env;
  const weapon = payload.action_params["weapon_id"];
  const weaponLabel = typeof weapon === "string" ? ` (${weapon.split(".").pop()})` : "";
  const fallback = fallbackClassOf(env);
  return (
    <>
      <span className="pd-type">DECISION</span>
      <span className="pd-summary">
        {payload.action.toUpperCase()}
        {weaponLabel}
      </span>
      <ConfidenceMeter confidence={payload.confidence} />
      <span className="pd-chip">{payload.reason_code}</span>
      {fallback !== null ? (
        <span className="pd-chip" data-fallback="true" data-testid="fallback-chip">
          FALLBACK: {fallback}
        </span>
      ) : null}
    </>
  );
}

/**
 * The card-cadence decision row. The committed registers ARE the tactical
 * choice — rendered in execution order as `R0 advance › R1 fire primary` so the
 * per-round variety the stream already carries is legible instead of collapsed
 * into a bare "plan committed" label.
 */
function PlanContent({
  env,
}: {
  env: SOEventEnvelope & { event_type: "plan_committed" };
}): React.JSX.Element {
  const { payload } = env;
  const registers = orderedRegisters(payload.registers);
  return (
    <>
      <span className="pd-type">PLAN</span>
      <span className="pd-summary" data-testid="plan-registers">
        {registers.map((register, i) => (
          <span className="pd-register" key={register.register_index}>
            {i === 0 ? "" : " › "}
            <b>R{register.register_index}</b> {cardLabel(register.card_id)}
          </span>
        ))}
      </span>
      <ConfidenceMeter confidence={payload.confidence} />
      <span className="pd-chip">SEAT {payload.seat.toUpperCase()}</span>
    </>
  );
}

export default function EventRow({
  env,
  side,
  lane,
  parentLane,
  focused = false,
  dimmed = false,
  thinking = false,
  onSelect,
  onHover,
}: EventRowProps): React.JSX.Element {
  const group = groupOf(env);
  const isDecision = env.event_type === "pilot_decision_made";
  const isPlan = env.event_type === "plan_committed";
  const rationale = rationaleOf(env);
  const fallback = isDecision ? fallbackClassOf(env) : null;

  return (
    // biome-ignore lint/a11y/useSemanticElements: rich clickable row wraps block-level content a native <button> cannot legally contain
    <div
      className="pd-row"
      data-testid={`event-row-${env.event_id}`}
      data-event-id={env.event_id}
      data-group={group}
      data-side={side}
      data-danger={isDangerEvent(env)}
      data-fallback={fallback !== null}
      data-focused={focused}
      data-dim={dimmed}
      data-thinking={thinking}
      role="button"
      tabIndex={-1}
      onClick={() => onSelect(env)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(env);
        }
      }}
      onMouseEnter={() => onHover?.(env)}
      onMouseLeave={() => onHover?.(null)}
    >
      <CausationCell side={side} lane={lane} parentLane={parentLane} />
      <div className="pd-rowmain">
        <span className="pd-stamp">{formatStamp(env)}</span>
        <span className="pd-glyph">{glyphOf(env)}</span>
        {group === "llm" ? (
          <LlmContent env={env} />
        ) : isDecision ? (
          <DecisionContent env={env} />
        ) : isPlan ? (
          <PlanContent env={env} />
        ) : (
          <>
            <span className="pd-type">{env.event_type.replace(/_/g, " ")}</span>
            <span className="pd-summary">{summarizeEnvelope(env)}</span>
          </>
        )}
        <span className="pd-side" data-side={side}>
          {side === "neutral" ? "SYS" : side.toUpperCase()}
        </span>
      </div>
      {rationale !== null ? (
        <div className="pd-rationale" data-testid="decision-rationale">
          “{rationale}”
        </div>
      ) : null}
    </div>
  );
}
