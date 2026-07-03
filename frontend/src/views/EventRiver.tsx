/**
 * EventRiver — PRESSURE DECK centerpiece.
 *
 * Renders ordered, tick-grouped rows newest-at-bottom with autoscroll that
 * pauses on hover / manual scroll and resumes via a floating LIVE chip.
 * All ordering / grouping / windowing is done upstream (pure `lib/river.ts`);
 * this component is presentation + scroll behaviour only.
 */
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { type MessageId, parentIdOf } from "../lib/causation";
import { llmEvidenceKind, type SideMap, sideOf, type TickGroup } from "../lib/river";
import type { SOEventEnvelope } from "../types";
import EventRow from "./EventRow";

export interface EventRiverProps {
  groups: readonly TickGroup[];
  hiddenCount: number;
  sides: SideMap;
  laneMap: ReadonlyMap<MessageId, number>;
  highlight: ReadonlySet<MessageId> | null;
  unresolved: ReadonlySet<MessageId>;
  focusedEventId: string | null;
  bottomKey: string | null;
  onSelect: (env: SOEventEnvelope) => void;
  onHover: (env: SOEventEnvelope | null) => void;
}

export default function EventRiver({
  groups,
  hiddenCount,
  sides,
  laneMap,
  highlight,
  unresolved,
  focusedEventId,
  bottomKey,
  onSelect,
  onHover,
}: EventRiverProps): React.JSX.Element {
  // (index is intentionally not needed: parent lanes resolve from laneMap.)
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const pausedRef = useRef(false);

  // Autoscroll to newest when pinned and not paused by hover.
  // biome-ignore lint/correctness/useExhaustiveDependencies: bottomKey is the change signal — re-run when the newest row id changes though the body reads scrollHeight
  useEffect(() => {
    const el = scrollRef.current;
    if (el === null || !pinned || pausedRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [bottomKey, pinned]);

  function onScroll(): void {
    const el = scrollRef.current;
    if (el === null) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setPinned(atBottom);
  }

  function resume(): void {
    const el = scrollRef.current;
    if (el !== null) el.scrollTop = el.scrollHeight;
    setPinned(true);
  }

  return (
    <div className="pd-river-wrap">
      <div className="pd-river-title">E V E N T&nbsp;&nbsp;R I V E R</div>
      <div
        className="pd-river"
        ref={scrollRef}
        onScroll={onScroll}
        onMouseEnter={() => {
          pausedRef.current = true;
        }}
        onMouseLeave={() => {
          pausedRef.current = false;
        }}
        role="log"
        aria-label="Event river"
        data-testid="event-river"
      >
        {hiddenCount > 0 ? (
          <div className="pd-earlier" data-testid="earlier-events">
            … {hiddenCount} earlier events
          </div>
        ) : null}
        {groups.map((group) => (
          <div key={group.tick} data-testid={`tick-group-${group.tick}`}>
            <div className="pd-tick-sep" data-testid={`tick-sep-${group.tick}`}>
              <span className="pd-tick-tab">TICK {String(group.tick).padStart(3, "0")}</span>
            </div>
            {group.rows.map((row) => {
              const mid = row.env.envelope.message_id;
              const parent = parentIdOf(row.env);
              const parentLane =
                parent !== null && laneMap.has(parent) ? (laneMap.get(parent) ?? null) : null;
              const requested = llmEvidenceKind(row.env) === "requested";
              return (
                <EventRow
                  key={row.env.event_id}
                  env={row.env}
                  side={sideOf(row.env, sides)}
                  lane={laneMap.get(mid) ?? 0}
                  parentLane={parentLane}
                  focused={row.env.event_id === focusedEventId}
                  dimmed={highlight !== null && !highlight.has(mid)}
                  thinking={requested && unresolved.has(mid)}
                  onSelect={onSelect}
                  onHover={onHover}
                />
              );
            })}
          </div>
        ))}
      </div>
      {!pinned ? (
        <button type="button" className="pd-live" onClick={resume} data-testid="live-chip">
          LIVE ▼
        </button>
      ) : null}
    </div>
  );
}
