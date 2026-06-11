import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev server on 5173 (Task 31 invariant); WebSocket bridge runs on 8765.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: "node",
    setupFiles: [],
    environmentOptions: {},
  },
});
