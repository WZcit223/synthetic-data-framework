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

test("a series keeps its colour when its neighbours are filtered out, and when it comes back", () => {
  const book = colorBook();
  const first = book.assign(["north", "south", "east"]);
  assert.deepEqual([...first.values()], SERIES.slice(0, 3));
  const later = book.assign(["east", "west"]); // north and south filtered out, west new
  assert.equal(later.get("east"), first.get("east"));
  assert.equal(later.get("west"), SERIES[3]); // a slot no name holds, so north keeps its own
  const back = book.assign(["north", "west"]);
  assert.equal(back.get("north"), first.get("north"));
  assert.notEqual(back.get("north"), back.get("west"));
  assert.equal(book.assign(["a", "x"], "x").get("x"), OTHER);
});

test("past eight names a new one takes the slot of a name not on screen, never one shown", () => {
  const book = colorBook();
  book.assign(SERIES.map((_, i) => `s${i}`));
  const next = book.assign(["s0", "t0"]);
  assert.equal(next.get("s0"), SERIES[0]);
  assert.equal(next.get("t0"), SERIES[1]); // s1 was not on screen
  assert.notEqual(book.assign(["s1", "t0"]).get("s1"), next.get("t0")); // s1 lost its slot: it gets another one
});
