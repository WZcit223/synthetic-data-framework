// Tests for the Explore chart view's model: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { valueFormatter } from "../../lib/format.js";
import { keyId, OTHER, pivot, toTable } from "../../lib/pivot.js";
import { MAX_BARS, MAX_SERIES, chartModel, chartPivot, isLine, seriesKey } from "./chartModel.js";
import { emptyView } from "./view.js";

const skus = Array.from({ length: 60 }, (_, i) => `SKU-${String(i).padStart(2, "0")}`);
const TABLE = toTable({
  fields: [
    { name: "date", label: "Date", kind: "time" },
    { name: "sku", label: "SKU", kind: "dimension" },
    { name: "channel", label: "Channel", kind: "dimension" },
    { name: "qty", label: "Quantity", kind: "measure", unit: "units", aggregate: "sum" },
  ],
  rows: skus.flatMap((s, i) => [["2025-01-01", s, "store", i + 1], ["2025-01-02", s, "web", 1], ["2025-01-03", s, "outlet", 2]]),
});

const model = (over, display = { stacked: false }) => {
  const v = { ...emptyView(), ...over };
  return chartModel(pivot(TABLE, ...chartPivot(v)), TABLE, v, display);
};

test("a line for one time field on rows, bars otherwise", () => {
  const v = over => ({ ...emptyView(), ...over });
  assert.equal(isLine(TABLE, v({ rows: [{ field: "date", grain: "day" }] })), true);
  assert.equal(isLine(TABLE, v({ rows: [{ field: "date", grain: "weekday" }] })), false);
  assert.equal(isLine(TABLE, v({ rows: [{ field: "date" }, { field: "sku" }] })), false);
  assert.equal(isLine(TABLE, v({ rows: [{ field: "sku" }] })), false);
});

test("bars stop at the first MAX_BARS rows and say so; a line keeps every point", () => {
  const bars = model({ rows: [{ field: "sku" }], values: [{ field: "qty", agg: "sum" }] });
  assert.equal(bars.line, false);
  assert.equal(bars.charts[0].labels.length, MAX_BARS);
  assert.match(bars.notes[0], /first 50 of 60 rows/);
  const line = model({ rows: [{ field: "date", grain: "day" }], values: [{ field: "qty", agg: "sum" }] });
  assert.equal(line.line, true);
  assert.deepEqual(line.charts[0].labels, ["2025-01-01", "2025-01-02", "2025-01-03"]);
  assert.deepEqual(line.charts[0].series[0].values, [skus.reduce((s, _, i) => s + i + 1, 0), 60, 120]);
});

test("series past MAX_SERIES fold into one Other, keyed apart from the rest", () => {
  const m = model({ rows: [{ field: "channel" }], columns: [{ field: "sku" }], values: [{ field: "qty", agg: "sum" }] });
  const series = m.charts[0].series;
  assert.equal(series.length, MAX_SERIES);
  assert.equal(series.at(-1).name, `Other (${60 - (MAX_SERIES - 1)} more)`);
  assert.equal(m.other, keyId([OTHER]));
  assert.equal(series.at(-1).id, m.other);
  assert.match(m.notes.join(" "), /53 smallest series are folded/);
});

test("one chart per value, each titled by its value and rows", () => {
  const m = model({ rows: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "max" }] });
  assert.deepEqual(m.charts.map(c => c.title), ["Sum of Quantity by Channel", "Max of Quantity by Channel"]);
  assert.match(m.notes.join(" "), /own chart and scale/);
  assert.equal(m.charts[0].format(1234.5), valueFormatter({ unit: "units", agg: "sum" })(1234.5));
});

test("with no row field, one category of the column totals", () => {
  const m = model({ columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] });
  assert.deepEqual(m.charts[0].labels, ["All rows"]);
  assert.deepEqual(Object.fromEntries(m.charts[0].series.map(s => [s.name, s.values[0]])), { outlet: 120, store: 1830, web: 60 });
});

test("bars stack only when asked, with columns, and when the values add up", () => {
  const over = { rows: [{ field: "sku" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] };
  assert.equal(model(over, { stacked: true }).stacked, true);
  assert.equal(model(over, { stacked: false }).stacked, false);
  assert.equal(model({ ...over, values: [{ field: "qty", agg: "mean" }] }, { stacked: true }).stacked, false);
  assert.equal(model({ ...over, columns: [] }, { stacked: true }).stacked, false);
});

test("the series key follows the column fields and their grains", () => {
  const v = { ...emptyView(), columns: [{ field: "channel" }] };
  assert.equal(seriesKey(v), seriesKey({ ...v, filters: { sku: { include: ["SKU-01"] } } }));
  assert.notEqual(seriesKey(v), seriesKey({ ...v, columns: [{ field: "sku" }] }));
});
