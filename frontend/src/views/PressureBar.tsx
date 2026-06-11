/**
 * PressureBar — Task 32.
 *
 * Renders a horizontal pressure bar for one mech.
 * The bar fill is proportional to current / maximum pressure.
 * data-pressure-pct is set to the rounded integer percentage (0–100).
 *
 * Pure presentational component — receives props only, emits nothing.
 */

export interface PressureBarProps {
  current: number;
  maximum: number;
}

export default function PressureBar({ current, maximum }: PressureBarProps): React.JSX.Element {
  const pct = maximum > 0 ? Math.round(Math.min(100, Math.max(0, (current / maximum) * 100))) : 0;

  return (
    <div
      data-testid="pressure-bar"
      data-pressure-pct={String(pct)}
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
          background: "#60a5fa", // blue-400
          transition: "width 0.2s",
        }}
      />
    </div>
  );
}
