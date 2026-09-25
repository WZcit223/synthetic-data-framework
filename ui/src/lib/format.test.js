// Tests for the shared formatting: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { compactFormatter, fmt, valueFormatter } from "./format.js";

const f = (spec, v) => valueFormatter(spec, "en-US")(v);

test("values are formatted by unit, aggregation and share", () => {
  assert.equal(f({ unit: "currency", agg: "sum" }, 1234.5), "1,234.50");
  assert.equal(f({ unit: "units", agg: "sum" }, 28897), "28,897");
  assert.equal(f({ unit: "units", agg: "sum" }, 2.345), "2.35");
  assert.equal(f({ unit: "units", agg: "mean" }, 3), "3.00");
  assert.equal(f({ unit: "units", agg: "count" }, 28897), "28,897");
  assert.equal(f({ unit: "share", agg: "mean" }, 0.1234), "12.3%");
  assert.equal(f({ unit: "currency", agg: "sum", showAs: "share_of_row" }, 0.5), "50.0%");
  assert.equal(f({ unit: "currency" }, null), "–");
  assert.equal(f({ unit: "units" }, 0), "0"); // a real zero stays 0; only a blank is "–"
});

test("axis labels are compact", () => {
  assert.equal(compactFormatter({ unit: "currency" }, "en-US")(1_234_567), "1.2M");
  assert.equal(compactFormatter({ showAs: "share_of_total" }, "en-US")(0.25), "25%");
});

test("fmt writes a number, a blank as a dash, and text as it is (the page writes it as text)", () => {
  assert.equal(fmt(1234.567), (1234.567).toLocaleString(undefined, { maximumFractionDigits: 2 }));
  assert.equal(fmt(null), "–");
  assert.equal(fmt("<b>&</b>"), "<b>&</b>");
});
