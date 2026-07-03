/**
 * PressureDeck — PRESSURE DECK root.
 *
 * Owns the single envelope subscription and folds it into every panel:
 * gauges (left), the Event River (centre), the radar (top-right) and the
 * inspector drawer. Incoming envelopes are buffered and flushed once per
 * animation frame (never setState-per-envelope) so a recorded match that
 * arrives faster than paint still renders correctly.
 */
import type React from "react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  ancestryOf,
  assignLanes,
  buildCausationIndex,
  highlightChain,
  type MessageId,
} from "../lib/causation";
import type { EnvelopeHandler } from "../lib/event_stream";
import { applyGaugeEvent, type GaugeState, type Gauges, initGauges } from "../lib/gauges";
import { useReducedMotion } from "../lib/motion";
import {
  buildSideMap,
  FILTER_GROUPS,
  type FilterGroup,
  filterRows,
  groupOf,
  orderRows,
  pairLlmEvidence,
  type RiverRow,
  type Side,
  type SideMap,
  summarizeEnvelope,
  windowRows,
} from "../lib/river";
import type { SOEventEnvelope } from "../types";
import EnvelopeInspector from "./EnvelopeInspector";
import EventRiver from "./EventRiver";
import GaugeRail from "./GaugeRail";
import RadarPanel from "./RadarPanel";
import Ticker from "./Ticker";

const MAX_STORED = 5000;
const WINDOW = 400;

const EMPTY_SIDES: SideMap = { byMech: new Map(), byPlayer: new Map() };

interface DeckState {
  rows: RiverRow[];
  arrival: number;
  matchId: string;
  tick: number;
  sides: SideMap;
  gauges: Gauges;
  victoryPlayer: string | null;
  victorySide: Side;
  latest: string;
  total: number;
  counts: Record<FilterGroup, number>;
  flashKey: number;
  flashSide: Side;
  ruptureKey: number;
}

const INITIAL: DeckState = {
  rows: [],
  arrival: 0,
  matchId: "",
  tick: 0,
  sides: EMPTY_SIDES,
  gauges: {},
  victoryPlayer: null,
  victorySide: "neutral",
  latest: "",
  total: 0,
  counts: { combat: 0, decisions: 0, thermal: 0, llm: 0, lifecycle: 0 },
  flashKey: 0,
  flashSide: "neutral",
  ruptureKey: 0,
};

type DeckAction = { type: "BATCH"; envs: readonly SOEventEnvelope[] };

function sideForMech(sides: SideMap, mechId: string): Side {
  return sides.byMech.get(mechId) ?? "neutral";
}

function reduce(state: DeckState, action: DeckAction): DeckState {
  let {
    matchId,
    tick,
    sides,
    gauges,
    victoryPlayer,
    victorySide,
    latest,
    total,
    flashKey,
    flashSide,
    ruptureKey,
    arrival,
  } = state;
  const counts = { ...state.counts };
  const rows = state.rows.slice();

  for (const env of action.envs) {
    rows.push({ env, arrival });
    arrival += 1;
    total += 1;
    counts[groupOf(env)] += 1;
    if (env.match_id) matchId = env.match_id;
    if (env.tick > tick) tick = env.tick;

    switch (env.event_type) {
      case "match_started": {
        sides = buildSideMap(env.payload.mechs);
        gauges = initGauges(env.payload.mechs, sides);
        break;
      }
      case "pilot_decision_made": {
        latest = `${env.subject.mech_id} ${env.payload.action} — ${summarizeEnvelope(env)}`;
        gauges = applyGaugeEvent(gauges, env);
        break;
      }
      case "damage_applied": {
        gauges = applyGaugeEvent(gauges, env);
        flashKey += 1;
        flashSide = sideForMech(sides, env.payload.target_id);
        break;
      }
      case "boiler_ruptured":
      case "mech_destroyed": {
        gauges = applyGaugeEvent(gauges, env);
        ruptureKey += 1;
        break;
      }
      case "victory_declared": {
        victoryPlayer = env.payload.winner_player_id;
        victorySide = sides.byPlayer.get(env.payload.winner_player_id) ?? "neutral";
        latest = `VICTORY ${env.payload.winner_player_id}`;
        break;
      }
      default:
        gauges = applyGaugeEvent(gauges, env);
    }
  }

  const trimmed = rows.length > MAX_STORED ? rows.slice(rows.length - MAX_STORED) : rows;

  return {
    rows: trimmed,
    arrival,
    matchId,
    tick,
    sides,
    gauges,
    victoryPlayer,
    victorySide,
    latest,
    total,
    counts,
    flashKey,
    flashSide,
    ruptureKey,
  };
}

// ---------------------------------------------------------------------------

function Odometer({ value }: { value: number }): React.JSX.Element {
  const digits = String(Math.max(0, value)).padStart(3, "0").slice(-3).split("");
  return (
    <span className="pd-odometer" data-testid="tick-odometer" aria-hidden="true">
      <span className="pd-odometer-label">TICK</span>
      {digits.map((d, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed 3-slot odometer, positional by design
        <span className="pd-digit" key={`digit-${i}`}>
          <span style={{ transform: `translateY(-${Number(d) * 10}%)` }}>
            {Array.from({ length: 10 }, (_, n) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static 0-9 column, never reorders
              <span key={n} style={{ display: "block", height: "1.6rem" }}>
                {n}
              </span>
            ))}
          </span>
        </span>
      ))}
    </span>
  );
}

export interface PressureDeckProps {
  subscribe: (handler: EnvelopeHandler) => () => void;
}

export default function PressureDeck({ subscribe }: PressureDeckProps): React.JSX.Element {
  const [state, dispatch] = useReducer(reduce, INITIAL);
  const reducedMotion = useReducedMotion();

  const bufferRef = useRef<SOEventEnvelope[]>([]);
  const frameRef = useRef<number | null>(null);
  const [playing, setPlaying] = useState(true);
  const playingRef = useRef(true);
  const [speed, setSpeed] = useState(1);

  const flush = useCallback(() => {
    frameRef.current = null;
    if (!playingRef.current) return;
    const batch = bufferRef.current;
    if (batch.length === 0) return;
    bufferRef.current = [];
    dispatch({ type: "BATCH", envs: batch });
  }, []);

  const schedule = useCallback(() => {
    if (frameRef.current === null && typeof requestAnimationFrame === "function") {
      frameRef.current = requestAnimationFrame(flush);
    }
  }, [flush]);

  useEffect(() => {
    playingRef.current = playing;
    if (playing) schedule();
  }, [playing, schedule]);

  useEffect(() => {
    const unsub = subscribe((env) => {
      bufferRef.current.push(env);
      schedule();
    });
    return () => {
      unsub();
      if (frameRef.current !== null && typeof cancelAnimationFrame === "function") {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [subscribe, schedule]);

  // ---- filters, inspector, focus, hover ----
  const [active, setActive] = useState<Set<FilterGroup>>(() => new Set(FILTER_GROUPS));
  const [selected, setSelected] = useState<SOEventEnvelope | null>(null);
  const [hoverId, setHoverId] = useState<MessageId | null>(null);
  const [focusIndex, setFocusIndex] = useState(-1);
  const tickerRef = useRef<HTMLDivElement>(null);

  const toggleGroup = useCallback((group: FilterGroup) => {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
  }, []);

  // ---- derived projection ----
  const ordered = useMemo(() => orderRows(state.rows), [state.rows]);
  const filtered = useMemo(() => filterRows(ordered, active), [ordered, active]);
  const windowed = useMemo(() => windowRows(filtered, WINDOW), [filtered]);
  const visible = windowed.visible;

  const visibleIndex = useMemo(() => buildCausationIndex(visible.map((r) => r.env)), [visible]);
  const laneMap = useMemo(
    () =>
      assignLanes(
        visible.map((r) => r.env.envelope.message_id),
        visibleIndex,
      ),
    [visible, visibleIndex],
  );
  const pairing = useMemo(() => pairLlmEvidence(visible.map((r) => r.env)), [visible]);

  const groups = useMemo(() => {
    // groupByTick over already-ordered visible rows.
    const out: { tick: number; rows: RiverRow[] }[] = [];
    let cur: { tick: number; rows: RiverRow[] } | null = null;
    for (const row of visible) {
      if (cur === null || cur.tick !== row.env.tick) {
        cur = { tick: row.env.tick, rows: [row] };
        out.push(cur);
      } else {
        cur.rows.push(row);
      }
    }
    return out;
  }, [visible]);

  const focusId = hoverId;
  const highlight = useMemo(
    () => (focusId === null ? null : highlightChain(focusId, visibleIndex)),
    [focusId, visibleIndex],
  );

  const byMessageId = useMemo(() => {
    const map = new Map<MessageId, SOEventEnvelope>();
    for (const r of state.rows) map.set(r.env.envelope.message_id, r.env);
    return map;
  }, [state.rows]);

  const ancestry = useMemo(() => {
    if (selected === null) return [];
    const ids = ancestryOf(
      selected.envelope.message_id,
      buildCausationIndex(state.rows.map((r) => r.env)),
    );
    const chain: SOEventEnvelope[] = [];
    for (const id of ids) {
      const env = byMessageId.get(id);
      if (env !== undefined) chain.push(env);
    }
    return orderRows(chain.map((env, i) => ({ env, arrival: i }))).map((r) => r.env);
  }, [selected, state.rows, byMessageId]);

  const flatVisible = visible;
  const focusedEventId =
    focusIndex >= 0 && focusIndex < flatVisible.length
      ? (flatVisible[focusIndex]?.env.event_id ?? null)
      : null;

  // ---- keyboard navigation ----
  const onSelect = useCallback((env: SOEventEnvelope) => setSelected(env), []);
  const onHover = useCallback(
    (env: SOEventEnvelope | null) => setHoverId(env === null ? null : env.envelope.message_id),
    [],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "j") {
        e.preventDefault();
        setFocusIndex((i) => Math.min(flatVisible.length - 1, i + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setFocusIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        const row = flatVisible[focusIndex];
        if (row !== undefined) setSelected(row.env);
      } else if (e.key === "f") {
        const el = tickerRef.current;
        if (el !== null) {
          const buttons = Array.from(el.querySelectorAll<HTMLButtonElement>(".pd-filter"));
          const activeIdx = buttons.indexOf(document.activeElement as HTMLButtonElement);
          const nextBtn = buttons[(activeIdx + 1) % Math.max(1, buttons.length)];
          nextBtn?.focus();
        }
      } else if (e.key === "Escape") {
        setSelected(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flatVisible, focusIndex]);

  // Scroll focused row into view.
  useEffect(() => {
    if (focusedEventId === null) return;
    document
      .querySelector(`[data-event-id="${focusedEventId}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [focusedEventId]);

  const gaugeList: GaugeState[] = useMemo(() => Object.values(state.gauges), [state.gauges]);
  const bottomKey = visible.length > 0 ? (visible[visible.length - 1]?.env.event_id ?? null) : null;

  return (
    <div className="pd-deck" data-testid="pressure-deck">
      <div className="pd-grain" aria-hidden="true" />

      <header className="pd-header">
        <span className="pd-wordmark">STEEL ONSLAUGHT</span>
        <span className="pd-matchid" data-testid="match-id">
          ▮ {state.matchId || "no match"}
        </span>
        <Odometer value={state.tick} />
        <div className="pd-transport">
          <button
            type="button"
            className="pd-tbtn"
            aria-pressed={playing}
            onClick={() => setPlaying((p) => !p)}
            data-testid="transport-play"
          >
            {playing ? "▶ LIVE" : "∥ HELD"}
          </button>
          {[1, 2, 4].map((s) => (
            <button
              key={s}
              type="button"
              className="pd-tbtn"
              aria-pressed={speed === s}
              onClick={() => setSpeed(s)}
            >
              ×{s}
            </button>
          ))}
        </div>
      </header>

      <div className="pd-body">
        <GaugeRail gauges={gaugeList} />

        <EventRiver
          groups={groups}
          hiddenCount={windowed.hiddenCount}
          sides={state.sides}
          laneMap={laneMap}
          highlight={highlight}
          unresolved={pairing.unresolved}
          focusedEventId={focusedEventId}
          bottomKey={bottomKey}
          onSelect={onSelect}
          onHover={onHover}
        />

        <div className="pd-right">
          <RadarPanel subscribe={subscribe} />
        </div>

        {selected !== null ? (
          <EnvelopeInspector
            env={selected}
            ancestry={ancestry}
            onClose={() => setSelected(null)}
            onSelect={setSelected}
          />
        ) : null}

        {state.victoryPlayer !== null ? (
          <div className="pd-victory" data-side={state.victorySide} data-testid="victory-stamp">
            <span>
              VICTORY ·{" "}
              {state.victorySide === "neutral"
                ? state.victoryPlayer
                : state.victorySide.toUpperCase()}
            </span>
          </div>
        ) : null}

        {state.flashKey > 0 && !reducedMotion ? (
          <div
            key={`flash-${state.flashKey}`}
            className="pd-flash"
            data-side={state.flashSide}
            aria-hidden="true"
          />
        ) : null}

        {state.ruptureKey > 0 && !reducedMotion ? (
          <div key={`rupture-${state.ruptureKey}`} className="pd-burst-layer" aria-hidden="true">
            {Array.from({ length: 8 }, (_, i) => {
              const angle = (i / 8) * Math.PI * 2;
              return (
                <span
                  // biome-ignore lint/suspicious/noArrayIndexKey: fixed 8-particle burst, keyed per rupture event above
                  key={i}
                  className="pd-particle"
                  style={
                    {
                      left: "20px",
                      top: "50%",
                      "--dx": `${Math.cos(angle) * 60}px`,
                      "--dy": `${Math.sin(angle) * 60}px`,
                    } as React.CSSProperties
                  }
                />
              );
            })}
          </div>
        ) : null}
      </div>

      <Ticker
        ref={tickerRef}
        active={active}
        counts={state.counts}
        total={state.total}
        onToggle={toggleGroup}
      />

      <div className="pd-live-region" aria-live="polite" data-testid="aria-live">
        Tick {state.tick}. {state.latest}
      </div>
    </div>
  );
}
