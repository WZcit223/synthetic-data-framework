// @vitest-environment jsdom
// Tests for the chart components, with Chart.js replaced by a recorder: npm test
import assert from "node:assert/strict";
import { render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import { test, vi } from "vitest";

const made = [];
vi.mock("./chartjs.js", () => ({
  Chart: class {
    constructor(canvas, config) {
      this.canvas = canvas;
      this.data = config.data;
      this.options = config.options;
      this.type = config.type;
      this.updates = 0;
      this.destroyed = false;
      made.push(this);
    }
    update() { this.updates++; }
    destroy() { this.destroyed = true; }
  },
}));

const { default: LineChart } = await import("./LineChart.svelte");
const { default: HeatGrid } = await import("./HeatGrid.svelte");

const fmt = v => `${v}`;

test("a chart is created from its props, updated when they change, destroyed on unmount", () => {
  made.length = 0;
  const props = { labels: ["a", "b"], format: fmt, series: [{ name: "demand", values: [1, 2] }] };
  const { rerender, unmount, container } = render(LineChart, props);
  flushSync();
  assert.equal(made.length, 1);
  const chart = made[0];
  assert.equal(chart.type, "line");
  assert.ok(container.querySelector("canvas") === chart.canvas);
  assert.deepEqual(chart.data.datasets[0].data, [1, 2]);

  rerender({ ...props, series: [{ name: "demand", values: [5, 6] }] });
  flushSync();
  assert.equal(made.length, 1); // the same instance, given the new data
  assert.equal(chart.updates, 1);
  assert.deepEqual(chart.data.datasets[0].data, [5, 6]);

  unmount();
  assert.equal(chart.destroyed, true);
});

test("a heat grid draws one cell per known value", () => {
  made.length = 0;
  render(HeatGrid, {
    format: fmt, rows: ["BULK"], columns: ["1", "2"],
    cells: [{ row: "BULK", column: "1", value: 0.5 }, { row: "BULK", column: "2", value: null }],
  });
  flushSync();
  assert.equal(made[0].type, "matrix");
  assert.equal(made[0].data.datasets[0].data.length, 1);
});
