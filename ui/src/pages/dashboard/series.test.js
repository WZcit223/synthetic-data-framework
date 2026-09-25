// Tests for the dashboard's demand chart data: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { demandChart } from "./series.js";

const DATA = {
  history: [{ date: "2025-03-30", qty: 4 }, { date: "2025-03-31", qty: 6 }],
  forecast: { forecaster: "gradient-boosting", level: 0.8, days: [
    { date: "2025-04-01", mean: 3.5, low: 1, high: 6 },
    { date: "2025-04-02", mean: 2.5, low: 0, high: 5 },
  ] },
};

test("the labels run over the history, then the forecast days", () => {
  assert.deepEqual(demandChart(DATA).labels, ["2025-03-30", "2025-03-31", "2025-04-01", "2025-04-02"]);
});

test("the forecast comes first, so its band takes its colour; each series is blank where the other is drawn", () => {
  const c = demandChart(DATA);
  assert.deepEqual(c.series.map(s => s.name), ["forecast", "demand"]);
  assert.deepEqual(c.series[0].values, [null, null, 3.5, 2.5]);
  assert.deepEqual(c.series[1].values, [4, 6, null, null]);
  assert.deepEqual(c.band, { name: "80 % interval", low: [null, null, 1, 0], high: [null, null, 6, 5] });
  assert.equal(c.total, 6);
});

test("with no forecast day there is no band", () => {
  const c = demandChart({ history: DATA.history, forecast: { forecaster: "x", level: 0.8, days: [] } });
  assert.equal(c.band, undefined);
  assert.deepEqual(c.labels, ["2025-03-30", "2025-03-31"]);
});
