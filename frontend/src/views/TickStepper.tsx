/**
 * TickStepper — Task 33.
 *
 * Navigation bar for the pilot decision inspector.  Renders four buttons:
 *   « (first)   ‹ (prev)   [currentTick]   › (next)   » (last)
 *
 * Invariants:
 * - `currentTick` is clamped to [0, finalTick]; prev at 0 → no-op;
 *   next at finalTick → no-op.
 * - `onChange` is called only when the new tick differs from `currentTick`.
 */

import React from "react";

export interface TickStepperProps {
  /** The tick currently displayed in the inspector. */
  currentTick: number;
  /** The last valid tick for this match (upper bound). */
  finalTick: number;
  /** Called with the new tick value when the user navigates. */
  onChange: (tick: number) => void;
}

export function TickStepper({
  currentTick,
  finalTick,
  onChange,
}: TickStepperProps): React.ReactElement {
  const atStart = currentTick <= 0;
  const atEnd = currentTick >= finalTick;

  function handleFirst(): void {
    if (!atStart) onChange(0);
  }

  function handlePrev(): void {
    if (!atStart) onChange(currentTick - 1);
  }

  function handleNext(): void {
    if (!atEnd) onChange(currentTick + 1);
  }

  function handleLast(): void {
    if (!atEnd) onChange(finalTick);
  }

  return (
    <div
      data-testid="tick-stepper"
      style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontFamily: "monospace" }}
    >
      <button
        data-testid="tick-first"
        onClick={handleFirst}
        disabled={atStart}
        aria-label="first tick"
        title="Jump to first tick"
      >
        «
      </button>
      <button
        data-testid="tick-prev"
        onClick={handlePrev}
        disabled={atStart}
        aria-label="previous tick"
        title="Previous tick"
      >
        ‹
      </button>
      <span
        data-testid="tick-current"
        style={{ minWidth: "4ch", textAlign: "center", fontWeight: "bold" }}
      >
        {currentTick}
      </span>
      <button
        data-testid="tick-next"
        onClick={handleNext}
        disabled={atEnd}
        aria-label="next tick"
        title="Next tick"
      >
        ›
      </button>
      <button
        data-testid="tick-last"
        onClick={handleLast}
        disabled={atEnd}
        aria-label="last tick"
        title="Jump to last tick"
      >
        »
      </button>
    </div>
  );
}
