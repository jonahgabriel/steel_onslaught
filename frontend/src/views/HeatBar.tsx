/**
 * HeatBar — Task 32.
 *
 * Renders a horizontal heat bar for one mech.
 * Color coding:
 *   - green  (data-heat-level="normal")  : heat <= redlineThreshold - 10
 *   - amber  (data-heat-level="warning") : redlineThreshold - 10 < heat <= redlineThreshold
 *   - red    (data-heat-level="redline") : heat > redlineThreshold
 *
 * Pure presentational component — receives props only, emits nothing.
 */

export interface HeatBarProps {
  heat: number;
  redlineThreshold: number;
  ruptureThreshold: number;
}

type HeatLevel = "normal" | "warning" | "redline";

function heatLevel(heat: number, redline: number): HeatLevel {
  if (heat > redline) return "redline";
  if (heat > redline - 10) return "warning";
  return "normal";
}

const HEAT_COLORS: Record<HeatLevel, string> = {
  normal: "#22c55e", // green-500
  warning: "#f59e0b", // amber-500
  redline: "#ef4444", // red-500
};

export default function HeatBar({
  heat,
  redlineThreshold,
  ruptureThreshold,
}: HeatBarProps): React.JSX.Element {
  const level = heatLevel(heat, redlineThreshold);
  const pct = Math.min(100, Math.max(0, (heat / ruptureThreshold) * 100));

  return (
    <div
      data-testid="heat-bar"
      data-heat-level={level}
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
          width: `${pct}%`,
          height: "100%",
          background: HEAT_COLORS[level],
          transition: "width 0.2s, background 0.2s",
        }}
      />
    </div>
  );
}
