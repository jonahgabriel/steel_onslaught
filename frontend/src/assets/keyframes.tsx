/**
 * Self-contained CSS motion for the asset pack.
 *
 * Animations ship as an inline `<style>` element rendered by the assets that
 * need them (via {@link AssetKeyframes}). This keeps every asset a single
 * import — no external stylesheet the layout agent must remember to include —
 * and works under jsdom (no CSS pipeline required).
 *
 * All animation is wrapped in `@media (prefers-reduced-motion: no-preference)`:
 * reduced-motion is the safe default — motion applies ONLY when the user has
 * expressed no preference. Static state (glow color, muzzle, steam) still
 * renders; it simply does not animate.
 *
 * Keyframe + class names are namespaced `so-` to avoid colliding with deck.css.
 */
import type { JSX } from "react";

export const ASSET_KEYFRAME_CSS = `
@keyframes so-crit-pulse { 0%,100% { opacity: .18 } 50% { opacity: .62 } }
@keyframes so-muzzle-flk { 0% { opacity: 1 } 100% { opacity: .5 } }
@keyframes so-vent-puff  { 0% { opacity: .75 } 70% { opacity: .18 } 100% { opacity: 0 } }
@keyframes so-tracer-dash { to { stroke-dashoffset: 0 } }
@keyframes so-scan-sweep  { 0% { transform: translateY(-100%) } 100% { transform: translateY(220%) } }
@media (prefers-reduced-motion: no-preference) {
  .so-anim-crit   { animation: so-crit-pulse 1.15s ease-in-out infinite; }
  .so-anim-muzzle { animation: so-muzzle-flk 0.16s steps(2) infinite; }
  .so-anim-vent   { animation: so-vent-puff 1.6s ease-out infinite; }
  .so-anim-tracer { animation: so-tracer-dash 0.25s ease-out both; }
  .so-anim-scan   { animation: so-scan-sweep 2.4s linear infinite; }
}
`.trim();

/** Inline `<style>` carrying the asset-pack keyframes. Idempotent to repeat. */
export function AssetKeyframes(): JSX.Element {
  // biome-ignore lint/security/noDangerouslySetInnerHtml: static, non-user CSS.
  return <style data-so-keyframes="" dangerouslySetInnerHTML={{ __html: ASSET_KEYFRAME_CSS }} />;
}
