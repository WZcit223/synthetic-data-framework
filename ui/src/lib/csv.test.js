// Tests for the CSV writers: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { csvCell, tableCsv } from "./csv.js";

const FIELDS = [
  { name: "sku_id", label: "SKU", kind: "dimension" },
  { name: "qty", label: "Quantity", kind: "measure", unit: "units" },
];

test("a flat table writes a header of labels, then one line per row", () => {
  assert.equal(tableCsv(FIELDS, [["SKU-1", 3], ["SKU-2", 0.5]]), "SKU,Quantity\r\nSKU-1,3\r\nSKU-2,0.5\r\n");
  assert.equal(tableCsv(FIELDS, []), "SKU,Quantity\r\n");
});

test("a blank cell is empty, never 0", () => {
  assert.equal(tableCsv(FIELDS, [["SKU-1", null]]), "SKU,Quantity\r\nSKU-1,\r\n");
});

test("the flat writer quotes separators and defuses a formula-like text", () => {
  const csv = tableCsv(FIELDS, [["=HYPERLINK(1)", 1], ["-x", -2], ['say "hi", twice', 3]]).split("\r\n");
  assert.equal(csv[1], "'=HYPERLINK(1),1");
  assert.equal(csv[2], "'-x,-2"); // a text is defused; a negative number stays a number
  assert.equal(csv[3], '"say ""hi"", twice",3');
});

test("every character a spreadsheet reads as a formula start is defused", () => {
  for (const c of ["=", "+", "-", "@", "\t", "\r"]) assert.ok(csvCell(c + "1").startsWith(c === "\r" ? "\"'" : "'"), JSON.stringify(c));
  assert.equal(csvCell("plain"), "plain");
  assert.equal(csvCell(null), "");
});
