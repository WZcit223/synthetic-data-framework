// The colour scheme the page shows (light or dark, from the system setting),
// as reactive state, and the colours the charts read from the theme's tokens.
// Contract: docs/refactor/frontend/interfaces.md §4.
import { paletteFor } from "../lib/palette.js";

const query = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

export const theme = $state({ scheme: query?.matches ? "light" : "dark" });

query?.addEventListener("change", e => {
  theme.scheme = e.matches ? "light" : "dark";
});

// A token's value on the page, or the fallback when there is none (a test without CSS).
function token(name, fallback) {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** The colours a chart draws with in `scheme` (a `Look`, charts/config.js). */
export function look(scheme) {
  const p = paletteFor(scheme);
  const light = scheme === "light";
  return {
    series: p.SERIES,
    other: p.OTHER,
    heat: p.HEAT,
    surface: token("--surface", p.SURFACE),
    raised: token("--surface-raised", light ? "#f6f8fa" : "#1c2430"),
    ink: token("--ink", light ? "#1f2328" : "#e6edf3"),
    muted: token("--ink-muted", light ? "#59636e" : "#8b98a9"),
    rule: token("--rule", light ? "#d1d9e0" : "#2a3441"),
    bad: token("--bad", light ? "#cf222e" : "#f85149"),
  };
}
