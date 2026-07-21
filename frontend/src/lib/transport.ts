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
import type { RuntimeStatusChangedPayload, SOEventEnvelope } from "../types";

export type TransportSpeed = 1 | 2 | 4;
export const TRANSPORT_SPEEDS: readonly TransportSpeed[] = [1, 2, 4];

/**
 * - `live`    — opt-in: follow the buffer end; every ingested frame is released
 *   at once. Entered only by an explicit LIVE action.
 * - `playing` — the DEFAULT: advance the cursor one tick per
 *   the injected `msPerTick / speed` ms as a paced replay from tick 0. If the cursor
 *   catches the buffer head of a still-streaming match it holds there and
 *   resumes as more frames arrive; on a finished match it stops on the final
 *   tick (see {@link TransportSnapshot.ended}).
 * - `paused`  — cursor frozen; nothing releases.
 */
export type TransportStatus = "live" | "playing" | "paused";

/** One picker entry — updated live as frames arrive. */
export interface MatchSummary {
  matchId: string;
  /** Canonical RED-side mech identities from `match_started`; "" until seen. */
  redLabel: string;
  /** Canonical BLUE-side mech identities from `match_started`; "" until seen. */
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
  /** The active match has streamed its sole canonical terminal (`match_ended`). */
  matchComplete: boolean;
  /** Latest injected runtime lifecycle projection, if the stream carries one. */
  runtimeStatus: RuntimeStatusChangedPayload | null;
  /**
   * Paced replay has reached the final tick of a *finished* match — playback is
   * over and the play control should offer REPLAY (restart from tick 0). False
   * while still buffering (cursor merely holding at the head of a live match)
   * and false in LIVE mode (there the operator is deliberately following the end).
   */
  ended: boolean;
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
  /** The sole canonical terminal event (`match_ended`) has been ingested. */
  complete: boolean;
  lastOrder: readonly [tick: number, sequence: number, eventId: string] | null;
  llmRequests: Map<string, boolean>;
  runtimeStatus: RuntimeStatusChangedPayload | null;
}

export interface MatchTransportOptions {
  /** Wall-clock ms per tick at ×1 from the validated application bootstrap. */
  msPerTick: number;
}

export class ProjectionIntegrityError extends Error {}

function compareOrder(
  left: readonly [number, number, string],
  right: readonly [number, number, string],
): number {
  if (left[0] !== right[0]) return left[0] - right[0];
  if (left[1] !== right[1]) return left[1] - right[1];
  if (left[2] < right[2]) return -1;
  if (left[2] > right[2]) return 1;
  return 0;
}

function canonicalStructuralJson(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new ProjectionIntegrityError("envelope content contains a non-finite number");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalStructuralJson(item)).join(",")}]`;
  }
  if (typeof value === "object") {
    const record = Object.fromEntries(Object.entries(value));
    const keys = Object.keys(record).sort((left, right) => {
      if (left < right) return -1;
      if (left > right) return 1;
      return 0;
    });
    return `{${keys
      .map((key) => `${JSON.stringify(key)}:${canonicalStructuralJson(record[key])}`)
      .join(",")}}`;
  }
  throw new ProjectionIntegrityError(`envelope content contains unsupported ${typeof value}`);
}

export class MatchTransport {
  private readonly msPerTick: number;
  private readonly buffers = new Map<string, MatchBuffer>();
  private readonly order: string[] = [];
  private readonly seenMessages = new Map<string, string>();

  private activeMatchId: string | null = null;
  /**
   * A picker choice pins the operator's view.  Without a pin, the first
   * MATCH_STARTED admitted after a stale/incomplete prefix is the live match
   * and must take over the deck (an old stream can end without match_ended).
   */
  private activeMatchExplicitlySelected = false;
  private releasedCount = 0;
  // Default = paced auto-play replay from tick 0 at ×1. LIVE is opt-in.
  private status: TransportStatus = "playing";
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

  constructor(options: MatchTransportOptions) {
    if (!Number.isInteger(options.msPerTick) || options.msPerTick <= 0) {
      throw new ProjectionIntegrityError("msPerTick must be a positive integer");
    }
    this.msPerTick = options.msPerTick;
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

  /** Validate and append one envelope to its isolated per-match canonical prefix. */
  ingest(env: SOEventEnvelope): void {
    const matchId = env.match_id;
    if (env.envelope.entity_id !== matchId) {
      throw new ProjectionIntegrityError(
        `entity_id ${env.envelope.entity_id} does not equal match_id ${matchId}`,
      );
    }
    const messageId = env.envelope.message_id;
    const content = canonicalStructuralJson(env);
    const priorContent = this.seenMessages.get(messageId);
    if (priorContent !== undefined) {
      if (priorContent === content) return;
      throw new ProjectionIntegrityError(
        `message_id ${messageId} was reused with different envelope content`,
      );
    }
    let buf = this.buffers.get(matchId);
    if (buf === undefined) {
      if (env.event_type !== "match_started" || env.tick !== 0 || env.sequence_in_tick !== 0) {
        throw new ProjectionIntegrityError(
          `first event for ${matchId} must be match_started at (tick, sequence) (0, 0)`,
        );
      }
      buf = {
        events: [],
        maxTick: -1,
        redLabel: "",
        blueLabel: "",
        complete: false,
        lastOrder: null,
        llmRequests: new Map<string, boolean>(),
        runtimeStatus: null,
      };
      this.buffers.set(matchId, buf);
      this.order.push(matchId);
      // Default selection follows a fresh match once the current buffer has
      // actually been rendered beyond setup.  A historical stream may be
      // truncated before match_ended; in that case waiting for
      // `activeBuffer.complete` leaves the UI stuck on the old match forever.
      // Keep a not-yet-rendered interleaved stream first-seen so a mux does
      // not churn selection while both matches are only being admitted.  An
      // explicit picker selection pins the view and is never overridden by a
      // new match.
      if (this.activeMatchId === null) {
        this.activeMatchId = matchId;
      } else if (
        !this.activeMatchExplicitlySelected &&
        (this.activeBuffer()?.complete === true ||
          ((this.activeBuffer()?.events.length ?? 0) > 1 && this.releasedCount > 0))
      ) {
        this.activeMatchId = matchId;
        this.releasedCount = 0;
        this.status = "playing";
        this.pendingReset = true;
        this.pendingStepForward = false;
        this.primeImmediate = true;
      }
    }
    // Dedup a StrictMode / reconnect re-stream: the same envelope must never land
    // in the buffer twice (it would duplicate rows and corrupt tick boundaries).
    if (buf.complete) {
      throw new ProjectionIntegrityError(`event ${env.event_id} arrived after match_ended`);
    }
    const order: readonly [number, number, string] = [env.tick, env.sequence_in_tick, env.event_id];
    if (buf.lastOrder !== null && compareOrder(buf.lastOrder, order) >= 0) {
      throw new ProjectionIntegrityError(
        `event order is not strictly monotonic for ${matchId}: ${env.event_id}`,
      );
    }
    if (env.event_type === "match_started" && buf.events.length > 0) {
      throw new ProjectionIntegrityError(`match_started repeated for ${matchId}`);
    }
    if (env.event_type === "runtime_status_changed") {
      const status = env.payload;
      if (status.status === "ready") {
        throw new ProjectionIntegrityError(
          "ready runtime status is not streamable after match_started",
        );
      }
      if (buf.runtimeStatus === null) {
        if (status.status !== "running" || env.tick !== 0 || env.sequence_in_tick <= 0) {
          throw new ProjectionIntegrityError(
            "first runtime status after match_started must be running at tick 0",
          );
        }
      } else {
        if (status.revision <= buf.runtimeStatus.revision) {
          throw new ProjectionIntegrityError("runtime status revision is not strictly monotonic");
        }
        if (
          status.owner_id !== buf.runtimeStatus.owner_id ||
          status.mode !== buf.runtimeStatus.mode ||
          status.match_index !== buf.runtimeStatus.match_index
        ) {
          throw new ProjectionIntegrityError("runtime status identity changed within a match");
        }
        if (buf.runtimeStatus.status === "ended") {
          throw new ProjectionIntegrityError(
            "runtime ended status must be followed by match_ended",
          );
        }
      }
      buf.runtimeStatus = status;
    }
    if (env.event_type === "llm_completion_requested") {
      buf.llmRequests.set(messageId, false);
    }
    if (
      env.event_type === "llm_completion_resolved" ||
      env.event_type === "llm_completion_failed"
    ) {
      const requestId = env.envelope.causation_id;
      if (requestId === null || !buf.llmRequests.has(requestId)) {
        throw new ProjectionIntegrityError(
          `${env.event_type} must name its canonical request message_id as causation_id`,
        );
      }
      if (buf.llmRequests.get(requestId) === true) {
        throw new ProjectionIntegrityError(`LLM request ${requestId} has multiple terminals`);
      }
      buf.llmRequests.set(requestId, true);
    }
    if (env.event_type === "match_ended") {
      if (buf.runtimeStatus !== null && buf.runtimeStatus.status !== "ended") {
        throw new ProjectionIntegrityError("runtime status must be ended before match_ended");
      }
      const unresolved = [...buf.llmRequests].filter(([, resolved]) => !resolved);
      if (unresolved.length > 0) {
        throw new ProjectionIntegrityError(
          `match_ended with ${unresolved.length} unresolved LLM completion request(s)`,
        );
      }
    }
    this.seenMessages.set(messageId, content);
    buf.lastOrder = order;
    buf.events.push(env);
    if (env.tick > buf.maxTick) buf.maxTick = env.tick;
    if (env.event_type === "match_started") {
      buf.redLabel = env.payload.mechs
        .filter((mech) => mech.side === "red")
        .map((mech) => mech.mech_id)
        .join("+");
      buf.blueLabel = env.payload.mechs
        .filter((mech) => mech.side === "blue")
        .map((mech) => mech.mech_id)
        .join("+");
    }
    if (env.event_type === "match_ended") {
      buf.complete = true;
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
      // Caught up to the buffer head: re-anchor the clock to `now` so that when
      // more frames arrive playback resumes paced (no catch-up burst) instead of
      // dumping the wall-clock backlog the instant more data lands. This must
      // fire REGARDLESS of `buf.complete` (D1): the old `!buf.complete` guard
      // froze `lastReleaseTime` while the cursor rested on a finished match, so a
      // StrictMode / reconnect re-stream that appended events dumped every "owed"
      // tick accrued during the rest at once — the pacing-burst race. The dedup
      // in `ingest` stops an identical re-stream from adding events at all; this
      // re-anchor keeps pacing honest even when the re-stream carries fresh ids.
      if (this.releasedCount >= events.length) {
        this.lastReleaseTime = now;
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
   * Switch the active match. Folds reset and the new buffer AUTO-PLAYS from
   * tick 0 at the current speed (rule 4 — same paced replay as the default),
   * regardless of the prior mode (a match switch always leaves LIVE).
   */
  selectMatch(matchId: string): void {
    const buf = this.buffers.get(matchId);
    if (buf === undefined) return;
    this.activeMatchExplicitlySelected = true;
    if (matchId === this.activeMatchId) {
      this.notifyState();
      return;
    }
    this.activeMatchId = matchId;
    this.releasedCount = 0;
    this.status = "playing";
    this.pendingReset = true;
    this.primeImmediate = true;
    this.notifyState();
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
    const atEnd = this.releasedCount >= events.length;
    const matchComplete = buf?.complete ?? false;
    // Finished replay: paced cursor rested on the last tick of a completed match
    // and there is real content behind it. Not in LIVE (deliberate follow) and
    // not on an empty buffer (nothing has streamed yet).
    const ended = this.status !== "live" && atEnd && matchComplete && this.releasedCount > 0;
    return {
      status: this.status,
      speed: this.speed,
      matches: this.matchSummaries(),
      activeMatchId: this.activeMatchId,
      cursorTick,
      bufferedTick: buf?.maxTick ?? -1,
      releasedCount: this.releasedCount,
      bufferedCount: events.length,
      atEnd,
      matchComplete,
      runtimeStatus: buf?.runtimeStatus ?? null,
      ended,
    };
  }

  /** Header-relevant fields only — NOT eventCount/releasedCount (those churn per frame). */
  private snapshotSignature(s: TransportSnapshot): string {
    const matchSig = s.matches
      .map((m) => `${m.matchId}:${m.tickCount}:${m.redLabel}:${m.blueLabel}`)
      .join("|");
    const runtimeSig =
      s.runtimeStatus === null
        ? ""
        : `${s.runtimeStatus.status}:${s.runtimeStatus.revision}:${s.runtimeStatus.last_command_id ?? ""}`;
    return `${s.status};${s.speed};${s.activeMatchId};${s.cursorTick};${s.atEnd};${s.ended};${s.matchComplete};${runtimeSig};${matchSig}`;
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
