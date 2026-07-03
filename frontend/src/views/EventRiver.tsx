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
  // Last observed scrollTop and a flag marking scrolls WE caused. Together they
  // let `onScroll` tell a genuine user scroll from the component's own
  // programmatic follow-scroll and from content-growth reflow — see below.
  const lastTopRef = useRef(0);
  const programmaticRef = useRef(false);

  // Follow the newest row while pinned. `bottomKey` is the per-append change
  // signal; the body reads scrollHeight fresh each run.
  // biome-ignore lint/correctness/useExhaustiveDependencies: bottomKey is the append signal — re-run when the newest row id changes though the body reads scrollHeight
  useEffect(() => {
    const el = scrollRef.current;
    if (el === null || !pinned) return;
    programmaticRef.current = true;
    el.scrollTop = el.scrollHeight;
    lastTopRef.current = el.scrollTop;
  }, [bottomKey, pinned]);

  // Only a genuine UPWARD user scroll un-pins; scrolling back to the bottom
  // re-pins. Appending a batch at the bottom (which grows scrollHeight and, via
  // scroll anchoring, nudges scrollTop DOWN toward the bottom) and our own
  // programmatic scroll must never un-pin — that race was freezing the river.
  function onScroll(): void {
    const el = scrollRef.current;
    if (el === null) return;
    const top = el.scrollTop;
    const prev = lastTopRef.current;
    lastTopRef.current = top;
    if (programmaticRef.current) {
      programmaticRef.current = false;
      return; // our own follow-scroll — never changes pin state
    }
    if (top < prev - 2) {
      setPinned(false); // user dragged the view upward → stop following
    } else if (el.scrollHeight - top - el.clientHeight < 24) {
      setPinned(true); // user returned to the bottom → resume following
    }
  }

  function resume(): void {
    const el = scrollRef.current;
    if (el !== null) {
      programmaticRef.current = true;
      el.scrollTop = el.scrollHeight;
      lastTopRef.current = el.scrollTop;
    }
    setPinned(true);
  }

  return (
    <div className="pd-river-wrap">
      <div className="pd-river-title">E V E N T&nbsp;&nbsp;R I V E R</div>
      <div
        className="pd-river"
        ref={scrollRef}
        onScroll={onScroll}
        onMouseEnter={() => setPinned(false)}
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
