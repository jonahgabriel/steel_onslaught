/**
 * RadarPanel — PRESSURE DECK top-right plotting table.
 *
 * Embeds the existing TacticalBoard (restyled container, not re-derived) as a
 * miniature dark plotting grid. The board keeps its own projection reducer and
 * the same `subscribe` fan-out the deck uses.
 */
import type React from "react";
import type { EnvelopeHandler } from "../lib/event_stream";
import TacticalBoard from "./TacticalBoard";

export interface RadarPanelProps {
  subscribe: (handler: EnvelopeHandler) => () => void;
}

export default function RadarPanel({ subscribe }: RadarPanelProps): React.JSX.Element {
  return (
    <div className="pd-radar pd-panel" data-testid="radar-panel">
      <div className="pd-radar-title">RADAR ▸ PLOTTING TABLE</div>
      <div className="pd-radar-board">
        <TacticalBoard subscribe={subscribe} />
      </div>
    </div>
  );
}
