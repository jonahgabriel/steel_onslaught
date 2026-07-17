import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";
import {
  FRONTEND_BOOTSTRAP_PATH,
  FRONTEND_EXPECTED_OVERLAY_HEADER,
  frontendBootstrapHttpTarget,
  GENERATED_FRONTEND_BOOTSTRAP,
  parseFrontendBootstrap,
} from "./src/lib/application";

export default defineConfig(({ command, mode }) => {
  const proxy =
    command === "serve" && mode !== "test"
      ? (() => {
          const raw: unknown = JSON.parse(
            readFileSync(new URL(GENERATED_FRONTEND_BOOTSTRAP, import.meta.url), "utf-8"),
          );
          const bootstrap = parseFrontendBootstrap(raw);
          return {
            [FRONTEND_BOOTSTRAP_PATH]: {
              target: frontendBootstrapHttpTarget(bootstrap),
              headers: {
                [FRONTEND_EXPECTED_OVERLAY_HEADER]: bootstrap.overlay_sha256,
              },
            },
          };
        })()
      : undefined;
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
