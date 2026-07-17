/**
 * Ticker — PRESSURE DECK bottom filter bar.
 *
 * Stencil toggle chips with live per-group counts; toggling a chip hides that
 * group's rows in the river.  `f` cycles chip focus (handled by the deck).
 */
import type React from "react";
import { forwardRef } from "react";
import { FILTER_GROUP_LABELS, FILTER_GROUPS, type FilterGroup } from "../lib/river";

export interface TickerProps {
  active: ReadonlySet<FilterGroup>;
  counts: Record<FilterGroup, number>;
  total: number;
  onToggle: (group: FilterGroup) => void;
}

const Ticker = forwardRef<HTMLDivElement, TickerProps>(function Ticker(
  { active, counts, total, onToggle },
  ref,
): React.JSX.Element {
  return (
    <footer className="pd-ticker" ref={ref} data-testid="ticker">
      {FILTER_GROUPS.map((group) => (
        <button
          key={group}
          type="button"
          className="pd-filter"
          data-group={group}
          data-active={active.has(group)}
          aria-pressed={active.has(group)}
          onClick={() => onToggle(group)}
          data-testid={`filter-${group}`}
        >
          ⌸ {FILTER_GROUP_LABELS[group]}
          <span className="pd-count">{counts[group]}</span>
        </button>
      ))}
      <span className="pd-total" data-testid="event-total">
        {total} events
      </span>
    </footer>
  );
});

export default Ticker;
