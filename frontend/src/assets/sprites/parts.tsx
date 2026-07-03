/**
 * Shared building blocks for the three chassis sprites.
 *
 * Coordinate system: a 100×100 viewBox, sprite centered at (50,50), NOSE
 * pointing UP (−y) at `facing = 0`. Facing arrives as DEGREES (the game's
 * `SOMechRuntimeState.facing`, e.g. 90 / 270 in fixtures) and is applied as a
 * clockwise SVG rotation about the center. All strokes use
 * `vectorEffect: non-scaling-stroke` so the 2px line reads identically whether
 * the sprite is painted at 24px (arena) or 48px (spec panel).
 */
import type { JSX, ReactNode } from "react";
import { AssetKeyframes } from "../keyframes";
import { cssVar, type MechState, SIDE_ACCENT, type Side, sideStyle } from "../theme";

export interface ChassisSpriteProps {
  /** Facing in degrees (clockwise; 0 = nose up). Defaults to 0. */
  facing?: number;
  /** Damage tier. Defaults to `nominal`. */
  state?: MechState;
  /** Emit steam vent puffs. */
  venting?: boolean;
  /** Show a muzzle flash at the nose. */
  firing?: boolean;
  /** Rendered pixel size (width = height). Defaults to 48. */
  size?: number;
  /** Side accent (RED/BLUE). Sets `--so-side`; omit to inherit `currentColor`. */
  side?: Side;
  /** Accessible label; defaults to a class + state description. */
  title?: string;
  /** Extra testid suffix / class passthrough. */
  className?: string;
}

const STROKE = cssVar("ash");
const HULL = cssVar("iron");
const DETAIL = cssVar("steam");
const DANGER = cssVar("danger");
const VENT = cssVar("vent");
const PHOSPHOR = cssVar("phosphor");

/** Common plate-stroke props for line-art blueprint geometry. */
export const plate = {
  fill: HULL,
  stroke: STROKE,
  strokeWidth: 2,
  strokeLinejoin: "round" as const,
  vectorEffect: "non-scaling-stroke" as const,
};

export const sideAccent = {
  fill: SIDE_ACCENT,
  stroke: SIDE_ACCENT,
  strokeWidth: 2,
  vectorEffect: "non-scaling-stroke" as const,
};

/** A small rivet dot. */
export function Rivet({ cx, cy }: { cx: number; cy: number }): JSX.Element {
  return <circle cx={cx} cy={cy} r={1.4} fill={STROKE} stroke="none" />;
}

/** Boiler stack — the class-defining silhouette detail. */
export function Boiler({ cx, cy, r }: { cx: number; cy: number; r: number }): JSX.Element {
  return (
    <g data-testid="sprite-boiler">
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill={cssVar("seam")}
        {...{ stroke: STROKE, strokeWidth: 2 }}
        vectorEffect="non-scaling-stroke"
      />
      <circle
        cx={cx}
        cy={cy}
        r={r * 0.5}
        fill="none"
        stroke={PHOSPHOR}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
    </g>
  );
}

/** Scorch smudges for the `damaged`/`critical` states. */
export function Scorch(): JSX.Element {
  return (
    <g data-testid="sprite-scorch" opacity={0.7}>
      <ellipse cx={38} cy={44} rx={9} ry={6} fill={cssVar("coal")} opacity={0.65} />
      <ellipse cx={64} cy={58} rx={7} ry={5} fill={cssVar("coal")} opacity={0.6} />
      <path
        d="M58 40 l6 -5 m-3 8 l7 -3"
        stroke={DANGER}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
        fill="none"
      />
    </g>
  );
}

/** Boiler-glow pulse for the `critical` state (`--danger`). */
export function CriticalGlow({ cx, cy, r }: { cx: number; cy: number; r: number }): JSX.Element {
  return (
    <circle
      data-testid="sprite-critical-glow"
      className="so-anim-crit"
      cx={cx}
      cy={cy}
      r={r * 1.5}
      fill={DANGER}
      opacity={0.4}
    />
  );
}

/** Steam vent puffs (three staggered) rising from the boiler rail. */
export function VentPuffs({ cx, cy }: { cx: number; cy: number }): JSX.Element {
  return (
    <g data-testid="sprite-vent">
      {[0, 1, 2].map((i) => (
        <circle
          key={i}
          className="so-anim-vent"
          cx={cx + (i - 1) * 7}
          cy={cy - i * 6 - 6}
          r={4 - i}
          fill={VENT}
          opacity={0.5}
          style={{ animationDelay: `${i * 0.35}s` }}
        />
      ))}
    </g>
  );
}

/** Muzzle flash wedge at the nose (points forward, rotates with the body). */
export function MuzzleFlash({ noseY }: { noseY: number }): JSX.Element {
  return (
    <g data-testid="sprite-muzzle" className="so-anim-muzzle">
      <path d={`M50 ${noseY} l-6 -10 l6 5 l6 -5 z`} fill={PHOSPHOR} stroke="none" />
      <circle cx={50} cy={noseY - 4} r={3} fill={DETAIL} opacity={0.9} />
    </g>
  );
}

/**
 * The outer frame every chassis sprite shares: SVG root, a11y, side theming,
 * facing rotation, and state/flag overlays. Concrete sprites supply their hull
 * (`body`) and destroyed (`wreck`) geometry plus the nose Y for the muzzle.
 */
export function SpriteFrame({
  chassis,
  body,
  wreck,
  noseY,
  boilerAt,
  facing = 0,
  state = "nominal",
  venting = false,
  firing = false,
  size = 48,
  side,
  title,
  className,
}: ChassisSpriteProps & {
  chassis: "scout" | "hunter" | "ironclad";
  body: ReactNode;
  wreck: ReactNode;
  noseY: number;
  boilerAt: { cx: number; cy: number; r: number };
}): JSX.Element {
  const destroyed = state === "destroyed";
  const label = title ?? `${chassis} chassis, ${state}`;
  return (
    <svg
      data-testid={`sprite-${chassis}`}
      data-chassis={chassis}
      data-state={state}
      data-facing={facing}
      data-venting={venting}
      data-firing={firing && !destroyed}
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label={label}
      style={sideStyle(side, { overflow: "visible", display: "block" })}
    >
      <title>{label}</title>
      {(state === "critical" || venting || (firing && !destroyed)) && <AssetKeyframes />}
      <g data-testid="sprite-body" transform={`rotate(${facing} 50 50)`}>
        {destroyed ? (
          wreck
        ) : (
          <>
            {body}
            {(state === "damaged" || state === "critical") && <Scorch />}
            {state === "critical" && <CriticalGlow {...boilerAt} />}
            {firing && <MuzzleFlash noseY={noseY} />}
          </>
        )}
        {venting && <VentPuffs cx={boilerAt.cx} cy={boilerAt.cy} />}
      </g>
    </svg>
  );
}

/** Shared wreck detailing: cracks + a residual danger tint over hull rubble. */
export function WreckCracks(): JSX.Element {
  return (
    <g
      data-testid="sprite-wreck"
      stroke={DANGER}
      strokeWidth={2}
      vectorEffect="non-scaling-stroke"
      fill="none"
    >
      <path d="M40 38 l10 12 l-6 10 M60 40 l-8 12 l10 8" />
    </g>
  );
}
