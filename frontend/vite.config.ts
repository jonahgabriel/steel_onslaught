import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import {
  DEFAULT_FRONTEND_BOOTSTRAP_TARGET,
  FRONTEND_BOOTSTRAP_PATH,
  FRONTEND_EXPECTED_OVERLAY_HEADER,
  frontendBootstrapHttpTarget,
  GENERATED_FRONTEND_BOOTSTRAP,
  parseFrontendBootstrap,
} from "./src/lib/application";

/**
 * Resolve the dev-server proxy for the bootstrap document.
 *
 * The generated bootstrap is gitignored, so a clean checkout does not have one
 * until a match server writes it. Reading it unconditionally made `npm run dev`
 * fail at config load — before a single byte was rendered. A missing file now
 * falls back to the default match-server origin; the deck then reports a
 * bootstrap fetch failure it can actually explain. Malformed content is still
 * fatal: that is drift, not absence.
 */
function bootstrapProxy(): Record<string, { target: string; headers?: Record<string, string> }> {
  const generated = new URL(GENERATED_FRONTEND_BOOTSTRAP, import.meta.url);
  if (!existsSync(fileURLToPath(generated))) {
    console.warn(
      `[steel-onslaught] no ${GENERATED_FRONTEND_BOOTSTRAP}; proxying ` +
        `${FRONTEND_BOOTSTRAP_PATH} to ${DEFAULT_FRONTEND_BOOTSTRAP_TARGET}. ` +
        "Run `uv run so play` to serve a match and regenerate it.",
    );
    return { [FRONTEND_BOOTSTRAP_PATH]: { target: DEFAULT_FRONTEND_BOOTSTRAP_TARGET } };
  }
  const raw: unknown = JSON.parse(readFileSync(generated, "utf-8"));
  const bootstrap = parseFrontendBootstrap(raw);
  return {
    [FRONTEND_BOOTSTRAP_PATH]: {
      target: frontendBootstrapHttpTarget(bootstrap),
      headers: {
        [FRONTEND_EXPECTED_OVERLAY_HEADER]: bootstrap.overlay_sha256,
      },
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const proxy = command === "serve" && mode !== "test" ? bootstrapProxy() : undefined;
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      ...(proxy === undefined ? {} : { proxy }),
    },
    test: {
      environment: "node",
      setupFiles: [],
      environmentOptions: {},
    },
  };
});
