/**
 * Minimal scaffold view — Task 31.
 *
 * Subscribes to the WebSocket bridge and shows a live event counter.
 * Task 32 replaces this with the tactical board projection.
 */
import { useEffect, useState } from "react";
import { EventStream } from "./lib/event_stream";
import type { SOEventEnvelope } from "./types";

export default function App(): React.JSX.Element {
  const [events, setEvents] = useState<SOEventEnvelope[]>([]);

  useEffect(() => {
    const stream = new EventStream();
    const unsubscribe = stream.subscribe((envelope) => {
      setEvents((previous) => [...previous, envelope]);
    });
    return () => {
      unsubscribe();
      stream.close();
    };
  }, []);

  const latest = events[events.length - 1];

  return (
    <main data-testid="app-root">
      <h1>Steel Onslaught</h1>
      <p data-testid="event-count">events received: {events.length}</p>
      {latest !== undefined && (
        <p data-testid="latest-event">
          tick {latest.tick} — {latest.event_type} — {latest.subject.mech_id}
        </p>
      )}
    </main>
  );
}
