/**
 * React binding for {@link MatchTransport}.
 *
 * Owns the single WebSocket subscription and the rAF pump: raw envelopes flow
 * into `transport.ingest`, `transport.frame(timestamp)` runs once per animation
 * frame, and the transport releases *only* the envelopes the current pacing
 * dictates to the deck's fold sink. The header reads `snapshot`; the controls
 * mutate the engine. Because pacing lives here, pause freezes every panel at
 * once (the deck simply stops receiving envelopes).
 */
import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import type { SOEventEnvelope } from "../types";
import { type EnvelopeHandler, EventStream } from "./event_stream";
import { MatchTransport, type TransportSnapshot, type TransportSpeed } from "./transport";

export interface TransportControls {
  togglePlay(): void;
  play(): void;
  pause(): void;
  setSpeed(speed: TransportSpeed): void;
  stepForward(): void;
  stepBackward(): void;
  restart(): void;
  goLive(): void;
  selectMatch(matchId: string): void;
}

export interface UseTransport {
  /** Released-envelope feed — the deck folds only what pacing releases. */
  subscribe: (handler: EnvelopeHandler) => () => void;
  snapshot: TransportSnapshot;
  controls: TransportControls;
}

export interface UseTransportOptions {
  /** Injected engine (tests); a real WebSocket-fed engine is built otherwise. */
  transport?: MatchTransport;
  /** Injected socket for the EventStream (tests). */
  makeStream?: () => EventStream;
}

export function useTransport(options: UseTransportOptions = {}): UseTransport {
  const transport = useMemo(() => options.transport ?? new MatchTransport(), [options.transport]);

  // Downstream fold handlers (PressureDeck + ArenaView via prop drilling).
  const handlersRef = useRef<Set<EnvelopeHandler>>(new Set());

  const subscribe = useCallback((handler: EnvelopeHandler) => {
    handlersRef.current.add(handler);
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  // Wire the engine's release sink to the fold handlers. `reset()` is a no-op:
  // every rebuilt prefix the engine releases begins with `match_started`, and
  // both the deck reducer and ArenaView re-initialise on that event — so the
  // reset flows in-band, in order, with zero cross-channel race.
  useEffect(() => {
    return transport.setSink({
      reset: () => {},
      release: (batch: readonly SOEventEnvelope[]) => {
        const handlers = [...handlersRef.current];
        for (const env of batch) {
          for (const handler of handlers) handler(env);
        }
      },
    });
  }, [transport]);

  // WebSocket → ingest, plus the rAF pump driving frame(timestamp).
  useEffect(() => {
    const stream = options.makeStream ? options.makeStream() : new EventStream();
    const unsubscribe = stream.subscribe((env) => transport.ingest(env));

    let raf = 0;
    const hasRaf = typeof requestAnimationFrame === "function";
    const loop = (timestamp: number): void => {
      transport.frame(timestamp);
      if (hasRaf) raf = requestAnimationFrame(loop);
    };
    if (hasRaf) raf = requestAnimationFrame(loop);

    return () => {
      unsubscribe();
      stream.close();
      if (raf !== 0 && typeof cancelAnimationFrame === "function") cancelAnimationFrame(raf);
    };
  }, [transport, options.makeStream]);

  const snapshot = useSyncExternalStore(
    useCallback((onChange) => transport.subscribeState(() => onChange()), [transport]),
    () => transport.snapshot(),
  );

  const controls = useMemo<TransportControls>(
    () => ({
      togglePlay: () => transport.togglePlay(),
      play: () => transport.play(),
      pause: () => transport.pause(),
      setSpeed: (speed) => transport.setSpeed(speed),
      stepForward: () => transport.stepForward(),
      stepBackward: () => transport.stepBackward(),
      restart: () => transport.restart(),
      goLive: () => transport.goLive(),
      selectMatch: (matchId) => transport.selectMatch(matchId),
    }),
    [transport],
  );

  return { subscribe, snapshot, controls };
}
