// Tests for the dashboard's policy comparison table: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { cheapestOutOfSample, comparisonTable } from "./comparison.js";

const row = (policy, extra = {}) => ({
  policy, skus_needing_order: 1, safety_stock_units: 2, unmet_units: 3, holding_cost: 4, order_cost: 5, ...extra,
});

test("one column per policy, whatever their number", () => {
  const t = comparisonTable({ horizon_days: 90, policies: [row("naive"), row("service-level-95"), row("cost-based")] });
  assert.deepEqual(t.fields.map(f => f.label), ["Metric", "naive", "service-level-95", "cost-based"]);
  assert.equal(t.rows.length, 5);
  assert.deepEqual(t.rows[0], ["SKUs to order", 1, 1, 1]);
});

test("the out-of-sample rows follow when the API measured them", () => {
  const t = comparisonTable({
    holdout_days: 30,
    policies: [row("a", { holdout_total_cost: 120, holdout_fill_rate: 0.9997 }), row("b", { holdout_total_cost: 60, holdout_fill_rate: 0.9966 })],
  });
  assert.deepEqual(t.rows.slice(5), [["Cost, last 30 days", 120, 60], ["Fill, last 30 days", "100.0%", "99.7%"]]);
  assert.equal(cheapestOutOfSample({ policies: [row("a", { holdout_total_cost: 120 }), row("b", { holdout_total_cost: 60 })] }).policy, "b");
  assert.equal(cheapestOutOfSample({ holdout_days: null, policies: [row("a")] }), null);
});
