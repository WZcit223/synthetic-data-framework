// Pure helpers of the Forecasts page (no DOM), so Node's test runner covers them. Every score,
// interval and bound comes from POST /forecasts/backtest and GET /forecasters; these helpers
// only read, check and lay them out. Contract: docs/refactor/algorithms/interfaces.md §8.
import { OTHER, SERIES } from "./palette.js";
import { readParam } from "./synthesis.js";

export const LEVELS = [0.5, 0.8, 0.9, 0.95]; // the central interval's probability, as the page offers it
export const STEP = 7; // days between origins: the backtest's default, not offered on the page
export const REFERENCE = "true-distribution"; // the benchmark's own row: the exact distribution it drew from
export const FORECAST_TABLES = ["scores", "by_horizon", "forecasts"];
const PREFERRED = ["seasonal-naive", "moving-average", "seasonal-linear"]; // fast: a first backtest answers in a second

// Each forecaster's colour follows its place in the catalogue, never its place on screen; past eight, grey.
export function forecasterColors(names, series = SERIES, other = OTHER) {
  return new Map(names.map((n, i) => [n, i < series.length ? series[i] : other]));
}

// The quantiles of a central interval: its two ends and the median, as the backtest takes them.
export const levelQuantiles = level => [(1 - level) / 2, 0.5, (1 + level) / 2].map(q => Number(q.toFixed(4)));

// A quantile's column in the forecasts table, as the backtest names it: 0.1 → "q10", 0.025 → "q2_5".
export const quantileField = q => "q" + String(Number((q * 100).toPrecision(6))).replace(".", "_");

const benchmarkDefaults = catalog => Object.fromEntries(catalog.benchmark.params.map(p => [p.name, p.default]));

// The request the page starts from: the fast built-ins that are mounted, on the current world, 14 days, 4 origins, 80 %.
export function defaultForecastRequest(catalog) {
  const names = catalog.forecasters.map(f => f.name);
  const preferred = PREFERRED.filter(n => names.includes(n));
  return {
    forecasters: (preferred.length ? preferred : names).slice(0, catalog.limits.max_forecasters),
    params: {},
    source: "world",
    benchmark: benchmarkDefaults(catalog),
    horizon: 14,
    origins: 4,
    level: 0.8,
  };
}

const isObject = v => v != null && typeof v === "object" && !Array.isArray(v);

/**
 * A request read from a link, fitted to the catalogue: forecasters not mounted, and parameters
 * a forecaster does not take, are dropped and named in ``dropped``; anything missing falls back
 * to the default. Values are kept as given, so the form shows them and the check names a bad one.
 */
export function fitForecastRequest(raw, catalog) {
  const base = defaultForecastRequest(catalog);
  if (!isObject(raw)) return { request: base, dropped: [] };
  const dropped = [];
  const byName = new Map(catalog.forecasters.map(f => [f.name, f]));
  let forecasters = base.forecasters;
  if (Array.isArray(raw.forecasters)) {
    const kept = [...new Set(raw.forecasters.filter(n => byName.has(n)))];
    dropped.push(...raw.forecasters.filter(n => !byName.has(n)).map(String));
    if (kept.length) forecasters = kept;
  }
  const params = {};
  if (isObject(raw.params)) {
    for (const [name, given] of Object.entries(raw.params)) {
      if (!byName.has(name) || !isObject(given)) continue; // a forecaster not mounted is named above
      const takes = new Set(byName.get(name).params.map(p => p.name));
      const kept = Object.fromEntries(Object.entries(given).filter(([k]) => takes.has(k)));
      dropped.push(...Object.keys(given).filter(k => !takes.has(k)).map(k => `${name}.${k}`));
      if (Object.keys(kept).length) params[name] = kept;
    }
  }
  const benchmark = { ...base.benchmark };
  if (isObject(raw.benchmark)) {
    for (const p of catalog.benchmark.params) if (raw.benchmark[p.name] !== undefined) benchmark[p.name] = raw.benchmark[p.name];
  }
  return {
    request: {
      forecasters,
      params,
      source: raw.source === "benchmark" ? "benchmark" : "world",
      benchmark,
      horizon: raw.horizon ?? base.horizon,
      origins: raw.origins ?? base.origins,
      level: LEVELS.includes(raw.level) ? raw.level : base.level,
    },
    dropped,
  };
}

const whole = (name, v, lo, hi) =>
  Number.isInteger(v) && v >= lo && v <= hi ? null : `${name} must be a whole number from ${lo} to ${hi}.`;

// Why a request cannot be sent, or null: the checks the endpoint makes, from the published bounds.
export function forecastRequestError(request, catalog) {
  if (!request.forecasters.length) return "Choose at least one forecaster.";
  const lim = catalog.limits;
  if (request.forecasters.length > lim.max_forecasters) return `At most ${lim.max_forecasters} forecasters.`;
  const byName = new Map(catalog.forecasters.map(f => [f.name, f]));
  for (const name of request.forecasters) {
    for (const p of byName.get(name)?.params ?? []) {
      const given = request.params[name]?.[p.name];
      if (given === undefined) continue; // left out: the forecaster's own default
      const read = readParam(p, given === null ? "" : typeof given === "boolean" ? given : String(given));
      if (read.error) return `${name} ${read.error.replaceAll("_", " ")}.`;
    }
  }
  const problem = whole("Horizon", request.horizon, 1, lim.max_horizon) ?? whole("Origins", request.origins, 1, lim.max_origins);
  if (problem) return problem;
  if (request.source === "benchmark") {
    for (const p of catalog.benchmark.params) {
      const v = request.benchmark[p.name];
      const read = readParam(p, v == null ? "" : String(v));
      if (read.error) return `Benchmark ${read.error.replaceAll("_", " ")}.`;
    }
  }
  return null;
}

// The POST /forecasts/backtest body for a request.
export function backtestBody(request) {
  const params = Object.fromEntries(
    request.forecasters.filter(n => request.params[n] && Object.keys(request.params[n]).length).map(n => [n, request.params[n]]),
  );
  return {
    forecasters: [...request.forecasters],
    params,
    source: request.source === "benchmark" ? { benchmark: { ...request.benchmark } } : { world: {} },
    horizon: request.horizon,
    origins: request.origins,
    step: STEP,
    quantiles: levelQuantiles(request.level),
  };
}

// The page's address for a request, so a link reproduces the backtest.
export const forecastHash = request => "#backtest=" + encodeURIComponent(JSON.stringify(request));

// The request an address holds, {error} when it cannot be read, or {} for none.
export function readForecastHash(hash) {
  const m = /^#backtest(?:=(.*))?$/.exec(hash);
  if (!m || !m[1]) return {};
  try {
    const v = JSON.parse(decodeURIComponent(m[1]));
    return isObject(v) ? { request: v } : { error: "the link holds no request" };
  } catch {
    return { error: "the request in this link is not valid JSON" };
  }
}

// A {fields, rows} table as one object per row, keyed by field name.
export function tableRecords({ fields, rows }) {
  return rows.map(r => Object.fromEntries(fields.map((f, i) => [f.name, r[i]])));
}

// How a score row reads: an error, a forecaster not run in time, the reference, or scored.
export function scoreReading(row) {
  if (row.error) return row.wape == null && row.seconds == null ? "not run" : "error";
  if (row.forecaster === REFERENCE) return "reference";
  return "scored";
}

/**
 * WAPE by days ahead: the days as labels and one series per forecaster (the reference
 * included), each value read from the by-horizon table; the page computes no score itself.
 */
export function wapeByHorizon(response) {
  const rows = tableRecords(response.by_horizon);
  const days = [...new Set(rows.map(r => r.days_ahead))].sort((a, b) => a - b);
  const names = [...new Set(rows.map(r => r.forecaster))];
  return {
    days,
    series: names.map(name => ({
      name,
      values: days.map(d => rows.find(r => r.forecaster === name && r.days_ahead === d)?.wape ?? null),
    })),
  };
}

// The SKUs of the last origin's forecasts, in the order the table gives them.
export const forecastSkus = response => [...new Set(tableRecords(response.forecasts).map(r => r.sku_id))];

/**
 * One SKU after the last origin, per forecaster: the days, the forecaster's mean, the actual
 * demand, and its interval (the lowest and highest quantile the request asked for).
 */
export function skuForecasts(response, sku, quantiles) {
  const rows = tableRecords(response.forecasts).filter(r => r.sku_id === sku);
  const days = [...new Set(rows.map(r => r.date))].sort();
  const low = quantileField(Math.min(...quantiles));
  const high = quantileField(Math.max(...quantiles));
  const names = [...new Set(rows.map(r => r.forecaster))];
  return names.map(name => {
    const at = d => rows.find(r => r.forecaster === name && r.date === d);
    return {
      forecaster: name,
      days,
      mean: days.map(d => at(d)?.mean ?? null),
      actual: days.map(d => at(d)?.actual ?? null),
      low: days.map(d => at(d)?.[low] ?? null),
      high: days.map(d => at(d)?.[high] ?? null),
    };
  });
}

// The link that opens one of the backtest's tables in Explore, which repeats the request.
export function forecastsLink(request, table) {
  return "explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { forecasts: { request: backtestBody(request), table } } }));
}
