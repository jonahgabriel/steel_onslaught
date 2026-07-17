/**
 * Deck furniture — favicon, wordmark lockup, and the AWAITING TRANSMISSION
 * boot/empty state.
 *
 * The favicon is emitted both as a React component and as a ready-to-use
 * `data:` URI string (`faviconDataUri`) — the LAYOUT agent wires it into
 * `index.html`; this pack does not touch that file. Because a favicon renders
 * with no page CSS context, its colors are literal hex (not CSS vars).
 */
import type { CSSProperties, JSX } from "react";
import { AssetKeyframes } from "./keyframes";
import { cssVar, PALETTE } from "./theme";

// ---------------------------------------------------------------------------
// Favicon — notched gear-boiler mark
// ---------------------------------------------------------------------------

/** Inner markup shared by the component and the data-URI (literal hex). */
const FAVICON_INNER = [
  `<path d='M3 3 H23 L29 9 V29 H9 L3 23 Z' fill='${PALETTE.coal}' stroke='${PALETTE.seam}' stroke-width='2'/>`,
  // gear ring (8 teeth via a dasharray-free star of rects is heavy; use a ring + notch spokes)
  `<circle cx='16' cy='16' r='9' fill='none' stroke='${PALETTE.phosphor}' stroke-width='2'/>`,
  `<g stroke='${PALETTE.phosphor}' stroke-width='2'>`,
  `<path d='M16 4 V7 M16 25 V28 M4 16 H7 M25 16 H28 M7.5 7.5 L9.6 9.6 M22.4 22.4 L24.5 24.5 M24.5 7.5 L22.4 9.6 M9.6 22.4 L7.5 24.5'/>`,
  `</g>`,
  // boiler core
  `<circle cx='16' cy='16' r='4' fill='${PALETTE.ember}'/>`,
  `<circle cx='16' cy='16' r='1.6' fill='${PALETTE.coal}'/>`,
].join("");

const FAVICON_SVG = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>${FAVICON_INNER}</svg>`;

/** Ready-to-use favicon `data:` URI for `<link rel="icon">`. */
export const faviconDataUri = `data:image/svg+xml,${encodeURIComponent(FAVICON_SVG)}`;

export interface FaviconProps {
  size?: number;
  className?: string;
  title?: string;
}

/** The gear-boiler mark as a React component (uses live CSS vars). */
export function Favicon({
  size = 32,
  className,
  title = "Steel Onslaught",
}: FaviconProps): JSX.Element {
  return (
    <svg
      data-testid="favicon"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      className={className}
    >
      <title>{title}</title>
      <path
        d="M3 3 H23 L29 9 V29 H9 L3 23 Z"
        fill={cssVar("coal")}
        stroke={cssVar("seam")}
        strokeWidth={2}
      />
      <circle cx={16} cy={16} r={9} fill="none" stroke={cssVar("phosphor")} strokeWidth={2} />
      <g stroke={cssVar("phosphor")} strokeWidth={2}>
        <path d="M16 4 V7 M16 25 V28 M4 16 H7 M25 16 H28 M7.5 7.5 L9.6 9.6 M22.4 22.4 L24.5 24.5 M24.5 7.5 L22.4 9.6 M9.6 22.4 L7.5 24.5" />
      </g>
      <circle cx={16} cy={16} r={4} fill={cssVar("ember")} />
      <circle cx={16} cy={16} r={1.6} fill={cssVar("coal")} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Wordmark lockup
// ---------------------------------------------------------------------------

const STENCIL_STACK = '"Big Shoulders Stencil", "Arial Narrow", system-ui, sans-serif';

export interface WordmarkProps {
  /** Overall height in px (mark + type scale from it). Defaults to 28. */
  height?: number;
  className?: string;
  /** Hide the gear-boiler mark, show type only. */
  markless?: boolean;
}

/** STEEL ONSLAUGHT lockup — gear-boiler mark + stencil type. */
export function Wordmark({ height = 28, className, markless = false }: WordmarkProps): JSX.Element {
  const fontSize = Math.round(height * 0.82);
  return (
    <span
      data-testid="wordmark"
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: Math.round(height * 0.28),
        lineHeight: 1,
        color: cssVar("steam"),
      }}
    >
      {!markless && <Favicon size={height} />}
      <span
        style={{
          fontFamily: STENCIL_STACK,
          fontWeight: 700,
          fontSize,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        Steel <span style={{ color: cssVar("phosphor") }}>Onslaught</span>
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// AWAITING TRANSMISSION — boot / empty state
// ---------------------------------------------------------------------------

export interface AwaitingTransmissionProps {
  /** Override the primary line (defaults to AWAITING TRANSMISSION). */
  label?: string;
  /** Secondary hint line under the label. */
  hint?: string;
  className?: string;
  style?: CSSProperties;
}

/** Full-panel empty state: scanline sweep behind stencil signage. */
export function AwaitingTransmission({
  label = "Awaiting Transmission",
  hint = "connect a ledger stream to begin",
  className,
  style,
}: AwaitingTransmissionProps): JSX.Element {
  return (
    <div
      data-testid="awaiting-transmission"
      className={className}
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        overflow: "hidden",
        minHeight: 160,
        padding: 24,
        color: cssVar("ash"),
        background: cssVar("iron"),
        ...style,
      }}
    >
      <AssetKeyframes />
      {/* scanline sweep */}
      <div
        aria-hidden
        className="so-anim-scan"
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          height: "40%",
          background: `linear-gradient(180deg, transparent, ${PALETTE.phosphor}22, transparent)`,
          pointerEvents: "none",
        }}
      />
      <Favicon size={40} />
      <span
        style={{
          fontFamily: STENCIL_STACK,
          fontWeight: 700,
          fontSize: 22,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: cssVar("phosphor"),
        }}
      >
        {label}
      </span>
      {hint && (
        <span
          style={{
            fontFamily: '"Martian Mono", ui-monospace, monospace',
            fontSize: 11,
            letterSpacing: "0.04em",
            color: cssVar("ash"),
          }}
        >
          {hint}
        </span>
      )}
    </div>
  );
}
