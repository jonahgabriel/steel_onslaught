/**
 * Weapon-class inference — PRESSURE DECK.
 *
 * Weapon ids arrive as `module.weapon.<name>` strings on `weapon_fired` and in
 * `weapon_cooldowns`; the wire carries no explicit `weapon_class`. This pure
 * lookup maps a weapon id to the class the arena tracer + spec-panel glyph use,
 * following the asset-pack class grouping (SPEC Rev 2 §"Weapon tracer styles").
 */
import type { WeaponClass } from "../assets/theme";

/** Keyword → class, checked in order against the weapon id substring. */
const WEAPON_CLASS_BY_KEYWORD: ReadonlyArray<readonly [string, WeaponClass]> = [
  ["machine_gun", "light"],
  ["shrapnel_thrower", "light"],
  ["steam_cannon", "medium"],
  ["heat_lance", "medium"],
  ["harpoon_gun", "heavy"],
  ["artillery_mortar", "siege"],
];

/** The weapon class for a weapon id (defaults to `light` for unknown ids). */
export function weaponClassOf(weaponId: string): WeaponClass {
  for (const [keyword, cls] of WEAPON_CLASS_BY_KEYWORD) {
    if (weaponId.includes(keyword)) return cls;
  }
  return "light";
}

/** A short, human weapon label — the last dotted segment (`machine_gun`). */
export function weaponLabel(weaponId: string): string {
  const dot = weaponId.lastIndexOf(".");
  return dot === -1 ? weaponId : weaponId.slice(dot + 1);
}
