/**
 * GaugeRail — PRESSURE DECK left rail.
 *
 * Two mech stacks (RED above BLUE), each a boiler-pressure dial, heat bar,
 * armor pool, mode chip and status lamp.  Reuses the existing HeatBar /
 * PressureBar logic (restyled, not re-derived) and folds from the same
 * envelope stream via `lib/gauges.ts`.
 */
import type React from "react";
import type { GaugeState, MechStatus } from "../lib/gauges";
import type { Side } from "../lib/river";
import HeatBar from "./HeatBar";
import PressureBar from "./PressureBar";

const STATUS_LABEL: Record<MechStatus, string> = {
  alive: "ALIVE",
  pilot_killed: "PILOT KILLED",
  destroyed: "DESTROYED",
};

/** SVG boiler-pressure dial: amber arc, red zone, needle at current psi. */
function BoilerDial({ current, maximum }: { current: number; maximum: number }): React.JSX.Element {
  const frac = maximum > 0 ? Math.max(0, Math.min(1, current / maximum)) : 0;
  // 240° sweep from 150° to 390°(=30°)
  const start = 150;
  const sweep = 240;
  const angle = start + frac * sweep;
  const cx = 46;
  const cy = 46;
  const r = 34;
  const rad = (deg: number): number => (deg * Math.PI) / 180;
  const arcPoint = (deg: number, radius: number): [number, number] => [
    cx + radius * Math.cos(rad(deg)),
    cy + radius * Math.sin(rad(deg)),
  ];
  const [nx, ny] = arcPoint(angle, r - 6);
  const [rzx1, rzy1] = arcPoint(start + sweep * 0.75, r);
  const [rzx2, rzy2] = arcPoint(start + sweep, r);

  return (
    <svg className="pd-dial" width={92} height={78} viewBox="0 0 92 78" aria-hidden="true">
      <path
        d={`M ${arcPoint(start, r).join(" ")} A ${r} ${r} 0 1 1 ${arcPoint(start + sweep, r).join(" ")}`}
        fill="none"
        stroke="#0d0f13"
        strokeWidth={7}
      />
      <path
        d={`M ${arcPoint(start, r).join(" ")} A ${r} ${r} 0 1 1 ${arcPoint(angle, r).join(" ")}`}
        fill="none"
        stroke="var(--phosphor)"
        strokeWidth={5}
        strokeLinecap="round"
      />
      <path
        d={`M ${rzx1} ${rzy1} A ${r} ${r} 0 0 1 ${rzx2} ${rzy2}`}
        fill="none"
        stroke="var(--danger)"
        strokeWidth={5}
        opacity={0.85}
      />
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--steam)" strokeWidth={2} />
      <circle cx={cx} cy={cy} r={3} fill="var(--steam)" />
      <text
        x={cx}
        y={cy + 20}
        textAnchor="middle"
        fontSize={10}
        fill="var(--ash)"
        fontFamily="var(--font-mono)"
      >
        {Math.round(current)}/{Math.round(maximum)}
      </text>
    </svg>
  );
}

function MechStack({ g }: { g: GaugeState }): React.JSX.Element {
  const armorPct =
    g.armorMax > 0 ? Math.max(0, Math.min(100, (g.armorValue / g.armorMax) * 100)) : 0;
  return (
    <section className="pd-mechstack pd-panel" data-side={g.side} data-testid={`gauge-${g.mechId}`}>
      <div className="pd-mech-head">
        <span className="pd-mech-name" data-side={g.side}>
          {g.side === "neutral" ? g.mechId : g.side.toUpperCase()}
        </span>
        <span className="pd-lamp" data-status={g.status} data-testid={`lamp-${g.mechId}`}>
          {STATUS_LABEL[g.status]}
        </span>
      </div>
      <BoilerDial current={g.pressureCurrent} maximum={g.pressureMaximum} />
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">HEAT</span>
        <HeatBar
          heat={g.heat}
          redlineThreshold={g.redlineThreshold}
          ruptureThreshold={g.ruptureThreshold}
        />
      </div>
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">PSI</span>
        <PressureBar current={g.pressureCurrent} maximum={g.pressureMaximum} />
      </div>
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">ARMOR</span>
        <div className="pd-armor" data-testid={`armor-${g.mechId}`}>
          <div className="pd-armor-fill" style={{ width: `${armorPct}%` }} />
        </div>
      </div>
      <div className="pd-gauge-row">
        <span className="pd-gauge-label">MODE</span>
        <span className="pd-mode-chip">{g.mode || "—"}</span>
      </div>
    </section>
  );
}

export interface GaugeRailProps {
  gauges: readonly GaugeState[];
}

const SIDE_ORDER: Record<Side, number> = { red: 0, blue: 1, neutral: 2 };

export default function GaugeRail({ gauges }: GaugeRailProps): React.JSX.Element {
  const ordered = [...gauges].sort((a, b) => SIDE_ORDER[a.side] - SIDE_ORDER[b.side]);
  return (
    <div className="pd-rail" data-testid="gauge-rail">
      {ordered.length === 0 ? (
        <div className="pd-earlier">awaiting match_started…</div>
      ) : (
        ordered.map((g) => <MechStack key={g.mechId} g={g} />)
      )}
    </div>
  );
}
