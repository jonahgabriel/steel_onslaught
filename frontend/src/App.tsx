/**
 * App — PRESSURE DECK shell.
 *
 * Owns the client-side match transport (via `useTransport`). With the server's
 * default `--tick-delay 0`, the WebSocket streams at full speed and the client
 * transport paces it; nonzero server pacing remains available. The deck folds
 * ONLY the envelopes the transport releases, so pause/step/speed/match-switch
 * affect the arena, spec panels, river and odometer together. The event stream
 * remains receive-only. Player selection can emit only a local intent through
 * an explicitly injected capability; the current composition root supplies no
 * such capability, so Start is fail-closed and sends nothing.
 */
import type { FrontendApplication } from "./lib/application";
import { useTransport } from "./lib/useTransport";
import MatchSetup, { type MatchStartIntentCapability } from "./views/MatchSetup";
import PressureDeck from "./views/PressureDeck";

export default function App({
  application,
  matchStartCapability,
}: {
  application: FrontendApplication;
  matchStartCapability?: MatchStartIntentCapability;
}): React.JSX.Element {
  const { subscribe, snapshot, controls } = useTransport({
    transport: application.transport,
    makeStream: application.makeStream,
    scheduler: application.scheduler,
    clock: application.clock,
  });
  return (
    <>
      <MatchSetup bootstrap={application.bootstrap} capability={matchStartCapability} />
      <PressureDeck
        subscribe={subscribe}
        transport={snapshot}
        controls={controls}
        scheduler={application.scheduler}
      />
    </>
  );
}
