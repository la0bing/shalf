import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev` proxies API calls to a console started with `shalf-console`
// (default port 8090). `npm run build` writes into the Python package, which
// serves the SPA itself.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/shalf_console/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8090",
      "/auth": "http://localhost:8090",
    },
  },
});
