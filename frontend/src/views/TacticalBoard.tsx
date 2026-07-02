/**
 * TacticalBoard — Task 32.
 *
 * SVG grid (40×40 cells) that is a pure projection of the event stream.
 *
 * State updates:
 *   - MATCH_STARTED  : initialises mech positions and boiler values
 *   - MOVEMENT_RESOLVED : updates mech position
 *   - BOILER_UPDATED    : updates heat / pressure display
 *   - WEAPON_FIRED      : shows a brief firing-line from attacker to target
 *   - MECH_DESTROYED    : removes the mech marker; adds a wreckage glyph
 *   - VICTORY_DECLARED  : shows a victory banner with the winner's player_id
 *
 * Invariants:
 *   - Never POSTs or fetches — pure projection of the event stream.
 *   - Receives an `subscribe` prop so tests can inject a stub EventStream.
 */
import { useEffect, useReducer } from "react";
import type { EnvelopeHandler } from "../lib/event_stream";
import type { SOEventEnvelope, SOMechRuntimeState, SOPosition } from "../types";
import MechMarker from "./MechMarker";

// ---------------------------------------------------------------------------
// Board constants
// ---------------------------------------------------------------------------

const GRID_CELLS = 40;
const CELL_SIZE = 14; // px per cell — keeps the board compact
const BOARD_SIZE = GRID_CELLS * CELL_SIZE; // 560px

// Firing-line visible duration in milliseconds (not ticks — purely visual)
const FIRING_LINE_TTL_MS = 600;

// ---------------------------------------------------------------------------
// Per-mech display state derived from events
// ---------------------------------------------------------------------------

interface MechDisplayState {
  mechId: string;
  playerId: string;
  chassisClass: "light" | "medium" | "heavy";
  position: SOPosition;
  heat: number;
  redlineThreshold: number;
  ruptureThreshold: number;
  pressureCurrent: number;
  pressureMaximum: number;
  hp: number;
  hpMax: number;
  alive: boolean;
}

interface FiringLine {
  id: string; // unique per-fire event
  from: SOPosition;
  to: SOPosition;
  expiresAt: number; // Date.now() + TTL
}

interface Wreckage {
  mechId: string;
  position: SOPosition;
}

// ---------------------------------------------------------------------------
// Board reducer state + actions
// ---------------------------------------------------------------------------

interface BoardState {
  mechs: Record<string, MechDisplayState>;
  firingLines: FiringLine[];
  wreckages: Wreckage[];
  victoryWinnerId: string | null;
}

const INITIAL_STATE: BoardState = {
  mechs: {},
  firingLines: [],
  wreckages: [],
  victoryWinnerId: null,
};

type BoardAction =
  | { type: "ENVELOPE"; envelope: SOEventEnvelope }
  | { type: "EXPIRE_FIRING_LINES" };

function mechFromRuntimeState(state: SOMechRuntimeState): MechDisplayState {
  return {
    mechId: state.mech_id,
    playerId: state.player_id,
    chassisClass: state.chassis_class,
    position: state.position,
    heat: state.boiler.heat_current,
    redlineThreshold: state.boiler.heat_redline_threshold,
    ruptureThreshold: state.boiler.heat_rupture_threshold,
    pressureCurrent: state.boiler.pressure_current,
    pressureMaximum: state.boiler.pressure_maximum,
    hp: state.hp,
    hpMax: state.hp_max,
    alive: state.alive,
  };
}

function boardReducer(state: BoardState, action: BoardAction): BoardState {
  if (action.type === "EXPIRE_FIRING_LINES") {
    const now = Date.now();
    const active = state.firingLines.filter((l) => l.expiresAt > now);
    if (active.length === state.firingLines.length) return state; // nothing changed
    return { ...state, firingLines: active };
  }

  const { envelope } = action;

  switch (envelope.event_type) {
    case "match_started": {
      const mechs: Record<string, MechDisplayState> = {};
      for (const mechState of envelope.payload.mechs) {
        mechs[mechState.mech_id] = mechFromRuntimeState(mechState);
      }
      return { ...INITIAL_STATE, mechs };
    }

    case "movement_resolved": {
      const mechId = envelope.subject.mech_id;
      const mech = state.mechs[mechId];
      if (!mech) return state;
      return {
        ...state,
        mechs: {
          ...state.mechs,
          [mechId]: { ...mech, position: envelope.payload.to },
        },
      };
    }

    case "boiler_updated": {
      const mechId = envelope.subject.mech_id;
      const mech = state.mechs[mechId];
      if (!mech) return state;
      return {
        ...state,
        mechs: {
          ...state.mechs,
          [mechId]: {
            ...mech,
            heat: envelope.payload.heat_after,
            pressureCurrent: envelope.payload.pressure_after,
          },
        },
      };
    }

    case "weapon_fired": {
      const attackerId = envelope.subject.mech_id;
      const targetId = envelope.payload.target_id;
      const attacker = state.mechs[attackerId];
      const target = state.mechs[targetId];
      if (!attacker || !target) return state;

      const line: FiringLine = {
        id: `${envelope.event_id}`,
        from: attacker.position,
        to: target.position,
        expiresAt: Date.now() + FIRING_LINE_TTL_MS,
      };
      return {
        ...state,
        firingLines: [...state.firingLines, line],
      };
    }

    case "mech_destroyed": {
      const mechId = envelope.subject.mech_id;
      const mech = state.mechs[mechId];
      if (!mech) return state;

      const { [mechId]: _removed, ...rest } = state.mechs;
      const wreckage: Wreckage = { mechId, position: mech.position };
      return {
        ...state,
        mechs: rest,
        wreckages: [...state.wreckages, wreckage],
      };
    }

    case "victory_declared": {
      return {
        ...state,
        victoryWinnerId: envelope.payload.winner_player_id,
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// TacticalBoard component
// ---------------------------------------------------------------------------

export interface TacticalBoardProps {
  /** Injected from EventStream.subscribe — allows test-stub injection. */
  subscribe: (handler: EnvelopeHandler) => () => void;
}

export default function TacticalBoard({ subscribe }: TacticalBoardProps): React.JSX.Element {
  const [state, dispatch] = useReducer(boardReducer, INITIAL_STATE);

  // Subscribe to events
  useEffect(() => {
    const unsubscribe = subscribe((envelope: SOEventEnvelope) => {
      dispatch({ type: "ENVELOPE", envelope });
    });
    return unsubscribe;
  }, [subscribe]);

  // Periodically expire stale firing lines
  useEffect(() => {
    if (state.firingLines.length === 0) return;
    const id = setInterval(() => {
      dispatch({ type: "EXPIRE_FIRING_LINES" });
    }, 100);
    return () => clearInterval(id);
  }, [state.firingLines.length]);

  const mechs = Object.values(state.mechs);

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <svg
        data-testid="tactical-board-svg"
        role="img"
        aria-label="Tactical board showing mech positions, heat and pressure"
        width={BOARD_SIZE}
        height={BOARD_SIZE}
        style={{ background: "#111827", display: "block" }}
      >
        <title>Tactical board</title>
        {/* Grid lines — keyed on the grid coordinate itself (stable identity) */}
        <g stroke="#1f2937" strokeWidth={0.5} opacity={0.6}>
          {Array.from({ length: GRID_CELLS + 1 }, (_, i) => i).map((c) => (
            <line key={`v${c}`} x1={c * CELL_SIZE} y1={0} x2={c * CELL_SIZE} y2={BOARD_SIZE} />
          ))}
          {Array.from({ length: GRID_CELLS + 1 }, (_, i) => i).map((c) => (
            <line key={`h${c}`} x1={0} y1={c * CELL_SIZE} x2={BOARD_SIZE} y2={c * CELL_SIZE} />
          ))}
        </g>

        {/* Firing lines */}
        {state.firingLines.map((line) => (
          <line
            key={line.id}
            data-testid={`firing-line-${line.id}`}
            x1={line.from.x * CELL_SIZE + CELL_SIZE / 2}
            y1={line.from.y * CELL_SIZE + CELL_SIZE / 2}
            x2={line.to.x * CELL_SIZE + CELL_SIZE / 2}
            y2={line.to.y * CELL_SIZE + CELL_SIZE / 2}
            stroke="#fbbf24"
            strokeWidth={1.5}
            opacity={0.8}
            strokeDasharray="4 2"
          />
        ))}

        {/* Wreckage glyphs */}
        {state.wreckages.map((w) => (
          <text
            key={w.mechId}
            data-testid={`wreckage-${w.mechId}`}
            x={w.position.x * CELL_SIZE + CELL_SIZE / 2}
            y={w.position.y * CELL_SIZE + CELL_SIZE / 2 + 4}
            textAnchor="middle"
            fontSize={CELL_SIZE * 0.7}
            fill="#6b7280"
          >
            ✕
          </text>
        ))}

        {/* Mech markers */}
        {mechs.map((mech) => (
          <MechMarker
            key={mech.mechId}
            mechId={mech.mechId}
            chassisClass={mech.chassisClass}
            heat={mech.heat}
            redlineThreshold={mech.redlineThreshold}
            ruptureThreshold={mech.ruptureThreshold}
            pressureCurrent={mech.pressureCurrent}
            pressureMaximum={mech.pressureMaximum}
            hp={mech.hp}
            hpMax={mech.hpMax}
            x={mech.position.x}
            y={mech.position.y}
            cellSize={CELL_SIZE}
            alive={mech.alive}
          />
        ))}
      </svg>

      {/* Victory banner — rendered outside SVG so it can overlay the board */}
      {state.victoryWinnerId !== null && (
        <div
          data-testid="victory-banner"
          data-winner={state.victoryWinnerId}
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.7)",
            color: "#fbbf24",
            fontSize: 28,
            fontWeight: "bold",
            letterSpacing: 2,
            zIndex: 10,
          }}
        >
          VICTORY: {state.victoryWinnerId}
        </div>
      )}
    </div>
  );
}
