// Tests for the Effects study form: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { policyRow, readForm, setKind, toForm } from "./form.js";

const CATALOG = {
  policies: [
    { kind: "service-level", params: [{ name: "service_level", type: "float", default: 0.95 }, { name: "lead_time_days", type: "int", default: 7 }] },
    { kind: "fixed", params: [{ name: "reorder_point", type: "int", default: 10 }] },
  ],
};
const REQUEST = {
  interventions: ["promo_spike"],
  policies: [{ kind: "service-level", service_level: 0.99, lead_time_days: 7 }],
  outcomes: ["simulated_cost"],
  replicates: 10,
  confidence: 0.95,
};

test("a request survives the form unchanged", () => {
  assert.deepEqual(readForm(toForm(REQUEST, CATALOG)), REQUEST);
});

test("an empty or unparsable number reads as NaN, so the checks name it", () => {
  const form = toForm(REQUEST, CATALOG);
  form.replicates = { text: "", bad: true };
  form.policies[0].values.service_level = { text: "", bad: false };
  const r = readForm(form);
  assert.ok(Number.isNaN(r.replicates));
  assert.ok(Number.isNaN(r.policies[0].service_level));
});

test("switching a policy's kind shows that kind's defaults, and switching back its own values", () => {
  const row = policyRow(REQUEST.policies[0], CATALOG);
  setKind(row, "fixed", CATALOG);
  assert.deepEqual(Object.keys(row.values), ["reorder_point"]);
  assert.equal(row.values.reorder_point.text, "10");
  setKind(row, "service-level", CATALOG);
  assert.equal(row.values.service_level.text, "0.99");
});

test("a policy of a kind not offered falls back to the first kind", () => {
  assert.equal(policyRow({ kind: "gone" }, CATALOG).kind, "service-level");
});
