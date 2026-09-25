// Tests for the Explore experiment form: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { defaultExperiment, experimentError, readExperimentForm, toExperimentForm } from "./experiment.js";

const CATALOG = {
  interventions: ["baseline", "promo_spike", "supplier_delay"],
  outcomes: ["fill_rate", "simulated_cost"],
  policies: [
    { kind: "service-level", params: [
      { name: "service_level", type: "float", default: 0.95, min: 0, max: 1, exclusive: true },
      { name: "lead_time_days", type: "int", default: 7, min: 1, max: 60 },
    ] },
    { kind: "min-max", params: [{ name: "days", type: "int", default: 14, min: 1, max: 90 }] },
  ],
  max_per_list: 6,
};

test("the default request: the first two interventions and policies, every outcome", () => {
  assert.deepEqual(defaultExperiment(CATALOG), {
    interventions: ["baseline", "promo_spike"],
    policies: [{ kind: "service-level" }, { kind: "min-max" }],
    outcomes: ["fill_rate", "simulated_cost"],
  });
});

test("a request fills the form and reads back, each parameter at its value or the default", () => {
  const request = { interventions: ["promo_spike"], policies: [{ kind: "service-level", service_level: 0.9 }], outcomes: ["fill_rate"] };
  assert.deepEqual(readExperimentForm(toExperimentForm(request, CATALOG)), {
    interventions: ["promo_spike"],
    policies: [{ kind: "service-level", service_level: 0.9, lead_time_days: 7 }],
    outcomes: ["fill_rate"],
  });
});

test("a field the browser cannot parse, or left empty, reads as NaN", () => {
  const form = toExperimentForm(defaultExperiment(CATALOG), CATALOG);
  form.policies[0].values.service_level = { text: "", bad: true };
  form.policies[1].values.days = { text: " ", bad: false };
  const [a, b] = readExperimentForm(form).policies;
  assert.ok(Number.isNaN(a.service_level) && Number.isNaN(b.days));
});

test("the checks the endpoint makes, before any request", () => {
  const ok = { interventions: ["baseline"], policies: [{ kind: "service-level", service_level: 0.9, lead_time_days: 7 }], outcomes: ["fill_rate"] };
  assert.equal(experimentError(ok, CATALOG), null);
  assert.equal(experimentError({ ...ok, interventions: [] }, CATALOG), "Choose at least one intervention.");
  assert.equal(experimentError({ ...ok, outcomes: [] }, CATALOG), "Choose at least one outcome.");
  const policy = p => experimentError({ ...ok, policies: [{ ...ok.policies[0], ...p }] }, CATALOG);
  assert.equal(policy({ service_level: NaN }), "Policy 1, service level: enter a number.");
  assert.equal(policy({ lead_time_days: 2.5 }), "Policy 1, lead time days: enter a whole number.");
  assert.equal(policy({ service_level: 1 }), "Policy 1, service level must be between 0 and 1, both excluded.");
  assert.equal(policy({ lead_time_days: 61 }), "Policy 1, lead time days must be from 1 to 60.");
});
