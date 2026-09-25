// The UI build: four HTML pages, each its own entry, bundled into ui/dist/ with
// hashed assets and nothing loaded from the network at run time. `npm run dev`
// serves the same pages with /api proxied to a local API.
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const PAGES = ["index", "explore", "synthesizers", "effects"];

export default defineConfig({
  plugins: [svelte()],
  // relative asset URLs, so ui/dist works wherever the API mounts it
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: { input: Object.fromEntries(PAGES.map(p => [p, `${p}.html`])) },
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    include: ["src/**/*.test.js"],
  },
});
