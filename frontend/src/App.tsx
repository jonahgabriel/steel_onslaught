/**
 * App — Tasks 31 + 32 + 34.
 *
 * Connects the WebSocket event stream (Task 31) to the tactical-board
 * projection (Task 32).  The stream is created inside the effect so React
 * StrictMode's mount/unmount/mount cycle opens a fresh socket per mount;
 * `so serve` streams the full recorded match to every client, so the final
 * mount always receives the complete event sequence (Task 34 Proof of Life).
 */
import { useCallback, useEffect, useRef } from "react";
import { type EnvelopeHandler, EventStream } from "./lib/event_stream";
import TacticalBoard from "./views/TacticalBoard";

export default function App(): React.JSX.Element {
  // Stable handler registry so TacticalBoard's subscription survives the
  // stream being torn down and recreated across StrictMode remounts.
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

  return (
    <main data-testid="app-root">
      <h1>Steel Onslaught</h1>
      <TacticalBoard subscribe={subscribe} />
    </main>
  );
}
