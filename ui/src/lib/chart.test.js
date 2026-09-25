// Tests for the chart drawing: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { barChart, clip, lineChart, niceTicks, stepIndex } from "./chart.js";

const format = v => (v == null ? "–" : String(v));
const series = (...names) => names.map((name, i) => ({ name, color: `#00000${i}` }));
const bars = svg => [...svg.matchAll(/class="bar" d="M([-\d.]+),[-\d.]+H([-\d.]+)/g)].map(m => [+m[1], +m[2]]);

test("ticks are round numbers that cover the data", () => {
  assert.deepEqual(niceTicks(0, 1234, 5).ticks, [0, 250, 500, 750, 1000, 1250]);
  const mixed = niceTicks(-37, 120, 4);
  assert.ok(mixed.ticks.includes(0) && mixed.lo <= -37 && mixed.hi >= 120, JSON.stringify(mixed));
  assert.deepEqual(niceTicks(0, 0).ticks, [0, 0.2, 0.4, 0.6, 0.8, 1]); // no data: a unit scale, not a division by zero
  assert.deepEqual(niceTicks(-5, -5).ticks, [-5, -4, -3, -2, -1, 0]);
  assert.deepEqual(niceTicks(0, 0.037, 4).ticks, [0, 0.01, 0.02, 0.03, 0.04]);
});

test("a long label is clipped with an ellipsis", () => {
  assert.equal(clip("spare-parts", 20), "spare-parts");
  assert.equal(clip("spare-parts", 6), "spare…");
});

test("bars grow from zero both ways, and a blank draws nothing", () => {
  const { svg, tips } = barChart({
    categories: [{ label: "up", values: [5] }, { label: "down", values: [-5] }, { label: "none", values: [null] }],
    series: series("qty"), format, compact: format, width: 600,
  });
  const [up, down] = bars(svg);
  assert.equal(bars(svg).length, 2);
  assert.equal(up[0], down[0]); // one baseline
  assert.ok(up[1] > up[0] && down[1] < down[0]);
  assert.deepEqual(tips[2].lines.map(l => l.value), ["–"]);
});

test("an all-blank chart still draws its axis and says so on hover", () => {
  const { svg, tips } = barChart({
    categories: [{ label: "a", values: [null, null] }],
    series: series("x", "y"), format, compact: format, width: 400,
  });
  assert.equal(bars(svg).length, 0);
  assert.match(svg, /<text [^>]*>0<\/text>/);
  assert.deepEqual(tips[0].lines, [{ color: "transparent", label: "no value", value: "–" }]);
});

test("stacked segments leave a gap and the total is labelled at the tip", () => {
  const { svg, tips } = barChart({
    categories: [{ label: "a", values: [3, null, 2] }],
    series: series("x", "y", "z"), format, compact: format, width: 500, stacked: true,
  });
  const [first, second] = bars(svg);
  assert.equal(second[0] - first[1], 2); // 1px back from each side of a shared edge
  assert.match(svg, /class="value"[^>]*>5<\/text>/);
  assert.deepEqual(tips[0].lines.map(l => l.label), ["x", "z"]); // a series without a value is left out
});

test("labels are escaped", () => {
  const { svg } = barChart({ categories: [{ label: "<b>x</b>", values: [1] }], series: series("q"), format, compact: format, width: 300 });
  assert.ok(!svg.includes("<b>") && svg.includes("&lt;b&gt;"));
});

test("a line breaks at a blank and a lone point is drawn as a dot", () => {
  const { svg } = lineChart({
    points: ["d1", "d2", "d3", "d4", "d5"],
    series: [{ name: "a", color: "#111111", values: [1, 2, null, 4, null] }],
    format, compact: format, width: 600,
  });
  const d = svg.match(/<path d="([^"]+)"/)[1];
  assert.equal((d.match(/M/g) ?? []).length, 2);
  assert.equal((svg.match(/<circle /g) ?? []).length, 1); // the point on d4
});

test("end labels name separate lines and give way when lines converge", () => {
  const model = values => ({
    points: ["a", "b"],
    series: [{ name: "north", color: "#111111", values: [1, values[0]] }, { name: "south", color: "#222222", values: [1, values[1]] }],
    format, compact: format, width: 600,
  });
  assert.match(lineChart(model([100, 0])).svg, />north<\/text>/);
  assert.doesNotMatch(lineChart(model([50, 49])).svg, />north<\/text>/);
});

test("the keyboard moves the crosshair one step, or to either end", () => {
  assert.equal(stepIndex("ArrowRight", null, 5), 0);
  assert.equal(stepIndex("ArrowLeft", null, 5), 4);
  assert.equal(stepIndex("ArrowRight", 4, 5), 4);
  assert.equal(stepIndex("ArrowLeft", 0, 5), 0);
  assert.equal(stepIndex("ArrowLeft", 3, 5), 2);
  assert.equal(stepIndex("Home", 3, 5), 0);
  assert.equal(stepIndex("End", 0, 5), 4);
  assert.equal(stepIndex("Enter", 2, 5), null);
});

test("a net-negative stack is labelled at its negative end", () => {
  const { svg } = barChart({
    categories: [{ label: "a", values: [-6, 2] }],
    series: series("x", "y"), format, compact: format, width: 500, stacked: true,
  });
  assert.equal(bars(svg).filter(([from, to]) => to < from).length, 1);
  // the negative segment is rounded at its end; its tip is the curve's control point
  const tip = +svg.match(/class="bar" d="M[-\d.]+,[-\d.]+H[-\d.]+Q([-\d.]+),/)[1];
  const label = svg.match(/<text class="value" x="([-\d.]+)"[^>]*text-anchor="(\w+)">-4<\/text>/);
  assert.ok(label, svg);
  assert.equal(label[2], "end");
  assert.equal(+label[1], tip - 6);
});
