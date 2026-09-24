// Tests for the Effects page's helpers: node --test ui/*.test.js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  amount, axisFor, budgetView, byMetric, COVERS, coversZero, defaultRequest, exploreLink, fitRequest, intervalText, nextPolicy,
  reading, readRequestHash, records, relativeText, replicateRows, requestError, requestHash,
} from "./effects-model.js";
import { sourceError } from "./sources.js";

const CATALOG = {
  interventions: ["baseline", "promo_spike", "supply_disruption"],
  policies: [
    { kind: "naive", params: [{ name: "lead_time_days", type: "int", default: 7, min: 1, max: 90, exclusive: false, nullable: false }] },
    {
      kind: "service-level",
      params: [
        { name: "service_level", type: "float", default: 0.95, min: 0.5, max: 1, exclusive: true, nullable: false },
        { name: "lead_time_days", type: "int", default: 7, min: 1, max: 90, exclusive: false, nullable: false },
      ],
    },
  ],
  outcomes: ["replenishment_need", "active_stockouts", "simulated_cost"],
  max_per_list: 6,
  effects: { max_replicates: 20 },
};

const effect = (metric, effect, lo, hi, extra = {}) => ({ intervention: "promo_spike", policy: "service-level-95", metric, effect, ci_low: lo, ci_high: hi, ...extra });

test("records reads a {fields, rows} table as objects", () => {
  const t = { fields: [{ name: "metric" }, { name: "effect" }], rows: [["holding_cost", 79790], ["unmet_units", -0.26]] };
  assert.deepEqual(records(t), [{ metric: "holding_cost", effect: 79790 }, { metric: "unmet_units", effect: -0.26 }]);
});

test("an interval covers 0 at its edges, and a zero-width interval at 0 covers it", () => {
  assert.equal(coversZero(effect("m", -0.26, -1.39, 0.87)), true);
  assert.equal(coversZero(effect("m", 79790, 72247, 87333)), false);
  assert.equal(coversZero(effect("m", -3, -5, -1)), false);
  assert.equal(coversZero(effect("m", 2, 0, 4)), true); // ends at 0: 0 is inside
  assert.equal(coversZero(effect("m", -2, -4, 0)), true);
  assert.equal(coversZero(effect("active_stockouts", 0, 0, 0)), true); // an unmoved metric
  assert.equal(coversZero(effect("m", 3, 3, 3)), false); // a zero-width interval away from 0
});

test("the reading says in words what the colour shows", () => {
  assert.equal(reading(effect("m", -0.26, -1.39, 0.87)), COVERS);
  assert.equal(reading(effect("m", 79790, 72247, 87333)), "above 0");
  assert.equal(reading(effect("m", -3, -5, -1)), "below 0");
});

test("effects are grouped by metric in the server's order", () => {
  const rows = [effect("unmet_units", 1, 0, 2), effect("holding_cost", 2, 1, 3), effect("unmet_units", 3, 2, 4, { policy: "naive" })];
  const groups = byMetric(rows);
  assert.deepEqual(groups.map(g => g.metric), ["unmet_units", "holding_cost"]);
  assert.deepEqual(groups[0].rows.map(r => r.policy), ["service-level-95", "naive"]);
});

test("each chart's axis keeps 0 inside, whatever side the values are on", () => {
  const up = axisFor([72247, 87333]);
  assert.equal(up.lo, 0);
  assert.ok(up.hi >= 87333 && up.ticks.includes(0));
  const down = axisFor([-8, -3]);
  assert.ok(down.lo <= -8 && down.hi === 0 && down.ticks.includes(0));
  const both = axisFor([-1.39, 0.87]);
  assert.ok(both.lo <= -1.39 && both.hi >= 0.87 && both.ticks.includes(0));
  const flat = axisFor([0, 0, null]);
  assert.ok(flat.hi > flat.lo && flat.ticks.includes(0)); // an unmoved metric still gets a scale
});

test("the replicate view reads each paired difference from the table, subtracting nothing", () => {
  const effects = [effect("unmet_units", -0.5, -1, 0), effect("holding_cost", 5, 4, 6)];
  const replicates = [
    { replicate: "0", seed: "42", intervention: "baseline", policy: "service-level-95", metric: "unmet_units", value: 1, difference: null },
    { replicate: "0", seed: "42", intervention: "promo_spike", policy: "service-level-95", metric: "unmet_units", value: 0, difference: -1 },
    { replicate: "1", seed: "43", intervention: "promo_spike", policy: "service-level-95", metric: "unmet_units", value: 7, difference: 0 },
    { replicate: "0", seed: "42", intervention: "promo_spike", policy: "service-level-95", metric: "holding_cost", value: 9, difference: 5 },
  ];
  const rows = replicateRows(effects, replicates, "unmet_units");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].effect, -0.5); // the mean is the server's effect
  assert.deepEqual(rows[0].dots, [{ replicate: "0", seed: "42", difference: -1 }, { replicate: "1", seed: "43", difference: 0 }]);
});

test("numbers are rounded as sdf effects rounds them", () => {
  const en = { locale: "en-US" };
  assert.equal(amount(137572.4, en), "137,572");
  assert.equal(amount(79790, { signed: true, ...en }), "+79,790");
  assert.equal(amount(-0.263, { signed: true, ...en }), "−0.263");
  assert.equal(amount(46.51, en), "46.5");
  assert.equal(amount(6.79e-6, { signed: true, ...en }), "+6.79e−6");
  assert.equal(amount(0.0005, en), "0.0005"); // fixed down to 1e-4, as Python's .3g
  assert.equal(amount(0.000123, en), "0.000123");
  assert.equal(amount(5e-5, en), "5e−5"); // trailing zeros dropped, as .3g drops them
  assert.equal(amount(0, { signed: true, ...en }), "0");
  assert.equal(amount(null), "–");
  assert.equal(intervalText({ ci_low: -1.39, ci_high: 0.866 }, "en-US"), "−1.39 to +0.866");
  assert.equal(relativeText(0.58, "en-US"), "+58%");
  assert.equal(relativeText(-0.4412, "en-US"), "−44.1%");
  assert.equal(relativeText(6.79e-6 / 0.99, "en-US"), "0%"); // rounds to 0: no sign
  assert.equal(relativeText(null), "–"); // no baseline to compare with
});

test("the budget shown is the server's check_only answer, as it is", () => {
  const within = budgetView({ work: 472500, max_work: 1200000, within_budget: true, size: "10 replicates × 2 arms" }, "en-US");
  assert.deepEqual(within, { over: false, share: 472500 / 1200000, text: "Work 472,500 of 1,200,000: 10 replicates × 2 arms." });
  const over = budgetView({ work: 4612500, max_work: 1200000, within_budget: false, size: "20 replicates × 7 arms" }, "en-US");
  assert.equal(over.over, true);
  assert.equal(over.share, 1);
  assert.match(over.text, /^Over the budget: work 4,612,500 exceeds 1,200,000 \(20 replicates × 7 arms\)/);
  // the server decides: the page never second-guesses within_budget from the numbers
  assert.equal(budgetView({ work: 5, max_work: 1, within_budget: true, size: "s" }).over, false);
});

test("the default request is a study of promo_spike under the default service level", () => {
  assert.deepEqual(defaultRequest(CATALOG), {
    interventions: ["promo_spike"],
    policies: [{ kind: "service-level", service_level: 0.95, lead_time_days: 7 }],
    outcomes: ["simulated_cost"],
    replicates: 10,
    confidence: 0.95,
  });
});

test("a linked request is fitted to the catalogue, naming what it drops", () => {
  const { request, dropped } = fitRequest(
    {
      interventions: ["supply_disruption", "baseline", "gone"],
      policies: [{ kind: "naive", lead_time_days: 3 }, { kind: "mystery" }],
      outcomes: ["active_stockouts"],
      replicates: 4,
      confidence: 0.9,
    },
    CATALOG,
  );
  assert.deepEqual(request, {
    interventions: ["supply_disruption"],
    policies: [{ kind: "naive", lead_time_days: 3 }],
    outcomes: ["active_stockouts"],
    replicates: 4,
    confidence: 0.9,
  });
  assert.deepEqual(dropped, ["baseline", "gone", "mystery"]);
  assert.deepEqual(fitRequest({ confidence: 0.42, outcomes: [] }, CATALOG).request, defaultRequest(CATALOG));
});

test("Add policy never repeats a policy already on the form", () => {
  const sl = { kind: "service-level", service_level: 0.95, lead_time_days: 7 };
  assert.deepEqual(nextPolicy(CATALOG, [sl]), { kind: "naive", lead_time_days: 7 }); // an unused kind first
  const naive = { kind: "naive", lead_time_days: 7 };
  assert.deepEqual(nextPolicy(CATALOG, [sl, naive]), { ...sl, service_level: 0.9 }); // then an unused level
  assert.deepEqual(nextPolicy(CATALOG, [sl, naive, { ...sl, service_level: 0.9 }]), { ...sl, service_level: 0.99 });
});

test("the form refuses what the server would", () => {
  const ok = defaultRequest(CATALOG);
  assert.equal(requestError(ok, CATALOG), null);
  assert.match(requestError({ ...ok, interventions: [] }, CATALOG), /at least one intervention/);
  assert.match(requestError({ ...ok, outcomes: [] }, CATALOG), /at least one outcome/);
  assert.match(requestError({ ...ok, replicates: 21 }, CATALOG), /from 2 to 20/);
  assert.match(requestError({ ...ok, replicates: 1 }, CATALOG), /from 2 to 20/);
  const edge = { ...ok, policies: [{ kind: "service-level", service_level: 1, lead_time_days: 7 }] };
  assert.match(requestError(edge, CATALOG), /Policy 1, service level: between 0.5 and 1, both excluded/);
  const nan = { ...ok, policies: [{ kind: "naive", lead_time_days: NaN }] };
  assert.match(requestError(nan, CATALOG), /Policy 1, lead time days: enter a/);
});

test("the address keeps the request, and a broken one says so", () => {
  const request = defaultRequest(CATALOG);
  assert.deepEqual(readRequestHash(requestHash(request)), { request });
  assert.equal(readRequestHash(""), null);
  assert.equal(readRequestHash("#other"), null);
  assert.deepEqual(readRequestHash("#request=%7B"), { error: "the request in this link is not valid JSON" });
  assert.deepEqual(readRequestHash("#request=%5B%5D"), { error: "the link holds no request" });
});

test("an Explore link names the effects source and round-trips through Explore's validator", () => {
  const request = { ...defaultRequest(CATALOG), check_only: true };
  for (const table of ["effects", "replicates"]) {
    const link = exploreLink(request, table);
    assert.match(link, /^explore\.html#view=/);
    const { source } = JSON.parse(decodeURIComponent(link.slice("explore.html#view=".length)));
    assert.equal(sourceError(source), null);
    assert.deepEqual(source, { effects: { request: defaultRequest(CATALOG), table } }); // check_only is never carried
  }
});

// -- the "Estimate from data" view ---------------------------------------------------------------

import {
  SWEEP, defaultEstimateRequest, estimateHash, estimateRequestError, estimatesLink, estimatorColors, fitEstimateRequest,
  readEstimateHash, scoreReading, sweepRequests, sweepSeries,
} from "./estimate-model.js";
import { OTHER, SERIES } from "./palette.js";

const ESTIMATORS = {
  estimators: ["difference-in-means", "ipw", "regression-adjustment", "median-difference"].map(name => ({ name, description: name })),
  unavailable: { "dowhy-backdoor": "needs dowhy" },
  limits: { max_rows: 40000, max_estimators: 6, max_seconds: 30 },
  benchmark: {
    params: [
      { name: "uplift", type: "float", default: 0.3, min: -0.9, max: 3, exclusive: false, nullable: false },
      { name: "confounding", type: "float", default: 1, min: 0, max: 3, exclusive: false, nullable: false },
      { name: "noise", type: "float", default: 0.25, min: 0, max: 1, exclusive: false, nullable: false },
      { name: "seed", type: "int", default: 7, min: 0, max: null, exclusive: false, nullable: false },
    ],
    question: { treatment: "promoted", outcome: "weekly_units", covariates: ["log_demand", "abc_class", "log_price"], treated_value: 1 },
  },
};

test("the view starts from the mounted built-ins, the benchmark's defaults and its whole adjustment set", () => {
  const r = defaultEstimateRequest(ESTIMATORS);
  assert.deepEqual(r.estimators, ["difference-in-means", "regression-adjustment", "ipw"]);
  assert.deepEqual(r.benchmark, { uplift: 0.3, confounding: 1, noise: 0.25, seed: 7 });
  assert.deepEqual(r.question.covariates, ["log_demand", "abc_class", "log_price"]);
  r.question.covariates.pop();
  assert.equal(ESTIMATORS.benchmark.question.covariates.length, 3); // a copy: editing the request never edits the catalogue
});

test("each estimator keeps the colour of its place in the catalogue", () => {
  const colors = estimatorColors([...ESTIMATORS.estimators.map(e => e.name), "a", "b", "c", "d", "e"]);
  assert.equal(colors.get("difference-in-means"), SERIES[0]);
  assert.equal(colors.get("median-difference"), SERIES[3]);
  assert.equal(colors.get("e"), OTHER); // a ninth folds to grey, never a generated hue
});

test("a linked estimation is fitted to the catalogue, naming what it drops", () => {
  const { request, dropped } = fitEstimateRequest(
    {
      estimators: ["ipw", "econml-dml", "ipw"],
      benchmark: { confounding: 2, seed: 3 },
      question: { covariates: ["log_price", "sku_id", "log_demand"] },
      confidence: 0.9,
    },
    ESTIMATORS,
  );
  assert.deepEqual(request.estimators, ["ipw"]);
  assert.deepEqual(request.benchmark, { uplift: 0.3, confounding: 2, noise: 0.25, seed: 3 });
  assert.deepEqual(request.question.covariates, ["log_demand", "log_price"]); // the benchmark's order
  assert.equal(request.confidence, 0.9);
  assert.deepEqual(dropped, ["econml-dml", "sku_id"]);
  assert.deepEqual(fitEstimateRequest(null, ESTIMATORS).request, defaultEstimateRequest(ESTIMATORS));
});

test("the view refuses what the server would, from the published bounds", () => {
  const ok = defaultEstimateRequest(ESTIMATORS);
  assert.equal(estimateRequestError(ok, ESTIMATORS), null);
  assert.match(estimateRequestError({ ...ok, estimators: [] }, ESTIMATORS), /at least one estimator/);
  assert.match(estimateRequestError({ ...ok, estimators: Array(7).fill("ipw") }, ESTIMATORS), /At most 6 estimators/);
  assert.match(estimateRequestError({ ...ok, benchmark: { ...ok.benchmark, confounding: 3.5 } }, ESTIMATORS), /Benchmark confounding: from 0 to 3/);
  assert.match(estimateRequestError({ ...ok, benchmark: { ...ok.benchmark, seed: -1 } }, ESTIMATORS), /Benchmark seed: at least 0/);
  assert.match(estimateRequestError({ ...ok, benchmark: { ...ok.benchmark, noise: "" } }, ESTIMATORS), /Benchmark noise: enter a value/);
});

test("the view's address keeps its request, and tells the effects view's apart", () => {
  const r = defaultEstimateRequest(ESTIMATORS);
  assert.deepEqual(readEstimateHash(estimateHash(r)), { request: r });
  assert.deepEqual(readEstimateHash("#estimate"), {});
  assert.deepEqual(readEstimateHash("#estimate="), {}); // an empty request is still this view
  assert.equal(readEstimateHash("#estimates"), null);
  assert.equal(readEstimateHash("#request=%7B%7D"), null);
  assert.equal(readEstimateHash(""), null);
  assert.deepEqual(readEstimateHash("#estimate=%7B"), { error: "the request in this link is not valid JSON" });
});

test("a score row reads in words", () => {
  const row = over => ({ effect: 6.3, ci_low: 3, ci_high: 9.6, covers: "yes", seconds: 0.01, ...over });
  assert.equal(scoreReading(row()), "covers the truth");
  assert.equal(scoreReading(row({ covers: "no" })), "misses the truth");
  assert.equal(scoreReading(row({ ci_low: null, ci_high: null, covers: null })), "no interval");
  assert.equal(scoreReading(row({ covers: null })), "no truth to compare");
  assert.equal(scoreReading(row({ effect: null, ci_low: null, ci_high: null, covers: null })), "error");
  assert.equal(scoreReading(row({ effect: null, seconds: null })), "not run");
});

test("the sweep varies only the confounding and reads each step's bias from the scores", () => {
  const r = defaultEstimateRequest(ESTIMATORS);
  const requests = sweepRequests(r);
  assert.deepEqual(requests.map(q => q.benchmark.confounding), SWEEP);
  assert.deepEqual(SWEEP, [0, 0.75, 1.5, 2.25, 3]);
  assert.ok(requests.every(q => q.benchmark.seed === 7 && q.estimators === r.estimators));
  assert.equal(r.benchmark.confounding, 1); // the view's own request is untouched
  const steps = [
    [{ estimator: "a", bias: 0.1 }, { estimator: "b", bias: 1 }],
    [{ estimator: "a", bias: null }, { estimator: "b", bias: 5 }],
  ];
  assert.deepEqual(sweepSeries(steps, ["a", "b", "c"]), [
    { name: "a", values: [0.1, null] },
    { name: "b", values: [1, 5] },
    { name: "c", values: [null, null] },
  ]);
});

test("an Explore link to the scores or the observed rows round-trips through Explore's validator", () => {
  const request = defaultEstimateRequest(ESTIMATORS);
  for (const table of ["scores", "data"]) {
    const { source } = JSON.parse(decodeURIComponent(estimatesLink(request, table).slice("explore.html#view=".length)));
    assert.equal(sourceError(source), null);
    assert.deepEqual(source, { estimates: { request, table } });
  }
});
