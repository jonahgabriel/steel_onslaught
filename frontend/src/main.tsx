import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { createFrontendApplication, loadFrontendBootstrap } from "./lib/application";
import "./styles/deck.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("missing #root container in index.html");
}
const rootContainer: HTMLElement = container;
const browserSocketFactory = {
  open: (url: string) => new WebSocket(url),
};

async function bootstrapApplication(): Promise<void> {
  const bootstrap = await loadFrontendBootstrap((path) => fetch(path));
  const application = createFrontendApplication(bootstrap, {
    socketFactory: browserSocketFactory,
    commandSocketFactory: browserSocketFactory,
    scheduler: {
      request: (callback) => requestAnimationFrame(callback),
      cancel: (handle) => cancelAnimationFrame(handle),
    },
    clock: { now: () => performance.now() },
  });

  createRoot(rootContainer).render(
    <StrictMode>
      <App application={application} />
    </StrictMode>,
  );
}

void bootstrapApplication();
