// The UI build: five HTML pages, each its own entry, bundled into ui/dist/ with
// hashed assets and nothing loaded from the network at run time. `npm run dev`
// serves the same pages with /api proxied to a local API.
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vite";

const PAGES = ["index", "explore", "synthesizers", "effects", "forecasts"];

export default defineConfig({
  plugins: [svelte(), svelteTesting()],
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
    // pure modules run in Node; a component test opts into a DOM with `// @vitest-environment jsdom`
    include: ["src/**/*.test.js"],
  },
});
