/**
 * PRESSURE DECK asset pack (Rev 2) — single barrel export.
 *
 * Everything the layout agent consumes is re-exported here. See the API table
 * in the handoff report. All assets are inline React SVG, themable via
 * `currentColor` and the `--so-side` custom property (see {@link sideStyle}).
 */

// Deck furniture
export { CardFace } from "./cards";
export {
  AwaitingTransmission,
  type AwaitingTransmissionProps,
  Favicon,
  type FaviconProps,
  faviconDataUri,
  Wordmark,
  type WordmarkProps,
} from "./furniture";
// Glyphs
export {
  GLYPHS,
  GlyphArmor,
  GlyphAssault,
  GlyphDamage,
  GlyphDeath,
  GlyphDecision,
  GlyphEvasion,
  GlyphFire,
  GlyphHeat,
  GlyphHit,
  GlyphLifecycle,
  GlyphLlm,
  GlyphMode,
  type GlyphProps,
  GlyphRecon,
  GlyphVent,
  GlyphWeaponHeavy,
  GlyphWeaponLight,
  GlyphWeaponMedium,
  GlyphWeaponSiege,
  LampCooldown,
  LampNominal,
  type LampProps,
  LampReady,
  LampSkull,
  LampWreck,
  MODE_GLYPH,
  WEAPON_CLASS_GLYPH,
} from "./glyphs";
// Motion
export { ASSET_KEYFRAME_CSS, AssetKeyframes } from "./keyframes";
// Chassis sprites
export { ChassisSprite, type ChassisSpriteDispatchProps } from "./sprites/ChassisSprite";
export type { ChassisSpriteProps } from "./sprites/parts";
export { SpriteHunter } from "./sprites/SpriteHunter";
export { SpriteIronclad } from "./sprites/SpriteIronclad";
export { SpriteScout } from "./sprites/SpriteScout";
// Weapon tracers
export { type Coord, Tracer, type TracerProps } from "./Tracer";
// Theme + shared enums / helpers
export {
  CHASSIS_ID_TO_CLASS,
  type ChassisClass,
  CLASS_CHIP,
  cssVar,
  type MechState,
  PALETTE,
  SIDE_ACCENT,
  SIDE_COLOR,
  SIDE_VAR,
  type Side,
  sideStyle,
  type WeaponClass,
} from "./theme";
