import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: ["autodev.localhost", "autodev-api.localhost"],
    hmr: { clientPort: 80 },
    proxy: {
      "/api": "http://backend:8000",
      "/ws": { target: "ws://backend:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
  },
});
