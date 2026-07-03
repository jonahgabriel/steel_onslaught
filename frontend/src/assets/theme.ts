/**
 * Shared theme primitives for the PRESSURE DECK asset pack (Rev 2).
 *
 * Every asset is inline SVG, themable two ways:
 *   1. `currentColor` — inherits the parent's CSS `color`.
 *   2. `--so-side` custom property — the side (RED/BLUE) accent color, flowed
 *      in by the parent or set from the `side` prop via {@link sideStyle}.
 *
 * Palette values mirror the deck spec `:root` variables. SVG fills reference
 * the CSS var first with the hex as a fallback (`var(--phosphor, #FFB454)`),
 * so assets theme from the live deck when mounted inside it, and still render
 * correctly standalone (tests, storybook, favicon data URI).
 */
import type { CSSProperties } from "react";

/** Deck palette (mirror of the spec `:root` variables). */
export const PALETTE = {
  coal: "#0B0C0E",
  iron: "#16181D",
  seam: "#262A33",
  phosphor: "#FFB454",
  ember: "#FF5D40",
  arc: "#58B6FF",
  steam: "#E8E4DA",
  ash: "#8A8F98",
  danger: "#FF3B2F",
  vent: "#9BE8C9",
} as const;

/** `var(--name, fallback)` helper for embedding themeable colors in SVG. */
export function cssVar(name: keyof typeof PALETTE): string {
  return `var(--${name}, ${PALETTE[name]})`;
}

export type Side = "red" | "blue";

/** Side accent color — RED maps to `--ember`, BLUE maps to `--arc`. */
export const SIDE_COLOR: Record<Side, string> = {
  red: cssVar("ember"),
  blue: cssVar("arc"),
};

/** The custom-property name every asset reads for its side accent. */
export const SIDE_VAR = "--so-side";

/**
 * Build a style object that sets `--so-side` from a `side` prop (when given)
 * and merges any extra style. Assets read `var(--so-side, currentColor)`, so
 * omitting `side` falls back to the inherited `color`.
 */
export function sideStyle(side?: Side, extra?: CSSProperties): CSSProperties {
  const vars: Record<string, string | number> = {};
  if (side) vars[SIDE_VAR] = SIDE_COLOR[side];
  return { ...vars, ...extra } as CSSProperties;
}

/** The side accent, as referenced inside SVG geometry. */
export const SIDE_ACCENT = `var(${SIDE_VAR}, currentColor)`;

// ---------------------------------------------------------------------------
// Shared enums used across sprites / tracers / spec panels
// ---------------------------------------------------------------------------

export type ChassisClass = "light" | "medium" | "heavy";
export type MechState = "nominal" | "damaged" | "critical" | "destroyed";
export type WeaponClass = "light" | "medium" | "heavy" | "siege";

/** Chassis id → class, from `contracts_data/chassis/*.yaml`. */
export const CHASSIS_ID_TO_CLASS: Record<string, ChassisClass> = {
  "chassis.light.scout_mk1": "light",
  "chassis.medium.hunter_mk1": "medium",
  "chassis.heavy.ironclad_mk1": "heavy",
};

/** Human class chip label. */
export const CLASS_CHIP: Record<ChassisClass, string> = {
  light: "LIGHT",
  medium: "MEDIUM",
  heavy: "HEAVY",
};
