/**
 * ArenaView — PRESSURE DECK centerpiece (Rev 2, evolved from TacticalBoard).
 *
 * The arena contract's plotting grid, scaled up into the dominant, square
 * center arena. The grid dimension is ALWAYS the authoritative
 * `match_started.payload.arena.size` — the demo runs `foundry_60` at 60×60, and
 * no dimension is assumed before that envelope arrives.
 * A pure projection of the event stream (never POSTs / fetches): it folds the
 * same `subscribe` fan-out the deck uses into chassis sprites (facing, damage
 * state, venting, firing), fading movement trails, per-weapon-class tracers
 * (weapon_fired → hit_resolved), armor-absorb shimmers, wreck + steam burst on
 * destruction, and range rings around the selected mech.
 *
 * Timing (TTL, purely visual — not game ticks) drives the transient overlays;
 * an interval expires them and forces the fade-out re-render.
 */
import type React from "react";
import { useEffect, useReducer } from "react";
import { ChassisSprite, Tracer } from "../assets";
import type { WeaponClass } from "../assets/theme";
import type { EnvelopeHandler } from "../lib/event_stream";
import { displayNameOf, mechStateOf } from "../lib/gauges";
import { weaponClassOf } from "../lib/weapons";
import type { SOArenaObjective, SOEventEnvelope, SOMechRuntimeState, SOPosition } from "../types";

/**
 * Grid dimension used ONLY before `match_started` arrives — an empty holding
 * frame with nothing plotted on it, never an arena default. The authoritative
 * dimension is the arena contract's `size` carried on MATCH_STARTED
 * (`payload.arena.size`), which replaces this on the first envelope. Nothing
 * may derive a coordinate, bound or assertion from this constant.
 */
export const PLACEHOLDER_GRID_CELLS = 40;
/** Minor grid lines every 2 cells (subtle) — keyed by coordinate, not index. */
const minorLines = (cells: number): number[] =>
  Array.from({ length: Math.floor(cells / 2) + 1 }, (_, i) => i * 2);
/** Sector marks every 8 cells (brighter) — the readable coarse grid. */
const sectorLines = (cells: number): number[] =>
  Array.from({ length: Math.floor(cells / 8) + 1 }, (_, i) => i * 8);
const TRAIL_MAX = 8;
const TRACER_TTL_MS = 700;
const FIRING_TTL_MS = 420;
const VENT_TTL_MS = 900;
const SHIMMER_TTL_MS = 520;
/** Movement breadcrumbs are transient visual overlays, not durable state. */
const TRAIL_TTL_MS = 2400;

interface ArenaMech {
  mechId: string;
  playerId: string;
  side: SOMechRuntimeState["side"];
  chassisClass: "light" | "medium" | "heavy";
  position: SOPosition;
  facing: number;
  hp: number;
  hpMax: number;
  alive: boolean;
  firingUntil: number;
  ventingUntil: number;
}

interface ArenaTracer {
  id: string;
  /** Subject identity is authoritative; positions may be co-located. */
  attackerPlayerId: string;
  attackerSide: SOMechRuntimeState["side"];
  from: SOPosition;
  to: SOPosition;
  weaponClass: WeaponClass;
  expiresAt: number;
  impact: boolean;
}

interface Shimmer {
  id: string;
  position: SOPosition;
  expiresAt: number;
}

interface TrailPoint {
  position: SOPosition;
  expiresAt: number;
}

export interface ArenaState {
  mechs: Record<string, ArenaMech>;
  /** Static obstacle cells carried by the authoritative arena snapshot. */
  obstacles: SOPosition[];
  /** Objective cells carried by the authoritative arena snapshot (Phase 4). */
  objectives: SOArenaObjective[];
  /** VP finish line from the arena contract; null on objective-free arenas. */
  vpThreshold: number | null;
  /** Latest cumulative VP per player (from objective_scored). */
  vpTotals: Record<string, number>;
  /** Grid dimension from the arena contract (`arena.size`). */
  gridCells: number;
  trails: Record<string, TrailPoint[]>;
  tracers: ArenaTracer[];
  shimmers: Shimmer[];
  victoryWinnerId: string | null;
  /** End reason for a terminal match with no winner (draw). */
  drawReason: string | null;
  selectedMechId: string | null;
  revision: number;
}

export const ARENA_INITIAL_STATE: ArenaState = {
  mechs: {},
  obstacles: [],
  objectives: [],
  vpThreshold: null,
  vpTotals: {},
  gridCells: PLACEHOLDER_GRID_CELLS,
  trails: {},
  tracers: [],
  shimmers: [],
  victoryWinnerId: null,
  drawReason: null,
  selectedMechId: null,
  revision: 0,
};

type ArenaAction =
  | { type: "ENVELOPE"; envelope: SOEventEnvelope }
  | { type: "EXPIRE" }
  | { type: "SELECT"; mechId: string };

function mechFromRuntime(state: SOMechRuntimeState): ArenaMech {
  return {
    mechId: state.mech_id,
    playerId: state.player_id,
    side: state.side,
    chassisClass: state.chassis_class,
    position: state.position,
    facing: state.facing,
    hp: state.hp,
    hpMax: state.hp_max,
    alive: state.alive,
    firingUntil: 0,
    ventingUntil: 0,
  };
}

/** Degrees clockwise from nose-up (−y) pointing from `a` toward `b`. */
function facingToward(a: SOPosition, b: SOPosition): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (dx === 0 && dy === 0) return 0;
  const deg = (Math.atan2(dx, -dy) * 180) / Math.PI;
  return (deg + 360) % 360;
}

export function arenaReduce(state: ArenaState, action: ArenaAction): ArenaState {
  if (action.type === "SELECT") {
    return {
      ...state,
      selectedMechId: state.selectedMechId === action.mechId ? null : action.mechId,
    };
  }

  if (action.type === "EXPIRE") {
    const now = Date.now();
    const tracers = state.tracers.filter((t) => t.expiresAt > now);
    const shimmers = state.shimmers.filter((s) => s.expiresAt > now);
    const trails: Record<string, TrailPoint[]> = {};
    for (const [mechId, points] of Object.entries(state.trails)) {
      const live = points.filter((point) => point.expiresAt > now);
      if (live.length > 0) trails[mechId] = live;
    }
    return { ...state, tracers, shimmers, trails, revision: state.revision + 1 };
  }

  const { envelope } = action;
  const now = Date.now();

  switch (envelope.event_type) {
    case "match_started": {
      const mechs: Record<string, ArenaMech> = {};
      for (const m of envelope.payload.mechs) mechs[m.mech_id] = mechFromRuntime(m);
      const obstacles = envelope.payload.arena.obstacles;
      const gridCells = envelope.payload.arena.size;
      return {
        ...ARENA_INITIAL_STATE,
        mechs,
        obstacles,
        gridCells,
        objectives: envelope.payload.arena.objectives,
        vpThreshold: envelope.payload.arena.vp_threshold,
      };
    }

    case "objective_scored":
      return { ...state, vpTotals: { ...envelope.payload.cumulative_vp } };

    case "movement_resolved": {
      const mech = state.mechs[envelope.subject.mech_id];
      if (mech === undefined) return state;
      const { to } = envelope.payload;
      const prevTrail = state.trails[mech.mechId] ?? [];
      const trail = [
        ...prevTrail,
        { position: mech.position, expiresAt: now + TRAIL_TTL_MS },
      ].slice(-TRAIL_MAX);
      return {
        ...state,
        mechs: {
          ...state.mechs,
          [mech.mechId]: { ...mech, position: to, facing: facingToward(mech.position, to) },
        },
        trails: { ...state.trails, [mech.mechId]: trail },
      };
    }

    case "weapon_fired": {
      const attacker = state.mechs[envelope.subject.mech_id];
      const target = state.mechs[envelope.payload.target_id];
      if (attacker === undefined || target === undefined) return state;
      const tracer: ArenaTracer = {
        id: envelope.event_id,
        attackerPlayerId: attacker.playerId,
        attackerSide: attacker.side,
        from: attacker.position,
        to: target.position,
        weaponClass: weaponClassOf(envelope.payload.weapon_id),
        expiresAt: now + TRACER_TTL_MS,
        impact: false,
      };
      return {
        ...state,
        tracers: [...state.tracers, tracer],
        mechs: {
          ...state.mechs,
          [attacker.mechId]: {
            ...attacker,
            firingUntil: now + FIRING_TTL_MS,
            facing: facingToward(attacker.position, target.position),
          },
        },
      };
    }

    case "hit_resolved": {
      if (!envelope.payload.result.hit) return state;
      const defenderId = envelope.payload.defender_id;
      const tracers = state.tracers.map((t) =>
        t.to.x === state.mechs[defenderId]?.position.x &&
        t.to.y === state.mechs[defenderId]?.position.y
          ? { ...t, impact: true }
          : t,
      );
      return { ...state, tracers };
    }

    case "damage_applied": {
      const mech = state.mechs[envelope.payload.target_id];
      if (mech === undefined) return state;
      return {
        ...state,
        mechs: { ...state.mechs, [mech.mechId]: { ...mech, hp: envelope.payload.hp_after } },
      };
    }

    case "armor_absorbed": {
      const target = state.mechs[envelope.payload.target_id];
      if (target === undefined) return state;
      const shimmer: Shimmer = {
        id: envelope.event_id,
        position: target.position,
        expiresAt: now + SHIMMER_TTL_MS,
      };
      return { ...state, shimmers: [...state.shimmers, shimmer] };
    }

    case "vent_intent": {
      const mech = state.mechs[envelope.subject.mech_id];
      if (mech === undefined) return state;
      return {
        ...state,
        mechs: {
          ...state.mechs,
          [mech.mechId]: { ...mech, ventingUntil: now + VENT_TTL_MS },
        },
      };
    }

    case "mech_destroyed": {
      const mech = state.mechs[envelope.subject.mech_id];
      if (mech === undefined) return state;
      return {
        ...state,
        mechs: { ...state.mechs, [mech.mechId]: { ...mech, alive: false } },
      };
    }

    case "victory_declared":
      return {
        ...state,
        victoryWinnerId: envelope.payload.winner_player_id,
        trails: {},
        tracers: [],
        shimmers: [],
      };

    case "match_ended":
      // Decisive endings are already represented by victory_declared. The
      // terminal envelope is still authoritative for a no-winner draw.
      if (envelope.payload.winner_id === null) {
        return {
          ...state,
          drawReason: envelope.payload.reason,
          trails: {},
          tracers: [],
          shimmers: [],
        };
      }
      return { ...state, trails: {}, tracers: [], shimmers: [] };

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------

/** Center of `cell` as a percentage of the arena square, on a `cells` grid. */
const pctOf = (cell: number, cells: number): string => `${((cell + 0.5) / cells) * 100}%`;

// --- sprite scale + de-overlap ---------------------------------------------

/** Sprite footprint in grid cells — the unit box spans this many cells. */
const SPRITE_FOOTPRINT_CELLS = 4;
/** Legibility floor for the unit box (% of the arena square). */
const SPRITE_FLOOR_PCT = 6;
/** Pair de-overlap applies at Chebyshev distance <= this (cells). */
const PAIR_RANGE_CELLS = 2;
/** Co-celled pair offset (% of the unit's own box), tapering with distance. */
const PAIR_OFFSET_PCT = 40;
const PAIR_OFFSET_TAPER_PCT = 10;
/** Paired sprites shrink to this scale so the pair reads as two silhouettes. */
const PAIR_SCALE = 0.85;

/**
 * Unit-box side length (% of the arena square). Sprites track the cell scale
 * (a fixed {@link SPRITE_FOOTPRINT_CELLS}-cell footprint — 10% on the classic
 * 40 grid, unchanged) with a floor so they stay legible on huge grids.
 */
export function spriteSizePct(gridCells: number): number {
  return Math.max((SPRITE_FOOTPRINT_CELLS / gridCells) * 100, SPRITE_FLOOR_PCT);
}

export interface SpriteOffset {
  /** Nudge along the pair-separation axis, % of the unit's OWN box. */
  dx: number;
  dy: number;
  /** True when this sprite is being de-overlapped against a neighbor. */
  paired: boolean;
}

/** The minimal shape {@link spriteOffsets} needs — every ArenaMech qualifies. */
export interface SpriteAnchor {
  mechId: string;
  position: SOPosition;
}

/**
 * De-overlap for adjacent / co-located sprites. Mechs legally clamber through
 * cover cells and each other's neighborhoods, so two units within
 * {@link PAIR_RANGE_CELLS} Chebyshev get nudged apart along their separation
 * axis (a fixed diagonal when co-celled, keyed by mech-id order so it is
 * deterministic). Offsets are in percent of the sprite's own box — cell-sized
 * nudges would be invisible at sprite scale. The TRUE cell stays inferable via
 * the always-on cell-anchor outline drawn in the grid layer.
 */
export function spriteOffsets(mechs: readonly SpriteAnchor[]): Record<string, SpriteOffset> {
  const result: Record<string, SpriteOffset> = {};
  for (const m of mechs) result[m.mechId] = { dx: 0, dy: 0, paired: false };
  const ordered = [...mechs].sort((a, b) => a.mechId.localeCompare(b.mechId));
  for (let i = 0; i < ordered.length; i += 1) {
    for (let j = i + 1; j < ordered.length; j += 1) {
      const a = ordered[i];
      const b = ordered[j];
      if (a === undefined || b === undefined) continue;
      const ddx = b.position.x - a.position.x;
      const ddy = b.position.y - a.position.y;
      const cheb = Math.max(Math.abs(ddx), Math.abs(ddy));
      if (cheb > PAIR_RANGE_CELLS) continue;
      let ux = Math.SQRT1_2;
      let uy = Math.SQRT1_2;
      if (ddx !== 0 || ddy !== 0) {
        const len = Math.hypot(ddx, ddy);
        ux = ddx / len;
        uy = ddy / len;
      }
      const magnitude = PAIR_OFFSET_PCT - PAIR_OFFSET_TAPER_PCT * cheb;
      const ra = result[a.mechId];
      const rb = result[b.mechId];
      if (ra !== undefined) {
        ra.dx -= ux * magnitude;
        ra.dy -= uy * magnitude;
        ra.paired = true;
      }
      if (rb !== undefined) {
        rb.dx += ux * magnitude;
        rb.dy += uy * magnitude;
        rb.paired = true;
      }
    }
  }
  return result;
}

export interface SpritePlacement {
  /** Final visual center, % of the arena square. */
  left: number;
  top: number;
  paired: boolean;
}

/**
 * Final sprite centers in arena-% space: cell center + the pair nudge from
 * {@link spriteOffsets}, with EDGE HANDLING — a nudge near the border must not
 * push a sprite off the board (verified live: a corner-adjacent pair clipped
 * the outer sprite). Each pair is shifted RIGIDLY back inside the arena
 * (preserving its separation, unlike per-sprite clamping which would re-merge
 * the blob), then hard-clamped as a safety net. Unpaired sprites always sit
 * exactly on their true cell center.
 */
export function spritePlacements(
  mechs: readonly SpriteAnchor[],
  gridCells: number,
): Record<string, SpritePlacement> {
  const unit = spriteSizePct(gridCells);
  const offsets = spriteOffsets(mechs);
  const result: Record<string, SpritePlacement> = {};
  for (const m of mechs) {
    const o = offsets[m.mechId] ?? { dx: 0, dy: 0, paired: false };
    result[m.mechId] = {
      left: ((m.position.x + 0.5) / gridCells) * 100 + (o.dx / 100) * unit,
      top: ((m.position.y + 0.5) / gridCells) * 100 + (o.dy / 100) * unit,
      paired: o.paired,
    };
  }
  const half = (unit * PAIR_SCALE) / 2;
  const lo = half;
  const hi = 100 - half;
  const overhang = (v: number) => (v < lo ? lo - v : v > hi ? hi - v : 0);
  const ordered = [...mechs].sort((a, b) => a.mechId.localeCompare(b.mechId));
  for (let i = 0; i < ordered.length; i += 1) {
    for (let j = i + 1; j < ordered.length; j += 1) {
      const a = ordered[i];
      const b = ordered[j];
      if (a === undefined || b === undefined) continue;
      const cheb = Math.max(
        Math.abs(b.position.x - a.position.x),
        Math.abs(b.position.y - a.position.y),
      );
      if (cheb > PAIR_RANGE_CELLS) continue;
      const pa = result[a.mechId];
      const pb = result[b.mechId];
      if (pa === undefined || pb === undefined) continue;
      const shiftX = overhang(pa.left) + overhang(pb.left);
      const shiftY = overhang(pa.top) + overhang(pb.top);
      pa.left += shiftX;
      pb.left += shiftX;
      pa.top += shiftY;
      pb.top += shiftY;
    }
  }
  for (const p of Object.values(result)) {
    if (!p.paired) continue;
    p.left = Math.min(Math.max(p.left, lo), hi);
    p.top = Math.min(Math.max(p.top, lo), hi);
  }
  return result;
}

/** Obstacle-block inset from the cell edge (grid units). */
const OBSTACLE_INSET = 0.08;
/** Corner-notch depth (grid units) — the asset-pack signature plate cut. */
const OBSTACLE_NOTCH = 0.22;

/**
 * Notched iron-block outline for the obstacle cell whose top-left is (x, y),
 * in grid coordinates (1 unit = 1 cell). Mirrors the favicon signature plate
 * (`M3 3 H23 L29 9 V29 H9 L3 23 Z`): a square with two opposite corners cut.
 */
function obstaclePath(x: number, y: number): string {
  const left = x + OBSTACLE_INSET;
  const right = x + 1 - OBSTACLE_INSET;
  const top = y + OBSTACLE_INSET;
  const bottom = y + 1 - OBSTACLE_INSET;
  return (
    `M${left} ${top} H${right - OBSTACLE_NOTCH} L${right} ${top + OBSTACLE_NOTCH} ` +
    `V${bottom} H${left + OBSTACLE_NOTCH} L${left} ${bottom - OBSTACLE_NOTCH} Z`
  );
}

function SteamBurst({ mechId }: { mechId: string }): React.JSX.Element {
  return (
    <span className="pd-arena-burst" data-testid={`arena-wreck-${mechId}`} aria-hidden="true">
      {Array.from({ length: 7 }, (_, i) => {
        const angle = (i / 7) * Math.PI * 2;
        return (
          <span
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed 7-particle burst, positional
            key={i}
            className="pd-arena-particle"
            style={
              {
                "--dx": `${Math.cos(angle) * 26}px`,
                "--dy": `${Math.sin(angle) * 26}px`,
              } as React.CSSProperties
            }
          />
        );
      })}
    </span>
  );
}

export interface ArenaViewProps {
  /** Injected from EventStream.subscribe — allows test-stub injection. */
  subscribe: (handler: EnvelopeHandler) => () => void;
}

export default function ArenaView({ subscribe }: ArenaViewProps): React.JSX.Element {
  const [state, dispatch] = useReducer(arenaReduce, ARENA_INITIAL_STATE);

  useEffect(() => {
    const unsubscribe = subscribe((envelope) => dispatch({ type: "ENVELOPE", envelope }));
    return unsubscribe;
  }, [subscribe]);

  const now = Date.now();
  const animating =
    state.tracers.length > 0 ||
    state.shimmers.length > 0 ||
    Object.values(state.trails).some((points) => points.length > 0) ||
    Object.values(state.mechs).some((m) => m.firingUntil > now || m.ventingUntil > now);

  useEffect(() => {
    if (!animating) return;
    const id = setInterval(() => dispatch({ type: "EXPIRE" }), 120);
    return () => clearInterval(id);
  }, [animating]);

  const mechs = Object.values(state.mechs);
  const selected = state.selectedMechId !== null ? state.mechs[state.selectedMechId] : undefined;

  const cells = state.gridCells;
  const minor = minorLines(cells);
  const sectors = sectorLines(cells);
  const unitPct = spriteSizePct(cells);
  const placements = spritePlacements(mechs, cells);
  // Painter's order: lower on screen renders on top (deterministic tiebreaks),
  // so a de-overlapped pair stacks the same way every render.
  const paintRank = new Map(
    [...mechs]
      .sort(
        (a, b) =>
          a.position.y - b.position.y ||
          a.position.x - b.position.x ||
          a.mechId.localeCompare(b.mechId),
      )
      .map((m, i) => [m.mechId, i]),
  );

  return (
    <div className="pd-arena" data-testid="arena">
      {/* grid floor + trails + range rings (grid-coordinate SVG) */}
      <svg
        className="pd-arena-grid"
        data-testid="arena-grid"
        viewBox={`0 0 ${cells} ${cells}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Arena plotting grid"
      >
        <title>Arena plotting grid</title>
        <rect x={0} y={0} width={cells} height={cells} fill="var(--coal)" />
        {/* Minor grid — subtle, at the seam level (every 2 cells). */}
        <g stroke="var(--seam)" strokeWidth={1} opacity={0.32}>
          {minor.map((c) => (
            <line
              key={`mv-${c}`}
              x1={c}
              y1={0}
              x2={c}
              y2={cells}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {minor.map((c) => (
            <line
              key={`mh-${c}`}
              x1={0}
              y1={c}
              x2={cells}
              y2={c}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>
        {/* Sector marks — brighter coarse grid (every 8 cells) so the arena reads. */}
        <g stroke="var(--ash)" strokeWidth={1.2} opacity={0.5}>
          {sectors.map((c) => (
            <line
              key={`v-${c}`}
              x1={c}
              y1={0}
              x2={c}
              y2={cells}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {sectors.map((c) => (
            <line
              key={`h-${c}`}
              x1={0}
              y1={c}
              x2={cells}
              y2={c}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>

        {/* obstacle terrain — notched iron blocks (foundry map). Drawn above
            the grid but below trails/sprites so units read over the walls. */}
        {state.obstacles.map((o) => (
          <g key={`obstacle-${o.x}-${o.y}`} data-testid="arena-obstacle">
            <path
              d={obstaclePath(o.x, o.y)}
              fill="var(--iron)"
              stroke="var(--seam)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            {/* interior seam — an ash diagonal so the low-contrast iron block
                reads unmistakably against the coal floor. */}
            <line
              x1={o.x + 0.3}
              y1={o.y + 0.3}
              x2={o.x + 0.7}
              y2={o.y + 0.7}
              stroke="var(--ash)"
              strokeWidth={1}
              opacity={0.55}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        ))}

        {/* objective cells (Phase 4) — brass diamonds under the units so a
            mech standing on a scoring cell stays legible. */}
        {state.objectives.map((objective) => (
          <g
            key={`objective-${objective.objective_id}`}
            data-testid="arena-objective"
            data-objective-id={objective.objective_id}
          >
            <path
              d={`M ${objective.cell.x + 0.5} ${objective.cell.y} L ${objective.cell.x + 1} ${
                objective.cell.y + 0.5
              } L ${objective.cell.x + 0.5} ${objective.cell.y + 1} L ${objective.cell.x} ${
                objective.cell.y + 0.5
              } Z`}
              fill="var(--brass, #b08d3f)"
              stroke="var(--seam)"
              strokeWidth={1}
              opacity={0.85}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        ))}

        {/* movement trails — most recent brightest */}
        {mechs.map((mech) => {
          const trail = state.trails[mech.mechId] ?? [];
          return trail.map((point, i) => (
            <circle
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length fading trail, positional
              key={`${mech.mechId}-trail-${i}`}
              data-testid={`arena-trail-${mech.mechId}`}
              cx={point.position.x + 0.5}
              cy={point.position.y + 0.5}
              r={0.5}
              fill={
                mech.side === "red"
                  ? "var(--ember)"
                  : mech.side === "blue"
                    ? "var(--arc)"
                    : "var(--steam)"
              }
              opacity={0.16 + (i / TRAIL_MAX) * 0.5}
            />
          ));
        })}

        {/* true-cell anchors — one outlined cell per mech, ALWAYS on. The unit
            sprite spans several cells (and de-overlap can nudge it off-center),
            so this outline is the ground truth for which cell a mech occupies. */}
        {mechs.map((mech) => (
          <rect
            key={`anchor-${mech.mechId}`}
            data-testid={`arena-cell-anchor-${mech.mechId}`}
            x={mech.position.x + 0.14}
            y={mech.position.y + 0.14}
            width={0.72}
            height={0.72}
            fill="none"
            stroke={
              mech.side === "red"
                ? "var(--ember)"
                : mech.side === "blue"
                  ? "var(--arc)"
                  : "var(--steam)"
            }
            strokeWidth={1.2}
            opacity={mech.alive ? 0.9 : 0.4}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {/* range rings on the selected mech */}
        {selected !== undefined
          ? [3, 6, 9].map((r) => (
              <circle
                key={`ring-${r}`}
                data-testid="arena-range-ring"
                cx={selected.position.x + 0.5}
                cy={selected.position.y + 0.5}
                r={r}
                fill="none"
                stroke="var(--phosphor)"
                strokeWidth={0.8}
                strokeDasharray="1 1"
                opacity={0.35}
                vectorEffect="non-scaling-stroke"
              />
            ))
          : null}
      </svg>

      {/* per-weapon-class tracers */}
      {state.tracers.map((t) => (
        <TracerLayer key={t.id} tracer={t} gridCells={cells} />
      ))}

      {/* armor-absorb shimmers */}
      {state.shimmers.map((s) => (
        <span
          key={s.id}
          className="pd-arena-shimmer"
          data-testid="arena-shimmer"
          style={{ left: pctOf(s.position.x, cells), top: pctOf(s.position.y, cells) }}
          aria-hidden="true"
        />
      ))}

      {/* chassis sprites (+ wreck + steam burst) */}
      {mechs.map((mech) => {
        const spriteState = mechStateOf(mech.hp, mech.hpMax, mech.alive);
        const side = mech.side;
        const selectedNow = state.selectedMechId === mech.mechId;
        const placement = placements[mech.mechId] ?? {
          left: ((mech.position.x + 0.5) / cells) * 100,
          top: ((mech.position.y + 0.5) / cells) * 100,
          paired: false,
        };
        const scale = placement.paired ? PAIR_SCALE : 1;
        return (
          <div
            key={mech.mechId}
            className="pd-arena-unit"
            data-testid={`arena-mech-${mech.mechId}`}
            data-chassis-class={mech.chassisClass}
            data-state={spriteState}
            data-selected={selectedNow}
            data-side={side}
            data-paired={placement.paired}
            style={{
              left: `${placement.left}%`,
              top: `${placement.top}%`,
              width: `${unitPct}%`,
              height: `${unitPct}%`,
              transform: `translate(-50%, -50%) scale(${scale})`,
              zIndex: 4 + (paintRank.get(mech.mechId) ?? 0),
            }}
          >
            {/* Side-colored glow ring under the sprite — makes each unit read
                against the dark arena and encodes its side at a glance. */}
            <span className="pd-arena-glow" data-side={side} aria-hidden="true" />
            <button
              type="button"
              className="pd-arena-unit-btn"
              aria-label={`Select ${mech.mechId}`}
              aria-pressed={selectedNow}
              onClick={() => dispatch({ type: "SELECT", mechId: mech.mechId })}
            >
              <ChassisSprite
                chassisClass={mech.chassisClass}
                state={spriteState}
                facing={mech.facing}
                venting={mech.alive && mech.ventingUntil > now}
                firing={mech.alive && mech.firingUntil > now}
                side={side === "neutral" ? undefined : side}
                size={40}
              />
            </button>
            {/* Name tag (A-01 / B-01) under the sprite. */}
            <span
              className="pd-arena-tag"
              data-side={side}
              data-testid={`arena-tag-${mech.mechId}`}
            >
              {displayNameOf(mech.mechId)}
            </span>
            {!mech.alive ? <SteamBurst mechId={mech.mechId} /> : null}
          </div>
        );
      })}

      {state.vpThreshold !== null ? (
        <div className="pd-arena-vp" data-testid="vp-scoreboard" data-threshold={state.vpThreshold}>
          {Object.entries(state.vpTotals)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([playerId, vp]) => (
              <span key={playerId} data-testid="vp-counter" data-player={playerId} data-vp={vp}>
                {displayNameOf(playerId)}: {vp}/{state.vpThreshold} VP
              </span>
            ))}
        </div>
      ) : null}

      {state.victoryWinnerId !== null ? (
        <div
          className="pd-arena-victory"
          data-testid="arena-victory"
          data-winner={state.victoryWinnerId}
        >
          {/* `victory-banner` is the Proof-of-Life projection contract (Task 34):
              the headless harness waits for
              [data-testid="victory-banner"][data-winner="<winner>"] and reads its
              text. It is a nested span (not a second testid on the band) so the
              `arena-victory` band keeps its own testid + styling. */}
          <span data-testid="victory-banner" data-winner={state.victoryWinnerId}>
            VICTORY · {state.victoryWinnerId}
          </span>
        </div>
      ) : null}

      {state.victoryWinnerId === null && state.drawReason !== null ? (
        <div className="pd-arena-victory pd-arena-draw" data-testid="arena-draw">
          <span data-testid="draw-banner" data-reason={state.drawReason}>
            DRAW · {state.drawReason}
          </span>
        </div>
      ) : null}
    </div>
  );
}

/** One tracer, positioned over the arena; impact ring appears on hit_resolved. */
function TracerLayer({
  tracer,
  gridCells,
}: {
  tracer: ArenaTracer;
  gridCells: number;
}): React.JSX.Element {
  // Attribute tracer color to the firing subject, not its position: two mechs
  // can legally share a cell, making a position lookup ambiguous.
  const side = tracer.attackerSide === "neutral" ? undefined : tracer.attackerSide;
  return (
    <Tracer
      from={tracer.from}
      to={tracer.to}
      weaponClass={tracer.weaponClass}
      gridCells={gridCells}
      side={side}
      impact={tracer.impact}
    />
  );
}
