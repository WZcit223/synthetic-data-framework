// Tests for the slider arithmetic: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { onGrid } from "./sliders.js";

test("a value moves onto the step grid of the new minimum, as the browser moves the slider", () => {
  // the API's bounds: 10 to 500 SKUs, 14 to 180 days; the sliders step by 20 and 10
  assert.equal(onGrid(200, { min: 10, max: 500 }, 20), 210);
  assert.equal(onGrid(90, { min: 14, max: 180 }, 10), 94);
  assert.equal(onGrid(200, { min: 20, max: 500 }, 20), 200); // already on the grid
});

test("a value outside the bounds lands on the nearest step inside them", () => {
  assert.equal(onGrid(600, { min: 10, max: 500 }, 20), 490);
  assert.equal(onGrid(0, { min: 10, max: 500 }, 20), 10);
  assert.equal(onGrid(500, { min: 10, max: 500 }, 20), 490); // 500 is off the grid 10, 30, ..., 490
});
