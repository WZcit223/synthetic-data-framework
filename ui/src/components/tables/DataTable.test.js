// @vitest-environment jsdom
// Tests for DataTable, with Tabulator replaced by a recorder: npm test
import assert from "node:assert/strict";
import { render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import { test, vi } from "vitest";

const made = [];
vi.mock("tabulator-tables", () => {
  class Tabulator {
    static registerModule() {}
    constructor(el, options) {
      this.el = el;
      this.options = options;
      this.handlers = {};
      this.calls = [];
      made.push(this);
    }
    on(event, fn) { this.handlers[event] = fn; }
    built() { this.handlers.tableBuilt?.(); }
    setColumns(cols) { this.calls.push(["setColumns", cols.map(c => c.field)]); }
    replaceData(data) { this.calls.push(["replaceData", data]); }
    destroy() { this.destroyed = true; }
  }
  return { Tabulator, FormatModule: {}, SortModule: {}, ResizeTableModule: {} };
});

const { default: DataTable } = await import("./DataTable.svelte");

const FIELDS = [
  { name: "sku_id", label: "SKU", kind: "dimension" },
  { name: "qty", label: "Quantity", kind: "measure" },
];

test("a table is built from the API shape and refreshed with new rows", () => {
  made.length = 0;
  const { rerender, unmount } = render(DataTable, { fields: FIELDS, rows: [["SKU-1", 3]], sort: { column: "qty", dir: "desc" } });
  flushSync();
  const t = made[0];
  assert.deepEqual(t.options.columns.map(c => c.field), ["sku_id", "qty"]);
  assert.deepEqual(t.options.data, [{ sku_id: "SKU-1", qty: 3 }]);
  assert.deepEqual(t.options.initialSort, [{ column: "qty", dir: "desc" }]);

  // new rows before the table is built wait for it, and only the newest are applied
  rerender({ fields: FIELDS, rows: [["SKU-2", 4]] });
  flushSync();
  rerender({ fields: FIELDS, rows: [["SKU-3", 5]] });
  flushSync();
  assert.deepEqual(t.calls, []);
  t.built();
  assert.deepEqual(t.calls, [["setColumns", ["sku_id", "qty"]], ["replaceData", [{ sku_id: "SKU-3", qty: 5 }]]]);

  rerender({ fields: FIELDS, rows: [] });
  flushSync();
  assert.deepEqual(t.calls.at(-1), ["replaceData", []]);
  assert.equal(made.length, 1);

  unmount();
  assert.equal(t.destroyed, true);
});

test("a download button appears only when asked for", () => {
  const plain = render(DataTable, { fields: FIELDS, rows: [] });
  assert.equal(plain.container.querySelector("button"), null);
  const withCsv = render(DataTable, { fields: FIELDS, rows: [], download: "plan" });
  assert.equal(withCsv.container.querySelector("button")?.textContent, "CSV");
});
