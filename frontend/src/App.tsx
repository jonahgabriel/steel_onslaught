/**
 * App — PRESSURE DECK shell.
 *
 * Owns the client-side match transport (via `useTransport`). With the server's
 * default `--tick-delay 0`, the WebSocket streams at full speed and the client
 * transport paces it; nonzero server pacing remains available. The deck folds
 * ONLY the envelopes the transport releases, so pause/step/speed/match-switch
 * affect the arena, spec panels, river and odometer together. The UI never
 * sends anything back — it is a pure projection.
 */
import type { FrontendApplication } from "./lib/application";
import { useTransport } from "./lib/useTransport";
import PressureDeck from "./views/PressureDeck";

export default function App({
  application,
}: {
  application: FrontendApplication;
}): React.JSX.Element {
  const { subscribe, snapshot, controls } = useTransport({
    transport: application.transport,
    makeStream: application.makeStream,
    scheduler: application.scheduler,
    clock: application.clock,
  });
  return (
    <PressureDeck
      subscribe={subscribe}
      transport={snapshot}
      controls={controls}
      scheduler={application.scheduler}
    />
  );
}
