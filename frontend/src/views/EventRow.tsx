/**
 * EventRow — PRESSURE DECK.
 *
 * One punch-card river row.  Three shapes, discriminated purely on data:
 *  - LLM evidence (event_type)   → a bracketed request/terminal strip.
 *  - pilot_decision_made         → an expanded decision row (rationale,
 *                                   confidence meter, reason chip, fallback).
 *  - everything else             → a single-line telemetry row.
 *
 * Presentational: all state (side, lane, dim, focus, thinking) arrives as
 * props so the row is trivially unit-testable.
 */
import type React from "react";
import {
  confidenceSegments,
  fallbackClassOf,
  formatStamp,
  glyphOf,
  groupOf,
  isDangerEvent,
  type Side,
  summarizeEnvelope,
} from "../lib/river";
import type { SOEventEnvelope } from "../types";

const SIDE_COLOR: Record<Side, string> = {
  red: "var(--ember)",
  blue: "var(--arc)",
  neutral: "var(--ash)",
};

const GUTTER_W = 48;
const ROW_H = 40;
const LANE_STEP = 7;
const LANE_X0 = 6;

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
          {env.payload.model} · {env.payload.reason_code}
          {env.payload.cost_usd !== null ? (
            <>
              {" "}
              · <b>${env.payload.cost_usd.toFixed(4)}</b>
            </>
          ) : null}
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
      </span>
    </>
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
      <span
        className="pd-conf"
        data-testid="decision-confidence"
        role="img"
        aria-label={`confidence ${payload.confidence.toFixed(2)}`}
      >
        {confidenceSegments(payload.confidence).map((on, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed 5-segment meter, never reorders
          <i key={i} data-on={on} />
        ))}
      </span>
      <span className="pd-chip">{payload.reason_code}</span>
      {fallback !== null ? (
        <span className="pd-chip" data-fallback="true" data-testid="fallback-chip">
          FALLBACK: {fallback}
        </span>
      ) : null}
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
  const rationale = isDecision && env.payload.rationale !== null ? env.payload.rationale : null;
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
