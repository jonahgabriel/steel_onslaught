/**
 * App — PRESSURE DECK shell.
 *
 * Owns the client-side match transport (via `useTransport`). With the server's
 * default `--tick-delay 0`, the WebSocket streams at full speed and the client
 * transport paces it; nonzero server pacing remains available. The deck folds
 * ONLY the envelopes the transport releases, so pause/step/speed/match-switch
 * affect the arena, spec panels, river and odometer together. The event stream
 * remains receive-only. Player selection can emit only a local intent through
 * the command gateway already constructed from the validated application
 * bootstrap and explicitly injected browser socket capability.
 */
import { useEffect, useState } from "react";
import type { FrontendApplication } from "./lib/application";
import type { BrowserHumanTurnPrompt } from "./lib/command_gateway";
import { useTransport } from "./lib/useTransport";
import MatchSetup from "./views/MatchSetup";
import PressureDeck from "./views/PressureDeck";

export default function App({
  application,
}: {
  application: FrontendApplication;
}): React.JSX.Element {
  const [humanPrompt, setHumanPrompt] = useState<BrowserHumanTurnPrompt | null>(
    application.commandGateway.prompt,
  );
  const [gatewayStatus, setGatewayStatus] = useState(application.commandGateway.status);
  useEffect(() => {
    return application.commandGateway.subscribePrompt(setHumanPrompt);
  }, [application.commandGateway]);
  useEffect(() => {
    return application.commandGateway.subscribeStatus(setGatewayStatus);
  }, [application.commandGateway]);
  const { subscribe, snapshot, controls } = useTransport({
    transport: application.transport,
    makeStream: application.makeStream,
    scheduler: application.scheduler,
    clock: application.clock,
  });
  useEffect(() => {
    if (snapshot.matchComplete) application.commandGateway.resetForNextMatch();
  }, [application.commandGateway, snapshot.matchComplete]);
  // A receipt only proves command acceptance. The canonical event stream is
  // the lifecycle authority: hide launch controls once MATCH_STARTED arrives,
  // then re-arm them after the active match reaches MATCH_ENDED.
  const matchStarted = snapshot.activeMatchId !== null && !snapshot.matchComplete;
  return (
    <>
      <MatchSetup
        bootstrap={application.bootstrap}
        capability={application.commandGateway}
        humanPrompt={humanPrompt}
        matchStarted={matchStarted}
        gatewayStatus={gatewayStatus}
      />
      <PressureDeck
        subscribe={subscribe}
        transport={snapshot}
        controls={controls}
        scheduler={application.scheduler}
      />
    </>
  );
}
