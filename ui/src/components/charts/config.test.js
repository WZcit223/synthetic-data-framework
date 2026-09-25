// Tests for the chart configurations: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { colorBook, DARK } from "../../lib/palette.js";
import { barConfig, heatConfig, intervalConfig, jitter, lineConfig, rampStep, stripConfig } from "./config.js";

const LOOK = {
  series: DARK.SERIES, other: DARK.OTHER, heat: DARK.HEAT, surface: "#161b22", raised: "#1c2430",
  ink: "#e6edf3", muted: "#8b98a9", rule: "#2a3441", bad: "#f85149",
};
const fmt = v => `${v}`;
const book = () => colorBook(LOOK.series, LOOK.other);

test("a line chart keeps a null as a gap and colours each series by its name", () => {
  const b = book();
  const c = lineConfig({ labels: ["d1", "d2", "d3"], format: fmt, series: [
    { name: "demand", values: [1, null, 3] },
    { name: "forecast", values: [2, 2, 2] },
  ] }, LOOK, b);
  assert.equal(c.type, "line");
  assert.deepEqual(c.data.labels, ["d1", "d2", "d3"]);
  assert.deepEqual(c.data.datasets.map(d => d.label), ["demand", "forecast"]);
  assert.deepEqual(c.data.datasets[0].data, [1, null, 3]);
  assert.equal(c.data.datasets[0].spanGaps, false);
  const [demand, forecast] = c.data.datasets.map(d => d.borderColor);
  assert.notEqual(demand, forecast);
  // "forecast" alone keeps its colour: a colour follows the name, not the position
  const again = lineConfig({ labels: ["d1"], format: fmt, series: [{ name: "forecast", values: [2] }] }, LOOK, b);
  assert.equal(again.data.datasets[0].borderColor, forecast);
});

test("a given colour wins over the book", () => {
  const c = lineConfig({ labels: ["a"], format: fmt, series: [{ name: "x", values: [1], color: "#123456" }] }, LOOK, book());
  assert.equal(c.data.datasets[0].borderColor, "#123456");
});

test("a band fills between its low and high, and its low edge is not in the legend", () => {
  const c = lineConfig({
    labels: ["a", "b"], format: fmt, series: [{ name: "forecast", values: [2, 3] }],
    band: { name: "80% interval", low: [1, null], high: [3, 4] },
  }, LOOK, book());
  const [low, high, line] = c.data.datasets;
  assert.deepEqual([low.label, high.label, line.label], ["80% interval (low)", "80% interval", "forecast"]);
  assert.deepEqual(low.data, [1, null]);
  assert.equal(high.fill, "-1");
  assert.equal(low.fill, false);
  const filter = c.options.plugins.legend.labels.filter;
  assert.equal(filter({ text: "80% interval (low)" }), false);
  assert.equal(filter({ text: "80% interval" }), true);
});

test("the ticks and the tooltip use the given format", () => {
  const pct = v => `${v * 100}%`;
  const c = lineConfig({ labels: ["a"], format: pct, series: [{ name: "s", values: [0.5] }] }, LOOK, book());
  assert.equal(c.options.scales.y.ticks.callback(0.25), "25%");
  assert.equal(c.options.plugins.tooltip.callbacks.label({ dataset: { label: "s" }, parsed: { y: 0.5 } }), "s: 50%");
});

test("bars can be stacked and horizontal; the value axis moves with them", () => {
  const series = [{ name: "a", values: [1, null] }, { name: "b", values: [2, 3] }];
  const v = barConfig({ series, labels: ["x", "y"], format: fmt }, LOOK, book());
  assert.equal(v.options.indexAxis, "x");
  assert.equal(v.options.scales.y.beginAtZero, true);
  assert.equal(v.options.scales.x.stacked, false);
  assert.deepEqual(v.data.datasets[0].data, [1, null]);
  const h = barConfig({ series, labels: ["x", "y"], format: fmt, stacked: true, horizontal: true }, LOOK, book());
  assert.equal(h.options.indexAxis, "y");
  assert.equal(h.options.scales.x.beginAtZero, true);
  assert.equal(h.options.scales.x.stacked, true);
  assert.equal(h.options.scales.y.stacked, true);
  assert.equal(h.options.plugins.legend.display, true);
  const one = barConfig({ series: [series[0]], labels: ["x", "y"], format: fmt }, LOOK, book());
  assert.equal(one.options.plugins.legend.display, false); // one series needs no legend
});

test("an interval chart puts one row per line, top to bottom, with its interval", () => {
  const rows = [
    { label: "promo", estimate: 2, low: 1, high: 3 },
    { label: "price", estimate: -1, low: null, high: null },
  ];
  const c = intervalConfig({ rows, format: fmt, reference: 0 }, LOOK, book());
  const points = c.data.datasets[0].data;
  assert.deepEqual(points[0], { x: 2, y: 0, xMin: 1, xMax: 3, label: "promo" });
  assert.deepEqual(points[1], { x: -1, y: 1, xMin: -1, xMax: -1, label: "price" }); // no interval: the point alone
  assert.equal(c.options.scales.y.reverse, true);
  assert.equal(c.options.scales.y.ticks.callback(1), "price");
  const ref = c.data.datasets.at(-1);
  assert.equal(ref.label, "reference");
  assert.deepEqual(ref.data.map(p => p.x), [0, 0]);
  const none = intervalConfig({ rows, format: fmt }, LOOK, book());
  assert.equal(none.data.datasets.length, 1); // no reference, no line
});

test("interval rows are coloured by their group", () => {
  const rows = [
    { label: "a", estimate: 1, low: 0, high: 2, group: "dml" },
    { label: "b", estimate: 1, low: 0, high: 2, group: "ols" },
    { label: "c", estimate: 1, low: 0, high: 2, group: "dml" },
  ];
  const c = intervalConfig({ rows, format: fmt }, LOOK, book());
  assert.deepEqual(c.data.datasets.map(d => [d.label, d.data.map(p => p.y)]), [["dml", [0, 2]], ["ols", [1]]]);
  assert.notEqual(c.data.datasets[0].backgroundColor, c.data.datasets[1].backgroundColor);
});

test("a strip chart jitters the same way on every draw and draws the mean as given", () => {
  assert.equal(jitter("a", 3), jitter("a", 3));
  assert.notEqual(jitter("a", 3), jitter("a", 4));
  for (let i = 0; i < 50; i++) assert.ok(Math.abs(jitter("g", i)) <= 0.25);
  const groups = [{ name: "promo", values: [1, 2, 9], mean: 4 }, { name: "price", values: [0], mean: 0 }];
  const c = stripConfig({ groups, format: fmt }, LOOK, book());
  assert.deepEqual(c.data.datasets[0].data.map(p => p.x), [1, 2, 9]);
  assert.ok(c.data.datasets[0].data.every(p => Math.abs(p.y - 0) <= 0.25));
  const mean = c.data.datasets.at(-1);
  assert.equal(mean.label, "mean");
  assert.deepEqual(mean.data, [{ x: 4, y: 0 }, { x: 0, y: 1 }]); // the mean the caller gave, not one computed here
});

test("a heat grid scales its cells onto the ramp and leaves a blank cell out", () => {
  assert.equal(rampStep(["a", "b", "c"], 0), "a");
  assert.equal(rampStep(["a", "b", "c"], 1), "c");
  assert.equal(rampStep(["a", "b", "c"], 0.5), "b");
  const cells = [
    { row: "BULK", column: "1", value: 0.2 },
    { row: "BULK", column: "2", value: 1, flag: true, label: "LOC-1" },
    { row: "PICK", column: "1", value: null },
  ];
  const c = heatConfig({ cells, rows: ["BULK", "PICK"], columns: ["1", "2"], format: fmt }, LOOK);
  const ds = c.data.datasets[0];
  assert.deepEqual(ds.data.map(p => [p.y, p.x, p.v]), [["BULK", "1", 0.2], ["BULK", "2", 1]]);
  assert.equal(ds.backgroundColor({ raw: { v: 0.2 } }), LOOK.heat[0]);
  assert.equal(ds.backgroundColor({ raw: { v: 1 } }), LOOK.heat.at(-1));
  assert.equal(ds.borderColor({ raw: { flag: true } }), LOOK.bad);
  assert.equal(ds.borderColor({ raw: { flag: false } }), LOOK.surface);
  assert.deepEqual(c.options.scales.y.labels, ["PICK", "BULK"]); // drawn bottom-up, so the first row is on top
  assert.equal(c.options.plugins.tooltip.callbacks.label({ raw: ds.data[1] }), "LOC-1");
});

test("a heat grid with a fixed domain colours by it, not by the values shown", () => {
  const cells = [{ row: "A", column: "1", value: 0 }, { row: "A", column: "2", value: 0 }];
  const fixed = heatConfig({ cells, rows: ["A"], columns: ["1", "2"], format: fmt, domain: [0, 1] }, LOOK);
  assert.equal(fixed.data.datasets[0].backgroundColor({ raw: { v: 0 } }), LOOK.heat[0]); // empty shelves read empty
  assert.equal(fixed.data.datasets[0].backgroundColor({ raw: { v: 1 } }), LOOK.heat.at(-1));
  const flat = heatConfig({ cells, rows: ["A"], columns: ["1", "2"], format: fmt }, LOOK);
  assert.equal(flat.data.datasets[0].backgroundColor({ raw: { v: 0 } }), rampStep(LOOK.heat, 0.5)); // all equal: the middle
});
