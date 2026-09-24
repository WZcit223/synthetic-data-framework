// Tests for the pivot engine: node --test ui/*.test.js
import assert from "node:assert/strict";
import { test } from "node:test";

import { compareParts, distinctValues, keptCount, OTHER, partLabel, pivot, timeKey, toCsv, toTable, viewError } from "./pivot.js";

const FIELDS = [
  { name: "day", label: "Day", kind: "time", unit: null, aggregate: null },
  { name: "region", label: "Region", kind: "dimension", unit: null, aggregate: null },
  { name: "channel", label: "Channel", kind: "dimension", unit: null, aggregate: null },
  { name: "qty", label: "Quantity", kind: "measure", unit: "units", aggregate: "sum" },
];
// Two regions, two channels, three months; one row without a quantity, one without a channel.
const TABLE = toTable({
  fields: FIELDS,
  rows: [
    ["2025-01-06", "north", "store", 4],
    ["2025-01-07", "north", "web", 6],
    ["2025-02-03", "north", "store", 10],
    ["2025-02-04", "south", "store", 1],
    ["2025-03-03", "south", "web", 3],
    ["2025-03-04", "south", "web", null],
    ["2025-03-05", "south", null, 2],
  ],
});

const cell = (result, rowKey, colKey, k = 0) => {
  const row = result.rows.find(r => r.key.join("|") === rowKey.join("|"));
  const j = result.columns.findIndex(c => c.key.join("|") === colKey.join("|"));
  return row.cells[j][k];
};

test("toTable accepts array rows and object rows", () => {
  const fromObjects = toTable({ fields: FIELDS, rows: [{ qty: 2, region: "north", day: "2025-01-01" }] });
  assert.deepEqual(fromObjects.rows, [["2025-01-01", "north", null, 2]]);
  assert.deepEqual(toTable({ fields: FIELDS, rows: [["2025-01-01", "north", null, 2]] }).rows, fromObjects.rows);
  assert.equal(toTable({ fields: FIELDS, rows: [], total_rows: 9 }).total_rows, 9);
});

test("each time grain gives the contract's key", () => {
  assert.equal(timeKey("2025-01-09", "day"), "2025-01-09");
  assert.equal(timeKey("2025-01-09", "week"), "2025-W02");
  assert.equal(timeKey("2024-12-30", "week"), "2025-W01"); // a Monday in the first ISO week of 2025
  assert.equal(timeKey("2021-01-03", "week"), "2020-W53"); // a Sunday in the last ISO week of 2020
  assert.equal(timeKey("2025-01-09", "month"), "2025-01");
  assert.equal(timeKey("2025-05-09", "quarter"), "2025-Q2");
  assert.equal(timeKey("2025-05-09", "year"), "2025");
  assert.equal(timeKey("2025-01-06", "weekday"), "Mon");
  assert.equal(timeKey("2025-01-12", "weekday"), "Sun");
  assert.equal(timeKey(null, "month"), null);
  assert.throws(() => timeKey("2025-01-01", "hour"), /unknown time grain "hour"/);
});

test("weekdays run Mon to Sun, numbers numerically, blanks last", () => {
  assert.deepEqual(["Sun", "Mon", "Wed"].sort(compareParts), ["Mon", "Wed", "Sun"]);
  assert.deepEqual(["SKU-10", null, "SKU-9"].sort(compareParts), ["SKU-9", "SKU-10", null]);
});

test("every aggregation, with a missing value ignored except by count", () => {
  const by = agg => pivot(TABLE, { rows: [{ field: "region" }], values: [{ field: "qty", agg }] }).rows.map(r => r.total[0]);
  assert.deepEqual(by("sum"), [20, 6]);
  assert.deepEqual(by("count"), [3, 4]);
  assert.deepEqual(by("mean"), [20 / 3, 2]);
  assert.deepEqual(by("median"), [6, 2]);
  assert.deepEqual(by("min"), [4, 1]);
  assert.deepEqual(by("max"), [10, 3]);
  const channels = pivot(TABLE, { rows: [{ field: "region" }], values: [{ field: "channel", agg: "count_distinct" }] });
  assert.deepEqual(channels.rows.map(r => r.total[0]), [2, 2]); // the blank channel is not a value
});

test("a total is aggregated from the rows, not from the cells", () => {
  const r = pivot(TABLE, {
    rows: [{ field: "region" }],
    columns: [{ field: "day", grain: "month" }],
    values: [{ field: "qty", agg: "mean" }],
  });
  assert.deepEqual(r.columns.map(c => c.key), [["2025-01"], ["2025-02"], ["2025-03"]]);
  // north: January mean 5, February 10; the row mean is 20/3, not (5 + 10) / 2
  assert.equal(r.rows[0].total[0], 20 / 3);
  assert.deepEqual(r.totals.columns.map(c => c[0]), [5, 5.5, 2.5]);
  assert.equal(r.totals.grand[0], 26 / 6);
});

test("an empty cell is null, never 0", () => {
  const r = pivot(TABLE, {
    rows: [{ field: "region" }],
    columns: [{ field: "day", grain: "month" }],
    values: [{ field: "qty", agg: "sum" }],
  });
  assert.equal(cell(r, ["north"], ["2025-03"]), null);
  assert.equal(cell(r, ["south"], ["2025-01"]), null);
  const onlyMissing = pivot(toTable({ fields: FIELDS, rows: [["2025-01-01", "x", "web", null]] }), {
    rows: [{ field: "region" }],
    values: [{ field: "qty", agg: "sum" }],
  });
  assert.equal(onlyMissing.rows[0].total[0], null);
});

test("include and exclude filters", () => {
  const view = f => pivot(TABLE, { rows: [{ field: "region" }], values: [{ field: "qty", agg: "sum" }], filters: f });
  const web = view({ channel: { include: ["web"] } });
  assert.deepEqual(web.rows.map(r => [r.key[0], r.total[0]]), [["north", 6], ["south", 3]]);
  assert.deepEqual([web.stats.rowsIn, web.stats.rowsUsed, web.stats.groups], [7, 3, 2]);
  const noBlank = view({ channel: { exclude: [null] }, region: { exclude: ["north"] } });
  assert.deepEqual(noBlank.rows.map(r => r.total[0]), [4]);
  assert.throws(() => view({ channel: { include: ["web"], exclude: ["store"] } }), /not both/);
});

test("shares of the grand, row and column total", () => {
  const base = { rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] };
  const total = pivot(TABLE, { ...base, showAs: "share_of_total" });
  assert.equal(cell(total, ["north"], ["store"]), 14 / 26);
  assert.equal(total.totals.grand[0], 1);
  const row = pivot(TABLE, { ...base, showAs: "share_of_row" });
  assert.equal(cell(row, ["south"], ["web"]), 3 / 6);
  assert.equal(row.rows[1].total[0], 1);
  const col = pivot(TABLE, { ...base, showAs: "share_of_column" });
  assert.equal(cell(col, ["north"], ["store"]), 14 / 15);
  assert.deepEqual(col.totals.columns.map(c => c[0]), [1, 1, 1]);
  assert.equal(cell(col, ["north"], [null]), null); // an empty cell has no share
});

test("sorting by label, by value and by a column, within each group", () => {
  const base = { rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] };
  assert.deepEqual(pivot(TABLE, { ...base, sort: { by: "label", dir: "desc" } }).rows.map(r => r.key[0]), ["south", "north"]);
  assert.deepEqual(pivot(TABLE, { ...base, sort: { by: "value", dir: "asc" } }).rows.map(r => r.key[0]), ["south", "north"]);
  assert.deepEqual(pivot(TABLE, { ...base, sort: { by: "value", dir: "desc" } }).rows.map(r => r.key[0]), ["north", "south"]);
  // only south has a blank channel: north has no value in that column and goes last in both directions
  for (const dir of ["asc", "desc"]) {
    const r = pivot(TABLE, { ...base, sort: { by: "column", key: [null], dir } });
    assert.deepEqual(r.rows.map(x => x.key[0]), ["south", "north"]);
  }
});

test("subtotals put each outer group before its children", () => {
  const view = {
    rows: [{ field: "region" }, { field: "channel" }],
    values: [{ field: "qty", agg: "sum" }],
    subtotals: true,
    sort: { by: "value", dir: "desc" },
  };
  const r = pivot(TABLE, view);
  assert.deepEqual(
    r.rows.map(x => [x.key.join("/"), x.depth, x.group, x.total[0]]),
    [
      ["north", 0, true, 20],
      ["north/store", 1, false, 14],
      ["north/web", 1, false, 6],
      ["south", 0, true, 6],
      ["south/web", 1, false, 3],
      ["south/", 1, false, 2],
      ["south/store", 1, false, 1],
    ],
  );
  const flat = pivot(TABLE, { ...view, subtotals: false });
  assert.deepEqual(flat.rows.map(x => x.key.join("/")), ["north/store", "north/web", "south/web", "south/", "south/store"]);
  assert.equal(flat.stats.groups, 5);
});

test("with no row or column field the grand total still holds", () => {
  const r = pivot(TABLE, { values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "count" }] });
  assert.deepEqual([r.rows, r.columns, r.totals.grand], [[], [], [26, 7]]);
});

test("a view the table cannot answer is rejected with a clear message", () => {
  assert.throws(() => pivot(TABLE, { rows: [{ field: "nope" }] }), /unknown field "nope"/);
  assert.throws(() => pivot(TABLE, { rows: [{ field: "region", grain: "month" }] }), /time grain applies to a time field only/);
  assert.throws(() => pivot(TABLE, { values: [{ field: "qty", agg: "mode" }] }), /unknown aggregation "mode"/);
  assert.throws(() => pivot(TABLE, { values: [{ field: "region", agg: "sum" }] }), /sum needs a measure/);
  assert.throws(() => pivot(TABLE, { showAs: "percent" }), /unknown showAs/);
});

test("distinct values with their counts, in label order", () => {
  assert.deepEqual(distinctValues(TABLE, "channel"), [
    { value: "store", count: 3 },
    { value: "web", count: 3 },
    { value: null, count: 1 },
  ]);
});

test("past maxColumns the smallest columns fold into Other, aggregated from their rows", () => {
  const view = { rows: [{ field: "region" }], columns: [{ field: "day" }], values: [{ field: "qty", agg: "median" }] };
  assert.equal(pivot(TABLE, view).columns.length, 7);
  const r = pivot(TABLE, view, { maxColumns: 3 });
  // kept: the two days with the largest median (10 on Feb 3, 6 on Jan 7); the other five fold
  assert.deepEqual(r.columns.map(c => c.key), [["2025-01-07"], ["2025-02-03"], [OTHER]]);
  assert.equal(r.stats.folded, 5);
  assert.equal(cell(r, ["south"], [OTHER]), 2); // median of 1, 3, 2 (the missing quantity ignored)
  assert.equal(cell(r, ["north"], [OTHER]), 4);
  assert.equal(r.totals.grand[0], pivot(TABLE, view).totals.grand[0]);
  assert.equal(pivot(TABLE, view, { maxColumns: 8 }).stats.folded, 0);
});

test("a key part reads as its value, (blank) or Other", () => {
  assert.deepEqual([partLabel("web"), partLabel(null), partLabel(OTHER), partLabel(3)], ["web", "(blank)", "Other", "3"]);
});

test("CSV holds the row labels, raw cells, subtotals and totals", () => {
  const r = pivot(TABLE, {
    rows: [{ field: "region" }, { field: "channel" }],
    columns: [{ field: "day", grain: "quarter" }],
    values: [{ field: "qty", agg: "sum" }],
    subtotals: true,
  });
  const csv = toCsv(r, { rowFields: ["Region", "Channel"], values: ["Sum of Quantity"] }).split("\r\n");
  assert.deepEqual(csv.slice(0, 4), [
    "Region,Channel,2025-Q1,Total",
    "north,Subtotal,20,20",
    "north,store,14,14",
    "north,web,6,6",
  ]);
  assert.equal(csv.at(-2), "Total,,26,26");
  assert.equal(csv.at(-1), "");
});

test("CSV quotes separators and defuses a formula-like label", () => {
  const t = toTable({
    fields: FIELDS,
    rows: [
      ["2025-01-01", "=HYPERLINK(1)", "a,b", 1],
      ["2025-01-01", "-x", 'say "hi"', -2],
    ],
  });
  const r = pivot(t, { rows: [{ field: "region" }, { field: "channel" }], values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "count" }] });
  const csv = toCsv(r, { rowFields: ["Region", "Channel"], values: ["Sum", "Count"] }).split("\r\n");
  assert.equal(csv[0], "Region,Channel,Total · Sum,Total · Count");
  assert.equal(csv[1], "'-x,\"say \"\"hi\"\"\",-2,1");
  assert.equal(csv[2], "'=HYPERLINK(1),\"a,b\",1,1");
});

test("a view from a link is checked for shape before it is used", () => {
  assert.equal(viewError({ rows: [{ field: "region" }], values: [{ field: "qty", agg: "sum" }], sort: { by: "column", key: ["web"], dir: "desc" } }), null);
  assert.equal(viewError({}), null);
  const bad = [
    [null, "must be an object"],
    [{ rows: null }, "rows must be a list"],
    [{ rows: [{}] }, "each of rows needs a field name"],
    [{ columns: [{ field: "day", grain: "hour" }] }, "unknown time grain"],
    [{ values: [{ field: "qty" }] }, "unknown aggregation"],
    [{ filters: [] }, "filters must be an object"],
    [{ filters: { region: { include: ["a"], exclude: [] } } }, "one include or exclude list"],
    [{ filters: { region: { include: "a" } } }, "one include or exclude list"],
    [{ showAs: "percent" }, "unknown showAs"],
    [{ showAs: null }, "unknown showAs"],
    [{ sort: null }, "sort.by"],
    [{ sort: { by: "size" } }, "sort.by"],
    [{ sort: { by: "column" } }, "needs the column's key"],
    [{ subtotals: "yes" }, "subtotals must be true or false"],
    [{ rowz: [] }, "unknown keys"],
  ];
  for (const [view, message] of bad) assert.match(viewError(view), new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), JSON.stringify(view));
});

test("no label can merge two columns or pass for the folded Other column", () => {
  const t = toTable({
    fields: FIELDS,
    rows: [
      ["2025-01-01", "a\u0001b", "x", 1],
      ["2025-01-01", "a", "b\u0001x", 2],
      ["2025-01-01", "\u0002other", "x", 4],
      ["2025-01-01", "null", "x", 8],
      ["2025-01-01", null, "x", 16],
    ],
  });
  const r = pivot(t, { columns: [{ field: "region" }, { field: "channel" }], values: [{ field: "qty", agg: "sum" }] });
  assert.equal(r.columns.length, 5);
  assert.deepEqual(r.totals.columns.map(c => c[0]).sort((a, b) => a - b), [1, 2, 4, 8, 16]);
  const folded = pivot(t, { columns: [{ field: "region" }], values: [{ field: "qty", agg: "sum" }] }, { maxColumns: 3 });
  assert.deepEqual(folded.columns.map(c => c.key[0]), ["null", null, OTHER]); // the two largest kept, blank last; "\u0002other" folds like any value
  assert.equal(folded.totals.columns[2][0], 7);
  assert.equal(partLabel("\u0002other"), "\u0002other");
});

test("rows sort by the share shown, not the raw value underneath", () => {
  const base = { rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] };
  // web: north 6 of 20 (30 %), south 3 of 6 (50 %); by raw value north comes first, by share of row south does
  const raw = pivot(TABLE, { ...base, sort: { by: "column", key: ["web"], dir: "desc" } });
  assert.deepEqual(raw.rows.map(r => r.key[0]), ["north", "south"]);
  const shares = pivot(TABLE, { ...base, showAs: "share_of_row", sort: { by: "column", key: ["web"], dir: "desc" } });
  assert.deepEqual(shares.rows.map(r => r.key[0]), ["south", "north"]);
  assert.deepEqual(shares.rows.map(r => cell(shares, r.key, ["web"])), [0.5, 0.3]);
  const col = pivot(TABLE, { ...base, showAs: "share_of_column", sort: { by: "column", key: ["web"], dir: "asc" } });
  assert.deepEqual(col.rows.map(r => r.key[0]), ["south", "north"]);
});

test("a filter's kept count ignores values the data does not hold", () => {
  const values = distinctValues(TABLE, "channel"); // store, web, (blank)
  assert.equal(keptCount(values, { exclude: ["gone", "web"] }), 2);
  assert.equal(keptCount(values, { include: ["gone", "web"] }), 1);
  assert.equal(keptCount(values, { exclude: [] }), 3);
});

test("the fold keeps the columns largest in size, a large negative one included", () => {
  const t = toTable({
    fields: FIELDS,
    rows: [["2025-01-01", "r", "loss", -100], ["2025-01-01", "r", "gain", 10], ["2025-01-01", "r", "tiny", 1], ["2025-01-01", "r", "small", -2]],
  });
  const r = pivot(t, { columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] }, { maxColumns: 3 });
  assert.deepEqual(r.columns.map(c => c.key[0]), ["gain", "loss", OTHER]);
  assert.equal(r.totals.columns[2][0], -1); // tiny and small, aggregated from their rows
});
