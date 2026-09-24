// Tests for the chart colours: node --test ui/*.test.js
import assert from "node:assert/strict";
import { test } from "node:test";

import { colorBook, contrast, heat, HEAT, inkOn, luminance, OTHER, SERIES, SURFACE } from "./palette.js";

test("the series colours keep their published order", () => {
  assert.deepEqual(SERIES, ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]);
});

test("every series colour has at least 3:1 contrast against the card surface", () => {
  for (const c of SERIES) assert.ok(contrast(c, SURFACE) >= 3, `${c}: ${contrast(c, SURFACE).toFixed(2)}`);
  assert.ok(contrast(OTHER, SURFACE) >= 3);
});

test("the heatmap ramp is one hue in steps rising in lightness, from its low to its high end", () => {
  assert.deepEqual([HEAT[0], HEAT.at(-1)], ["#104281", "#86b6ef"]);
  assert.equal(heat(0), HEAT[0]);
  assert.equal(heat(1), HEAT.at(-1));
  for (let i = 1; i < HEAT.length; i++) assert.ok(luminance(HEAT[i]) > luminance(HEAT[i - 1]), HEAT[i]);
  assert.deepEqual([0.1, 0.3, 0.45, 0.55, 0.7, 0.9].map(heat), HEAT);
});

test("text on a heatmap cell always clears 4.5:1", () => {
  for (let i = 0; i <= 20; i++) {
    const fill = heat(i / 20);
    assert.ok(contrast(fill, inkOn(fill)) >= 4.5, `${fill}: ${contrast(fill, inkOn(fill)).toFixed(2)}`);
  }
});

test("a series keeps its colour when its neighbours are filtered out", () => {
  const book = colorBook();
  const first = book.assign(["north", "south", "east"]);
  assert.deepEqual([...first.values()], SERIES.slice(0, 3));
  const later = book.assign(["east", "west"]); // north and south filtered out, west new
  assert.equal(later.get("east"), first.get("east"));
  assert.equal(later.get("west"), SERIES[0]); // the first slot not on screen
  assert.equal(book.assign(["a", "x"], "x").get("x"), OTHER);
});

test("more names than slots start the book again without repeating a colour on screen", () => {
  const book = colorBook();
  book.assign(SERIES.map((_, i) => `s${i}`));
  const next = book.assign(["t0", "t1"]);
  assert.equal(new Set(next.values()).size, 2);
});
