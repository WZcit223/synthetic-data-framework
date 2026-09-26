// @vitest-environment jsdom
// Tests for the table mapping: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { cellText, columns, records } from "./config.js";

const FIELDS = [
  { name: "sku_id", label: "SKU", kind: "dimension" },
  { name: "day", label: "Day", kind: "time" },
  { name: "qty", label: "Quantity", kind: "measure", unit: "units" },
];

// A stand-in for the cell Tabulator hands a formatter.
function cell(value, data = {}) {
  const el = document.createElement("div");
  return { getValue: () => value, getData: () => data, getElement: () => el, el };
}

test("an API table is taken as it is: titles, alignment and sort order come from the fields", () => {
  const cols = columns(FIELDS);
  assert.deepEqual(cols.map(c => c.field), ["sku_id", "day", "qty"]);
  assert.deepEqual(cols.map(c => c.title), ["SKU", "Day", "Quantity (units)"]);
  assert.deepEqual(cols.map(c => c.hozAlign), ["left", "left", "right"]);
  assert.deepEqual(cols.map(c => c.sorter), ["string", "string", "number"]);
  assert.ok(cols.every(c => c.headerSort));
});

test("a title is text too: a label from the API is shown, not run", () => {
  const [col] = columns([{ name: "p", label: '<img src=x onerror="alert(1)">', kind: "measure" }]);
  const node = col.titleFormatter({ getValue: () => col.title });
  assert.equal(node.nodeType, 3);
  assert.equal(node.textContent, '<img src=x onerror="alert(1)">');
});

test("rows become records keyed by field name", () => {
  assert.deepEqual(records(FIELDS, [["SKU-1", "2025-01-01", 3]]), [{ sku_id: "SKU-1", day: "2025-01-01", qty: 3 }]);
});

test("a cell is text, never HTML, and a blank reads as a dash", () => {
  const [sku, , qty] = columns(FIELDS);
  const node = sku.formatter(cell("<b>x</b>"));
  assert.equal(node.nodeType, 3); // a text node: markup from the API is shown, not run
  assert.equal(node.textContent, "<b>x</b>");
  assert.equal(qty.formatter(cell(1234.5)).textContent, "1,234.5");
  assert.equal(qty.formatter(cell(null)).textContent, "–");
  assert.equal(cellText(0), "0");
});

test("a page's formatter and tone apply to their field", () => {
  const cols = columns(FIELDS, { format: { qty: v => `${v} u` }, tone: { qty: v => (v < 0 ? "bad" : null) } });
  const neg = cell(-2);
  assert.equal(cols[2].formatter(neg).textContent, "-2 u");
  assert.ok(neg.el.classList.contains("tone-bad"));
  const pos = cell(2);
  cols[2].formatter(pos);
  assert.equal(pos.el.classList.length, 0);
});

test("a field may set its column's minimum width; otherwise it fits the title", () => {
  const [sku, , qty] = columns([{ ...FIELDS[0], minWidth: 230 }, FIELDS[1], FIELDS[2]]);
  assert.equal(sku.minWidth, 230);
  assert.equal(qty.minWidth, Math.max(72, 8 * "Quantity".length + 34));
});
