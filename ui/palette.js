// Chart colours, fixed constants (docs/refactor/explore/02-pivot-page.md).
// Series hues are assigned in this order and never cycled: a ninth series folds
// into "Other". A series keeps its colour when a filter removes its neighbours.

export const SURFACE = "#161b22"; // the card surface every chart sits on (--panel in style.css)

// A published categorical order, stepped for dark surfaces and checked for
// colour-blind separation between neighbours; palette.test.js keeps it that way.
export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
export const OTHER = "#6e7681"; // the folded tail: a neutral grey, not a ninth hue

// The heatmap's single-hue sequential ramp, low to high: six steps of one blue
// scale. The steps are discrete, and the middle step of that scale (#2a78d6) is
// left out: at its lightness neither white nor dark text reaches 4.5:1, so every
// shade here carries readable cell text.
export const HEAT = ["#104281", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#86b6ef"];

// The ramp step for t in [0, 1].
export const heat = t => HEAT[Math.min(HEAT.length - 1, Math.max(0, Math.floor(t * HEAT.length)))];

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
// when first seen, so filtering out a neighbour never repaints the survivors.
// A new name takes the first slot not used by the names on screen; the folded
// tail (``other``) is always grey. Call reset() when the series field changes.
export function colorBook() {
  const slots = new Map();
  return {
    reset() { slots.clear(); },
    assign(names, other = null) {
      const shown = new Set(names.filter(n => slots.has(n)).map(n => slots.get(n)));
      for (const n of names) {
        if (n === other || slots.has(n)) continue;
        let free = SERIES.findIndex((_, i) => !shown.has(i));
        if (free < 0) { // more distinct names over time than slots: start again from the names on screen
          slots.clear();
          return this.assign(names, other);
        }
        slots.set(n, free);
        shown.add(free);
      }
      return new Map(names.map(n => [n, n === other ? OTHER : SERIES[slots.get(n)]]));
    },
  };
}
