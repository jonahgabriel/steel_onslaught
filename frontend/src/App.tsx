/**
 * App — PRESSURE DECK shell.
 *
 * Owns the single WebSocket subscription (StrictMode double-mount safe) and
 * fans every envelope out to the deck's panels through a stable handler
 * registry, exactly as the original Task 31/32 wiring did.  The stream is a
 * pure projection source — the UI never sends anything back.
 */
import { useCallback, useEffect, useRef } from "react";
import { type EnvelopeHandler, EventStream } from "./lib/event_stream";
import PressureDeck from "./views/PressureDeck";

export default function App(): React.JSX.Element {
  const handlersRef = useRef<Set<EnvelopeHandler>>(new Set());

  useEffect(() => {
    const stream = new EventStream();
    const unsubscribe = stream.subscribe((envelope) => {
      for (const handler of [...handlersRef.current]) {
        handler(envelope);
      }
    });
    return () => {
      unsubscribe();
      stream.close();
    };
  }, []);

  const subscribe = useCallback((handler: EnvelopeHandler) => {
    handlersRef.current.add(handler);
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  return <PressureDeck subscribe={subscribe} />;
}
