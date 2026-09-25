// Tests for the Explore view: presets, labels, the link, and each shelf change: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { toTable } from "../../lib/pivot.js";
import {
  DEFAULT_DISPLAY, PRESETS, addToShelf, additive, axisLabel, chipsFor, defaultGrain, displayError, emptyView, fallbackView,
  isPreset, linkHash, moveChip, nextSort, presetKey, readLink, removeChip, rowsKey, swapAxes, valueLabel,
} from "./view.js";

const TABLE = toTable({
  fields: [
    { name: "date", label: "Order date", kind: "time" },
    { name: "channel", label: "Channel", kind: "dimension" },
    { name: "status", label: "Status", kind: "dimension" },
    { name: "qty", label: "Quantity", kind: "measure", unit: "units", aggregate: "sum" },
    { name: "price", label: "Price", kind: "measure", aggregate: "mean" },
  ],
  rows: Array.from({ length: 60 }, (_, i) => [`2025-0${1 + Math.floor(i / 30)}-${String(1 + (i % 28)).padStart(2, "0")}`, i % 2 ? "web" : "store", i % 3 ? "shipped" : "cancelled", i, 2]),
});

const view = over => ({ ...emptyView(), ...over });

test("a preset is offered for its source and recognised only while unchanged", () => {
  assert.equal(presetKey({ dataset: "inventory" }), "inventory");
  assert.equal(presetKey({ experiment: {} }), "experiment");
  assert.equal(presetKey({ synthesis: {} }, { kind: "table" }), "synthesis-table");
  assert.equal(presetKey({ effects: { table: "replicates" } }), "effects-replicates");
  assert.equal(presetKey({ estimates: { table: "scores" } }), "estimates-scores");
  const p = PRESETS["order-lines"][1];
  const v = { ...emptyView(), ...structuredClone(p.view) };
  const d = { ...DEFAULT_DISPLAY, ...p.display };
  assert.equal(isPreset(p, v, d), true);
  assert.equal(isPreset(p, v, { ...d, totals: false }), false);
  assert.equal(isPreset(p, { ...v, showAs: "share_of_total" }, d), false);
});

test("a table no preset knows opens on its first dimension by its first measure", () => {
  assert.deepEqual(fallbackView(TABLE), { rows: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] });
});

test("labels name the field, its grain and its aggregation", () => {
  assert.equal(axisLabel(TABLE, { field: "date", grain: "month" }), "Order date · Month");
  assert.equal(axisLabel(TABLE, { field: "channel" }), "Channel");
  assert.equal(valueLabel(TABLE, { field: "qty", agg: "sum" }), "Sum of Quantity");
  assert.equal(valueLabel(TABLE, { field: "channel", agg: "count" }), "Count of rows");
  assert.equal(valueLabel(TABLE, { field: "channel", agg: "count_distinct" }), "Distinct Channel");
  const v = view({ filters: { status: { exclude: ["cancelled"] }, channel: { include: ["web"] } } });
  assert.deepEqual(chipsFor(TABLE, v, "filters").map(c => c.label), ["Status: all but cancelled", "Channel: web"]);
});

test("a time field's first grain follows how many days it spans", () => {
  assert.equal(defaultGrain(TABLE, "date"), "week");
});

test("adding a field puts it on its shelf; an axis field moves with its grain", () => {
  let v = addToShelf(view({}), TABLE, "rows", "date");
  assert.deepEqual(v.rows, [{ field: "date", grain: "week" }]);
  v = addToShelf({ ...v, rows: [{ field: "date", grain: "month" }] }, TABLE, "columns", "date");
  assert.deepEqual([v.rows, v.columns], [[], [{ field: "date", grain: "month" }]]);
  v = addToShelf(v, TABLE, "values", "price");
  assert.deepEqual(v.values, [{ field: "price", agg: "mean" }]);
  v = addToShelf(v, TABLE, "filters", "status");
  assert.deepEqual(v.filters, { status: { exclude: [] } });
  assert.equal(addToShelf(v, TABLE, "rows", "nope"), v);
});

test("a change returns a new view and leaves the old one as it was", () => {
  const before = view({ rows: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] });
  const copy = structuredClone(before);
  addToShelf(before, TABLE, "rows", "status");
  moveChip(before, TABLE, "rows", 0, "columns");
  removeChip(before, "values", 0);
  swapAxes(before);
  assert.deepEqual(before, copy);
});

test("moving a chip reorders a shelf, or carries it to another; a filter moved away is dropped", () => {
  const v = view({ rows: [{ field: "channel" }, { field: "status" }, { field: "date", grain: "day" }], filters: { status: { exclude: ["cancelled"] } } });
  assert.deepEqual(moveChip(v, TABLE, "rows", 0, "rows", 3).rows.map(a => a.field), ["status", "date", "channel"]);
  assert.deepEqual(moveChip(v, TABLE, "rows", 2, "rows", 0).rows.map(a => a.field), ["date", "channel", "status"]);
  const moved = moveChip(v, TABLE, "rows", 2, "columns");
  assert.deepEqual(moved.columns, [{ field: "date", grain: "day" }]);
  const unfiltered = moveChip(v, TABLE, "filters", 0, "values");
  assert.deepEqual(unfiltered.filters, {});
  assert.deepEqual(unfiltered.values, [{ field: "status", agg: "count" }]);
  assert.equal(moveChip(v, TABLE, "filters", 0, "filters"), v);
});

test("fewer than two row fields turn subtotals off, and a column sort goes with its column", () => {
  const v = view({ rows: [{ field: "channel" }, { field: "status" }], columns: [{ field: "date", grain: "month" }], subtotals: true, sort: { by: "column", key: ["2025-01"], dir: "desc" } });
  const one = removeChip(v, "rows", 1);
  assert.equal(one.subtotals, false);
  assert.deepEqual(one.sort, { by: "label", dir: "asc" });
});

test("swapping the axes swaps row and column shares too", () => {
  const v = swapAxes(view({ rows: [{ field: "channel" }], columns: [{ field: "status" }], showAs: "share_of_row" }));
  assert.deepEqual([v.rows, v.columns, v.showAs], [[{ field: "status" }], [{ field: "channel" }], "share_of_column"]);
});

test("a header clicked again flips its direction; a new one starts where it reads best", () => {
  assert.deepEqual(nextSort({ by: "label", dir: "asc" }, "label"), { by: "label", dir: "desc" });
  assert.deepEqual(nextSort({ by: "label", dir: "asc" }, "value"), { by: "value", dir: "desc" });
  assert.deepEqual(nextSort({ by: "column", key: ["a"], dir: "desc" }, "column", ["a"]), { by: "column", key: ["a"], dir: "asc" });
  assert.deepEqual(nextSort({ by: "column", key: ["a"], dir: "desc" }, "column", ["b"]), { by: "column", key: ["b"], dir: "desc" });
});

test("stacking needs values that add up", () => {
  assert.equal(additive(view({ values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "count" }] })), true);
  assert.equal(additive(view({ values: [{ field: "qty", agg: "mean" }] })), false);
  assert.equal(additive(view({ values: [{ field: "qty", agg: "sum" }], showAs: "share_of_column" })), false);
});

test("rowsKey changes with the row fields and their grains only", () => {
  const v = view({ rows: [{ field: "date", grain: "month" }] });
  assert.equal(rowsKey(v), rowsKey({ ...v, values: [{ field: "qty", agg: "sum" }] }));
  assert.notEqual(rowsKey(v), rowsKey({ ...v, rows: [{ field: "date", grain: "week" }] }));
});

test("the link round-trips, and a broken one says why", () => {
  const source = { dataset: "order-lines" };
  const v = view({ rows: [{ field: "channel" }] });
  assert.deepEqual(readLink(linkHash(source, v, DEFAULT_DISPLAY)), { source, view: v, display: DEFAULT_DISPLAY });
  assert.equal(readLink("#other"), null);
  assert.deepEqual(readLink("#view=%7Bbad"), { error: "the view in this link is not valid JSON" });
  assert.deepEqual(readLink("#view=null"), { error: "the link holds no source and view" });
  assert.deepEqual(readLink("#view=%5B1%5D"), { error: "the link holds no source and view" });
});

test("a link's display settings are checked", () => {
  assert.equal(displayError(null), null);
  assert.equal(displayError({ as: "chart", stacked: true }), null);
  assert.equal(displayError([]), "the display must be an object");
  assert.equal(displayError({ as: "pie" }), "display.as must be table or chart");
  assert.equal(displayError({ heatmap: "yes" }), "display.heatmap must be true or false");
  assert.equal(displayError({ colour: "red" }), 'the display has an unknown key "colour"');
});
