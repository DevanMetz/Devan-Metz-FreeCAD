import { defineConfig } from "vite";

// Local UI smoke tests use the same Python bridge as the hosted Container.
export default defineConfig({ server: {
  host: "127.0.0.1", port: 5178, strictPort: true,
  proxy: { "/api/generate": { target: "http://127.0.0.1:8086", rewrite: () => "/generate" } },
} });
