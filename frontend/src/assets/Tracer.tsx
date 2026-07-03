/**
 * Weapon tracer — one styled line per `weapon_class`, drawn in the arena.
 *
 * `from`/`to` are GRID coordinates (cell indices). The tracer renders a
 * self-contained `<svg>` whose viewBox spans the whole grid (`0 0 N N`), so the
 * arena scales it to the plotting square via width/height 100%. Strokes use
 * `vectorEffect: non-scaling-stroke`, so line weight stays crisp at any arena
 * size and `preserveAspectRatio="none"` cannot distort them.
 *
 * Per-class style (SPEC Rev 2):
 *   light  — dashed rapid stipple burst
 *   medium — solid bolt / heat-shimmer beam
 *   heavy  — thick line with a barbed head
 *   siege  — arced lob path + impact ring
 */
import type { JSX } from "react";
import { AssetKeyframes } from "./keyframes";
import { cssVar, SIDE_ACCENT, type Side, sideStyle, type WeaponClass } from "./theme";

export interface Coord {
  x: number;
  y: number;
}

export interface TracerProps {
  from: Coord;
  to: Coord;
  weaponClass: WeaponClass;
  /** Grid dimension (cells per side). Defaults to 40. */
  gridCells?: number;
  /** Side accent; sets `--so-side`, else inherits `currentColor`. */
  side?: Side;
  /** Show an impact ring at `to` (e.g. on `hit_resolved`). Siege always does. */
  impact?: boolean;
  /** Animate the tracer draw-in (guarded by prefers-reduced-motion). */
  animate?: boolean;
  className?: string;
}

const center = (n: number): number => n + 0.5;

/** Impact ring at the target cell. */
function ImpactRing({ cx, cy }: { cx: number; cy: number }): JSX.Element {
  return (
    <g data-testid="tracer-impact">
      <circle
        cx={cx}
        cy={cy}
        r={1.1}
        fill="none"
        stroke={SIDE_ACCENT}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={cx} cy={cy} r={0.4} fill={cssVar("phosphor")} stroke="none" />
    </g>
  );
}

export function Tracer({
  from,
  to,
  weaponClass,
  gridCells = 40,
  side,
  impact = false,
  animate = false,
  className,
}: TracerProps): JSX.Element {
  const x1 = center(from.x);
  const y1 = center(from.y);
  const x2 = center(to.x);
  const y2 = center(to.y);
  const animClass = animate ? "so-anim-tracer" : undefined;

  let line: JSX.Element;
  switch (weaponClass) {
    case "light":
      line = (
        <line
          className={animClass}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke={SIDE_ACCENT}
          strokeWidth={1.5}
          strokeDasharray="2 1.5"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      );
      break;
    case "medium":
      line = (
        <g className={animClass}>
          <line
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={SIDE_ACCENT}
            strokeWidth={5}
            strokeLinecap="round"
            opacity={0.3}
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={cssVar("phosphor")}
            strokeWidth={2}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </g>
      );
      break;
    case "heavy": {
      const ang = Math.atan2(y2 - y1, x2 - x1);
      const bl = 2.2;
      const b1x = x2 - bl * Math.cos(ang - 0.5);
      const b1y = y2 - bl * Math.sin(ang - 0.5);
      const b2x = x2 - bl * Math.cos(ang + 0.5);
      const b2y = y2 - bl * Math.sin(ang + 0.5);
      line = (
        <g className={animClass}>
          <line
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={SIDE_ACCENT}
            strokeWidth={3.5}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={`M${x2} ${y2} L${b1x} ${b1y} M${x2} ${y2} L${b2x} ${b2y}`}
            stroke={SIDE_ACCENT}
            strokeWidth={2.5}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            fill="none"
          />
        </g>
      );
      break;
    }
    default: {
      // siege — arced lob (control point lifted perpendicular to the chord)
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      const dist = Math.hypot(x2 - x1, y2 - y1);
      const lift = Math.max(3, dist * 0.35);
      const cy = my - lift;
      line = (
        <path
          className={animClass}
          d={`M${x1} ${y1} Q${mx} ${cy} ${x2} ${y2}`}
          fill="none"
          stroke={SIDE_ACCENT}
          strokeWidth={2}
          strokeDasharray="3 2"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      );
      break;
    }
  }

  const showRing = impact || weaponClass === "siege";

  return (
    <svg
      data-testid={`tracer-${weaponClass}`}
      data-weapon-class={weaponClass}
      className={className}
      viewBox={`0 0 ${gridCells} ${gridCells}`}
      preserveAspectRatio="none"
      width="100%"
      height="100%"
      role="presentation"
      style={sideStyle(side, {
        position: "absolute",
        inset: 0,
        overflow: "visible",
        pointerEvents: "none",
      })}
    >
      {animate && <AssetKeyframes />}
      {line}
      {showRing && <ImpactRing cx={x2} cy={y2} />}
    </svg>
  );
}

export default Tracer;
