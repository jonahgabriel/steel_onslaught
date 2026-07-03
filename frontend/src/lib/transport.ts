/**
 * Client-side match transport — the pacing brain of the PRESSURE DECK.
 *
 * With the Python server's default `--tick-delay 0`, envelopes stream at full
 * speed and the CLIENT owns pacing; nonzero legacy server pacing remains
 * available. Client release control is what makes pause *real*: nothing
 * downstream (arena, spec panels, river, odometer) advances unless this engine
 * *releases* an envelope to it. Pausing simply stops releasing — every panel
 * freezes together.
 *
 * Responsibilities:
 *   - ingest raw envelopes into per-`match_id` buffers (a multi-match `so serve
 *     --match all` stream keeps each match contiguous; we split it by id);
 *   - drive a playback cursor that advances by *whole tick boundaries*, paced
 *     against a wall clock (`frame(now)`, fed rAF timestamps) at ×1/×2/×4;
 *   - expose play / pause / step ±1 tick / restart / LIVE / match-select
 *     controls;
 *   - emit ONLY released envelopes to a fold sink, with an ordered `reset()`
 *     signal before a rebuild so downstream reducers stay in lockstep.
 *
 * The engine is framework-agnostic and deterministic: all timing flows through
 * the `now` passed to `frame`, so tests drive it with an injected clock.
 */
import type { SOEventEnvelope } from "../types";

/** Wall-clock milliseconds a single tick occupies at ×1 speed. */
export const BASE_MS_PER_TICK = 500;

export type TransportSpeed = 1 | 2 | 4;
export const TRANSPORT_SPEEDS: readonly TransportSpeed[] = [1, 2, 4];

/**
 * - `live`    — follow the buffer end; every ingested frame is released at once.
 * - `playing` — advance the cursor one tick per `BASE_MS_PER_TICK / speed` ms.
 * - `paused`  — cursor frozen; nothing releases.
 */
export type TransportStatus = "live" | "playing" | "paused";

/** One picker entry — updated live as frames arrive. */
export interface MatchSummary {
  matchId: string;
  /** First mech id (RED side) from `match_started`; "" until seen. */
  redLabel: string;
  /** Second mech id (BLUE side) from `match_started`; "" until seen. */
  blueLabel: string;
  /** Highest tick + 1 buffered so far (0 before any event). */
  tickCount: number;
  eventCount: number;
}

export interface TransportSnapshot {
  status: TransportStatus;
  speed: TransportSpeed;
  matches: readonly MatchSummary[];
  activeMatchId: string | null;
  /** Tick of the last released envelope for the active match, or -1. */
  cursorTick: number;
  /** Highest tick buffered for the active match, or -1. */
  bufferedTick: number;
  releasedCount: number;
  bufferedCount: number;
  /** Cursor sits at (or past) the buffer end — nothing left to play. */
  atEnd: boolean;
}

/**
 * Fold sink. `reset()` clears downstream fold state; `release(batch)` folds the
 * batch in order. The engine always calls `reset()` before re-releasing a
 * rebuilt prefix, and both flow through the same synchronous call so a React
 * consumer that funnels them into one ordered buffer never inverts them.
 */
export interface ReleaseSink {
  reset(): void;
  release(batch: readonly SOEventEnvelope[]): void;
}

export type StateListener = (snapshot: TransportSnapshot) => void;

interface MatchBuffer {
  events: SOEventEnvelope[];
  maxTick: number;
  redLabel: string;
  blueLabel: string;
}

export interface MatchTransportOptions {
  /** Wall-clock ms per tick at ×1 (default {@link BASE_MS_PER_TICK}). */
  msPerTick?: number;
}

export class MatchTransport {
  private readonly msPerTick: number;
  private readonly buffers = new Map<string, MatchBuffer>();
  private readonly order: string[] = [];

  private activeMatchId: string | null = null;
  private releasedCount = 0;
  private status: TransportStatus = "live";
  private speed: TransportSpeed = 1;

  private lastReleaseTime = 0;
  /** Release one tick immediately on the next playing frame (snappy resume). */
  private primeImmediate = true;
  private pendingReset = false;
  private pendingStepForward = false;

  private sink: ReleaseSink | null = null;
  private readonly stateListeners = new Set<StateListener>();

  /**
   * Cached snapshot + a header-relevant signature. `snapshot()` returns a
   * stable reference (required by `useSyncExternalStore`) that only changes
   * when a field the header renders changes — so streaming thousands of
   * within-tick envelopes does not thrash React.
   */
  private cachedSnapshot: TransportSnapshot;
  private signature = "";

  constructor(options: MatchTransportOptions = {}) {
    this.msPerTick = options.msPerTick ?? BASE_MS_PER_TICK;
    this.cachedSnapshot = this.buildSnapshot();
    this.signature = this.snapshotSignature(this.cachedSnapshot);
  }

  // -- wiring -------------------------------------------------------------

  /** Register the fold sink (reset/release). Returns an unsubscribe fn. */
  setSink(sink: ReleaseSink): () => void {
    this.sink = sink;
    return () => {
      if (this.sink === sink) this.sink = null;
    };
  }

  subscribeState(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    listener(this.snapshot());
    return () => {
      this.stateListeners.delete(listener);
    };
  }

  // -- ingest -------------------------------------------------------------

  /** Append a raw envelope into its match buffer (canonical order assumed). */
  ingest(env: SOEventEnvelope): void {
    const matchId = env.match_id;
    let buf = this.buffers.get(matchId);
    if (buf === undefined) {
      buf = { events: [], maxTick: -1, redLabel: "", blueLabel: "" };
      this.buffers.set(matchId, buf);
      this.order.push(matchId);
      if (this.activeMatchId === null) this.activeMatchId = matchId;
    }
    buf.events.push(env);
    if (env.tick > buf.maxTick) buf.maxTick = env.tick;
    if (env.event_type === "match_started") {
      buf.redLabel = env.payload.mechs[0]?.mech_id ?? "";
      buf.blueLabel = env.payload.mechs[1]?.mech_id ?? "";
    }
    this.notifyState();
  }

  // -- clock --------------------------------------------------------------

  private get tickDurationMs(): number {
    return this.msPerTick / this.speed;
  }

  private activeBuffer(): MatchBuffer | null {
    if (this.activeMatchId === null) return null;
    return this.buffers.get(this.activeMatchId) ?? null;
  }

  /** Release the whole tick beginning at the cursor into `batch`. */
  private releaseTickInto(buf: MatchBuffer, batch: SOEventEnvelope[]): void {
    const events = buf.events;
    const first = events[this.releasedCount];
    if (first === undefined) return;
    const tick = first.tick;
    let ev: SOEventEnvelope | undefined = first;
    while (ev !== undefined && ev.tick === tick) {
      batch.push(ev);
      this.releasedCount += 1;
      ev = events[this.releasedCount];
    }
  }

  /**
   * Advance the transport to wall-clock time `now` and release whatever the
   * current mode/cursor dictates. Call once per animation frame with the rAF
   * timestamp (or an injected clock value in tests).
   */
  frame(now: number): void {
    const buf = this.activeBuffer();
    if (buf === null) return;
    const events = buf.events;
    const batch: SOEventEnvelope[] = [];
    let changed = false;

    if (this.pendingReset) {
      this.sink?.reset();
      this.pendingReset = false;
      changed = true;
      // Rebuild the prefix the cursor should already show (0 for restart/switch,
      // the retained slice for step-back / a live jump).
      for (let i = 0; i < this.releasedCount && i < events.length; i += 1) {
        const ev = events[i];
        if (ev !== undefined) batch.push(ev);
      }
    }

    if (this.pendingStepForward) {
      this.releaseTickInto(buf, batch);
      this.pendingStepForward = false;
    }

    if (this.status === "live") {
      while (this.releasedCount < events.length) {
        const ev = events[this.releasedCount];
        if (ev !== undefined) batch.push(ev);
        this.releasedCount += 1;
      }
    } else if (this.status === "playing") {
      const dur = this.tickDurationMs;
      if (this.primeImmediate) {
        this.lastReleaseTime = now;
        this.releaseTickInto(buf, batch);
      }
      let guard = 0;
      while (
        this.releasedCount < events.length &&
        now - this.lastReleaseTime >= dur &&
        guard < 100000
      ) {
        this.releaseTickInto(buf, batch);
        this.lastReleaseTime += dur;
        guard += 1;
      }
    }
    this.primeImmediate = false;

    if (batch.length > 0) {
      this.sink?.release(batch);
      changed = true;
    }
    if (changed) this.notifyState();
  }

  // -- controls -----------------------------------------------------------

  play(): void {
    if (this.status === "playing") return;
    this.status = "playing";
    this.primeImmediate = true;
    this.notifyState();
  }

  pause(): void {
    if (this.status === "paused") return;
    this.status = "paused";
    this.notifyState();
  }

  togglePlay(): void {
    if (this.status === "playing") this.pause();
    else this.play();
  }

  setSpeed(speed: TransportSpeed): void {
    if (this.speed === speed) return;
    this.speed = speed;
    this.notifyState();
  }

  /** Jump to the buffer end and follow new frames as they arrive. */
  goLive(): void {
    this.status = "live";
    this.notifyState();
  }

  /** Reveal the next whole tick, then hold (implies pause). */
  stepForward(): void {
    this.status = "paused";
    const buf = this.activeBuffer();
    if (buf === null || this.releasedCount >= buf.events.length) {
      this.notifyState();
      return;
    }
    this.pendingStepForward = true;
    this.notifyState();
  }

  /** Retract the most recently revealed tick, then hold (implies pause). */
  stepBackward(): void {
    this.status = "paused";
    const buf = this.activeBuffer();
    if (buf === null || this.releasedCount === 0) {
      this.notifyState();
      return;
    }
    const events = buf.events;
    const lastReleased = events[this.releasedCount - 1];
    if (lastReleased === undefined) {
      this.notifyState();
      return;
    }
    const lastTick = lastReleased.tick;
    let target = this.releasedCount;
    while (target > 0 && events[target - 1]?.tick === lastTick) target -= 1;
    this.releasedCount = target;
    this.pendingReset = true; // fold state is forward-only → rebuild from 0
    this.notifyState();
  }

  /** Rewind to tick 0 and play forward under current settings. */
  restart(): void {
    this.releasedCount = 0;
    this.status = "playing";
    this.pendingReset = true;
    this.primeImmediate = true;
    this.notifyState();
  }

  /**
   * Switch the active match. Folds reset and the buffer replays through the
   * current transport settings (LIVE → instant full state; playing → from the
   * top at the current speed; paused → held at tick 0).
   */
  selectMatch(matchId: string): void {
    const buf = this.buffers.get(matchId);
    if (buf === undefined || matchId === this.activeMatchId) return;
    this.activeMatchId = matchId;
    // LIVE jumps to the end; every other mode reveals the setup tick (tick 0)
    // immediately so the new match's board is visible even while paused, then
    // replays forward under the current transport settings.
    this.releasedCount = this.status === "live" ? buf.events.length : this.firstTickCount(buf);
    this.pendingReset = true;
    this.primeImmediate = true;
    this.notifyState();
  }

  /** Number of events in the first (setup) tick of a buffer. */
  private firstTickCount(buf: MatchBuffer): number {
    const events = buf.events;
    const head = events[0];
    if (head === undefined) return 0;
    let n = 0;
    let ev: SOEventEnvelope | undefined = head;
    while (ev !== undefined && ev.tick === head.tick) {
      n += 1;
      ev = events[n];
    }
    return n;
  }

  // -- snapshot -----------------------------------------------------------

  private matchSummaries(): MatchSummary[] {
    return this.order.map((matchId) => {
      const buf = this.buffers.get(matchId);
      if (buf === undefined) {
        return { matchId, redLabel: "", blueLabel: "", tickCount: 0, eventCount: 0 };
      }
      return {
        matchId,
        redLabel: buf.redLabel,
        blueLabel: buf.blueLabel,
        tickCount: buf.maxTick + 1,
        eventCount: buf.events.length,
      };
    });
  }

  /** The current cached snapshot (stable reference between header-relevant changes). */
  snapshot(): TransportSnapshot {
    return this.cachedSnapshot;
  }

  private buildSnapshot(): TransportSnapshot {
    const buf = this.activeBuffer();
    const events = buf?.events ?? [];
    const cursorTick = this.releasedCount > 0 ? (events[this.releasedCount - 1]?.tick ?? -1) : -1;
    return {
      status: this.status,
      speed: this.speed,
      matches: this.matchSummaries(),
      activeMatchId: this.activeMatchId,
      cursorTick,
      bufferedTick: buf?.maxTick ?? -1,
      releasedCount: this.releasedCount,
      bufferedCount: events.length,
      atEnd: this.releasedCount >= events.length,
    };
  }

  /** Header-relevant fields only — NOT eventCount/releasedCount (those churn per frame). */
  private snapshotSignature(s: TransportSnapshot): string {
    const matchSig = s.matches
      .map((m) => `${m.matchId}:${m.tickCount}:${m.redLabel}:${m.blueLabel}`)
      .join("|");
    return `${s.status};${s.speed};${s.activeMatchId};${s.cursorTick};${s.atEnd};${matchSig}`;
  }

  private notifyState(): void {
    const next = this.buildSnapshot();
    const sig = this.snapshotSignature(next);
    if (sig === this.signature) return; // header unchanged — keep the stable ref
    this.cachedSnapshot = next;
    this.signature = sig;
    for (const listener of [...this.stateListeners]) listener(next);
  }
}
