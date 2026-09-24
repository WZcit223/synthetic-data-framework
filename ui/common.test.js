// Tests for the shared formatting: node --test ui/*.test.js
import assert from "node:assert/strict";
import { test } from "node:test";

import { compactFormatter, describeDetail, esc, valueFormatter } from "./common.js";

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

test("an API error detail reads as one line", () => {
  assert.equal(describeDetail("unknown dataset 'x'"), "unknown dataset 'x'");
  assert.equal(
    describeDetail([{ loc: ["body", "policies", 0, "service_level"], msg: "Input should be less than 1" }]),
    "policies.0.service_level: Input should be less than 1",
  );
  assert.equal(describeDetail(undefined), null);
});

test("escaping covers every markup character", () => {
  assert.equal(esc(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
  assert.equal(esc(null), "");
});
