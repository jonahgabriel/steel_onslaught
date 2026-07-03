/**
 * ArenaView — PRESSURE DECK centerpiece (Rev 2, evolved from TacticalBoard).
 *
 * The 40×40 plotting grid scaled up into the dominant, square center arena.
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
import type { SOEventEnvelope, SOMechRuntimeState, SOPosition } from "../types";

export const GRID_CELLS = 40;
/** Minor grid lines every 2 cells (subtle) — keyed by coordinate, not index. */
const MINOR = Array.from({ length: GRID_CELLS / 2 + 1 }, (_, i) => i * 2);
/** Sector marks every 8 cells (brighter) — the readable coarse grid. */
const SECTORS = Array.from({ length: GRID_CELLS / 8 + 1 }, (_, i) => i * 8);
const TRAIL_MAX = 8;
const TRACER_TTL_MS = 700;
const FIRING_TTL_MS = 420;
const VENT_TTL_MS = 900;
const SHIMMER_TTL_MS = 520;

interface ArenaMech {
  mechId: string;
  playerId: string;
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

export interface ArenaState {
  mechs: Record<string, ArenaMech>;
  trails: Record<string, SOPosition[]>;
  tracers: ArenaTracer[];
  shimmers: Shimmer[];
  victoryWinnerId: string | null;
  selectedMechId: string | null;
  revision: number;
}

export const ARENA_INITIAL_STATE: ArenaState = {
  mechs: {},
  trails: {},
  tracers: [],
  shimmers: [],
  victoryWinnerId: null,
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
    return { ...state, tracers, shimmers, revision: state.revision + 1 };
  }

  const { envelope } = action;
  const now = Date.now();

  switch (envelope.event_type) {
    case "match_started": {
      const mechs: Record<string, ArenaMech> = {};
      for (const m of envelope.payload.mechs) mechs[m.mech_id] = mechFromRuntime(m);
      return { ...ARENA_INITIAL_STATE, mechs };
    }

    case "movement_resolved": {
      const mech = state.mechs[envelope.subject.mech_id];
      if (mech === undefined) return state;
      const { to } = envelope.payload;
      const prevTrail = state.trails[mech.mechId] ?? [];
      const trail = [...prevTrail, mech.position].slice(-TRAIL_MAX);
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
      return { ...state, victoryWinnerId: envelope.payload.winner_player_id };

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------

const pct = (cell: number): string => `${((cell + 0.5) / GRID_CELLS) * 100}%`;

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
    Object.values(state.mechs).some((m) => m.firingUntil > now || m.ventingUntil > now);

  useEffect(() => {
    if (!animating) return;
    const id = setInterval(() => dispatch({ type: "EXPIRE" }), 120);
    return () => clearInterval(id);
  }, [animating]);

  const mechs = Object.values(state.mechs);
  const selected = state.selectedMechId !== null ? state.mechs[state.selectedMechId] : undefined;

  return (
    <div className="pd-arena" data-testid="arena">
      {/* grid floor + trails + range rings (grid-coordinate SVG) */}
      <svg
        className="pd-arena-grid"
        data-testid="arena-grid"
        viewBox={`0 0 ${GRID_CELLS} ${GRID_CELLS}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Arena plotting grid"
      >
        <title>Arena plotting grid</title>
        <rect x={0} y={0} width={GRID_CELLS} height={GRID_CELLS} fill="var(--coal)" />
        {/* Minor grid — subtle, at the seam level (every 2 cells). */}
        <g stroke="var(--seam)" strokeWidth={1} opacity={0.32}>
          {MINOR.map((c) => (
            <line
              key={`mv-${c}`}
              x1={c}
              y1={0}
              x2={c}
              y2={GRID_CELLS}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {MINOR.map((c) => (
            <line
              key={`mh-${c}`}
              x1={0}
              y1={c}
              x2={GRID_CELLS}
              y2={c}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>
        {/* Sector marks — brighter coarse grid (every 8 cells) so the arena reads. */}
        <g stroke="var(--ash)" strokeWidth={1.2} opacity={0.5}>
          {SECTORS.map((c) => (
            <line
              key={`v-${c}`}
              x1={c}
              y1={0}
              x2={c}
              y2={GRID_CELLS}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {SECTORS.map((c) => (
            <line
              key={`h-${c}`}
              x1={0}
              y1={c}
              x2={GRID_CELLS}
              y2={c}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>

        {/* movement trails — most recent brightest */}
        {mechs.map((mech) => {
          const trail = state.trails[mech.mechId] ?? [];
          return trail.map((p, i) => (
            <circle
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length fading trail, positional
              key={`${mech.mechId}-trail-${i}`}
              data-testid={`arena-trail-${mech.mechId}`}
              cx={p.x + 0.5}
              cy={p.y + 0.5}
              r={0.5}
              fill={mech.playerId === mechs[0]?.playerId ? "var(--ember)" : "var(--arc)"}
              opacity={0.16 + (i / TRAIL_MAX) * 0.5}
            />
          ));
        })}

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
        <TracerLayer key={t.id} tracer={t} redPlayerId={mechs[0]?.playerId} mechs={state.mechs} />
      ))}

      {/* armor-absorb shimmers */}
      {state.shimmers.map((s) => (
        <span
          key={s.id}
          className="pd-arena-shimmer"
          data-testid="arena-shimmer"
          style={{ left: pct(s.position.x), top: pct(s.position.y) }}
          aria-hidden="true"
        />
      ))}

      {/* chassis sprites (+ wreck + steam burst) */}
      {mechs.map((mech) => {
        const spriteState = mechStateOf(mech.hp, mech.hpMax, mech.alive);
        const side = mech.playerId === mechs[0]?.playerId ? "red" : "blue";
        const selectedNow = state.selectedMechId === mech.mechId;
        return (
          <div
            key={mech.mechId}
            className="pd-arena-unit"
            data-testid={`arena-mech-${mech.mechId}`}
            data-chassis-class={mech.chassisClass}
            data-state={spriteState}
            data-selected={selectedNow}
            data-side={side}
            style={{ left: pct(mech.position.x), top: pct(mech.position.y) }}
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
                side={side}
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

      {state.victoryWinnerId !== null ? (
        <div
          className="pd-arena-victory"
          data-testid="arena-victory"
          data-winner={state.victoryWinnerId}
        >
          VICTORY · {state.victoryWinnerId}
        </div>
      ) : null}
    </div>
  );
}

/** One tracer, positioned over the arena; impact ring appears on hit_resolved. */
function TracerLayer({
  tracer,
  redPlayerId,
  mechs,
}: {
  tracer: ArenaTracer;
  redPlayerId: string | undefined;
  mechs: Record<string, ArenaMech>;
}): React.JSX.Element {
  // Attribute the tracer color to the firing side (the mech at `from`).
  const firer = Object.values(mechs).find(
    (m) => m.position.x === tracer.from.x && m.position.y === tracer.from.y,
  );
  const side = firer !== undefined && firer.playerId === redPlayerId ? "red" : "blue";
  return (
    <Tracer
      from={tracer.from}
      to={tracer.to}
      weaponClass={tracer.weaponClass}
      side={side}
      impact={tracer.impact}
    />
  );
}
