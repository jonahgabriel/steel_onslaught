/**
 * MechMarker — Task 32.
 *
 * SVG foreignObject containing the mech's heat/pressure/hp bars and a chassis
 * class icon letter (L/M/H).  Positioned at grid cell (x, y) on the tactical
 * board; `cellSize` is the pixel width/height of one grid cell.
 *
 * Returns null when alive=false — the caller swaps in a wreckage glyph.
 *
 * Pure presentational component — receives props only, emits nothing.
 */
import HeatBar from "./HeatBar";
import PressureBar from "./PressureBar";

export interface MechMarkerProps {
  mechId: string;
  chassisClass: "light" | "medium" | "heavy";
  heat: number;
  redlineThreshold: number;
  ruptureThreshold: number;
  pressureCurrent: number;
  pressureMaximum: number;
  hp: number;
  hpMax: number;
  x: number;
  y: number;
  cellSize: number;
  alive: boolean;
}

const CLASS_LABELS: Record<"light" | "medium" | "heavy", string> = {
  light: "L",
  medium: "M",
  heavy: "H",
};

const CLASS_COLORS: Record<"light" | "medium" | "heavy", string> = {
  light: "#a3e635", // lime-400
  medium: "#fb923c", // orange-400
  heavy: "#a78bfa", // violet-400
};

export default function MechMarker({
  mechId,
  chassisClass,
  heat,
  redlineThreshold,
  ruptureThreshold,
  pressureCurrent,
  pressureMaximum,
  hp,
  hpMax,
  x,
  y,
  cellSize,
  alive,
}: MechMarkerProps): React.JSX.Element | null {
  if (!alive) return null;

  const px = x * cellSize;
  const py = y * cellSize;
  const hpPct = hpMax > 0 ? Math.round(Math.min(100, Math.max(0, (hp / hpMax) * 100))) : 0;

  return (
    <g
      data-testid={`mech-marker-${mechId}`}
      data-chassis-class={chassisClass}
      transform={`translate(${px}, ${py})`}
    >
      {/* Chassis circle icon */}
      <circle
        r={cellSize * 0.35}
        cx={cellSize / 2}
        cy={cellSize / 2}
        fill={CLASS_COLORS[chassisClass]}
        stroke="#1f2937"
        strokeWidth={1}
      />
      <text
        x={cellSize / 2}
        y={cellSize / 2 + 4}
        textAnchor="middle"
        fontSize={cellSize * 0.4}
        fill="#1f2937"
        fontWeight="bold"
        style={{ userSelect: "none" }}
      >
        {CLASS_LABELS[chassisClass]}
      </text>

      {/* Status bars rendered via foreignObject below the marker circle */}
      <foreignObject x={0} y={cellSize * 0.75} width={cellSize} height={cellSize * 0.9}>
        <div style={{ display: "flex", flexDirection: "column", gap: 1, padding: "0 1px" }}>
          <HeatBar
            heat={heat}
            redlineThreshold={redlineThreshold}
            ruptureThreshold={ruptureThreshold}
          />
          <PressureBar current={pressureCurrent} maximum={pressureMaximum} />
          {/* HP bar */}
          <div
            data-testid="hp-bar"
            data-hp-pct={String(hpPct)}
            style={{
              width: "100%",
              height: 4,
              background: "#374151",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${hpPct}%`,
                height: "100%",
                background: "#34d399", // emerald-400
                transition: "width 0.2s",
              }}
            />
          </div>
        </div>
      </foreignObject>
    </g>
  );
}
