// @vitest-environment jsdom
// Tests for PivotTable, with Tabulator replaced by a recorder: npm test
import assert from "node:assert/strict";
import { render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import { test, vi } from "vitest";

import { pivot, toTable } from "../../lib/pivot.js";

const made = [];
vi.mock("tabulator-tables", () => {
  class Tabulator {
    static registerModule() {}
    constructor(el, options) {
      this.options = options;
      this.handlers = {};
      made.push(this);
    }
    on(event, fn) { this.handlers[event] = fn; }
    destroy() { this.destroyed = true; }
  }
  const m = {};
  return { Tabulator, FormatModule: m, FrozenColumnsModule: m, DataTreeModule: m, ColumnCalcsModule: m, InteractionModule: m, ResizeTableModule: m };
});

const { default: PivotTable } = await import("./PivotTable.svelte");

const TABLE = toTable({
  fields: [
    { name: "region", label: "Region", kind: "dimension" },
    { name: "channel", label: "Channel", kind: "dimension" },
    { name: "qty", label: "Quantity", kind: "measure", aggregate: "sum" },
  ],
  rows: [["north", "store", 4], ["north", "web", 6], ["south", "web", 3]],
});

function props(view, extra = {}) {
  const v = { rows: [], columns: [], values: [], filters: {}, showAs: "value", sort: { by: "label", dir: "asc" }, subtotals: false, ...view };
  return {
    result: pivot(TABLE, v), view: v, rowTitles: v.rows.map(a => a.field), valueTitles: v.values.map(x => x.field),
    formats: v.values.map(() => String), totals: true, collapsed: new Set(), onsort: () => {}, ontoggle: () => {}, ...extra,
  };
}

test("a header click asks for the sort that header names", () => {
  made.length = 0;
  const asked = [];
  render(PivotTable, props({ rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }] }, { onsort: s => asked.push(s) }));
  flushSync();
  const t = made[0];
  const column = field => ({ getField: () => field, getSubColumns: () => [] });
  t.handlers.headerClick({}, column("c1_0"));
  t.handlers.headerClick({}, column("r0"));
  t.handlers.headerClick({}, column("t_0"));
  assert.deepEqual(asked, [{ by: "column", key: ["web"] }, { by: "label" }, { by: "value" }]);
});

test("a group of values sorts by its column; a higher group sorts nothing", () => {
  made.length = 0;
  const asked = [];
  const view = { rows: [{ field: "region" }], columns: [{ field: "channel" }], values: [{ field: "qty", agg: "sum" }, { field: "qty", agg: "max" }] };
  render(PivotTable, props(view, { onsort: s => asked.push(s) }));
  flushSync();
  const t = made[0];
  const column = field => ({ getField: () => field, getSubColumns: () => [] });
  const group = (...subs) => ({ getField: () => undefined, getSubColumns: () => subs });
  t.handlers.headerClick({}, group(column("c1_0"), column("c1_1")));
  t.handlers.headerClick({}, column("c1_1")); // a value header under it
  t.handlers.headerClick({}, group(group(column("c0_0")))); // a group of groups
  assert.deepEqual(asked, [{ by: "column", key: ["web"] }]);
});

test("the tree opens with the collapsed groups closed and reports each toggle; a new result rebuilds it", () => {
  made.length = 0;
  const toggled = [];
  const view = { rows: [{ field: "region" }, { field: "channel" }], values: [{ field: "qty", agg: "sum" }], subtotals: true };
  const { rerender, unmount } = render(PivotTable, props(view, { collapsed: new Set(['["north"]']), ontoggle: k => toggled.push(k) }));
  flushSync();
  const t = made[0];
  assert.equal(t.options.dataTree, true);
  assert.equal(t.options.columnCalcs, "table");
  const start = t.options.dataTreeStartExpanded;
  assert.equal(start({ getData: () => ({ _key: ["north"] }) }), false);
  assert.equal(start({ getData: () => ({ _key: ["south"] }) }), true);
  t.handlers.dataTreeRowCollapsed({ getData: () => ({ _key: ["south"] }) });
  t.handlers.dataTreeRowExpanded({ getData: () => ({ _key: ["north"] }) });
  assert.deepEqual(toggled, ['["south"]', '["north"]']);

  rerender(props({ ...view, sort: { by: "value", dir: "desc" } }, { collapsed: new Set(['["south"]']) }));
  flushSync();
  assert.equal(made.length, 2);
  assert.equal(t.destroyed, true);
  assert.equal(made[1].options.dataTreeStartExpanded({ getData: () => ({ _key: ["south"] }) }), false);
  unmount();
  assert.equal(made[1].destroyed, true);
});

test("the heat key and the cut note show under the table", () => {
  made.length = 0;
  const { container } = render(PivotTable, props({ rows: [{ field: "region" }], values: [{ field: "qty", agg: "sum" }] }, { heat: true }));
  flushSync();
  assert.match(container.querySelector(".heatkey").textContent, /qty\s*3.*10/s);
  assert.equal(container.querySelector(".more"), null);
});
