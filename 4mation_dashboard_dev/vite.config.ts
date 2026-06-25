import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const apiTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/socket.io": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "../4mation_dashboard_deploy",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        // SPA React principale
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        // Page solveur héritée (préservée telle quelle)
        solver: fileURLToPath(new URL("./solver.html", import.meta.url)),
      },
    },
  },
});
