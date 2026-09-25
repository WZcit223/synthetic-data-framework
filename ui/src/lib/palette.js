// Chart colours, fixed constants (docs/refactor/explore/02-pivot-page.md).
// Series hues are assigned in this order and never cycled: a ninth series folds
// into "Other". A series keeps its colour when a filter removes its neighbours.

export const SURFACE = "#161b22"; // the dark theme's card surface every chart sits on (--surface in theme.css)

// A published categorical order, stepped for dark surfaces and checked for
// colour-blind separation between neighbours; palette.test.js keeps it that way.
export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const OTHER = "#6e7681"; // the folded tail: a neutral grey, not a ninth hue

// The heatmap's single-hue sequential ramp, low to high: six steps of one blue
// scale. The steps are discrete, and the middle step of that scale (#2a78d6) is
// left out: at its lightness neither white nor dark text reaches 4.5:1, so every
// shade here carries readable cell text.
export const HEAT = ["#104281", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#86b6ef"];

// The light theme's set, for pages on the new components (docs/refactor/frontend/interfaces.md §4):
// the same hues in the same order, stepped darker so they read on a white surface, and the
// heat ramp running from pale to deep blue.
export const LIGHT = {
  SURFACE: "#ffffff",
  SERIES: ["#1f6fd1", "#c24e1f", "#13805a", "#9a6700", "#b83f6b", "#1a7f1a", "#6f63d6", "#c94f4f"],
  OTHER: "#8c959f",
  HEAT: ["#dbe9fb", "#b4d1f6", "#86b6ef", "#5596e8", "#2f78d6", "#1c5cab"],
};
export const DARK = { SURFACE, SERIES, OTHER, HEAT };

// The set for a colour scheme ("light" or "dark").
export const paletteFor = scheme => (scheme === "light" ? LIGHT : DARK);

const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));

// WCAG relative luminance and contrast ratio.
export function luminance(color) {
  const [r, g, b] = rgb(color).map(v => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// The text colour that reads best on a filled background (a heatmap cell).
export const INK_LIGHT = "#ffffff";
export const INK_DARK = "#0d1117";
export const inkOn = fill => (contrast(fill, INK_LIGHT) >= contrast(fill, INK_DARK) ? INK_LIGHT : INK_DARK);

// Colours that follow the series, not its position: a name keeps the slot it got
// when first seen, so filtering out a neighbour never repaints the survivors and a
// series that comes back gets its own colour again. A new name takes the first
// slot no name holds; when all are held it takes the slot of a name not on screen.
// The folded tail (``other``) is always grey. Call reset() when the series field changes.
export function colorBook(series = SERIES, otherColor = OTHER) {
  const slots = new Map();
  return {
    reset() { slots.clear(); },
    assign(names, other = null) {
      const shown = new Set(names.filter(n => slots.has(n)).map(n => slots.get(n)));
      for (const n of names) {
        if (n === other || slots.has(n)) continue;
        const held = new Set(slots.values());
        let free = series.findIndex((_, i) => !held.has(i));
        if (free < 0) {
          free = series.findIndex((_, i) => !shown.has(i)); // at most eight names show, so one exists
          for (const [name, i] of slots) if (i === free) slots.delete(name);
        }
        slots.set(n, free);
        shown.add(free);
      }
      return new Map(names.map(n => [n, n === other ? otherColor : series[slots.get(n)]]));
    },
  };
}
