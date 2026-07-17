/**
 * Glyph set — 12–16px mono-line icons for the deck.
 *
 * Every glyph is a 16×16 viewBox, `stroke: currentColor`, 1.5 stroke — so it
 * inherits color from its row/chip. Status lamps carry semantic fills but stay
 * overridable via `color`. Each renders `data-testid="glyph-<name>"`.
 *
 * Families: mode (recon/assault/evasion) · weapon-class (light/medium/heavy/
 * siege) · river event-type (fire/hit/damage/armor/heat/vent/mode/decision/
 * llm/lifecycle/death) · status lamps (nominal/skull/wreck) · ready/cooldown.
 */
import type { JSX, ReactNode } from "react";
import { cssVar } from "./theme";

export interface GlyphProps {
  size?: number;
  title?: string;
  className?: string;
}

function Glyph({
  name,
  title,
  size = 14,
  className,
  children,
  fill = false,
}: GlyphProps & { name: string; children: ReactNode; fill?: boolean }): JSX.Element {
  return (
    <svg
      data-testid={`glyph-${name}`}
      data-glyph={name}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      role="img"
      aria-label={title ?? name}
      fill={fill ? "currentColor" : "none"}
      stroke={fill ? "none" : "currentColor"}
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <title>{title ?? name}</title>
      {children}
    </svg>
  );
}

// ---- mode glyphs ----------------------------------------------------------

export const GlyphRecon = (p: GlyphProps): JSX.Element => (
  <Glyph name="recon" title="recon" {...p}>
    <path d="M1.5 8 C4 4 12 4 14.5 8 C12 12 4 12 1.5 8 Z" />
    <circle cx={8} cy={8} r={2} />
  </Glyph>
);

export const GlyphAssault = (p: GlyphProps): JSX.Element => (
  <Glyph name="assault" title="assault" {...p}>
    <circle cx={8} cy={8} r={5} />
    <path d="M8 1 V4 M8 12 V15 M1 8 H4 M12 8 H15" />
  </Glyph>
);

export const GlyphEvasion = (p: GlyphProps): JSX.Element => (
  <Glyph name="evasion" title="evasion" {...p}>
    <path d="M3 5 L8 9 L13 5 M3 9 L8 13 L13 9" />
  </Glyph>
);

// ---- weapon-class glyphs --------------------------------------------------

export const GlyphWeaponLight = (p: GlyphProps): JSX.Element => (
  <Glyph name="weapon-light" title="light weapon" {...p}>
    <path d="M2 8 H14" strokeDasharray="2 1.5" />
    <path d="M11 5 L14 8 L11 11" />
  </Glyph>
);

export const GlyphWeaponMedium = (p: GlyphProps): JSX.Element => (
  <Glyph name="weapon-medium" title="medium weapon" {...p}>
    <path d="M2 8 H13" strokeWidth={2.4} />
    <path d="M13 5 L15 8 L13 11" />
  </Glyph>
);

export const GlyphWeaponHeavy = (p: GlyphProps): JSX.Element => (
  <Glyph name="weapon-heavy" title="heavy weapon" {...p}>
    <path d="M2 8 H11" strokeWidth={2.6} />
    <path d="M11 4 L15 8 L11 12 M11 8 H8" />
  </Glyph>
);

export const GlyphWeaponSiege = (p: GlyphProps): JSX.Element => (
  <Glyph name="weapon-siege" title="siege weapon" {...p}>
    <path d="M2 13 Q8 1 14 13" strokeDasharray="2.5 2" />
    <circle cx={14} cy={13} r={1.5} />
  </Glyph>
);

// ---- river event-type glyphs ----------------------------------------------

export const GlyphFire = (p: GlyphProps): JSX.Element => (
  <Glyph name="fire" title="weapon fired" {...p}>
    <path d="M8 2 C5 6 6 8 8 9 C10 8 11 6 8 2 Z" />
    <path d="M8 9 C6.5 10 6 12 8 14 C10 12 9.5 10 8 9 Z" />
  </Glyph>
);

export const GlyphHit = (p: GlyphProps): JSX.Element => (
  <Glyph name="hit" title="hit resolved" {...p}>
    <circle cx={8} cy={8} r={5} />
    <path d="M8 3 V8 L11 10" />
  </Glyph>
);

export const GlyphDamage = (p: GlyphProps): JSX.Element => (
  <Glyph name="damage" title="damage applied" {...p}>
    <path d="M8 1 L10 6 L15 6 L11 9 L13 14 L8 11 L3 14 L5 9 L1 6 L6 6 Z" />
  </Glyph>
);

export const GlyphArmor = (p: GlyphProps): JSX.Element => (
  <Glyph name="armor" title="armor absorbed" {...p}>
    <path d="M8 1 L14 4 V8 C14 12 11 14 8 15 C5 14 2 12 2 8 V4 Z" />
  </Glyph>
);

export const GlyphHeat = (p: GlyphProps): JSX.Element => (
  <Glyph name="heat" title="heat" {...p}>
    <path d="M6 2 V9 M6 9 A2.5 3 0 1 0 6 9.1 Z" />
    <path d="M10 3 C9 4 11 5 10 6 M13 3 C12 4 14 5 13 6" />
  </Glyph>
);

export const GlyphVent = (p: GlyphProps): JSX.Element => (
  <Glyph name="vent" title="vent" {...p}>
    <path d="M4 13 C4 9 8 10 8 7 C8 4 6 4 6 2" />
    <path d="M9 13 C9 9 13 10 13 7 C13 5 11.5 5 11.5 3" />
  </Glyph>
);

export const GlyphMode = (p: GlyphProps): JSX.Element => (
  <Glyph name="mode" title="mode" {...p}>
    <circle cx={8} cy={8} r={2.2} />
    <path d="M8 1 V3 M8 13 V15 M1 8 H3 M13 8 H15 M3.5 3.5 L5 5 M11 11 L12.5 12.5 M12.5 3.5 L11 5 M5 11 L3.5 12.5" />
  </Glyph>
);

export const GlyphDecision = (p: GlyphProps): JSX.Element => (
  <Glyph name="decision" title="decision" {...p}>
    <path d="M8 2 L14 8 L8 14 L2 8 Z" />
  </Glyph>
);

export const GlyphLlm = (p: GlyphProps): JSX.Element => (
  <Glyph name="llm" title="llm evidence" {...p}>
    <rect x={3} y={4} width={10} height={8} rx={2} />
    <path d="M6 8 H6.01 M10 8 H10.01" strokeWidth={2} />
    <path d="M8 2 V4" />
  </Glyph>
);

export const GlyphLifecycle = (p: GlyphProps): JSX.Element => (
  <Glyph name="lifecycle" title="lifecycle" {...p}>
    <path d="M13 8 A5 5 0 1 1 11 4" />
    <path d="M11 1 V4 H8" />
  </Glyph>
);

export const GlyphDeath = (p: GlyphProps): JSX.Element => (
  <Glyph name="death" title="destroyed" {...p}>
    <path d="M8 1 C4 1 2 4 2 7 C2 9 3 10 4 11 V13 H12 V11 C13 10 14 9 14 7 C14 4 12 1 8 1 Z" />
    <path d="M6 7 H6.01 M10 7 H10.01" strokeWidth={2} />
  </Glyph>
);

// ---- status lamps ---------------------------------------------------------

export interface LampProps extends GlyphProps {
  /** Override the lamp fill (defaults to the semantic color). */
  color?: string;
}

export const LampNominal = ({ color, ...p }: LampProps): JSX.Element => (
  <Glyph name="lamp-nominal" title="nominal" fill {...p}>
    <circle cx={8} cy={8} r={4} fill={color ?? cssVar("vent")} />
  </Glyph>
);

export const LampSkull = ({ color, ...p }: LampProps): JSX.Element => (
  <Glyph name="lamp-skull" title="pilot killed" fill {...p}>
    <path
      d="M8 2 C4.5 2 3 4.5 3 7 C3 8.5 4 9.5 5 10 V12 H11 V10 C12 9.5 13 8.5 13 7 C13 4.5 11.5 2 8 2 Z"
      fill={color ?? cssVar("ash")}
    />
    <circle cx={6} cy={7} r={1.1} fill={cssVar("coal")} />
    <circle cx={10} cy={7} r={1.1} fill={cssVar("coal")} />
  </Glyph>
);

export const LampWreck = ({ color, ...p }: LampProps): JSX.Element => (
  <Glyph name="lamp-wreck" title="destroyed" {...p}>
    <path
      d="M2 13 L5 6 L8 10 L11 5 L14 13 Z"
      fill={color ?? cssVar("danger")}
      stroke={color ?? cssVar("danger")}
    />
  </Glyph>
);

export const LampReady = ({ color, ...p }: LampProps): JSX.Element => (
  <Glyph name="lamp-ready" title="ready" fill {...p}>
    <circle cx={8} cy={8} r={4} fill={color ?? cssVar("vent")} />
    <path d="M6 8 L7.5 9.5 L10 6" stroke={cssVar("coal")} strokeWidth={1.4} fill="none" />
  </Glyph>
);

export const LampCooldown = ({ color, ...p }: LampProps): JSX.Element => (
  <Glyph name="lamp-cooldown" title="cooldown" {...p}>
    <circle cx={8} cy={8} r={5} stroke={color ?? cssVar("phosphor")} />
    <path d="M8 5 V8 L10 9.5" stroke={color ?? cssVar("phosphor")} />
  </Glyph>
);

// ---- registries -----------------------------------------------------------

/** Every glyph by its short name — handy for data-driven river/spec rendering. */
export const GLYPHS: Record<string, (p: GlyphProps) => JSX.Element> = {
  recon: GlyphRecon,
  assault: GlyphAssault,
  evasion: GlyphEvasion,
  "weapon-light": GlyphWeaponLight,
  "weapon-medium": GlyphWeaponMedium,
  "weapon-heavy": GlyphWeaponHeavy,
  "weapon-siege": GlyphWeaponSiege,
  fire: GlyphFire,
  hit: GlyphHit,
  damage: GlyphDamage,
  armor: GlyphArmor,
  heat: GlyphHeat,
  vent: GlyphVent,
  mode: GlyphMode,
  decision: GlyphDecision,
  llm: GlyphLlm,
  lifecycle: GlyphLifecycle,
  death: GlyphDeath,
};

/** Weapon class → its class glyph. */
export const WEAPON_CLASS_GLYPH = {
  light: GlyphWeaponLight,
  medium: GlyphWeaponMedium,
  heavy: GlyphWeaponHeavy,
  siege: GlyphWeaponSiege,
} as const;

/** Pilot mode → its mode glyph. */
export const MODE_GLYPH = {
  recon: GlyphRecon,
  assault: GlyphAssault,
  evasion: GlyphEvasion,
} as const;
