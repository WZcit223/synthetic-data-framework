// Tests for the Forecasts page's pure helpers: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import {
  REFERENCE, backtestBody, defaultForecastRequest, fitForecastRequest, forecastHash, forecastRequestError,
  forecastSkus, forecasterColors, forecastsLink, levelQuantiles, quantileField, readForecastHash, scoreReading,
  skuForecasts, tableRecords, wapeByHorizon,
} from "./forecasts-model.js";

const param = (name, type, def, min = null, max = null, nullable = false) => ({ name, type, default: def, min, max, exclusive: false, nullable });

const CATALOG_BASE = {
  forecasters: [
    { name: "gradient-boosting", params: [param("max_iter", "int", 200, 10, 1000), param("seed", "int", null, 0, null, true)] },
    { name: "mean", params: [] },
    { name: "moving-average", params: [param("window", "int", 28, 1, 365)] },
    { name: "seasonal-linear", params: [param("period", "int", 7, 2, 28)] },
    { name: "seasonal-naive", params: [param("period", "int", 7, 1, 28)] },
  ],
  limits: { max_forecasters: 3, max_horizon: 56, max_origins: 12, min_history: 28 },
  benchmark: { params: [param("n_skus", "int", 200, 10, 400), param("seed", "int", null, 0, null, true)] },
};
const CATALOG = CATALOG_BASE;

test("the default request is the fast built-ins on the world, 14 days, 4 origins, 80 %", () => {
  assert.deepEqual(defaultForecastRequest(CATALOG), {
    forecasters: ["seasonal-naive", "moving-average", "seasonal-linear"],
    params: {},
    source: "world",
    benchmark: { n_skus: 200, seed: null },
    horizon: 14,
    origins: 4,
    level: 0.8,
  });
  const only = { ...CATALOG, forecasters: [CATALOG.forecasters[0], CATALOG.forecasters[1]] };
  assert.deepEqual(defaultForecastRequest(only).forecasters, ["gradient-boosting", "mean"]); // none preferred: the catalogue
});

test("a request from a link keeps what the catalogue offers and names what it dropped", () => {
  const { request, dropped } = fitForecastRequest(
    {
      forecasters: ["mean", "prophet", "mean"],
      params: { mean: {}, "moving-average": { window: 7, span: 3 }, prophet: { x: 1 } },
      source: "benchmark",
      benchmark: { n_skus: 50, extra: 1 },
      horizon: 21,
      origins: 2,
      level: 0.9,
    },
    CATALOG,
  );
  assert.deepEqual(dropped, ["prophet", "moving-average.span"]);
  assert.deepEqual(request, {
    forecasters: ["mean"],
    params: { "moving-average": { window: 7 } },
    source: "benchmark",
    benchmark: { n_skus: 50, seed: null },
    horizon: 21,
    origins: 2,
    level: 0.9,
  });
  assert.equal(fitForecastRequest({ level: 0.42, source: "elsewhere" }, CATALOG).request.level, 0.8);
  assert.deepEqual(fitForecastRequest({ level: "0.9" }, CATALOG).dropped, ['level "0.9"']); // named, not changed silently
  assert.equal(fitForecastRequest({ source: "elsewhere" }, CATALOG).request.source, "world");
  assert.deepEqual(fitForecastRequest([], CATALOG), { request: defaultForecastRequest(CATALOG), dropped: [] });
  assert.deepEqual(fitForecastRequest({ forecasters: ["prophet"] }, CATALOG).request.forecasters, defaultForecastRequest(CATALOG).forecasters);
});

test("a request is checked against the published limits and bounds before it is sent", () => {
  const ok = defaultForecastRequest(CATALOG);
  assert.equal(forecastRequestError(ok, CATALOG), null);
  assert.equal(forecastRequestError({ ...ok, forecasters: [] }, CATALOG), "Choose at least one forecaster.");
  assert.equal(forecastRequestError({ ...ok, forecasters: ["mean", "seasonal-naive", "moving-average", "seasonal-linear"] }, CATALOG), "At most 3 forecasters.");
  assert.equal(forecastRequestError({ ...ok, params: { "moving-average": { window: 0 } } }, CATALOG), "moving-average window: from 1 to 365.");
  assert.equal(forecastRequestError({ ...ok, params: { "moving-average": { window: "x" } } }, CATALOG), "moving-average window: enter a number.");
  assert.equal(forecastRequestError({ ...ok, params: { mean: { window: 0 } } }, CATALOG), null); // not among the chosen
  assert.equal(forecastRequestError({ ...ok, horizon: 57 }, CATALOG), "Horizon must be a whole number from 1 to 56.");
  assert.equal(forecastRequestError({ ...ok, origins: 1.5 }, CATALOG), "Origins must be a whole number from 1 to 12.");
  assert.equal(forecastRequestError({ ...ok, source: "benchmark", benchmark: { n_skus: 5, seed: null } }, CATALOG), "Benchmark n skus: from 10 to 400.");
  assert.equal(forecastRequestError({ ...ok, benchmark: { n_skus: 5, seed: null } }, CATALOG), null); // the world ignores it
  // a number field holding text that is not a number: refused, even where the parameter may be none
  const bench = { ...ok, source: "benchmark", benchmark: { n_skus: 200, seed: NaN } };
  assert.equal(forecastRequestError(bench, CATALOG), "Benchmark seed: enter a number.");
  assert.equal(forecastRequestError({ ...ok, forecasters: ["gradient-boosting"], params: { "gradient-boosting": { seed: NaN } } }, CATALOG),
    "gradient-boosting seed: enter a number.");
  assert.equal(forecastRequestError({ ...ok, params: { "moving-average": { window: NaN } } }, CATALOG), "moving-average window: enter a number.");
});

test("the backtest body carries the chosen forecasters' parameters, the source and the interval's quantiles", () => {
  const request = {
    ...defaultForecastRequest(CATALOG),
    params: { "moving-average": { window: 7 }, mean: { x: 1 }, "seasonal-naive": {} },
  };
  assert.deepEqual(backtestBody(request), {
    forecasters: ["seasonal-naive", "moving-average", "seasonal-linear"],
    params: { "moving-average": { window: 7 } },
    source: { world: {} },
    horizon: 14,
    origins: 4,
    step: 7,
    quantiles: [0.1, 0.5, 0.9],
  });
  assert.deepEqual(backtestBody({ ...request, source: "benchmark" }).source, { benchmark: { n_skus: 200, seed: null } });
  assert.deepEqual(levelQuantiles(0.95), [0.025, 0.5, 0.975]);
  assert.deepEqual(levelQuantiles(0.5), [0.25, 0.5, 0.75]);
  assert.deepEqual([0.1, 0.025, 0.5, 0.975].map(quantileField), ["q10", "q2_5", "q50", "q97_5"]);
});

test("the address holds the request, and a bad one says why", () => {
  const request = defaultForecastRequest(CATALOG);
  assert.deepEqual(readForecastHash(forecastHash(request)), { request });
  assert.deepEqual(readForecastHash(""), {});
  assert.deepEqual(readForecastHash("#backtest"), {});
  assert.deepEqual(readForecastHash("#backtest=%7Bnope"), { error: "the request in this link is not valid JSON" });
  assert.deepEqual(readForecastHash("#backtest=" + encodeURIComponent("[1]")), { error: "the link holds no request" });
});

const RESPONSE = {
  scores: {
    fields: [{ name: "forecaster" }, { name: "wape" }, { name: "seconds" }, { name: "error" }],
    rows: [
      ["mean", 0.9, 0.01, null], ["broken", null, 0.2, "boom"], ["late", null, null, "not run: the time budget ran out"],
      ["slow", null, 31.2, "not finished: the time budget ran out"], [REFERENCE, 0.8, null, null],
    ],
  },
  by_horizon: {
    fields: [{ name: "forecaster" }, { name: "days_ahead" }, { name: "wape" }],
    rows: [["mean", 2, 0.95], ["mean", 1, 0.85], [REFERENCE, 1, 0.8]],
  },
  forecasts: {
    fields: [{ name: "sku_id" }, { name: "date" }, { name: "forecaster" }, { name: "actual" }, { name: "mean" }, { name: "q10" }, { name: "q50" }, { name: "q90" }],
    rows: [
      ["S2", "2025-01-02", "mean", 3, 2.5, 1, 2, 4],
      ["S2", "2025-01-01", "mean", 1, 2.4, 0.5, 2, 4.5],
      ["S1", "2025-01-01", "mean", 0, 1, 0, 1, 2],
      ["S2", "2025-01-01", REFERENCE, 1, 2, 0, 2, 5],
    ],
  },
};

test("the tables are read as the server wrote them, the page computes no score", () => {
  assert.deepEqual(tableRecords(RESPONSE.scores)[0], { forecaster: "mean", wape: 0.9, seconds: 0.01, error: null });
  assert.deepEqual(tableRecords(RESPONSE.scores).map(scoreReading), ["scored", "error", "not run", "not finished", "reference"]);
  assert.deepEqual(wapeByHorizon(RESPONSE), {
    days: [1, 2],
    series: [{ name: "mean", values: [0.85, 0.95] }, { name: REFERENCE, values: [0.8, null] }],
  });
  assert.deepEqual(forecastSkus(RESPONSE), ["S2", "S1"]);
  assert.deepEqual(skuForecasts(RESPONSE, "S2", [0.1, 0.5, 0.9]), [
    { forecaster: "mean", days: ["2025-01-01", "2025-01-02"], mean: [2.4, 2.5], actual: [1, 3], low: [0.5, 1], high: [4.5, 4] },
    { forecaster: REFERENCE, days: ["2025-01-01", "2025-01-02"], mean: [2, null], actual: [1, null], low: [0, null], high: [5, null] },
  ]);
});

test("colours follow the catalogue order, and Explore repeats the backtest body", () => {
  const colors = forecasterColors(["a", "b", "c"], ["#1", "#2"], "#grey");
  assert.deepEqual([...colors], [["a", "#1"], ["b", "#2"], ["c", "#grey"]]);
  const request = defaultForecastRequest(CATALOG);
  const link = forecastsLink(request, "by_horizon");
  const view = JSON.parse(decodeURIComponent(link.replace("explore.html#view=", "")));
  assert.deepEqual(view, { source: { forecasts: { request: backtestBody(request), table: "by_horizon" } } });
});

test("a benchmark too short for the backtest is refused before it is sent, as the server would", () => {
  const catalog = { ...CATALOG, benchmark: { params: [...CATALOG.benchmark.params, param("days", "int", 365, 84, 730)] } };
  const request = { ...defaultForecastRequest(catalog), source: "benchmark", horizon: 56, origins: 4 };
  // the server's rule (analytics/forecasters/backtest.py): horizon + (origins - 1) × 7 + min_history days
  assert.equal(forecastRequestError({ ...request, benchmark: { ...request.benchmark, days: 104 } }, catalog),
    "The benchmark's 104 days are too few: 56 days ahead, 4 origins 7 days apart and 28 days before the first need 105.");
  assert.equal(forecastRequestError({ ...request, benchmark: { ...request.benchmark, days: 105 } }, catalog), null);
});
