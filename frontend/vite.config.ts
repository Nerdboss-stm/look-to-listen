import { defineConfig } from "vite";

export default defineConfig({
  // Read REPO_URL (and any VITE_* vars) from the repo-root .env without exposing secrets
  envDir: "..",
  envPrefix: ["VITE_", "REPO_URL"],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
      "/clips": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
