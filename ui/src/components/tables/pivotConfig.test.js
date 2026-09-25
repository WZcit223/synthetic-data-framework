// @vitest-environment jsdom
// Tests for the pivot result → Tabulator mapping: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { pivot, toTable } from "../../lib/pivot.js";
import { MAX_TABLE_COLUMNS, pivotConfig } from "./pivotConfig.js";

const TABLE = toTable({
  fields: [
    { name: "region", label: "Region", kind: "dimension" },
    { name: "channel", label: "Channel", kind: "dimension" },
    { name: "tier", label: "Tier", kind: "dimension" },
    { name: "qty", label: "Quantity", kind: "measure", unit: "units", aggregate: "sum" },
  ],
  rows: [
    ["north", "store", "a", 4],
    ["north", "web", "a", 6],
    ["north", "web", "b", 10],
    ["south", "store", "b", 1],
    ["south", "web", "a", 3],
  ],
});

const RAMP = ["#000001", "#000002", "#000003"];
const fmt = v => String(v);

function config(view, extra = {}) {
  const v = { rows: [], columns: [], values: [], filters: {}, showAs: "value", sort: { by: "label", dir: "asc" }, subtotals: false, ...view };
  const result = pivot(TABLE, v);
  return {
    result,
    c: pivotConfig(result, {
      view: v,
      rowTitles: v.rows.map(a => a.field),
      valueTitles: v.values.map(x => `${x.agg} ${x.field}`),
      formats: v.values.map(() => fmt),
      totals: true,
      heat: false,
      ramp: RAMP,
      ink: () => "#fff",
      ...extra,
    }),
  };
}

const leaves = cols => cols.flatMap(c => (c.columns ? leaves(c.columns) : [c]));
const calc = (c, field) => leaves(c.columns).find(x => x.field === field).bottomCalc?.();

test("column fields become nested header groups over one leaf per value", () => {
  const { c } = config({ rows: [{ field: "region" }], columns: [{ field: "channel" }, { field: "tier" }], values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "mean" }] });
  const titles = cols => cols.map(x => (x.columns ? { [x.title]: titles(x.columns) } : x.title));
  assert.deepEqual(titles(c.columns.slice(1)), [
    { store: [{ a: ["sum qty", "mean qty"] }, { b: ["sum qty", "mean qty"] }] },
    { web: [{ a: ["sum qty", "mean qty"] }, { b: ["sum qty", "mean qty"] }] },
    { Total: ["sum qty", "mean qty"] },
  ]);
  assert.equal(c.columns[0].frozen, true);
  assert.deepEqual(leaves(c.columns).map(x => x.field), ["r0", "c0_0", "c0_1", "c1_0", "c1_1", "c2_0", "c2_1", "c3_0", "c3_1", "t_0", "t_1"]);
});

test("the totals row is pivot()'s totals as given, for a sum, a mean and a share", () => {
  for (const [agg, showAs] of [["sum", "value"], ["mean", "value"], ["sum", "share_of_row"]]) {
    const { c, result } = config({ rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg }], showAs });
    assert.equal(calc(c, "c0_0"), result.totals.columns[0][0], `${agg} ${showAs}`);
    assert.equal(calc(c, "c1_0"), result.totals.columns[1][0], `${agg} ${showAs}`);
    assert.equal(calc(c, "t_0"), result.totals.grand[0], `${agg} ${showAs}`);
    assert.equal(calc(c, "r0"), "Total");
  }
  // the mean of the whole table, not a mean of the rows' means
  const { c } = config({ rows: [{ field: "region" }], values: [{ field: "qty", agg: "mean" }] });
  assert.equal(calc(c, "t_0"), 24 / 5);
  // totals off: no totals row and no total column
  const off = config({ rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] }, { totals: false }).c;
  assert.equal(calc(off, "c0_0"), undefined);
  assert.ok(!leaves(off.columns).some(x => x.field === "t_0"));
});

test("subtotals nest the rows as a tree under their group rows", () => {
  const { c, result } = config({ rows: [{ field: "region" }, { field: "channel" }], values: [{ field: "qty", agg: "sum" }], subtotals: true });
  assert.equal(c.tree, true);
  assert.deepEqual(c.columns.map(x => x.field), ["label", "t_0"]);
  assert.equal(c.columns[0].title, "region / channel ▲");
  const shape = rows => rows.map(r => (r._children ? { [r.label]: shape(r._children) } : `${r.label}=${r.t_0}`));
  assert.deepEqual(shape(c.data), [{ north: ["store=4", "web=16"] }, { south: ["store=1", "web=3"] }]);
  const group = result.rows.find(r => r.group && r.key[0] === "north");
  assert.equal(c.data[0].t_0, group.total[0]);
});

test("flat rows leave a repeated label prefix blank", () => {
  const { c } = config({ rows: [{ field: "region" }, { field: "channel" }], values: [{ field: "qty", agg: "sum" }] });
  assert.equal(c.tree, false);
  assert.deepEqual(c.data.map(r => [r.r0, r.r1]), [["north", "store"], ["", "web"], ["south", "store"], ["", "web"]]);
});

test("each clickable header names the sort it asks for, and the current one is marked", () => {
  const { c } = config({ rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }], sort: { by: "column", key: ["web"], dir: "desc" } });
  assert.deepEqual(c.sorts, { r0: { by: "label" }, c0_0: { by: "column", key: ["store"] }, c1_0: { by: "column", key: ["web"] }, t_0: { by: "value" } });
  assert.deepEqual(leaves(c.columns).map(x => x.title), ["region", "store", "web ▼", "Total"]);
  assert.ok(leaves(c.columns).every(x => (x.field in c.sorts) === /sortable/.test(x.cssClass ?? "")));
  // with several values, a column's group header (and the totals') sorts by it, not its value headers
  const two = config({ rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "max" }] }).c;
  assert.deepEqual(two.groupSorts, { c0_0: { by: "column", key: ["store"] }, c1_0: { by: "column", key: ["web"] }, t_0: { by: "value" } });
  assert.deepEqual(two.sorts, { r0: { by: "label" } });
  assert.deepEqual(two.columns.slice(1).map(x => x.cssClass), ["sortable", "sortable", "sortable"]);
  // no option Tabulator would reject without a module it does not load
  const all = cols => cols.flatMap(x => [x, ...(x.columns ? all(x.columns) : [])]);
  assert.ok(all(two.columns).every(x => !("headerSort" in x) && !("resizable" in x) && !Object.keys(x).some(k => k.startsWith("_"))));
});

test("with no row field the label header is blank, not Tabulator's placeholder", () => {
  const { c } = config({ columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] });
  assert.equal(c.columns[0].title, " ");
});

test("titles are text, never markup", () => {
  const { c } = config({ rows: [{ field: "region" }], values: [{ field: "qty", agg: "sum" }] }, { rowTitles: ["<img src=x onerror=alert(1)>"] });
  const node = c.columns[0].titleFormatter({ getValue: () => c.columns[0].title });
  assert.equal(node.nodeType, Node.TEXT_NODE);
});

test("heat shades leaf cells over the ramp, and a wide result is cut", () => {
  const { c } = config({ rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] }, { heat: true });
  assert.deepEqual(c.heatKey, { label: "sum qty", lo: "1", hi: "16", each: false });
  const el = document.createElement("div");
  const col = leaves(c.columns).find(x => x.field === "c1_0");
  col.formatter({ getValue: () => 16, getData: () => ({}), getElement: () => el });
  assert.equal(el.style.background, "rgb(0, 0, 3)");
  assert.equal(c.cut, null);

  const many = { columns: Array.from({ length: MAX_TABLE_COLUMNS + 5 }, (_, j) => ({ key: [`k${j}`] })), rows: [], totals: { columns: [], grand: [1] } };
  const wide = pivotConfig(many, { view: { rows: [], columns: [{ field: "x" }], values: [{ field: "y", agg: "sum" }] }, rowTitles: [], valueTitles: ["y"], formats: [fmt], totals: true, heat: false, ramp: RAMP, ink: () => "#fff" });
  assert.deepEqual(wide.cut, { shown: MAX_TABLE_COLUMNS, of: MAX_TABLE_COLUMNS + 5 });
});
