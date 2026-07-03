# PRESSURE DECK — event-native UI design spec

> **Status:** design locked (foreground, 2026-07-02); implementation
> dispatched to an Opus agent workflow. Companion to
> `2026-07-02-llm-pilot-plan.md` R6.
> **Operator brief:** "something cool where I can see actual events flowing."

## Concept

The interface IS the ledger. Steel Onslaught's runtime truth is an
append-only stream of ONEX envelopes — so the UI renders that stream as its
centerpiece instead of hiding it behind a game view. One committed aesthetic:

**Boiler-room mission control.** A flight-recorder deck for a steam-pressure
mech duel: coal-dark iron panels, amber phosphor data glow, military stencil
signage, steam-white prose for the LLM's thoughts. NOT neon cyberpunk, NOT
purple-gradient dashboard. The single memorable thing: **the Event River — a
living, causation-threaded stream of real envelopes you can watch think.**

## Visual system

Typography (Google Fonts `<link>` in `index.html`; no npm deps):

- Display / signage: **Big Shoulders Stencil** (weights 500/700) — hangar
  stencil for the header, section labels, filter chips.
- Event data / mono: **Martian Mono** (400/700) — every tick stamp, event
  type, payload figure. This font carries the deck's character.
- Prose / labels: **Archivo Narrow** (400/600) — rationale text, tooltips.

Palette (CSS variables on `:root`; dark theme only):

```css
--coal:     #0B0C0E;  /* page background */
--iron:     #16181D;  /* panels */
--seam:     #262A33;  /* borders, rules */
--phosphor: #FFB454;  /* amber — system/match events, primary accent */
--ember:    #FF5D40;  /* side RED attribution */
--arc:      #58B6FF;  /* side BLUE attribution */
--steam:    #E8E4DA;  /* body text, rationale */
--ash:      #8A8F98;  /* muted, timestamps */
--danger:   #FF3B2F;  /* rupture / destroyed / fallback glow */
--vent:     #9BE8C9;  /* venting / recovery accents */
```

Texture: a subtle CSS noise/grain overlay on `--coal` (SVG feTurbulence data
URI, ~3% opacity) and 1px double-rule borders on panels — riveted-plate
feel without images. Every panel corner carries a 45° notch (clip-path) —
the deck's signature detail.

## Layout (asymmetric, full viewport)

```
┌──────────────────────────────────────────────────────────────────┐
│ STEEL ONSLAUGHT ▮ match.01JX…  TICK ⟦ 0 4 7 ⟧  ▶ ∥ ×1 ×2 ×4     │ header
├────────────┬────────────────────────────────────┬───────────────┤
│  RED       │                                    │ ┌───────────┐ │
│  gauges    │        E V E N T   R I V E R       │ │  RADAR    │ │
│  ────────  │   (dominant column, ~55% width,    │ │  plotting │ │
│  pressure  │    causation gutter on the left)   │ │  table    │ │
│  heat      │                                    │ └───────────┘ │
│  armor     │   … flows downward, newest at      │   (overlaps   │
│  mode      │     bottom, autoscroll …           │    river hdr) │
│  BLUE      │                                    │  INSPECTOR    │
│  gauges    │                                    │  (drawer)     │
├────────────┴────────────────────────────────────┴───────────────┤
│ ⌸ COMBAT ⌸ DECISIONS ⌸ THERMAL ⌸ LLM ⌸ LIFECYCLE   214 events   │ ticker
└──────────────────────────────────────────────────────────────────┘
```

- **Header strip:** stencil wordmark; match id in mono; a rolling-digit
  tick odometer (CSS transform roll per digit); playback transport
  (play/pause/speed — drives nothing server-side; `so serve --tick-delay`
  paces the stream, the transport controls client-side buffering/step).
- **Left rail (~280px):** two mech stacks (RED above BLUE). Each: circular
  **boiler-pressure dial** (SVG needle, amber arc, red zone), heat bar,
  armor-pool bar (degrading pool → width + notch marks), mode chip
  (recon/assault/evasion), status lamp (alive / PILOT KILLED / DESTROYED).
  Restyle existing `HeatBar`/`PressureBar` logic; do not re-derive state —
  fold these from the same envelope subscription the board uses.
- **Event River (centerpiece):** see below.
- **Radar plotting table (top-right, overlapping the river's header —
  deliberate grid-break):** the existing `TacticalBoard` restyled to a
  miniature dark plotting grid: side-colored mech markers, fading movement
  trails (last ~8 positions), weapon-fire tracer lines animated on
  `weapon_fired`/`hit_resolved` (draw a line RED→BLUE grid cell, 250ms).
- **Bottom ticker:** filter chips as stencil toggles with live counts —
  COMBAT (weapon/hit/damage/armor), DECISIONS (`pilot_decision_made` +
  intents), THERMAL (boiler/heat/vent), LLM (evidence events), LIFECYCLE
  (match/spawn/victory/scored). Chips toggle river visibility per group.

## The Event River

Ordered by `(tick, sequence_in_tick)`, grouped under **tick separators**
(thin seam rule with the tick number in a mono tab). Newest at bottom;
autoscroll ON by default, paused by hover/manual scroll, with a floating
`LIVE ▼` chip to resume.

**Event row anatomy** (punch-card style, one line, ~40px):

```
│ 047.03  ◆ WEAPON_FIRED     mg.02 → mech.blue.01          RED │
```

- causation gutter (left, ~48px): SVG lane graph — threads connect each
  envelope to its `caused_by` parent, colored by originating side, drawn
  with stroke-dashoffset animation as rows appear. Hovering a row
  highlights its full ancestry chain (ancestors + descendants) and dims
  the rest of the river to 35% opacity.
- tick.seq stamp (mono, `--ash`), type glyph + name (mono; color by
  group: combat `--phosphor`, thermal `--vent`, danger events `--danger`),
  one-line payload summary (hand-written per event type — damage numbers,
  weapon ids, mode names; NEVER raw JSON in the row), side tag.

**Decision rows render expanded** (the star of the show):

```
│ 047.01  ◇ DECISION  mech.red.01  FIRE_WEAPON (mg.02)  conf ▮▮▮▮▯  RED │
│         “Enemy overcommitted to extreme proximity; firing machine       │
│          gun punishes their mistake.”                                   │
```

- rationale in `--steam` Archivo italic, quoted; absent for heuristic
  pilots (row stays single-line).
- confidence as 5-segment amber meter; `reason_code` chip; `LLM_FALLBACK`
  decisions get a `--danger` left border + "FALLBACK: <class>" chip.

**LLM evidence rows** — discriminated by `payload.kind ===
"llm_completion_requested" | "llm_completion_resolved"` (they piggyback on
existing telemetry event types; a pinned-member-set test FORBIDS adding new
`SOEventType` members — do not touch that enum). Render as a paired
bracket: REQUESTED shows provider/model + persona; RESOLVED shows latency
ms + `prompt_tokens`/`completion_tokens` (+ `cost_usd` when nonzero) as a
compact usage strip. While a request is unresolved, show a subtle amber
pulse on the bracket (the LLM is "thinking").

**Inspector drawer** (right, 380px, slides over): click any row → full
envelope JSON (mono, softly syntax-tinted: keys `--ash`, strings
`--steam`, numbers `--phosphor`), causation ancestry as a clickable list,
copy-JSON button. `Esc` closes. Generalize `DecisionInspector` into this
`EnvelopeInspector`; keep its tests passing or migrate them.

## Motion (CSS only — no motion libraries)

- Row entry: `opacity 0→1` + `translateY(8px)→0`, 180ms ease-out, 60ms
  stagger within a tick batch; type glyph gets a 2-frame phosphor flicker
  keyframe on entry.
- Causation threads draw in via stroke-dashoffset (240ms).
- `damage_applied`: 300ms edge-glow flash on the victim's side of the
  viewport (inset box-shadow pulse in side color). `boiler_ruptured` /
  `mech_destroyed`: steam burst — 6–8 CSS radial particles from the
  gauge rail + the row, plus the row itself gets a `--danger` glow.
- Odometer digits roll on tick change (transform translateY).
- `victory_declared`: the river dims, a stencil VICTORY banner stamps over
  the deck (scale 1.15→1, 300ms), winner in side color.
- Honor `prefers-reduced-motion: reduce` — disable entry animation,
  particles, and flashes (state changes remain instant + visible).

## Technical constraints (bind the implementation)

1. React 19 + Vite + TypeScript strict. **No new runtime npm deps** (fonts
   via `<link>`; SVG/CSS for everything). Vitest + Testing Library for
   tests; Biome clean; `npm run build` clean.
2. Reuse `lib/event_stream.ts` and `types.ts` `parseEnvelope` untouched in
   behavior; the parity test (`types_parity.test.ts`) must stay green. LLM
   evidence discrimination happens on `payload.kind`, never on new enum
   members.
3. Reuse the existing `subscribe` fan-out pattern in `App.tsx` (StrictMode
   double-mount safe). `TacticalBoard`, `HeatBar`, `PressureBar` are
   restyled/embedded, not re-derived; `DecisionInspector` →
   `EnvelopeInspector`.
4. All existing frontend tests stay green (62 passing today). New
   fixture-driven tests (fixtures under `__tests__/fixtures/` are the
   source of truth): river ordering by `(tick, sequence_in_tick)`; tick
   grouping; per-group filter toggles; decision row rationale +
   fallback rendering; LLM-evidence `payload.kind` discrimination +
   pairing; inspector opens with full envelope; ancestry highlight set
   computation (pure function — test it directly).
5. Causation graph: compute lanes/ancestry in a pure, unit-tested module
   (`lib/causation.ts`): `ancestryOf(eventId) → Set<eventId>` from the
   envelope `caused_by`/parent fields as they exist in `types.ts` — read
   the actual field names from the code, do not guess.
6. Works live against `so serve --ledger <path> --match <id> --tick-delay
   0.5` on `ws://127.0.0.1:8765`, and renders a complete recorded match
   correctly when frames arrive faster than paint (batch state updates per
   animation frame; do not setState per envelope).
7. Accessibility: AA contrast for all text on `--coal`/`--iron`;
   `aria-live="polite"` region announcing tick + latest decision; keyboard
   nav j/k rows, `f` cycles filter focus, `Esc` closes inspector; visible
   focus rings (amber).
8. Performance: a 200-tick match ≈ several thousand envelopes — virtualize
   or window the river (simple windowing is fine: render last N=400 rows +
   "…earlier events" loader); the causation gutter only draws visible rows.

## Acceptance (verify phase checks these)

- [ ] `npm ci && npm run build && npx vitest run` green; Biome clean.
- [ ] All pre-existing tests green, new tests cover the list in §constraints-4.
- [ ] Fixture replay renders: tick separators, expanded decision rows with
      rationale, LLM evidence pairing, filters, inspector, gauges.
- [ ] Reduced-motion honored (test via `matchMedia` mock).
- [ ] No new runtime deps in `package.json` dependencies.
- [ ] Visual: dark boiler-deck aesthetic per this spec — stencil display
      font, Martian Mono data, amber phosphor + side colors, notched
      panels, grain overlay. No purple gradients, no default fonts.
